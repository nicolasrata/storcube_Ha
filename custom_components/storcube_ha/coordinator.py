"""Coordinateur de données pour l'intégration Storcube Battery Monitor."""
import asyncio
import logging
from datetime import timedelta, datetime
import json
import websockets
import aiohttp

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.typing import ConfigType
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_USERNAME,
    CONF_PASSWORD,
)
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import storage

from .const import (
    DOMAIN,
    NAME,
    CONF_DEVICE_ID,
    CONF_APP_CODE,
    CONF_LOGIN_NAME,
    CONF_AUTH_PASSWORD,
    DEFAULT_PORT,
    DEFAULT_APP_CODE,
    WS_URI,
    TOKEN_URL,
    FIRMWARE_URL,
    OUTPUT_URL,
    SET_POWER_URL,
    SET_THRESHOLD_URL,
)
from .firmware import StorCubeFirmwareManager

_LOGGER = logging.getLogger(__name__)

class StorCubeDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching StorCube data."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None, # On gère nos propres boucles
        )
        self.config_entry = config_entry
        self.data = {
            "websocket": {},
            "rest_api": {},
            "firmware": {},
            "last_ws_update": None,
            "last_rest_update": None,
            "ws_connected": False,
        }
        self.hass = hass
        self._auth_token = None
        self._ws_task = None
        self._rest_task = None
        self._firmware_task = None
        self._device_id = config_entry.data[CONF_DEVICE_ID]
        self._session = None
        
        self.firmware_manager = StorCubeFirmwareManager(
            hass=hass,
            device_id=self._device_id,
            login_name=config_entry.data[CONF_LOGIN_NAME],
            auth_password=config_entry.data[CONF_AUTH_PASSWORD],
            app_code=config_entry.data.get(CONF_APP_CODE, DEFAULT_APP_CODE)
        )

    async def get_auth_token(self, force_refresh=False):
        """Récupérer le token d'authentification."""
        if self._auth_token and not force_refresh:
            return self._auth_token

        storage_key = f"{DOMAIN}_auth_token_{self.config_entry.entry_id}"
        store = storage.Store(self.hass, 1, storage_key)

        if not force_refresh:
            token_data = await store.async_load()
            if token_data and isinstance(token_data, dict) and "token" in token_data:
                self._auth_token = token_data["token"]
                return self._auth_token

        try:
            token_credentials = {
                "appCode": self.config_entry.data.get(CONF_APP_CODE, DEFAULT_APP_CODE),
                "loginName": self.config_entry.data[CONF_LOGIN_NAME],
                "password": self.config_entry.data[CONF_AUTH_PASSWORD]
            }
            
            headers = {'Content-Type': 'application/json'}
            if not self._session:
                self._session = aiohttp.ClientSession()

            async with self._session.post(TOKEN_URL, json=token_credentials, headers=headers, timeout=10) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get('code') == 200:
                    self._auth_token = data['data']['token']
                    await store.async_save({"token": self._auth_token})
                    return self._auth_token
                raise Exception(f"Erreur d'authentification: {data.get('message', 'Réponse inconnue')}")
        except Exception as e:
            _LOGGER.error("Erreur lors de la récupération du token: %s", str(e))
            return None

    async def async_setup(self):
        """Set up the coordinator."""
        _LOGGER.info("Configuration du coordinateur StorCube...")

        # Initialiser la session
        self._session = aiohttp.ClientSession()

        # Premier essai d'obtention du token
        if not await self.get_auth_token():
            _LOGGER.error("Impossible d'obtenir le token initial")

        # Démarrer les boucles de mise à jour
        self._ws_task = asyncio.create_task(self._websocket_loop())
        self._rest_task = asyncio.create_task(self._rest_loop())
        self._firmware_task = asyncio.create_task(self._firmware_loop())
        
        return True

    async def _websocket_loop(self):
        """Boucle de connexion WebSocket."""
        while True:
            try:
                token = await self.get_auth_token()
                if not token:
                    await asyncio.sleep(30)
                    continue

                uri = f"{WS_URI}{token}"
                websocket_headers = {
                    "Authorization": token,
                    "Content-Type": "application/json",
                    "user-agent": "Mozilla/5.0"
                }

                async with websockets.connect(
                    uri,
                    additional_headers=websocket_headers,
                    ping_interval=15,
                    ping_timeout=5
                ) as websocket:
                    _LOGGER.info("WebSocket connecté")
                    self.data["ws_connected"] = True

                    # Demander les rapports pour notre appareil
                    request_data = {"reportEquip": [self._device_id]}
                    await websocket.send(json.dumps(request_data))

                    while True:
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=35)
                            if not message.strip():
                                continue
                                
                            json_data = json.loads(message)
                            if json_data == "SUCCESS":
                                continue

                            if isinstance(json_data, dict):
                                # Extraction des données pour notre device
                                device_data = None
                                if self._device_id in json_data:
                                    device_data = json_data[self._device_id]
                                elif "list" in json_data:
                                    # Format alternatif
                                    device_data = json_data
                                else:
                                    # Essayer de trouver dans les valeurs
                                    for val in json_data.values():
                                        if isinstance(val, dict) and val.get("equipId") == self._device_id:
                                            device_data = val
                                            break

                                if device_data:
                                    _LOGGER.debug("Données WebSocket reçues pour %s", self._device_id)
                                    self.data["websocket"] = device_data
                                    self.data["last_ws_update"] = datetime.now()
                                    self._notify_sensors({"websocket_data": device_data})

                        except asyncio.TimeoutError:
                            # Heartbeat si pas de message
                            await websocket.send(json.dumps(request_data))
                        except json.JSONDecodeError:
                            _LOGGER.warning("Erreur décodage JSON WebSocket")
                        except Exception as e:
                            _LOGGER.error("Erreur dans la réception WebSocket: %s", e)
                            break

            except Exception as e:
                _LOGGER.error("Erreur connexion WebSocket: %s", e)
                self.data["ws_connected"] = False
                self._auth_token = None # Forcer rafraîchissement token au prochain tour
            
            _LOGGER.info("Reconnexion WebSocket dans 10 secondes...")
            self.data["ws_connected"] = False
            await asyncio.sleep(10)

    async def _rest_loop(self):
        """Boucle de mise à jour REST (fallback et données complémentaires)."""
        while True:
            try:
                # Intervalle dynamique : 15s si WS déconnecté (pour le fallback), 30s si WS connecté
                interval = 15 if not self.data["ws_connected"] else 30
                
                token = await self.get_auth_token()
                if token:
                    headers = {
                        "Authorization": token,
                        "Content-Type": "application/json",
                        "appCode": self.config_entry.data.get(CONF_APP_CODE, DEFAULT_APP_CODE)
                    }
                    output_url = f"{OUTPUT_URL}{self._device_id}"

                    if not self._session:
                        self._session = aiohttp.ClientSession()

                    try:
                        async with self._session.get(output_url, headers=headers, timeout=5) as response:
                            if response.status == 200:
                                res_json = await response.json()
                                if res_json.get("code") == 200 and res_json.get("data"):
                                    scene_data = res_json["data"][0]
                                    _LOGGER.debug("Données REST reçues pour %s", self._device_id)
                                    self.data["rest_api"] = scene_data
                                    self.data["last_rest_update"] = datetime.now()
                                    self._notify_sensors({"rest_data": scene_data})
                            elif response.status == 401:
                                _LOGGER.warning("Token expiré, tentative de rafraîchissement...")
                                self._auth_token = None
                            elif response.status == 404:
                                _LOGGER.warning("API REST Scènes (404) indisponible pour %s", self._device_id)
                            else:
                                _LOGGER.debug("Erreur API REST : %s", response.status)
                    except asyncio.TimeoutError:
                        _LOGGER.debug("Timeout API REST pour %s, on continue...", self._device_id)

            except Exception as e:
                _LOGGER.error("Erreur boucle REST: %s", e)
            
            await asyncio.sleep(interval)

    async def _firmware_loop(self):
        """Boucle de mise à jour firmware (très lent)."""
        while True:
            try:
                _LOGGER.info("Vérification firmware...")
                info = await self.firmware_manager.check_firmware_upgrade()
                if info:
                    self.data["firmware"] = {
                        "current_version": info.get("current_version", "Inconnue"),
                        "latest_version": info.get("latest_version", "Inconnue"),
                        "upgrade_available": info.get("upgrade_available", False),
                        "firmware_notes": info.get("firmware_notes", []),
                        "last_check": datetime.now().isoformat()
                    }
                    self._notify_sensors({"firmware": self.data["firmware"]})
            except Exception as e:
                _LOGGER.error("Erreur vérification firmware: %s", e)
            
            await asyncio.sleep(3600) # Toutes les heures

    def _notify_sensors(self, payload):
        """Notifier les capteurs des nouvelles données."""
        if DOMAIN in self.hass.data and self.config_entry.entry_id in self.hass.data[DOMAIN]:
            sensors = self.hass.data[DOMAIN][self.config_entry.entry_id].get("sensors", [])
            for sensor in sensors:
                if hasattr(sensor, 'handle_state_update'):
                    sensor.handle_state_update(payload)

    async def async_shutdown(self):
        """Arrêter le coordinateur."""
        for task in [self._ws_task, self._rest_task, self._firmware_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self._session:
            await self._session.close()

    async def set_power_value(self, value):
        """Modifier la puissance."""
        token = await self.get_auth_token()
        if not token or not self._session: return False
        headers = {"Authorization": token, "Content-Type": "application/json", "appCode": self.config_entry.data.get(CONF_APP_CODE, DEFAULT_APP_CODE)}
        params = {"equipId": self._device_id, "power": int(value)}
        async with self._session.get(SET_POWER_URL, headers=headers, params=params, timeout=10) as resp:
            return (await resp.json()).get("code") == 200

    async def set_threshold_value(self, value):
        """Modifier le seuil."""
        token = await self.get_auth_token()
        if not token or not self._session: return False
        headers = {"Authorization": token, "Content-Type": "application/json", "appCode": self.config_entry.data.get(CONF_APP_CODE, DEFAULT_APP_CODE)}
        payload = {"reserved": str(value), "equipId": self._device_id}
        async with self._session.post(SET_THRESHOLD_URL, headers=headers, json=payload, timeout=10) as resp:
            return (await resp.json()).get("code") == 200

    async def check_firmware_upgrade(self):
        """Force check firmware."""
        return await self.firmware_manager.check_firmware_upgrade()

"""Capteur binaire pour l'intégration Storcube Battery Monitor."""
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, ICON_CONNECTION

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurer le capteur binaire basé sur une entrée de configuration."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    device_id = config_entry.data[CONF_DEVICE_ID]

    async_add_entities([StorCubeBatteryConnectionSensor(coordinator, device_id)])

class StorCubeBatteryConnectionSensor(BinarySensorEntity):
    """Capteur binaire pour l'état de la connexion de la batterie."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = ICON_CONNECTION
    _attr_has_entity_name = True

    def __init__(self, coordinator, device_id: str) -> None:
        """Initialiser le capteur."""
        self.coordinator = coordinator
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_connection"
        self._attr_name = "Statut Connexion"

    @property
    def device_info(self) -> DeviceInfo:
        """Retourner les informations sur l'appareil."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=f"Batterie StorCube {self._device_id}",
            manufacturer="StorCube",
        )

    @property
    def is_on(self) -> bool:
        """Retourner l'état de la connexion."""
        # On considère connecté si le WebSocket est actif ou si on a eu une mise à jour REST récente
        ws_connected = self.coordinator._internal_data.get("ws_connected", False)
        if ws_connected:
            return True

        last_rest = self.coordinator._internal_data.get("last_rest_update")
        if last_rest:
            # Si on a eu une mise à jour REST il y a moins de 60s, on considère comme connecté
            from datetime import datetime
            return (datetime.now() - last_rest).total_seconds() < 60

        return False

    @property
    def should_poll(self) -> bool:
        return False

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @callback
    def handle_state_update(self, payload: dict) -> None:
        """Gérer la mise à jour de l'état depuis le coordinateur."""
        self.async_write_ha_state()

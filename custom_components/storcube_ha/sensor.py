"""Support for Storcube Battery Monitor sensors."""
from __future__ import annotations

import logging
import json
import asyncio
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE_ID,
    PERCENTAGE,
    UnitOfPower,
    UnitOfEnergy,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Seuil pour considérer les données WebSocket comme obsolètes (60 secondes)
WS_STALE_THRESHOLD = 60

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    config = config_entry.data
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    sensors = [
        StorcubeBatteryLevelSensor(config, coordinator),
        StorcubeBatteryPowerSensor(config, coordinator),
        StorcubeBatteryTemperatureSensor(config, coordinator),
        StorcubeBatteryCapacityWhSensor(config, coordinator),
        StorcubeBatteryStatusSensor(config, coordinator),
        StorcubeBatteryThresholdSensor(config, coordinator),
        StorcubeSolarPowerSensor(config, coordinator),
        StorcubeSolarEnergySensor(config, coordinator),
        StorcubeSolarPowerSensor2(config, coordinator),
        StorcubeSolarEnergySensor2(config, coordinator),
        StorcubeSolarEnergyTotalSensor(config, coordinator),
        StorcubeOutputPowerSensor(config, coordinator),
        StorcubeOutputEnergySensor(config, coordinator),
        StorcubeStatusSensor(config, coordinator),
        StorcubeModelSensor(config, coordinator),
        StorcubeSerialNumberSensor(config, coordinator),
        StorcubeOutputTypeSensor(config, coordinator),
        StorcubeReservedSensor(config, coordinator),
        StorcubeWorkStatusSensor(config, coordinator),
        StorcubeOnlineSensor(config, coordinator),
        StorcubeErrorCodeSensor(config, coordinator),
        StorcubeFirmwareSensor(config, coordinator),
        StorcubeOperatingModeSensor(config, coordinator),
    ]

    async_add_entities(sensors)
    hass.data[DOMAIN][config_entry.entry_id]["sensors"] = sensors

class StorcubeBatterySensor(SensorEntity):
    """Capteur pour les données de la batterie solaire."""

    _attr_has_entity_name = True

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        self._config = config
        self.coordinator = coordinator
        self._websocket_data = {}
        self._rest_data = {}
        self._attr_native_value = None
        self._device_id = config[CONF_DEVICE_ID]

    @property
    def should_poll(self) -> bool:
        """No polling needed, the coordinator pushes updates."""
        return False

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._update_value_from_sources()

    @callback
    def handle_state_update(self, payload: dict[str, Any]) -> None:
        """Gérer la mise à jour de l'état depuis le coordinateur."""
        try:
            if "websocket_data" in payload:
                self._websocket_data = payload["websocket_data"]
            elif "rest_data" in payload:
                self._rest_data = payload["rest_data"]

            self._update_value_from_sources()
            self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error("Erreur lors de la mise à jour du capteur %s: %s", self.name, str(e))

    def _is_ws_fresh(self):
        """Vérifie si les données WebSocket sont récentes."""
        last_ws = self.coordinator.data.get("last_ws_update")
        if not last_ws:
            return False
        return (datetime.now() - last_ws).total_seconds() < WS_STALE_THRESHOLD

    def _update_value_from_sources(self):
        """Mettre à jour la valeur en fonction des sources disponibles."""
        pass

class StorcubeBatteryLevelSensor(StorcubeBatterySensor):
    """Représentation du niveau de la batterie."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialiser le capteur."""
        super().__init__(config, coordinator)
        self._attr_name = "Niveau Batterie"
        self._attr_native_unit_of_measurement = "%"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = f"{self._device_id}_battery_level"
        self._attr_icon = "mdi:battery-high"

    def _update_value_from_sources(self):
        try:
            if self._is_ws_fresh() and "soc" in self._websocket_data:
                soc = self._websocket_data.get("soc")
                if isinstance(soc, (int, float)) and soc > 0:
                    self._attr_native_value = soc
            elif self._rest_data and "soc" in self._rest_data:
                soc = self._rest_data.get("soc")
                if isinstance(soc, (int, float)) and soc > 0:
                    self._attr_native_value = soc
        except Exception as e:
            _LOGGER.error("Error updating battery level: %s", e)

class StorcubeBatteryPowerSensor(StorcubeBatterySensor):
    """Représentation de la puissance de la batterie."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Puissance Batterie"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = f"{self._device_id}_battery_power"

    def _update_value_from_sources(self):
        try:
            if self._is_ws_fresh():
                self._attr_native_value = self._websocket_data.get("invPower")
            elif self._rest_data:
                self._attr_native_value = self._rest_data.get("outputPower")
        except Exception as e:
            _LOGGER.error("Error updating battery power: %s", e)

class StorcubeBatteryThresholdSensor(StorcubeBatterySensor):
    """Représentation du seuil de la batterie."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Seuil Batterie"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = f"{self._device_id}_battery_threshold"
        self._attr_icon = "mdi:battery-charging-medium"

    def _update_value_from_sources(self):
        try:
            if self._is_ws_fresh() and "reserved" in self._websocket_data:
                self._attr_native_value = self._websocket_data.get("reserved")
            elif self._rest_data and "reserved" in self._rest_data:
                self._attr_native_value = self._rest_data.get("reserved")
        except Exception as e:
            _LOGGER.error("Error updating battery threshold: %s", e)

class StorcubeBatteryTemperatureSensor(StorcubeBatterySensor):
    """Représentation de la température de la batterie."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Température Batterie"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = f"{self._device_id}_battery_temperature"

    def _update_value_from_sources(self):
        try:
            if self._is_ws_fresh():
                self._attr_native_value = self._websocket_data.get("temp")
            elif self._rest_data:
                self._attr_native_value = self._rest_data.get("temp")
        except Exception as e:
            _LOGGER.error("Error updating battery temperature: %s", e)

class StorcubeBatteryCapacityWhSensor(StorcubeBatterySensor):
    """Représentation de la capacité de la batterie en Wh."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialiser le capteur."""
        super().__init__(config, coordinator)
        self._attr_name = "Capacité Batterie (Wh)"
        self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY_STORAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = f"{self._device_id}_battery_capacity_wh"
        self._attr_icon = "mdi:battery-charging"

    def _update_value_from_sources(self):
        try:
            if self._is_ws_fresh():
                self._attr_native_value = self._websocket_data.get("capacity")
            elif self._rest_data:
                self._attr_native_value = self._rest_data.get("capacity")
        except Exception as e:
            _LOGGER.error("Error updating battery capacity: %s", e)

class StorcubeBatteryStatusSensor(StorcubeBatterySensor):
    """Représentation de l'état de la batterie."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "État Batterie"
        self._attr_unique_id = f"{self._device_id}_battery_status"

    def _update_value_from_sources(self):
        try:
            is_work = None
            if self._is_ws_fresh():
                is_work = self._websocket_data.get("isWork")
            elif self._rest_data:
                is_work = self._rest_data.get("workStatus")

            if is_work is not None:
                self._attr_native_value = 'online' if is_work == 1 else 'offline'
        except Exception as e:
            _LOGGER.error("Error updating battery status: %s", e)

class StorcubeSolarPowerSensor(StorcubeBatterySensor):
    """Représentation de la puissance solaire."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Puissance Solaire"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = f"{self._device_id}_solar_power"
        self._attr_icon = "mdi:solar-power"

    def _update_value_from_sources(self):
        try:
            if self._is_ws_fresh() and "pv1power" in self._websocket_data:
                self._attr_native_value = self._websocket_data.get("pv1power")
            elif self._rest_data:
                self._attr_native_value = self._rest_data.get("pv1power")
        except Exception as e:
            _LOGGER.error("Error updating solar power: %s", e)

class StorcubeSolarPowerSensor2(StorcubeBatterySensor):
    """Représentation de la puissance solaire du deuxième panneau."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Puissance Solaire 2"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = f"{self._device_id}_solar_power_2"
        self._attr_icon = "mdi:solar-power"

    def _update_value_from_sources(self):
        try:
            if self._is_ws_fresh() and "pv2power" in self._websocket_data:
                self._attr_native_value = self._websocket_data.get("pv2power")
            elif self._rest_data:
                self._attr_native_value = self._rest_data.get("pv2power")
        except Exception as e:
            _LOGGER.error("Error updating solar power 2: %s", e)

class StorcubeSolarEnergySensor(StorcubeBatterySensor):
    """Représentation de l'énergie solaire produite."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Énergie Solaire"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_unique_id = f"{self._device_id}_solar_energy"
        self._last_power = 0
        self._last_update_time = None
        self._attr_native_value = 0

    def _update_value_from_sources(self):
        try:
            current_power = 0
            if self._is_ws_fresh():
                current_power = self._websocket_data.get("pv1power", 0)
            elif self._rest_data:
                current_power = self._rest_data.get("pv1power", 0)

            current_time = datetime.now()
            if self._last_update_time is not None and current_power > 0:
                time_diff = (current_time - self._last_update_time).total_seconds() / 3600
                energy_increment = ((self._last_power + current_power) / 2) * time_diff / 1000
                self._attr_native_value += energy_increment

            self._last_power = current_power
            self._last_update_time = current_time
        except Exception as e:
            _LOGGER.error("Error updating solar energy: %s", e)

class StorcubeSolarEnergySensor2(StorcubeBatterySensor):
    """Représentation de l'énergie solaire produite par le deuxième panneau."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Énergie Solaire 2"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_unique_id = f"{self._device_id}_solar_energy_2"
        self._last_power = 0
        self._last_update_time = None
        self._attr_native_value = 0

    def _update_value_from_sources(self):
        try:
            current_power = 0
            if self._is_ws_fresh():
                current_power = self._websocket_data.get("pv2power", 0)
            elif self._rest_data:
                current_power = self._rest_data.get("pv2power", 0)

            current_time = datetime.now()
            if self._last_update_time is not None and current_power > 0:
                time_diff = (current_time - self._last_update_time).total_seconds() / 3600
                energy_increment = ((self._last_power + current_power) / 2) * time_diff / 1000
                self._attr_native_value += energy_increment

            self._last_power = current_power
            self._last_update_time = current_time
        except Exception as e:
            _LOGGER.error("Error updating solar energy 2: %s", e)

class StorcubeSolarEnergyTotalSensor(StorcubeBatterySensor):
    """Représentation de l'énergie solaire totale."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Énergie Solaire Totale"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_unique_id = f"{self._device_id}_solar_energy_total"
        self._last_power = 0
        self._last_update_time = None
        self._attr_native_value = 0

    def _update_value_from_sources(self):
        try:
            p1 = 0
            p2 = 0
            if self._is_ws_fresh():
                p1 = self._websocket_data.get("pv1power", 0)
                p2 = self._websocket_data.get("pv2power", 0)
            elif self._rest_data:
                p1 = self._rest_data.get("pv1power", 0)
                p2 = self._rest_data.get("pv2power", 0)

            current_power = p1 + p2
            current_time = datetime.now()
            if self._last_update_time is not None and current_power > 0:
                time_diff = (current_time - self._last_update_time).total_seconds() / 3600
                energy_increment = ((self._last_power + current_power) / 2) * time_diff / 1000
                self._attr_native_value += energy_increment

            self._last_power = current_power
            self._last_update_time = current_time
        except Exception as e:
            _LOGGER.error("Error updating solar energy total: %s", e)

class StorcubeOutputPowerSensor(StorcubeBatterySensor):
    """Représentation de la puissance de sortie."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Puissance Sortie"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = f"{self._device_id}_output_power"
        self._attr_icon = "mdi:flash"

    def _update_value_from_sources(self):
        try:
            if self._is_ws_fresh():
                self._attr_native_value = self._websocket_data.get("invPower")
            elif self._rest_data:
                self._attr_native_value = self._rest_data.get("outputPower")
        except Exception as e:
            _LOGGER.error("Error updating output power: %s", e)

class StorcubeOutputEnergySensor(StorcubeBatterySensor):
    """Représentation de l'énergie de sortie."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Énergie Sortie"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_unique_id = f"{self._device_id}_output_energy"
        self._last_power = 0
        self._last_update_time = None
        self._attr_native_value = 0

    def _update_value_from_sources(self):
        try:
            current_power = 0
            if self._is_ws_fresh():
                current_power = self._websocket_data.get("invPower", 0)
            elif self._rest_data:
                current_power = self._rest_data.get("outputPower", 0)

            current_time = datetime.now()
            if self._last_update_time is not None and current_power > 0:
                time_diff = (current_time - self._last_update_time).total_seconds() / 3600
                energy_increment = ((self._last_power + current_power) / 2) * time_diff / 1000
                self._attr_native_value += energy_increment

            self._last_power = current_power
            self._last_update_time = current_time
        except Exception as e:
            _LOGGER.error("Error updating output energy: %s", e)

class StorcubeStatusSensor(StorcubeBatterySensor):
    """Représentation de l'état du système."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "État Système"
        self._attr_unique_id = f"{self._device_id}_status"

    def _update_value_from_sources(self):
        try:
            is_work = None
            if self._is_ws_fresh():
                is_work = self._websocket_data.get("isWork")
            elif self._rest_data:
                is_work = self._rest_data.get("workStatus")

            if is_work is not None:
                self._attr_native_value = "En marche" if is_work == 1 else "Arrêté"
        except Exception as e:
            _LOGGER.error("Error updating status: %s", e)

class StorcubeModelSensor(StorcubeBatterySensor):
    """Représentation du modèle."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Modèle"
        self._attr_unique_id = f"{self._device_id}_model"
        self._attr_icon = "mdi:information"

    def _update_value_from_sources(self):
        try:
            if self._is_ws_fresh():
                self._attr_native_value = self._websocket_data.get("equipModelCode")
            elif self._rest_data:
                self._attr_native_value = self._rest_data.get("equipModelCode")
        except Exception as e:
            _LOGGER.error("Error updating model: %s", e)

class StorcubeSerialNumberSensor(StorcubeBatterySensor):
    """Représentation du numéro de série."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Numéro de série"
        self._attr_unique_id = f"{self._device_id}_serial_number"
        self._attr_icon = "mdi:barcode"

    def _update_value_from_sources(self):
        self._attr_native_value = self._device_id

class StorcubeOutputTypeSensor(StorcubeBatterySensor):
    """Représentation du type de sortie."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Type de sortie"
        self._attr_unique_id = f"{self._device_id}_output_type"

    def _update_value_from_sources(self):
        try:
            val = None
            if self._is_ws_fresh():
                val = self._websocket_data.get("outputType")
            elif self._rest_data:
                val = self._rest_data.get("outputType")

            if val is not None:
                self._attr_native_value = str(val)
        except Exception as e:
            _LOGGER.error("Error updating output type: %s", e)

class StorcubeReservedSensor(StorcubeBatterySensor):
    """Niveau de réserve."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Niveau de réserve"
        self._attr_unique_id = f"{self._device_id}_reserved"
        self._attr_native_unit_of_measurement = PERCENTAGE

    def _update_value_from_sources(self):
        try:
            if self._is_ws_fresh() and "reserved" in self._websocket_data:
                self._attr_native_value = self._websocket_data.get("reserved")
            elif self._rest_data and "reserved" in self._rest_data:
                self._attr_native_value = self._rest_data.get("reserved")
        except Exception as e:
            _LOGGER.error("Error updating reserved: %s", e)

class StorcubeWorkStatusSensor(StorcubeBatterySensor):
    """État de fonctionnement."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "État fonctionnement"
        self._attr_unique_id = f"{self._device_id}_work_status"

    def _update_value_from_sources(self):
        try:
            status = None
            if self._is_ws_fresh():
                status = self._websocket_data.get("workStatus")
            elif self._rest_data:
                status = self._rest_data.get("workStatus")

            if status is not None:
                status_map = {0: "Arrêté", 1: "En fonctionnement", 2: "En erreur"}
                self._attr_native_value = status_map.get(status, "Inconnu")
        except Exception as e:
            _LOGGER.error("Error updating work status: %s", e)

class StorcubeOnlineSensor(StorcubeBatterySensor):
    """État de connexion."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Connexion"
        self._attr_unique_id = f"{self._device_id}_online_status"

    def _update_value_from_sources(self):
        try:
            online = None
            if self._is_ws_fresh():
                online = self._websocket_data.get("rgOnline")
            elif self._rest_data:
                online = self._rest_data.get("rgOnline")

            if online is not None:
                self._attr_native_value = "En ligne" if online == 1 else "Hors ligne"
        except Exception as e:
            _LOGGER.error("Error updating online: %s", e)

class StorcubeErrorCodeSensor(StorcubeBatterySensor):
    """Code d'erreur."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Code erreur"
        self._attr_unique_id = f"{self._device_id}_error_code"

    def _update_value_from_sources(self):
        try:
            if self._is_ws_fresh():
                self._attr_native_value = self._websocket_data.get("errorCode")
            elif self._rest_data:
                self._attr_native_value = self._rest_data.get("errorCode")
        except Exception as e:
            _LOGGER.error("Error updating error code: %s", e)

class StorcubeOperatingModeSensor(StorcubeBatterySensor):
    """Mode de fonctionnement."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Mode"
        self._attr_unique_id = f"{self._device_id}_operating_mode"

    def _update_value_from_sources(self):
        try:
            mode = None
            if self._is_ws_fresh():
                mode = self._websocket_data.get("operatingMode")
            elif self._rest_data:
                mode = self._rest_data.get("operatingMode")
            
            if mode is not None:
                mode_map = {0: "Normal", 1: "Économie", 2: "Boost", 3: "Veille"}
                self._attr_native_value = mode_map.get(mode, f"Mode {mode}")
        except Exception as e:
            _LOGGER.error("Error updating operating mode: %s", e)

class StorcubeFirmwareSensor(StorcubeBatterySensor):
    """Version du firmware."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(config, coordinator)
        self._attr_name = "Firmware"
        self._attr_unique_id = f"{self._device_id}_firmware"
        self._firmware_data = None

    @callback
    def handle_state_update(self, payload: dict[str, Any]) -> None:
        if "firmware" in payload:
            self._firmware_data = payload["firmware"]
        super().handle_state_update(payload)

    def _update_value_from_sources(self):
        if self._firmware_data:
            cv = self._firmware_data.get("current_version", "Inconnue")
            ua = self._firmware_data.get("upgrade_available", False)
            self._attr_native_value = f"{cv} (MàJ dispos)" if ua else cv
        elif self.coordinator.data.get("firmware"):
            f = self.coordinator.data["firmware"]
            self._attr_native_value = f.get("current_version", "Inconnue")

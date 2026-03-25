"""Number platform for Storcube Battery Monitor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE_ID,
    UnitOfPower,
    PERCENTAGE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Storcube number platform."""
    config = config_entry.data
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = [
        StorcubePowerNumber(config, coordinator),
        StorcubeThresholdNumber(config, coordinator)
    ]

    async_add_entities(entities)

class StorcubePowerNumber(NumberEntity):
    """Représente le contrôle de puissance de sortie StorCube."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the Storcube Power Number."""
        self._config = config
        self.coordinator = coordinator
        self._device_id = config[CONF_DEVICE_ID]
        self._attr_name = f"Puissance de Sortie StorCube"
        self._attr_unique_id = f"{self._device_id}_output_power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_native_min_value = 0.0
        self._attr_native_max_value = 800.0
        self._attr_native_step = 1.0
        self._attr_mode = NumberMode.SLIDER
        self._attr_native_value = 100.0

    @property
    def should_poll(self) -> bool:
        return False

    async def async_set_native_value(self, value: float) -> None:
        """Set the power value."""
        if await self.coordinator.set_power_value(value):
            self._attr_native_value = value
            self.async_write_ha_state()

class StorcubeThresholdNumber(NumberEntity):
    """Représente le contrôle du seuil de batterie StorCube."""

    def __init__(self, config: ConfigType, coordinator) -> None:
        """Initialize the Storcube Threshold Number."""
        self._config = config
        self.coordinator = coordinator
        self._device_id = config[CONF_DEVICE_ID]
        self._attr_name = f"Seuil de Batterie StorCube"
        self._attr_unique_id = f"{self._device_id}_battery_threshold"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_native_min_value = 0.0
        self._attr_native_max_value = 100.0
        self._attr_native_step = 1.0
        self._attr_mode = NumberMode.SLIDER
        self._attr_native_value = 80.0

    @property
    def should_poll(self) -> bool:
        return False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        val = self.coordinator.data.get("websocket", {}).get("reserved") or self.coordinator.data.get("rest_api", {}).get("reserved")
        if val is not None:
            self._attr_native_value = float(val)

    async def async_set_native_value(self, value: float) -> None:
        """Set the threshold value."""
        if await self.coordinator.set_threshold_value(value):
            self._attr_native_value = value
            self.async_write_ha_state()

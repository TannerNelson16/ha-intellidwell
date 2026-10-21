"""Support for IntelliDwell Sprinkler Controller sensors."""

from datetime import datetime, timedelta
import logging
from typing import Any, override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import IntelliDwellConfigEntry
from .const import DOMAIN
from .coordinator import IntelliDwellCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: IntelliDwellConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator: IntelliDwellCoordinator = config_entry.runtime_data

    entities: list[SensorEntity] = [
        IntelliDwellActiveZoneSensor(coordinator, config_entry),
        IntelliDwellTimerRemainingSensor(coordinator, config_entry),
    ]
    async_add_entities(entities)


def _get_zone_display_name(coordinator: IntelliDwellCoordinator, pin: int) -> str:
    """Get zone display name with zone index prefix."""
    z_num = pin + 1
    raw_name = ""
    if isinstance(coordinator.data, dict):
        settings = coordinator.data.get("settings", {})
        if isinstance(settings, dict):
            zone_names = settings.get("zone_names", [])
            if isinstance(zone_names, list) and pin < len(zone_names):
                name = zone_names[pin]
                if name and isinstance(name, str) and name.strip():
                    raw_name = name.strip()

    if not raw_name or raw_name.lower() == f"zone {z_num}":
        return f"Zone {z_num}"
    if raw_name.lower().startswith(f"zone {z_num}"):
        return raw_name
    return f"Zone {z_num}: {raw_name}"


class IntelliDwellActiveZoneSensor(
    CoordinatorEntity[IntelliDwellCoordinator], SensorEntity
):
    """Sensor reporting the currently watering zone."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:sprinkler"
    _attr_name = "Active Zone"

    def __init__(
        self,
        coordinator: IntelliDwellCoordinator,
        config_entry: IntelliDwellConfigEntry,
    ) -> None:
        """Initialize the active zone sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{config_entry.entry_id}_active_zone"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name="IntelliDwell Sprinkler Controller",
            manufacturer="IntelliDwell",
            model="Sprinkler Controller V2",
            configuration_url=f"http://{coordinator.client.host}/scheduler",
        )

    @property
    @override
    def native_value(self) -> str:
        """Return the active zone name or 'Idle'."""
        if not isinstance(self.coordinator.data, dict):
            return "Idle"

        # Check timers first
        timers = self.coordinator.data.get("timers", {})
        for pin_str, remaining in timers.items():
            try:
                pin = int(pin_str)
                if remaining > 0:
                    return _get_zone_display_name(self.coordinator, pin)
            except (ValueError, TypeError):
                continue

        # Check sequential run queue
        queue = self.coordinator.data.get("queue", {})
        if isinstance(queue, dict) and queue.get("active"):
            steps = queue.get("steps", [])
            idx = queue.get("current_index", 0)
            if 0 <= idx < len(steps):
                step_pin = steps[idx].get("pin", 0)
                return _get_zone_display_name(self.coordinator, step_pin)

        # Check active relays
        relay_states = self.coordinator.data.get("relay_states", [])
        for pin, state in enumerate(relay_states):
            if state == 1:
                return _get_zone_display_name(self.coordinator, pin)

        return "Idle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return active watering details."""
        if not isinstance(self.coordinator.data, dict):
            return {}

        timers = self.coordinator.data.get("timers", {})
        for pin_str, remaining in timers.items():
            try:
                pin = int(pin_str)
                if remaining > 0:
                    return {
                        "active_zone_index": pin + 1,
                        "remaining_seconds": remaining,
                        "timer_active": True,
                    }
            except (ValueError, TypeError):
                continue

        queue = self.coordinator.data.get("queue", {})
        if isinstance(queue, dict) and queue.get("active"):
            return {
                "queue_active": True,
                "current_step": queue.get("current_index", 0) + 1,
                "remaining_seconds": queue.get("remaining_seconds", 0),
            }

        return {"timer_active": False}


class IntelliDwellTimerRemainingSensor(
    CoordinatorEntity[IntelliDwellCoordinator], SensorEntity
):
    """Sensor reporting remaining watering time as a live countdown timestamp."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:timer-sand"
    _attr_name = "Watering Time Remaining"

    def __init__(
        self,
        coordinator: IntelliDwellCoordinator,
        config_entry: IntelliDwellConfigEntry,
    ) -> None:
        """Initialize the timer remaining sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{config_entry.entry_id}_timer_remaining"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name="IntelliDwell Sprinkler Controller",
            manufacturer="IntelliDwell",
            model="Sprinkler Controller V2",
            configuration_url=f"http://{coordinator.client.host}/scheduler",
        )

    def _get_remaining_seconds(self) -> int:
        """Get remaining seconds across timers or queue."""
        if not isinstance(self.coordinator.data, dict):
            return 0

        timers = self.coordinator.data.get("timers", {})
        for pin_str, remaining in timers.items():
            try:
                rem = int(remaining)
                if rem > 0:
                    return rem
            except (ValueError, TypeError):
                continue

        queue = self.coordinator.data.get("queue", {})
        if isinstance(queue, dict) and queue.get("active"):
            return int(queue.get("remaining_seconds", 0))

        return 0

    @property
    @override
    def native_value(self) -> datetime | None:
        """Return end timestamp for live countdown in HA frontend."""
        remaining = self._get_remaining_seconds()
        if remaining > 0:
            return dt_util.utcnow() + timedelta(seconds=remaining)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return remaining seconds and minutes."""
        remaining = self._get_remaining_seconds()
        return {
            "remaining_seconds": remaining,
            "remaining_minutes": round(remaining / 60, 1) if remaining > 0 else 0,
            "timer_active": remaining > 0,
        }

"""Support for IntelliDwell Sprinkler Controller switches."""

from datetime import timedelta
import logging
from typing import Any, override

from pyintellidwell import IntelliDwellConnectionError

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
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
    """Set up the switch platform."""
    coordinator: IntelliDwellCoordinator = config_entry.runtime_data

    entities: list[SwitchEntity] = [
        IntelliDwellZoneSwitch(coordinator, config_entry, zone_index)
        for zone_index in range(10)
    ]
    async_add_entities(entities)


class IntelliDwellZoneSwitch(
    CoordinatorEntity[IntelliDwellCoordinator], SwitchEntity
):
    """Representation of an IntelliDwell Sprinkler Zone switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: IntelliDwellCoordinator,
        config_entry: IntelliDwellConfigEntry,
        zone_index: int,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.zone_index = zone_index
        self._attr_name = self._get_zone_name()
        self._attr_unique_id = f"{config_entry.entry_id}_zone_{zone_index}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name="IntelliDwell Sprinkler Controller",
            manufacturer="IntelliDwell",
            model="Sprinkler Controller V2",
            configuration_url=f"http://{coordinator.client.host}/scheduler",
        )

    def _get_zone_name(self) -> str:
        """Get friendly zone name formatted with zone number prefix to preserve numerical sort."""
        z_num = self.zone_index + 1
        raw_name = ""
        if isinstance(self.coordinator.data, dict):
            settings = self.coordinator.data.get("settings", {})
            if isinstance(settings, dict):
                zone_names = settings.get("zone_names", [])
                if isinstance(zone_names, list) and self.zone_index < len(zone_names):
                    name = zone_names[self.zone_index]
                    if name and isinstance(name, str) and name.strip():
                        raw_name = name.strip()

        if not raw_name or raw_name.lower() == f"zone {z_num}":
            return f"Zone {z_num}"

        if raw_name.lower().startswith(f"zone {z_num}"):
            return raw_name

        return f"Zone {z_num}: {raw_name}"

    def _sync_zone_name(self) -> None:
        """Synchronize zone name with entity registry."""
        new_name = self._get_zone_name()
        self._attr_name = new_name
        if self.registry_entry:
            ent_reg = er.async_get(self.hass)
            updates: dict[str, Any] = {}
            if self.registry_entry.original_name != new_name:
                updates["original_name"] = new_name
            if self.registry_entry.name is not None and self.registry_entry.name != new_name:
                updates["name"] = None
            if updates:
                ent_reg.async_update_entity(self.entity_id, **updates)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        self._sync_zone_name()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._sync_zone_name()
        super()._handle_coordinator_update()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return zone attributes including schedule and timer details."""
        schedules = []
        schedule_enabled = True
        timers = {}
        if isinstance(self.coordinator.data, dict):
            sched_list = self.coordinator.data.get("schedules", [])
            if isinstance(sched_list, list) and self.zone_index < len(sched_list):
                zone_sched = sched_list[self.zone_index]
                if isinstance(zone_sched, dict):
                    schedules = zone_sched.get("schedules", [])
                    schedule_enabled = zone_sched.get("enabled", True)
            timers = self.coordinator.data.get("timers", {})

        remaining = int(timers.get(str(self.zone_index), 0))
        timer_active = remaining > 0

        attrs: dict[str, Any] = {
            "zone_index": self.zone_index + 1,
            "zone_name": self._get_zone_name(),
            "schedule_enabled": schedule_enabled,
            "schedules": schedules,
            "timer_active": timer_active,
            "timer_remaining_seconds": remaining,
        }
        if timer_active:
            ends_at = dt_util.utcnow() + timedelta(seconds=remaining)
            attrs["timer_ends_at"] = ends_at.isoformat()

        return attrs

    @property
    @override
    def is_on(self) -> bool:
        """Return true if switch is on."""
        states = self.coordinator.data.get("relay_states", [])
        if self.zone_index < len(states):
            return states[self.zone_index] == 1
        return False

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        try:
            await self.coordinator.client.set_relay(self.zone_index, "on")
        except IntelliDwellConnectionError as err:
            raise HomeAssistantError(
                f"Error turning on zone {self.zone_index + 1}: {err}"
            ) from err

        await self.coordinator.async_request_refresh()

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        try:
            await self.coordinator.client.set_relay(self.zone_index, "off")
        except IntelliDwellConnectionError as err:
            raise HomeAssistantError(
                f"Error turning off zone {self.zone_index + 1}: {err}"
            ) from err

        await self.coordinator.async_request_refresh()

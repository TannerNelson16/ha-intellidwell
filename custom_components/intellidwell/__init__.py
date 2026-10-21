import asyncio
import logging
import types
from typing import Any

import aiohttp
from pyintellidwell import (
    IntelliDwellClient,
    IntelliDwellConnectionError,
    IntelliDwellInvalidResponseError,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .coordinator import IntelliDwellCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]

type IntelliDwellConfigEntry = ConfigEntry[IntelliDwellCoordinator]

SERVICE_ADD_SCHEDULE = "add_schedule"
SERVICE_EDIT_SCHEDULE = "edit_schedule"
SERVICE_DELETE_SCHEDULE = "delete_schedule"
SERVICE_TOGGLE_SCHEDULE_ITEM = "toggle_schedule_item"
SERVICE_TOGGLE_ZONE_SCHEDULE = "toggle_zone_schedule"
SERVICE_START_TIMER = "start_timer"
SERVICE_CANCEL_TIMER = "cancel_timer"


async def _safe_client_request(self: IntelliDwellClient, method: str, path: str, **kwargs: Any) -> Any:
    """Execute HTTP request against controller, safely parsing JSON or plain text."""
    if self._session is None:
        self._session = aiohttp.ClientSession()
        self._close_session = True

    url = f"http://{self.host}/{path.lstrip('/')}"
    try:
        async with self._session.request(method, url, timeout=10, **kwargs) as response:
            if response.status != 200:
                raise IntelliDwellConnectionError(f"HTTP error {response.status}")
            try:
                return await response.json()
            except (ValueError, aiohttp.ContentTypeError):
                return await response.text()
    except asyncio.TimeoutError as err:
        raise IntelliDwellConnectionError(f"Timeout connecting to {self.host}") from err
    except aiohttp.ClientError as err:
        raise IntelliDwellConnectionError(f"Error connecting to {self.host}") from err
    except Exception as err:
        raise IntelliDwellConnectionError(f"Error connecting to {self.host}: {err}") from err


def _calculate_off_time(on_time: str, duration_mins: int) -> str:
    """Calculate off_time string HH:MM from on_time and duration in minutes."""
    try:
        parts = on_time.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        total_mins = (hours * 60 + minutes + duration_mins) % (24 * 60)
        return f"{total_mins // 60:02d}:{total_mins % 60:02d}"
    except Exception:
        return on_time


def _get_coordinator(hass: HomeAssistant, call: ServiceCall) -> IntelliDwellCoordinator:
    """Retrieve coordinator from call data or default to first available."""
    domain_data = hass.data.get(DOMAIN, {})
    if not domain_data:
        raise HomeAssistantError("No IntelliDwell sprinkler controller is loaded")

    entry_id = call.data.get("config_entry_id") or call.data.get("entry_id")
    if entry_id and entry_id in domain_data:
        return domain_data[entry_id]

    return next(iter(domain_data.values()))


def _zone_to_pin(zone_val: Any) -> int:
    """Translate zone parameter (1-10 or 0-9) to 0-indexed relay pin."""
    try:
        val = int(str(zone_val).replace("Zone", "").strip())
    except (ValueError, TypeError) as err:
        raise HomeAssistantError(f"Invalid zone identifier: {zone_val}") from err

    if 1 <= val <= 10:
        return val - 1
    if 0 <= val < 10:
        return val
    raise HomeAssistantError(f"Zone must be between 1 and 10, got {zone_val}")


async def _async_ensure_card_registered(hass: HomeAssistant) -> None:
    """Ensure intellidwell-scheduler-card is registered in Lovelace resources."""
    card_url = "/local/intellidwell-scheduler-card.js"
    try:
        lovelace = hass.data.get("lovelace")
        if lovelace and hasattr(lovelace, "resources"):
            resources = lovelace.resources
            if hasattr(resources, "loaded") and resources.loaded:
                for item in resources.async_items():
                    if item.get("url", "").startswith(card_url):
                        return
                await resources.async_create_item({
                    "res_type": "module",
                    "url": f"{card_url}?v=1.0.0",
                })
    except Exception as err:
        _LOGGER.debug("Could not auto-register lovelace resource: %s", err)


async def async_setup_entry(
    hass: HomeAssistant, entry: IntelliDwellConfigEntry
) -> bool:
    """Set up IntelliDwell Sprinkler Controller from a config entry."""
    host = entry.data[CONF_HOST]
    session = async_get_clientsession(hass)

    client = IntelliDwellClient(host, session=session)
    client._request = types.MethodType(_safe_client_request, client)

    coordinator = IntelliDwellCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    domain_entries = hass.data.setdefault(DOMAIN, {})
    domain_entries[entry.entry_id] = coordinator

    await _async_ensure_card_registered(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def async_handle_add_schedule(call: ServiceCall) -> None:
        """Handle adding a schedule."""
        coord = _get_coordinator(hass, call)
        pin = _zone_to_pin(call.data.get("zone"))
        days = call.data.get("days", [])
        if isinstance(days, str):
            days = [d.strip() for d in days.split(",")]
        on_time = call.data.get("on_time") or call.data.get("onTime")
        off_time = call.data.get("off_time") or call.data.get("offTime")
        duration = call.data.get("duration_mins") or call.data.get("duration")

        if not on_time:
            raise HomeAssistantError("Start time (on_time) is required")
        if not off_time and duration:
            off_time = _calculate_off_time(str(on_time), int(duration))
        if not off_time:
            raise HomeAssistantError("Either off_time or duration_mins must be provided")

        payload = {"days": days, "onTime": on_time, "offTime": off_time}
        try:
            await coord.client._request("POST", f"add-schedule/{pin}", json=payload)
        except Exception as err:
            raise HomeAssistantError(f"Failed to add schedule on zone {pin + 1}: {err}") from err

        coord.mark_schedules_dirty()
        await coord.async_request_refresh()

    async def async_handle_edit_schedule(call: ServiceCall) -> None:
        """Handle editing a schedule."""
        coord = _get_coordinator(hass, call)
        pin = _zone_to_pin(call.data.get("zone"))
        schedule_id = call.data.get("schedule_id") or call.data.get("id")
        if not schedule_id:
            raise HomeAssistantError("schedule_id is required")

        days = call.data.get("days", [])
        if isinstance(days, str):
            days = [d.strip() for d in days.split(",")]
        on_time = call.data.get("on_time") or call.data.get("onTime")
        off_time = call.data.get("off_time") or call.data.get("offTime")
        duration = call.data.get("duration_mins") or call.data.get("duration")

        if not on_time:
            raise HomeAssistantError("Start time (on_time) is required")
        if not off_time and duration:
            off_time = _calculate_off_time(str(on_time), int(duration))
        if not off_time:
            raise HomeAssistantError("Either off_time or duration_mins must be provided")

        payload = {"days": days, "onTime": on_time, "offTime": off_time}
        try:
            await coord.client._request("POST", f"edit-schedule/{pin}/{schedule_id}", json=payload)
        except Exception as err:
            raise HomeAssistantError(f"Failed to edit schedule on zone {pin + 1}: {err}") from err

        coord.mark_schedules_dirty()
        await coord.async_request_refresh()

    async def async_handle_delete_schedule(call: ServiceCall) -> None:
        """Handle deleting a schedule."""
        coord = _get_coordinator(hass, call)
        pin = _zone_to_pin(call.data.get("zone"))
        schedule_id = call.data.get("schedule_id") or call.data.get("id")
        if not schedule_id:
            raise HomeAssistantError("schedule_id is required")

        try:
            await coord.client._request("POST", f"delete-schedule/{pin}/{schedule_id}")
        except Exception as err:
            raise HomeAssistantError(f"Failed to delete schedule on zone {pin + 1}: {err}") from err

        coord.mark_schedules_dirty()
        await coord.async_request_refresh()

    async def async_handle_toggle_schedule_item(call: ServiceCall) -> None:
        """Handle toggling a single schedule rule."""
        coord = _get_coordinator(hass, call)
        pin = _zone_to_pin(call.data.get("zone"))
        schedule_id = call.data.get("schedule_id") or call.data.get("id")
        if not schedule_id:
            raise HomeAssistantError("schedule_id is required")

        enabled = bool(call.data.get("enabled", True))
        state_str = "true" if enabled else "false"

        try:
            await coord.client._request("POST", f"toggle-schedule-item/{pin}/{schedule_id}/{state_str}")
        except Exception as err:
            raise HomeAssistantError(f"Failed to toggle schedule rule on zone {pin + 1}: {err}") from err

        coord.mark_schedules_dirty()
        await coord.async_request_refresh()

    async def async_handle_toggle_zone_schedule(call: ServiceCall) -> None:
        """Handle toggling master schedule for a zone."""
        coord = _get_coordinator(hass, call)
        pin = _zone_to_pin(call.data.get("zone"))
        enabled = bool(call.data.get("enabled", True))
        state_str = "true" if enabled else "false"
        try:
            await coord.client._request("GET", f"toggle-schedule/{pin}/{state_str}")
        except Exception as err:
            raise HomeAssistantError(f"Failed to toggle zone {pin + 1} schedule: {err}") from err

        coord.mark_schedules_dirty()
        await coord.async_request_refresh()

    async def async_handle_start_timer(call: ServiceCall) -> None:
        """Handle starting a timed watering run on a zone."""
        coord = _get_coordinator(hass, call)
        pin = _zone_to_pin(call.data.get("zone"))
        minutes = int(call.data.get("duration_mins") or call.data.get("minutes", 15))
        if minutes <= 0:
            raise HomeAssistantError("Duration must be at least 1 minute")

        try:
            await coord.client._request("GET", f"relay-timer/{pin}/{minutes}")
        except Exception as err:
            raise HomeAssistantError(f"Failed to start timer on zone {pin + 1}: {err}") from err

        await coord.async_request_refresh()

    async def async_handle_cancel_timer(call: ServiceCall) -> None:
        """Handle cancelling active watering timer."""
        coord = _get_coordinator(hass, call)
        pin = 0
        if "zone" in call.data and call.data["zone"] is not None:
            pin = _zone_to_pin(call.data["zone"])
        try:
            await coord.client._request("GET", f"cancel-timer/{pin}")
        except Exception as err:
            raise HomeAssistantError(f"Failed to cancel timer: {err}") from err

        await coord.async_request_refresh()

    # Register services once
    if not hass.services.has_service(DOMAIN, SERVICE_ADD_SCHEDULE):
        hass.services.async_register(DOMAIN, SERVICE_ADD_SCHEDULE, async_handle_add_schedule)
        hass.services.async_register(DOMAIN, SERVICE_EDIT_SCHEDULE, async_handle_edit_schedule)
        hass.services.async_register(DOMAIN, SERVICE_DELETE_SCHEDULE, async_handle_delete_schedule)
        hass.services.async_register(DOMAIN, SERVICE_TOGGLE_SCHEDULE_ITEM, async_handle_toggle_schedule_item)
        hass.services.async_register(DOMAIN, SERVICE_TOGGLE_ZONE_SCHEDULE, async_handle_toggle_zone_schedule)
        hass.services.async_register(DOMAIN, SERVICE_START_TIMER, async_handle_start_timer)
        hass.services.async_register(DOMAIN, SERVICE_CANCEL_TIMER, async_handle_cancel_timer)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: IntelliDwellConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        domain_entries = hass.data.get(DOMAIN, {})
        domain_entries.pop(entry.entry_id, None)
        if not domain_entries:
            hass.services.async_remove(DOMAIN, SERVICE_ADD_SCHEDULE)
            hass.services.async_remove(DOMAIN, SERVICE_EDIT_SCHEDULE)
            hass.services.async_remove(DOMAIN, SERVICE_DELETE_SCHEDULE)
            hass.services.async_remove(DOMAIN, SERVICE_TOGGLE_SCHEDULE_ITEM)
            hass.services.async_remove(DOMAIN, SERVICE_TOGGLE_ZONE_SCHEDULE)
            hass.services.async_remove(DOMAIN, SERVICE_START_TIMER)
            hass.services.async_remove(DOMAIN, SERVICE_CANCEL_TIMER)

    return unload_ok

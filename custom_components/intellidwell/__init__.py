import asyncio
from collections.abc import Callable
import logging
from pathlib import Path
import types
from typing import Any

import aiohttp
from pyintellidwell import (
    IntelliDwellClient,
    IntelliDwellConnectionError,
    IntelliDwellInvalidResponseError,
)

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CARD_VERSION,
    CONF_FORECAST_RAIN_48H_SENSOR,
    CONF_FORECAST_RAIN_SENSOR,
    CONF_RAIN_48H_SENSOR,
    CONF_RAIN_SENSOR,
    CONF_SOIL_MOISTURE_SENSOR,
    CONF_TEMP_SENSOR,
    CONF_WEATHER_ENTITY,
    CONF_WIND_SENSOR,
    DOMAIN,
    WEATHER_OPTION_DEFAULTS,
    WEATHER_STRING_KEYS,
    resolve_weather_options,
)
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
SERVICE_PUSH_WEATHER = "push_weather"
SERVICE_UPDATE_WEATHER_SETTINGS = "update_weather_settings"
SERVICE_APPLY_WEATHER_MODIFIER = "apply_weather_modifier"
SERVICE_RUN_COOLING_MIST = "run_cooling_mist"


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

    device_id = call.data.get("device_id")
    if device_id:
        from homeassistant.helpers import device_registry as dr
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get(device_id)
        if device:
            for c_entry in device.config_entries:
                if c_entry in domain_data:
                    return domain_data[c_entry]

    entity_id = call.data.get("entity_id")
    if entity_id:
        from homeassistant.helpers import entity_registry as er
        ent_reg = er.async_get(hass)
        ent = ent_reg.async_get(entity_id)
        if ent and ent.config_entry_id in domain_data:
            return domain_data[ent.config_entry_id]

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


CARD_PATH = "/intellidwell/intellidwell-scheduler-card.js"
CARD_URL = f"{CARD_PATH}?v={CARD_VERSION}"
WEATHER_CARD_PATH = "/intellidwell/intellidwell-weather-card.js"
WEATHER_CARD_URL = f"{WEATHER_CARD_PATH}?v={CARD_VERSION}"
DATA_STATIC_REGISTERED = f"{DOMAIN}_static_registered"


async def _async_ensure_card_registered(hass: HomeAssistant) -> None:
    """Serve and register scheduler & smart weather cards in Lovelace resources."""
    www_dir = Path(__file__).parent / "www"
    scheduler_path = www_dir / "intellidwell-scheduler-card.js"
    weather_path = www_dir / "intellidwell-weather-card.js"

    # Register static paths with Home Assistant HTTP component once
    if DATA_STATIC_REGISTERED not in hass.data:
        if hasattr(hass, "http") and hass.http:
            try:
                configs = [StaticPathConfig(CARD_PATH, str(scheduler_path), True)]
                if weather_path.exists():
                    configs.append(StaticPathConfig(WEATHER_CARD_PATH, str(weather_path), True))
                await hass.http.async_register_static_paths(configs)
                hass.data[DATA_STATIC_REGISTERED] = True
            except Exception as err:
                _LOGGER.debug("Could not register static path for cards: %s", err)

    # Register or cache-bust card URLs in Lovelace resources
    try:
        lovelace = hass.data.get("lovelace")
        if lovelace and hasattr(lovelace, "resources"):
            resources = lovelace.resources
            if hasattr(resources, "loaded") and resources.loaded:
                items = list(resources.async_items())
                card_specs = [
                    (
                        CARD_PATH,
                        CARD_URL,
                        ("/local/intellidwell-scheduler-card.js",),
                    ),
                    (
                        WEATHER_CARD_PATH,
                        WEATHER_CARD_URL,
                        ("/local/intellidwell-weather-card.js",),
                    ),
                ]
                for path, url_versioned, legacy_prefixes in card_specs:
                    matched = None
                    for item in items:
                        cur_url = item.get("url", "")
                        if cur_url == url_versioned:
                            matched = item
                            break
                        if cur_url.startswith(path) or any(
                            cur_url.startswith(p) for p in legacy_prefixes
                        ):
                            matched = item
                            try:
                                await resources.async_update_item(
                                    item["id"],
                                    {"res_type": "module", "url": url_versioned},
                                )
                            except Exception:
                                pass
                            break
                    if matched is None:
                        await resources.async_create_item(
                            {"res_type": "module", "url": url_versioned}
                        )
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

    weather_unsubs: list[Callable[[], None]] = []

    def _bind_weather_listeners(cur_entry: IntelliDwellConfigEntry) -> None:
        while weather_unsubs:
            weather_unsubs.pop()()
        tracked: list[str] = []
        for opt_key in (
            CONF_RAIN_SENSOR,
            CONF_RAIN_48H_SENSOR,
            CONF_TEMP_SENSOR,
            CONF_WEATHER_ENTITY,
            CONF_FORECAST_RAIN_SENSOR,
            CONF_FORECAST_RAIN_48H_SENSOR,
            CONF_SOIL_MOISTURE_SENSOR,
            CONF_WIND_SENSOR,
        ):
            ent_id = cur_entry.options.get(opt_key)
            if isinstance(ent_id, str) and ent_id.strip() and ent_id.strip() not in tracked:
                tracked.append(ent_id.strip())
        if not tracked:
            return

        async def _on_weather_entity_change(_event: Event) -> None:
            coordinator.mark_weather_dirty()
            await coordinator.async_request_refresh()

        weather_unsubs.append(
            async_track_state_change_event(hass, tracked, _on_weather_entity_change)
        )

    def _clear_weather_listeners() -> None:
        while weather_unsubs:
            weather_unsubs.pop()()

    async def _async_update_options(
        _hass: HomeAssistant, updated_entry: IntelliDwellConfigEntry
    ) -> None:
        _bind_weather_listeners(updated_entry)
        coordinator.mark_weather_dirty()
        await coordinator.async_request_refresh()

    _bind_weather_listeners(entry)
    entry.async_on_unload(_clear_weather_listeners)
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

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

    async def async_handle_push_weather(call: ServiceCall) -> None:
        """Handle pushing weather / rain data to controller."""
        coord = _get_coordinator(hass, call)
        rain_today = float(call.data.get("rain_today", 0.0))
        source = str(call.data.get("source", "Home Assistant"))
        delay_days = int(call.data.get("delay_days", 0))
        temp = call.data.get("temp")
        if temp is not None and str(temp).strip() != "":
            try:
                temp = float(temp)
            except (ValueError, TypeError):
                temp = None
        else:
            temp = None
        soil_pct = call.data.get("soil_moisture_pct")
        wind_mph = call.data.get("wind_speed_mph")
        try:
            extra_fields = soil_pct is not None or wind_mph is not None
            if hasattr(coord.client, "push_weather") and not extra_fields:
                await coord.client.push_weather(
                    rain_today_in=rain_today,
                    source=source,
                    delay_days=delay_days,
                    temp=temp
                )
            else:
                payload: dict[str, Any] = {
                    "rain_today_in": rain_today,
                    "source": source,
                    "delay_days": delay_days,
                }
                if temp is not None:
                    payload["temp"] = temp
                if soil_pct is not None:
                    payload["soil_moisture_pct"] = float(soil_pct)
                if wind_mph is not None:
                    payload["wind_speed_mph"] = float(wind_mph)
                await coord.client._request("POST", "api/weather", json=payload)
        except Exception as err:
            raise HomeAssistantError(f"Failed to push weather data: {err}") from err

        if delay_days > 0:
            coord.mark_rain_delay_dirty()
        await coord.async_request_refresh()

    async def async_handle_update_weather_settings(call: ServiceCall) -> None:
        """Persist Smart Weather automation rules from dashboard card into entry options."""
        coord = _get_coordinator(hass, call)
        target_entry = coord.config_entry
        if target_entry is None:
            raise HomeAssistantError("Controller config entry is unavailable")

        merged = dict(target_entry.options)
        raw_opts = call.data.get("options") if isinstance(call.data.get("options"), dict) else call.data
        for key, default_val in WEATHER_OPTION_DEFAULTS.items():
            if key not in raw_opts:
                continue
            val = raw_opts[key]
            if key in WEATHER_STRING_KEYS:
                merged[key] = str(val).strip() if val else ""
            elif isinstance(default_val, bool):
                merged[key] = bool(val)
            elif isinstance(default_val, int):
                try:
                    merged[key] = int(round(float(val)))
                except (ValueError, TypeError) as err:
                    raise HomeAssistantError(f"Invalid integer for {key}: {val}") from err
            elif isinstance(default_val, float):
                try:
                    merged[key] = round(float(val), 2)
                except (ValueError, TypeError) as err:
                    raise HomeAssistantError(f"Invalid number for {key}: {val}") from err

        # Force evaluation & push when user saves & asks to apply immediately
        coord._last_weather_signature = None
        coord.mark_weather_dirty()
        hass.config_entries.async_update_entry(target_entry, options=merged)
        await coord.async_request_refresh()

        if call.data.get("apply_now"):
            rec_mod = (coord.last_weather_evaluation or {}).get("recommended_modifier")
            if isinstance(rec_mod, dict):
                try:
                    await coord.async_apply_weather_modifier(rec_mod)
                    await coord.async_request_refresh()
                except Exception as err:
                    raise HomeAssistantError(f"Failed to push weather modifier: {err}") from err

    async def async_handle_apply_weather_modifier(call: ServiceCall) -> None:
        """Push the recommended weather modifier or clear any active modifier on the controller."""
        coord = _get_coordinator(hass, call)
        mode = str(call.data.get("mode") or "recommended").lower()
        if mode == "clear" or call.data.get("clear") is True:
            mod: dict[str, Any] = {
                "active": False,
                "scale_pct": 100,
                "skip_pins": [],
                "inhibit": False,
                "freeze_skip": False,
                "wind_skip": False,
                "syringe": {},
                "reason": "Cleared",
                "ttl_seconds": 0,
            }
        elif mode == "recommended":
            rec = (coord.last_weather_evaluation or {}).get("recommended_modifier")
            if isinstance(rec, dict):
                mod = dict(rec)
            else:
                opts = resolve_weather_options(dict(coord.config_entry.options) if coord.config_entry else None)
                eval_data = coord.last_weather_evaluation or {}
                mod = coord._build_local_weather_modifier(
                    opts,
                    eval_data.get("temp_f"),
                    [],
                    [],
                    eval_data.get("wind_mph"),
                    eval_data.get("soil_moisture_pct"),
                    0,
                )
        else:
            scale_pct = int(call.data.get("scale_pct", 100))
            inhibit = bool(call.data.get("inhibit", False))
            wind_skip = bool(call.data.get("wind_skip", False))
            freeze_skip = bool(call.data.get("freeze_skip", False))
            raw_pins = call.data.get("skip_pins") or []
            skip_pins = [int(p) for p in raw_pins] if isinstance(raw_pins, list) else []
            active = bool(inhibit or freeze_skip or wind_skip or scale_pct != 100 or call.data.get("active", False))
            mod = {
                "active": active,
                "scale_pct": scale_pct,
                "skip_pins": skip_pins,
                "inhibit": inhibit,
                "freeze_skip": freeze_skip,
                "wind_skip": wind_skip,
                "reason": str(call.data.get("reason") or f"Custom {scale_pct}%"),
                "ttl_seconds": int(call.data.get("ttl_seconds", 86400)) if active else 0,
            }

        try:
            await coord.async_apply_weather_modifier(mod)
        except Exception as err:
            raise HomeAssistantError(f"Failed to apply weather modifier: {err}") from err
        await coord.async_request_refresh()

    async def async_handle_run_cooling_mist(call: ServiceCall) -> None:
        """Run a short Afternoon Cooling Mist queue across turf zones."""
        coord = _get_coordinator(hass, call)
        raw_pins = call.data.get("pins")
        pins = [int(p) for p in raw_pins] if isinstance(raw_pins, list) else None
        minutes = call.data.get("minutes")
        mins_int = int(minutes) if minutes is not None else None
        try:
            await coord.async_run_cooling_mist(pins=pins, minutes=mins_int)
        except Exception as err:
            raise HomeAssistantError(f"Failed to start cooling mist: {err}") from err
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
        hass.services.async_register(DOMAIN, SERVICE_PUSH_WEATHER, async_handle_push_weather)
    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_WEATHER_SETTINGS):
        hass.services.async_register(DOMAIN, SERVICE_UPDATE_WEATHER_SETTINGS, async_handle_update_weather_settings)
    if not hass.services.has_service(DOMAIN, SERVICE_APPLY_WEATHER_MODIFIER):
        hass.services.async_register(DOMAIN, SERVICE_APPLY_WEATHER_MODIFIER, async_handle_apply_weather_modifier)
    if not hass.services.has_service(DOMAIN, SERVICE_RUN_COOLING_MIST):
        hass.services.async_register(DOMAIN, SERVICE_RUN_COOLING_MIST, async_handle_run_cooling_mist)

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
            hass.services.async_remove(DOMAIN, SERVICE_PUSH_WEATHER)
            hass.services.async_remove(DOMAIN, SERVICE_UPDATE_WEATHER_SETTINGS)
            hass.services.async_remove(DOMAIN, SERVICE_APPLY_WEATHER_MODIFIER)
            hass.services.async_remove(DOMAIN, SERVICE_RUN_COOLING_MIST)

    return unload_ok

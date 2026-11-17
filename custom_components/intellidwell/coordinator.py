"""DataUpdateCoordinator for IntelliDwell Sprinkler Controller."""

import asyncio
from datetime import timedelta
import logging
from typing import Any, override

from pyintellidwell import (
    IntelliDwellClient,
    IntelliDwellConnectionError,
    IntelliDwellInvalidResponseError,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_AUTO_RAIN_DELAY,
    CONF_DELAY_DAYS,
    CONF_FORECAST_POP_THRESHOLD,
    CONF_HEAVY_DELAY_DAYS,
    CONF_HEAVY_RAIN_THRESHOLD,
    CONF_RAIN_SENSOR,
    CONF_RAIN_THRESHOLD,
    CONF_SOURCE_NAME,
    CONF_STOP_ACTIVE_WATERING,
    CONF_TEMP_SENSOR,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_PUSH_ENABLED,
    DEFAULT_AUTO_RAIN_DELAY,
    DEFAULT_DELAY_DAYS,
    DEFAULT_FORECAST_POP_THRESHOLD,
    DEFAULT_HEAVY_DELAY_DAYS,
    DEFAULT_HEAVY_RAIN_THRESHOLD,
    DEFAULT_RAIN_THRESHOLD,
    DEFAULT_STOP_ACTIVE_WATERING,
    DEFAULT_WEATHER_PUSH_ENABLED,
)

_LOGGER = logging.getLogger(__name__)


def _parse_float(value: Any) -> float | None:
    """Safely convert a state or attribute value to float."""
    if value is None or str(value).strip() in ("unknown", "unavailable", ""):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


class IntelliDwellCoordinator(DataUpdateCoordinator[dict]):
    """Class to manage fetching IntelliDwell Sprinkler Controller data."""

    def __init__(
        self, hass: HomeAssistant, client: IntelliDwellClient, entry: ConfigEntry
    ) -> None:
        """Initialize."""
        self.client = client
        self._cached_settings: dict[str, Any] = {}
        self._cached_schedules: list[Any] = []
        self._cached_rain_delay: int = 0
        self._schedules_dirty: bool = True
        self._rain_delay_dirty: bool = True
        self._settings_dirty: bool = True
        self._rain_delay_poll_counter: int = 0
        self._settings_poll_counter: int = 0
        self._weather_dirty: bool = True
        self._weather_push_counter: int = 0
        self._last_weather_signature: tuple[Any, ...] | None = None

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"IntelliDwell Sprinkler Coordinator ({client.host})",
            update_interval=timedelta(seconds=10),
        )

    def mark_schedules_dirty(self) -> None:
        """Mark schedules as needing a fresh fetch."""
        self._schedules_dirty = True

    def mark_rain_delay_dirty(self) -> None:
        """Mark rain delay as needing a fresh fetch."""
        self._rain_delay_dirty = True

    def mark_settings_dirty(self) -> None:
        """Mark settings as needing a fresh fetch."""
        self._settings_dirty = True

    def mark_weather_dirty(self) -> None:
        """Mark weather push data as needing immediate evaluation and push."""
        self._weather_dirty = True

    async def _get_rain_delay(self) -> dict[str, Any]:
        if hasattr(self.client, "get_rain_delay"):
            return await self.client.get_rain_delay()
        try:
            res = await self.client._request("GET", "get-rain-delay")
            return res if isinstance(res, dict) else {"days_remaining": 0}
        except Exception as e:
            _LOGGER.debug("Error fetching rain delay: %s", e)
            return {"days_remaining": 0}

    async def _get_schedules(self) -> list[Any]:
        if hasattr(self.client, "get_schedules"):
            return await self.client.get_schedules()
        try:
            res = await self.client._request("GET", "get-schedules")
            return res if isinstance(res, list) else []
        except Exception as e:
            _LOGGER.debug("Error fetching schedules: %s", e)
            return []

    async def _get_settings_raw(self) -> dict[str, Any]:
        """Fetch raw settings from the controller."""
        try:
            res = await self.client._request("GET", "get-settings")
            if isinstance(res, dict):
                return res
        except Exception as e:
            _LOGGER.debug("Error fetching settings: %s", e)
        return {}

    def _resolve_weather_source(
        self,
        opts: dict[str, Any],
        rain_ent: str,
        weather_ent: str,
    ) -> str:
        """Resolve display source label from custom option or entity friendly name."""
        source_name = (opts.get(CONF_SOURCE_NAME) or "").strip()
        if source_name:
            return source_name
        for ent_id in (rain_ent, weather_ent):
            if ent_id:
                st = self.hass.states.get(ent_id)
                if st and st.attributes.get("friendly_name"):
                    return str(st.attributes["friendly_name"])
        return "Home Assistant"

    def _calculate_auto_rain_delay(
        self,
        opts: dict[str, Any],
        rain_today: float,
        weather_ent: str,
    ) -> int:
        """Calculate rain delay days from configured rainfall & forecast thresholds."""
        if not opts.get(CONF_AUTO_RAIN_DELAY, DEFAULT_AUTO_RAIN_DELAY):
            return 0
        rain_thresh = float(opts.get(CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD))
        hvy_thresh = float(opts.get(CONF_HEAVY_RAIN_THRESHOLD, DEFAULT_HEAVY_RAIN_THRESHOLD))
        std_days = int(opts.get(CONF_DELAY_DAYS, DEFAULT_DELAY_DAYS))
        hvy_days = int(opts.get(CONF_HEAVY_DELAY_DAYS, DEFAULT_HEAVY_DELAY_DAYS))
        pop_thresh = int(opts.get(CONF_FORECAST_POP_THRESHOLD, DEFAULT_FORECAST_POP_THRESHOLD))

        today_pop = 0
        if weather_ent:
            st_w = self.hass.states.get(weather_ent)
            forecast = st_w.attributes.get("forecast") if st_w else None
            if isinstance(forecast, (list, tuple)) and forecast and isinstance(forecast[0], dict):
                raw_pop = _parse_float(forecast[0].get("precipitation_probability"))
                if raw_pop is not None:
                    today_pop = int(raw_pop)

        if rain_today >= hvy_thresh:
            return hvy_days
        if rain_today >= rain_thresh:
            return std_days
        if weather_ent and today_pop >= pop_thresh:
            return 1
        return 0

    async def _async_evaluate_and_push_weather(self, status_data: dict[str, Any]) -> None:
        """Push configured weather entities and apply automatic rain delay when needed."""
        opts = dict(self.config_entry.options) if self.config_entry else {}
        if not opts.get(CONF_WEATHER_PUSH_ENABLED, DEFAULT_WEATHER_PUSH_ENABLED):
            return

        rain_ent = (opts.get(CONF_RAIN_SENSOR) or "").strip()
        temp_ent = (opts.get(CONF_TEMP_SENSOR) or "").strip()
        weather_ent = (opts.get(CONF_WEATHER_ENTITY) or "").strip()
        if not (rain_ent or temp_ent or weather_ent):
            return

        rain_today = 0.0
        if rain_ent:
            st_rain = self.hass.states.get(rain_ent)
            parsed_rain = _parse_float(st_rain.state) if st_rain else None
            if parsed_rain is None:
                if not temp_ent and not weather_ent:
                    return
                rain_today = 0.0
            else:
                rain_today = parsed_rain

        temp: float | None = None
        if temp_ent:
            st_temp = self.hass.states.get(temp_ent)
            temp = _parse_float(st_temp.state) if st_temp else None
        elif weather_ent:
            st_w = self.hass.states.get(weather_ent)
            temp = _parse_float(st_w.attributes.get("temperature")) if st_w else None

        source = self._resolve_weather_source(opts, rain_ent, weather_ent)
        delay_days = self._calculate_auto_rain_delay(opts, rain_today, weather_ent)
        sig = (
            round(rain_today, 2),
            round(temp, 1) if temp is not None else None,
            source,
            delay_days,
        )

        if (
            not self._weather_dirty
            and sig == self._last_weather_signature
            and self._weather_push_counter > 0
        ):
            self._weather_push_counter -= 1
            return

        try:
            if hasattr(self.client, "push_weather"):
                await self.client.push_weather(
                    rain_today_in=rain_today,
                    source=source,
                    delay_days=delay_days,
                    temp=temp,
                )
            else:
                payload: dict[str, Any] = {
                    "rain_today_in": rain_today,
                    "source": source,
                    "delay_days": delay_days,
                }
                if temp is not None:
                    payload["temp"] = temp
                await self.client._request("POST", "api/weather", json=payload)

            self._last_weather_signature = sig
            self._weather_dirty = False
            self._weather_push_counter = 90  # Re-push every ~15 minutes (90 x 10s)
            if delay_days > 0:
                self._rain_delay_dirty = True

            rain_thresh = float(opts.get(CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD))
            if (
                opts.get(CONF_AUTO_RAIN_DELAY, DEFAULT_AUTO_RAIN_DELAY)
                and opts.get(CONF_STOP_ACTIVE_WATERING, DEFAULT_STOP_ACTIVE_WATERING)
                and rain_today >= rain_thresh
            ):
                if any(status_data.get("relay_states", [])) or bool(status_data.get("timers")):
                    await self.client._request("GET", "cancel-timer/0")
        except Exception as err:
            _LOGGER.debug("Error pushing automatic weather data: %s", err)

    @override
    async def _async_update_data(self) -> dict:
        """Fetch status, and conditionally rain delay, schedules, and settings sequentially."""
        try:
            status_data = await self.client.get_status()
        except (IntelliDwellConnectionError, IntelliDwellInvalidResponseError) as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error communicating with API: {err}") from err

        await self._async_evaluate_and_push_weather(status_data)

        # Rain delay refresh (every ~60s or immediately if marked dirty)
        if self._rain_delay_dirty or self._rain_delay_poll_counter <= 0:
            rain_delay_res = await self._get_rain_delay()
            self._cached_rain_delay = (
                rain_delay_res.get("days_remaining", 0)
                if isinstance(rain_delay_res, dict)
                else 0
            )
            self._rain_delay_dirty = False
            self._rain_delay_poll_counter = 6  # 6 x 10s = 60s
        else:
            self._rain_delay_poll_counter -= 1

        # Schedules refresh (only on startup or after explicit schedule modifications)
        if self._schedules_dirty or not self._cached_schedules:
            sched_res = await self._get_schedules()
            if sched_res:
                self._cached_schedules = sched_res
            self._schedules_dirty = False

        # Settings refresh (every ~30 mins or immediately if marked dirty)
        if self._settings_dirty or not self._cached_settings or self._settings_poll_counter <= 0:
            sett_res = await self._get_settings_raw()
            if sett_res:
                self._cached_settings = sett_res
            self._settings_dirty = False
            self._settings_poll_counter = 180  # 180 x 10s = 30 mins
        else:
            self._settings_poll_counter -= 1

        status_data["rain_delay"] = self._cached_rain_delay
        status_data["schedules"] = self._cached_schedules
        status_data["settings"] = self._cached_settings
        return status_data

"""DataUpdateCoordinator for IntelliDwell Sprinkler Controller."""

import asyncio
from datetime import timedelta
import logging
import re
from typing import Any, override

from pyintellidwell import (
    IntelliDwellClient,
    IntelliDwellConnectionError,
    IntelliDwellInvalidResponseError,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ANTICIPATED_24H_THRESHOLD,
    CONF_ANTICIPATED_48H_THRESHOLD,
    CONF_AUTO_RAIN_DELAY,
    CONF_COLLECTED_48H_THRESHOLD,
    CONF_COOL_WAVE_ENABLED,
    CONF_COOL_WAVE_REDUCE_PCT,
    CONF_COOL_WAVE_TEMP_THRESHOLD,
    CONF_DELAY_DAYS,
    CONF_FORECAST_POP_THRESHOLD,
    CONF_FORECAST_RAIN_48H_SENSOR,
    CONF_FORECAST_RAIN_SENSOR,
    CONF_FREEZE_SKIP_ENABLED,
    CONF_FREEZE_TEMP_THRESHOLD,
    CONF_HEAT_WAVE_BOOST_PCT,
    CONF_HEAT_WAVE_DAYS,
    CONF_HEAT_WAVE_ENABLED,
    CONF_HEAT_WAVE_SYRINGE_ENABLED,
    CONF_HEAT_WAVE_SYRINGE_MINUTES,
    CONF_HEAT_WAVE_SYRINGE_TEMP,
    CONF_HEAT_WAVE_SYRINGE_TIME,
    CONF_HEAT_WAVE_TEMP_THRESHOLD,
    CONF_HEAVY_DELAY_DAYS,
    CONF_HEAVY_RAIN_THRESHOLD,
    CONF_RAIN_48H_SENSOR,
    CONF_RAIN_SENSOR,
    CONF_RAIN_THRESHOLD,
    CONF_SOIL_MOISTURE_MAX_PCT,
    CONF_SOIL_MOISTURE_SENSOR,
    CONF_SOURCE_NAME,
    CONF_STOP_ACTIVE_WATERING,
    CONF_TEMP_SENSOR,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_PUSH_ENABLED,
    CONF_WIND_PROTECT_DRIP_EXEMPT,
    CONF_WIND_SENSOR,
    CONF_WIND_SKIP_ENABLED,
    CONF_WIND_SKIP_THRESHOLD,
    DEFAULT_ANTICIPATED_24H_THRESHOLD,
    DEFAULT_ANTICIPATED_48H_THRESHOLD,
    DEFAULT_AUTO_RAIN_DELAY,
    DEFAULT_COLLECTED_48H_THRESHOLD,
    DEFAULT_COOL_WAVE_ENABLED,
    DEFAULT_COOL_WAVE_REDUCE_PCT,
    DEFAULT_COOL_WAVE_TEMP_THRESHOLD,
    DEFAULT_DELAY_DAYS,
    DEFAULT_FORECAST_POP_THRESHOLD,
    DEFAULT_FREEZE_SKIP_ENABLED,
    DEFAULT_FREEZE_TEMP_THRESHOLD,
    DEFAULT_HEAT_WAVE_BOOST_PCT,
    DEFAULT_HEAT_WAVE_DAYS,
    DEFAULT_HEAT_WAVE_ENABLED,
    DEFAULT_HEAT_WAVE_SYRINGE_ENABLED,
    DEFAULT_HEAT_WAVE_SYRINGE_MINUTES,
    DEFAULT_HEAT_WAVE_SYRINGE_TEMP,
    DEFAULT_HEAT_WAVE_SYRINGE_TIME,
    DEFAULT_HEAT_WAVE_TEMP_THRESHOLD,
    DEFAULT_HEAVY_DELAY_DAYS,
    DEFAULT_HEAVY_RAIN_THRESHOLD,
    DEFAULT_RAIN_THRESHOLD,
    DEFAULT_SOIL_MOISTURE_MAX_PCT,
    DEFAULT_STOP_ACTIVE_WATERING,
    DEFAULT_WEATHER_PUSH_ENABLED,
    DEFAULT_WIND_PROTECT_DRIP_EXEMPT,
    DEFAULT_WIND_SKIP_ENABLED,
    DEFAULT_WIND_SKIP_THRESHOLD,
    resolve_weather_options,
)

_LOGGER = logging.getLogger(__name__)
_DRIP_ZONE_NAME_RE = re.compile(
    r"(flower|bed|garden|drip|veggie|vegetable|shrub|rose|bush|planter|tree)",
    re.IGNORECASE,
)


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
        self._schedules_poll_counter: int = 0
        self._settings_poll_counter: int = 0
        self._weather_dirty: bool = True
        self._weather_push_counter: int = 0
        self._last_weather_signature: tuple[Any, ...] | None = None
        self._last_ha_modifier_active: bool = False
        self._last_syringe_date: str | None = None
        self.last_weather_evaluation: dict[str, Any] = {}

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

    async def _get_schedules(self) -> list[Any] | None:
        try:
            if hasattr(self.client, "get_schedules"):
                res = await self.client.get_schedules()
            else:
                res = await self.client._request("GET", "get-schedules")
            return res if isinstance(res, list) else None
        except Exception as e:
            _LOGGER.debug("Error fetching schedules: %s", e)
            return None

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
        forecast_rain_ent: str = "",
    ) -> str:
        """Resolve display source label from custom option or entity friendly name."""
        source_name = (opts.get(CONF_SOURCE_NAME) or "").strip()
        if source_name:
            return source_name
        for ent_id in (rain_ent, weather_ent, forecast_rain_ent):
            if ent_id:
                st = self.hass.states.get(ent_id)
                if st and st.attributes.get("friendly_name"):
                    return str(st.attributes["friendly_name"])
        return "Home Assistant"

    async def _async_get_weather_forecast_details(
        self, weather_ent: str
    ) -> dict[str, Any]:
        """Fetch next-24h/48h QPF, POP %, highs/lows, wind, and humidity from weather entity."""
        empty: dict[str, Any] = {
            "ant_24": 0.0,
            "ant_48": 0.0,
            "today_pop": 0,
            "forecast_highs": [],
            "forecast_lows": [],
            "wind_mph": None,
            "humidity": None,
        }
        if not weather_ent:
            return empty
        st_w = self.hass.states.get(weather_ent)
        wind_mph = _parse_float(st_w.attributes.get("wind_speed")) if st_w else None
        wind_unit = str(st_w.attributes.get("wind_speed_unit") or "").lower() if st_w else ""
        if wind_mph is not None and wind_unit in ("km/h", "kph"):
            wind_mph = round(wind_mph * 0.621371, 1)
        elif wind_mph is not None and wind_unit == "m/s":
            wind_mph = round(wind_mph * 2.23694, 1)
        humidity = _parse_float(st_w.attributes.get("humidity")) if st_w else None

        forecast = st_w.attributes.get("forecast") if st_w else None
        if not (isinstance(forecast, (list, tuple)) and forecast) and self.hass.services.has_service(
            "weather", "get_forecasts"
        ):
            try:
                resp = await self.hass.services.async_call(
                    "weather",
                    "get_forecasts",
                    {"entity_id": weather_ent, "type": "daily"},
                    blocking=True,
                    return_response=True,
                )
                if isinstance(resp, dict):
                    ent_resp = resp.get(weather_ent)
                    if isinstance(ent_resp, dict):
                        forecast = ent_resp.get("forecast")
            except Exception as err:
                _LOGGER.debug(
                    "Error calling weather.get_forecasts for %s: %s", weather_ent, err
                )
        if not (isinstance(forecast, (list, tuple)) and forecast and isinstance(forecast[0], dict)):
            return {**empty, "wind_mph": wind_mph, "humidity": humidity}

        unit = st_w.attributes.get("precipitation_unit") if st_w else None
        scale = (1.0 / 25.4) if unit == "mm" else 1.0
        p0 = (_parse_float(forecast[0].get("precipitation")) or 0.0) * scale
        ant_24 = p0
        if len(forecast) > 1 and isinstance(forecast[1], dict):
            p1 = (_parse_float(forecast[1].get("precipitation")) or 0.0) * scale
            ant_48 = p0 + p1
        else:
            ant_48 = ant_24
        raw_pop = _parse_float(forecast[0].get("precipitation_probability"))
        today_pop = int(raw_pop) if raw_pop is not None else 0

        highs: list[float] = []
        lows: list[float] = []
        for entry in forecast[:7]:
            if not isinstance(entry, dict):
                continue
            hi = _parse_float(entry.get("temperature"))
            lo = _parse_float(entry.get("templow"))
            if hi is not None:
                highs.append(hi)
            if lo is not None:
                lows.append(lo)

        return {
            "ant_24": round(ant_24, 4),
            "ant_48": round(ant_48, 4),
            "today_pop": today_pop,
            "forecast_highs": highs,
            "forecast_lows": lows,
            "wind_mph": wind_mph,
            "humidity": humidity,
        }

    async def _async_get_weather_forecast(
        self, weather_ent: str
    ) -> tuple[float, float, int]:
        """Fetch next-24h QPF (in), next-48h QPF (in), and POP (%) from weather entity."""
        details = await self._async_get_weather_forecast_details(weather_ent)
        return details["ant_24"], details["ant_48"], details["today_pop"]

    def _turf_pins(self) -> list[int]:
        """Return 0-indexed non-drip zone pins for Cooling Mist / wind filtering."""
        znames = self._cached_settings.get("zone_names", []) if isinstance(self._cached_settings, dict) else []
        pins: list[int] = []
        for pin in range(10):
            zname = str(znames[pin]) if pin < len(znames) else ""
            if not _DRIP_ZONE_NAME_RE.search(zname):
                pins.append(pin)
        return pins

    def _build_local_weather_modifier(
        self,
        opts: dict[str, Any],
        temp: float | None,
        forecast_highs: list[float],
        forecast_lows: list[float],
        wind_mph: float | None,
        soil_pct: float | None,
        delay_days: int,
    ) -> dict[str, Any]:
        """Evaluate Freeze Skip, Wind Drift Guard, Heat Wave Boost, Cool Wave Trim, Cooling Mist, and Soil Veto."""
        cfg = resolve_weather_options(opts)
        freeze_en = bool(cfg[CONF_FREEZE_SKIP_ENABLED])
        freeze_th = float(cfg[CONF_FREEZE_TEMP_THRESHOLD])
        wind_en = bool(cfg[CONF_WIND_SKIP_ENABLED])
        wind_th = float(cfg[CONF_WIND_SKIP_THRESHOLD])
        drip_exempt = bool(cfg[CONF_WIND_PROTECT_DRIP_EXEMPT])
        hw_en = bool(cfg[CONF_HEAT_WAVE_ENABLED])
        hw_th = float(cfg[CONF_HEAT_WAVE_TEMP_THRESHOLD])
        hw_days_req = max(1, min(7, int(cfg[CONF_HEAT_WAVE_DAYS])))
        hw_boost = max(5, min(60, int(cfg[CONF_HEAT_WAVE_BOOST_PCT])))
        cw_en = bool(cfg[CONF_COOL_WAVE_ENABLED])
        cw_th = float(cfg[CONF_COOL_WAVE_TEMP_THRESHOLD])
        cw_reduce = max(5, min(50, int(cfg[CONF_COOL_WAVE_REDUCE_PCT])))
        syr_en = bool(cfg[CONF_HEAT_WAVE_SYRINGE_ENABLED])
        syr_temp = float(cfg[CONF_HEAT_WAVE_SYRINGE_TEMP])
        syr_mins = max(1, min(10, int(cfg[CONF_HEAT_WAVE_SYRINGE_MINUTES])))
        syr_time = str(cfg[CONF_HEAT_WAVE_SYRINGE_TIME] or DEFAULT_HEAT_WAVE_SYRINGE_TIME)
        soil_max = int(cfg[CONF_SOIL_MOISTURE_MAX_PCT])

        tonight_low = forecast_lows[0] if forecast_lows else None
        today_high = forecast_highs[0] if forecast_highs else temp
        freeze_skip = freeze_en and (
            (temp is not None and temp <= freeze_th)
            or (tonight_low is not None and tonight_low <= freeze_th)
        )
        wind_skip = wind_en and wind_mph is not None and wind_mph >= wind_th and not freeze_skip

        skip_pins: list[int] = []
        if wind_skip:
            skip_pins = self._turf_pins() if drip_exempt else list(range(10))

        hot_streak = 0
        for idx, hi in enumerate(forecast_highs):
            eff_hi = max(hi, temp) if (idx == 0 and temp is not None) else hi
            if eff_hi >= hw_th:
                hot_streak += 1
            else:
                break
        if not forecast_highs and temp is not None and temp >= (hw_th + 5.0):
            hot_streak = hw_days_req

        soil_saturated = soil_pct is not None and soil_pct >= soil_max
        heat_wave = (
            hw_en
            and hot_streak >= hw_days_req
            and not soil_saturated
            and not freeze_skip
            and delay_days == 0
        )
        cool_wave = (
            cw_en
            and not heat_wave
            and not freeze_skip
            and delay_days == 0
            and today_high is not None
            and today_high <= cw_th
        )

        hot_for_mist = (temp is not None and temp >= syr_temp) or (
            today_high is not None and today_high >= syr_temp
        )
        syringe_recommended = (
            syr_en
            and hot_for_mist
            and not freeze_skip
            and not wind_skip
            and not soil_saturated
            and delay_days == 0
        )
        syringe_pins = self._turf_pins()[:6] if syringe_recommended else []

        scale_pct = 100
        if heat_wave:
            scale_pct = 100 + hw_boost
        elif cool_wave:
            scale_pct = max(50, 100 - cw_reduce)

        reasons: list[str] = []
        if freeze_skip:
            reasons.append(f"Freeze Skip (<= {freeze_th:.0f}F)")
        elif soil_saturated and hw_en and hot_streak >= hw_days_req:
            reasons.append(f"Heat boost vetoed (soil {soil_pct:.0f}% >= {soil_max}%)")
        elif heat_wave:
            reasons.append(f"Heat Wave +{hw_boost}% (>= {hw_th:.0f}F)")
        elif cool_wave:
            reasons.append(f"Cool Wave -{cw_reduce}% (<= {cw_th:.0f}F)")
        if wind_skip:
            reasons.append(f"Wind Skip ({wind_mph:.0f} mph)")
        if syringe_recommended:
            reasons.append(f"Cooling Mist {syr_mins}m @ {syr_time}")

        active = bool(freeze_skip or wind_skip or scale_pct != 100 or syringe_recommended)
        return {
            "active": active,
            "scale_pct": scale_pct,
            "skip_pins": skip_pins,
            "inhibit": bool(freeze_skip),
            "freeze_skip": bool(freeze_skip),
            "wind_skip": bool(wind_skip),
            "heat_wave_active": bool(heat_wave),
            "cool_wave_active": bool(cool_wave),
            "soil_saturated": bool(soil_saturated),
            "hot_streak": hot_streak,
            "syringe": {
                "enabled": syringe_recommended,
                "time": syr_time,
                "minutes": syr_mins,
                "pins": syringe_pins,
            },
            "reason": " · ".join(reasons) or "Normal",
            "ttl_seconds": 86400 if active else 0,
        }

    def _calculate_auto_rain_delay(
        self,
        opts: dict[str, Any],
        rain_today: float,
        col_48: float,
        ant_24: float,
        ant_48: float,
        today_pop: int,
        has_forecast: bool,
    ) -> int:
        """Calculate rain delay days using collected & anticipated thresholds."""
        if not opts.get(CONF_AUTO_RAIN_DELAY, DEFAULT_AUTO_RAIN_DELAY):
            return 0
        rain_thresh = float(opts.get(CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD))
        col_48_thresh = float(
            opts.get(CONF_COLLECTED_48H_THRESHOLD, DEFAULT_COLLECTED_48H_THRESHOLD)
        )
        ant_24_thresh = float(
            opts.get(CONF_ANTICIPATED_24H_THRESHOLD, DEFAULT_ANTICIPATED_24H_THRESHOLD)
        )
        ant_48_thresh = float(
            opts.get(CONF_ANTICIPATED_48H_THRESHOLD, DEFAULT_ANTICIPATED_48H_THRESHOLD)
        )
        pop_thresh = int(
            opts.get(CONF_FORECAST_POP_THRESHOLD, DEFAULT_FORECAST_POP_THRESHOLD)
        )
        hvy_thresh = float(opts.get(CONF_HEAVY_RAIN_THRESHOLD, DEFAULT_HEAVY_RAIN_THRESHOLD))
        std_days = int(opts.get(CONF_DELAY_DAYS, DEFAULT_DELAY_DAYS))
        hvy_days = int(opts.get(CONF_HEAVY_DELAY_DAYS, DEFAULT_HEAVY_DELAY_DAYS))

        should_delay = (
            rain_today >= rain_thresh
            or col_48 >= col_48_thresh
            or ant_24 >= ant_24_thresh
            or ant_48 >= ant_48_thresh
            or (has_forecast and today_pop >= pop_thresh)
        )
        if not should_delay:
            return 0

        combined_24 = rain_today + ant_24
        is_heavy = (
            combined_24 >= hvy_thresh
            or col_48 >= hvy_thresh * 1.25
            or ant_48 >= hvy_thresh * 1.25
        )
        return hvy_days if is_heavy else std_days

    async def _async_evaluate_and_push_weather(self, status_data: dict[str, Any]) -> None:
        """Push configured weather entities and apply automatic rain delay when needed."""
        opts = dict(self.config_entry.options) if self.config_entry else {}
        if not opts.get(CONF_WEATHER_PUSH_ENABLED, DEFAULT_WEATHER_PUSH_ENABLED):
            return

        rain_ent = (opts.get(CONF_RAIN_SENSOR) or "").strip()
        rain_48h_ent = (opts.get(CONF_RAIN_48H_SENSOR) or "").strip()
        temp_ent = (opts.get(CONF_TEMP_SENSOR) or "").strip()
        weather_ent = (opts.get(CONF_WEATHER_ENTITY) or "").strip()
        forecast_rain_ent = (opts.get(CONF_FORECAST_RAIN_SENSOR) or "").strip()
        forecast_rain_48h_ent = (opts.get(CONF_FORECAST_RAIN_48H_SENSOR) or "").strip()
        soil_ent = (opts.get(CONF_SOIL_MOISTURE_SENSOR) or "").strip()
        wind_ent = (opts.get(CONF_WIND_SENSOR) or "").strip()
        if not (
            rain_ent
            or rain_48h_ent
            or temp_ent
            or weather_ent
            or forecast_rain_ent
            or forecast_rain_48h_ent
            or soil_ent
            or wind_ent
        ):
            return

        rain_today = 0.0
        if rain_ent:
            st_rain = self.hass.states.get(rain_ent)
            parsed_rain = _parse_float(st_rain.state) if st_rain else None
            if parsed_rain is None:
                if not (
                    rain_48h_ent
                    or temp_ent
                    or weather_ent
                    or forecast_rain_ent
                    or forecast_rain_48h_ent
                    or soil_ent
                    or wind_ent
                ):
                    return
                rain_today = 0.0
            else:
                rain_today = parsed_rain

        col_48 = rain_today
        if rain_48h_ent:
            st_48 = self.hass.states.get(rain_48h_ent)
            parsed_48 = _parse_float(st_48.state) if st_48 else None
            if parsed_48 is not None:
                col_48 = parsed_48

        wx_details = await self._async_get_weather_forecast_details(weather_ent)
        ant_24 = wx_details["ant_24"]
        ant_48 = wx_details["ant_48"]
        today_pop = wx_details["today_pop"]
        if forecast_rain_ent:
            st_f24 = self.hass.states.get(forecast_rain_ent)
            parsed_f24 = _parse_float(st_f24.state) if st_f24 else None
            if parsed_f24 is not None:
                ant_24 = parsed_f24
        if forecast_rain_48h_ent:
            st_f48 = self.hass.states.get(forecast_rain_48h_ent)
            parsed_f48 = _parse_float(st_f48.state) if st_f48 else None
            if parsed_f48 is not None:
                ant_48 = parsed_f48
        ant_48 = max(ant_48, ant_24)

        temp: float | None = None
        if temp_ent:
            st_temp = self.hass.states.get(temp_ent)
            temp = _parse_float(st_temp.state) if st_temp else None
        elif weather_ent:
            st_w = self.hass.states.get(weather_ent)
            temp = _parse_float(st_w.attributes.get("temperature")) if st_w else None

        soil_pct: float | None = None
        if soil_ent:
            st_soil = self.hass.states.get(soil_ent)
            soil_pct = _parse_float(st_soil.state) if st_soil else None

        wind_mph: float | None = wx_details.get("wind_mph")
        if wind_ent:
            st_wind = self.hass.states.get(wind_ent)
            parsed_wind = _parse_float(st_wind.state) if st_wind else None
            if parsed_wind is not None:
                wind_mph = parsed_wind

        humidity: float | None = wx_details.get("humidity")
        source = self._resolve_weather_source(opts, rain_ent, weather_ent, forecast_rain_ent)
        has_forecast = bool(weather_ent or forecast_rain_ent)
        delay_days = self._calculate_auto_rain_delay(
            opts, rain_today, col_48, ant_24, ant_48, today_pop, has_forecast
        )
        modifier = self._build_local_weather_modifier(
            opts,
            temp,
            wx_details.get("forecast_highs") or [],
            wx_details.get("forecast_lows") or [],
            wind_mph,
            soil_pct,
            delay_days,
        )
        lows = wx_details.get("forecast_lows") or []
        highs = wx_details.get("forecast_highs") or []
        min_7d_low = min(lows) if lows else None
        self.last_weather_evaluation = {
            "evaluated_at": dt_util.utcnow().isoformat(),
            "source": source,
            "rain_today_in": round(rain_today, 2),
            "collected_48h_in": round(col_48, 2),
            "anticipated_24h_in": round(ant_24, 2),
            "anticipated_48h_in": round(ant_48, 2),
            "pop_pct": today_pop,
            "temp_f": round(temp, 1) if temp is not None else None,
            "today_high_f": round(highs[0], 1) if highs else (round(temp, 1) if temp is not None else None),
            "tonight_low_f": round(lows[0], 1) if lows else None,
            "hard_freeze_warning": bool(min_7d_low is not None and min_7d_low <= 28.0),
            "wind_mph": round(wind_mph, 1) if wind_mph is not None else None,
            "humidity_pct": round(humidity, 1) if humidity is not None else None,
            "soil_moisture_pct": round(soil_pct, 1) if soil_pct is not None else None,
            "soil_saturated": bool(modifier.get("soil_saturated")),
            "hot_streak": int(modifier.get("hot_streak", 0)),
            "recommended_delay_days": delay_days,
            "recommended_modifier": modifier,
        }

        if not opts.get(CONF_WEATHER_PUSH_ENABLED, DEFAULT_WEATHER_PUSH_ENABLED):
            return

        include_modifier = bool(modifier.get("active") or self._last_ha_modifier_active)
        sig = (
            round(rain_today, 2),
            round(temp, 1) if temp is not None else None,
            source,
            delay_days,
            round(soil_pct, 1) if soil_pct is not None else None,
            round(wind_mph, 1) if wind_mph is not None else None,
            modifier.get("active"),
            modifier.get("scale_pct"),
            tuple(modifier.get("skip_pins") or []),
            modifier.get("inhibit"),
        )

        if (
            not self._weather_dirty
            and sig == self._last_weather_signature
            and self._weather_push_counter > 0
        ):
            self._weather_push_counter -= 1
        else:
            try:
                has_extra = (
                    soil_pct is not None
                    or wind_mph is not None
                    or humidity is not None
                    or include_modifier
                )
                if hasattr(self.client, "push_weather") and not has_extra:
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
                    if soil_pct is not None:
                        payload["soil_moisture_pct"] = round(soil_pct, 1)
                    if wind_mph is not None:
                        payload["wind_speed_mph"] = round(wind_mph, 1)
                    if humidity is not None:
                        payload["humidity"] = round(humidity, 1)
                    if include_modifier:
                        payload["weather_modifier"] = modifier
                    await self.client._request("POST", "api/weather", json=payload)

                self._last_ha_modifier_active = bool(modifier.get("active"))
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

        # Optional daily Afternoon Cooling Mist trigger inside configured 15-min window
        syr_cfg = modifier.get("syringe") if isinstance(modifier.get("syringe"), dict) else {}
        if syr_cfg.get("enabled") and syr_cfg.get("pins"):
            now_local = dt_util.now()
            today_str = now_local.date().isoformat()
            is_busy = (
                any(status_data.get("relay_states", []))
                or bool(status_data.get("timers"))
                or bool((status_data.get("queue") or {}).get("active"))
            )
            if not is_busy and self._last_syringe_date != today_str:
                try:
                    t_parts = str(syr_cfg.get("time") or DEFAULT_HEAT_WAVE_SYRINGE_TIME).split(":")
                    target_mins = int(t_parts[0]) * 60 + int(t_parts[1])
                    cur_mins = now_local.hour * 60 + now_local.minute
                    if target_mins <= cur_mins < (target_mins + 15):
                        self._last_syringe_date = today_str
                        await self.async_run_cooling_mist(
                            pins=list(syr_cfg["pins"]),
                            minutes=int(syr_cfg.get("minutes") or DEFAULT_HEAT_WAVE_SYRINGE_MINUTES),
                        )
                except Exception as err:
                    _LOGGER.debug("Error evaluating Cooling Mist window: %s", err)

    async def async_apply_weather_modifier(self, modifier: dict[str, Any]) -> None:
        """Immediately push an explicit weather modifier payload to controller via /api/weather."""
        eval_data = self.last_weather_evaluation or {}
        payload: dict[str, Any] = {
            "rain_today_in": float(eval_data.get("rain_today_in") or 0.0),
            "source": str(eval_data.get("source") or "Home Assistant"),
            "delay_days": 0,
            "weather_modifier": modifier,
        }
        if eval_data.get("temp_f") is not None:
            payload["temp"] = eval_data["temp_f"]
        if eval_data.get("soil_moisture_pct") is not None:
            payload["soil_moisture_pct"] = eval_data["soil_moisture_pct"]
        if eval_data.get("wind_mph") is not None:
            payload["wind_speed_mph"] = eval_data["wind_mph"]
        await self.client._request("POST", "api/weather", json=payload)
        self._last_ha_modifier_active = bool(modifier.get("active"))

    async def async_run_cooling_mist(
        self,
        pins: list[int] | None = None,
        minutes: int | None = None,
    ) -> None:
        """Start a short sequential cooling mist run on turf pins."""
        opts = resolve_weather_options(dict(self.config_entry.options) if self.config_entry else {})
        safe_mins = max(1, min(10, int(minutes or opts[CONF_HEAT_WAVE_SYRINGE_MINUTES])))
        target_pins = pins if pins else self._turf_pins()[:6]
        if not target_pins:
            target_pins = [0]
        queue = [{"pin": int(p), "duration_mins": safe_mins} for p in target_pins]
        await self.client._request("POST", "start-run-queue", json={"queue": queue})

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

        # Schedules refresh (every ~60s, on startup, or immediately after schedule changes)
        if self._schedules_dirty or not self._cached_schedules or self._schedules_poll_counter <= 0:
            sched_res = await self._get_schedules()
            if sched_res is not None:
                self._cached_schedules = sched_res
                self._schedules_dirty = False
                self._schedules_poll_counter = 6  # 6 x 10s = 60s
        else:
            self._schedules_poll_counter -= 1

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

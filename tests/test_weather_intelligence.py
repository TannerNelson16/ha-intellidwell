"""Test smart weather automation in IntelliDwell Home Assistant integration."""
from unittest.mock import patch

from homeassistant import data_entry_flow
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from custom_components.intellidwell.const import (
    CONF_FREEZE_SKIP_ENABLED,
    CONF_FREEZE_TEMP_THRESHOLD,
    CONF_HEAT_WAVE_BOOST_PCT,
    CONF_HEAT_WAVE_ENABLED,
    CONF_HEAT_WAVE_TEMP_THRESHOLD,
    CONF_RAIN_SENSOR,
    CONF_SOIL_MOISTURE_MAX_PCT,
    CONF_SOIL_MOISTURE_SENSOR,
    CONF_TEMP_SENSOR,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_PUSH_ENABLED,
    CONF_WIND_SENSOR,
    CONF_WIND_SKIP_ENABLED,
    CONF_WIND_SKIP_THRESHOLD,
    DOMAIN,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_weather_modifier_heat_wave_soil_veto_freeze_and_wind_drip_exempt(
    hass: HomeAssistant,
) -> None:
    """Verify HA computes Heat Wave boost, soil veto, Freeze Skip, and Wind Drift Guard."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.1.1.1"},
        options={
            CONF_WEATHER_PUSH_ENABLED: True,
            CONF_RAIN_SENSOR: "sensor.daily_rain",
            CONF_TEMP_SENSOR: "sensor.outdoor_temp",
            CONF_SOIL_MOISTURE_SENSOR: "sensor.soil_moisture",
            CONF_WIND_SENSOR: "sensor.wind_mph",
            CONF_WEATHER_ENTITY: "weather.home",
            CONF_HEAT_WAVE_ENABLED: True,
            CONF_HEAT_WAVE_TEMP_THRESHOLD: 90.0,
            CONF_HEAT_WAVE_BOOST_PCT: 20,
            CONF_FREEZE_SKIP_ENABLED: True,
            CONF_FREEZE_TEMP_THRESHOLD: 34.0,
            CONF_WIND_SKIP_ENABLED: True,
            CONF_WIND_SKIP_THRESHOLD: 20.0,
            CONF_SOIL_MOISTURE_MAX_PCT: 45,
        },
        entry_id="mock_smart_wx_entry",
    )
    entry.add_to_hass(hass)

    hass.states.async_set("sensor.daily_rain", "0.0")
    hass.states.async_set("sensor.outdoor_temp", "94")
    hass.states.async_set("sensor.soil_moisture", "28")
    hass.states.async_set("sensor.wind_mph", "5")
    hass.states.async_set(
        "weather.home",
        "sunny",
        {
            "temperature": 94,
            "humidity": 25,
            "forecast": [
                {"temperature": 94, "templow": 65, "precipitation": 0.0, "precipitation_probability": 0},
                {"temperature": 93, "templow": 64, "precipitation": 0.0, "precipitation_probability": 0},
            ],
        },
    )

    status_payload = {
        "relay_states": [0] * 10,
        "timers": {},
        "queue": {},
        "weather_modifier": {
            "active": True,
            "scale_pct": 120,
            "heat_wave_active": True,
            "reason": "Heat Wave +20%",
        },
    }

    with patch(
        "custom_components.intellidwell.IntelliDwellClient.get_status",
        return_value=status_payload,
    ), patch(
        "custom_components.intellidwell.coordinator.IntelliDwellCoordinator._get_settings_raw",
        return_value={"zone_names": ["Front Turf", "Flower Bed Drip", "Back Turf"]},
    ), patch(
        "custom_components.intellidwell._safe_client_request",
        return_value={"status": "ok"},
    ) as mock_req, patch(
        "homeassistant.components.http.HomeAssistantHTTP.async_register_static_paths"
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # 1. Heat Wave Boost +20% pushed
        wx_calls = [c for c in mock_req.call_args_list if "api/weather" in c.args]
        assert wx_calls
        p1 = wx_calls[-1].kwargs["json"]
        assert p1["soil_moisture_pct"] == 28.0
        assert p1["weather_modifier"]["heat_wave_active"] is True
        assert p1["weather_modifier"]["scale_pct"] == 120

        mod_sensor = hass.states.get("sensor.intellidwell_sprinkler_controller_weather_modifier")
        assert mod_sensor is not None
        assert mod_sensor.state == "Heat Wave (+20%)"

        coord = hass.data[DOMAIN][entry.entry_id]

        # 2. Saturated Soil Moisture (52% >= 45%) vetoes Heat Wave boost back to 100%
        hass.states.async_set("sensor.soil_moisture", "52")
        await hass.async_block_till_done()
        wx_calls = [c for c in mock_req.call_args_list if "api/weather" in c.args]
        p2 = wx_calls[-1].kwargs["json"]
        assert p2["weather_modifier"]["scale_pct"] == 100
        assert p2["weather_modifier"]["active"] is False

        # 3. High Wind (24 mph) skips turf zones (0, 2) while leaving "Flower Bed Drip" (1) exempt
        hass.states.async_set("sensor.soil_moisture", "25")
        hass.states.async_set("sensor.wind_mph", "24")
        coord.mark_weather_dirty()
        await coord.async_refresh()
        await hass.async_block_till_done()
        wx_calls = [c for c in mock_req.call_args_list if "api/weather" in c.args]
        p3 = wx_calls[-1].kwargs["json"]
        assert p3["wind_speed_mph"] == 24.0, p3
        assert p3["weather_modifier"]["wind_skip"] is True, p3
        assert 0 in p3["weather_modifier"]["skip_pins"]
        assert 2 in p3["weather_modifier"]["skip_pins"]
        assert 1 not in p3["weather_modifier"]["skip_pins"]

        # 4. Freeze Skip inhibits all watering when outdoor temp drops to 31F
        hass.states.async_set("sensor.outdoor_temp", "31")
        coord.mark_weather_dirty()
        await coord.async_refresh()
        await hass.async_block_till_done()
        wx_calls = [c for c in mock_req.call_args_list if "api/weather" in c.args]
        p4 = wx_calls[-1].kwargs["json"]
        assert p4["weather_modifier"]["freeze_skip"] is True
        assert p4["weather_modifier"]["inhibit"] is True


async def test_options_flow_smart_weather_fields(hass: HomeAssistant) -> None:
    """Test saving soil moisture, heat wave, freeze skip, and wind skip options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.1.1.1"},
        options={},
        entry_id="mock_smart_opts",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.intellidwell.IntelliDwellClient.get_status",
        return_value={"relay_states": [0] * 10, "timers": {}, "queue": {}},
    ), patch(
        "homeassistant.components.http.HomeAssistantHTTP.async_register_static_paths"
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    with patch(
        "custom_components.intellidwell.coordinator.IntelliDwellCoordinator.async_request_refresh"
    ):
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_WEATHER_PUSH_ENABLED: True,
                CONF_SOIL_MOISTURE_SENSOR: "sensor.lawn_soil",
                CONF_WIND_SENSOR: "sensor.backyard_wind",
                CONF_SOIL_MOISTURE_MAX_PCT: 50,
                CONF_HEAT_WAVE_TEMP_THRESHOLD: 92,
                CONF_HEAT_WAVE_BOOST_PCT: 30,
                CONF_FREEZE_TEMP_THRESHOLD: 33,
                CONF_WIND_SKIP_THRESHOLD: 18,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SOIL_MOISTURE_SENSOR] == "sensor.lawn_soil"
    assert entry.options[CONF_WIND_SENSOR] == "sensor.backyard_wind"
    assert entry.options[CONF_HEAT_WAVE_BOOST_PCT] == 30
    assert entry.options[CONF_WIND_SKIP_THRESHOLD] == 18

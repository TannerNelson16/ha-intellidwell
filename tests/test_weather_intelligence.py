"""Test smart weather automation in IntelliDwell Home Assistant integration."""
import subprocess
from pathlib import Path
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


async def test_weather_card_services_and_cool_wave_and_cooling_mist(hass: HomeAssistant) -> None:
    """Verify card services update options, compute Cool Wave, apply/clear modifier, and run cooling mist."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.1.1.1"},
        options={
            CONF_WEATHER_PUSH_ENABLED: True,
            CONF_TEMP_SENSOR: "sensor.outdoor_temp",
            CONF_WEATHER_ENTITY: "weather.home",
        },
        entry_id="mock_card_svc",
    )
    entry.add_to_hass(hass)

    hass.states.async_set("sensor.outdoor_temp", "54")
    hass.states.async_set(
        "weather.home",
        "cloudy",
        {
            "temperature": 54,
            "forecast": [
                {"temperature": 55, "templow": 42, "precipitation": 0.0, "precipitation_probability": 0},
            ],
        },
    )

    with (
        patch(
            "custom_components.intellidwell.IntelliDwellClient.get_status",
            return_value={"relay_states": [0] * 10, "timers": {}, "queue": {}},
        ),
        patch(
            "custom_components.intellidwell.coordinator.IntelliDwellCoordinator._get_settings_raw",
            return_value={"zone_names": ["Front Turf", "Rose Bed Drip", "Back Turf"]},
        ),
        patch(
            "custom_components.intellidwell._safe_client_request",
            return_value={"status": "ok"},
        ) as mock_req,
        patch("homeassistant.components.http.HomeAssistantHTTP.async_register_static_paths"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        mod_sensor = hass.states.get("sensor.intellidwell_sprinkler_controller_weather_modifier")
        assert mod_sensor is not None
        assert mod_sensor.attributes["config_entry_id"] == entry.entry_id
        assert mod_sensor.attributes["weather_evaluation"]["recommended_modifier"]["cool_wave_active"] is True
        assert mod_sensor.attributes["weather_evaluation"]["recommended_modifier"]["scale_pct"] == 80

        # 1. Card updates Cool Wave reduce pct + enables Cooling Mist and applies immediately
        await hass.services.async_call(
            DOMAIN,
            "update_weather_settings",
            {
                "config_entry_id": entry.entry_id,
                "options": {
                    "cool_wave_reduce_pct": 25,
                    "heat_wave_syringe_enabled": True,
                    "heat_wave_syringe_minutes": 4,
                },
                "apply_now": True,
            },
            blocking=True,
        )
        await hass.async_block_till_done()
        assert entry.options["cool_wave_reduce_pct"] == 25
        assert entry.options["heat_wave_syringe_enabled"] is True

        wx_calls = [c for c in mock_req.call_args_list if "api/weather" in c.args]
        assert wx_calls
        assert wx_calls[-1].kwargs["json"]["weather_modifier"]["scale_pct"] == 75

        # 2. Clear override sends inactive modifier
        await hass.services.async_call(
            DOMAIN,
            "apply_weather_modifier",
            {"config_entry_id": entry.entry_id, "mode": "clear"},
            blocking=True,
        )
        wx_calls = [c for c in mock_req.call_args_list if "api/weather" in c.args]
        assert wx_calls[-1].kwargs["json"]["weather_modifier"]["active"] is False

        # 3. Run Cooling Mist triggers non-drip zones via start-run-queue
        await hass.services.async_call(
            DOMAIN,
            "run_cooling_mist",
            {"config_entry_id": entry.entry_id, "minutes": 3},
            blocking=True,
        )
        queue_calls = [c for c in mock_req.call_args_list if "start-run-queue" in c.args]
        assert queue_calls
        q_items = queue_calls[-1].kwargs["json"]["queue"]
        pins = [x["pin"] for x in q_items]
        assert 0 in pins and 2 in pins and 1 not in pins
        assert all(x["duration_mins"] == 3 for x in q_items)


def test_weather_card_js_runs_presets_simulator_and_saves_without_clobber() -> None:
    """Execute real intellidwell-weather-card.js in Node VM."""
    card_path = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "intellidwell"
        / "www"
        / "intellidwell-weather-card.js"
    )
    node_script = r"""
const fs = require("fs");
const vm = require("vm");

const code = fs.readFileSync(process.argv[1], "utf8");

class FakeEl {
  constructor() {
    this.innerHTML = "";
    this.listeners = {};
    this.shadowRoot = {
      innerHTML: "",
      activeElement: null,
      getElementById: () => null,
      querySelectorAll: () => [],
    };
  }
  attachShadow() { return this.shadowRoot; }
  querySelector() { return null; }
  addEventListener(ev, fn) { this.listeners[ev] = fn; }
}

const defined = {};
const calls = [];
const sandbox = {
  HTMLElement: FakeEl,
  customElements: { define: (n, c) => { defined[n] = c; } },
  window: {},
  document: { createElement: () => new FakeEl() },
  console: { info: () => {}, error: console.error, log: () => {} },
  setTimeout: () => 1,
  clearTimeout: () => {},
  CustomEvent: function(t, i) { this.type = t; this.detail = i && i.detail; },
};
sandbox.window = sandbox;
vm.runInNewContext(code, sandbox);

const CardCls = defined["intellidwell-weather-card"];
if (!CardCls) throw new Error("Missing intellidwell-weather-card");

const card = new CardCls();
card.setConfig({ title: "Lawn Weather" });
card.hass = {
  entities: {
    "sensor.intellidwell_sprinkler_controller_weather_modifier": { platform: "intellidwell" },
    "weather.home": { platform: "nws" },
    "sensor.outdoor_rain": { platform: "ambient" },
  },
  states: {
    "sensor.intellidwell_sprinkler_controller_weather_modifier": {
      entity_id: "sensor.intellidwell_sprinkler_controller_weather_modifier",
      state: "Heat Wave (+20%)",
      attributes: {
        active: true,
        scale_pct: 120,
        heat_wave_active: true,
        cool_wave_active: false,
        rain_delay_days: 0,
        config_entry_id: "entry_abc",
        weather_options: {
          heat_wave_boost_pct: 20,
          cool_wave_reduce_pct: 20,
          rain_sensor: "sensor.outdoor_rain",
          weather_entity: "weather.home",
        },
        weather_evaluation: {
          source: "Ambient PWS",
          temp_f: 94,
          tonight_low_f: 68,
          rain_today_in: 0,
          collected_48h_in: 0,
          anticipated_24h_in: 0,
          anticipated_48h_in: 0,
          pop_pct: 5,
          wind_mph: 6,
          soil_moisture_pct: 29,
          hard_freeze_warning: false,
          recommended_modifier: { active: true, scale_pct: 120, reason: "Heat Wave +20%" },
        },
      },
    },
    "weather.home": { entity_id: "weather.home", state: "sunny", attributes: { friendly_name: "Home Forecast" } },
    "sensor.outdoor_rain": { entity_id: "sensor.outdoor_rain", state: "0.0", attributes: { friendly_name: "Outdoor Rain" } },
  },
  callService: async (dom, svc, data) => { calls.push({ dom, svc, data }); },
};

if (!card.shadowRoot.innerHTML.includes("24m")) throw new Error("Missing 24m Heat Wave simulator readout");
if (!card.shadowRoot.innerHTML.includes("Ambient PWS")) throw new Error("Missing Ambient PWS evaluation source");
if (!card.shadowRoot.innerHTML.includes("Home Forecast")) throw new Error("Missing Home Forecast entity picker option");

// Verify dirty draft protection against incoming hass poll
card._dirty = true;
card.shadowRoot.innerHTML = "<div id='sentinel'>KEEP_USER_SLIDER</div>";
card.hass = card._hass;
if (!card.shadowRoot.innerHTML.includes("KEEP_USER_SLIDER")) {
  throw new Error("Dirty slider state was clobbered by background hass poll");
}

console.log("WX_CARD_TESTS_PASSED");
"""
    res = subprocess.run(
        ["node", "-e", node_script, str(card_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Node test failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"
    assert "WX_CARD_TESTS_PASSED" in res.stdout

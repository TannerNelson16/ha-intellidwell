"""Tests for scheduler card entity discovery, resource cache-busting, and schedule polling."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from pyintellidwell import IntelliDwellConnectionError

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

from custom_components.intellidwell.const import CARD_VERSION, DOMAIN
from pytest_homeassistant_custom_component.common import MockConfigEntry


REPO_ROOT = Path(__file__).resolve().parents[1]
CARD_JS_PATH = REPO_ROOT / "custom_components" / "intellidwell" / "www" / "intellidwell-scheduler-card.js"


async def test_lovelace_resource_cache_busts_on_upgrade(hass: HomeAssistant) -> None:
    """Upgrading from unversioned 1.0.3 card URL updates Lovelace resource with ?v=CARD_VERSION."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "1.1.1.1"}, entry_id="mock_entry")
    entry.add_to_hass(hass)

    mock_resources = MagicMock()
    mock_resources.loaded = True
    mock_resources.async_items.return_value = [
        {"id": "res_123", "url": "/intellidwell/intellidwell-scheduler-card.js", "type": "module"}
    ]
    mock_resources.async_update_item = AsyncMock()
    mock_resources.async_create_item = AsyncMock()
    hass.data["lovelace"] = SimpleNamespace(resources=mock_resources)

    with (
        patch(
            "custom_components.intellidwell.IntelliDwellClient.get_status",
            return_value={"relay_states": [0] * 10, "timers": {}, "queue": {}},
        ),
        patch("homeassistant.components.http.HomeAssistantHTTP.async_register_static_paths"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    mock_resources.async_update_item.assert_awaited_once_with(
        "res_123",
        {
            "res_type": "module",
            "url": f"/intellidwell/intellidwell-scheduler-card.js?v={CARD_VERSION}",
        },
    )
    mock_resources.async_create_item.assert_not_called()


async def test_coordinator_handles_schedule_error_and_populates_switch_attrs(
    hass: HomeAssistant,
    area_registry: ar.AreaRegistry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Zone switches populate schedules cleanly even when get_schedules recovers after an error or device has an area."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "1.1.1.1"}, entry_id="mock_entry")
    entry.add_to_hass(hass)

    garage = area_registry.async_get_or_create("Garage")
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="IntelliDwell Sprinkler Controller",
    )
    device_registry.async_update_device(device.id, area_id=garage.id)

    sample_schedules = [
        {
            "enabled": True,
            "schedules": [
                {
                    "id": "sch_1",
                    "days": ["Mon", "Wed", "Fri"],
                    "onTime": "06:00",
                    "offTime": "06:20",
                    "enabled": True,
                }
            ],
        }
    ] + [{"enabled": False, "schedules": []} for _ in range(9)]

    sched_attempts = 0

    async def fake_safe_request(_self, _method: str, path: str, **_kwargs):
        nonlocal sched_attempts
        if path == "api/status":
            return {"relay_states": [0] * 10, "timers": {}, "queue": {}}
        if path == "get-schedules":
            sched_attempts += 1
            if sched_attempts == 1:
                raise IntelliDwellConnectionError("temporary busy")
            return sample_schedules
        if path == "get-rain-delay":
            return {"days_remaining": 0}
        if path == "get-settings":
            return {"zone_names": ["Chicken Area"] + [f"Zone {i}" for i in range(2, 11)]}
        return {}

    with (
        patch(
            "custom_components.intellidwell.IntelliDwellClient.get_status",
            return_value={"relay_states": [0] * 10, "timers": {}, "queue": {}},
        ),
        patch("custom_components.intellidwell._safe_client_request", side_effect=fake_safe_request),
        patch("homeassistant.components.http.HomeAssistantHTTP.async_register_static_paths"),
    ):
        # First refresh happens during setup (get-schedules raises -> caught cleanly)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN][entry.entry_id]
        # Second refresh recovers schedules cleanly because failed dirty poll keeps retrying
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert sched_attempts == 2

    # Regardless of generated entity_id prefix, unique_id lookup locates zone 1 switch with schedules
    zone1_entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_zone_0")
    assert zone1_entity_id is not None
    state = hass.states.get(zone1_entity_id)
    assert state is not None
    assert state.attributes["zone_index"] == 1
    assert state.attributes["schedules"] == sample_schedules[0]["schedules"]


def test_scheduler_card_js_matches_area_prefixed_and_renamed_entities() -> None:
    """Execute the real JS card in Node to verify Garage-prefixed, renamed, and non-matching switches."""
    node_script = r"""
const fs = require("fs");
const vm = require("vm");

const cardCode = fs.readFileSync(process.argv[1], "utf8");

class FakeElement {
  constructor() {
    this.innerHTML = "";
    this.shadowRoot = {
      innerHTML: "",
      getElementById: () => null,
      querySelectorAll: () => [],
    };
  }
  attachShadow() {
    return this.shadowRoot;
  }
}

const definedElements = {};
const sandbox = {
  HTMLElement: FakeElement,
  customElements: {
    define: (name, cls) => { definedElements[name] = cls; },
  },
  window: {},
  document: {
    createElement: () => new FakeElement(),
  },
  console: { info: () => {}, error: console.error, log: () => {} },
  setInterval: () => 1,
  clearInterval: () => {},
  CustomEvent: function(type, init) { this.type = type; this.detail = init && init.detail; },
};
sandbox.window = sandbox;

vm.runInNewContext(cardCode, sandbox);
const CardCls = definedElements["intellidwell-scheduler-card"];
if (!CardCls) throw new Error("Card class was not registered");

const assert = (cond, msg) => {
  if (!cond) throw new Error("Assertion failed: " + msg);
};

// Case 1: Real HA entity IDs prefixed with Area ("garage_") + custom renamed switch
const card = new CardCls();
card.setConfig({ title: "Sprinkler Schedules", show_zone_filter: true });
card.hass = {
  entities: {
    "switch.garage_intellidwell_sprinkler_controller_zone_1_chicken_area": { platform: "intellidwell" },
    "switch.custom_front_lawn": { platform: "intellidwell" },
    "switch.other_vendor_valve": { platform: "rainbird" },
  },
  states: {
    "switch.garage_intellidwell_sprinkler_controller_zone_1_chicken_area": {
      entity_id: "switch.garage_intellidwell_sprinkler_controller_zone_1_chicken_area",
      state: "off",
      attributes: {
        zone_index: 1,
        zone_name: "Zone 1: Chicken Area",
        schedule_enabled: false,
        schedules: [
          { id: "sch_1", days: ["Tue", "Thu"], onTime: "01:00", offTime: "01:30", enabled: true }
        ],
        timer_remaining_seconds: 0,
      },
    },
    "switch.custom_front_lawn": {
      entity_id: "switch.custom_front_lawn",
      state: "off",
      attributes: {
        zone_index: 2,
        zone_name: "Zone 2: Front Lawn",
        schedule_enabled: true,
        schedules: [],
        timer_remaining_seconds: 0,
      },
    },
    "switch.other_vendor_valve": {
      entity_id: "switch.other_vendor_valve",
      state: "off",
      attributes: {
        zone_index: 1,
        zone_name: "Other Valve",
        schedule_enabled: true,
        schedules: [],
      },
    },
  },
  callService: () => {},
};

const found = card._getScheduleEntities();
assert(found.length === 2, `Expected 2 zones, got ${found.length}`);
assert(found[0].attributes.zone_index === 1, "Zone 1 sorted first");
assert(found[1].attributes.zone_index === 2, "Zone 2 sorted second");

const html = card.shadowRoot.innerHTML;
assert(!html.includes("No sprinkler zones found"), "Card must not show empty zones notice");
assert(html.includes("Zone 1: Chicken Area"), "Missing Zone 1 title");
assert(html.includes("01:00 \u2013 01:30"), "Missing schedule time range");
assert(html.includes("30 min"), "Missing schedule duration");
assert(!html.includes("Other Valve"), "Unrelated vendor valve leaked into card");

// Case 2: Fallback without hass.entities registry populated
const cardFallback = new CardCls();
cardFallback.setConfig({ title: "Fallback Test" });
cardFallback.hass = {
  states: {
    "switch.garage_intellidwell_sprinkler_controller_zone_6_front_flower_area": {
      entity_id: "switch.garage_intellidwell_sprinkler_controller_zone_6_front_flower_area",
      state: "off",
      attributes: {
        zone_index: 6,
        zone_name: "Zone 6: Front Flower Area",
        schedule_enabled: true,
        schedules: [{ id: "sch_6", days: ["Mon"], onTime: "05:00", offTime: "05:15", enabled: true }],
      },
    },
  },
};
assert(cardFallback._getScheduleEntities().length === 1, "Fallback without hass.entities failed");

// Case 3: Open modal prevents background hass polls from wiping HTML
card._modalState = { mode: "add", zoneIndex: 1, scheduleId: null, days: ["Mon"], onTime: "06:00", offTime: "06:20", durationMins: 20 };
card.shadowRoot.innerHTML = "<div id='sentinel'>OPEN_MODAL</div>";
card.hass = card._hass;
assert(card.shadowRoot.innerHTML.includes("OPEN_MODAL"), "Open modal was clobbered by hass update");

console.log("JS_CARD_TESTS_PASSED");
"""
    res = subprocess.run(
        ["node", "-e", node_script, str(CARD_JS_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Node test failed:\nSTDOUT:{res.stdout}\nSTDERR:{res.stderr}"
    assert "JS_CARD_TESTS_PASSED" in res.stdout

"""Test switch platform for IntelliDwell Sprinkler Controller."""
from unittest.mock import patch

from pyintellidwell import IntelliDwellConnectionError

from homeassistant import config_entries
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from homeassistant.components.intellidwell.const import DOMAIN
from tests.common import MockConfigEntry

async def test_switches(hass: HomeAssistant, entity_registry: er.EntityRegistry) -> None:
    """Test switch setup and operations."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.1.1.1"},
        entry_id="mock_entry",
    )
    entry.add_to_hass(hass)

    status_data = {
        "relay_states": [0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
        "timers": {},
        "queue": {}
    }

    with patch(
        "homeassistant.components.intellidwell.IntelliDwellClient.get_status",
        return_value=status_data,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entity_registry.async_is_registered("switch.intellidwell_sprinkler_controller_zone_1")
        assert entity_registry.async_is_registered("switch.intellidwell_sprinkler_controller_zone_2")

        state1 = hass.states.get("switch.intellidwell_sprinkler_controller_zone_1")
        assert state1.state == "off"
        
        state2 = hass.states.get("switch.intellidwell_sprinkler_controller_zone_2")
        assert state2.state == "on"

        with patch(
            "homeassistant.components.intellidwell.IntelliDwellClient.set_relay"
        ) as mock_set_relay:
            await hass.services.async_call(
                SWITCH_DOMAIN,
                SERVICE_TURN_ON,
                {ATTR_ENTITY_ID: "switch.intellidwell_sprinkler_controller_zone_1"},
                blocking=True,
            )
            mock_set_relay.assert_called_once_with(0, "on")

        with patch(
            "homeassistant.components.intellidwell.IntelliDwellClient.set_relay"
        ) as mock_set_relay:
            await hass.services.async_call(
                SWITCH_DOMAIN,
                SERVICE_TURN_OFF,
                {ATTR_ENTITY_ID: "switch.intellidwell_sprinkler_controller_zone_2"},
                blocking=True,
            )
            mock_set_relay.assert_called_once_with(1, "off")

async def test_switch_setup_failure(hass: HomeAssistant) -> None:
    """Test switch platform setup fails when the coordinator cannot connect initially."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.1.1.1"},
        entry_id="mock_entry",
    )
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.intellidwell.IntelliDwellClient.get_status",
        side_effect=IntelliDwellConnectionError,
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state == config_entries.ConfigEntryState.SETUP_RETRY

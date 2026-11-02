"""Test switch platform for IntelliDwell Sprinkler Controller."""
from unittest.mock import patch

from pyintellidwell import IntelliDwellConnectionError

from homeassistant import config_entries
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.intellidwell.const import DOMAIN
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
        "custom_components.intellidwell.IntelliDwellClient.get_status",
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
            "custom_components.intellidwell.IntelliDwellClient.set_relay"
        ) as mock_set_relay:
            await hass.services.async_call(
                SWITCH_DOMAIN,
                SERVICE_TURN_ON,
                {ATTR_ENTITY_ID: "switch.intellidwell_sprinkler_controller_zone_1"},
                blocking=True,
            )
            mock_set_relay.assert_called_once_with(0, "on")

        with patch(
            "custom_components.intellidwell.IntelliDwellClient.set_relay"
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
        "custom_components.intellidwell.IntelliDwellClient.get_status",
        side_effect=IntelliDwellConnectionError,
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state == config_entries.ConfigEntryState.SETUP_RETRY


async def test_switch_preserves_user_rename(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test user custom rename is preserved and not overwritten on coordinator updates."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.1.1.1"},
        entry_id="mock_entry",
    )
    entry.add_to_hass(hass)

    status_data = {
        "relay_states": [0] * 10,
        "timers": {},
        "queue": {},
        "settings": {"zone_names": ["Front Yard"]},
    }

    with patch(
        "custom_components.intellidwell.IntelliDwellClient.get_status",
        return_value=status_data,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Initial zone name entity
        entity_id = "switch.intellidwell_sprinkler_controller_zone_1"
        reg_entry = entity_registry.async_get(entity_id)
        assert reg_entry is not None

        # User renames the entity in Home Assistant
        entity_registry.async_update_entity(entity_id, name="My Custom Sprinkler Name")
        await hass.async_block_till_done()

        # Trigger coordinator refresh
        coordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        # The user's custom name should still be intact
        reg_entry_after = entity_registry.async_get(entity_id)
        assert reg_entry_after.name == "My Custom Sprinkler Name"


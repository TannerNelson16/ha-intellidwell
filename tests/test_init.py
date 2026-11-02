"""Test __init__ for IntelliDwell Sprinkler Controller."""
from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from custom_components.intellidwell.const import DOMAIN
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_setup_and_unload_entry(hass: HomeAssistant) -> None:
    """Test setting up and unloading an entry."""
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
    }

    with patch(
        "custom_components.intellidwell.IntelliDwellClient.get_status",
        return_value=status_data,
    ), patch(
        "homeassistant.components.http.HomeAssistantHTTP.async_register_static_paths"
    ) as mock_register_static:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Check static path registered
        mock_register_static.assert_called_once()
        static_configs = mock_register_static.call_args[0][0]
        assert static_configs[0].url_path == "/intellidwell/intellidwell-scheduler-card.js"

        # Check services registered
        assert hass.services.has_service(DOMAIN, "start_timer")
        assert hass.services.has_service(DOMAIN, "cancel_timer")
        assert hass.services.has_service(DOMAIN, "add_schedule")
        assert hass.services.has_service(DOMAIN, "edit_schedule")
        assert hass.services.has_service(DOMAIN, "delete_schedule")
        assert hass.services.has_service(DOMAIN, "toggle_schedule_item")
        assert hass.services.has_service(DOMAIN, "toggle_zone_schedule")

        # Unload entry
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        # Check services removed after last entry unloaded
        assert not hass.services.has_service(DOMAIN, "start_timer")
        assert not hass.services.has_service(DOMAIN, "cancel_timer")

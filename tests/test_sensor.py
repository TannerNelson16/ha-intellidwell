"""Test sensor platform for IntelliDwell Sprinkler Controller."""
from unittest.mock import patch

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from custom_components.intellidwell.const import DOMAIN
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_sensors(hass: HomeAssistant) -> None:
    """Test sensor values for active zone and timer remaining."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.1.1.1"},
        entry_id="mock_entry",
    )
    entry.add_to_hass(hass)

    status_data = {
        "relay_states": [1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        "timers": {"0": 600},
        "queue": {},
        "settings": {"zone_names": ["Front Lawn"]},
    }

    with patch(
        "custom_components.intellidwell.IntelliDwellClient.get_status",
        return_value=status_data,
    ), patch(
        "custom_components.intellidwell.coordinator.IntelliDwellCoordinator._get_settings_raw",
        return_value={"zone_names": ["Front Lawn"]},
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        active_zone = hass.states.get("sensor.intellidwell_sprinkler_controller_active_zone")
        assert active_zone is not None
        assert active_zone.state == "Zone 1: Front Lawn"

        remaining = hass.states.get("sensor.intellidwell_sprinkler_controller_watering_time_remaining")
        assert remaining is not None
        assert remaining.attributes["remaining_seconds"] == 600
        assert remaining.attributes["remaining_minutes"] == 10.0

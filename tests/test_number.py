"""Test number platform for IntelliDwell Sprinkler Controller."""
from unittest.mock import patch

from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN, SERVICE_SET_VALUE
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST
from homeassistant.core import HomeAssistant

from custom_components.intellidwell.const import DOMAIN
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_rain_delay_number(hass: HomeAssistant) -> None:
    """Test rain delay number entity and service call."""
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
        "rain_delay": 2,
    }

    with patch(
        "custom_components.intellidwell.IntelliDwellClient.get_status",
        return_value=status_data,
    ), patch(
        "custom_components.intellidwell.coordinator.IntelliDwellCoordinator._get_rain_delay",
        return_value={"days_remaining": 2},
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("number.intellidwell_sprinkler_controller_rain_delay")
        assert state is not None
        assert float(state.state) == 2.0

        with patch(
            "custom_components.intellidwell.IntelliDwellClient.set_rain_delay"
        ) as mock_set_rain_delay:
            await hass.services.async_call(
                NUMBER_DOMAIN,
                SERVICE_SET_VALUE,
                {
                    ATTR_ENTITY_ID: "number.intellidwell_sprinkler_controller_rain_delay",
                    "value": 3,
                },
                blocking=True,
            )
            mock_set_rain_delay.assert_called_once_with(3)

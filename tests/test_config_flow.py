"""Test the IntelliDwell Sprinkler Controller config flow."""
from unittest.mock import patch

from pyintellidwell import IntelliDwellConnectionError

from homeassistant import config_entries, data_entry_flow
from custom_components.intellidwell.const import (
    CONF_ANTICIPATED_24H_THRESHOLD,
    CONF_ANTICIPATED_48H_THRESHOLD,
    CONF_AUTO_RAIN_DELAY,
    CONF_COLLECTED_48H_THRESHOLD,
    CONF_DELAY_DAYS,
    CONF_FORECAST_POP_THRESHOLD,
    CONF_FORECAST_RAIN_48H_SENSOR,
    CONF_FORECAST_RAIN_SENSOR,
    CONF_HEAVY_DELAY_DAYS,
    CONF_HEAVY_RAIN_THRESHOLD,
    CONF_RAIN_48H_SENSOR,
    CONF_RAIN_SENSOR,
    CONF_RAIN_THRESHOLD,
    CONF_SOURCE_NAME,
    CONF_STOP_ACTIVE_WATERING,
    CONF_TEMP_SENSOR,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_PUSH_ENABLED,
    DOMAIN,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

async def test_flow_user_init(hass: HomeAssistant) -> None:
    """Test user setup flow initiates correctly."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

async def test_flow_user_success(hass: HomeAssistant) -> None:
    """Test successful configuration setup flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    
    with patch(
        "custom_components.intellidwell.config_flow.IntelliDwellClient.get_status",
        return_value={"relay_states": [0] * 10},
    ), patch(
        "custom_components.intellidwell.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "1.1.1.1"},
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["title"] == "IntelliDwell Sprinkler (1.1.1.1)"
    assert result2["data"] == {CONF_HOST: "1.1.1.1"}
    assert len(mock_setup_entry.mock_calls) == 1

async def test_flow_user_cannot_connect(hass: HomeAssistant) -> None:
    """Test connection error handling during configuration."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.intellidwell.config_flow.IntelliDwellClient.get_status",
        side_effect=IntelliDwellConnectionError,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "1.1.1.1"},
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}

async def test_flow_user_duplicate(hass: HomeAssistant) -> None:
    """Test duplicate host setup aborts."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.1.1.1"},
        entry_id="mock_entry",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "1.1.1.1"},
    )
    await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.ABORT
    assert result2["reason"] == "already_configured"

async def test_flow_user_unknown_error(hass: HomeAssistant) -> None:
    """Test unexpected exception handling during configuration."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.intellidwell.config_flow.IntelliDwellClient.get_status",
        side_effect=Exception("Generic error"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "1.1.1.1"},
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.FORM
    assert result2["errors"] == {"base": "unknown"}


async def test_options_flow_weather_config(hass: HomeAssistant) -> None:
    """Test opening and saving the weather push & rain-delay options flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.1.1.1"},
        options={},
        entry_id="mock_options_entry",
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
    assert result["step_id"] == "init"

    with patch(
        "custom_components.intellidwell.coordinator.IntelliDwellCoordinator.async_request_refresh"
    ):
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_WEATHER_PUSH_ENABLED: True,
                CONF_RAIN_SENSOR: "sensor.ambient_daily_rain",
                CONF_RAIN_48H_SENSOR: "sensor.ambient_48h_rain",
                CONF_TEMP_SENSOR: "sensor.outdoor_temperature",
                CONF_WEATHER_ENTITY: "weather.morgan_weather",
                CONF_FORECAST_RAIN_SENSOR: "sensor.qpf_24h",
                CONF_FORECAST_RAIN_48H_SENSOR: "sensor.qpf_48h",
                CONF_SOURCE_NAME: "Ambient PWS",
                CONF_AUTO_RAIN_DELAY: True,
                CONF_RAIN_THRESHOLD: 0.25,
                CONF_COLLECTED_48H_THRESHOLD: 0.50,
                CONF_ANTICIPATED_24H_THRESHOLD: 0.15,
                CONF_ANTICIPATED_48H_THRESHOLD: 0.30,
                CONF_DELAY_DAYS: 2,
                CONF_HEAVY_RAIN_THRESHOLD: 0.60,
                CONF_HEAVY_DELAY_DAYS: 4,
                CONF_FORECAST_POP_THRESHOLD: 75,
                CONF_STOP_ACTIVE_WATERING: True,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_RAIN_SENSOR] == "sensor.ambient_daily_rain"
    assert entry.options[CONF_RAIN_48H_SENSOR] == "sensor.ambient_48h_rain"
    assert entry.options[CONF_TEMP_SENSOR] == "sensor.outdoor_temperature"
    assert entry.options[CONF_WEATHER_ENTITY] == "weather.morgan_weather"
    assert entry.options[CONF_FORECAST_RAIN_SENSOR] == "sensor.qpf_24h"
    assert entry.options[CONF_FORECAST_RAIN_48H_SENSOR] == "sensor.qpf_48h"
    assert entry.options[CONF_ANTICIPATED_24H_THRESHOLD] == 0.15
    assert entry.options[CONF_ANTICIPATED_48H_THRESHOLD] == 0.30
    assert entry.options[CONF_SOURCE_NAME] == "Ambient PWS"
    assert entry.options[CONF_HEAVY_DELAY_DAYS] == 4

    # Clearing optional entity/text fields normalizes them to empty string
    result3 = await hass.config_entries.options.async_init(entry.entry_id)
    with patch(
        "custom_components.intellidwell.coordinator.IntelliDwellCoordinator.async_request_refresh"
    ):
        result4 = await hass.config_entries.options.async_configure(
            result3["flow_id"],
            user_input={
                CONF_WEATHER_PUSH_ENABLED: True,
                CONF_RAIN_SENSOR: "sensor.ambient_daily_rain",
                CONF_AUTO_RAIN_DELAY: False,
            },
        )
        await hass.async_block_till_done()

    assert result4["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_RAIN_48H_SENSOR] == ""
    assert entry.options[CONF_TEMP_SENSOR] == ""
    assert entry.options[CONF_WEATHER_ENTITY] == ""
    assert entry.options[CONF_FORECAST_RAIN_SENSOR] == ""
    assert entry.options[CONF_FORECAST_RAIN_48H_SENSOR] == ""
    assert entry.options[CONF_SOURCE_NAME] == ""
    assert entry.options[CONF_AUTO_RAIN_DELAY] is False


async def test_anticipated_precipitation_delay_evaluation(hass: HomeAssistant) -> None:
    """Test coordinator calculates standard/heavy rain delays from anticipated QPF."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.1.1.1"},
        options={
            CONF_WEATHER_PUSH_ENABLED: True,
            CONF_RAIN_SENSOR: "sensor.daily_rain",
            CONF_WEATHER_ENTITY: "weather.morgan_weather",
            CONF_AUTO_RAIN_DELAY: True,
            CONF_RAIN_THRESHOLD: 0.25,
            CONF_COLLECTED_48H_THRESHOLD: 0.50,
            CONF_ANTICIPATED_24H_THRESHOLD: 0.15,
            CONF_ANTICIPATED_48H_THRESHOLD: 0.30,
            CONF_HEAVY_RAIN_THRESHOLD: 0.50,
            CONF_DELAY_DAYS: 2,
            CONF_HEAVY_DELAY_DAYS: 3,
            CONF_FORECAST_POP_THRESHOLD: 60,
        },
        entry_id="mock_anticipated_entry",
    )
    entry.add_to_hass(hass)

    hass.states.async_set("sensor.daily_rain", "0.10", {"friendly_name": "Backyard Rain"})
    hass.states.async_set(
        "weather.morgan_weather",
        "rainy",
        {
            "temperature": 54,
            "precipitation_unit": "in",
            "forecast": [
                {"precipitation": 0.20, "precipitation_probability": 40},
                {"precipitation": 0.05, "precipitation_probability": 20},
            ],
        },
    )

    with patch(
        "custom_components.intellidwell.IntelliDwellClient.get_status",
        return_value={"relay_states": [0] * 10, "timers": {}, "queue": {}},
    ), patch(
        "custom_components.intellidwell._safe_client_request",
        return_value={"status": "ok"},
    ) as mock_req, patch(
        "homeassistant.components.http.HomeAssistantHTTP.async_register_static_paths"
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        weather_calls = [c for c in mock_req.call_args_list if "api/weather" in c.args]
        assert weather_calls, "Expected initial automatic push to api/weather"
        assert weather_calls[-1].kwargs["json"]["delay_days"] == 2

        # Heavy combined 24h (0.10 collected + 0.45 anticipated = 0.55 >= 0.50) triggers heavy delay (3d)
        hass.states.async_set(
            "weather.morgan_weather",
            "pouring",
            {
                "temperature": 50,
                "precipitation_unit": "in",
                "forecast": [
                    {"precipitation": 0.45, "precipitation_probability": 85},
                    {"precipitation": 0.10, "precipitation_probability": 30},
                ],
            },
        )
        await hass.async_block_till_done()

        weather_calls = [c for c in mock_req.call_args_list if "api/weather" in c.args]
        assert weather_calls[-1].kwargs["json"]["delay_days"] == 3

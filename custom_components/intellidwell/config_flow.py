"""Config flow for IntelliDwell Sprinkler Controller integration."""
import logging
from typing import Any

import voluptuous as vol

import voluptuous as vol
from pyintellidwell import IntelliDwellClient, IntelliDwellConnectionError, IntelliDwellInvalidResponseError

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ANTICIPATED_24H_THRESHOLD,
    CONF_ANTICIPATED_48H_THRESHOLD,
    CONF_AUTO_RAIN_DELAY,
    CONF_COLLECTED_48H_THRESHOLD,
    CONF_DELAY_DAYS,
    CONF_FORECAST_POP_THRESHOLD,
    CONF_FORECAST_RAIN_48H_SENSOR,
    CONF_FORECAST_RAIN_SENSOR,
    CONF_FREEZE_SKIP_ENABLED,
    CONF_FREEZE_TEMP_THRESHOLD,
    CONF_HEAT_WAVE_BOOST_PCT,
    CONF_HEAT_WAVE_ENABLED,
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
    CONF_WIND_SENSOR,
    CONF_WIND_SKIP_ENABLED,
    CONF_WIND_SKIP_THRESHOLD,
    DEFAULT_ANTICIPATED_24H_THRESHOLD,
    DEFAULT_ANTICIPATED_48H_THRESHOLD,
    DEFAULT_AUTO_RAIN_DELAY,
    DEFAULT_COLLECTED_48H_THRESHOLD,
    DEFAULT_DELAY_DAYS,
    DEFAULT_FORECAST_POP_THRESHOLD,
    DEFAULT_FREEZE_SKIP_ENABLED,
    DEFAULT_FREEZE_TEMP_THRESHOLD,
    DEFAULT_HEAT_WAVE_BOOST_PCT,
    DEFAULT_HEAT_WAVE_ENABLED,
    DEFAULT_HEAT_WAVE_TEMP_THRESHOLD,
    DEFAULT_HEAVY_DELAY_DAYS,
    DEFAULT_HEAVY_RAIN_THRESHOLD,
    DEFAULT_RAIN_THRESHOLD,
    DEFAULT_SOIL_MOISTURE_MAX_PCT,
    DEFAULT_STOP_ACTIVE_WATERING,
    DEFAULT_WEATHER_PUSH_ENABLED,
    DEFAULT_WIND_SKIP_ENABLED,
    DEFAULT_WIND_SKIP_THRESHOLD,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
    }
)

async def validate_input(client: IntelliDwellClient) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    try:
        await client.get_status()
    except (IntelliDwellConnectionError, IntelliDwellInvalidResponseError) as err:
        raise CannotConnect from err
    return {"title": f"IntelliDwell Sprinkler ({client.host})"}

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IntelliDwell Sprinkler Controller."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            self._async_abort_entries_match({CONF_HOST: host})
            
            try:
                session = async_get_clientsession(self.hass)
                client = IntelliDwellClient(host, session=session)
                info = await validate_input(client)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler for this integration."""
        return IntelliDwellOptionsFlowHandler(config_entry)


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(
            CONF_WEATHER_PUSH_ENABLED, default=DEFAULT_WEATHER_PUSH_ENABLED
        ): selector.BooleanSelector(),
        vol.Optional(CONF_RAIN_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_RAIN_48H_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_TEMP_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_WEATHER_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="weather")
        ),
        vol.Optional(CONF_FORECAST_RAIN_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_FORECAST_RAIN_48H_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_SOURCE_NAME): selector.TextSelector(),
        vol.Optional(
            CONF_AUTO_RAIN_DELAY, default=DEFAULT_AUTO_RAIN_DELAY
        ): selector.BooleanSelector(),
        vol.Optional(
            CONF_RAIN_THRESHOLD, default=DEFAULT_RAIN_THRESHOLD
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.01,
                max=5.0,
                step=0.01,
                unit_of_measurement="in",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_COLLECTED_48H_THRESHOLD, default=DEFAULT_COLLECTED_48H_THRESHOLD
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.01,
                max=10.0,
                step=0.05,
                unit_of_measurement="in",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_ANTICIPATED_24H_THRESHOLD, default=DEFAULT_ANTICIPATED_24H_THRESHOLD
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.01,
                max=5.0,
                step=0.05,
                unit_of_measurement="in",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_ANTICIPATED_48H_THRESHOLD, default=DEFAULT_ANTICIPATED_48H_THRESHOLD
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.01,
                max=10.0,
                step=0.05,
                unit_of_measurement="in",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_DELAY_DAYS, default=DEFAULT_DELAY_DAYS
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=5,
                step=1,
                unit_of_measurement="days",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_HEAVY_RAIN_THRESHOLD, default=DEFAULT_HEAVY_RAIN_THRESHOLD
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.05,
                max=10.0,
                step=0.05,
                unit_of_measurement="in",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_HEAVY_DELAY_DAYS, default=DEFAULT_HEAVY_DELAY_DAYS
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=5,
                step=1,
                unit_of_measurement="days",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_FORECAST_POP_THRESHOLD, default=DEFAULT_FORECAST_POP_THRESHOLD
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=10,
                max=100,
                step=5,
                unit_of_measurement="%",
                mode=selector.NumberSelectorMode.SLIDER,
            )
        ),
        vol.Optional(
            CONF_STOP_ACTIVE_WATERING, default=DEFAULT_STOP_ACTIVE_WATERING
        ): selector.BooleanSelector(),
        vol.Optional(CONF_SOIL_MOISTURE_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_WIND_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(
            CONF_SOIL_MOISTURE_MAX_PCT, default=DEFAULT_SOIL_MOISTURE_MAX_PCT
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=10,
                max=95,
                step=1,
                unit_of_measurement="%",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_HEAT_WAVE_ENABLED, default=DEFAULT_HEAT_WAVE_ENABLED
        ): selector.BooleanSelector(),
        vol.Optional(
            CONF_HEAT_WAVE_TEMP_THRESHOLD, default=DEFAULT_HEAT_WAVE_TEMP_THRESHOLD
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=70,
                max=120,
                step=1,
                unit_of_measurement="°F",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_HEAT_WAVE_BOOST_PCT, default=DEFAULT_HEAT_WAVE_BOOST_PCT
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=5,
                max=60,
                step=5,
                unit_of_measurement="%",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_FREEZE_SKIP_ENABLED, default=DEFAULT_FREEZE_SKIP_ENABLED
        ): selector.BooleanSelector(),
        vol.Optional(
            CONF_FREEZE_TEMP_THRESHOLD, default=DEFAULT_FREEZE_TEMP_THRESHOLD
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=20,
                max=45,
                step=1,
                unit_of_measurement="°F",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_WIND_SKIP_ENABLED, default=DEFAULT_WIND_SKIP_ENABLED
        ): selector.BooleanSelector(),
        vol.Optional(
            CONF_WIND_SKIP_THRESHOLD, default=DEFAULT_WIND_SKIP_THRESHOLD
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=5,
                max=60,
                step=1,
                unit_of_measurement="mph",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
    }
)


class IntelliDwellOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for IntelliDwell weather push & rain delay."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage weather push entities and automatic rain-delay thresholds."""
        if user_input is not None:
            cleaned = dict(user_input)
            for key in (
                CONF_RAIN_SENSOR,
                CONF_RAIN_48H_SENSOR,
                CONF_TEMP_SENSOR,
                CONF_WEATHER_ENTITY,
                CONF_FORECAST_RAIN_SENSOR,
                CONF_FORECAST_RAIN_48H_SENSOR,
                CONF_SOIL_MOISTURE_SENSOR,
                CONF_WIND_SENSOR,
                CONF_SOURCE_NAME,
            ):
                val = cleaned.get(key)
                cleaned[key] = str(val).strip() if val else ""
            return self.async_create_entry(title="", data=cleaned)

        suggested = {
            k: v
            for k, v in self._entry.options.items()
            if not (isinstance(v, str) and not v.strip())
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, suggested),
        )

class CannotConnect(Exception):
    """Error to indicate we cannot connect."""

"""DataUpdateCoordinator for IntelliDwell Sprinkler Controller."""

import asyncio
from datetime import timedelta
import logging
from typing import Any, override

from pyintellidwell import (
    IntelliDwellClient,
    IntelliDwellConnectionError,
    IntelliDwellInvalidResponseError,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)


class IntelliDwellCoordinator(DataUpdateCoordinator[dict]):
    """Class to manage fetching IntelliDwell Sprinkler Controller data."""

    def __init__(
        self, hass: HomeAssistant, client: IntelliDwellClient, entry: ConfigEntry
    ) -> None:
        """Initialize."""
        self.client = client
        self._cached_settings: dict[str, Any] = {}
        self._cached_schedules: list[Any] = []
        self._cached_rain_delay: int = 0
        self._schedules_dirty: bool = True
        self._rain_delay_dirty: bool = True
        self._settings_dirty: bool = True
        self._rain_delay_poll_counter: int = 0
        self._settings_poll_counter: int = 0

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"IntelliDwell Sprinkler Coordinator ({client.host})",
            update_interval=timedelta(seconds=10),
        )

    def mark_schedules_dirty(self) -> None:
        """Mark schedules as needing a fresh fetch."""
        self._schedules_dirty = True

    def mark_rain_delay_dirty(self) -> None:
        """Mark rain delay as needing a fresh fetch."""
        self._rain_delay_dirty = True

    def mark_settings_dirty(self) -> None:
        """Mark settings as needing a fresh fetch."""
        self._settings_dirty = True

    async def _get_rain_delay(self) -> dict[str, Any]:
        if hasattr(self.client, "get_rain_delay"):
            return await self.client.get_rain_delay()
        try:
            res = await self.client._request("GET", "get-rain-delay")
            return res if isinstance(res, dict) else {"days_remaining": 0}
        except Exception as e:
            _LOGGER.debug("Error fetching rain delay: %s", e)
            return {"days_remaining": 0}

    async def _get_schedules(self) -> list[Any]:
        if hasattr(self.client, "get_schedules"):
            return await self.client.get_schedules()
        try:
            res = await self.client._request("GET", "get-schedules")
            return res if isinstance(res, list) else []
        except Exception as e:
            _LOGGER.debug("Error fetching schedules: %s", e)
            return []

    async def _get_settings_raw(self) -> dict[str, Any]:
        """Fetch raw settings from the controller."""
        try:
            res = await self.client._request("GET", "get-settings")
            if isinstance(res, dict):
                return res
        except Exception as e:
            _LOGGER.debug("Error fetching settings: %s", e)
        return {}

    @override
    async def _async_update_data(self) -> dict:
        """Fetch status, and conditionally rain delay, schedules, and settings sequentially."""
        try:
            status_data = await self.client.get_status()
        except (IntelliDwellConnectionError, IntelliDwellInvalidResponseError) as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error communicating with API: {err}") from err

        # Rain delay refresh (every ~60s or immediately if marked dirty)
        if self._rain_delay_dirty or self._rain_delay_poll_counter <= 0:
            rain_delay_res = await self._get_rain_delay()
            self._cached_rain_delay = (
                rain_delay_res.get("days_remaining", 0)
                if isinstance(rain_delay_res, dict)
                else 0
            )
            self._rain_delay_dirty = False
            self._rain_delay_poll_counter = 6  # 6 x 10s = 60s
        else:
            self._rain_delay_poll_counter -= 1

        # Schedules refresh (only on startup or after explicit schedule modifications)
        if self._schedules_dirty or not self._cached_schedules:
            sched_res = await self._get_schedules()
            if sched_res:
                self._cached_schedules = sched_res
            self._schedules_dirty = False

        # Settings refresh (every ~30 mins or immediately if marked dirty)
        if self._settings_dirty or not self._cached_settings or self._settings_poll_counter <= 0:
            sett_res = await self._get_settings_raw()
            if sett_res:
                self._cached_settings = sett_res
            self._settings_dirty = False
            self._settings_poll_counter = 180  # 180 x 10s = 30 mins
        else:
            self._settings_poll_counter -= 1

        status_data["rain_delay"] = self._cached_rain_delay
        status_data["schedules"] = self._cached_schedules
        status_data["settings"] = self._cached_settings
        return status_data

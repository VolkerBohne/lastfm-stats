"""Data update coordinator for Last.fm Stats."""

from __future__ import annotations

from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_API_KEY, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from lastfm_stats import LastFmClient, LastFmError, MonthCache, YearStats, collect_year_stats

from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ERROR_INVALID_API_KEY,
    LOGGER,
    STORAGE_VERSION,
)

if TYPE_CHECKING:
    from . import LastfmStatsConfigEntry


def month_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    """Return the store holding settled monthly counts in <config>/.storage."""
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")


class LastfmStatsCoordinator(DataUpdateCoordinator[YearStats]):
    """Fetches this year's scrobbles per month for one Last.fm user."""

    config_entry: LastfmStatsConfigEntry

    def __init__(self, hass: HomeAssistant, entry: LastfmStatsConfigEntry) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_USERNAME]}",
            update_interval=timedelta(minutes=interval),
        )
        self._client = LastFmClient(entry.data[CONF_API_KEY], entry.data[CONF_USERNAME])
        self._store = month_store(hass, entry.entry_id)
        self._months: dict[str, int] = {}

    async def async_load_cache(self) -> None:
        """Load cached monthly counts; a missing store means an empty cache."""
        data = await self._store.async_load()
        self._months = MonthCache.from_months((data or {}).get("months")).as_dict()

    async def _async_update_data(self) -> YearStats:
        now = dt_util.utcnow()
        cache = MonthCache.from_months(self._months)
        try:
            # requests blocks, so the Last.fm calls run in the executor.
            stats = await self.hass.async_add_executor_job(
                partial(collect_year_stats, self._client, now.year, cache=cache, now=now)
            )
        except LastFmError as err:
            if err.code == ERROR_INVALID_API_KEY:
                raise ConfigEntryAuthFailed(str(err)) from err
            raise UpdateFailed(str(err)) from err

        if cache.dirty:
            self._months = cache.as_dict()
            await self._store.async_save({"months": self._months})
        return stats

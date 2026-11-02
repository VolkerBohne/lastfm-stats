"""The Last.fm Stats integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import LastfmStatsCoordinator, month_store

PLATFORMS = [Platform.SENSOR]

type LastfmStatsConfigEntry = ConfigEntry[LastfmStatsCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: LastfmStatsConfigEntry) -> bool:
    """Set up Last.fm Stats from a config entry."""
    coordinator = LastfmStatsCoordinator(hass, entry)
    await coordinator.async_load_cache()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LastfmStatsConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: LastfmStatsConfigEntry) -> None:
    """Delete the cached monthly counts when the integration is removed."""
    await month_store(hass, entry.entry_id).async_remove()


async def _async_update_listener(
    hass: HomeAssistant, entry: LastfmStatsConfigEntry
) -> None:
    """Reload so a changed update interval takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)

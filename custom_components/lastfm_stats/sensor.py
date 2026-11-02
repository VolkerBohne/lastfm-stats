"""Sensors for Last.fm Stats."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from lastfm_stats.stats import month_names

from . import LastfmStatsConfigEntry
from .const import DOMAIN
from .coordinator import LastfmStatsCoordinator

UNIT = "scrobbles"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LastfmStatsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[LastfmStatsSensor] = [
        YearScrobblesSensor(coordinator),
        TotalScrobblesSensor(coordinator),
    ]
    entities.extend(MonthScrobblesSensor(coordinator, month) for month in range(1, 13))
    async_add_entities(entities)


class LastfmStatsSensor(CoordinatorEntity[LastfmStatsCoordinator], SensorEntity):
    """Base class: one device per Last.fm user."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UNIT
    _attr_icon = "mdi:music-note"

    def __init__(self, coordinator: LastfmStatsCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        username = entry.data[CONF_USERNAME]
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        # Entity IDs would otherwise follow the translated name and differ per
        # UI language; fixed IDs keep dashboard examples valid everywhere.
        self.entity_id = f"sensor.lastfm_{slugify(username)}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Last.fm {username}",
            manufacturer="Last.fm",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=f"https://www.last.fm/user/{username}",
        )


class YearScrobblesSensor(LastfmStatsSensor):
    """Scrobbles in the current calendar year (UTC), months as attribute."""

    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: LastfmStatsCoordinator) -> None:
        super().__init__(coordinator, "year_scrobbles")

    @property
    def native_value(self) -> int:
        return self.coordinator.data.year_plays

    @property
    def last_reset(self) -> datetime:
        return datetime(self.coordinator.data.year, 1, 1, tzinfo=timezone.utc)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stats = self.coordinator.data
        return {"year": stats.year, "months": month_names(stats.months)}


class TotalScrobblesSensor(LastfmStatsSensor):
    """All-time scrobbles."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: LastfmStatsCoordinator) -> None:
        super().__init__(coordinator, "total_scrobbles")

    @property
    def native_value(self) -> int:
        return self.coordinator.data.total_plays


class MonthScrobblesSensor(LastfmStatsSensor):
    """Scrobbles in one month of the current year; future months are 0."""

    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: LastfmStatsCoordinator, month: int) -> None:
        super().__init__(coordinator, f"month_{month:02d}")
        self._month = month

    @property
    def native_value(self) -> int:
        return self.coordinator.data.months[self._month]

    @property
    def last_reset(self) -> datetime:
        return datetime(self.coordinator.data.year, self._month, 1, tzinfo=timezone.utc)

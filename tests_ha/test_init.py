from datetime import datetime, timedelta, timezone

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.lastfm_stats.const import DOMAIN, STORAGE_VERSION
from lastfm_stats import LastFmError

from .conftest import NOW


def utc(year, month, day=15):
    return datetime(year, month, day, 12, tzinfo=timezone.utc)


def storage_key(entry):
    return f"{DOMAIN}.{entry.entry_id}"


async def setup(hass, entry):
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_first_update_fills_store_with_settled_months(
    hass, hass_storage, freezer, lastfm, config_entry
):
    freezer.move_to(NOW)
    lastfm.add(utc(2026, 1, 5), utc(2026, 9, 3), utc(2026, 10, 3))

    await setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    # user.getInfo plus one request for each month up to November.
    assert lastfm.requests == ["user.getInfo"] + ["count"] * 11
    months = hass_storage[storage_key(config_entry)]["data"]["months"]
    assert sorted(months) == [f"2026-{month:02d}" for month in range(1, 10)]
    assert months["2026-01"] == 1 and months["2026-09"] == 1


async def test_update_with_filled_store_costs_three_requests(
    hass, hass_storage, freezer, lastfm, config_entry
):
    freezer.move_to(NOW)
    hass_storage[storage_key(config_entry)] = {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": storage_key(config_entry),
        "data": {"months": {f"2026-{month:02d}": 7 for month in range(1, 10)}},
    }
    lastfm.add(utc(2026, 10, 20), utc(2026, 11, 1))

    await setup(hass, config_entry)

    assert lastfm.requests == ["user.getInfo", "count", "count"]
    assert config_entry.runtime_data.data.year_plays == 9 * 7 + 2

    lastfm.requests.clear()
    freezer.tick(timedelta(minutes=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert lastfm.requests == ["user.getInfo", "count", "count"]


async def test_second_update_reuses_cache_written_by_first(
    hass, hass_storage, freezer, lastfm, config_entry
):
    freezer.move_to(NOW)
    await setup(hass, config_entry)

    lastfm.requests.clear()
    await config_entry.runtime_data.async_refresh()

    assert lastfm.requests == ["user.getInfo", "count", "count"]


async def test_invalid_api_key_starts_reauth(hass, freezer, lastfm, config_entry):
    freezer.move_to(NOW)
    lastfm.error = LastFmError("Last.fm error 10: Invalid API key", 10)

    await setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


async def test_other_errors_retry_setup(hass, freezer, lastfm, config_entry):
    freezer.move_to(NOW)
    lastfm.error = LastFmError("Last.fm request failed with HTTP 503")

    await setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_and_remove_deletes_store(
    hass, hass_storage, freezer, lastfm, config_entry
):
    freezer.move_to(NOW)
    await setup(hass, config_entry)
    assert storage_key(config_entry) in hass_storage

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED

    await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()

    assert storage_key(config_entry) not in hass_storage


async def test_options_change_reloads_with_new_interval(
    hass, freezer, lastfm, config_entry
):
    freezer.move_to(NOW)
    await setup(hass, config_entry)
    assert config_entry.runtime_data.update_interval == timedelta(minutes=60)

    hass.config_entries.async_update_entry(config_entry, options={"scan_interval": 30})
    await hass.async_block_till_done()

    assert config_entry.runtime_data.update_interval == timedelta(minutes=30)

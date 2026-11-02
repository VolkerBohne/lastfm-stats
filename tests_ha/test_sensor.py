from datetime import datetime, timezone

from homeassistant.helpers import entity_registry as er

from .conftest import NOW


def utc(year, month, day=15):
    return datetime(year, month, day, 12, tzinfo=timezone.utc)


async def setup(hass, entry):
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_sensor_states_and_attributes(hass, freezer, lastfm, config_entry):
    freezer.move_to(NOW)
    lastfm.add(utc(2026, 1, 5), utc(2026, 1, 6), utc(2026, 3, 1), utc(2026, 11, 1))

    await setup(hass, config_entry)

    year = hass.states.get("sensor.lastfm_rj_year_scrobbles")
    assert year.state == "4"
    assert year.attributes["unit_of_measurement"] == "scrobbles"
    assert year.attributes["state_class"] == "total"
    assert year.attributes["year"] == 2026
    assert year.attributes["months"] == {
        "January": 2,
        "February": 0,
        "March": 1,
        "April": 0,
        "May": 0,
        "June": 0,
        "July": 0,
        "August": 0,
        "September": 0,
        "October": 0,
        "November": 1,
        "December": 0,
    }
    assert year.attributes["last_reset"] == "2026-01-01T00:00:00+00:00"

    total = hass.states.get("sensor.lastfm_rj_total_scrobbles")
    assert total.state == "75970"
    assert total.attributes["state_class"] == "total_increasing"

    assert hass.states.get("sensor.lastfm_rj_month_01").state == "2"
    assert hass.states.get("sensor.lastfm_rj_month_11").state == "1"
    december = hass.states.get("sensor.lastfm_rj_month_12")
    assert december.state == "0"
    assert december.attributes["last_reset"] == "2026-12-01T00:00:00+00:00"


async def test_entities_belong_to_one_device(hass, freezer, lastfm, config_entry):
    freezer.move_to(NOW)
    await setup(hass, config_entry)

    entries = er.async_entries_for_config_entry(er.async_get(hass), config_entry.entry_id)

    assert len(entries) == 14
    assert len({entry.device_id for entry in entries}) == 1
    assert {entry.unique_id for entry in entries} >= {
        f"{config_entry.entry_id}_year_scrobbles",
        f"{config_entry.entry_id}_total_scrobbles",
        f"{config_entry.entry_id}_month_01",
        f"{config_entry.entry_id}_month_12",
    }


async def test_entity_ids_do_not_depend_on_language(hass, freezer, lastfm, config_entry):
    freezer.move_to(NOW)
    await hass.config.async_update(language="de")

    await setup(hass, config_entry)

    state = hass.states.get("sensor.lastfm_rj_year_scrobbles")
    assert state.name == "Last.fm RJ Scrobbles dieses Jahr"
    assert hass.states.get("sensor.lastfm_rj_month_03").name == "Last.fm RJ Scrobbles März"

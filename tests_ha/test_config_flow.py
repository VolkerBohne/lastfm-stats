import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.lastfm_stats.const import DOMAIN
from lastfm_stats import LastFmError

from .conftest import API_KEY


async def test_user_flow_creates_entry(hass, lastfm):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": " rj ", "api_key": f" {API_KEY} "}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Last.fm RJ"
    assert result["data"] == {"username": "RJ", "api_key": API_KEY}
    assert result["result"].unique_id == "rj"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (LastFmError("Last.fm error 10: Invalid API key", 10), "invalid_auth"),
        (LastFmError("Last.fm error 6: User not found", 6), "user_not_found"),
        (LastFmError("Network error talking to Last.fm: boom"), "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_user_flow_errors(hass, lastfm, error, expected):
    lastfm.error = error
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "rj", "api_key": API_KEY}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}

    lastfm.error = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "rj", "api_key": API_KEY}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_aborts_for_configured_user(hass, lastfm, config_entry):
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "rJ", "api_key": API_KEY}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_api_key(hass, lastfm, config_entry):
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    lastfm.error = LastFmError("Last.fm error 10: Invalid API key", 10)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": "bad"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    lastfm.error = None
    new_key = "f" * 32
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": new_key}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data["api_key"] == new_key


async def test_options_flow_sets_scan_interval(hass, lastfm, config_entry):
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 30}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {"scan_interval": 30}


async def test_options_flow_rejects_too_short_interval(hass, lastfm, config_entry):
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    with pytest.raises(vol.Invalid):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {"scan_interval": 5}
        )

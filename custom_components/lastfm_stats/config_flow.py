"""Config flow for Last.fm Stats."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback

from lastfm_stats import LastFmClient, LastFmError

from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ERROR_INVALID_API_KEY,
    ERROR_USER_NOT_FOUND,
    LOGGER,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_API_KEY): str,
    }
)
REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): str})


async def _validate(
    hass: HomeAssistant, username: str, api_key: str
) -> tuple[dict[str, Any] | None, str | None]:
    """Check the credentials; return the user info or an error key."""
    client = LastFmClient(api_key, username)
    try:
        info = await hass.async_add_executor_job(client.get_user_info)
    except LastFmError as err:
        if err.code == ERROR_INVALID_API_KEY:
            return None, "invalid_auth"
        if err.code == ERROR_USER_NOT_FOUND:
            return None, "user_not_found"
        return None, "cannot_connect"
    except Exception:  # noqa: BLE001
        LOGGER.exception("Unexpected error while validating Last.fm credentials")
        return None, "unknown"
    return info, None


class LastfmStatsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Last.fm Stats."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            api_key = user_input[CONF_API_KEY].strip()
            info, error = await _validate(self.hass, username, api_key)
            if error:
                errors["base"] = error
            else:
                # Last.fm usernames are case-insensitive.
                await self.async_set_unique_id(info["username"].lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Last.fm {info['username']}",
                    data={CONF_USERNAME: info["username"], CONF_API_KEY: api_key},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            _, error = await _validate(self.hass, entry.data[CONF_USERNAME], api_key)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: api_key}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> LastfmStatsOptionsFlow:
        return LastfmStatsOptionsFlow()


class LastfmStatsOptionsFlow(OptionsFlow):
    """Change the update interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

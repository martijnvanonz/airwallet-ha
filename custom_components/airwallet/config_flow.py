"""Config flow: phone number + PIN, then the laundry room."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AirwalletAuthError, AirwalletClient, AirwalletError
from .const import CONF_LOCATION_ID, CONF_PHONE, CONF_PIN, CONF_REFRESH_TOKEN, DOMAIN

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PHONE): str,
        vol.Required(CONF_PIN): str,
        vol.Optional(CONF_LOCATION_ID): str,
    }
)


class AirwalletConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, phone: str, pin: str, location_id: str | None) -> tuple[dict[str, Any], str]:
        """Log in and resolve the laundry room. Returns (entry data, location name)."""
        client = AirwalletClient(async_get_clientsession(self.hass), phone, pin)
        await client.login()
        location_id = location_id or await client.get_favorite_location_id()
        if not location_id:
            raise NoLocation
        location = await client.get_location(location_id)
        data = {
            CONF_PHONE: phone,
            CONF_PIN: pin,
            CONF_LOCATION_ID: location_id,
            CONF_REFRESH_TOKEN: client.refresh_token,
        }
        return data, location.name

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data, name = await self._validate(
                    user_input[CONF_PHONE].strip(), user_input[CONF_PIN].strip(), user_input.get(CONF_LOCATION_ID)
                )
            except AirwalletAuthError:
                errors["base"] = "invalid_auth"
            except NoLocation:
                errors["base"] = "no_location"
            except (AirwalletError, aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(data[CONF_LOCATION_ID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=name, data=data)
        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                data, _ = await self._validate(entry.data[CONF_PHONE], user_input[CONF_PIN].strip(), entry.data[CONF_LOCATION_ID])
            except AirwalletAuthError:
                errors["base"] = "invalid_auth"
            except (AirwalletError, aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_PIN): str}), errors=errors
        )


class NoLocation(Exception):
    """The account has no favorite laundry room and none was given."""

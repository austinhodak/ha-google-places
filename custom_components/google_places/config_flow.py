"""Config flow for Google Places integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_API_KEY, CONF_PLACE_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLACES_API_URL = "https://places.googleapis.com/v1/places/{place_id}"

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)

    headers = {
        "X-Goog-Api-Key": data[CONF_API_KEY],
        "X-Goog-FieldMask": "name"
    }
    url = PLACES_API_URL.format(place_id=data[CONF_PLACE_ID])

    try:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                raise InvalidAuth
            place_data = await response.json()

        # Check if the response contains a name (basic validation)
        if "name" not in place_data:
            raise CannotConnect

        # Return info that you want to store in the config entry.
        return {"title": place_data["name"]}
    except aiohttp.ClientError:
        raise CannotConnect
    except KeyError:
        raise InvalidAuth

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Google Places."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                    vol.Required(CONF_PLACE_ID): str,
                }
            ),
            errors=errors,
        )

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""

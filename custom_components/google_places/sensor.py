"""Support for Google Places sensors."""

from __future__ import annotations

from datetime import timedelta
from datetime import time
import logging

import aiohttp
from aiohttp.client_exceptions import ClientError
import async_timeout

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import CONF_API_KEY, CONF_PLACE_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(days=1)
TIMEOUT = 10
PLACES_API_URL = "https://places.googleapis.com/v1/places/{place_id}"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Google Places sensor from a config entry."""
    api_key = config_entry.data[CONF_API_KEY]
    place_id = config_entry.data[CONF_PLACE_ID]

    coordinator = GooglePlacesDataUpdateCoordinator(hass, api_key, place_id)

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        raise
    except Exception as err:
        _LOGGER.error("Error setting up Google Places integration: %s", err)
        raise ConfigEntryNotReady from err

    async_add_entities([GooglePlacesSensor(coordinator)], True)


class GooglePlacesDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Google Places data."""

    def __init__(self, hass, api_key, place_id):
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.api_key = api_key
        self.place_id = place_id
        self.session = async_get_clientsession(hass)

    async def _async_update_data(self):
        """Fetch data from Google Places API."""
        try:
            async with async_timeout.timeout(10):
                headers = {
                    "X-Goog-Api-Key": self.api_key,
                    "X-Goog-FieldMask": "currentOpeningHours,regularOpeningHours",
                }
                url = PLACES_API_URL.format(place_id=self.place_id)
                response = await self.session.get(url, headers=headers)
                response.raise_for_status()
                data = await response.json()

            current_opening_hours = data.get("currentOpeningHours", {})
            regular_opening_hours = data.get("regularOpeningHours", {})

            return {
                "open_now": current_opening_hours.get("openNow"),
                "periods": regular_opening_hours.get("periods", []),
                "weekday_text": regular_opening_hours.get("weekdayDescriptions", []),
            }
        except (TimeoutError, ClientError) as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err


class GooglePlacesSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Google Places sensor."""

    def format_periods(self, periods):
        days = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        formatted_hours = {}

        for period in periods:
            open_day = days[period["open"]["day"] - 1]
            close_day = days[period["close"]["day"] - 1]

            open_time = time(period["open"]["hour"], period["open"]["minute"]).strftime(
                "%I:%M %p"
            )
            close_time = time(period["close"]["hour"], period["close"]["minute"]).strftime(
                "%I:%M %p"
            )

            if open_day == close_day:
                if open_day not in formatted_hours:
                    formatted_hours[open_day] = []
                formatted_hours[open_day].append(f"{open_time} - {close_time}")
            else:
                if open_day not in formatted_hours:
                    formatted_hours[open_day] = []
                if close_day not in formatted_hours:
                    formatted_hours[close_day] = []
                formatted_hours[open_day].append(f"{open_time} - 12:00 AM")
                formatted_hours[close_day].append(f"12:00 AM - {close_time}")

        return formatted_hours

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "Business Hours"
        self._attr_unique_id = f"{DOMAIN}_{coordinator.place_id}"

    @property
    def state(self):
        """Return the state of the sensor."""
        if self.coordinator.data.get("open_now") is True:
            return "Open"
        return "Closed"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        formatted_hours = self.format_periods(self.coordinator.data.get("periods", []))
        return {
            "hours": formatted_hours,
            "weekday_text": self.coordinator.data.get("weekday_text", []),
        }
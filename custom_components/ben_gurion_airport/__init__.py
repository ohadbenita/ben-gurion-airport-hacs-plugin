"""The Ben Gurion Airport integration."""

from __future__ import annotations

from datetime import date

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_DIRECTION,
    CONF_FLIGHT_CODE,
    CONF_FLIGHT_DATE,
    COORDINATOR_KEY,
    DOMAIN,
    DIRECTION_DEPARTURE_LABEL,
    SERVICE_TRACK_FLIGHT,
    SERVICE_UNTRACK_FLIGHT,
    TRACKED_FLIGHTS_KEY,
    tracked_flights_signal,
)
from .coordinator import BenGurionAirportDataUpdateCoordinator
from .tracking import TrackedFlightsStore

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Ben Gurion Airport integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ben Gurion Airport from a config entry."""
    tracked_flights = TrackedFlightsStore(hass, entry.entry_id)
    await tracked_flights.async_load()

    coordinator = BenGurionAirportDataUpdateCoordinator(hass, entry, tracked_flights)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        COORDINATOR_KEY: coordinator,
        TRACKED_FLIGHTS_KEY: tracked_flights,
    }

    await _async_register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_TRACK_FLIGHT)
            hass.services.async_remove(DOMAIN, SERVICE_UNTRACK_FLIGHT)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


TRACK_FLIGHT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_FLIGHT_CODE): cv.string,
        vol.Required(CONF_FLIGHT_DATE): cv.date,
        vol.Optional(CONF_DIRECTION, default=DIRECTION_DEPARTURE_LABEL): vol.In(
            ["departure", "arrival"]
        ),
        vol.Optional(CONF_NAME): cv.string,
    }
)

UNTRACK_FLIGHT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_FLIGHT_CODE): cv.string,
        vol.Required(CONF_FLIGHT_DATE): cv.date,
        vol.Optional(CONF_DIRECTION, default=DIRECTION_DEPARTURE_LABEL): vol.In(
            ["departure", "arrival"]
        ),
    }
)


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain services once."""
    if hass.services.has_service(DOMAIN, SERVICE_TRACK_FLIGHT):
        return

    async def async_handle_track_flight(call: ServiceCall) -> None:
        """Track a specific flight."""
        entry = _async_get_loaded_entry(hass)
        if entry is None:
            raise HomeAssistantError("Ben Gurion Airport is not configured")

        tracked_flights: TrackedFlightsStore = hass.data[DOMAIN][entry.entry_id][
            TRACKED_FLIGHTS_KEY
        ]
        definition = await tracked_flights.async_track_flight(
            flight_code=call.data[CONF_FLIGHT_CODE],
            flight_date=call.data[CONF_FLIGHT_DATE],
            direction=call.data[CONF_DIRECTION],
            name=call.data.get(CONF_NAME),
        )

        async_dispatcher_send(hass, tracked_flights_signal(entry.entry_id))
        coordinator: BenGurionAirportDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
            COORDINATOR_KEY
        ]
        await coordinator.async_request_refresh()

        if definition is None:
            raise HomeAssistantError("Failed to track flight")

    async def async_handle_untrack_flight(call: ServiceCall) -> None:
        """Stop tracking a specific flight."""
        entry = _async_get_loaded_entry(hass)
        if entry is None:
            raise HomeAssistantError("Ben Gurion Airport is not configured")

        tracked_flights: TrackedFlightsStore = hass.data[DOMAIN][entry.entry_id][
            TRACKED_FLIGHTS_KEY
        ]
        definition = await tracked_flights.async_untrack_flight(
            flight_code=call.data[CONF_FLIGHT_CODE],
            flight_date=call.data[CONF_FLIGHT_DATE],
            direction=call.data[CONF_DIRECTION],
        )
        if definition is None:
            flight_date = _normalize_service_date(call.data[CONF_FLIGHT_DATE])
            raise HomeAssistantError(
                f"Tracked flight not found for {call.data[CONF_FLIGHT_CODE]} on {flight_date}"
            )

        async_dispatcher_send(hass, tracked_flights_signal(entry.entry_id))
        coordinator: BenGurionAirportDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
            COORDINATOR_KEY
        ]
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_TRACK_FLIGHT,
        async_handle_track_flight,
        schema=TRACK_FLIGHT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UNTRACK_FLIGHT,
        async_handle_untrack_flight,
        schema=UNTRACK_FLIGHT_SCHEMA,
    )


def _async_get_loaded_entry(hass: HomeAssistant) -> ConfigEntry | None:
    """Return the loaded config entry for this integration."""
    if not hass.data.get(DOMAIN):
        return None

    entry_id = next(iter(hass.data[DOMAIN]))
    return hass.config_entries.async_get_entry(entry_id)


def _normalize_service_date(value: date | str) -> str:
    """Normalize a service-supplied date."""
    if isinstance(value, date):
        return value.isoformat()
    return str(value)

"""The Ben Gurion Airport integration."""

from __future__ import annotations

from datetime import date

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.core import ServiceCall
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .api import BenGurionAirportApiClient, BenGurionAirportApiError
from .const import (
    CONF_DIRECTION,
    CONF_FLIGHT_CODE,
    CONF_FLIGHT_DATE,
    CONF_INCLUDE_COMPLETED,
    CONF_QUERY,
    COORDINATOR_KEY,
    DOMAIN,
    DIRECTION_ARRIVAL,
    DIRECTION_ARRIVAL_LABEL,
    DIRECTION_DEPARTURE,
    DIRECTION_DEPARTURE_LABEL,
    SERVICE_SEARCH_FLIGHTS,
    SERVICE_TRACK_FLIGHT,
    SERVICE_UNTRACK_FLIGHT,
    TRACKED_FLIGHTS_KEY,
    tracked_flights_signal,
)
from .coordinator import BenGurionAirportDataUpdateCoordinator
from .tracking import TrackedFlightsStore

PLATFORMS: list[Platform] = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
IGNORED_SEARCH_TOKENS = {"FROM", "TO", "FLIGHT"}
LOCAL_AIRPORT_TOKENS = {"TLV", "BEN", "GURION", "BENGURION", "TELAVIV"}


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
            hass.services.async_remove(DOMAIN, SERVICE_SEARCH_FLIGHTS)
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

SEARCH_FLIGHTS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_QUERY, default=""): cv.string,
        vol.Optional(CONF_FLIGHT_DATE): cv.date,
        vol.Optional(CONF_DIRECTION): vol.In(["departure", "arrival"]),
        vol.Optional(CONF_INCLUDE_COMPLETED, default=True): cv.boolean,
        vol.Optional("limit", default=20): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=50),
        ),
    }
)


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain services once."""
    if hass.services.has_service(DOMAIN, SERVICE_TRACK_FLIGHT):
        return

    async def async_handle_search_flights(call: ServiceCall) -> dict[str, object]:
        """Search current airport feed records."""
        entry = _async_get_loaded_entry(hass)
        if entry is None:
            raise HomeAssistantError("Ben Gurion Airport is not configured")

        direction = call.data.get(CONF_DIRECTION)
        api_direction = _api_direction(direction)
        include_completed = call.data[CONF_INCLUDE_COMPLETED]
        limit = call.data["limit"]
        query_tokens = _search_tokens(call.data[CONF_QUERY])
        api_query = " ".join(query_tokens)

        api = BenGurionAirportApiClient(hass)
        try:
            flights = await api.async_fetch_flights(
                direction=api_direction,
                include_completed=include_completed,
                limit=1000 if not api_query else max(200, limit * 5),
                query=api_query or None,
            )
        except BenGurionAirportApiError as err:
            raise HomeAssistantError(str(err)) from err

        matches = _filter_search_results(
            flights,
            query_tokens=query_tokens,
            flight_date=call.data.get(CONF_FLIGHT_DATE),
        )
        return {
            "count": len(matches),
            "flights": [_search_result(flight) for flight in matches[:limit]],
        }

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
        SERVICE_SEARCH_FLIGHTS,
        async_handle_search_flights,
        schema=SEARCH_FLIGHTS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
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


def _api_direction(direction: str | None) -> str | None:
    """Convert service direction labels to API direction codes."""
    if direction == DIRECTION_DEPARTURE_LABEL:
        return DIRECTION_DEPARTURE
    if direction == DIRECTION_ARRIVAL_LABEL:
        return DIRECTION_ARRIVAL
    return None


def _filter_search_results(
    flights: list[dict[str, object]],
    *,
    query_tokens: list[str],
    flight_date: date | str | None,
) -> list[dict[str, object]]:
    """Filter fetched flights for user-facing search."""
    requested_date = _normalize_service_date(flight_date) if flight_date else None

    matches = []
    for flight in flights:
        if (
            requested_date
            and (flight.get("scheduled_time") or "")[:10] != requested_date
        ):
            continue

        search_text = _flight_search_text(flight)
        if query_tokens and not all(token in search_text for token in query_tokens):
            continue

        matches.append(flight)

    return matches


def _search_tokens(query: str) -> list[str]:
    """Build useful search tokens from a natural flight query."""
    tokens = []
    for raw_token in query.upper().replace("-", " ").split():
        token = "".join(char for char in raw_token if char.isalnum())
        if not token or token in IGNORED_SEARCH_TOKENS or token in LOCAL_AIRPORT_TOKENS:
            continue
        tokens.append(token)
    return tokens


def _flight_search_text(flight: dict[str, object]) -> str:
    """Build normalized searchable text for a flight."""
    values = [
        flight.get("flight_code"),
        flight.get("flight_number"),
        flight.get("airline_code"),
        flight.get("airline_name"),
        flight.get("airport_code"),
        flight.get("city"),
        flight.get("city_raw"),
        flight.get("country"),
        "TLV",
        "Ben Gurion",
        "Tel Aviv",
    ]
    return "".join(
        char
        for value in values
        for char in str(value or "").upper()
        if char.isalnum()
    )


def _search_result(flight: dict[str, object]) -> dict[str, object]:
    """Return the compact flight payload shown in action responses."""
    return {
        "flight_code": flight.get("flight_code"),
        "flight_date": (flight.get("scheduled_time") or "")[:10],
        "direction": flight.get("direction"),
        "scheduled_time": flight.get("scheduled_time"),
        "updated_time": flight.get("updated_time"),
        "status": flight.get("status"),
        "airline_name": flight.get("airline_name"),
        "airport_code": flight.get("airport_code"),
        "city": flight.get("city"),
        "terminal": flight.get("terminal"),
        "gate": flight.get("gate"),
        "checkin_zone": flight.get("checkin_zone"),
    }

"""Constants for the Ben Gurion Airport integration."""

from __future__ import annotations

DOMAIN = "ben_gurion_airport"
NAME = "Ben Gurion Airport"

DEFAULT_REFRESH_MINUTES = 5
DEFAULT_BOARD_LIMIT = 10
DEFAULT_INCLUDE_COMPLETED = False

CONF_BOARD_LIMIT = "board_limit"
CONF_DIRECTION = "direction"
CONF_FLIGHT_CODE = "flight_code"
CONF_FLIGHT_DATE = "flight_date"
CONF_INCLUDE_COMPLETED = "include_completed"
CONF_REFRESH_MINUTES = "refresh_minutes"

RESOURCE_ID = "e83f763b-b7d7-479e-b172-ae981ddc6de5"
API_URL = "https://data.gov.il/api/3/action/datastore_search"
USER_AGENT = "datagov-external-client"

UPCOMING_STATUSES = ["ON TIME", "DELAYED", "EARLY", "FINAL", "NOT FINAL"]
COMPLETED_STATUSES = ["DEPARTED", "LANDED", "CANCELED"]

DIRECTION_ARRIVAL = "A"
DIRECTION_DEPARTURE = "D"
DIRECTION_ARRIVAL_LABEL = "arrival"
DIRECTION_DEPARTURE_LABEL = "departure"

COORDINATOR_KEY = "coordinator"
TRACKED_FLIGHTS_KEY = "tracked_flights"
TRACKED_FLIGHTS_STORE_VERSION = 1

SERVICE_TRACK_FLIGHT = "track_flight"
SERVICE_UNTRACK_FLIGHT = "untrack_flight"

STATE_NOT_FOUND = "not_found"


def tracked_flights_signal(entry_id: str) -> str:
    """Build the dispatcher signal name for tracked flights."""
    return f"{DOMAIN}_{entry_id}_tracked_flights_updated"

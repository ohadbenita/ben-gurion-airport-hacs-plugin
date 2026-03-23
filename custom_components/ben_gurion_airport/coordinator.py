"""DataUpdateCoordinator for Ben Gurion Airport."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import BenGurionAirportApiClient, BenGurionAirportApiError
from .const import (
    CONF_BOARD_LIMIT,
    CONF_INCLUDE_COMPLETED,
    CONF_REFRESH_MINUTES,
    DIRECTION_ARRIVAL,
    DIRECTION_DEPARTURE,
    DOMAIN,
    UPCOMING_STATUSES,
)
from .tracking import TrackedFlightsStore, build_tracked_flight_snapshots

_LOGGER = logging.getLogger(__name__)


class BenGurionAirportDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate Ben Gurion Airport data fetching."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        tracked_flights: TrackedFlightsStore,
    ) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.api = BenGurionAirportApiClient(hass)
        self.tracked_flights = tracked_flights

        refresh_minutes = entry.options.get(
            CONF_REFRESH_MINUTES,
            entry.data[CONF_REFRESH_MINUTES],
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=refresh_minutes),
        )

    @property
    def board_limit(self) -> int:
        """Return the configured board limit."""
        return self.entry.options.get(CONF_BOARD_LIMIT, self.entry.data[CONF_BOARD_LIMIT])

    @property
    def include_completed(self) -> bool:
        """Return whether completed flights should be included."""
        return self.entry.options.get(
            CONF_INCLUDE_COMPLETED,
            self.entry.data[CONF_INCLUDE_COMPLETED],
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the remote API."""
        try:
            departures = await self.api.async_fetch_flights(
                direction=DIRECTION_DEPARTURE,
                include_completed=True,
            )
            arrivals = await self.api.async_fetch_flights(
                direction=DIRECTION_ARRIVAL,
                include_completed=True,
            )
        except BenGurionAirportApiError as err:
            raise UpdateFailed(str(err)) from err

        now = dt_util.utcnow().isoformat()
        board_departures = filter_board_flights(departures, self.include_completed)
        board_arrivals = filter_board_flights(arrivals, self.include_completed)

        return {
            "fetched_at": now,
            "departures": summarize_board(board_departures, self.board_limit),
            "arrivals": summarize_board(board_arrivals, self.board_limit),
            "tracked_flights": build_tracked_flight_snapshots(
                self.tracked_flights.values(),
                departures,
                arrivals,
            ),
        }


def filter_board_flights(
    flights: list[dict[str, Any]],
    include_completed: bool,
) -> list[dict[str, Any]]:
    """Filter flights for board presentation."""
    if include_completed:
        return flights

    return [
        flight
        for flight in flights
        if flight.get("status") in UPCOMING_STATUSES
    ]


def summarize_board(flights: list[dict[str, Any]], board_limit: int) -> dict[str, Any]:
    """Build summary data for one board."""
    sorted_flights = sorted(
        flights,
        key=lambda item: item.get("scheduled_time") or "",
    )
    board = sorted_flights[:board_limit]
    delayed_count = sum(1 for flight in sorted_flights if flight.get("is_delayed"))

    return {
        "count": len(sorted_flights),
        "delayed_count": delayed_count,
        "next_flight": board[0] if board else None,
        "flights": board,
    }

"""Tracked-flight persistence and matching helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
from typing import Any

from homeassistant.helpers.storage import Store

from .const import DOMAIN, TRACKED_FLIGHTS_STORE_VERSION


@dataclass(slots=True, frozen=True)
class TrackedFlightDefinition:
    """A configured tracked flight."""

    id: str
    flight_code: str
    flight_date: str
    direction: str
    name: str | None = None


class TrackedFlightsStore:
    """Persist tracked flights for a config entry."""

    def __init__(self, hass: Any, entry_id: str) -> None:
        """Initialize the tracked-flight store."""
        self._store = Store(
            hass,
            TRACKED_FLIGHTS_STORE_VERSION,
            f"{DOMAIN}.{entry_id}.tracked_flights",
        )
        self._tracked_flights: dict[str, TrackedFlightDefinition] = {}

    async def async_load(self) -> None:
        """Load tracked flights from storage."""
        payload = await self._store.async_load()
        if not payload:
            self._tracked_flights = {}
            return

        self._tracked_flights = {
            item["id"]: TrackedFlightDefinition(**item)
            for item in payload.get("tracked_flights", [])
        }

    async def async_track_flight(
        self,
        *,
        flight_code: str,
        flight_date: str | date,
        direction: str,
        name: str | None = None,
    ) -> TrackedFlightDefinition:
        """Add or update a tracked flight."""
        normalized_code = normalize_flight_code(flight_code)
        normalized_date = normalize_flight_date(flight_date)
        tracker_id = build_tracked_flight_id(direction, normalized_code, normalized_date)

        existing = self._tracked_flights.get(tracker_id)
        definition = TrackedFlightDefinition(
            id=tracker_id,
            flight_code=normalized_code,
            flight_date=normalized_date,
            direction=direction,
            name=name if name is not None else (existing.name if existing else None),
        )
        self._tracked_flights[tracker_id] = definition
        await self._async_save()
        return definition

    async def async_untrack_flight(
        self,
        *,
        flight_code: str,
        flight_date: str | date,
        direction: str,
    ) -> TrackedFlightDefinition | None:
        """Remove a tracked flight."""
        tracker_id = build_tracked_flight_id(
            direction,
            normalize_flight_code(flight_code),
            normalize_flight_date(flight_date),
        )
        definition = self._tracked_flights.pop(tracker_id, None)
        await self._async_save()
        return definition

    def get(self, tracker_id: str) -> TrackedFlightDefinition | None:
        """Return a tracked flight by id."""
        return self._tracked_flights.get(tracker_id)

    def values(self) -> tuple[TrackedFlightDefinition, ...]:
        """Return all tracked flights."""
        return tuple(self._tracked_flights.values())

    async def _async_save(self) -> None:
        """Save tracked flights to storage."""
        await self._store.async_save(
            {
                "tracked_flights": [
                    asdict(definition)
                    for definition in sorted(
                        self._tracked_flights.values(),
                        key=lambda item: item.id,
                    )
                ]
            }
        )


def normalize_flight_code(flight_code: str) -> str:
    """Normalize a flight code for matching."""
    return "".join(char for char in flight_code.upper() if char.isalnum())


def normalize_flight_date(flight_date: str | date) -> str:
    """Normalize a flight date to ISO format."""
    if isinstance(flight_date, date):
        return flight_date.isoformat()
    return str(flight_date)


def build_tracked_flight_id(direction: str, flight_code: str, flight_date: str) -> str:
    """Build a stable id for a tracked flight."""
    safe_date = flight_date.replace("-", "_")
    return f"{direction}_{flight_code.lower()}_{safe_date}"


def build_tracked_flight_snapshots(
    tracked_flights: tuple[TrackedFlightDefinition, ...],
    departures: list[dict[str, Any]],
    arrivals: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build the current snapshot for each tracked flight."""
    snapshots: dict[str, dict[str, Any]] = {}

    for definition in tracked_flights:
        source = departures if definition.direction == "departure" else arrivals
        matches = [
            flight
            for flight in source
            if flight.get("flight_code") == definition.flight_code
            and (flight.get("scheduled_time") or "")[:10] == definition.flight_date
        ]
        flight = matches[0] if matches else None
        snapshots[definition.id] = {
            "matched": bool(matches),
            "match_count": len(matches),
            "flight": flight,
            "change_token": build_change_token(flight),
        }

    return snapshots


def build_change_token(flight: dict[str, Any] | None) -> str | None:
    """Build a token that changes whenever the tracked flight payload changes."""
    if flight is None:
        return None

    payload = json.dumps(flight, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()

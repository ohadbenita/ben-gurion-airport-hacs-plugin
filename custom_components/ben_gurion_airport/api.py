"""API client for Ben Gurion Airport flight data."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import logging
from typing import Any

from aiohttp import ClientError

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_URL, RESOURCE_ID, USER_AGENT

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class BenGurionAirportApiClient:
    """Thin async client for the data.gov.il datastore API."""

    hass: Any

    async def async_fetch_flights(
        self,
        *,
        direction: str | None = None,
        include_completed: bool = False,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Fetch flights from the airport feed."""
        params: dict[str, Any] = {
            "resource_id": RESOURCE_ID,
            "limit": limit,
            "sort": "CHSTOL asc",
        }

        filters: dict[str, Any] = {}
        if direction:
            filters["CHAORD"] = direction

        if not include_completed:
            filters["CHRMINE"] = ["ON TIME", "DELAYED", "EARLY", "FINAL", "NOT FINAL"]

        if filters:
            params["filters"] = json.dumps(filters, separators=(",", ":"))

        session = async_get_clientsession(self.hass)
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }

        _LOGGER.debug("Fetching airport data with params=%s", params)

        try:
            async with session.get(API_URL, params=params, headers=headers, timeout=30) as response:
                response.raise_for_status()
                payload = await response.json()
        except (TimeoutError, ClientError, ValueError) as err:
            raise BenGurionAirportApiError(f"Failed to fetch airport data: {err}") from err

        if not payload.get("success"):
            raise BenGurionAirportApiError(
                f"Airport API returned an unsuccessful response: {payload}"
            )

        records = payload["result"].get("records", [])
        return [normalize_record(record) for record in records]


class BenGurionAirportApiError(Exception):
    """Raised when the airport API request fails."""


def normalize_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a raw API record into a Home Assistant-friendly dict."""
    scheduled = record.get("CHSTOL")
    actual = record.get("CHPTOL")
    flight_code = f"{record.get('CHOPER', '')}{record.get('CHFLTN', '')}".strip()

    return {
        "id": str(record.get("_id", "")),
        "flight_code": flight_code,
        "flight_number": record.get("CHFLTN"),
        "airline_code": record.get("CHOPER"),
        "airline_name": record.get("CHOPERD"),
        "direction": "departure" if record.get("CHAORD") == "D" else "arrival",
        "airport_code": record.get("CHLOC1"),
        "city": record.get("CHLOC1T"),
        "city_hebrew": record.get("CHLOC1TH"),
        "city_raw": record.get("CHLOC1D"),
        "country": record.get("CHLOCCT"),
        "country_hebrew": record.get("CHLOC1CH"),
        "scheduled_time": scheduled,
        "updated_time": actual,
        "terminal": record.get("CHTERM"),
        "gate": record.get("CHCINT"),
        "checkin_zone": record.get("CHCKZN"),
        "status": record.get("CHRMINE"),
        "status_hebrew": record.get("CHRMINH"),
        "is_delayed": record.get("CHRMINE") == "DELAYED",
    }

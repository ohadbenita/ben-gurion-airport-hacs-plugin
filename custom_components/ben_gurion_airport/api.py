"""API client for Ben Gurion Airport flight data."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import asyncio
import json
import logging
from typing import Any

from aiohttp import ClientError, ClientResponseError

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_URL, RESOURCE_ID, UPCOMING_STATUSES, USER_AGENT

_LOGGER = logging.getLogger(__name__)

TRANSIENT_HTTP_STATUSES = {429, 502, 503, 504}
RETRY_DELAYS = (1, 3)


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

        try:
            payload = await self._async_fetch_payload(params)
        except BenGurionAirportApiError:
            if "filters" not in params:
                raise

            fallback_params = {
                "resource_id": RESOURCE_ID,
                "limit": limit * 2,
                "sort": "CHSTOL asc",
            }
            _LOGGER.warning(
                "Filtered airport data request failed; retrying without API filters"
            )
            payload = await self._async_fetch_payload(fallback_params)

        if not payload.get("success"):
            raise BenGurionAirportApiError(
                f"Airport API returned an unsuccessful response: {payload}"
            )

        records = payload["result"].get("records", [])
        filtered_records = filter_records(
            records,
            direction=direction,
            include_completed=include_completed,
        )
        return [normalize_record(record) for record in filtered_records[:limit]]

    async def _async_fetch_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        """Fetch a payload from the airport API with transient-error retries."""
        session = async_get_clientsession(self.hass)
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }

        _LOGGER.debug("Fetching airport data with params=%s", params)

        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                async with session.get(
                    API_URL,
                    params=params,
                    headers=headers,
                    timeout=30,
                ) as response:
                    response.raise_for_status()
                    return await response.json()
            except ClientResponseError as err:
                if err.status not in TRANSIENT_HTTP_STATUSES or attempt == len(
                    RETRY_DELAYS
                ):
                    raise BenGurionAirportApiError(
                        f"Failed to fetch airport data: {err}"
                    ) from err

                delay = RETRY_DELAYS[attempt]
                _LOGGER.warning(
                    "Airport API returned HTTP %s; retrying in %s seconds",
                    err.status,
                    delay,
                )
                await asyncio.sleep(delay)
            except (TimeoutError, ClientError) as err:
                if attempt == len(RETRY_DELAYS):
                    raise BenGurionAirportApiError(
                        f"Failed to fetch airport data: {err}"
                    ) from err

                delay = RETRY_DELAYS[attempt]
                _LOGGER.warning(
                    "Airport API request failed; retrying in %s seconds: %s",
                    delay,
                    err,
                )
                await asyncio.sleep(delay)
            except ValueError as err:
                raise BenGurionAirportApiError(
                    f"Failed to fetch airport data: {err}"
                ) from err

        raise BenGurionAirportApiError("Failed to fetch airport data")


class BenGurionAirportApiError(Exception):
    """Raised when the airport API request fails."""


def filter_records(
    records: list[Mapping[str, Any]],
    *,
    direction: str | None,
    include_completed: bool,
) -> list[Mapping[str, Any]]:
    """Apply the same filters locally that are normally sent to the API."""
    filtered_records = records

    if direction:
        filtered_records = [
            record for record in filtered_records if record.get("CHAORD") == direction
        ]

    if not include_completed:
        filtered_records = [
            record
            for record in filtered_records
            if record.get("CHRMINE") in UPCOMING_STATUSES
        ]

    return filtered_records


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

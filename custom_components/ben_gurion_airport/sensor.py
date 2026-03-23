"""Sensors for the Ben Gurion Airport integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    COORDINATOR_KEY,
    DOMAIN,
    STATE_NOT_FOUND,
    TRACKED_FLIGHTS_KEY,
    tracked_flights_signal,
)
from .coordinator import BenGurionAirportDataUpdateCoordinator
from .tracking import TrackedFlightDefinition, TrackedFlightsStore


@dataclass(frozen=True, kw_only=True)
class BenGurionAirportSensorDescription(SensorEntityDescription):
    """Describe a Ben Gurion Airport sensor."""

    board_key: str


SENSORS: tuple[BenGurionAirportSensorDescription, ...] = (
    BenGurionAirportSensorDescription(
        key="departures_board",
        name="Departures Board",
        icon="mdi:airplane-takeoff",
        board_key="departures",
    ),
    BenGurionAirportSensorDescription(
        key="arrivals_board",
        name="Arrivals Board",
        icon="mdi:airplane-landing",
        board_key="arrivals",
    ),
    BenGurionAirportSensorDescription(
        key="airport_last_update",
        name="Last Update",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        board_key="meta",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Ben Gurion Airport sensors."""
    coordinator: BenGurionAirportDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        COORDINATOR_KEY
    ]
    tracked_flights: TrackedFlightsStore = hass.data[DOMAIN][entry.entry_id][TRACKED_FLIGHTS_KEY]

    tracked_entities: dict[str, BenGurionAirportTrackedFlightSensor] = {}
    known_tracker_ids: set[str] = set()
    initial_tracked_entities: list[BenGurionAirportTrackedFlightSensor] = []

    for definition in tracked_flights.values():
        entity = BenGurionAirportTrackedFlightSensor(
            coordinator,
            entry,
            tracked_flights,
            definition.id,
        )
        tracked_entities[definition.id] = entity
        known_tracker_ids.add(definition.id)
        initial_tracked_entities.append(entity)

    async_add_entities(
        [
            *[
                BenGurionAirportSensor(coordinator, entry, description)
                for description in SENSORS
            ],
            *initial_tracked_entities,
        ]
    )

    @callback
    def async_handle_tracked_flights_update() -> None:
        """Add newly tracked flights and refresh existing tracked entities."""
        new_entities: list[BenGurionAirportTrackedFlightSensor] = []
        for definition in tracked_flights.values():
            if definition.id in known_tracker_ids:
                continue

            entity = BenGurionAirportTrackedFlightSensor(
                coordinator,
                entry,
                tracked_flights,
                definition.id,
            )
            tracked_entities[definition.id] = entity
            known_tracker_ids.add(definition.id)
            new_entities.append(entity)

        if new_entities:
            async_add_entities(new_entities)

        for entity in tracked_entities.values():
            entity.async_write_ha_state()

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            tracked_flights_signal(entry.entry_id),
            async_handle_tracked_flights_update,
        )
    )


class BenGurionAirportSensor(
    CoordinatorEntity[BenGurionAirportDataUpdateCoordinator], SensorEntity
):
    """Representation of a Ben Gurion Airport sensor."""

    entity_description: BenGurionAirportSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BenGurionAirportDataUpdateCoordinator,
        entry: ConfigEntry,
        description: BenGurionAirportSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Israel Open Data Portal",
            "model": "Ben Gurion Airport Feed",
        }

    @property
    def native_value(self) -> Any:
        """Return the sensor state."""
        if self.entity_description.board_key == "meta":
            return self.coordinator.data["fetched_at"]

        return self.coordinator.data[self.entity_description.board_key]["count"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity attributes."""
        if self.entity_description.board_key == "meta":
            return {
                "refresh_minutes": int(self.coordinator.update_interval.total_seconds() / 60),
                "board_limit": self.coordinator.board_limit,
                "include_completed": self.coordinator.include_completed,
            }

        board = self.coordinator.data[self.entity_description.board_key]
        return {
            "delayed_count": board["delayed_count"],
            "next_flight": board["next_flight"],
            "flights": board["flights"],
        }


class BenGurionAirportTrackedFlightSensor(
    CoordinatorEntity[BenGurionAirportDataUpdateCoordinator], SensorEntity
):
    """Representation of a tracked Ben Gurion Airport flight."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BenGurionAirportDataUpdateCoordinator,
        entry: ConfigEntry,
        tracked_flights: TrackedFlightsStore,
        tracker_id: str,
    ) -> None:
        """Initialize the tracked-flight sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._tracked_flights = tracked_flights
        self._tracker_id = tracker_id
        self._attr_unique_id = f"{entry.entry_id}_{tracker_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Israel Open Data Portal",
            "model": "Ben Gurion Airport Feed",
        }

    @property
    def available(self) -> bool:
        """Return whether the entity is still configured."""
        return self._definition is not None and super().available

    @property
    def name(self) -> str:
        """Return the entity name."""
        definition = self._definition
        if definition is None:
            return self._tracker_id

        if definition.name:
            return definition.name

        return f"Tracked {definition.flight_code} {definition.flight_date}"

    @property
    def icon(self) -> str:
        """Return the entity icon."""
        definition = self._definition
        if definition is None:
            return "mdi:airplane-alert"
        if definition.direction == "departure":
            return "mdi:airplane-takeoff"
        return "mdi:airplane-landing"

    @property
    def native_value(self) -> str | None:
        """Return the tracked flight status."""
        if self._definition is None:
            return None

        snapshot = self._snapshot
        if not snapshot or not snapshot.get("flight"):
            return STATE_NOT_FOUND

        return snapshot["flight"].get("status") or STATE_NOT_FOUND

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return tracked-flight attributes."""
        definition = self._definition
        if definition is None:
            return {}

        snapshot = self._snapshot
        attributes: dict[str, Any] = {
            "tracked_flight_code": definition.flight_code,
            "tracked_flight_date": definition.flight_date,
            "tracked_direction": definition.direction,
            "matched": bool(snapshot and snapshot.get("matched")),
            "match_count": snapshot.get("match_count", 0) if snapshot else 0,
            "change_token": snapshot.get("change_token") if snapshot else None,
            "last_refresh": self.coordinator.data.get("fetched_at"),
        }

        if definition.name:
            attributes["tracking_name"] = definition.name

        if snapshot and snapshot.get("flight"):
            attributes.update(snapshot["flight"])

        return attributes

    @property
    def _definition(self) -> TrackedFlightDefinition | None:
        """Return the tracked-flight definition."""
        return self._tracked_flights.get(self._tracker_id)

    @property
    def _snapshot(self) -> dict[str, Any] | None:
        """Return the current tracked-flight snapshot."""
        return self.coordinator.data.get("tracked_flights", {}).get(self._tracker_id)

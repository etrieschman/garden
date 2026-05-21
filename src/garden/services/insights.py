"""Read-side queries that aggregate across domain entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from garden.domain import Event, Location, Plant, Recommendation, Taxon
from garden.storage.base import Storage


@dataclass
class PlantStatus:
    plant: Plant
    taxon: Taxon | None
    location: Location | None
    last_event: Event | None
    active_recommendations: list[Recommendation]


def plant_status(storage: Storage, plant_id: str) -> PlantStatus:
    plant = storage.get_plant(plant_id)
    if not plant:
        raise LookupError(f"plant not found: {plant_id}")
    events = storage.list_events(plant_id=plant_id)
    return PlantStatus(
        plant=plant,
        taxon=storage.get_taxon(plant.taxon_id),
        location=storage.get_location(plant.location_id) if plant.location_id else None,
        last_event=events[0] if events else None,
        active_recommendations=storage.list_recommendations(plant_id=plant_id),
    )


def recent_activity(storage: Storage, days: int = 7) -> list[Event]:
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    return storage.list_events(since=since)

"""Logging — discrete events and observations.

Every input channel (CLI, future web/Slack) calls into these functions. This is
the single point at which user-visible verbs become rows in storage.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from garden.domain import TERMINAL_PLANT_STATUSES, Event, EventType, Observation, PlantStatus
from garden.services.garden import resolve_plant
from garden.storage.base import Storage


def log_event(
    storage: Storage,
    *,
    plant_query: str | None = None,
    location_id: str | None = None,
    type: EventType,
    occurred_at: datetime | None = None,
    details: dict[str, Any] | None = None,
    notes: str | None = None,
    source: str = "cli",
    actor: str = "manual:user",
    from_location_id: str | None = None,
) -> Event:
    plant_id: str | None = None
    if plant_query:
        plant = resolve_plant(storage, plant_query)
        if plant.status in TERMINAL_PLANT_STATUSES:
            raise ValueError(
                f"plant {plant.id!r} is {plant.status.value} — no further events can be "
                "logged for it. If this was a mistake, fix the plant status directly or "
                "delete the terminal event (e.g. the DIED / REMOVED event)."
            )
        plant_id = plant.id
        if location_id is None and plant.location_id is not None:
            location_id = plant.location_id
        _update_plant_status_from_event(storage, plant_id, type)

    event = Event(
        type=type,
        plant_id=plant_id,
        location_id=location_id,
        from_location_id=from_location_id,
        occurred_at=occurred_at or datetime.now(UTC).replace(tzinfo=None),
        details=details or {},
        notes=notes,
        source=source,
        actor=actor,
    )
    return storage.create_event(event)


def log_observation(
    storage: Storage,
    *,
    metric: str,
    value_numeric: float | None = None,
    value_text: str | None = None,
    unit: str | None = None,
    plant_query: str | None = None,
    location_id: str | None = None,
    occurred_at: datetime | None = None,
    source: str = "manual:user",
    notes: str | None = None,
) -> Observation:
    plant_id: str | None = None
    if plant_query:
        plant_id = resolve_plant(storage, plant_query).id
    obs = Observation(
        metric=metric,
        value_numeric=value_numeric,
        value_text=value_text,
        unit=unit,
        plant_id=plant_id,
        location_id=location_id,
        occurred_at=occurred_at or datetime.now(UTC).replace(tzinfo=None),
        source=source,
        notes=notes,
    )
    return storage.create_observation(obs)


_STATUS_FROM_EVENT = {
    EventType.SEEDED: PlantStatus.SEEDED,
    EventType.GERMINATED: PlantStatus.GERMINATED,
    EventType.TRANSPLANTED: PlantStatus.TRANSPLANTED,
    EventType.HARVESTED: PlantStatus.HARVESTED,
    EventType.DIED: PlantStatus.DEAD,
    EventType.REMOVED: PlantStatus.REMOVED,
}


def _update_plant_status_from_event(
    storage: Storage, plant_id: str, event_type: EventType
) -> None:
    new_status = _STATUS_FROM_EVENT.get(event_type)
    if new_status is None:
        return
    plant = storage.get_plant(plant_id)
    if plant is None or plant.status == new_status:
        return
    plant.status = new_status
    storage.update_plant(plant)

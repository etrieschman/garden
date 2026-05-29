"""Logging — discrete events and observations.

Every input channel (CLI, future web/Slack) calls into these functions. This is
the single point at which user-visible verbs become rows in storage.

What an event does to its target plant lives in `EVENT_EFFECTS`
(`garden.domain.event`). This module just applies those effects.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from garden.domain import EVENT_EFFECTS, Event, EventType, Observation, Plant
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
    photo_path: str | None = None,
    source: str = "cli",
    actor: str = "manual:user",
    from_location_id: str | None = None,
) -> Event:
    occurred = occurred_at or datetime.now(UTC).replace(tzinfo=None)
    details = details or {}

    plant_id: str | None = None
    if plant_query:
        plant = resolve_plant(storage, plant_query)
        if not plant.is_alive:
            raise ValueError(
                f"plant {plant.id!r} was marked terminal on "
                f"{plant.terminal_at:%Y-%m-%d} — no further events can be logged "
                "for it. If this was a mistake, delete the DIED/REMOVED event."
            )
        plant_id = plant.id
        if location_id is None and plant.location_id is not None:
            location_id = plant.location_id
        _apply_event_to_plant(storage, plant, type, occurred, details)

    event = Event(
        type=type,
        plant_id=plant_id,
        location_id=location_id,
        from_location_id=from_location_id,
        occurred_at=occurred,
        details=details,
        photo_path=photo_path,
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


def _apply_event_to_plant(
    storage: Storage,
    plant: Plant,
    event_type: EventType,
    occurred_at: datetime,
    details: dict[str, Any],
) -> None:
    """Apply the EVENT_EFFECTS entry for `event_type` to `plant` and persist."""
    effect = EVENT_EFFECTS.get(event_type)
    if effect is None:
        return
    changed = False
    if effect.lifecycle is not None and plant.status != effect.lifecycle:
        plant.status = effect.lifecycle
        changed = True
    if effect.terminal:
        plant.terminal_at = occurred_at
        plant.terminal_cause = (
            details.get(effect.cause_field) if effect.cause_field else None
        )
        changed = True
    if changed:
        storage.update_plant(plant)

"""Coverage for the event-admin paths: bed-scoped events + prefix delete."""

import pytest

from garden.domain import (
    Event,
    EventType,
    Location,
    LocationKind,
    Plant,
    PlantStatus,
    Taxon,
)
from garden.services import logging as logging_svc
from garden.storage.sqlite import SQLiteStorage


def _bed(storage: SQLiteStorage, id_: str = "bed-a") -> Location:
    loc = Location(id=id_, name=id_, kind=LocationKind.RAISED_BED)
    storage.upsert_location(loc)
    return loc


def test_bed_scoped_event_stores_location_id_with_null_plant(storage: SQLiteStorage) -> None:
    bed = _bed(storage)
    e = storage.create_event(
        Event(
            type=EventType.AMENDED,
            location_id=bed.id,
            details={"added": "bag of manure"},
        )
    )
    rows = storage.list_events(location_id=bed.id)
    assert len(rows) == 1
    assert rows[0].plant_id is None
    assert rows[0].location_id == bed.id
    assert rows[0].details == {"added": "bag of manure"}
    assert rows[0].id == e.id


def test_find_events_by_prefix_and_delete(storage: SQLiteStorage) -> None:
    bed = _bed(storage)
    e = storage.create_event(Event(type=EventType.AMENDED, location_id=bed.id))

    prefix = str(e.id)[:8]
    matches = storage.find_events_by_prefix(prefix)
    assert len(matches) == 1
    assert matches[0].id == e.id

    storage.delete_event(e.id)
    assert storage.find_events_by_prefix(prefix) == []
    assert storage.list_events(location_id=bed.id) == []


def test_terminal_plants_excluded_from_recommend_context(storage: SQLiteStorage) -> None:
    """`terminal_at != None` makes a plant invisible to the recommend pipeline."""
    from datetime import UTC, datetime

    from garden.services.recommend import build_context

    bed = _bed(storage)
    taxon = storage.upsert_taxon(
        Taxon(id="t1", scientific_name="Solanum lycopersicum", common_name="tomato")
    )
    alive = storage.create_plant(
        Plant(id="alive", taxon_id=taxon.id, location_id=bed.id, status=PlantStatus.GROWING)
    )
    storage.create_plant(
        Plant(
            id="dead",
            taxon_id=taxon.id,
            location_id=bed.id,
            status=PlantStatus.GROWING,
            terminal_at=datetime.now(UTC),
            terminal_cause="frost",
        )
    )

    ctx = build_context(storage)
    assert {p.id for p in ctx.plants} == {alive.id}


@pytest.mark.parametrize(
    ("terminal_event", "details", "expected_cause"),
    [
        (EventType.DIED, {"cause": "frost"}, "frost"),
        (EventType.REMOVED, {"reason": "end of season"}, "end of season"),
        (EventType.DIED, {}, None),
    ],
)
def test_terminal_event_marks_plant_and_refuses_further_events(
    storage: SQLiteStorage,
    terminal_event: EventType,
    details: dict[str, object],
    expected_cause: str | None,
) -> None:
    """A DIED/REMOVED event sets terminal_at + terminal_cause; further events
    on that plant raise. Both verbs go through the same EVENT_EFFECTS entry."""
    bed = _bed(storage)
    taxon = storage.upsert_taxon(
        Taxon(id="t1", scientific_name="Solanum lycopersicum", common_name="tomato")
    )
    plant = storage.create_plant(
        Plant(id="p1", taxon_id=taxon.id, location_id=bed.id, status=PlantStatus.GROWING)
    )

    logging_svc.log_event(
        storage, plant_query=plant.id, type=terminal_event, details=details
    )

    refreshed = storage.get_plant(plant.id)
    assert refreshed is not None
    assert refreshed.terminal_at is not None
    assert refreshed.terminal_cause == expected_cause
    # lifecycle status is preserved — DIED/REMOVED no longer overwrite it
    assert refreshed.status == PlantStatus.GROWING

    with pytest.raises(ValueError, match="terminal"):
        logging_svc.log_event(storage, plant_query=plant.id, type=EventType.WATERED)

    types = [e.type for e in storage.list_events(plant_id=plant.id)]
    assert EventType.WATERED not in types

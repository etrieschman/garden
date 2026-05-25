"""Coverage for the event-admin paths: bed-scoped events + prefix delete."""

from garden.domain import (
    Event,
    EventType,
    Location,
    LocationKind,
)
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

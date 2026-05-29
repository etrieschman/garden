"""Coverage for `services/snapshot.py` — the single feed for the website + `garden today`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from garden.domain import (
    Dimensions,
    Location,
    LocationKind,
    Plant,
    PlantStatus,
    Taxon,
)
from garden.recommendations import build_engines
from garden.services import snapshot as snapshot_svc
from garden.storage.sqlite import SQLiteStorage


def _setup(storage: SQLiteStorage) -> dict[str, Plant]:
    storage.upsert_location(
        Location(
            id="outdoor-bed",
            name="outdoor",
            kind=LocationKind.RAISED_BED,
            lat=42.37,
            lon=-71.10,
            dimensions=Dimensions(length_cm=120, width_cm=60),
        )
    )
    storage.upsert_location(
        Location(id="seed-tray", name="indoor tray", kind=LocationKind.SEED_TRAY)
    )
    taxon = storage.upsert_taxon(
        Taxon(id="t1", scientific_name="Ocimum basilicum", common_name="basil")
    )
    plants = {
        "outdoor": Plant(
            id="o1", taxon_id=taxon.id, location_id="outdoor-bed", status=PlantStatus.GROWING
        ),
        "indoor": Plant(
            id="i1", taxon_id=taxon.id, location_id="seed-tray", status=PlantStatus.SEEDED
        ),
        "no-bed": Plant(id="o2", taxon_id=taxon.id, status=PlantStatus.SEEDED),
        "terminal": Plant(
            id="d1",
            taxon_id=taxon.id,
            location_id="outdoor-bed",
            status=PlantStatus.GROWING,
            terminal_at=datetime.now(UTC) - timedelta(days=2),
        ),
    }
    for p in plants.values():
        storage.create_plant(p)
    return plants


def test_snapshot_partitions_alive_plants_and_drops_terminal(storage: SQLiteStorage) -> None:
    plants = _setup(storage)
    snap = snapshot_svc.get_snapshot(storage, build_engines(["care-profile"]))

    assert {p.id for p in snap.outdoor_plants} == {plants["outdoor"].id}
    # plants with no location fall in with indoor (seed-tray) plants
    assert {p.id for p in snap.indoor_plants} == {plants["indoor"].id, plants["no-bed"].id}
    assert {p.id for p in snap.terminal_plants} == {plants["terminal"].id}


def test_snapshot_buckets_recs_by_due(storage: SQLiteStorage) -> None:
    """Without weather data the care-profile engine emits no due-dated recs, so the
    snapshot's today/upcoming buckets should be empty rather than crash."""
    _setup(storage)
    snap = snapshot_svc.get_snapshot(storage, build_engines(["care-profile"]))
    # smoke check: no exceptions, all three buckets are lists
    assert isinstance(snap.today_actions, list)
    assert isinstance(snap.upcoming_actions, list)
    assert isinstance(snap.later_actions, list)

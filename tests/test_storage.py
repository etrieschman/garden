from garden.domain import (
    Dimensions,
    Event,
    EventType,
    Location,
    LocationKind,
    Plant,
    PlantStatus,
    Substrate,
    Taxon,
)
from garden.storage.sqlite import SQLiteStorage


def test_round_trip_taxon_location_plant_event(storage: SQLiteStorage) -> None:
    taxon = storage.upsert_taxon(
        Taxon(
            id="solanum-lycopersicum--garden-gem",
            scientific_name="Solanum lycopersicum",
            common_name="Tomato",
            cultivar="Garden Gem",
            category="vegetable",
        )
    )
    loc = storage.upsert_location(
        Location(
            id="patio-north",
            name="Patio raised bed (north)",
            kind=LocationKind.RAISED_BED,
            lat=42.3736,
            lon=-71.1034,
            dimensions=Dimensions(length_cm=240, width_cm=120, depth_cm=30),
            substrate=Substrate(medium="Coast of Maine raised bed mix"),
        )
    )
    plant = storage.create_plant(
        Plant(
            id="garden-gem-1",
            taxon_id=taxon.id,
            location_id=loc.id,
            status=PlantStatus.TRANSPLANTED,
        )
    )
    storage.create_event(
        Event(type=EventType.TRANSPLANTED, plant_id=plant.id, location_id=loc.id)
    )

    # round-trip
    assert storage.get_plant("garden-gem-1") is not None
    loaded_loc = storage.get_location("patio-north")
    assert loaded_loc is not None
    assert loaded_loc.dimensions is not None
    assert loaded_loc.dimensions.length_cm == 240
    assert loaded_loc.substrate is not None
    assert loaded_loc.substrate.medium == "Coast of Maine raised bed mix"

    events = storage.list_events(plant_id="garden-gem-1")
    assert len(events) == 1
    assert events[0].type == EventType.TRANSPLANTED


def test_find_plant_by_cultivar(storage: SQLiteStorage) -> None:
    storage.upsert_taxon(
        Taxon(id="t1", scientific_name="Solanum lycopersicum", cultivar="Garden Gem")
    )
    storage.upsert_taxon(
        Taxon(id="t2", scientific_name="Solanum lycopersicum", cultivar="Cherokee Purple")
    )
    storage.create_plant(Plant(id="gem-1", taxon_id="t1"))
    storage.create_plant(Plant(id="cherokee-1", taxon_id="t2"))

    hits = storage.find_plants("Garden Gem")
    assert [p.id for p in hits] == ["gem-1"]

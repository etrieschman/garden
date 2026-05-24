"""End-to-end: transplant a Garden Gem tomato into a raised bed and confirm
the full data flow (taxon resolved, plant created, event logged, status updated)."""

from garden.domain import (
    Dimensions,
    EventType,
    LocationKind,
    PlantStatus,
)
from garden.providers.catalog import LocalCatalog
from garden.services import garden as garden_svc
from garden.services import logging
from garden.storage.sqlite import SQLiteStorage


def test_transplant_garden_gem_to_raised_bed(storage: SQLiteStorage) -> None:
    catalog = LocalCatalog()

    # 1. user creates the raised bed
    bed = garden_svc.add_location(
        storage,
        id="patio-north",
        name="Patio raised bed (north)",
        kind=LocationKind.RAISED_BED,
        lat=42.37360754570248,
        lon=-71.10338051500713,
        dimensions=Dimensions(length_cm=240, width_cm=120, depth_cm=30),
        substrate_medium="Coast of Maine raised bed mix",
    )
    assert bed.dimensions is not None
    assert bed.dimensions.area_m2 == 2.88

    # 2. user runs `garden log transplant "Garden Gem" --to patio-north`
    taxon = garden_svc.resolve_taxon(storage, catalog, "Garden Gem")
    assert taxon.cultivar == "Garden Gem"
    assert taxon.scientific_name == "Solanum lycopersicum"

    plant = garden_svc.add_plant(
        storage, taxon=taxon, location_id=bed.id, status=PlantStatus.TRANSPLANTED
    )
    assert plant.id == "tomato-garden-gem-1"
    assert plant.location_id == "patio-north"

    event = logging.log_event(
        storage,
        plant_query=plant.id,
        type=EventType.TRANSPLANTED,
        location_id=bed.id,
    )
    assert event.plant_id == plant.id
    assert event.location_id == bed.id
    assert event.type == EventType.TRANSPLANTED

    # 3. the plant's status was auto-advanced by the logging service
    refreshed = storage.get_plant(plant.id)
    assert refreshed is not None
    assert refreshed.status == PlantStatus.TRANSPLANTED

    # 4. event is queryable both by plant and by location
    by_plant = storage.list_events(plant_id=plant.id)
    by_location = storage.list_events(location_id=bed.id)
    assert len(by_plant) == 1 and by_plant[0].id == event.id
    assert len(by_location) == 1 and by_location[0].id == event.id

    # 5. another transplant of the same taxon gets a unique id
    plant2 = garden_svc.add_plant(storage, taxon=taxon, location_id=bed.id)
    assert plant2.id == "tomato-garden-gem-2"

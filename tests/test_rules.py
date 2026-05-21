from datetime import datetime, timedelta

from garden.domain import (
    Event,
    EventType,
    Location,
    LocationKind,
    Plant,
    PlantStatus,
    Taxon,
)
from garden.providers.weather import WeatherSample
from garden.recommendations import GardenContext, RuleEngine


def _ctx(now: datetime, **overrides) -> GardenContext:
    base = {
        "now": now,
        "plants": [],
        "locations": {},
        "taxa": {},
        "events_by_plant": {},
        "observations_by_location": {},
        "forecast_by_location": {},
    }
    base.update(overrides)
    return GardenContext(**base)


def test_post_transplant_hold_fires_within_14d() -> None:
    now = datetime(2026, 5, 21, 12)
    plant = Plant(id="gem-1", taxon_id="t1", location_id="bed", status=PlantStatus.TRANSPLANTED)
    transplant = Event(
        type=EventType.TRANSPLANTED, plant_id="gem-1", occurred_at=now - timedelta(days=3)
    )
    ctx = _ctx(now, plants=[plant], events_by_plant={"gem-1": [transplant]})
    recs = RuleEngine().generate(ctx)
    assert any(r.action == "hold-fertilizer" for r in recs)


def test_post_transplant_hold_skips_after_fertilizer() -> None:
    now = datetime(2026, 5, 21, 12)
    plant = Plant(id="gem-1", taxon_id="t1", location_id="bed", status=PlantStatus.TRANSPLANTED)
    transplant = Event(
        type=EventType.TRANSPLANTED, plant_id="gem-1", occurred_at=now - timedelta(days=3)
    )
    fert = Event(
        type=EventType.FERTILIZED, plant_id="gem-1", occurred_at=now - timedelta(days=1)
    )
    ctx = _ctx(now, plants=[plant], events_by_plant={"gem-1": [transplant, fert]})
    recs = RuleEngine().generate(ctx)
    assert not any(r.action == "hold-fertilizer" for r in recs)


def test_frost_warning_for_tomato() -> None:
    now = datetime(2026, 5, 21, 12)
    plant = Plant(id="gem-1", taxon_id="t1", location_id="bed")
    taxon = Taxon(id="t1", scientific_name="Solanum lycopersicum", cultivar="Garden Gem")
    loc = Location(id="bed", name="Bed", kind=LocationKind.RAISED_BED)
    forecast = [
        WeatherSample(timestamp=now + timedelta(days=1), temp_c_min=2.0, temp_c_max=14.0)
    ]
    ctx = _ctx(
        now,
        plants=[plant],
        taxa={"t1": taxon},
        locations={"bed": loc},
        forecast_by_location={"bed": forecast},
    )
    recs = RuleEngine().generate(ctx)
    assert any(r.action == "cover-for-frost" for r in recs)


def test_dry_spell_water_for_dry_warm_days() -> None:
    now = datetime(2026, 7, 15, 12)
    plant = Plant(id="gem-1", taxon_id="t1", location_id="bed")
    forecast = [
        WeatherSample(timestamp=now + timedelta(days=i), temp_c_max=28.0, rain_mm=0.0)
        for i in range(0, 4)
    ]
    ctx = _ctx(now, plants=[plant], forecast_by_location={"bed": forecast})
    recs = RuleEngine().generate(ctx)
    assert any(r.action == "water" for r in recs)

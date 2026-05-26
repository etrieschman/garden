"""Coverage for the care-profile engine: bundle resolution + per-check rules."""

from datetime import UTC, datetime, timedelta

from garden.domain import (
    Event,
    EventType,
    Plant,
    PlantStatus,
    Taxon,
)
from garden.domain.location import Location, LocationKind
from garden.providers.weather import WeatherSample
from garden.recommendations import CareProfileBundle, GardenContext
from garden.recommendations.care_profile import (
    _check_fertilize,
    _check_frost,
    _check_water,
)

TOMATO = Taxon(id="t1", scientific_name="Solanum lycopersicum", common_name="Tomato")


def _ctx(
    plant: Plant,
    taxon: Taxon = TOMATO,
    events: list[Event] | None = None,
    forecast: list[WeatherSample] | None = None,
    now: datetime | None = None,
) -> GardenContext:
    now = now or datetime(2026, 7, 15, 12, tzinfo=UTC)
    location = Location(id="bed", name="bed", kind=LocationKind.RAISED_BED)
    return GardenContext(
        now=now,
        plants=[plant],
        locations={"bed": location},
        taxa={taxon.id: taxon},
        events_by_plant={plant.id: events or []},
        forecast_by_location={"bed": forecast or []},
    )


def _plant() -> Plant:
    return Plant(
        id="gem-1", taxon_id="t1", location_id="bed", status=PlantStatus.TRANSPLANTED
    )


# ---------- bundle resolution ----------


def test_load_default_bundle_includes_tomato() -> None:
    bundle = CareProfileBundle.load_default()
    tomato = bundle.resolve("Solanum lycopersicum")
    assert tomato is not None
    assert tomato.water is not None
    assert tomato.frost is not None and tomato.frost.min_safe_temp_c == 5
    assert tomato.fertilize is not None


def test_cultivar_override_merges_with_species_default() -> None:
    bundle = CareProfileBundle.load_default()
    species = bundle.resolve("Solanum lycopersicum")
    gem = bundle.resolve("Solanum lycopersicum", "Garden Gem")
    assert species is not None and gem is not None
    assert species.water is not None and gem.water is not None
    assert gem.water.days_between_normal == 4         # cultivar override
    assert species.water.days_between_normal == 5     # species default
    assert gem.water.days_between_hot == species.water.days_between_hot  # inherited
    assert gem.frost == species.frost                 # inherited (cultivar didn't set)
    assert gem.fertilize == species.fertilize         # inherited


# ---------- water ----------


def test_water_fires_when_overdue() -> None:
    profile = CareProfileBundle.load_default().resolve("Solanum lycopersicum")
    assert profile is not None
    now = datetime(2026, 7, 15, 12, tzinfo=UTC)
    last_water = Event(
        type=EventType.WATERED, plant_id="gem-1", occurred_at=now - timedelta(days=7)
    )
    recs = _check_water(_plant(), TOMATO, profile, _ctx(_plant(), events=[last_water], now=now))
    assert len(recs) == 1 and recs[0].action == "water"
    assert "7d since last water" in recs[0].reason


def test_water_silent_when_recently_watered() -> None:
    profile = CareProfileBundle.load_default().resolve("Solanum lycopersicum")
    assert profile is not None
    now = datetime(2026, 7, 15, 12, tzinfo=UTC)
    last_water = Event(
        type=EventType.WATERED, plant_id="gem-1", occurred_at=now - timedelta(days=2)
    )
    recs = _check_water(_plant(), TOMATO, profile, _ctx(_plant(), events=[last_water], now=now))
    assert recs == []


def test_water_significant_rain_resets_clock() -> None:
    profile = CareProfileBundle.load_default().resolve("Solanum lycopersicum")
    assert profile is not None
    now = datetime(2026, 7, 15, 12, tzinfo=UTC)
    last_water = Event(
        type=EventType.WATERED, plant_id="gem-1", occurred_at=now - timedelta(days=10)
    )
    forecast = [
        WeatherSample(timestamp=now - timedelta(days=2), rain_mm=15.0, temp_c_mean=20.0)
    ]
    recs = _check_water(
        _plant(), TOMATO, profile, _ctx(_plant(), events=[last_water], forecast=forecast, now=now)
    )
    assert recs == []  # rain >= 10mm counted as a watering


def test_water_uses_hot_cadence_when_forecast_hot() -> None:
    profile = CareProfileBundle.load_default().resolve("Solanum lycopersicum")
    assert profile is not None
    now = datetime(2026, 7, 15, 12, tzinfo=UTC)
    # 4 days under normal (5d) cadence — silent — but over hot (3d) cadence — fires
    last_water = Event(
        type=EventType.WATERED, plant_id="gem-1", occurred_at=now - timedelta(days=4)
    )
    hot_forecast = [
        WeatherSample(timestamp=now + timedelta(days=i), temp_c_max=32.0)
        for i in range(7)
    ]
    recs = _check_water(
        _plant(), TOMATO, profile, _ctx(_plant(), events=[last_water], forecast=hot_forecast, now=now)
    )
    assert len(recs) == 1
    assert "hot cadence" in recs[0].reason


# ---------- frost ----------


def test_frost_fires_for_tender_plant_with_cold_forecast() -> None:
    profile = CareProfileBundle.load_default().resolve("Solanum lycopersicum")
    assert profile is not None
    now = datetime(2026, 5, 25, 12, tzinfo=UTC)
    forecast = [WeatherSample(timestamp=now + timedelta(days=1), temp_c_min=2.0)]
    recs = _check_frost(_plant(), TOMATO, profile, _ctx(_plant(), forecast=forecast, now=now))
    assert len(recs) == 1 and recs[0].action == "cover-for-frost"


def test_frost_silent_for_hardy_lettuce_with_light_frost() -> None:
    profile = CareProfileBundle.load_default().resolve("Lactuca sativa")
    assert profile is not None and profile.frost is not None
    assert profile.frost.min_safe_temp_c is not None and profile.frost.min_safe_temp_c <= 0
    now = datetime(2026, 4, 5, 12, tzinfo=UTC)
    lettuce_taxon = Taxon(id="t2", scientific_name="Lactuca sativa", common_name="Lettuce")
    plant = Plant(id="lettuce-1", taxon_id="t2", location_id="bed", status=PlantStatus.TRANSPLANTED)
    # forecast min -1°C — above lettuce's threshold (-2)
    forecast = [WeatherSample(timestamp=now + timedelta(days=1), temp_c_min=-1.0)]
    recs = _check_frost(plant, lettuce_taxon, profile, _ctx(plant, lettuce_taxon, forecast=forecast, now=now))
    assert recs == []


# ---------- fertilize ----------


def test_fertilize_fires_after_first_feed_window() -> None:
    profile = CareProfileBundle.load_default().resolve("Solanum lycopersicum")
    assert profile is not None
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    # transplanted 20 days ago — past the 14-day first-feed window
    transplant = Event(
        type=EventType.TRANSPLANTED, plant_id="gem-1", occurred_at=now - timedelta(days=20)
    )
    recs = _check_fertilize(
        _plant(), TOMATO, profile, _ctx(_plant(), events=[transplant], now=now)
    )
    assert len(recs) == 1 and recs[0].action == "fertilize"


def test_fertilize_silent_during_first_feed_window() -> None:
    profile = CareProfileBundle.load_default().resolve("Solanum lycopersicum")
    assert profile is not None
    now = datetime(2026, 5, 25, 12, tzinfo=UTC)
    transplant = Event(
        type=EventType.TRANSPLANTED, plant_id="gem-1", occurred_at=now - timedelta(days=5)
    )
    recs = _check_fertilize(
        _plant(), TOMATO, profile, _ctx(_plant(), events=[transplant], now=now)
    )
    assert recs == []

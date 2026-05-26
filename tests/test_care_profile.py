"""Coverage for the care-profile engine: bundle resolution, GDD, stages, due_at."""

from datetime import UTC, datetime, timedelta

from garden.domain import (
    Event,
    EventType,
    Observation,
    Plant,
    PlantStatus,
    Taxon,
)
from garden.domain.enums import AmendmentUnit
from garden.domain.location import Location, LocationKind
from garden.providers.weather import WeatherSample
from garden.recommendations import CareProfileBundle, GardenContext
from garden.recommendations.amendments import AmendmentCatalog
from garden.recommendations.care_profile import (
    _check_fertilize,
    _check_frost,
    _check_water,
    current_stage,
)
from garden.services.gdd import gdd_since

CATALOG = AmendmentCatalog.load_default()

TOMATO = Taxon(id="t1", scientific_name="Solanum lycopersicum", common_name="Tomato")
NOW = datetime(2026, 7, 15, 12, tzinfo=UTC)


def _ctx(
    plant: Plant,
    taxon: Taxon = TOMATO,
    events: list[Event] | None = None,
    forecast: list[WeatherSample] | None = None,
    observations: list[Observation] | None = None,
    now: datetime = NOW,
    location_kind: LocationKind = LocationKind.RAISED_BED,
) -> GardenContext:
    location = Location(id="bed", name="bed", kind=location_kind)
    return GardenContext(
        now=now,
        plants=[plant],
        locations={"bed": location},
        taxa={taxon.id: taxon},
        events_by_plant={plant.id: events or []},
        forecast_by_location={"bed": forecast or []},
        observations_by_location={"bed": observations or []},
    )


def _plant() -> Plant:
    return Plant(
        id="gem-1", taxon_id="t1", location_id="bed", status=PlantStatus.TRANSPLANTED
    )


def _temp_obs(date: datetime, mean_c: float) -> Observation:
    return Observation(
        metric="temp_c_mean",
        value_numeric=mean_c,
        unit="C",
        occurred_at=date,
        location_id="bed",
        source="provider:test",
    )


# ---------- bundle resolution ----------


def test_load_default_bundle_includes_tomato() -> None:
    bundle = CareProfileBundle.load_default()
    tomato = bundle.resolve("Solanum lycopersicum")
    assert tomato is not None
    assert tomato.gdd is not None and tomato.gdd.base_temp_c == 10
    assert tomato.water is not None
    assert tomato.frost is not None and tomato.frost.min_safe_temp_c == 5
    assert tomato.fertilize is not None and len(tomato.fertilize.stages) == 4


def test_cultivar_override_merges_with_species_default() -> None:
    bundle = CareProfileBundle.load_default()
    species = bundle.resolve("Solanum lycopersicum")
    gem = bundle.resolve("Solanum lycopersicum", "Garden Gem")
    assert species is not None and gem is not None
    assert species.water is not None and gem.water is not None
    assert gem.water.days_between_normal == 4         # cultivar override
    assert species.water.days_between_normal == 5
    assert gem.water.days_between_hot == species.water.days_between_hot  # inherited
    assert gem.frost == species.frost
    assert gem.fertilize == species.fertilize


# ---------- GDD math ----------


def test_gdd_skips_cold_days_and_sums_above_base() -> None:
    since = datetime(2026, 6, 1, tzinfo=UTC)
    now = datetime(2026, 6, 5, tzinfo=UTC)
    obs = [
        _temp_obs(datetime(2026, 6, 1, tzinfo=UTC), 5),    # below base 10 → 0
        _temp_obs(datetime(2026, 6, 2, tzinfo=UTC), 15),   # +5
        _temp_obs(datetime(2026, 6, 3, tzinfo=UTC), 20),   # +10
        _temp_obs(datetime(2026, 6, 4, tzinfo=UTC), 25),   # +15
    ]
    assert gdd_since(obs, since=since, base_temp_c=10.0, now=now) == 30


def test_gdd_ignores_observations_outside_window() -> None:
    obs = [
        _temp_obs(datetime(2026, 5, 30, tzinfo=UTC), 20),  # before since
        _temp_obs(datetime(2026, 6, 10, tzinfo=UTC), 20),  # after now
        _temp_obs(datetime(2026, 6, 5, tzinfo=UTC), 20),   # in window: +10
    ]
    gdd = gdd_since(
        obs,
        since=datetime(2026, 6, 1, tzinfo=UTC),
        base_temp_c=10.0,
        now=datetime(2026, 6, 7, tzinfo=UTC),
    )
    assert gdd == 10


# ---------- water ----------


def test_water_due_at_set_in_future_when_recently_watered() -> None:
    profile = CareProfileBundle.load_default().resolve("Solanum lycopersicum")
    assert profile is not None
    last_water = Event(
        type=EventType.WATERED, plant_id="gem-1", occurred_at=NOW - timedelta(days=2)
    )
    recs = _check_water(_plant(), TOMATO, profile, _ctx(_plant(), events=[last_water]))
    assert len(recs) == 1
    rec = recs[0]
    assert rec.due_at is not None and rec.due_at > NOW   # future, not yet urgent
    expected_due = (NOW - timedelta(days=2)) + timedelta(days=5)  # cadence 5d
    assert abs((rec.due_at - expected_due).total_seconds()) < 60


def test_water_due_now_when_overdue() -> None:
    profile = CareProfileBundle.load_default().resolve("Solanum lycopersicum")
    assert profile is not None
    last_water = Event(
        type=EventType.WATERED, plant_id="gem-1", occurred_at=NOW - timedelta(days=7)
    )
    recs = _check_water(_plant(), TOMATO, profile, _ctx(_plant(), events=[last_water]))
    assert len(recs) == 1 and recs[0].due_at is not None
    assert recs[0].due_at < NOW  # overdue
    assert "7d since last water" in recs[0].reason


def test_water_significant_rain_pushes_due_at_forward() -> None:
    profile = CareProfileBundle.load_default().resolve("Solanum lycopersicum")
    assert profile is not None
    last_water = Event(
        type=EventType.WATERED, plant_id="gem-1", occurred_at=NOW - timedelta(days=10)
    )
    forecast = [WeatherSample(timestamp=NOW - timedelta(days=2), rain_mm=15.0, temp_c_mean=20.0)]
    recs = _check_water(
        _plant(), TOMATO, profile, _ctx(_plant(), events=[last_water], forecast=forecast)
    )
    assert len(recs) == 1
    # Effective last water = 2 days ago (the rain); due = 2 days ago + 5d = 3 days from now
    assert recs[0].due_at is not None and recs[0].due_at > NOW


def test_water_uses_hot_cadence_when_forecast_hot() -> None:
    profile = CareProfileBundle.load_default().resolve("Solanum lycopersicum")
    assert profile is not None
    last_water = Event(
        type=EventType.WATERED, plant_id="gem-1", occurred_at=NOW - timedelta(days=4)
    )
    hot_forecast = [
        WeatherSample(timestamp=NOW + timedelta(days=i), temp_c_max=32.0) for i in range(7)
    ]
    recs = _check_water(
        _plant(), TOMATO, profile, _ctx(_plant(), events=[last_water], forecast=hot_forecast)
    )
    # 4 days since last water; hot cadence is 3d → due was 1 day ago
    assert len(recs) == 1 and recs[0].due_at is not None
    assert recs[0].due_at < NOW
    assert "hot cadence" in recs[0].reason


# ---------- frost ----------


def test_frost_fires_for_tender_plant_with_cold_forecast() -> None:
    profile = CareProfileBundle.load_default().resolve("Solanum lycopersicum")
    assert profile is not None
    now = datetime(2026, 5, 25, 12, tzinfo=UTC)
    forecast = [WeatherSample(timestamp=now + timedelta(days=1), temp_c_min=2.0)]
    recs = _check_frost(_plant(), TOMATO, profile, _ctx(_plant(), forecast=forecast, now=now))
    assert len(recs) == 1
    assert recs[0].action == "cover-for-frost"
    assert recs[0].due_at == now + timedelta(days=1)


# ---------- fertilize: stage-aware ----------


def test_fertilize_silent_in_establishing_stage() -> None:
    """Just transplanted, GDD < 100 → establishing stage, skip=true → silent."""
    profile = CareProfileBundle.load_default().resolve("Solanum lycopersicum")
    assert profile is not None
    transplant = Event(
        type=EventType.TRANSPLANTED, plant_id="gem-1", occurred_at=NOW - timedelta(days=3)
    )
    obs = [_temp_obs(NOW - timedelta(days=i), 20) for i in range(1, 4)]
    recs = _check_fertilize(
        _plant(), TOMATO, profile, _ctx(_plant(), events=[transplant], observations=obs), CATALOG
    )
    assert recs == []


def test_fertilize_fires_in_vegetative_stage_with_no_prior_feed() -> None:
    """20 days at 20C → GDD ≈ 200 → vegetative stage; zero nutrients applied →
    nutrient-balance check fires with a deficit."""
    profile = CareProfileBundle.load_default().resolve("Solanum lycopersicum")
    assert profile is not None
    transplant = Event(
        type=EventType.TRANSPLANTED, plant_id="gem-1", occurred_at=NOW - timedelta(days=20)
    )
    obs = [_temp_obs(NOW - timedelta(days=i), 20) for i in range(1, 21)]
    recs = _check_fertilize(
        _plant(), TOMATO, profile, _ctx(_plant(), events=[transplant], observations=obs), CATALOG
    )
    assert len(recs) == 1
    assert "vegetative" in recs[0].reason.lower()
    assert "deficit" in recs[0].reason.lower()
    assert recs[0].due_at is not None


def test_fertilize_quiet_when_recently_fed_enough_n() -> None:
    """Plant in vegetative stage with a recent fertilizer event covering the deficit
    should be silent."""
    profile = CareProfileBundle.load_default().resolve("Solanum lycopersicum")
    assert profile is not None
    transplant = Event(
        type=EventType.TRANSPLANTED, plant_id="gem-1", occurred_at=NOW - timedelta(days=20)
    )
    # 50g of 10-10-10 = 5g N applied yesterday → more than enough to clear vegetative deficit
    fert = Event(
        type=EventType.FERTILIZED,
        plant_id="gem-1",
        occurred_at=NOW - timedelta(days=1),
        details={
            "type": "balanced_10_10_10",
            "quantity": 50.0,
            "unit": AmendmentUnit.G.value,
        },
    )
    obs = [_temp_obs(NOW - timedelta(days=i), 20) for i in range(1, 21)]
    recs = _check_fertilize(
        _plant(), TOMATO, profile,
        _ctx(_plant(), events=[transplant, fert], observations=obs),
        CATALOG,
    )
    assert recs == []


def test_fertilize_uses_container_multiplier_for_target() -> None:
    """Container plants need *more* N per week (target × multiplier); same applied
    N → larger deficit → still fires when the same scenario in raised_bed wouldn't."""
    profile = CareProfileBundle.load_default().resolve("Solanum lycopersicum")
    assert profile is not None
    transplant = Event(
        type=EventType.TRANSPLANTED, plant_id="gem-1", occurred_at=NOW - timedelta(days=20)
    )
    obs = [_temp_obs(NOW - timedelta(days=i), 20) for i in range(1, 21)]
    recs = _check_fertilize(
        _plant(),
        TOMATO,
        profile,
        _ctx(
            _plant(),
            events=[transplant],
            observations=obs,
            location_kind=LocationKind.CONTAINER,
        ),
        CATALOG,
    )
    assert len(recs) == 1
    assert "container modifier" in recs[0].reason


# ---------- garden show helpers ----------


def test_current_stage_returns_stage_and_gdd() -> None:
    profile = CareProfileBundle.load_default().resolve("Solanum lycopersicum")
    assert profile is not None
    transplant = Event(
        type=EventType.TRANSPLANTED, plant_id="gem-1", occurred_at=NOW - timedelta(days=20)
    )
    obs = [_temp_obs(NOW - timedelta(days=i), 20) for i in range(1, 21)]
    stage, gdd = current_stage(
        _plant(), profile, _ctx(_plant(), events=[transplant], observations=obs)
    )
    assert stage is not None and stage.name == "vegetative"
    assert gdd is not None and 190 < gdd < 210

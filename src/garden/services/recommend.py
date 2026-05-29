"""Recommendation orchestrator. Builds context, runs engines, persists results."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from garden.domain import Event, Recommendation
from garden.providers.weather import WeatherProvider, WeatherSample
from garden.recommendations.base import GardenContext, RecommendationEngine
from garden.storage.base import Storage


def build_context(
    storage: Storage,
    *,
    weather: WeatherProvider | None = None,
    now: datetime | None = None,
    forecast_days: int = 5,
    history_days: int = 30,
) -> GardenContext:
    now = now or datetime.now(UTC)
    # Terminal plants get no recommendations — filtering at the context layer
    # means every engine downstream sees only living plants.
    plants = [p for p in storage.list_plants() if p.is_alive]
    locations = {loc.id: loc for loc in storage.list_locations()}
    taxa = {t.id: t for t in storage.list_taxa()}
    obs_by_loc: dict[str, list] = {}
    for loc_id in locations:
        obs_by_loc[loc_id] = storage.list_observations(location_id=loc_id)

    events_by_plant: dict[str, list[Event]] = {}
    history_since = now - timedelta(days=history_days)
    for plant in plants:
        events_by_plant[plant.id] = storage.list_events(
            plant_id=plant.id, since=history_since
        )

    bed_events_by_location: dict[str, list[Event]] = {}
    for loc_id in locations:
        all_at_loc = storage.list_events(location_id=loc_id, since=history_since)
        bed_events_by_location[loc_id] = [e for e in all_at_loc if e.plant_id is None]

    forecast_by_location: dict[str, list[WeatherSample]] = {}
    if weather is not None:
        start: date = (now - timedelta(days=3)).date()
        end: date = (now + timedelta(days=forecast_days)).date()
        for loc in locations.values():
            if loc.lat is None or loc.lon is None:
                continue
            try:
                forecast_by_location[loc.id] = weather.daily(loc.lat, loc.lon, start, end)
            except Exception:
                # Bad network shouldn't break recommendations entirely
                forecast_by_location[loc.id] = []

    return GardenContext(
        now=now,
        plants=plants,
        locations=locations,
        taxa=taxa,
        events_by_plant=events_by_plant,
        bed_events_by_location=bed_events_by_location,
        observations_by_location=obs_by_loc,
        forecast_by_location=forecast_by_location,
    )


def run_engines(
    engines: list[RecommendationEngine], ctx: GardenContext
) -> list[Recommendation]:
    """Run every engine; dedupe by (plant_id, action), keeping highest confidence."""
    raw: list[Recommendation] = []
    for engine in engines:
        raw.extend(engine.generate(ctx))

    by_key: dict[tuple[str | None, str], Recommendation] = {}
    for rec in raw:
        key = (rec.plant_id, rec.action)
        if key not in by_key or rec.confidence > by_key[key].confidence:
            by_key[key] = rec
    return list(by_key.values())


def refresh_recommendations(
    storage: Storage,
    engines: list[RecommendationEngine],
    weather: WeatherProvider | None = None,
) -> list[Recommendation]:
    ctx = build_context(storage, weather=weather)
    recs = run_engines(engines, ctx)
    # Replace, not accumulate: each `garden recommend` produces a fresh snapshot.
    # Dismissed recs are preserved so we don't re-suggest things you said no to.
    storage.clear_undismissed_recommendations()
    for rec in recs:
        storage.create_recommendation(rec)
    return recs

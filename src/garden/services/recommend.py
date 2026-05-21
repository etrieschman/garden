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
    now = now or datetime.now(UTC).replace(tzinfo=None)
    plants = storage.list_plants()
    locations = {loc.id: loc for loc in storage.list_locations()}
    taxa = {t.id: t for t in storage.list_taxa()}

    events_by_plant: dict[str, list[Event]] = {}
    history_since = now - timedelta(days=history_days)
    for plant in plants:
        events_by_plant[plant.id] = storage.list_events(
            plant_id=plant.id, since=history_since
        )

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
    for rec in recs:
        storage.create_recommendation(rec)
    return recs

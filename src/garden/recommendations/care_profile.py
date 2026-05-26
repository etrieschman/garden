"""Care-profile-driven recommendation engine.

Looks up each plant's species (with optional cultivar override) in the bundled
care-profiles registry, then emits recommendations based on the plant's recent
events and the location's weather forecast.

Replaces the old hand-coded RuleEngine: water, frost, and fertilizer rules
are now per-species data instead of generic Python thresholds.

Plants without a profile get no recommendations from this engine. Add a profile
in `data/care_profiles.yaml` to fix that.
"""

from __future__ import annotations

from datetime import timedelta

from garden.domain import EventType, Plant, Recommendation, Taxon
from garden.recommendations.base import GardenContext
from garden.recommendations.profiles import CareProfile, CareProfileBundle


class CareProfileEngine:
    name = "care-profile"

    def __init__(self, bundle: CareProfileBundle | None = None) -> None:
        self.bundle = bundle or CareProfileBundle.load_default()

    def generate(self, ctx: GardenContext) -> list[Recommendation]:
        recs: list[Recommendation] = []
        for plant in ctx.plants:
            taxon = ctx.taxa.get(plant.taxon_id)
            if not taxon:
                continue
            profile = self.bundle.resolve(taxon.scientific_name, taxon.cultivar)
            if not profile:
                continue
            recs.extend(_check_water(plant, taxon, profile, ctx))
            recs.extend(_check_frost(plant, taxon, profile, ctx))
            recs.extend(_check_fertilize(plant, taxon, profile, ctx))
        return recs


# ---------- individual checks (top-level for testability) ----------


def _check_water(
    plant: Plant, taxon: Taxon, profile: CareProfile, ctx: GardenContext
) -> list[Recommendation]:
    if not profile.water or not plant.location_id:
        return []

    events = ctx.events_by_plant.get(plant.id, [])
    water_dates = [e.occurred_at for e in events if e.type == EventType.WATERED]
    last_water = max(water_dates, default=None)

    forecast = ctx.forecast_by_location.get(plant.location_id, [])
    past_rain = [
        s.timestamp
        for s in forecast
        if s.timestamp <= ctx.now
        and s.rain_mm is not None
        and s.rain_mm >= profile.water.significant_rain_mm
    ]
    last_rain = max(past_rain, default=None)

    candidates = [d for d in (last_water, last_rain) if d is not None]
    effective_last = max(candidates) if candidates else None

    # Pick cadence based on forecast heat (next 7 days)
    upcoming = [s for s in forecast if s.timestamp > ctx.now][:7]
    max_upcoming = max(
        (s.temp_c_max for s in upcoming if s.temp_c_max is not None),
        default=None,
    )
    hot = max_upcoming is not None and max_upcoming > profile.water.hot_temp_threshold_c
    days_between = profile.water.days_between_hot if hot else profile.water.days_between_normal

    if effective_last is None:
        days_since: float = 999.0
    else:
        days_since = (ctx.now - effective_last).total_seconds() / 86400

    if days_since < days_between:
        return []

    parts: list[str] = []
    if effective_last is None:
        parts.append("no watering or significant rain recorded yet")
    else:
        last_kind = "water" if last_water == effective_last else "rain"
        parts.append(
            f"{int(days_since)}d since last {last_kind} "
            f"(threshold ≥{profile.water.significant_rain_mm}mm rain counts)"
        )
    parts.append(f"{taxon.display_name} wants water every {days_between}d")
    if hot:
        parts.append(f"forecast max {max_upcoming:.0f}°C — hot cadence")
    if profile.sources:
        parts.append(profile.sources[0])

    return [
        Recommendation(
            plant_id=plant.id,
            location_id=plant.location_id,
            action="water",
            reason=". ".join(parts) + ".",
            engine="care-profile",
            confidence=0.9,
        )
    ]


def _check_frost(
    plant: Plant, taxon: Taxon, profile: CareProfile, ctx: GardenContext
) -> list[Recommendation]:
    if not profile.frost or profile.frost.min_safe_temp_c is None or not plant.location_id:
        return []
    forecast = ctx.forecast_by_location.get(plant.location_id, [])
    next_3d = [s for s in forecast if 0 <= (s.timestamp - ctx.now).days <= 2]
    risky = [
        s
        for s in next_3d
        if s.temp_c_min is not None and s.temp_c_min <= profile.frost.min_safe_temp_c
    ]
    if not risky:
        return []
    soonest = min(risky, key=lambda s: s.timestamp)
    return [
        Recommendation(
            plant_id=plant.id,
            location_id=plant.location_id,
            action="cover-for-frost",
            reason=(
                f"Forecast low {soonest.temp_c_min:.0f}°C on {soonest.timestamp.date()}; "
                f"{taxon.display_name} needs protection below {profile.frost.min_safe_temp_c}°C."
            ),
            engine="care-profile",
            confidence=0.95,
            valid_until=soonest.timestamp + timedelta(days=1),
        )
    ]


def _check_fertilize(
    plant: Plant, taxon: Taxon, profile: CareProfile, ctx: GardenContext
) -> list[Recommendation]:
    if not profile.fertilize:
        return []
    events = ctx.events_by_plant.get(plant.id, [])
    transplants = [e.occurred_at for e in events if e.type == EventType.TRANSPLANTED]
    if not transplants:
        return []  # no anchor to schedule from

    fertilizes = [e.occurred_at for e in events if e.type == EventType.FERTILIZED]
    if fertilizes:
        last = max(fertilizes)
        due = last + timedelta(days=profile.fertilize.interval_days)
        cadence_label = f"every {profile.fertilize.interval_days}d"
    else:
        last = max(transplants)
        due = last + timedelta(days=profile.fertilize.first_feed_days_after_transplant)
        cadence_label = (
            f"first feed {profile.fertilize.first_feed_days_after_transplant}d after transplant"
        )

    if ctx.now < due:
        return []

    days_overdue = (ctx.now - due).days
    parts: list[str] = [f"Due {due.date()}"]
    if days_overdue > 0:
        parts.append(f"{days_overdue}d overdue")
    parts.append(cadence_label)
    if profile.fertilize.preferred:
        parts.append(f"prefers: {profile.fertilize.preferred}")
    if profile.sources:
        parts.append(profile.sources[0])
    return [
        Recommendation(
            plant_id=plant.id,
            location_id=plant.location_id,
            action="fertilize",
            reason=". ".join(parts) + ".",
            engine="care-profile",
            confidence=0.85,
            valid_after=due,
        )
    ]

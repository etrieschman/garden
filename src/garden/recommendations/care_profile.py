"""Care-profile-driven recommendation engine.

Looks up each plant's species (with optional cultivar override) in the bundled
care-profiles registry, then emits recommendations based on:
  - the plant's recent events (last water, last fertilizer, transplant date)
  - the location's weather forecast (rain ≥ threshold counts as watering;
    forecast heat picks the hot vs normal cadence)
  - cumulative GDD since transplant (for growth-stage-aware fertilizer rules)

Every emitted Recommendation has a `due_at` so callers can show a timeline
("today / in 3 days / next week") rather than just "now."

Plants without a profile get no recommendations from this engine.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from garden.domain import EventType, LocationKind, Plant, Recommendation, Taxon
from garden.recommendations.base import GardenContext
from garden.recommendations.profiles import (
    CareProfile,
    CareProfileBundle,
    FertilizeStage,
)
from garden.services.gdd import gdd_since

# Locations that drain/leach faster get the container_multiplier applied.
_CONTAINER_KINDS = {LocationKind.CONTAINER, LocationKind.INDOOR, LocationKind.SEED_TRAY}


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


# ---------- public helpers (used by `garden show <plant>`) ----------


def current_stage(
    plant: Plant, profile: CareProfile, ctx: GardenContext
) -> tuple[FertilizeStage | None, float | None]:
    """Return (current_stage, gdd_since_transplant) — both None if undetermined."""
    if not profile.fertilize or not profile.fertilize.stages:
        return None, None
    transplant = _last_transplant(plant, ctx)
    if not transplant:
        return None, None
    if not plant.location_id:
        return None, None
    observations = ctx.observations_by_location.get(plant.location_id, [])
    base = profile.gdd.base_temp_c if profile.gdd else 10.0
    gdd = gdd_since(observations, since=transplant, base_temp_c=base, now=ctx.now)
    stage = _stage_for_gdd(profile.fertilize.stages, gdd)
    return stage, gdd


# ---------- individual checks ----------


def _check_water(
    plant: Plant, taxon: Taxon, profile: CareProfile, ctx: GardenContext
) -> list[Recommendation]:
    if not profile.water or not plant.location_id:
        return []

    events = ctx.events_by_plant.get(plant.id, [])
    water_dates = [e.occurred_at for e in events if e.type == EventType.WATERED]
    last_water = max(water_dates, default=None)

    forecast = ctx.forecast_by_location.get(plant.location_id, [])
    past_rain_dates = [
        s.timestamp
        for s in forecast
        if s.timestamp <= ctx.now
        and s.rain_mm is not None
        and s.rain_mm >= profile.water.significant_rain_mm
    ]
    last_rain = max(past_rain_dates, default=None)

    candidates = [d for d in (last_water, last_rain) if d is not None]
    effective_last = max(candidates) if candidates else None

    upcoming = [s for s in forecast if s.timestamp > ctx.now][:7]
    max_upcoming = max(
        (s.temp_c_max for s in upcoming if s.temp_c_max is not None),
        default=None,
    )
    hot = max_upcoming is not None and max_upcoming > profile.water.hot_temp_threshold_c
    days_between = profile.water.days_between_hot if hot else profile.water.days_between_normal

    if effective_last is None:
        due_at = ctx.now
        reason_lead = "no watering or significant rain on record"
    else:
        due_at = effective_last + timedelta(days=days_between)
        days_since = (ctx.now - effective_last).total_seconds() / 86400
        last_kind = "water" if last_water == effective_last else "rain"
        reason_lead = (
            f"{days_since:.0f}d since last {last_kind} "
            f"(≥{profile.water.significant_rain_mm:g}mm rain counts)"
        )

    parts = [reason_lead, f"{taxon.display_name} wants water every {days_between}d"]
    if hot and max_upcoming is not None:
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
            due_at=due_at,
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
                f"{taxon.display_name} needs protection below "
                f"{profile.frost.min_safe_temp_c:g}°C."
            ),
            engine="care-profile",
            confidence=0.95,
            due_at=soonest.timestamp,
            valid_until=soonest.timestamp + timedelta(days=1),
        )
    ]


def _check_fertilize(
    plant: Plant, taxon: Taxon, profile: CareProfile, ctx: GardenContext
) -> list[Recommendation]:
    if not profile.fertilize or not profile.fertilize.stages:
        return []
    transplant_date = _last_transplant(plant, ctx)
    if not transplant_date or not plant.location_id:
        return []

    base_temp = profile.gdd.base_temp_c if profile.gdd else 10.0
    observations = ctx.observations_by_location.get(plant.location_id, [])
    gdd = gdd_since(observations, since=transplant_date, base_temp_c=base_temp, now=ctx.now)
    stage = _stage_for_gdd(profile.fertilize.stages, gdd)
    if stage is None or stage.skip:
        return []

    # Container kinds need feeds more frequently
    multiplier = _container_multiplier(plant, ctx, profile)
    effective_cadence = max(1, round(stage.cadence_days / multiplier))

    events = ctx.events_by_plant.get(plant.id, [])
    fertilizes_after_transplant = [
        e.occurred_at
        for e in events
        if e.type == EventType.FERTILIZED and e.occurred_at >= transplant_date
    ]
    if fertilizes_after_transplant:
        last_fert = max(fertilizes_after_transplant)
        due_at = last_fert + timedelta(days=effective_cadence)
    else:
        # First feed of this stage: due as soon as the (non-skip) stage was reached.
        # We approximate stage entry as "now" if we just crossed into it.
        due_at = ctx.now

    parts: list[str] = [
        f"{stage.name.replace('_', ' ').capitalize()} stage (GDD {gdd:.0f} "
        f"since transplant {(ctx.now - transplant_date).days}d ago)"
    ]
    if fertilizes_after_transplant:
        days_since = (ctx.now - last_fert).total_seconds() / 86400
        parts.append(f"last feed {days_since:.0f}d ago; cadence {effective_cadence}d")
    else:
        parts.append(f"no feed yet in this stage; cadence {effective_cadence}d")
    if multiplier != 1.0:
        parts.append(f"container modifier ×{multiplier:g}")
    if stage.preferred:
        parts.append(f"prefer: {stage.preferred}")
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
            due_at=due_at,
        )
    ]


# ---------- internals ----------


def _last_transplant(plant: Plant, ctx: GardenContext) -> datetime | None:
    events = ctx.events_by_plant.get(plant.id, [])
    transplants = [e.occurred_at for e in events if e.type == EventType.TRANSPLANTED]
    return max(transplants, default=None)


def _stage_for_gdd(stages: list[FertilizeStage], gdd: float) -> FertilizeStage | None:
    """Pick the first stage whose `until_gdd` exceeds current GDD; the final stage
    has `until_gdd is None` and catches everything afterward."""
    for stage in stages:
        if stage.until_gdd is None or gdd < stage.until_gdd:
            return stage
    return None


def _container_multiplier(
    plant: Plant, ctx: GardenContext, profile: CareProfile
) -> float:
    if not profile.fertilize:
        return 1.0
    location = ctx.locations.get(plant.location_id or "")
    if location is None or location.kind not in _CONTAINER_KINDS:
        return 1.0
    return profile.fertilize.container_multiplier

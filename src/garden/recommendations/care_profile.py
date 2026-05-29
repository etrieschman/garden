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

from garden.domain import (
    INDOOR_LOCATION_KINDS,
    EventType,
    LocationKind,
    Observation,
    Plant,
    Recommendation,
    Taxon,
)
from garden.recommendations.amendments import AmendmentCatalog
from garden.recommendations.base import GardenContext
from garden.recommendations.profiles import (
    CareProfile,
    CareProfileBundle,
    FertilizeStage,
)
from garden.services.gdd import gdd_since
from garden.services.nutrients import NutrientTotals, cumulative_nutrients

# Locations that drain/leach faster get the container_multiplier applied.
_CONTAINER_KINDS = {
    LocationKind.CONTAINER,
    LocationKind.INDOOR,
    LocationKind.SEED_TRAY,
    LocationKind.FLOWER_POT,
}


class CareProfileEngine:
    name = "care-profile"

    def __init__(
        self,
        bundle: CareProfileBundle | None = None,
        amendments: AmendmentCatalog | None = None,
    ) -> None:
        self.bundle = bundle or CareProfileBundle.load_default()
        self.amendments = amendments or AmendmentCatalog.load_default()

    def generate(self, ctx: GardenContext) -> list[Recommendation]:
        recs: list[Recommendation] = []
        for plant in ctx.plants:
            taxon = ctx.taxa.get(plant.taxon_id)
            if not taxon:
                continue
            profile = self.bundle.resolve(taxon.scientific_name, taxon.cultivar)
            if not profile:
                continue
            # Indoor plants (seed tray under a grow light, etc.) get no
            # outdoor-weather recommendations — the gardener controls their
            # water and light directly. Fertilizer is GDD-gated and naturally
            # stays silent indoors (no outdoor temps → no GDD → establishing).
            location = ctx.locations.get(plant.location_id or "")
            if location is not None and location.kind in INDOOR_LOCATION_KINDS:
                continue
            recs.extend(_check_water(plant, taxon, profile, ctx))
            recs.extend(_check_frost(plant, taxon, profile, ctx))
            recs.extend(_check_fertilize(plant, taxon, profile, ctx, self.amendments))
        return recs


# ---------- public helpers (used by `garden show <plant>`) ----------


def plant_available_nutrients(
    plant: Plant,
    ctx: GardenContext,
    catalog: AmendmentCatalog,
    *,
    since: datetime | None = None,
) -> NutrientTotals:
    """Nutrients credited to a single plant since `since`.

    - Plant-direct fertilizer/amend events count in full (you fed *this* plant).
    - Bed-scoped amendments are a shared pool, split evenly across the living
      plants drawing from that bed. Care-profile targets are per-plant, so a
      whole-bed amendment must be apportioned to compare on equal terms. (See
      the module-level discussion in the commit that introduced this.)
    """
    own = cumulative_nutrients(ctx.events_by_plant.get(plant.id, []), catalog, since=since)
    if not plant.location_id:
        return own
    bed_total = cumulative_nutrients(
        ctx.bed_events_by_location.get(plant.location_id, []), catalog, since=since
    )
    share = max(1, _living_plants_in_bed(ctx, plant.location_id))
    return NutrientTotals(
        n_g=own.n_g + bed_total.n_g / share,
        p2o5_g=own.p2o5_g + bed_total.p2o5_g / share,
        k2o_g=own.k2o_g + bed_total.k2o_g / share,
    )


def _living_plants_in_bed(ctx: GardenContext, location_id: str) -> int:
    return sum(
        1
        for p in ctx.plants
        if p.location_id == location_id and p.is_alive
    )


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

    # Watering counts whether logged on the plant directly OR on its bed — a
    # bed watering wets every plant in it (no splitting, unlike nutrients).
    plant_events = ctx.events_by_plant.get(plant.id, [])
    bed_events = ctx.bed_events_by_location.get(plant.location_id, [])
    water_dates = [
        e.occurred_at
        for e in (*plant_events, *bed_events)
        if e.type == EventType.WATERED
    ]
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
    plant: Plant,
    taxon: Taxon,
    profile: CareProfile,
    ctx: GardenContext,
    catalog: AmendmentCatalog,
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

    multiplier = _container_multiplier(plant, ctx, profile)
    events = ctx.events_by_plant.get(plant.id, [])

    # Nutrient-balance mode: stage has explicit per-week N target.
    if stage.target_n_g_per_week is not None:
        return _check_fertilize_by_nutrients(
            plant, taxon, profile, ctx, stage, gdd, observations,
            base_temp, transplant_date, multiplier, catalog,
        )

    # Cadence fallback: stage didn't declare a target.
    return _check_fertilize_by_cadence(
        plant, taxon, profile, ctx, stage, gdd, transplant_date, multiplier, events,
    )


def _check_fertilize_by_nutrients(
    plant: Plant,
    taxon: Taxon,
    profile: CareProfile,
    ctx: GardenContext,
    stage: FertilizeStage,
    gdd: float,
    observations: list[Observation],
    base_temp: float,
    transplant_date: datetime,
    multiplier: float,
    catalog: AmendmentCatalog,
) -> list[Recommendation]:
    stage_start = _stage_start_date(profile, stage, transplant_date, observations, base_temp)
    # Plant-direct events count in full; bed amendments are split per-capita.
    #
    # `since=transplant_date` (not stage_start): slow-release amendments applied
    # at planting time continue mineralizing for weeks. Counting them against
    # the current stage's target is the right honest accounting — they're still
    # feeding the plant. If you heavily amend at transplant, the engine should
    # stay quiet through vegetative; if you starve-prep, it should fire early.
    applied = plant_available_nutrients(plant, ctx, catalog, since=transplant_date)
    weeks_in_stage = max(0.0, (ctx.now - stage_start).total_seconds() / (86400 * 7))
    target = _stage_targets(stage, weeks_in_stage, multiplier)
    deficit_n_g = target.n_g - applied.n_g

    # Below ~0.2 g of N deficit, leave the user alone; that's noise.
    if deficit_n_g < 0.2:
        return []

    # Roughly when will the deficit appear? Now if already past, else later.
    due_at = ctx.now

    parts = [
        f"{stage.name.replace('_', ' ').capitalize()} stage (GDD {gdd:.0f}, "
        f"{(ctx.now - transplant_date).days}d since transplant)",
        f"N applied {applied.n_g:.1f}g vs target {target.n_g:.1f}g over "
        f"{weeks_in_stage:.1f} weeks (deficit {deficit_n_g:.1f}g)",
    ]
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
            confidence=0.9,
            due_at=due_at,
        )
    ]


def _check_fertilize_by_cadence(
    plant: Plant,
    taxon: Taxon,
    profile: CareProfile,
    ctx: GardenContext,
    stage: FertilizeStage,
    gdd: float,
    transplant_date: datetime,
    multiplier: float,
    events: list,
) -> list[Recommendation]:
    effective_cadence = max(1, round(stage.cadence_days / multiplier))
    fertilizes_after_transplant = [
        e.occurred_at
        for e in events
        if e.type == EventType.FERTILIZED and e.occurred_at >= transplant_date
    ]
    if fertilizes_after_transplant:
        last_fert = max(fertilizes_after_transplant)
        due_at = last_fert + timedelta(days=effective_cadence)
    else:
        due_at = ctx.now

    parts = [
        f"{stage.name.replace('_', ' ').capitalize()} stage (GDD {gdd:.0f}, "
        f"{(ctx.now - transplant_date).days}d since transplant)"
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


def _stage_targets(stage: FertilizeStage, weeks: float, multiplier: float) -> NutrientTotals:
    """Cumulative nutrient targets over `weeks`, optionally accelerated for containers."""
    return NutrientTotals(
        n_g=(stage.target_n_g_per_week or 0) * weeks * multiplier,
        p2o5_g=(stage.target_p2o5_g_per_week or 0) * weeks * multiplier,
        k2o_g=(stage.target_k2o_g_per_week or 0) * weeks * multiplier,
    )


def _stage_start_date(
    profile: CareProfile,
    current_stage: FertilizeStage,
    transplant_date: datetime,
    observations: list[Observation],
    base_temp: float,
) -> datetime:
    """When did the current stage begin? At the prior stage's GDD boundary."""
    if not profile.fertilize or not profile.fertilize.stages:
        return transplant_date
    idx = profile.fertilize.stages.index(current_stage)
    if idx == 0:
        return transplant_date
    prior = profile.fertilize.stages[idx - 1]
    if prior.until_gdd is None:
        return transplant_date
    return _gdd_milestone(observations, transplant_date, base_temp, prior.until_gdd) or transplant_date


def _gdd_milestone(
    observations: list[Observation],
    since: datetime,
    base_temp_c: float,
    target_gdd: float,
) -> datetime | None:
    """Date when cumulative GDD first reached `target_gdd`. None if never."""
    total = 0.0
    for obs in sorted(observations, key=lambda o: o.occurred_at):
        if obs.metric != "temp_c_mean" or obs.value_numeric is None or obs.occurred_at < since:
            continue
        total += max(0.0, obs.value_numeric - base_temp_c)
        if total >= target_gdd:
            return obs.occurred_at
    return None


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


def _container_multiplier(plant: Plant, ctx: GardenContext, profile: CareProfile) -> float:
    if not profile.fertilize:
        return 1.0
    location = ctx.locations.get(plant.location_id or "")
    if location is None or location.kind not in _CONTAINER_KINDS:
        return 1.0
    return profile.fertilize.container_multiplier

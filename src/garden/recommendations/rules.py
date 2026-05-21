"""Simple rule-based recommendation engine.

Three starter rules:
- post-transplant fertilizer hold (give roots time to settle)
- dry-spell water recommendation (no rain + no water + warm forecast)
- frost cover-up warning (forecast min temp below threshold)

Rules are intentionally small functions — adding a new one is a one-file edit.
"""

from collections.abc import Callable
from datetime import timedelta

from garden.domain import EventType, Plant, Recommendation
from garden.recommendations.base import GardenContext

Rule = Callable[[Plant, GardenContext], Recommendation | None]


def _post_transplant_fertilizer_hold(plant: Plant, ctx: GardenContext) -> Recommendation | None:
    events = ctx.events_by_plant.get(plant.id, [])
    transplants = [e for e in events if e.type == EventType.TRANSPLANTED]
    if not transplants:
        return None
    most_recent = max(transplants, key=lambda e: e.occurred_at)
    days_since = (ctx.now - most_recent.occurred_at).days
    if days_since >= 14:
        return None
    fertilizes = [e for e in events if e.type == EventType.FERTILIZED and e.occurred_at > most_recent.occurred_at]
    if fertilizes:
        return None
    return Recommendation(
        plant_id=plant.id,
        action="hold-fertilizer",
        reason=(
            f"Recently transplanted ({days_since}d ago). "
            f"Wait until {(most_recent.occurred_at + timedelta(days=14)).date()} "
            f"before first feeding."
        ),
        engine="rules",
        confidence=0.85,
        valid_after=most_recent.occurred_at,
        valid_until=most_recent.occurred_at + timedelta(days=14),
    )


def _dry_spell_water(plant: Plant, ctx: GardenContext) -> Recommendation | None:
    if not plant.location_id:
        return None
    forecast = ctx.forecast_by_location.get(plant.location_id, [])
    today = ctx.now.date()
    past_3d = [s for s in forecast if 0 <= (today - s.timestamp.date()).days <= 2]
    next_2d = [s for s in forecast if 0 <= (s.timestamp.date() - today).days <= 1]
    if not next_2d:
        return None
    rain_3d = sum(s.rain_mm or 0 for s in past_3d)
    max_temp_next_2d = max((s.temp_c_max or 0) for s in next_2d)
    if rain_3d > 5.0 or max_temp_next_2d < 24.0:
        return None
    events = ctx.events_by_plant.get(plant.id, [])
    waters = [e for e in events if e.type == EventType.WATERED]
    if waters:
        last_water = max(waters, key=lambda e: e.occurred_at)
        if (ctx.now - last_water.occurred_at).days < 2:
            return None
    return Recommendation(
        plant_id=plant.id,
        action="water",
        reason=(
            f"Dry conditions: {rain_3d:.1f}mm rain in last 3 days, "
            f"forecast high {max_temp_next_2d:.0f}°C. No recent watering logged."
        ),
        engine="rules",
        confidence=0.7,
    )


def _frost_cover(plant: Plant, ctx: GardenContext) -> Recommendation | None:
    if not plant.location_id:
        return None
    taxon = ctx.taxa.get(plant.taxon_id)
    # frost-sensitive: tomatoes, peppers, basil, cucumber. Hardier crops skip.
    sensitive = {"Solanum lycopersicum", "Capsicum annuum", "Ocimum basilicum", "Cucumis sativus"}
    if not taxon or taxon.scientific_name not in sensitive:
        return None
    forecast = ctx.forecast_by_location.get(plant.location_id, [])
    next_3d = [s for s in forecast if 0 <= (s.timestamp - ctx.now).days <= 2]
    risky = [s for s in next_3d if (s.temp_c_min or 99) <= 5.0]
    if not risky:
        return None
    soonest = min(risky, key=lambda s: s.timestamp)
    return Recommendation(
        plant_id=plant.id,
        action="cover-for-frost",
        reason=(
            f"{taxon.display_name} is frost-sensitive. "
            f"Forecast low {soonest.temp_c_min:.0f}°C on {soonest.timestamp.date()}. "
            "Cover or bring inside."
        ),
        engine="rules",
        confidence=0.95,
        valid_until=soonest.timestamp + timedelta(days=1),
    )


class RuleEngine:
    name = "rules"

    def __init__(self, rules: list[Rule] | None = None) -> None:
        self.rules: list[Rule] = rules or [
            _post_transplant_fertilizer_hold,
            _dry_spell_water,
            _frost_cover,
        ]

    def generate(self, ctx: GardenContext) -> list[Recommendation]:
        out: list[Recommendation] = []
        for plant in ctx.plants:
            for rule in self.rules:
                rec = rule(plant, ctx)
                if rec is not None:
                    out.append(rec)
        return out

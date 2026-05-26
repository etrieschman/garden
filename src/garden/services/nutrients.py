"""Unit conversion + nutrient accounting from events.

Walks `AMENDED` and `FERTILIZED` events, converts each (quantity, unit, type)
to a mass in grams of N / P2O5 / K2O applied, and sums across a time window.

This is the single source of truth for "how much N did I apply to plant X
since transplant?" The recommendation engine and `garden show <plant>` both
consume it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from garden.domain import Event, EventType
from garden.domain.enums import AmendmentUnit
from garden.recommendations.amendments import AmendmentCatalog

# Mass → kg conversion factors. Volume units handled separately (need density).
_MASS_TO_KG: Final[dict[AmendmentUnit, float]] = {
    AmendmentUnit.KG: 1.0,
    AmendmentUnit.G: 0.001,
    AmendmentUnit.LB: 0.45359237,
    AmendmentUnit.OZ: 0.02834952,
}

# Volume → L conversion factors. Need density (kg/L) to reach mass.
_VOLUME_TO_L: Final[dict[AmendmentUnit, float]] = {
    AmendmentUnit.L: 1.0,
    AmendmentUnit.ML: 0.001,
    AmendmentUnit.GAL: 3.78541,         # US gallon
    AmendmentUnit.FL_OZ: 0.0295735,     # US fl oz
    AmendmentUnit.CU_FT: 28.3168,
    AmendmentUnit.CU_YD: 764.555,
    AmendmentUnit.TSP: 0.00492892,      # US tsp
    AmendmentUnit.TBSP: 0.0147868,      # US tbsp
    AmendmentUnit.CUP: 0.236588,        # US cup
}


@dataclass
class NutrientTotals:
    """Grams of N, P2O5, K2O applied. Label values, not elemental P/K."""

    n_g: float = 0.0
    p2o5_g: float = 0.0
    k2o_g: float = 0.0


def to_kg(quantity: float, unit: AmendmentUnit, density_kg_per_l: float | None) -> float | None:
    """Convert (quantity, unit) to kilograms.

    Mass units convert directly. Volume units need `density_kg_per_l`; without
    it the function returns None (signal: "we know the volume but can't compute
    nutrient mass — engine should skip this event for nutrient totals").
    """
    if unit in _MASS_TO_KG:
        return quantity * _MASS_TO_KG[unit]
    if unit in _VOLUME_TO_L:
        if density_kg_per_l is None:
            return None
        return quantity * _VOLUME_TO_L[unit] * density_kg_per_l
    raise ValueError(f"unknown unit: {unit}")


def event_nutrients(event: Event, catalog: AmendmentCatalog) -> NutrientTotals:
    """Extract grams of N / P2O5 / K2O contributed by a single event.

    Reads structured fields out of `event.details`. Missing or unparseable
    fields contribute zero (the event is still kept for the human log).
    """
    if event.type not in (EventType.AMENDED, EventType.FERTILIZED):
        return NutrientTotals()

    details = event.details or {}
    quantity = details.get("quantity")
    unit_raw = details.get("unit")
    type_key = details.get("type")
    if quantity is None or unit_raw is None:
        return NutrientTotals()
    try:
        unit = AmendmentUnit(unit_raw)
    except ValueError:
        return NutrientTotals()

    entry = catalog.get(type_key) if type_key else None
    density = entry.kg_per_l if entry else None

    # Per-event NPK overrides win over the catalog default.
    n_pct = _coerce_float(details.get("n_pct"))
    if n_pct is None and entry:
        n_pct = entry.n_pct
    p2o5_pct = _coerce_float(details.get("p_pct"))
    if p2o5_pct is None and entry:
        p2o5_pct = entry.p2o5_pct
    k2o_pct = _coerce_float(details.get("k_pct"))
    if k2o_pct is None and entry:
        k2o_pct = entry.k2o_pct

    mass_kg = to_kg(quantity, unit, density)
    if mass_kg is None:
        return NutrientTotals()
    mass_g = mass_kg * 1000
    return NutrientTotals(
        n_g=mass_g * (n_pct or 0) / 100,
        p2o5_g=mass_g * (p2o5_pct or 0) / 100,
        k2o_g=mass_g * (k2o_pct or 0) / 100,
    )


def cumulative_nutrients(
    events: list[Event],
    catalog: AmendmentCatalog,
    *,
    since: datetime | None = None,
) -> NutrientTotals:
    totals = NutrientTotals()
    for event in events:
        if since is not None and event.occurred_at < since:
            continue
        each = event_nutrients(event, catalog)
        totals.n_g += each.n_g
        totals.p2o5_g += each.p2o5_g
        totals.k2o_g += each.k2o_g
    return totals


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None

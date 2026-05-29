"""One snapshot, many views.

`get_snapshot()` returns everything the website (`index.qmd`) and the
`garden today` CLI need to render the current state of the garden. Both
surfaces call this; neither reaches into storage internals directly.

Adding a future web/API layer should mean *another* renderer of this
snapshot, not another query path through `Storage`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from garden.domain import (
    INDOOR_LOCATION_KINDS,
    Location,
    Plant,
    Recommendation,
    Taxon,
)
from garden.providers.weather import WeatherProvider
from garden.recommendations.base import RecommendationEngine
from garden.services import recommend
from garden.storage.base import Storage


@dataclass
class GardenSnapshot:
    """A point-in-time view of the garden.

    Built once; rendered many ways. Every list is sorted in display order.
    """

    now: datetime
    locations: list[Location]
    taxa_by_id: dict[str, Taxon]
    outdoor_plants: list[Plant]
    indoor_plants: list[Plant]
    terminal_plants: list[Plant]
    today_actions: list[Recommendation]
    upcoming_actions: list[Recommendation]
    later_actions: list[Recommendation] = field(default_factory=list)


def get_snapshot(
    storage: Storage,
    engines: list[RecommendationEngine],
    *,
    weather: WeatherProvider | None = None,
    now: datetime | None = None,
    upcoming_window_days: int = 7,
) -> GardenSnapshot:
    """Refresh recommendations and bundle them with current plant/bed state.

    `today_actions`: due today or overdue.
    `upcoming_actions`: due within `upcoming_window_days` (exclusive of today).
    `later_actions`: everything else (no due date or beyond the window).
    """
    now = now or datetime.now(UTC)
    locations = storage.list_locations()
    locations_by_id = {loc.id: loc for loc in locations}
    taxa_by_id = {t.id: t for t in storage.list_taxa()}
    all_plants = storage.list_plants()

    alive = [p for p in all_plants if p.is_alive]
    terminal = sorted(
        (p for p in all_plants if not p.is_alive),
        key=lambda p: p.terminal_at or now,
        reverse=True,
    )
    outdoor, indoor = _partition_by_location(alive, locations_by_id)

    recs = recommend.refresh_recommendations(storage, engines, weather=weather)
    today, upcoming, later = _bucket_by_due(recs, now, upcoming_window_days)

    return GardenSnapshot(
        now=now,
        locations=locations,
        taxa_by_id=taxa_by_id,
        outdoor_plants=_sort_plants(outdoor),
        indoor_plants=_sort_plants(indoor),
        terminal_plants=terminal,
        today_actions=today,
        upcoming_actions=upcoming,
        later_actions=later,
    )


def _partition_by_location(
    plants: list[Plant], locations_by_id: dict[str, Location]
) -> tuple[list[Plant], list[Plant]]:
    outdoor: list[Plant] = []
    indoor: list[Plant] = []
    for p in plants:
        if p.location_id is None:
            indoor.append(p)
            continue
        loc = locations_by_id.get(p.location_id)
        if loc is None or loc.kind in INDOOR_LOCATION_KINDS:
            indoor.append(p)
        else:
            outdoor.append(p)
    return outdoor, indoor


def _sort_plants(plants: list[Plant]) -> list[Plant]:
    return sorted(plants, key=lambda p: (p.location_id or "", p.id))


def _bucket_by_due(
    recs: list[Recommendation], now: datetime, window_days: int
) -> tuple[list[Recommendation], list[Recommendation], list[Recommendation]]:
    today_end = now + timedelta(days=1)
    window_end = now + timedelta(days=window_days)
    today: list[Recommendation] = []
    upcoming: list[Recommendation] = []
    later: list[Recommendation] = []
    for r in recs:
        due = r.due_at
        if due is None:
            later.append(r)
        elif due <= today_end:
            today.append(r)
        elif due <= window_end:
            upcoming.append(r)
        else:
            later.append(r)
    today.sort(key=lambda r: r.due_at or now)
    upcoming.sort(key=lambda r: r.due_at or now)
    later.sort(key=lambda r: r.due_at or now + timedelta(days=365))
    return today, upcoming, later

"""Growing Degree Day (GDD) accumulator.

GDD = sum over days of `max(0, daily_mean_temp_c - base_temp_c)`. Each species
has its own base temp (10°C for tomato, 5°C for lettuce, etc.). Cold days
contribute nothing; warm days pile up fast.

Inputs are `Observation` rows with `metric="temp_c_mean"` (populated by
`garden weather`). One observation per day per location.
"""

from __future__ import annotations

from datetime import datetime

from garden.domain import Observation


def gdd_since(
    observations: list[Observation],
    since: datetime,
    base_temp_c: float,
    *,
    now: datetime | None = None,
) -> float:
    """Sum GDD contributions from `temp_c_mean` observations between `since` and `now`.

    `observations` should be all observations for the location (filtering here);
    callers typically pass `storage.list_observations(location_id=..., metric=...)`.
    """
    end = now or datetime.now(since.tzinfo)
    total = 0.0
    for obs in observations:
        if obs.metric != "temp_c_mean":
            continue
        if obs.value_numeric is None:
            continue
        if obs.occurred_at < since or obs.occurred_at > end:
            continue
        total += max(0.0, obs.value_numeric - base_temp_c)
    return total

"""Amendment and fertilizer catalog — densities and NPK defaults.

Loaded from `src/garden/data/amendments.yaml`. Used by the nutrient-accumulator
service to convert (quantity, unit, type) into grams of N / P2O5 / K2O applied.
"""

from __future__ import annotations

from importlib.resources import files
from typing import Self

import yaml
from pydantic import BaseModel, Field


class AmendmentEntry(BaseModel):
    """One amendment / fertilizer in the catalog.

    `npk` is the **label** N-P2O5-K2O percent by mass. To get the nutrient
    available *this season*, multiply by `release_fraction` — synthetic
    granulars and liquid fertilizers release ~100% (`1.0`), composted manures
    and slow-release organics release only ~15-30% in the first year. The
    rest mineralizes over subsequent seasons; the engine ignores that for
    simplicity.
    """

    key: str
    display: str
    kind: str
    kg_per_l: float
    npk: list[float] = Field(min_length=3, max_length=3)
    release_fraction: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of label NPK that mineralizes this season. "
            "1.0 = full availability (synthetics, liquids); ~0.2 = composted "
            "manure / compost; ~0.8 = blood meal. Applied uniformly to N, P, K — "
            "a simplification (K is usually faster than N or P from organics)."
        ),
    )
    notes: str | None = None
    sources: list[str] = Field(default_factory=list)

    @property
    def n_pct(self) -> float:
        return self.npk[0]

    @property
    def p2o5_pct(self) -> float:
        return self.npk[1]

    @property
    def k2o_pct(self) -> float:
        return self.npk[2]


class AmendmentCatalog(BaseModel):
    entries: list[AmendmentEntry] = Field(default_factory=list)

    def get(self, key: str) -> AmendmentEntry | None:
        for entry in self.entries:
            if entry.key == key:
                return entry
        return None

    def keys(self) -> list[str]:
        return [entry.key for entry in self.entries]

    @classmethod
    def load_default(cls) -> Self:
        text = (files("garden") / "data" / "amendments.yaml").read_text()
        return cls.model_validate(yaml.safe_load(text))

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
    key: str
    display: str
    kind: str
    kg_per_l: float
    npk: list[float] = Field(min_length=3, max_length=3)
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

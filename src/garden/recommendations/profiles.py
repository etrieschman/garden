"""Care-profile schema and bundle loader.

A care profile is per-species (with optional per-cultivar overrides) horticulture
guidance: how often to water, when frost becomes a risk, fertilizer cadence, etc.
Sourced from cooperative-extension publications and seed-catalog data, not USDA
(which is species-level only).

Bundle format lives in `src/garden/data/care_profiles.yaml` — see that file's
header for the schema and editing rules.
"""

from __future__ import annotations

from importlib.resources import files
from typing import Self

import yaml
from pydantic import BaseModel, Field


class WaterProfile(BaseModel):
    days_between_normal: int = 7
    days_between_hot: int = 5
    hot_temp_threshold_c: float = 30.0
    significant_rain_mm: float = 10.0


class FrostProfile(BaseModel):
    min_safe_temp_c: float | None = None  # None => not frost-sensitive


class FertilizeProfile(BaseModel):
    first_feed_days_after_transplant: int = 14
    interval_days: int = 14
    preferred: str | None = None


class CareProfile(BaseModel):
    scientific_name: str
    cultivar: str | None = None
    common_name: str | None = None
    water: WaterProfile | None = None
    frost: FrostProfile | None = None
    fertilize: FertilizeProfile | None = None
    sources: list[str] = Field(default_factory=list)


class CareProfileBundle(BaseModel):
    profiles: list[CareProfile] = Field(default_factory=list)

    def resolve(
        self, scientific_name: str, cultivar: str | None = None
    ) -> CareProfile | None:
        """Look up a profile; cultivar override merges over species default."""
        species_default = self._find(scientific_name, cultivar=None)
        if cultivar:
            override = self._find(scientific_name, cultivar=cultivar)
            if override:
                return _merge(species_default, override)
        return species_default

    def _find(self, scientific_name: str, *, cultivar: str | None) -> CareProfile | None:
        for p in self.profiles:
            if p.scientific_name == scientific_name and p.cultivar == cultivar:
                return p
        return None

    @classmethod
    def load_default(cls) -> Self:
        """Load the bundled care_profiles.yaml shipped with the package."""
        text = (files("garden") / "data" / "care_profiles.yaml").read_text()
        return cls.model_validate(yaml.safe_load(text))


def _merge(base: CareProfile | None, override: CareProfile) -> CareProfile:
    """Field-wise merge: override fields win, but None-valued sections fall back to base."""
    if base is None:
        return override

    def section(b: BaseModel | None, o: BaseModel | None) -> BaseModel | None:
        if o is None:
            return b
        if b is None:
            return o
        # Only fields the override *explicitly set* in YAML win; Pydantic defaults
        # would otherwise silently clobber the species baseline.
        override_set = o.model_dump(exclude_unset=True)
        merged = {**b.model_dump(), **override_set}
        return type(b)(**merged)

    return CareProfile(
        scientific_name=base.scientific_name,
        common_name=override.common_name or base.common_name,
        cultivar=override.cultivar,
        water=section(base.water, override.water),  # type: ignore[arg-type]
        frost=section(base.frost, override.frost),  # type: ignore[arg-type]
        fertilize=section(base.fertilize, override.fertilize),  # type: ignore[arg-type]
        sources=list(base.sources) + list(override.sources),
    )

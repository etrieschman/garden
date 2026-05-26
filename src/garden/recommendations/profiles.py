"""Care-profile schema and bundle loader.

A care profile is per-species (with optional per-cultivar overrides) horticulture
guidance: how often to water, frost tolerance, GDD-driven fertilizer stages.
Sourced from cooperative-extension publications and seed-catalog data.

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


class GDDProfile(BaseModel):
    base_temp_c: float = 10.0


class FertilizeStage(BaseModel):
    """A single growth-stage rule for fertilizing.

    `until_gdd` is the upper boundary: stage applies until cumulative GDD
    (since transplant or seeding) reaches this value. The last stage uses
    `until_gdd: null` to mean "rest of the plant's life."

    Two recommendation modes:
    - If `target_n_g_per_week` is set, the engine does **nutrient-balance**: it
      sums N applied (via amended + fertilized events) since stage entry and
      compares against `target * weeks_in_stage`.
    - Otherwise it falls back to **cadence**: recommend every `cadence_days`.
    """

    name: str
    until_gdd: float | None = None
    skip: bool = False                  # if True, no fertilizer recommendation
    cadence_days: int = 14
    preferred: str | None = None
    target_n_g_per_week: float | None = None
    target_p2o5_g_per_week: float | None = None
    target_k2o_g_per_week: float | None = None


class FertilizeProfile(BaseModel):
    stages: list[FertilizeStage] = Field(default_factory=list)
    container_multiplier: float = 1.5   # multiply cadence by 1/this for containers


class CareProfile(BaseModel):
    scientific_name: str
    cultivar: str | None = None
    common_name: str | None = None
    gdd: GDDProfile | None = None
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
    """Field-wise merge: cultivar's explicitly-set fields win over species defaults."""
    if base is None:
        return override

    def section(b: BaseModel | None, o: BaseModel | None) -> BaseModel | None:
        if o is None:
            return b
        if b is None:
            return o
        override_set = o.model_dump(exclude_unset=True)
        merged = {**b.model_dump(), **override_set}
        return type(b)(**merged)

    return CareProfile(
        scientific_name=base.scientific_name,
        common_name=override.common_name or base.common_name,
        cultivar=override.cultivar,
        gdd=section(base.gdd, override.gdd),  # type: ignore[arg-type]
        water=section(base.water, override.water),  # type: ignore[arg-type]
        frost=section(base.frost, override.frost),  # type: ignore[arg-type]
        fertilize=section(base.fertilize, override.fertilize),  # type: ignore[arg-type]
        sources=list(base.sources) + list(override.sources),
    )

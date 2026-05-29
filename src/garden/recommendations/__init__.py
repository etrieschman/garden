from collections.abc import Callable

from garden.recommendations.base import GardenContext, RecommendationEngine
from garden.recommendations.care_profile import CareProfileEngine
from garden.recommendations.profiles import (
    CareProfile,
    CareProfileBundle,
    FertilizeProfile,
    FrostProfile,
    WaterProfile,
)

# Registry of engine name → factory. To add a new engine, drop its name and
# constructor here; `settings.engines` (list[str]) selects which ones run.
ENGINE_REGISTRY: dict[str, Callable[[], RecommendationEngine]] = {
    "care-profile": CareProfileEngine,
}


def build_engines(names: list[str]) -> list[RecommendationEngine]:
    """Look up each name in `ENGINE_REGISTRY` and instantiate it.

    Raises ValueError on an unknown name so a typo in settings fails loudly.
    """
    out: list[RecommendationEngine] = []
    for name in names:
        factory = ENGINE_REGISTRY.get(name)
        if factory is None:
            known = ", ".join(sorted(ENGINE_REGISTRY))
            raise ValueError(f"unknown engine {name!r}. Known: {known}.")
        out.append(factory())
    return out


__all__ = [
    "ENGINE_REGISTRY",
    "CareProfile",
    "CareProfileBundle",
    "CareProfileEngine",
    "FertilizeProfile",
    "FrostProfile",
    "GardenContext",
    "RecommendationEngine",
    "WaterProfile",
    "build_engines",
]

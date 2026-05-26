from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from garden.domain import Event, Location, Observation, Plant, Recommendation, Taxon
from garden.providers.weather import WeatherSample


@dataclass
class GardenContext:
    """Read-only snapshot passed to every engine.

    The orchestrator builds this once per recommendation run so engines don't
    each have to hit the database.
    """

    now: datetime
    plants: list[Plant]
    locations: dict[str, Location] = field(default_factory=dict)
    taxa: dict[str, Taxon] = field(default_factory=dict)
    events_by_plant: dict[str, list[Event]] = field(default_factory=dict)
    # Bed-scoped events (plant_id is None, location_id matches the bed). These
    # credit every plant in that bed for nutrient accounting (an amendment
    # applied to the whole bed feeds everything growing in it).
    bed_events_by_location: dict[str, list[Event]] = field(default_factory=dict)
    observations_by_location: dict[str, list[Observation]] = field(default_factory=dict)
    forecast_by_location: dict[str, list[WeatherSample]] = field(default_factory=dict)


class RecommendationEngine(Protocol):
    """Pluggable recommendation source.

    Implementations: rule-based, USDA guidelines, ML, anything else. Each is
    independent — orchestrator runs all enabled engines and dedupes by (plant, action).
    """

    name: str

    def generate(self, ctx: GardenContext) -> list[Recommendation]: ...

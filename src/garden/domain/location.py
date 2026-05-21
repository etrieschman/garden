import math
from datetime import date, datetime

from pydantic import BaseModel, Field

from garden._clock import now as _now
from garden.domain.enums import LocationKind


class Dimensions(BaseModel):
    length_cm: int | None = None
    width_cm: int | None = None
    depth_cm: int | None = None
    diameter_cm: int | None = None  # round containers

    @property
    def area_m2(self) -> float | None:
        if self.length_cm and self.width_cm:
            return (self.length_cm * self.width_cm) / 10_000
        if self.diameter_cm:
            return math.pi * (self.diameter_cm / 200) ** 2
        return None

    @property
    def volume_l(self) -> float | None:
        area = self.area_m2
        if area is None or self.depth_cm is None:
            return None
        return area * (self.depth_cm / 100) * 1000


class Substrate(BaseModel):
    medium: str
    components: list[str] = Field(default_factory=list)
    amendments: list[str] = Field(default_factory=list)
    last_refreshed: date | None = None


class Location(BaseModel):
    """A place plants live. Beds, containers, greenhouses, indoor seed trays.

    Hierarchy via `parent_id` (e.g., a bed inside a 'backyard' location).
    Derived fields (hardiness_zone, sun profile) are cached by services, not user-set.
    """

    id: str
    name: str
    kind: LocationKind
    lat: float | None = None
    lon: float | None = None
    dimensions: Dimensions | None = None
    substrate: Substrate | None = None
    parent_id: str | None = None
    hardiness_zone: str | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=_now)

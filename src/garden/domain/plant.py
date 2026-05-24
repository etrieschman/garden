from datetime import UTC, datetime

from pydantic import BaseModel, Field

from garden.domain.enums import PlantStatus


class Plant(BaseModel):
    """A specific plant instance in the garden. One row per plant, not per species."""

    id: str
    taxon_id: str
    location_id: str | None = None
    status: PlantStatus = PlantStatus.SEEDED
    planted_at: datetime | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from garden.domain.enums import PlantStatus


class Plant(BaseModel):
    """A specific plant instance in the garden. One row per plant, not per species.

    `status` is the *lifecycle phase* (seeded → germinated → … → flowering →
    fruiting). "Is this plant still in the garden?" is answered by
    `terminal_at is None`, not by any status value. Legacy rows may still
    carry `status=DEAD/REMOVED` from before the split; new code should read
    `terminal_at` for that question.
    """

    id: str
    taxon_id: str
    location_id: str | None = None
    status: PlantStatus = PlantStatus.SEEDED
    label: str | None = None
    planted_at: datetime | None = None
    terminal_at: datetime | None = None
    terminal_cause: str | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_alive(self) -> bool:
        """Whether the plant is still in the garden."""
        return self.terminal_at is None

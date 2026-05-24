from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Recommendation(BaseModel):
    """A suggested action produced by a RecommendationEngine."""

    id: UUID = Field(default_factory=uuid4)
    plant_id: str | None = None
    location_id: str | None = None
    action: str          # "water" | "fertilize" | "prune" | "harvest" | "cover_for_frost" | ...
    reason: str          # short human explanation
    engine: str          # name of the engine that produced it
    confidence: float = 1.0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    valid_after: datetime | None = None
    valid_until: datetime | None = None
    dismissed_at: datetime | None = None
    details: dict[str, Any] = Field(default_factory=dict)

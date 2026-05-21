from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from garden._clock import now as _now
from garden.domain.enums import EventType


class Event(BaseModel):
    """A discrete action.

    Can attach to a plant, a location, or both. Type-specific data lives in `details`.
    """

    id: UUID = Field(default_factory=uuid4)
    type: EventType
    occurred_at: datetime = Field(default_factory=_now)
    plant_id: str | None = None
    location_id: str | None = None
    from_location_id: str | None = None  # transplants: source
    details: dict[str, Any] = Field(default_factory=dict)
    actor: str = "manual:user"
    source: str = "cli"
    notes: str | None = None

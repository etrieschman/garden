from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Observation(BaseModel):
    """A measurement.

    Unified shape for manual notes, provider-fetched data (weather), and future
    sensor streams. The `source` string discriminates origin.
    """

    id: UUID = Field(default_factory=uuid4)
    metric: str  # prefer values from `MetricKind`; free string for legacy/ad-hoc
    value_numeric: float | None = None
    value_text: str | None = None
    unit: str | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    plant_id: str | None = None
    location_id: str | None = None
    source: str = "manual:user"  # "manual:<who>" | "provider:<name>" | "sensor:<id>"
    notes: str | None = None

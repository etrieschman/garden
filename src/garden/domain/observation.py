from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Observation(BaseModel):
    """A measurement.

    Unified shape for manual notes, provider-fetched data (weather), and future
    sensor streams. The `source` string discriminates origin.
    """

    id: UUID = Field(default_factory=uuid4)
    metric: str  # e.g. "rain_mm", "soil_moisture_pct", "temp_c", "height_cm", "leaf_color"
    value_numeric: float | None = None
    value_text: str | None = None
    unit: str | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    plant_id: str | None = None
    location_id: str | None = None
    source: str = "manual:user"  # "manual:<who>" | "provider:<name>" | "sensor:<id>"
    notes: str | None = None

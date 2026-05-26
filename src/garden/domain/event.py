"""Events — discrete actions taken in the garden.

Everything Event-related lives here: the `Event` row, the per-type detail
schemas, and the `EVENT_DETAILS` registry that maps each EventType to its
schema. The CLI auto-generates `garden log <verb>` subcommands by walking
this registry, so adding a new event type means:
    1) add the enum value in domain/enums.py
    2) add a Pydantic model below
    3) register it in EVENT_DETAILS
No CLI code changes needed.

`SEEDED` and `TRANSPLANTED` aren't in EVENT_DETAILS — they're handled by
bespoke CLI commands because they also create a Plant.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from garden.domain.enums import AmendmentUnit, EventType

# ---------- the Event row itself ----------


class Event(BaseModel):
    """A discrete action.

    Can attach to a plant, a location, or both. Type-specific data lives in `details`.
    """

    id: UUID = Field(default_factory=uuid4)
    type: EventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    plant_id: str | None = None
    location_id: str | None = None
    from_location_id: str | None = None  # transplants: source
    details: dict[str, Any] = Field(default_factory=dict)
    actor: str = "manual:user"
    source: str = "cli"
    notes: str | None = None


# ---------- per-event-type detail schemas ----------


class WaterDetails(BaseModel):
    amount_l: float | None = Field(default=None, description="Litres applied.")
    method: str | None = Field(
        default=None, description="base | drip | foliar | overhead"
    )


class FertilizeDetails(BaseModel):
    type: str | None = Field(
        default=None,
        description="Amendment key from `garden amendments` (e.g. 'fish_emulsion', 'balanced_5_10_5').",
    )
    quantity: float | None = Field(default=None, description="Amount in `unit`.")
    unit: AmendmentUnit | None = Field(default=None, description="Unit of `quantity`.")
    n_pct: float | None = Field(
        default=None, description="% N override (defaults to catalog NPK[0])."
    )
    p_pct: float | None = Field(
        default=None, description="% P2O5 override (defaults to catalog NPK[1])."
    )
    k_pct: float | None = Field(
        default=None, description="% K2O override (defaults to catalog NPK[2])."
    )


class HarvestDetails(BaseModel):
    weight_g: float | None = Field(default=None, description="Total grams harvested.")
    count: int | None = Field(default=None, description="Number of items.")


class PruneDetails(BaseModel):
    what: str | None = Field(
        default=None, description="What was removed (e.g. 'suckers', 'lower leaves')."
    )
    fraction_removed: float | None = Field(
        default=None, description="Rough fraction 0-1."
    )


class TreatedDetails(BaseModel):
    pest_or_disease: str | None = Field(default=None, description="Target identified.")
    treatment: str | None = Field(default=None, description="Spray/method used.")


class AmendedDetails(BaseModel):
    type: str | None = Field(
        default=None,
        description="Amendment key from `garden amendments` (e.g. 'cow_manure', 'compost').",
    )
    quantity: float | None = Field(default=None, description="Amount in `unit`.")
    unit: AmendmentUnit | None = Field(default=None, description="Unit of `quantity`.")
    n_pct: float | None = Field(
        default=None, description="% N override (defaults to catalog NPK[0])."
    )
    p_pct: float | None = Field(
        default=None, description="% P2O5 override (defaults to catalog NPK[1])."
    )
    k_pct: float | None = Field(
        default=None, description="% K2O override (defaults to catalog NPK[2])."
    )


class GerminatedDetails(BaseModel):
    pass


class DiedDetails(BaseModel):
    cause: str | None = Field(default=None, description="Suspected cause.")


class RemovedDetails(BaseModel):
    reason: str | None = Field(default=None)


class ObservedDetails(BaseModel):
    """Free-form notes attach via Event.notes. Structured measurements should be
    `Observation` rows, not Event details."""


EVENT_DETAILS: dict[EventType, type[BaseModel]] = {
    EventType.WATERED: WaterDetails,
    EventType.FERTILIZED: FertilizeDetails,
    EventType.HARVESTED: HarvestDetails,
    EventType.PRUNED: PruneDetails,
    EventType.TREATED: TreatedDetails,
    EventType.AMENDED: AmendedDetails,
    EventType.GERMINATED: GerminatedDetails,
    EventType.DIED: DiedDetails,
    EventType.REMOVED: RemovedDetails,
    EventType.OBSERVED: ObservedDetails,
}

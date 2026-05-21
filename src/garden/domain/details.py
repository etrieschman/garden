"""Per-event-type detail schemas.

Each `EventType` has an associated Pydantic model that describes the shape of
`Event.details`. The registry below is the **single source of truth** for what
fields each event accepts.

The CLI introspects this registry to auto-generate `garden log <verb>`
subcommands. Future input channels (web form, Slack, sensors) read the same
registry. Adding a new event type means: add an enum value, add a model here,
register it. No CLI changes required.

`SEEDED` and `TRANSPLANTED` aren't here — they're handled by bespoke commands
because they *create* a Plant alongside logging the event.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from garden.domain.enums import EventType


class WaterDetails(BaseModel):
    amount_l: float | None = Field(default=None, description="Litres applied.")
    method: str | None = Field(
        default=None, description="base | drip | foliar | overhead"
    )


class FertilizeDetails(BaseModel):
    product: str | None = Field(default=None, description="Fertilizer name/brand.")
    npk: str | None = Field(default=None, description="N-P-K ratio, e.g. 5-10-5.")
    amount_g: float | None = Field(default=None, description="Grams applied.")


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
    added: str | None = Field(default=None, description="What was added.")
    amount: str | None = Field(default=None, description="Amount with units.")


class GerminatedDetails(BaseModel):
    pass


class DiedDetails(BaseModel):
    cause: str | None = Field(default=None, description="Suspected cause.")


class RemovedDetails(BaseModel):
    reason: str | None = Field(default=None)


class ObservedDetails(BaseModel):
    """Free-form notes attach via Event.notes. Structured measurements should be
    `Observation` rows, not Event details — that's why this model is empty."""


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

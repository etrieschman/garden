"""SQLAlchemy ORM models. Internal to the SQLite adapter — do not import outside `storage/`."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from garden._clock import now as _now
from garden.domain import (
    Dimensions,
    Event,
    EventType,
    Location,
    LocationKind,
    Observation,
    Plant,
    PlantStatus,
    Recommendation,
    Substrate,
    Taxon,
)


class Base(DeclarativeBase):
    pass


class TaxonRow(Base):
    __tablename__ = "taxa"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    scientific_name: Mapped[str] = mapped_column(String, index=True)
    common_name: Mapped[str | None] = mapped_column(String, nullable=True)
    cultivar: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    def to_domain(self) -> Taxon:
        return Taxon(
            id=self.id,
            scientific_name=self.scientific_name,
            common_name=self.common_name,
            cultivar=self.cultivar,
            category=self.category,
            source=self.source,
            metadata=self.extra or {},
        )

    @classmethod
    def from_domain(cls, t: Taxon) -> "TaxonRow":
        return cls(
            id=t.id,
            scientific_name=t.scientific_name,
            common_name=t.common_name,
            cultivar=t.cultivar,
            category=t.category,
            source=t.source,
            extra=t.metadata,
        )


class LocationRow(Base):
    __tablename__ = "locations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    dimensions: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    substrate: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    hardiness_zone: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    def to_domain(self) -> Location:
        return Location(
            id=self.id,
            name=self.name,
            kind=LocationKind(self.kind),
            lat=self.lat,
            lon=self.lon,
            dimensions=Dimensions(**self.dimensions) if self.dimensions else None,
            substrate=Substrate(**self.substrate) if self.substrate else None,
            parent_id=self.parent_id,
            hardiness_zone=self.hardiness_zone,
            notes=self.notes,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, loc: Location) -> "LocationRow":
        return cls(
            id=loc.id,
            name=loc.name,
            kind=loc.kind.value,
            lat=loc.lat,
            lon=loc.lon,
            dimensions=loc.dimensions.model_dump(mode="json") if loc.dimensions else None,
            substrate=loc.substrate.model_dump(mode="json") if loc.substrate else None,
            parent_id=loc.parent_id,
            hardiness_zone=loc.hardiness_zone,
            notes=loc.notes,
            created_at=loc.created_at,
        )


class PlantRow(Base):
    __tablename__ = "plants"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    taxon_id: Mapped[str] = mapped_column(ForeignKey("taxa.id"), index=True)
    location_id: Mapped[str | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String)
    planted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    def to_domain(self) -> Plant:
        return Plant(
            id=self.id,
            taxon_id=self.taxon_id,
            location_id=self.location_id,
            status=PlantStatus(self.status),
            planted_at=self.planted_at,
            notes=self.notes,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, p: Plant) -> "PlantRow":
        return cls(
            id=p.id,
            taxon_id=p.taxon_id,
            location_id=p.location_id,
            status=p.status.value,
            planted_at=p.planted_at,
            notes=p.notes,
            created_at=p.created_at,
        )


class EventRow(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    plant_id: Mapped[str | None] = mapped_column(
        ForeignKey("plants.id"), nullable=True, index=True
    )
    location_id: Mapped[str | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True, index=True
    )
    from_location_id: Mapped[str | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True
    )
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    actor: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_domain(self) -> Event:
        return Event(
            id=UUID(self.id),
            type=EventType(self.type),
            occurred_at=self.occurred_at,
            plant_id=self.plant_id,
            location_id=self.location_id,
            from_location_id=self.from_location_id,
            details=self.details or {},
            actor=self.actor,
            source=self.source,
            notes=self.notes,
        )

    @classmethod
    def from_domain(cls, e: Event) -> "EventRow":
        return cls(
            id=str(e.id),
            type=e.type.value,
            occurred_at=e.occurred_at,
            plant_id=e.plant_id,
            location_id=e.location_id,
            from_location_id=e.from_location_id,
            details=e.details,
            actor=e.actor,
            source=e.source,
            notes=e.notes,
        )


class ObservationRow(Base):
    __tablename__ = "observations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    metric: Mapped[str] = mapped_column(String, index=True)
    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    plant_id: Mapped[str | None] = mapped_column(
        ForeignKey("plants.id"), nullable=True, index=True
    )
    location_id: Mapped[str | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_domain(self) -> Observation:
        return Observation(
            id=UUID(self.id),
            metric=self.metric,
            value_numeric=self.value_numeric,
            value_text=self.value_text,
            unit=self.unit,
            occurred_at=self.occurred_at,
            plant_id=self.plant_id,
            location_id=self.location_id,
            source=self.source,
            notes=self.notes,
        )

    @classmethod
    def from_domain(cls, o: Observation) -> "ObservationRow":
        return cls(
            id=str(o.id),
            metric=o.metric,
            value_numeric=o.value_numeric,
            value_text=o.value_text,
            unit=o.unit,
            occurred_at=o.occurred_at,
            plant_id=o.plant_id,
            location_id=o.location_id,
            source=o.source,
            notes=o.notes,
        )


class RecommendationRow(Base):
    __tablename__ = "recommendations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    plant_id: Mapped[str | None] = mapped_column(
        ForeignKey("plants.id"), nullable=True, index=True
    )
    location_id: Mapped[str | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String, index=True)
    reason: Mapped[str] = mapped_column(Text)
    engine: Mapped[str] = mapped_column(String, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    valid_after: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    def to_domain(self) -> Recommendation:
        return Recommendation(
            id=UUID(self.id),
            plant_id=self.plant_id,
            location_id=self.location_id,
            action=self.action,
            reason=self.reason,
            engine=self.engine,
            confidence=self.confidence,
            generated_at=self.generated_at,
            valid_after=self.valid_after,
            valid_until=self.valid_until,
            dismissed_at=self.dismissed_at,
            details=self.details or {},
        )

    @classmethod
    def from_domain(cls, r: Recommendation) -> "RecommendationRow":
        return cls(
            id=str(r.id),
            plant_id=r.plant_id,
            location_id=r.location_id,
            action=r.action,
            reason=r.reason,
            engine=r.engine,
            confidence=r.confidence,
            generated_at=r.generated_at,
            valid_after=r.valid_after,
            valid_until=r.valid_until,
            dismissed_at=r.dismissed_at,
            details=r.details,
        )

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, or_, select
from sqlalchemy.orm import Session, sessionmaker

from garden.domain import (
    Event,
    Location,
    Observation,
    Plant,
    Recommendation,
    Taxon,
)
from garden.settings import GardenMeta
from garden.storage.models import (
    Base,
    EventRow,
    GardenRow,
    LocationRow,
    ObservationRow,
    PlantRow,
    RecommendationRow,
    TaxonRow,
)


class SQLiteStorage:
    """Default Storage implementation. Backs onto a single .sqlite file."""

    def __init__(self, db_path: str | Path = "data/garden.sqlite") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{self.db_path}"
        self.engine = create_engine(url, echo=False, future=True)
        self.Session: sessionmaker[Session] = sessionmaker(self.engine, expire_on_commit=False)

    def init_schema(self) -> None:
        Base.metadata.create_all(self.engine)
        self._ensure_columns()
        self._backfill_terminal_at()

    def _ensure_columns(self) -> None:
        """Idempotent inline migrations: add columns to existing tables if missing.

        `Base.metadata.create_all` only creates tables; it never adds columns
        to existing ones. Each `(table, column, type)` here is safe to re-apply:
        we skip the ALTER when the column already exists.
        """
        wanted: list[tuple[str, str, str]] = [
            ("recommendations", "due_at", "TIMESTAMP"),
            ("plants", "label", "VARCHAR"),
            ("plants", "terminal_at", "TIMESTAMP"),
            ("plants", "terminal_cause", "VARCHAR"),
            ("events", "photo_path", "VARCHAR"),
            ("garden", "engines", "JSON"),
        ]
        with self.engine.begin() as c:
            for table, column, sqltype in wanted:
                cols = c.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
                if not any(col[1] == column for col in cols):
                    c.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {sqltype}")

    def _backfill_terminal_at(self) -> None:
        """Set `plants.terminal_at` for legacy DEAD/REMOVED plants from their
        terminal event's `occurred_at`. Falls back to `created_at` if no event
        is on record. Idempotent: skips plants that already have a value.
        """
        with self.engine.begin() as c:
            rows = c.exec_driver_sql(
                "SELECT id, status, created_at FROM plants "
                "WHERE terminal_at IS NULL AND status IN ('dead', 'removed')"
            ).fetchall()
            for plant_id, status, created_at in rows:
                terminal_event_type = "died" if status == "dead" else "removed"
                ev = c.exec_driver_sql(
                    "SELECT occurred_at, details FROM events "
                    "WHERE plant_id = ? AND type = ? "
                    "ORDER BY occurred_at DESC LIMIT 1",
                    (plant_id, terminal_event_type),
                ).fetchone()
                if ev is not None:
                    occurred_at, details_json = ev
                    cause: str | None = None
                    if details_json:
                        import json
                        try:
                            cause = json.loads(details_json).get("cause") or json.loads(
                                details_json
                            ).get("reason")
                        except (ValueError, AttributeError):
                            cause = None
                    c.exec_driver_sql(
                        "UPDATE plants SET terminal_at = ?, terminal_cause = ? WHERE id = ?",
                        (occurred_at, cause, plant_id),
                    )
                else:
                    c.exec_driver_sql(
                        "UPDATE plants SET terminal_at = ? WHERE id = ?",
                        (created_at, plant_id),
                    )

    # ---- garden settings ----
    def get_garden(self) -> GardenMeta:
        with self.Session() as s:
            row = s.get(GardenRow, 1)
            if row is None:
                return GardenMeta()
            defaults = GardenMeta.model_fields["engines"].default
            return GardenMeta(
                name=row.name,
                default_lat=row.default_lat,
                default_lon=row.default_lon,
                timezone=row.timezone,
                engines=row.engines if row.engines else list(defaults),
            )

    def save_garden(self, meta: GardenMeta) -> None:
        with self.Session.begin() as s:
            row = s.get(GardenRow, 1)
            if row is None:
                s.add(
                    GardenRow(
                        id=1,
                        name=meta.name,
                        default_lat=meta.default_lat,
                        default_lon=meta.default_lon,
                        timezone=meta.timezone,
                        engines=list(meta.engines),
                    )
                )
            else:
                row.name = meta.name
                row.default_lat = meta.default_lat
                row.default_lon = meta.default_lon
                row.timezone = meta.timezone
                row.engines = list(meta.engines)

    # ---- taxa ----
    def upsert_taxon(self, taxon: Taxon) -> Taxon:
        with self.Session.begin() as s:
            existing = s.get(TaxonRow, taxon.id)
            if existing:
                existing.scientific_name = taxon.scientific_name
                existing.common_name = taxon.common_name
                existing.cultivar = taxon.cultivar
                existing.category = taxon.category
                existing.source = taxon.source
                existing.extra = taxon.metadata
            else:
                s.add(TaxonRow.from_domain(taxon))
        return taxon

    def get_taxon(self, taxon_id: str) -> Taxon | None:
        with self.Session() as s:
            row = s.get(TaxonRow, taxon_id)
            return row.to_domain() if row else None

    def find_taxon(self, query: str) -> list[Taxon]:
        q = f"%{query.lower()}%"
        with self.Session() as s:
            stmt = select(TaxonRow).where(
                or_(
                    TaxonRow.id.ilike(q),
                    TaxonRow.scientific_name.ilike(q),
                    TaxonRow.common_name.ilike(q),
                    TaxonRow.cultivar.ilike(q),
                )
            )
            return [r.to_domain() for r in s.scalars(stmt)]

    def list_taxa(self) -> list[Taxon]:
        with self.Session() as s:
            return [r.to_domain() for r in s.scalars(select(TaxonRow))]

    # ---- locations ----
    def upsert_location(self, location: Location) -> Location:
        with self.Session.begin() as s:
            existing = s.get(LocationRow, location.id)
            if existing:
                fresh = LocationRow.from_domain(location)
                for col in (
                    "name",
                    "kind",
                    "lat",
                    "lon",
                    "dimensions",
                    "substrate",
                    "parent_id",
                    "hardiness_zone",
                    "notes",
                ):
                    setattr(existing, col, getattr(fresh, col))
            else:
                s.add(LocationRow.from_domain(location))
        return location

    def get_location(self, location_id: str) -> Location | None:
        with self.Session() as s:
            row = s.get(LocationRow, location_id)
            return row.to_domain() if row else None

    def list_locations(self) -> list[Location]:
        with self.Session() as s:
            return [r.to_domain() for r in s.scalars(select(LocationRow))]

    # ---- plants ----
    def create_plant(self, plant: Plant) -> Plant:
        with self.Session.begin() as s:
            s.add(PlantRow.from_domain(plant))
        return plant

    def update_plant(self, plant: Plant) -> Plant:
        with self.Session.begin() as s:
            existing = s.get(PlantRow, plant.id)
            if not existing:
                raise KeyError(f"plant not found: {plant.id}")
            fresh = PlantRow.from_domain(plant)
            for col in (
                "taxon_id",
                "location_id",
                "status",
                "label",
                "planted_at",
                "terminal_at",
                "terminal_cause",
                "notes",
            ):
                setattr(existing, col, getattr(fresh, col))
        return plant

    def get_plant(self, plant_id: str) -> Plant | None:
        with self.Session() as s:
            row = s.get(PlantRow, plant_id)
            return row.to_domain() if row else None

    def find_plants(self, query: str) -> list[Plant]:
        q = f"%{query.lower()}%"
        with self.Session() as s:
            stmt = (
                select(PlantRow)
                .join(TaxonRow, TaxonRow.id == PlantRow.taxon_id)
                .where(
                    or_(
                        PlantRow.id.ilike(q),
                        PlantRow.label.ilike(q),
                        TaxonRow.cultivar.ilike(q),
                        TaxonRow.common_name.ilike(q),
                        TaxonRow.scientific_name.ilike(q),
                    )
                )
            )
            return [r.to_domain() for r in s.scalars(stmt)]

    def list_plants(self, location_id: str | None = None) -> list[Plant]:
        with self.Session() as s:
            stmt = select(PlantRow)
            if location_id is not None:
                stmt = stmt.where(PlantRow.location_id == location_id)
            return [r.to_domain() for r in s.scalars(stmt)]

    # ---- events ----
    def create_event(self, event: Event) -> Event:
        with self.Session.begin() as s:
            s.add(EventRow.from_domain(event))
        return event

    def list_events(
        self,
        plant_id: str | None = None,
        location_id: str | None = None,
        since: datetime | None = None,
    ) -> list[Event]:
        with self.Session() as s:
            stmt = select(EventRow).order_by(EventRow.occurred_at.desc())
            if plant_id is not None:
                stmt = stmt.where(EventRow.plant_id == plant_id)
            if location_id is not None:
                stmt = stmt.where(EventRow.location_id == location_id)
            if since is not None:
                stmt = stmt.where(EventRow.occurred_at >= since)
            return [r.to_domain() for r in s.scalars(stmt)]

    def find_events_by_prefix(self, id_prefix: str) -> list[Event]:
        with self.Session() as s:
            stmt = select(EventRow).where(EventRow.id.like(f"{id_prefix}%"))
            return [r.to_domain() for r in s.scalars(stmt)]

    def delete_event(self, event_id: UUID) -> None:
        with self.Session.begin() as s:
            row = s.get(EventRow, str(event_id))
            if row is not None:
                s.delete(row)

    # ---- observations ----
    def create_observation(self, observation: Observation) -> Observation:
        with self.Session.begin() as s:
            s.add(ObservationRow.from_domain(observation))
        return observation

    def list_observations(
        self,
        metric: str | None = None,
        plant_id: str | None = None,
        location_id: str | None = None,
        since: datetime | None = None,
    ) -> list[Observation]:
        with self.Session() as s:
            stmt = select(ObservationRow).order_by(ObservationRow.occurred_at.desc())
            if metric is not None:
                stmt = stmt.where(ObservationRow.metric == metric)
            if plant_id is not None:
                stmt = stmt.where(ObservationRow.plant_id == plant_id)
            if location_id is not None:
                stmt = stmt.where(ObservationRow.location_id == location_id)
            if since is not None:
                stmt = stmt.where(ObservationRow.occurred_at >= since)
            return [r.to_domain() for r in s.scalars(stmt)]

    def delete_observations(
        self,
        *,
        location_id: str,
        source_prefix: str,
        since: datetime,
        until: datetime,
    ) -> int:
        """Delete observations for one location whose source starts with `source_prefix`,
        in [since, until]. Used to make weather refreshes idempotent."""
        with self.Session.begin() as s:
            return (
                s.query(ObservationRow)
                .filter(
                    ObservationRow.location_id == location_id,
                    ObservationRow.source.like(f"{source_prefix}%"),
                    ObservationRow.occurred_at >= since,
                    ObservationRow.occurred_at <= until,
                )
                .delete()
            )

    # ---- recommendations ----
    def create_recommendation(self, rec: Recommendation) -> Recommendation:
        with self.Session.begin() as s:
            s.add(RecommendationRow.from_domain(rec))
        return rec

    def list_recommendations(
        self,
        plant_id: str | None = None,
        location_id: str | None = None,
        include_dismissed: bool = False,
    ) -> list[Recommendation]:
        with self.Session() as s:
            stmt = select(RecommendationRow).order_by(RecommendationRow.generated_at.desc())
            if plant_id is not None:
                stmt = stmt.where(RecommendationRow.plant_id == plant_id)
            if location_id is not None:
                stmt = stmt.where(RecommendationRow.location_id == location_id)
            if not include_dismissed:
                stmt = stmt.where(RecommendationRow.dismissed_at.is_(None))
            return [r.to_domain() for r in s.scalars(stmt)]

    def dismiss_recommendation(self, rec_id: UUID) -> None:
        with self.Session.begin() as s:
            row = s.get(RecommendationRow, str(rec_id))
            if row:
                row.dismissed_at = datetime.now(UTC)

    def find_recommendations_by_prefix(self, id_prefix: str) -> list[Recommendation]:
        with self.Session() as s:
            stmt = select(RecommendationRow).where(
                RecommendationRow.id.like(f"{id_prefix}%")
            )
            return [r.to_domain() for r in s.scalars(stmt)]

    def clear_undismissed_recommendations(self) -> None:
        """Delete every recommendation the user hasn't dismissed. Used to make
        `refresh_recommendations` produce a clean snapshot rather than accumulate."""
        with self.Session.begin() as s:
            s.query(RecommendationRow).filter(
                RecommendationRow.dismissed_at.is_(None)
            ).delete()

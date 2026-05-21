"""Reconcile garden.yaml into the database.

The yaml is the declarative source of truth for beds: hand-edit it, the next
CLI invocation upserts the changes into the DB. The DB-side log of events,
plants, and observations stays authoritative for itself — the yaml never owns
that data.

Called once at GardenApp.open() so every CLI command runs with a synced DB.
"""

from __future__ import annotations

from garden.config.yaml_config import BedConfig, GardenConfig
from garden.domain import Dimensions, Location, LocationKind, Substrate
from garden.storage.base import Storage


def sync_config_to_storage(cfg: GardenConfig, storage: Storage) -> int:
    """Upsert every bed declared in `cfg` into `storage`. Returns the count synced.

    Idempotent: re-running with an unchanged yaml is a no-op write per row
    (upsert) but doesn't add or delete anything.
    Removal: deleting a bed from yaml does NOT delete it from the DB, since
    historical events/observations still reference it.
    """
    for bed in cfg.beds:
        storage.upsert_location(_bed_to_location(bed, cfg))
    return len(cfg.beds)


def _bed_to_location(bed: BedConfig, cfg: GardenConfig) -> Location:
    return Location(
        id=bed.id,
        name=bed.name or bed.id,
        kind=LocationKind(bed.kind),
        lat=bed.lat if bed.lat is not None else cfg.default_lat,
        lon=bed.lon if bed.lon is not None else cfg.default_lon,
        dimensions=Dimensions.model_validate(bed.dimensions) if bed.dimensions else None,
        substrate=Substrate.model_validate(bed.substrate) if bed.substrate else None,
        notes=bed.notes,
    )

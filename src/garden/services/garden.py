"""Operations that create or modify Plants and Locations."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from garden.domain import (
    Dimensions,
    Location,
    LocationKind,
    Plant,
    PlantStatus,
    Substrate,
    Taxon,
)
from garden.providers.catalog import CatalogProvider, LocalCatalog
from garden.storage.base import Storage


def _slug(*parts: str) -> str:
    s = "-".join(p.lower() for p in parts if p)
    return re.sub(r"[^a-z0-9-]+", "-", s).strip("-") or "x"


def parse_dimensions(text: str) -> Dimensions:
    """Parse a dimensions string in **integer cm**.

    Accepted forms:
        - ``"40cm"``          → round container, diameter only
        - ``"60x40cm"``       → length × width
        - ``"240x120x30cm"``  → length × width × depth

    Decimals are rejected (round to the nearest cm). Raises ValueError on
    anything that doesn't parse, so a typo doesn't silently drop a dimension.
    """
    cleaned = text.strip().lower().removesuffix("cm").strip()
    raw = cleaned.replace("x", " ").split()
    if not raw:
        raise ValueError(f"could not parse dimensions: {text!r}")
    try:
        parts = [int(p) for p in raw]
    except ValueError as e:
        raise ValueError(
            f"dimensions must be integer cm (got {text!r}); "
            "round to the nearest centimetre, e.g. 30 instead of 30.5"
        ) from e
    if len(parts) == 1:
        return Dimensions(diameter_cm=parts[0])
    if len(parts) == 2:
        return Dimensions(length_cm=parts[0], width_cm=parts[1])
    if len(parts) == 3:
        return Dimensions(length_cm=parts[0], width_cm=parts[1], depth_cm=parts[2])
    raise ValueError(f"could not parse dimensions: {text!r}")


def add_location(
    storage: Storage,
    *,
    id: str,
    name: str | None = None,
    kind: LocationKind,
    lat: float | None = None,
    lon: float | None = None,
    dimensions: Dimensions | None = None,
    substrate_medium: str | None = None,
) -> Location:
    loc = Location(
        id=id,
        name=name or id,
        kind=kind,
        lat=lat,
        lon=lon,
        dimensions=dimensions,
        substrate=Substrate(medium=substrate_medium) if substrate_medium else None,
    )
    return storage.upsert_location(loc)


def resolve_taxon(
    storage: Storage,
    catalog: CatalogProvider,
    query: str,
    *,
    category: str | None = None,
) -> Taxon:
    """Look up an existing taxon (DB → catalog) or create one from `query`."""
    # 1. existing DB hits
    hits = storage.find_taxon(query)
    if len(hits) == 1:
        return hits[0]

    # 2. catalog provider
    found = catalog.lookup(query)
    if found:
        return storage.upsert_taxon(found)

    # 3. coin from query
    if isinstance(catalog, LocalCatalog):
        new = catalog.coin(query, category=category)
    else:
        new = Taxon(id=_slug(query), scientific_name=query, common_name=query, source="manual")
    return storage.upsert_taxon(new)


def add_plant(
    storage: Storage,
    *,
    taxon: Taxon,
    location_id: str | None,
    status: PlantStatus = PlantStatus.SEEDED,
    planted_at: datetime | None = None,
    suffix: str | None = None,
    label: str | None = None,
) -> Plant:
    """Create a plant. Auto-IDs by taxon + ordinal so multiple plants don't clash."""
    base = _slug(taxon.common_name or taxon.scientific_name, taxon.cultivar or "")
    existing_ids = {p.id for p in storage.list_plants()}
    plant_id: str
    if suffix:
        plant_id = _slug(base, suffix)
    else:
        i = 1
        while True:
            candidate = f"{base}-{i}"
            if candidate not in existing_ids:
                plant_id = candidate
                break
            i += 1
    plant = Plant(
        id=plant_id,
        taxon_id=taxon.id,
        location_id=location_id,
        status=status,
        label=label,
        planted_at=planted_at or datetime.now(UTC).replace(tzinfo=None),
    )
    return storage.create_plant(plant)


def resolve_plant(storage: Storage, query: str) -> Plant:
    """Resolve a plant by id, slug, or fuzzy-name. Raises if ambiguous."""
    direct = storage.get_plant(query)
    if direct:
        return direct
    hits = storage.find_plants(query)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise LookupError(f"no plant matches {query!r}")
    raise LookupError(
        f"{query!r} matches multiple plants: " + ", ".join(p.id for p in hits)
    )

"""Container that wires storage, providers, and engines together.

This module also owns instance discovery (where the user's `garden.sqlite`
lives on disk) so there's one entry point: `GardenApp.open()`.

An *instance* is a directory containing `garden.sqlite`. Discovery order:
1. `$GARDEN_HOME` env var
2. `./garden-data/` walking up from cwd to the repo root
3. `~/.config/garden/` (XDG default for users not in a repo checkout)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from garden.providers.catalog import CatalogProvider, LocalCatalog
from garden.providers.weather import OpenMeteoProvider, WeatherProvider
from garden.recommendations import RecommendationEngine, RuleEngine
from garden.settings import GardenMeta
from garden.storage.base import Storage
from garden.storage.sqlite import SQLiteStorage

INSTANCE_DIR_NAME = "garden-data"
DB_FILENAME = "garden.sqlite"
LEGACY_YAML_FILENAME = "garden.yaml"


class InstanceNotFoundError(RuntimeError):
    pass


@dataclass
class GardenApp:
    meta: GardenMeta
    storage: Storage
    catalog: CatalogProvider
    weather: WeatherProvider
    engines: list[RecommendationEngine]
    instance_dir: Path

    @classmethod
    def open(cls, instance_dir: Path | None = None) -> GardenApp:
        """Open the GardenApp at `instance_dir` (or discover one from env/cwd)."""
        inst = instance_dir or discover_instance()
        storage = SQLiteStorage(inst / DB_FILENAME)
        storage.init_schema()
        _migrate_legacy_yaml(inst, storage)  # one-time, no-op after first run
        meta = storage.get_garden()
        return cls(
            meta=meta,
            storage=storage,
            catalog=LocalCatalog(),
            weather=OpenMeteoProvider(),
            engines=[RuleEngine()],
            instance_dir=inst,
        )

    def save_meta(self) -> None:
        self.storage.save_garden(self.meta)


# ---------- instance discovery + bootstrap ----------


def discover_instance(start: Path | None = None) -> Path:
    """Return the instance directory. Raises if none is found."""
    env = os.environ.get("GARDEN_HOME")
    if env:
        p = Path(env).expanduser()
        if (p / DB_FILENAME).exists() or (p / LEGACY_YAML_FILENAME).exists():
            return p
        raise InstanceNotFoundError(
            f"GARDEN_HOME is set to {p} but no garden.sqlite there. "
            f"Run `garden init {p}` to scaffold one."
        )

    cwd = (start or Path.cwd()).resolve()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / INSTANCE_DIR_NAME
        if (candidate / DB_FILENAME).exists() or (candidate / LEGACY_YAML_FILENAME).exists():
            return candidate
        if (parent / "pyproject.toml").exists():
            break

    home_default = Path.home() / ".config" / "garden"
    if (home_default / DB_FILENAME).exists():
        return home_default

    raise InstanceNotFoundError(
        "No garden instance found. Run `garden init` to create one."
    )


def init_instance(
    path: Path,
    *,
    name: str = "My Garden",
    default_lat: float | None = None,
    default_lon: float | None = None,
    timezone: str = "America/New_York",
) -> Path:
    """Create a fresh instance directory at `path` with an initialized DB."""
    path = path.expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    db = path / DB_FILENAME
    if db.exists():
        raise FileExistsError(f"{db} already exists; refusing to overwrite")
    storage = SQLiteStorage(db)
    storage.init_schema()
    storage.save_garden(
        GardenMeta(
            name=name,
            default_lat=default_lat,
            default_lon=default_lon,
            timezone=timezone,
        )
    )
    return path


# ---------- one-shot yaml migration (transitional) ----------


def _migrate_legacy_yaml(instance_dir: Path, storage: Storage) -> None:
    """Absorb a pre-existing garden.yaml into the SQLite database.

    Idempotent: renames the yaml to `.migrated` afterward so the migration
    only ever runs once per instance. Safe to delete this function (and the
    yaml file/handling) after a release or two.
    """
    yaml_path = instance_dir / LEGACY_YAML_FILENAME
    if not yaml_path.exists():
        return

    import yaml as _yaml

    from garden.domain import Dimensions, Location, LocationKind, Substrate

    data = _yaml.safe_load(yaml_path.read_text()) or {}

    meta = GardenMeta(
        name=data.get("name", "My Garden"),
        default_lat=data.get("default_lat"),
        default_lon=data.get("default_lon"),
        timezone=data.get("timezone", "America/New_York"),
    )
    storage.save_garden(meta)

    for bed in data.get("beds", []) or []:
        loc = Location(
            id=bed["id"],
            name=bed.get("name") or bed["id"],
            kind=LocationKind(bed.get("kind", "raised_bed")),
            lat=bed.get("lat", meta.default_lat),
            lon=bed.get("lon", meta.default_lon),
            dimensions=Dimensions(**bed["dimensions"]) if bed.get("dimensions") else None,
            substrate=Substrate(**bed["substrate"]) if bed.get("substrate") else None,
            notes=bed.get("notes"),
        )
        storage.upsert_location(loc)

    yaml_path.rename(instance_dir / f"{LEGACY_YAML_FILENAME}.migrated")

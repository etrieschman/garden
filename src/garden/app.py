"""Container that wires storage, providers, and engines together.

Every entry point (CLI today, web/Slack tomorrow) constructs a GardenApp and
calls service-layer functions through it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from garden import instance
from garden.config import GardenConfig, load_config, save_config
from garden.providers.catalog import CatalogProvider, LocalCatalog
from garden.providers.weather import OpenMeteoProvider, WeatherProvider
from garden.recommendations import RecommendationEngine, RuleEngine
from garden.services.sync import sync_config_to_storage
from garden.storage.base import Storage
from garden.storage.sqlite import SQLiteStorage


@dataclass
class GardenApp:
    config: GardenConfig
    storage: Storage
    catalog: CatalogProvider
    weather: WeatherProvider
    engines: list[RecommendationEngine]
    instance_dir: Path

    @property
    def config_path(self) -> Path:
        return instance.config_path(self.instance_dir)

    @classmethod
    def open(cls, instance_dir: Path | None = None) -> GardenApp:
        """Open the GardenApp at `instance_dir` (or discover one from env/cwd)."""
        inst = instance_dir or instance.discover()
        cfg = load_config(instance.config_path(inst))
        storage = SQLiteStorage(instance.db_path(inst))
        storage.init_schema()
        sync_config_to_storage(cfg, storage)
        return cls(
            config=cfg,
            storage=storage,
            catalog=LocalCatalog(),
            weather=OpenMeteoProvider(),
            engines=[RuleEngine()],
            instance_dir=inst,
        )

    def save_config(self) -> None:
        save_config(self.config, self.config_path)

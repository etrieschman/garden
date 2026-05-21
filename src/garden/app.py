"""Container that wires storage, providers, and engines together.

Every entry point (CLI today, web/Slack tomorrow) constructs a GardenApp and
calls service-layer functions through it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from garden.config import GardenConfig, load_config, save_config
from garden.providers.catalog import CatalogProvider, LocalCatalog
from garden.providers.weather import OpenMeteoProvider, WeatherProvider
from garden.recommendations import RecommendationEngine, RuleEngine
from garden.storage.base import Storage
from garden.storage.sqlite import SQLiteStorage


@dataclass
class GardenApp:
    config: GardenConfig
    storage: Storage
    catalog: CatalogProvider
    weather: WeatherProvider
    engines: list[RecommendationEngine]
    config_path: Path

    @classmethod
    def from_config(cls, config_path: str | Path = "config/garden.yaml") -> GardenApp:
        path = Path(config_path)
        cfg = load_config(path)
        storage = SQLiteStorage(cfg.db_path)
        storage.init_schema()
        return cls(
            config=cfg,
            storage=storage,
            catalog=LocalCatalog(),
            weather=OpenMeteoProvider(),
            engines=[RuleEngine()],
            config_path=path,
        )

    def save_config(self) -> None:
        save_config(self.config, self.config_path)

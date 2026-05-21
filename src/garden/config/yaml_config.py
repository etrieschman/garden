"""garden.yaml round-trip.

The yaml is a *snapshot* of the user's garden setup — beds, common aliases,
provider choices. The CLI reads it on startup and writes back when you add/edit
beds so the file stays in sync with the database. Manual edits to the yaml are
also honored (the CLI applies them on next run).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class BedConfig(BaseModel):
    id: str
    name: str | None = None
    kind: str = "raised_bed"
    lat: float | None = None
    lon: float | None = None
    dimensions: dict[str, Any] | None = None
    substrate: dict[str, Any] | None = None
    notes: str | None = None


class GardenConfig(BaseModel):
    name: str = "My Garden"
    default_lat: float | None = None
    default_lon: float | None = None
    timezone: str = "America/New_York"
    beds: list[BedConfig] = Field(default_factory=list)
    aliases: dict[str, str] = Field(default_factory=dict)  # short → plant id

    def find_bed(self, bed_id: str) -> BedConfig | None:
        for b in self.beds:
            if b.id == bed_id:
                return b
        return None


def load_config(path: str | Path) -> GardenConfig:
    p = Path(path)
    if not p.exists():
        return GardenConfig()
    with p.open() as f:
        data = yaml.safe_load(f) or {}
    # Drop legacy fields that have moved out of the yaml schema.
    data.pop("db_path", None)
    return GardenConfig.model_validate(data)


def save_config(cfg: GardenConfig, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        yaml.safe_dump(
            cfg.model_dump(mode="json", exclude_none=True),
            f,
            sort_keys=False,
            default_flow_style=False,
        )

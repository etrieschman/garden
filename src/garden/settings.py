"""Garden-wide settings (name, default lat/lon, timezone).

Lives in the SQLite `garden` table as a single row. Use `GardenApp.meta` to
read/write — never reach into the table directly.
"""

from __future__ import annotations

from pydantic import BaseModel


class GardenMeta(BaseModel):
    name: str = "My Garden"
    default_lat: float | None = None
    default_lon: float | None = None
    timezone: str = "America/New_York"

from datetime import date, datetime
from typing import Protocol

from pydantic import BaseModel


class WeatherSample(BaseModel):
    """A single weather observation. Maps to one or more domain Observations."""

    timestamp: datetime
    temp_c_min: float | None = None
    temp_c_max: float | None = None
    temp_c_mean: float | None = None
    rain_mm: float | None = None
    sunshine_hours: float | None = None
    gdd_base_10c: float | None = None  # cumulative growing degree days, base 10°C


class WeatherProvider(Protocol):
    """Fetches weather for a lat/lon. Implementations: Open-Meteo, NOAA, etc."""

    name: str

    def daily(
        self,
        lat: float,
        lon: float,
        start: date,
        end: date,
    ) -> list[WeatherSample]: ...

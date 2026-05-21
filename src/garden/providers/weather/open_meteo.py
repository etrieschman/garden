"""Open-Meteo daily archive + forecast.

No API key. Free for hobby use. Endpoint docs: https://open-meteo.com/en/docs
"""

from datetime import date, datetime

import httpx

from garden.providers.weather.base import WeatherSample

_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


class OpenMeteoProvider:
    name = "open-meteo"

    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    def daily(self, lat: float, lon: float, start: date, end: date) -> list[WeatherSample]:
        today = date.today()
        out: list[WeatherSample] = []
        if start < today:
            out.extend(self._fetch(_ARCHIVE_URL, lat, lon, start, min(end, today)))
        if end >= today:
            forecast_start = max(start, today)
            out.extend(self._fetch(_FORECAST_URL, lat, lon, forecast_start, end))
        return out

    def _fetch(
        self, url: str, lat: float, lon: float, start: date, end: date
    ) -> list[WeatherSample]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": ",".join(
                [
                    "temperature_2m_min",
                    "temperature_2m_max",
                    "temperature_2m_mean",
                    "precipitation_sum",
                    "sunshine_duration",
                ]
            ),
            "timezone": "auto",
        }
        with httpx.Client(timeout=self._timeout) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            data = r.json()

        daily = data.get("daily") or {}
        dates: list[str] = daily.get("time", [])
        tmin = daily.get("temperature_2m_min", [])
        tmax = daily.get("temperature_2m_max", [])
        tmean = daily.get("temperature_2m_mean", [])
        rain = daily.get("precipitation_sum", [])
        sun_sec = daily.get("sunshine_duration", [])

        samples: list[WeatherSample] = []
        gdd_cum = 0.0
        for i, d in enumerate(dates):
            mean = tmean[i] if i < len(tmean) else None
            if mean is not None:
                gdd_cum += max(0.0, mean - 10.0)
            samples.append(
                WeatherSample(
                    timestamp=datetime.fromisoformat(d),
                    temp_c_min=tmin[i] if i < len(tmin) else None,
                    temp_c_max=tmax[i] if i < len(tmax) else None,
                    temp_c_mean=mean,
                    rain_mm=rain[i] if i < len(rain) else None,
                    sunshine_hours=(sun_sec[i] / 3600.0) if i < len(sun_sec) and sun_sec[i] else None,
                    gdd_base_10c=gdd_cum,
                )
            )
        return samples

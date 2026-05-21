# garden

Track a home garden — plants, events, observations, recommendations.

Designed so each layer (storage, weather providers, recommendation engines, UI) can be swapped without touching the others.

## Quick start

```bash
uv sync                                    # install deps
uv run garden bed add patio-north \
    --kind raised_bed \
    --dim 240x120x30cm \
    --lat 42.37360754570248 \
    --lon -71.10338051500713 \
    --substrate "Coast of Maine raised bed mix"

uv run garden log transplant "Garden Gem" --to patio-north
uv run garden status
```

## Architecture

```
Inputs       :  Typer CLI  →  (future: HTMX web form, Slack, photos, sensors)
                    ↓
Services     :  log_event, get_recommendations, refresh_weather       (the use cases)
                    ↓
Domain       :  Plant, Event, Observation, Recommendation, Taxon, Location  (pure Pydantic)
                  ↓                              ↓                     ↓
Storage       External providers         Recommendation engines
(SQLite      (Open-Meteo, NOAA,         (rule-based, USDA, future ML)
 default)     USDA, OSM)
```

Every boundary is a `Protocol`. Swap implementations via config.

## Project layout

```
src/garden/
├── domain/          # Pure Pydantic models — no I/O
├── storage/         # Storage Protocol + SQLite impl
├── providers/       # Weather, catalog (sun/soil to come)
├── recommendations/ # Engine Protocol + rule-based default
├── services/        # Use-case layer the CLI/UI call into
├── config/          # garden.yaml round-trip
└── cli/             # Typer commands
```

## Status

**v0** (current): CLI, SQLite storage, Open-Meteo weather, rule-based recommendations.

**v1** (planned): HTMX web UI, USDA guideline engine, OSM-based urban shading model, Alembic migrations.

**v2** (planned): Hardware sensors, ML recommendations, photo logging.

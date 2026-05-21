# garden

Track a home garden — plants, events, observations, recommendations.

Designed so each layer (storage, weather providers, recommendation engines, UI)
can be swapped without touching the others.

## Quick start

```bash
git clone https://github.com/etrieschman/garden
cd garden
uv sync
uv run garden status         # uses ./garden-data/ as instance
```

If you forked or want your own data, see [Making it yours](#making-it-yours).

## What's where

```
src/garden/         ← code (generic, sharable)
config/garden.example.yaml   ← template that `garden init` copies from
garden-data/        ← YOUR data (this is what makes the DB "your garden")
  ├── README.md       ← how to fork/replace this directory
  ├── garden.yaml     ← your beds, defaults
  └── garden.sqlite   ← your events, observations
tests/              ← test suite
```

The code in `src/garden/` doesn't know or care which instance directory it's
running against. That separation is the point.

## Making it yours

After forking or cloning, replace this repo's `garden-data/` with your own.

**Easiest path — start fresh in the same repo:**

```bash
rm -rf garden-data/
uv run garden init           # scaffolds a clean ./garden-data/
# edit garden-data/garden.yaml: set name, default_lat, default_lon
uv run garden bed add my-bed --kind raised_bed --dim 240x120x30cm
```

Commit your `garden-data/` so you can sync across machines via `git pull`.

**If you want privacy** — keep the code public, move data to a private repo:

```bash
mv garden-data ../my-garden-data   # somewhere outside this repo
cd ../my-garden-data
git init && gh repo create my-garden-data --private --source=. --push
echo 'export GARDEN_HOME=~/dev/my-garden-data' >> ~/.zshrc
```

The CLI discovers the instance via:
1. `$GARDEN_HOME` if set
2. `./garden-data/` walking up to the repo root
3. `~/.config/garden/` (XDG default)

## Usage

```bash
uv run garden bed add patio-north --kind raised_bed --dim 240x120x30cm \
    --substrate "Coast of Maine raised bed mix"

uv run garden log transplant "Garden Gem" --to patio-north
uv run garden water gem --amount 2.0
uv run garden harvest gem --weight 250 --count 8

uv run garden weather                      # pulls Open-Meteo into observations
uv run garden recommend                    # runs all engines, persists results
uv run garden status                       # overview
uv run garden show tomato-garden-gem-1     # one plant's detail
```

Set `GARDEN_STRICT=1` to disable fuzzy plant matching and require explicit args.

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

## Status

**v0** (current): CLI, SQLite storage, Open-Meteo weather, rule-based recommendations.

**v1** (planned): HTMX web UI, USDA guideline engine, OSM-based urban shading
model, Alembic migrations.

**v2** (planned): Hardware sensors, ML recommendations, photo logging.

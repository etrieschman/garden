# garden

Track a home garden — plants, events, observations, recommendations.

Designed so each layer (storage, weather providers, recommendation engines, UI)
can be swapped without touching the others.

## Quick start

```bash
git clone https://github.com/etrieschman/garden
cd garden
uv sync
uv run garden status         # uses ./garden-data/ as the instance
```

If you forked or want your own data, see [Making it yours](#making-it-yours).

If you'll run the notebooks, install the output-stripping git filter once per
clone so notebook outputs never get committed:

```bash
uv run nbstripout --install
```

## Where things live

```
src/garden/         ← code (generic, sharable)
garden-data/        ← YOUR data (one SQLite file)
  ├── README.md
  └── garden.sqlite   ← settings, beds, plants, events, observations
tests/              ← test suite
```

**Everything is in `garden.sqlite`:**
- The `garden` table (single row) holds settings: `name`, `default_lat`, `default_lon`, `timezone`.
- The `locations` table holds your beds.
- The `plants`, `events`, `observations`, `recommendations`, `taxa` tables hold the gardening journal.

There used to be a separate `garden.yaml`. It's gone — see [the design note](#why-only-sqlite) below.

## Making it yours

After forking or cloning, replace this repo's `garden-data/garden.sqlite` with your own.

**Easiest path — start fresh in the same repo:**

```bash
rm garden-data/garden.sqlite
uv run garden init \
    --name "My Garden" \
    --lat 42.3 --lon -71.1 \
    --timezone America/New_York

uv run garden bed add my-bed --kind raised_bed --dim 240x120x30cm
```

Commit your `garden-data/` so it syncs across machines via `git pull`.

**If you want privacy** — keep the code public, move data to a private repo:

```bash
mv garden-data ../my-garden-data
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
# Beds
uv run garden bed add patio-north --kind raised_bed --dim 240x120x30cm \
    --substrate "Coast of Maine raised bed mix"
uv run garden bed list

# Plants — created via `garden log seeded` or `garden log transplanted`
uv run garden list

# Logging — `garden log <verb>` is registry-driven (see domain/event.py)
uv run garden log transplanted "Garden Gem" --to patio-north
uv run garden log seeded "Basil" --in patio-north
uv run garden log watered gem --amount-l 2.0 --method base
uv run garden log fertilized gem --type fish_emulsion --quantity 2 --unit tbsp
uv run garden log amended patio-north --type cow_manure --quantity 1 --unit cu-ft
uv run garden log harvested gem --weight-g 250 --count 8
uv run garden log delete <id-prefix>        # fix mistakes (delete + re-log)
uv run garden log --help                    # all verbs auto-generated

# Settings
uv run garden config show
uv run garden config set name "Erich's Garden"

# Reports + actions
uv run garden show tomato-garden-gem-1      # events, GDD, growth stage, nutrients, recs
uv run garden status
uv run garden weather                       # fetch + show + store Open-Meteo data
uv run garden recommend [--within 7]        # timeline of upcoming actions
uv run garden profile show "Garden Gem"     # what the engine knows about a species
uv run garden amendments                    # known fertilizer/amendment types
```

Set `GARDEN_STRICT=1` to disable fuzzy plant matching.

## Recommendations

Per-species **care profiles** (`src/garden/data/care_profiles.yaml`, cited to
cooperative-extension sources) drive water, frost, and fertilizer advice. The
engine combines each profile with your logged events and the weather forecast:

- **Water** — next-due from last watering or significant rain; faster cadence when the forecast is hot.
- **Frost** — warns when the 3-day forecast dips below the species threshold.
- **Fertilizer** — a **nutrient budget**, not a calendar. Growing-degree-days (from stored temps) pick the growth stage; each stage has a target N/P/K per week; the engine sums *plant-available* nutrients you've applied (`mass × NPK% × release_fraction`) and recommends feeding when you're below target. Slow-release inputs (composted manure ≈ 0.2) count for far less than synthetics (≈ 1.0).

Every recommendation has a `due_at`, so `garden recommend` reads as a timeline.
See [docs/CHEATSHEET.md](docs/CHEATSHEET.md) for the full command map.

## Architecture

```
Inputs       :  Typer CLI  →  (future: HTMX web form, Slack, photos, sensors)
                    ↓
Services     :  log_event, get_recommendations, refresh_weather       (use cases)
                    ↓
Domain       :  Plant, Event, Observation, Recommendation, Taxon, Location  (pure Pydantic)
                  ↓                              ↓                     ↓
Storage       External providers         Recommendation engines
(SQLite      (Open-Meteo, NOAA,         (rule-based, USDA, future ML)
 default)     USDA, OSM)
```

Every boundary is a `Protocol`. Swap implementations via config.

### Why only SQLite?

The previous version had a `garden.yaml` for "config" alongside `garden.sqlite`
for "data". That sounded clean in theory but in practice both files held *beds*,
which created a "which is the source of truth?" muddle that wasn't worth the
hand-editability win (everyone uses the CLI anyway).

If you want to hand-edit settings, `garden config show` / `garden config set`
covers the common cases. If you ever need full vim-on-yaml, we can add a
`garden config edit` that dumps → opens editor → re-imports — but only if
someone actually wants it.

## Status

**v0.3** (current): CLI, single SQLite store, Open-Meteo weather, care-profile
engine with GDD growth stages and nutrient-balance fertilizer (release-fraction
aware). Live dashboard at [etrieschman.github.io/garden](https://etrieschman.github.io/garden/)
rendered from this repo via Quarto + GitHub Actions on every push.

**v1** (planned): HTMX web UI, USDA guideline engine, OSM-based urban shading
model, ET-based irrigation, Alembic migrations.

**v2** (planned): Hardware sensors, ML recommendations, photo logging.

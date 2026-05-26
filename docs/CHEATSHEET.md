# garden — command cheatsheet

Every command accepts `--help` for the full option list. This is the map.

## Setup

```bash
garden init [PATH]                          # scaffold a fresh instance (defaults to ./garden-data)
garden init --name "X" --lat 42 --lon -71 --timezone America/New_York
garden config show
garden config set name "Erich's Garden"     # or default_lat / default_lon / timezone
```

## Beds

```bash
garden bed add patio-north --kind raised_bed --dim 240x120x30cm \
    --substrate "Coast of Maine raised bed mix"
garden bed list
```

- `--kind`: `raised_bed`, `in_ground`, `container`, `flower_pot`, `greenhouse`, `hydroponic`, `indoor`, `seed_tray`
- `--dim` (**integer cm**, round decimals): `LxWxDcm` (beds) · `LxWcm` (no depth) · `Ncm` (round-container diameter)
- `--lat`/`--lon` default to the garden's configured location

## Plants

```bash
garden plant "Improved Garden Gem" --to patio-north   # add an established plant
garden list                                            # all plants
garden show <plant>                                    # detail: events, GDD, stage, nutrients, recs
```

## Logging actions

`garden log <verb> <target> [options]`. The target auto-resolves to a plant
(id or fuzzy name) or a bed id; plants win on conflict. Every verb takes
`--when ISO_TIMESTAMP` and `--notes/-n`.

**Creation verbs** (also create the Plant):

```bash
garden log seed "Basil" --in patio-north
garden log transplant "Improved Garden Gem" --to patio-north --from seed-tray
```

**Event verbs** (registry-driven — `garden log <verb> --help` for fields):

| Verb         | Key flags                                                  | Target       |
|--------------|------------------------------------------------------------|--------------|
| `watered`    | `--amount-l 2.0 --method base`                             | plant or bed |
| `fertilized` | `--type fish_emulsion --quantity 2 --unit tbsp`            | plant or bed |
| `amended`    | `--type cow_manure --quantity 1 --unit cu-ft`              | bed          |
| `harvested`  | `--weight-g 250 --count 8`                                 | plant        |
| `pruned`     | `--what suckers --fraction-removed 0.2`                    | plant        |
| `treated`    | `--pest-or-disease aphids --treatment soap`                | plant or bed |
| `germinated` | —                                                          | plant        |
| `died`       | `--cause "root rot"`                                       | plant        |
| `removed`    | `--reason "end of season"`                                 | plant        |
| `observed`   | (use `--notes`)                                            | plant or bed |

See [Fertilizer & nutrients](#fertilizer--nutrients) for `--type`/`--unit` details.

## Review + fix mistakes

```bash
garden log list                          # last 20 events with short ids
garden log list --plant gem --type watered --limit 50
garden log delete 412b6a17 [-y]          # delete by id prefix (no in-place edit yet — delete + re-log)
```

## Weather + recommendations

```bash
garden weather [--days-back 14 --days-forward 7] [--no-store]   # fetch + show + store
garden recommend                         # next 7 days, sorted by due date
garden recommend --within 3|30           # tighter / wider horizon
garden recommend --all                   # everything, ignoring due date
garden recommend --no-weather            # offline
```

Recommendations carry a `due_at`, so output reads as a timeline (`TODAY` /
`tomorrow` / `in 3d` / `2d late`).

## How the engine decides

Per-species **care profiles** (`src/garden/data/care_profiles.yaml`, cited to
cooperative-extension sources) drive everything. The engine pairs each profile
with your logged events + weather forecast:

- **Water** — next-due = last watering or significant rain + cadence; switches to a faster "hot" cadence when the forecast is hot.
- **Frost** — warns if the 3-day forecast min drops below the species threshold.
- **Fertilizer** — *nutrient-balance*, not just calendar (see below).
- **Container kinds** (`container`/`flower_pot`/`indoor`/`seed_tray`) water + feed faster via a multiplier.

```bash
garden profile list                      # species the engine knows
garden profile show "Improved Garden Gem"   # merged species+cultivar profile
```

Add a species = edit `care_profiles.yaml`. Cultivar entries override species
fields. No code changes.

## Fertilizer & nutrients

Fertilizer uses **growing-degree-day (GDD) growth stages** + a **nutrient
budget**, not a fixed schedule:

1. GDD accumulates from your stored daily temps since transplant (base temp is per-species — tomato 10°C, lettuce 5°C…).
2. GDD picks the current stage (establishing → vegetative → flowering → fruiting), each with a target N/P/K **g per week**.
3. The engine sums **plant-available** nutrients you've applied (`mass × NPK% × release_fraction`) and recommends feeding when you're below target.

`release_fraction` discounts slow-release inputs: synthetic granular/liquid ≈
1.0, composted manure ≈ 0.2. So 1 cu ft of cow manure counts as the ~17 g of N
that actually mineralizes this season, not its full label value.

```bash
garden amendments                        # known --type keys + density + NPK + release_fraction
garden log fertilized gem --type balanced_5_10_5 --quantity 50 --unit g
garden log amended patio-north --type cow_manure --quantity 1 --unit cu-ft
```

- `--type` must be a known amendment (`garden amendments`) **or** you must pass `--n-pct/--p-pct/--k-pct` for a custom one.
- `--unit`: mass (`kg g lb oz`) or volume (`L ml gal fl-oz cu-ft cu-yd tsp tbsp cup`). Volume needs the amendment's density (in the catalog) to compute mass.
- `--n-pct/--p-pct/--k-pct` override the catalog NPK (e.g. your bag's label differs).

`garden show <plant>` reports GDD, current stage, and N/P/K applied vs target.

## Adding a recommendation engine

Implement the `RecommendationEngine` Protocol, drop the class in
`src/garden/recommendations/`, add it to `engines=[...]` in `app.py`. The
orchestrator dedupes by `(plant_id, action)`, keeping highest confidence — so
new engines (ML, ET-based irrigation, USDA scrapers) are additive.

## Data exploration

```bash
uv sync --group notebook
uv run jupyter lab                       # notebooks/explore.ipynb
```

Or hit the SQLite directly:

```python
import pandas as pd
from sqlalchemy import create_engine
engine = create_engine("sqlite:///garden-data/garden.sqlite")
pd.read_sql("SELECT * FROM events", engine)
```

## Strict mode

`GARDEN_STRICT=1` disables fuzzy plant matching (require exact ids) — useful for scripts.

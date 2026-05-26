# garden — command cheatsheet

Every `garden <command>` also accepts `--help` for the full option list. This
page is just the at-a-glance map of what exists.

## Setup

```bash
garden init [PATH]                       # scaffold a fresh instance
garden init --name "X" --lat 42 --lon -71 --timezone America/New_York

garden config show                       # current settings
garden config set name "Erich's Garden"  # update one setting
garden config set default_lat 42.37
```

## Beds (locations)

```bash
garden bed add my-bed --kind raised_bed --dim 240x120x30cm \
    --substrate "Coast of Maine raised bed mix"
garden bed add greenhouse --kind greenhouse --lat 42.3 --lon -71.1
garden bed list
```

`--kind` choices: `raised_bed`, `in_ground`, `container`, `greenhouse`,
`hydroponic`, `indoor`, `seed_tray`.

`--dim` format: `NxNxNcm` (L×W×D) or `Ncm` (diameter for round containers).

## Plants

```bash
garden plant "Garden Gem" --to my-bed              # add an existing-life plant
garden list                                         # list all plants
garden show <plant-id-or-name>                      # detail view
```

## Logging actions

`garden log <verb> <target> [options]`. The target is auto-detected — pass a
plant id/name **or** a bed id. Plants win on conflict.

**Creation verbs** (these create a Plant alongside the event):

```bash
garden log seed "Basil" --in my-bed
garden log transplant "Garden Gem" --to my-bed --from old-bed
```

**Plant- or bed-scoped events** (registry-driven; see `--help` per verb):

| Verb         | Flags                                              | Typical target |
|--------------|----------------------------------------------------|----------------|
| `watered`    | `--amount-l 2.0 --method base`                     | plant or bed   |
| `fertilized` | `--product "Neptune's" --npk 2-3-1 --amount-g 50`  | plant or bed   |
| `harvested`  | `--weight-g 250 --count 8`                         | plant          |
| `pruned`     | `--what suckers --fraction-removed 0.2`            | plant          |
| `treated`    | `--pest-or-disease aphids --treatment soap`        | plant or bed   |
| `amended`    | `--added "bag of manure" --amount "50 lb"`         | bed            |
| `germinated` | (no extra fields)                                  | plant          |
| `died`       | `--cause "root rot"`                               | plant          |
| `removed`    | `--reason "end of season"`                         | plant          |
| `observed`   | `--notes "..."`                                    | plant or bed   |

All verbs accept `--when ISO_TIMESTAMP` and `--notes "..."` / `-n "..."`.

## Reviewing + fixing mistakes

```bash
garden log list                          # last 20 events with short ids
garden log list --plant gem --type watered
garden log list --bed patio-north --limit 50
garden log delete 412b6a17               # delete by id prefix (asks confirm)
garden log delete 412b6a17 -y            # skip confirmation
```

Editing isn't a CLI command yet — delete and re-log to fix mistakes.

## Reports

```bash
garden status                            # garden overview
garden show <plant>                      # one plant's full history
```

## Weather + recommendations

```bash
garden weather                           # pull Open-Meteo for all beds
garden weather --days-back 30 --days-forward 7
garden recommend                         # default: next 7 days, sorted by due date
garden recommend --within 3              # urgent (next 3 days only)
garden recommend --within 30             # full month-ahead
garden recommend --all                   # show all recs regardless of due date
garden recommend --no-weather            # offline (skip weather fetch)
```

Output is a timeline: each rec carries a `due_at` so you see "TODAY / tomorrow
/ in 3 days" not just a flat list of overdue items.

### How the engine decides

Recommendations come from per-species **care profiles** in
`src/garden/data/care_profiles.yaml`, with citations to cooperative-extension
publications. Each profile knows:

- **Water cadence** — normal days-between, hot-cadence, threshold temp, and
  what rain depth counts as "a watering"
- **Frost tolerance** — minimum safe temp (null if frost-hardy)
- **Growth stages** (GDD-driven) — establishing / vegetative / flowering /
  fruiting boundaries with stage-appropriate fertilizer mix and cadence
- **GDD base temp** — used to accumulate degree-days from your weather
  observations (tomato 10°C, lettuce 5°C, pepper 12°C, etc.)
- **Container multiplier** — feeds and waters faster in containers / seed trays

The engine pairs profiles with your logged events and the weather forecast:
- last watering / last rain → next water due date (or hot cadence if forecast hot)
- transplant date + accumulated GDD → current growth stage → fertilizer mix and cadence
- container vs raised bed → multiplier on feed cadence
- forecast min temp → frost warning if below profile threshold

### Inspecting profiles

```bash
garden profile list                      # all species the engine knows
garden profile show "Garden Gem"         # merged profile for one taxon
garden profile show "Solanum lycopersicum"
garden show <plant>                      # adds current GDD + growth stage
```

Adding a species = edit `src/garden/data/care_profiles.yaml`. Cultivars override
species defaults field-by-field. No code changes.

### Adding a new recommendation engine

The `RecommendationEngine` Protocol lets you plug in ML, ET-based irrigation,
USDA scrapers, etc. Drop a class in `src/garden/recommendations/`, add it to the
`engines=[...]` list in `app.py`, and the orchestrator dedupes by `(plant_id,
action)` keeping highest confidence.

## Data exploration (notebook)

```bash
uv sync --group notebook                 # one-time
uv run jupyter lab                       # open notebooks/explore.ipynb
```

Or read the SQLite directly from anywhere:

```python
import pandas as pd
from sqlalchemy import create_engine
engine = create_engine("sqlite:///garden-data/garden.sqlite")
events = pd.read_sql("SELECT * FROM events", engine)
```

## Strict mode

`GARDEN_STRICT=1` disables fuzzy plant name matching (you must use the exact
plant id, not a substring). Useful for scripting.

```bash
GARDEN_STRICT=1 garden log watered tomato-garden-gem-1 --amount-l 2.0
```

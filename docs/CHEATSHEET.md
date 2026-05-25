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
garden recommend                         # run engines, persist results
garden recommend --no-weather            # offline
```

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

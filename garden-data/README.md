# garden-data/

**This directory holds personal garden data — beds, plants, events, observations.**
It is committed alongside the code so it syncs across machines via `git pull` /
`git push`. The code in `src/garden/` is generic; this directory is what makes
the database "your garden."

## Files

- `garden.yaml` — your beds, aliases, and defaults (lat/lon, garden name).
  Hand-editable. The CLI also writes to it when you run `garden bed add`.
- `garden.sqlite` — your event log, observations, plants, taxa.
  Binary; SQLAlchemy/SQLite reads/writes it. Committed so it syncs.

## You forked this repo — now what?

You probably want to replace this directory with your own data. Two ways:

**1. Start fresh (recommended)**

```bash
rm -rf garden-data/
uv run garden init
# Edit garden-data/garden.yaml — set name, default_lat, default_lon
uv run garden bed add my-bed --kind raised_bed --dim 240x120x30cm
```

**2. Keep this as a reference, point GARDEN_HOME elsewhere**

```bash
mv garden-data garden-data.example
uv run garden init ~/my-garden-data    # or anywhere else
export GARDEN_HOME=~/my-garden-data    # add to your shell profile
```

## Syncing across machines

```bash
# After a day of logging on Machine A:
git -C garden-data status               # changed: garden.sqlite, garden.yaml
git add garden-data && git commit -m "logged today's events"
git push

# On Machine B:
git pull
```

**Caveat:** `garden.sqlite` is binary. Don't edit on two machines without
pulling first, or you'll get an unmergeable conflict. If that ever becomes a
problem, we can add a YAML/JSON export (the storage layer is pluggable).

## Privacy

This is a public repo. Anything you put in `garden-data/` is public too. If
your data ever needs to be private:
- Move `garden-data/` to a separate **private** repo of your own,
- Clone it somewhere, and
- Set `GARDEN_HOME=/path/to/clone` so the CLI finds it.

The code doesn't care where the instance directory lives.

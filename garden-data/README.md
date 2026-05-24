# garden-data/

**This directory holds your personal garden data as a single SQLite file.**
It's committed alongside the code so it syncs across machines via `git pull` /
`git push`. The code in `src/garden/` is generic; this directory is what makes
the database "your garden."

## Files

- `garden.sqlite` — settings (one row in the `garden` table), beds, plants,
  events, observations, recommendations. Binary; SQLAlchemy reads/writes it.

That's it. There used to be a `garden.yaml` here too; it's been folded into
the SQLite. If you upgraded from the old version, `garden.yaml.migrated` may
be sitting around as a one-time breadcrumb — it's safe to delete.

## You forked this repo — now what?

You probably want to replace this database with your own. Two paths:

**1. Start fresh (recommended)**

```bash
rm garden-data/garden.sqlite
uv run garden init \
    --name "My Garden" \
    --lat 42.3 --lon -71.1 \
    --timezone America/New_York

uv run garden bed add my-bed --kind raised_bed --dim 240x120x30cm
```

**2. Keep this as a reference, point GARDEN_HOME elsewhere**

```bash
mv garden-data garden-data.example
uv run garden init ~/my-garden-data
export GARDEN_HOME=~/my-garden-data
```

## Syncing across machines

```bash
# After a day of logging on Machine A:
git -C garden-data status
git add garden-data && git commit -m "logged today's events"
git push

# On Machine B:
git pull
```

**Caveat:** `garden.sqlite` is binary, so concurrent edits across machines
produce unmergeable conflicts. Commit before switching machines.

## Privacy

This is a public repo. Anything in `garden-data/` is public too. If your
data should be private, move `garden-data/` to a separate private repo and
set `GARDEN_HOME=/path/to/it`. The code doesn't care where the data lives.

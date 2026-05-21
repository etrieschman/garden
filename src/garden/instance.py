"""Garden instance discovery.

An *instance* is a directory containing `garden.yaml` + `garden.sqlite`. It
holds personal data, kept entirely separate from the code in `src/garden/`.

Discovery order (first hit wins):
1. `$GARDEN_HOME` env var
2. `./garden-data/` walking up from cwd to repo root
3. `~/.config/garden/` (XDG default for users not in a repo checkout)

If nothing is found and an instance is required, `discover()` raises and the
CLI tells the user to run `garden init`.
"""

from __future__ import annotations

import os
from pathlib import Path

INSTANCE_DIR_NAME = "garden-data"
CONFIG_FILENAME = "garden.yaml"
DB_FILENAME = "garden.sqlite"
EXAMPLE_CONFIG = "config/garden.example.yaml"


class InstanceNotFoundError(RuntimeError):
    pass


def discover(start: Path | None = None) -> Path:
    """Return the instance directory. Raises if none is found."""
    env = os.environ.get("GARDEN_HOME")
    if env:
        p = Path(env).expanduser()
        if (p / CONFIG_FILENAME).exists():
            return p
        raise InstanceNotFoundError(
            f"GARDEN_HOME is set to {p} but {CONFIG_FILENAME} is missing there. "
            f"Run `garden init {p}` to scaffold one."
        )

    cwd = (start or Path.cwd()).resolve()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / INSTANCE_DIR_NAME
        if (candidate / CONFIG_FILENAME).exists():
            return candidate
        if (parent / "pyproject.toml").exists():
            break  # stop at repo root

    home_default = Path.home() / ".config" / "garden"
    if (home_default / CONFIG_FILENAME).exists():
        return home_default

    raise InstanceNotFoundError(
        "No garden instance found. Run `garden init` (creates ./garden-data) "
        "or `garden init <path>` to scaffold one, then set GARDEN_HOME or run "
        "from inside the repo."
    )


def init_instance(path: Path, *, template: Path | None = None) -> Path:
    """Create a fresh instance directory at `path`.

    Copies `config/garden.example.yaml` to `<path>/garden.yaml`. The SQLite file
    is left absent — the first CLI call will create it.
    """
    path = path.expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    target = path / CONFIG_FILENAME
    if target.exists():
        raise FileExistsError(f"{target} already exists; refusing to overwrite")

    # Find template (allow override for tests)
    if template is None:
        template = _find_template()
    target.write_text(template.read_text())
    return path


def _find_template() -> Path:
    """Locate config/garden.example.yaml relative to the repo or installed pkg."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / EXAMPLE_CONFIG
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"could not locate {EXAMPLE_CONFIG} — installation may be corrupted"
    )


def db_path(instance_dir: Path) -> Path:
    return instance_dir / DB_FILENAME


def config_path(instance_dir: Path) -> Path:
    return instance_dir / CONFIG_FILENAME

"""Garden CLI entry point.

Imports the topic submodules so their commands register on the shared Typer
apps. The submodules cover:
    bed.py   — `garden bed <add|list>`
    log.py   — `garden log <verb> ...` (registry-driven; seed/transplant create plants)
    show.py  — `garden list | show | status | recommend | weather`
This file owns the meta commands: `init` and `config show|set`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from garden import app as app_mod

# importing these modules registers their commands on the shared Typer apps
from garden.cli import bed, log, profile, show  # noqa: F401
from garden.cli._app import app, config_app, console, garden_app
from garden.settings import GardenMeta


@app.command("init")
def cmd_init(
    path: Annotated[
        Path | None,
        typer.Argument(help="Directory to scaffold (defaults to ./garden-data)."),
    ] = None,
    name: Annotated[str, typer.Option(help="Garden name.")] = "My Garden",
    lat: Annotated[float | None, typer.Option(help="Default latitude.")] = None,
    lon: Annotated[float | None, typer.Option(help="Default longitude.")] = None,
    timezone: Annotated[str, typer.Option(help="IANA timezone.")] = "America/New_York",
) -> None:
    """Create a fresh garden instance (empty database + settings)."""
    target = (path or Path.cwd() / app_mod.INSTANCE_DIR_NAME).expanduser().resolve()
    try:
        created = app_mod.init_instance(
            target, name=name, default_lat=lat, default_lon=lon, timezone=timezone
        )
    except FileExistsError as e:
        console.print(f"[yellow]![/yellow] {e}")
        raise typer.Exit(code=1) from e
    console.print(f"[green]✓[/green] Scaffolded instance at [bold]{created}[/bold]")
    console.print(
        "  use [bold]garden config set[/bold] to change name/lat/lon/timezone later"
    )


@config_app.command("show")
def config_show() -> None:
    """Print current garden settings."""
    ga = garden_app()
    t = Table(title=f"{ga.meta.name} — settings")
    t.add_column("key")
    t.add_column("value")
    for key in ("name", "default_lat", "default_lon", "timezone"):
        t.add_row(key, str(getattr(ga.meta, key)))
    console.print(t)


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="One of: name, default_lat, default_lon, timezone.")],
    value: Annotated[str, typer.Argument(help="New value (lat/lon are floats).")],
) -> None:
    """Change a single garden setting."""
    ga = garden_app()
    if key not in GardenMeta.model_fields:
        raise typer.BadParameter(f"unknown key: {key!r}")
    coerced: object = float(value) if key in ("default_lat", "default_lon") else value
    setattr(ga.meta, key, coerced)
    ga.save_meta()
    console.print(f"[green]✓[/green] {key} = {coerced!r}")


if __name__ == "__main__":
    app()

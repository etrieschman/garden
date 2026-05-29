"""Shared CLI state: Typer apps, helpers, console.

Every cli/*.py module imports the appropriate `*_app` here and attaches its
commands. `main.py` triggers all imports and exposes the entry point.
"""

from __future__ import annotations

import os

import typer
from rich.console import Console

from garden.app import GardenApp, InstanceNotFoundError

console = Console()

app = typer.Typer(
    name="garden",
    help="Track a home garden — plants, events, observations, recommendations.",
    no_args_is_help=True,
)
bed_app = typer.Typer(help="Manage beds / locations.", no_args_is_help=True)
log_app = typer.Typer(help="Log a discrete event.", no_args_is_help=True)
config_app = typer.Typer(help="Show or change garden settings.", no_args_is_help=True)
profile_app = typer.Typer(help="Inspect care profiles.", no_args_is_help=True)
recommend_app = typer.Typer(
    help="Generate, list, or dismiss recommendations.", no_args_is_help=True
)

app.add_typer(bed_app, name="bed")
app.add_typer(log_app, name="log")
app.add_typer(config_app, name="config")
app.add_typer(profile_app, name="profile")
app.add_typer(recommend_app, name="recommend")


def strict() -> bool:
    """Whether --strict / GARDEN_STRICT mode is active. Disables fuzzy resolution."""
    return os.environ.get("GARDEN_STRICT", "").lower() in ("1", "true", "yes")


def garden_app() -> GardenApp:
    try:
        return GardenApp.open()
    except InstanceNotFoundError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=1) from e

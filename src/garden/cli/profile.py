"""`garden profile show|list` — inspect care profiles."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from garden.cli._app import console, profile_app
from garden.recommendations import CareProfile, CareProfileBundle


def _print_profile(p: CareProfile) -> None:
    name = (
        f"{p.common_name} '{p.cultivar}'"
        if p.cultivar and p.common_name
        else (p.common_name or p.cultivar or p.scientific_name)
    )
    console.print(f"[bold cyan]{name}[/bold cyan]  ({p.scientific_name})")
    if p.water:
        console.print("  [bold]water[/bold]")
        console.print(f"    every {p.water.days_between_normal}d normally")
        console.print(
            f"    every {p.water.days_between_hot}d when forecast 7d max "
            f"> {p.water.hot_temp_threshold_c:g}°C"
        )
        console.print(f"    ≥{p.water.significant_rain_mm:g}mm rain counts as a watering")
    if p.frost:
        if p.frost.min_safe_temp_c is None:
            console.print("  [bold]frost[/bold]  frost-hardy")
        else:
            console.print(
                f"  [bold]frost[/bold]  protect below {p.frost.min_safe_temp_c:g}°C"
            )
    if p.fertilize:
        console.print("  [bold]fertilize[/bold]")
        console.print(
            f"    first feed: {p.fertilize.first_feed_days_after_transplant}d after transplant"
        )
        console.print(f"    then every {p.fertilize.interval_days}d")
        if p.fertilize.preferred:
            console.print(f"    preferred: {p.fertilize.preferred}")
    if p.sources:
        console.print("  [dim]sources:[/dim]")
        for s in p.sources:
            console.print(f"    - {s}")


def _matches(p: CareProfile, query: str) -> bool:
    q = query.lower()
    return any(
        field and q == field.lower()
        for field in (p.scientific_name, p.common_name, p.cultivar)
    )


@profile_app.command("show")
def profile_show(
    taxon: Annotated[
        str, typer.Argument(help="Scientific name, common name, or cultivar.")
    ],
) -> None:
    """Show the care profile the recommendation engine uses for a taxon."""
    bundle = CareProfileBundle.load_default()
    candidates = [p for p in bundle.profiles if _matches(p, taxon)]
    if not candidates:
        console.print(f"[red]✗[/red] no profile found for {taxon!r}")
        console.print("  try `garden profile list` to see what's known.")
        raise typer.Exit(code=1)

    for i, candidate in enumerate(candidates):
        resolved = bundle.resolve(candidate.scientific_name, candidate.cultivar)
        if resolved is None:
            continue
        if i:
            console.print()
        _print_profile(resolved)


@profile_app.command("list")
def profile_list() -> None:
    """List every taxon with a care profile."""
    bundle = CareProfileBundle.load_default()
    t = Table(title="Known care profiles")
    t.add_column("scientific name")
    t.add_column("common")
    t.add_column("cultivar")
    t.add_column("water (n/h °C)")
    t.add_column("frost ≤")
    for p in bundle.profiles:
        water = (
            f"{p.water.days_between_normal}d / {p.water.days_between_hot}d"
            if p.water
            else "—"
        )
        frost = (
            f"{p.frost.min_safe_temp_c:g}°C"
            if p.frost and p.frost.min_safe_temp_c is not None
            else ("hardy" if p.frost else "—")
        )
        t.add_row(
            p.scientific_name,
            p.common_name or "—",
            p.cultivar or "—",
            water,
            frost,
        )
    console.print(t)

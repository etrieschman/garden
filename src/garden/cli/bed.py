"""`garden bed ...` — add and list beds (locations)."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from garden.cli._app import bed_app, console, garden_app, strict
from garden.domain import LocationKind
from garden.services import garden as garden_svc


@bed_app.command("add")
def bed_add(
    id: Annotated[str, typer.Argument(help="Short id / slug, e.g. 'patio-north'.")],
    kind: Annotated[
        LocationKind, typer.Option(help="raised_bed / in_ground / container / ...")
    ] = LocationKind.RAISED_BED,
    dim: Annotated[
        str | None,
        typer.Option(
            help=(
                "Dimensions in integer cm. LxWxD raised beds: '240x120x30cm'. "
                "LxW only: '60x40cm'. Round containers (diameter): '40cm'. "
                "Round decimals to the nearest cm."
            ),
        ),
    ] = None,
    lat: Annotated[
        float | None, typer.Option(help="Latitude (defaults to garden default).")
    ] = None,
    lon: Annotated[
        float | None, typer.Option(help="Longitude (defaults to garden default).")
    ] = None,
    substrate: Annotated[
        str | None, typer.Option(help="Soil/medium description.")
    ] = None,
    name: Annotated[
        str | None, typer.Option(help="Human-readable name (defaults to id).")
    ] = None,
) -> None:
    """Add a bed/location."""
    ga = garden_app()
    try:
        dims = garden_svc.parse_dimensions(dim) if dim else None
    except ValueError as e:
        raise typer.BadParameter(str(e), param_hint="--dim") from e
    final_lat = lat if lat is not None else ga.meta.default_lat
    final_lon = lon if lon is not None else ga.meta.default_lon
    if strict() and (final_lat is None or final_lon is None):
        raise typer.BadParameter("--lat and --lon required in strict mode")

    loc = garden_svc.add_location(
        ga.storage,
        id=id,
        name=name,
        kind=kind,
        lat=final_lat,
        lon=final_lon,
        dimensions=dims,
        substrate_medium=substrate,
    )

    area = loc.dimensions.area_m2 if loc.dimensions else None
    volume = loc.dimensions.volume_l if loc.dimensions else None
    summary = f"[green]✓[/green] {loc.kind.value} '{loc.id}'"
    if area:
        summary += f" — {area:.2f} m²"
    if volume:
        summary += f", ~{volume:.0f} L"
    console.print(summary)


@bed_app.command("list")
def bed_list() -> None:
    """List all beds."""
    ga = garden_app()
    locs = ga.storage.list_locations()
    if not locs:
        console.print("[dim]no beds yet — `garden bed add`[/dim]")
        return
    t = Table(title="Beds")
    t.add_column("id")
    t.add_column("kind")
    t.add_column("size")
    t.add_column("lat,lon")
    t.add_column("# plants", justify="right")
    counts: dict[str, int] = {}
    for p in ga.storage.list_plants():
        if p.location_id:
            counts[p.location_id] = counts.get(p.location_id, 0) + 1
    for loc in locs:
        size = ""
        if loc.dimensions:
            if loc.dimensions.area_m2:
                size = f"{loc.dimensions.area_m2:.2f} m²"
            if loc.dimensions.volume_l:
                size += f" / {loc.dimensions.volume_l:.0f} L"
        coords = f"{loc.lat:.4f},{loc.lon:.4f}" if (loc.lat and loc.lon) else "—"
        t.add_row(loc.id, loc.kind.value, size, coords, str(counts.get(loc.id, 0)))
    console.print(t)

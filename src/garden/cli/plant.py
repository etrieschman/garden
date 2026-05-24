"""`garden plant <taxon>` — add a plant to a bed."""

from __future__ import annotations

from typing import Annotated

import typer

from garden.cli._app import app, console, garden_app, strict
from garden.domain import PlantStatus
from garden.services import garden as garden_svc


@app.command("plant")
def plant_add(
    taxon_query: Annotated[
        str, typer.Argument(help="Cultivar/species, e.g. 'Garden Gem'.")
    ],
    to: Annotated[str | None, typer.Option(help="Bed id to plant into.")] = None,
    status: Annotated[
        PlantStatus, typer.Option(help="Initial status.")
    ] = PlantStatus.TRANSPLANTED,
) -> None:
    """Add a plant to a bed (creates a Taxon if needed)."""
    ga = garden_app()
    if strict() and to is None:
        raise typer.BadParameter("--to required in strict mode")
    taxon = garden_svc.resolve_taxon(ga.storage, ga.catalog, taxon_query)
    plant = garden_svc.add_plant(ga.storage, taxon=taxon, location_id=to, status=status)
    console.print(
        f"[green]🌱[/green] Created plant [bold]{plant.id}[/bold] "
        f"({taxon.display_name}) in [bold]{to or '—'}[/bold]"
    )

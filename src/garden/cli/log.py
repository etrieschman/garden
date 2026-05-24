"""`garden log <verb> ...` — schema-driven event logging.

Per-verb subcommands are auto-generated from `EVENT_DETAILS` (see
`domain/event.py`). The bespoke `transplant` and `seed` subcommands stay
hand-written because they create a Plant alongside the event.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any

import typer
from pydantic import BaseModel

from garden.cli._app import console, garden_app, log_app
from garden.domain import EventType, PlantStatus
from garden.domain.event import EVENT_DETAILS
from garden.services import garden as garden_svc
from garden.services import logging


def _build_log_command(event_type: EventType, model: type[BaseModel]) -> Callable[..., None]:
    """Build a Typer-compatible callable for `garden log <event_type>`.

    Common params (plant, --when, --notes) plus one --flag per field on the
    detail model. Validates inputs through the Pydantic model before forwarding
    to the logging service.
    """

    def _impl(**kwargs: Any) -> None:
        plant = kwargs.pop("plant")
        when = kwargs.pop("when", None)
        notes = kwargs.pop("notes", None)
        details_raw = {k: v for k, v in kwargs.items() if v is not None}
        details = model.model_validate(details_raw).model_dump(exclude_none=True)
        occurred = datetime.fromisoformat(when) if when else None
        ga = garden_app()
        e = logging.log_event(
            ga.storage,
            plant_query=plant,
            type=event_type,
            occurred_at=occurred,
            details=details,
            notes=notes,
        )
        suffix = f"  {details}" if details else ""
        console.print(
            f"[green]✓[/green] Logged {event_type.value} for [bold]{e.plant_id}[/bold] "
            f"at {e.occurred_at:%Y-%m-%d %H:%M}{suffix}"
        )

    params: list[inspect.Parameter] = [
        inspect.Parameter(
            "plant",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=str,
        ),
        inspect.Parameter(
            "when",
            kind=inspect.Parameter.KEYWORD_ONLY,
            default=typer.Option(None, help="ISO timestamp; defaults to now."),
            annotation=str | None,
        ),
        inspect.Parameter(
            "notes",
            kind=inspect.Parameter.KEYWORD_ONLY,
            default=typer.Option(None, "--notes", "-n", help="Free-form note."),
            annotation=str | None,
        ),
    ]
    for fname, finfo in model.model_fields.items():
        params.append(
            inspect.Parameter(
                fname,
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=typer.Option(None, help=finfo.description or ""),
                annotation=finfo.annotation,
            )
        )

    _impl.__signature__ = inspect.Signature(params)  # type: ignore[attr-defined]
    _impl.__name__ = f"log_{event_type.value}"
    doc = (model.__doc__ or "").strip().splitlines()[0] if model.__doc__ else ""
    _impl.__doc__ = doc or f"Log a {event_type.value} event."
    return _impl


for _event_type, _model in EVENT_DETAILS.items():
    log_app.command(_event_type.value)(_build_log_command(_event_type, _model))


# ---------- creation verbs (special-cased because they create Plants) ----------


@log_app.command("transplant")
def log_transplant(
    taxon_or_plant: Annotated[
        str, typer.Argument(help="Plant id (existing) or taxon name (new plant).")
    ],
    to: Annotated[str, typer.Option(help="Bed id to transplant into.")],
    from_bed: Annotated[
        str | None, typer.Option("--from", help="Source location, if known.")
    ] = None,
    when: Annotated[
        str | None, typer.Option(help="ISO timestamp; defaults to now.")
    ] = None,
    notes: Annotated[str | None, typer.Option("--notes", "-n")] = None,
) -> None:
    """Log a transplant. Creates the Plant if `taxon_or_plant` doesn't match one."""
    ga = garden_app()
    if not ga.storage.get_location(to):
        raise typer.BadParameter(
            f"bed not found: {to!r}. Add it with `garden bed add {to} ...`"
        )
    occurred = datetime.fromisoformat(when) if when else datetime.now(UTC)

    fuzzy_hits = ga.storage.find_plants(taxon_or_plant)
    existing = ga.storage.get_plant(taxon_or_plant) or (fuzzy_hits[0] if fuzzy_hits else None)
    if existing is not None:
        plant = existing
    else:
        taxon = garden_svc.resolve_taxon(ga.storage, ga.catalog, taxon_or_plant)
        plant = garden_svc.add_plant(
            ga.storage,
            taxon=taxon,
            location_id=to,
            status=PlantStatus.TRANSPLANTED,
            planted_at=occurred,
        )
        console.print(
            f"[green]🌱[/green] Created plant [bold]{plant.id}[/bold] ({taxon.display_name})"
        )

    if plant.location_id != to:
        from_bed = from_bed or plant.location_id
        plant.location_id = to
        plant.status = PlantStatus.TRANSPLANTED
        ga.storage.update_plant(plant)

    e = logging.log_event(
        ga.storage,
        plant_query=plant.id,
        type=EventType.TRANSPLANTED,
        occurred_at=occurred,
        location_id=to,
        from_location_id=from_bed,
        notes=notes,
    )
    console.print(
        f"[green]🪴[/green] Logged transplant of [bold]{plant.id}[/bold] → "
        f"[bold]{to}[/bold] at {e.occurred_at:%Y-%m-%d %H:%M}"
    )


@log_app.command("seed")
def log_seed(
    taxon: Annotated[str, typer.Argument(help="Cultivar/species.")],
    where: Annotated[
        str | None, typer.Option("--in", help="Location id (e.g. a seed tray).")
    ] = None,
    when: Annotated[
        str | None, typer.Option(help="ISO timestamp; defaults to now.")
    ] = None,
    notes: Annotated[str | None, typer.Option("--notes", "-n")] = None,
) -> None:
    """Log seeding (creates a Plant in status=seeded)."""
    ga = garden_app()
    occurred = datetime.fromisoformat(when) if when else datetime.now(UTC)
    tx = garden_svc.resolve_taxon(ga.storage, ga.catalog, taxon)
    plant = garden_svc.add_plant(
        ga.storage,
        taxon=tx,
        location_id=where,
        status=PlantStatus.SEEDED,
        planted_at=occurred,
    )
    logging.log_event(
        ga.storage,
        plant_query=plant.id,
        type=EventType.SEEDED,
        occurred_at=occurred,
        location_id=where,
        notes=notes,
    )
    console.print(
        f"[green]🌱[/green] Seeded {tx.display_name} → [bold]{plant.id}[/bold]"
    )

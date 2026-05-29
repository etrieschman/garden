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
from garden.recommendations.amendments import AmendmentCatalog
from garden.services import garden as garden_svc
from garden.services import logging


def _validate_amendment_type(event_type: EventType, details: dict[str, Any]) -> None:
    """For AMENDED / FERTILIZED, refuse unknown amendment keys unless the user
    supplies NPK overrides. Keeps the catalog the single source of typo-checked
    truth without locking users out of new amendments."""
    if event_type not in (EventType.AMENDED, EventType.FERTILIZED):
        return
    type_key = details.get("type")
    if not type_key:
        return
    catalog = AmendmentCatalog.load_default()
    if catalog.get(type_key) is not None:
        return
    has_override = any(details.get(k) is not None for k in ("n_pct", "p_pct", "k_pct"))
    if has_override:
        return
    known = ", ".join(catalog.keys())
    raise typer.BadParameter(
        f"unknown amendment {type_key!r}. "
        f"Known: {known}. For a new amendment, also pass --n-pct / --p-pct / --k-pct.",
        param_hint="--type",
    )


_FANOUT_BLOCKED = {EventType.DIED, EventType.REMOVED}


def _fan_out_to_bed(
    ga: Any,
    bed_id: str,
    event_type: EventType,
    occurred_at: datetime | None,
    details: dict[str, Any],
    notes: str | None,
    photo_path: str | None = None,
) -> None:
    """Log `event_type` against every alive plant in `bed_id`. Used by `--all`."""
    if event_type in _FANOUT_BLOCKED:
        raise typer.BadParameter(
            f"`--all` is not allowed for {event_type.value} — terminal events "
            "must target individual plants."
        )
    bed = ga.storage.get_location(bed_id)
    if bed is None:
        raise typer.BadParameter(
            f"`--all` requires the target to be a bed; {bed_id!r} is not a known bed."
        )
    targets = [p for p in ga.storage.list_plants(location_id=bed.id) if p.is_alive]
    if not targets:
        console.print(f"[yellow]![/yellow] no alive plants in {bed.id!r} — nothing to log")
        return
    for plant in targets:
        logging.log_event(
            ga.storage,
            plant_query=plant.id,
            location_id=bed.id,
            type=event_type,
            occurred_at=occurred_at,
            details=details,
            notes=notes,
            photo_path=photo_path,
        )
    suffix = f"  {details}" if details else ""
    console.print(
        f"[green]✓[/green] Logged {event_type.value} for [bold]{len(targets)}[/bold] "
        f"plant(s) in [bold]{bed.id}[/bold]{suffix}"
    )


def _resolve_target(storage: Any, target: str) -> tuple[str | None, str | None]:
    """Resolve a positional target to (plant_query, location_id).

    Plants take precedence over beds. Returns one populated and one None so
    `log_event` can decide whether to attach to a plant or a location.
    """
    if storage.get_plant(target) or storage.find_plants(target):
        return target, None
    if storage.get_location(target):
        return None, target
    raise typer.BadParameter(
        f"no plant or bed matches {target!r}. "
        "Use `garden bed list` or `garden list` to see what's available."
    )


def _build_log_command(event_type: EventType, model: type[BaseModel]) -> Callable[..., None]:
    """Build a Typer-compatible callable for `garden log <event_type>`.

    Common params (target, --when, --notes) plus one --flag per field on the
    detail model. `target` is a plant id/name or a bed id (auto-detected, plant
    wins on conflict). Validates inputs through the Pydantic model before
    forwarding to the logging service.
    """

    def _impl(**kwargs: Any) -> None:
        target = kwargs.pop("target")
        when = kwargs.pop("when", None)
        notes = kwargs.pop("notes", None)
        photo = kwargs.pop("photo", None)
        fan_out = kwargs.pop("all", False)
        details_raw = {k: v for k, v in kwargs.items() if v is not None}
        details = model.model_validate(details_raw).model_dump(exclude_none=True)
        _validate_amendment_type(event_type, details)
        occurred = datetime.fromisoformat(when) if when else None
        ga = garden_app()

        if fan_out:
            _fan_out_to_bed(ga, target, event_type, occurred, details, notes, photo)
            return

        plant_query, location_id = _resolve_target(ga.storage, target)
        try:
            e = logging.log_event(
                ga.storage,
                plant_query=plant_query,
                location_id=location_id,
                type=event_type,
                occurred_at=occurred,
                details=details,
                notes=notes,
                photo_path=photo,
            )
        except ValueError as err:
            raise typer.BadParameter(str(err)) from err
        suffix = f"  {details}" if details else ""
        target_label = e.plant_id or e.location_id or target
        console.print(
            f"[green]✓[/green] Logged {event_type.value} for [bold]{target_label}[/bold] "
            f"at {e.occurred_at:%Y-%m-%d %H:%M}{suffix}"
        )

    params: list[inspect.Parameter] = [
        inspect.Parameter(
            "target",
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
        inspect.Parameter(
            "photo",
            kind=inspect.Parameter.KEYWORD_ONLY,
            default=typer.Option(
                None, "--photo", help="Path to a photo to attach to this event."
            ),
            annotation=str | None,
        ),
        inspect.Parameter(
            "all",
            kind=inspect.Parameter.KEYWORD_ONLY,
            default=typer.Option(
                False,
                "--all",
                help=(
                    "Target must be a bed; fan this event out to every alive plant in it. "
                    "Not allowed for died/removed."
                ),
            ),
            annotation=bool,
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


@log_app.command(EventType.TRANSPLANTED.value)
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

    try:
        e = logging.log_event(
            ga.storage,
            plant_query=plant.id,
            type=EventType.TRANSPLANTED,
            occurred_at=occurred,
            location_id=to,
            from_location_id=from_bed,
            notes=notes,
        )
    except ValueError as err:
        raise typer.BadParameter(str(err)) from err
    console.print(
        f"[green]🪴[/green] Logged transplant of [bold]{plant.id}[/bold] → "
        f"[bold]{to}[/bold] at {e.occurred_at:%Y-%m-%d %H:%M}"
    )


# ---------- review / fix mistakes ----------


@log_app.command("list")
def log_list(
    plant: Annotated[str | None, typer.Option("--plant", help="Filter to one plant.")] = None,
    bed: Annotated[str | None, typer.Option("--bed", help="Filter to one bed.")] = None,
    type: Annotated[
        EventType | None, typer.Option("--type", help="Filter to one event type.")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max rows.")] = 20,
) -> None:
    """List recent events (with short ids for `garden log delete`)."""
    from rich.table import Table

    ga = garden_app()
    events = ga.storage.list_events(plant_id=plant, location_id=bed)
    if type is not None:
        events = [e for e in events if e.type == type]
    events = events[:limit]
    if not events:
        console.print("[dim]no events match[/dim]")
        return
    t = Table(title=f"Events (latest {len(events)})")
    t.add_column("id")
    t.add_column("when")
    t.add_column("type")
    t.add_column("target")
    t.add_column("details")
    t.add_column("notes")
    for e in events:
        target_label = e.plant_id or e.location_id or "—"
        details = ", ".join(f"{k}={v}" for k, v in (e.details or {}).items())
        t.add_row(
            str(e.id)[:8],
            e.occurred_at.strftime("%Y-%m-%d %H:%M"),
            e.type.value,
            target_label,
            details,
            (e.notes or "")[:40],
        )
    console.print(t)


@log_app.command("delete")
def log_delete(
    id_prefix: Annotated[
        str, typer.Argument(help="Event id or unique prefix (from `garden log list`).")
    ],
    yes: Annotated[bool, typer.Option("-y", "--yes", help="Skip confirmation.")] = False,
) -> None:
    """Delete an event. Find its id with `garden log list`."""
    ga = garden_app()
    matches = ga.storage.find_events_by_prefix(id_prefix)
    if not matches:
        console.print(f"[red]✗[/red] no event matches {id_prefix!r}")
        raise typer.Exit(code=1)
    if len(matches) > 1:
        console.print(
            f"[yellow]![/yellow] {id_prefix!r} is ambiguous ({len(matches)} matches). "
            "Use more characters of the id."
        )
        raise typer.Exit(code=1)
    event = matches[0]
    target_label = event.plant_id or event.location_id or "—"
    console.print(
        f"About to delete: [bold]{event.type.value}[/bold] on [bold]{target_label}[/bold] "
        f"at {event.occurred_at:%Y-%m-%d %H:%M}"
    )
    if not yes and not typer.confirm("Proceed?"):
        raise typer.Abort()
    ga.storage.delete_event(event.id)
    console.print(f"[green]✓[/green] deleted {str(event.id)[:8]}")


@log_app.command(EventType.SEEDED.value)
def log_seed(
    taxon: Annotated[str, typer.Argument(help="Cultivar/species.")],
    where: Annotated[
        str | None, typer.Option("--in", help="Location id (e.g. a seed tray).")
    ] = None,
    when: Annotated[
        str | None, typer.Option(help="ISO timestamp; defaults to now.")
    ] = None,
    notes: Annotated[str | None, typer.Option("--notes", "-n")] = None,
    label: Annotated[
        str | None,
        typer.Option(help="Friendly name you'll use to refer to this plant."),
    ] = None,
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
        label=label,
    )
    logging.log_event(
        ga.storage,
        plant_query=plant.id,
        type=EventType.SEEDED,
        occurred_at=occurred,
        location_id=where,
        notes=notes,
    )
    suffix = f" [dim]({label!r})[/dim]" if label else ""
    console.print(
        f"[green]🌱[/green] Seeded {tx.display_name} → [bold]{plant.id}[/bold]{suffix}"
    )

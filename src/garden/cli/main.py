"""Garden CLI entry point.

Conventions:
- Verbs ride at the top level: `garden water gem`, `garden harvest gem`.
- `garden log <verb>` is also accepted for the long form.
- `--strict` (or env `GARDEN_STRICT=1`) disables fuzzy/inferred behavior.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from garden.app import GardenApp
from garden.config.yaml_config import BedConfig
from garden.domain import EventType, LocationKind, PlantStatus
from garden.services import insights, logging, recommend, setup

app = typer.Typer(
    name="garden",
    help="Track a home garden — plants, events, observations, recommendations.",
    no_args_is_help=True,
)
bed_app = typer.Typer(help="Manage beds / locations.", no_args_is_help=True)
log_app = typer.Typer(help="Log a discrete event.", no_args_is_help=True)
app.add_typer(bed_app, name="bed")
app.add_typer(log_app, name="log")

console = Console()


def _strict() -> bool:
    return os.environ.get("GARDEN_STRICT", "").lower() in ("1", "true", "yes")


def _app() -> GardenApp:
    return GardenApp.from_config()


# ---------- bed ----------


@bed_app.command("add")
def bed_add(
    id: Annotated[str, typer.Argument(help="Short id / slug, e.g. 'patio-north'.")],
    kind: Annotated[LocationKind, typer.Option(help="raised_bed / in_ground / container / ...")] = LocationKind.RAISED_BED,
    dim: Annotated[str | None, typer.Option(help="Dimensions like 240x120x30cm or 40cm (diameter).")] = None,
    lat: Annotated[float | None, typer.Option(help="Latitude (defaults to garden default).")] = None,
    lon: Annotated[float | None, typer.Option(help="Longitude (defaults to garden default).")] = None,
    substrate: Annotated[str | None, typer.Option(help="Soil/medium description.")] = None,
    name: Annotated[str | None, typer.Option(help="Human-readable name (defaults to id).")] = None,
) -> None:
    """Add a bed/location."""
    ga = _app()
    dims = setup.parse_dimensions(dim) if dim else None
    final_lat = lat if lat is not None else ga.config.default_lat
    final_lon = lon if lon is not None else ga.config.default_lon
    if _strict() and (final_lat is None or final_lon is None):
        raise typer.BadParameter("--lat and --lon required in strict mode")

    loc = setup.add_location(
        ga.storage,
        id=id,
        name=name,
        kind=kind,
        lat=final_lat,
        lon=final_lon,
        dimensions=dims,
        substrate_medium=substrate,
    )

    # Update yaml snapshot
    existing = ga.config.find_bed(id)
    bed_cfg = BedConfig(
        id=loc.id,
        name=loc.name,
        kind=loc.kind.value,
        lat=loc.lat,
        lon=loc.lon,
        dimensions=loc.dimensions.model_dump(exclude_none=True) if loc.dimensions else None,
        substrate=loc.substrate.model_dump(exclude_none=True) if loc.substrate else None,
    )
    if existing:
        ga.config.beds = [b if b.id != id else bed_cfg for b in ga.config.beds]
    else:
        ga.config.beds.append(bed_cfg)
    ga.save_config()

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
    ga = _app()
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
    plants = ga.storage.list_plants()
    counts: dict[str, int] = {}
    for p in plants:
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


# ---------- plant ----------


@app.command("plant")
def plant_add(
    taxon_query: Annotated[str, typer.Argument(help="Cultivar/species, e.g. 'Garden Gem'.")],
    to: Annotated[str | None, typer.Option(help="Bed id to plant into.")] = None,
    status: Annotated[PlantStatus, typer.Option(help="Initial status.")] = PlantStatus.TRANSPLANTED,
) -> None:
    """Add a plant to a bed (creates a Taxon if needed)."""
    ga = _app()
    if _strict() and to is None:
        raise typer.BadParameter("--to required in strict mode")
    taxon = setup.resolve_taxon(ga.storage, ga.catalog, taxon_query)
    plant = setup.add_plant(ga.storage, taxon=taxon, location_id=to, status=status)
    console.print(
        f"[green]🌱[/green] Created plant [bold]{plant.id}[/bold] "
        f"({taxon.display_name}) in [bold]{to or '—'}[/bold]"
    )


# ---------- log (the common verbs as top-level shortcuts) ----------


def _log_simple(
    type: EventType, plant: str, details: dict | None = None, notes: str | None = None
) -> None:
    ga = _app()
    e = logging.log_event(
        ga.storage, plant_query=plant, type=type, details=details or {}, notes=notes
    )
    console.print(
        f"[green]✓[/green] Logged {type.value} for [bold]{e.plant_id}[/bold] "
        f"at {e.occurred_at:%Y-%m-%d %H:%M}"
    )


@app.command("water")
def water(
    plant: str,
    amount_l: Annotated[float | None, typer.Option("--amount", "--amount-l", help="Liters.")] = None,
    notes: Annotated[str | None, typer.Option("--notes", "-n")] = None,
) -> None:
    """Log a watering."""
    details = {"amount_l": amount_l} if amount_l is not None else {}
    _log_simple(EventType.WATERED, plant, details, notes)


@app.command("fertilize")
def fertilize(
    plant: str,
    product: Annotated[str | None, typer.Option("--with", help="Fertilizer/product name.")] = None,
    notes: Annotated[str | None, typer.Option("--notes", "-n")] = None,
) -> None:
    """Log a fertilization."""
    details = {"product": product} if product else {}
    _log_simple(EventType.FERTILIZED, plant, details, notes)


@app.command("harvest")
def harvest(
    plant: str,
    weight_g: Annotated[float | None, typer.Option("--weight", "--weight-g", help="Grams.")] = None,
    count: Annotated[int | None, typer.Option("--count")] = None,
    notes: Annotated[str | None, typer.Option("--notes", "-n")] = None,
) -> None:
    """Log a harvest."""
    details: dict = {}
    if weight_g is not None:
        details["weight_g"] = weight_g
    if count is not None:
        details["count"] = count
    _log_simple(EventType.HARVESTED, plant, details, notes)


@app.command("prune")
def prune(
    plant: str,
    what: Annotated[str | None, typer.Option("--what", help="What was removed.")] = None,
    notes: Annotated[str | None, typer.Option("--notes", "-n")] = None,
) -> None:
    """Log a pruning."""
    details = {"what": what} if what else {}
    _log_simple(EventType.PRUNED, plant, details, notes)


# ---------- log subcommands (creation verbs) ----------


@log_app.command("transplant")
def log_transplant(
    taxon_or_plant: Annotated[
        str, typer.Argument(help="Plant id (existing) or taxon name (new plant).")
    ],
    to: Annotated[str, typer.Option(help="Bed id to transplant into.")],
    from_bed: Annotated[str | None, typer.Option("--from", help="Source location, if known.")] = None,
    when: Annotated[str | None, typer.Option(help="ISO timestamp; defaults to now.")] = None,
    notes: Annotated[str | None, typer.Option("--notes", "-n")] = None,
) -> None:
    """Log a transplant. Creates the Plant if `taxon_or_plant` doesn't match one."""
    ga = _app()
    if not ga.storage.get_location(to):
        raise typer.BadParameter(f"bed not found: {to!r}. Add it with `garden bed add {to} ...`")
    occurred = datetime.fromisoformat(when) if when else datetime.now(UTC).replace(tzinfo=None)

    existing = ga.storage.get_plant(taxon_or_plant) or (
        ga.storage.find_plants(taxon_or_plant)[0]
        if ga.storage.find_plants(taxon_or_plant)
        else None
    )
    if existing is not None:
        plant = existing
    else:
        taxon = setup.resolve_taxon(ga.storage, ga.catalog, taxon_or_plant)
        plant = setup.add_plant(
            ga.storage, taxon=taxon, location_id=to, status=PlantStatus.TRANSPLANTED, planted_at=occurred
        )
        console.print(f"[green]🌱[/green] Created plant [bold]{plant.id}[/bold] ({taxon.display_name})")

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
    where: Annotated[str | None, typer.Option("--in", help="Location id (e.g. a seed tray).")] = None,
    when: Annotated[str | None, typer.Option(help="ISO timestamp; defaults to now.")] = None,
    notes: Annotated[str | None, typer.Option("--notes", "-n")] = None,
) -> None:
    """Log seeding (creates a Plant in status=seeded)."""
    ga = _app()
    occurred = datetime.fromisoformat(when) if when else datetime.now(UTC).replace(tzinfo=None)
    tx = setup.resolve_taxon(ga.storage, ga.catalog, taxon)
    plant = setup.add_plant(
        ga.storage, taxon=tx, location_id=where, status=PlantStatus.SEEDED, planted_at=occurred
    )
    logging.log_event(
        ga.storage,
        plant_query=plant.id,
        type=EventType.SEEDED,
        occurred_at=occurred,
        location_id=where,
        notes=notes,
    )
    console.print(f"[green]🌱[/green] Seeded {tx.display_name} → [bold]{plant.id}[/bold]")


# ---------- read-side ----------


@app.command("list")
def list_plants() -> None:
    ga = _app()
    plants = ga.storage.list_plants()
    if not plants:
        console.print("[dim]no plants yet — `garden plant <taxon>`[/dim]")
        return
    t = Table(title="Plants")
    t.add_column("id")
    t.add_column("taxon")
    t.add_column("location")
    t.add_column("status")
    t.add_column("planted")
    for p in plants:
        taxon = ga.storage.get_taxon(p.taxon_id)
        t.add_row(
            p.id,
            taxon.display_name if taxon else p.taxon_id,
            p.location_id or "—",
            p.status.value,
            p.planted_at.strftime("%Y-%m-%d") if p.planted_at else "—",
        )
    console.print(t)


@app.command("show")
def show(plant: str) -> None:
    """Show details for one plant."""
    ga = _app()
    pl = setup.resolve_plant(ga.storage, plant)
    status = insights.plant_status(ga.storage, pl.id)
    taxon = status.taxon.display_name if status.taxon else pl.taxon_id
    loc = status.location.name if status.location else "—"
    console.print(f"[bold cyan]{pl.id}[/bold cyan]  ({taxon})")
    console.print(f"  location: {loc}")
    console.print(f"  status:   {pl.status.value}")
    console.print(f"  planted:  {pl.planted_at:%Y-%m-%d}" if pl.planted_at else "  planted:  —")
    if status.last_event:
        e = status.last_event
        console.print(f"  last event: {e.type.value} at {e.occurred_at:%Y-%m-%d %H:%M}")
    events = ga.storage.list_events(plant_id=pl.id)
    if events:
        console.print()
        et = Table(title="Recent events")
        et.add_column("when")
        et.add_column("type")
        et.add_column("details")
        for e in events[:10]:
            et.add_row(
                e.occurred_at.strftime("%Y-%m-%d %H:%M"),
                e.type.value,
                ", ".join(f"{k}={v}" for k, v in (e.details or {}).items()),
            )
        console.print(et)
    if status.active_recommendations:
        console.print()
        rt = Table(title="Recommendations")
        rt.add_column("action")
        rt.add_column("reason")
        rt.add_column("engine")
        for r in status.active_recommendations:
            rt.add_row(r.action, r.reason, r.engine)
        console.print(rt)


@app.command("status")
def status() -> None:
    """Garden overview: beds, plants, and active recommendations."""
    ga = _app()
    locs = ga.storage.list_locations()
    plants = ga.storage.list_plants()
    recs = ga.storage.list_recommendations()
    console.print(f"[bold]{ga.config.name}[/bold] — {len(locs)} beds, {len(plants)} plants, {len(recs)} active recommendations")
    if plants:
        console.print()
        list_plants()
    if recs:
        console.print()
        rt = Table(title="Active recommendations")
        rt.add_column("plant")
        rt.add_column("action")
        rt.add_column("reason")
        rt.add_column("engine")
        for r in recs:
            rt.add_row(r.plant_id or "—", r.action, r.reason, r.engine)
        console.print(rt)


@app.command("recommend")
def cmd_recommend(
    no_weather: Annotated[bool, typer.Option(help="Skip weather fetch (offline).")] = False,
) -> None:
    """Run recommendation engines and persist results."""
    ga = _app()
    weather = None if no_weather else ga.weather
    recs = recommend.refresh_recommendations(ga.storage, ga.engines, weather=weather)
    console.print(f"[green]✓[/green] Generated {len(recs)} recommendations")
    for r in recs:
        target = r.plant_id or r.location_id or "—"
        console.print(f"  • [bold]{r.action}[/bold] [{target}] — {r.reason}")


@app.command("weather")
def cmd_weather(
    days_back: Annotated[int, typer.Option(help="How many days of history to pull.")] = 14,
    days_forward: Annotated[int, typer.Option(help="Forecast days.")] = 7,
) -> None:
    """Refresh weather observations for all beds with lat/lon."""
    from datetime import date, timedelta

    ga = _app()
    locs = [loc for loc in ga.storage.list_locations() if loc.lat and loc.lon]
    if not locs:
        console.print("[yellow]no beds have lat/lon[/yellow]")
        return
    start = date.today() - timedelta(days=days_back)
    end = date.today() + timedelta(days=days_forward)
    n = 0
    for loc in locs:
        try:
            samples = ga.weather.daily(loc.lat, loc.lon, start, end)
        except Exception as e:
            console.print(f"[red]✗[/red] {loc.id}: {e}")
            continue
        for s in samples:
            if s.rain_mm is not None:
                logging.log_observation(
                    ga.storage,
                    metric="rain_mm",
                    value_numeric=s.rain_mm,
                    unit="mm",
                    location_id=loc.id,
                    occurred_at=s.timestamp,
                    source=f"provider:{ga.weather.name}",
                )
                n += 1
            if s.temp_c_mean is not None:
                logging.log_observation(
                    ga.storage,
                    metric="temp_c_mean",
                    value_numeric=s.temp_c_mean,
                    unit="C",
                    location_id=loc.id,
                    occurred_at=s.timestamp,
                    source=f"provider:{ga.weather.name}",
                )
                n += 1
    console.print(f"[green]✓[/green] Stored {n} weather observations across {len(locs)} beds")


if __name__ == "__main__":
    app()

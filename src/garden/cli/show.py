"""Read-side commands: `garden list`, `show`, `status`, `recommend`, `weather`."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

import typer
from rich.table import Table

from garden.cli._app import app, console, garden_app
from garden.services import garden as garden_svc
from garden.services import insights, logging, recommend


@app.command("list")
def list_plants() -> None:
    """List all plants."""
    ga = garden_app()
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
    ga = garden_app()
    pl = garden_svc.resolve_plant(ga.storage, plant)
    status = insights.plant_status(ga.storage, pl.id)
    taxon = status.taxon.display_name if status.taxon else pl.taxon_id
    loc = status.location.name if status.location else "—"
    console.print(f"[bold cyan]{pl.id}[/bold cyan]  ({taxon})")
    console.print(f"  location: {loc}")
    console.print(f"  status:   {pl.status.value}")
    console.print(
        f"  planted:  {pl.planted_at:%Y-%m-%d}" if pl.planted_at else "  planted:  —"
    )
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
    ga = garden_app()
    locs = ga.storage.list_locations()
    plants = ga.storage.list_plants()
    recs = ga.storage.list_recommendations()
    console.print(
        f"[bold]{ga.meta.name}[/bold] — {len(locs)} beds, {len(plants)} plants, "
        f"{len(recs)} active recommendations"
    )
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
    ga = garden_app()
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
    ga = garden_app()
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
    console.print(
        f"[green]✓[/green] Stored {n} weather observations across {len(locs)} beds"
    )

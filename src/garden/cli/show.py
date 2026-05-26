"""Read-side commands: `garden list`, `show`, `status`, `recommend`, `weather`."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

import typer
from rich.table import Table

from garden.cli._app import app, console, garden_app
from garden.domain import Recommendation
from garden.recommendations import CareProfileBundle
from garden.recommendations.amendments import AmendmentCatalog
from garden.recommendations.care_profile import current_stage
from garden.services import garden as garden_svc
from garden.services import insights, logging, recommend
from garden.services.nutrients import cumulative_nutrients


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
    # GDD + growth stage + nutrient totals (if profile + stages exist)
    nutrient_info = _resolve_plant_nutrition(ga, pl)
    if nutrient_info is not None:
        stage_label, gdd, applied, target = nutrient_info
        console.print(
            f"  GDD since transplant: {gdd:.0f}  →  stage: [bold]{stage_label}[/bold]"
        )
        if target is not None:
            deficit_n = target.n_g - applied.n_g
            deficit_label = (
                f"deficit {deficit_n:+.1f}g"
                if abs(deficit_n) > 0.05
                else "on target"
            )
            console.print(
                f"  N applied this stage: [bold]{applied.n_g:.1f}g[/bold] "
                f"vs target {target.n_g:.1f}g  ({deficit_label})"
            )
            console.print(
                f"  P₂O₅: {applied.p2o5_g:.1f}g / target {target.p2o5_g:.1f}g     "
                f"K₂O: {applied.k2o_g:.1f}g / target {target.k2o_g:.1f}g"
            )
        else:
            console.print(
                f"  N applied this stage: [bold]{applied.n_g:.1f}g[/bold]   "
                f"P₂O₅: {applied.p2o5_g:.1f}g   K₂O: {applied.k2o_g:.1f}g  "
                f"[dim](no target set)[/dim]"
            )

    if status.active_recommendations:
        console.print()
        rt = Table(title="Recommendations")
        rt.add_column("action")
        rt.add_column("due")
        rt.add_column("reason")
        rt.add_column("engine")
        for r in status.active_recommendations:
            rt.add_row(r.action, _due_label(r, datetime.now(UTC)), r.reason, r.engine)
        console.print(rt)


def _resolve_plant_nutrition(ga, pl):
    """Return (stage_label, gdd, applied_NutrientTotals, target_NutrientTotals | None)
    or None if the plant has no profile/stage available."""
    from garden.recommendations.care_profile import _stage_start_date, _stage_targets

    taxon = ga.storage.get_taxon(pl.taxon_id)
    if not taxon:
        return None
    bundle = CareProfileBundle.load_default()
    profile = bundle.resolve(taxon.scientific_name, taxon.cultivar)
    if not profile or not profile.fertilize or not profile.fertilize.stages:
        return None
    ctx = recommend.build_context(ga.storage, weather=None)
    stage, gdd = current_stage(pl, profile, ctx)
    if stage is None or gdd is None:
        return None

    # Sum nutrients applied since this stage began
    transplant = next(
        (e.occurred_at for e in ctx.events_by_plant.get(pl.id, [])
         if e.type.value == "transplanted"),
        None,
    )
    observations = (
        ctx.observations_by_location.get(pl.location_id, []) if pl.location_id else []
    )
    base_temp = profile.gdd.base_temp_c if profile.gdd else 10.0
    stage_start = (
        _stage_start_date(profile, stage, transplant, observations, base_temp)
        if transplant is not None
        else None
    )
    bed_events = (
        ctx.bed_events_by_location.get(pl.location_id, []) if pl.location_id else []
    )
    # Count everything since transplant — see care_profile._check_fertilize_by_nutrients
    # for why (slow-release amendments span multiple stages).
    applied = cumulative_nutrients(
        ctx.events_by_plant.get(pl.id, []) + bed_events,
        AmendmentCatalog.load_default(),
        since=transplant,
    )

    target = None
    if stage.target_n_g_per_week is not None and stage_start is not None:
        from garden.recommendations.care_profile import _container_multiplier
        multiplier = _container_multiplier(pl, ctx, profile)
        weeks = max(0.0, (ctx.now - stage_start).total_seconds() / (86400 * 7))
        target = _stage_targets(stage, weeks, multiplier)

    return stage.name.replace("_", " "), gdd, applied, target


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
    within: Annotated[
        int, typer.Option("--within", help="Show recommendations due within N days.")
    ] = 7,
    no_weather: Annotated[bool, typer.Option(help="Skip weather fetch (offline).")] = False,
    show_all: Annotated[
        bool, typer.Option("--all", help="Show every rec regardless of due date.")
    ] = False,
) -> None:
    """Run recommendation engines and show what's coming, sorted by due date."""
    ga = garden_app()
    weather = None if no_weather else ga.weather
    recs = recommend.refresh_recommendations(ga.storage, ga.engines, weather=weather)
    now = datetime.now(UTC)
    cutoff = now + timedelta(days=within)
    visible = (
        recs if show_all else [r for r in recs if r.due_at is None or r.due_at <= cutoff]
    )
    visible.sort(key=lambda r: r.due_at or now + timedelta(days=365))

    header_when = "all recommendations" if show_all else f"next {within} days"
    console.print(
        f"[bold]Recommendations[/bold] ({header_when}, as of {now:%Y-%m-%d %H:%M})"
    )
    if not visible:
        console.print("  [dim]nothing in this window[/dim]")
        return
    for r in visible:
        console.print(
            f"  [bold]{_due_label(r, now)}[/bold]  "
            f"{r.action:<16} {r.plant_id or r.location_id or '—':<28} {r.reason}"
        )


def _due_label(rec: Recommendation, now: datetime) -> str:
    if rec.due_at is None:
        return "no date".rjust(10)
    delta = rec.due_at - now
    days = round(delta.total_seconds() / 86400)
    if days < 0:
        return f"{-days}d late".rjust(10)
    if days == 0:
        return "TODAY".rjust(10)
    if days == 1:
        return "tomorrow".rjust(10)
    return f"in {days}d".rjust(10)


@app.command("amendments")
def cmd_amendments() -> None:
    """List the known amendment + fertilizer types (the `--type` choices for `garden log amended/fertilized`)."""
    catalog = AmendmentCatalog.load_default()
    t = Table(title=f"Amendments + fertilizers ({len(catalog.entries)} entries)")
    t.add_column("key")
    t.add_column("name")
    t.add_column("kind")
    t.add_column("kg/L", justify="right")
    t.add_column("NPK", justify="right")
    for e in catalog.entries:
        t.add_row(
            e.key,
            e.display,
            e.kind,
            f"{e.kg_per_l:g}",
            f"{e.npk[0]:g}-{e.npk[1]:g}-{e.npk[2]:g}",
        )
    console.print(t)


@app.command("weather")
def cmd_weather(
    days_back: Annotated[int, typer.Option(help="How many days of history to pull.")] = 14,
    days_forward: Annotated[int, typer.Option(help="Forecast days.")] = 7,
    no_store: Annotated[
        bool, typer.Option("--no-store", help="Display only; don't write observations.")
    ] = False,
) -> None:
    """Fetch and display weather for every bed (and store observations by default)."""
    ga = garden_app()
    locs = [loc for loc in ga.storage.list_locations() if loc.lat and loc.lon]
    if not locs:
        console.print("[yellow]no beds have lat/lon[/yellow]")
        return
    start = date.today() - timedelta(days=days_back)
    end = date.today() + timedelta(days=days_forward)
    today = date.today()
    stored = 0
    for loc in locs:
        try:
            samples = ga.weather.daily(loc.lat, loc.lon, start, end)
        except Exception as e:
            console.print(f"[red]✗[/red] {loc.id}: {e}")
            continue

        # ---- display ----
        title = f"{loc.id} — {ga.weather.name}  ({loc.lat:.4f}, {loc.lon:.4f})  {start} → {end}"
        t = Table(title=title)
        t.add_column("date")
        t.add_column("min", justify="right")
        t.add_column("mean", justify="right")
        t.add_column("max", justify="right")
        t.add_column("rain mm", justify="right")
        t.add_column("sun h", justify="right")
        t.add_column("")
        rain_total = 0.0
        gdd10_total = 0.0
        for s in samples:
            s_date = s.timestamp.date()
            if s.rain_mm is not None:
                rain_total += s.rain_mm
            if s.temp_c_mean is not None:
                gdd10_total += max(0.0, s.temp_c_mean - 10.0)
            marker = (
                "today" if s_date == today else ("forecast" if s_date > today else "")
            )
            row_style = "bold cyan" if s_date == today else None
            t.add_row(
                s_date.isoformat(),
                f"{s.temp_c_min:.0f}" if s.temp_c_min is not None else "—",
                f"{s.temp_c_mean:.0f}" if s.temp_c_mean is not None else "—",
                f"{s.temp_c_max:.0f}" if s.temp_c_max is not None else "—",
                f"{s.rain_mm:.1f}" if s.rain_mm is not None else "—",
                f"{s.sunshine_hours:.1f}" if s.sunshine_hours is not None else "—",
                marker,
                style=row_style,
            )
        console.print(t)
        console.print(
            f"  [dim]totals:[/dim] rain {rain_total:.1f} mm   "
            f"GDD (base 10°C): {gdd10_total:.0f}"
        )

        # ---- store (unless --no-store) ----
        if no_store:
            continue
        # Idempotent refresh: drop existing provider observations for this
        # location in the same window, then insert. Prevents the GDD/rain
        # accumulator from double-counting if the user runs `weather` twice.
        window_start = datetime(start.year, start.month, start.day, tzinfo=UTC)
        window_end = datetime(end.year, end.month, end.day, 23, 59, tzinfo=UTC)
        ga.storage.delete_observations(
            location_id=loc.id,
            source_prefix="provider:",
            since=window_start,
            until=window_end,
        )
        for s in samples:
            for metric, value, unit in (
                ("rain_mm", s.rain_mm, "mm"),
                ("temp_c_mean", s.temp_c_mean, "C"),
                ("temp_c_min", s.temp_c_min, "C"),
                ("temp_c_max", s.temp_c_max, "C"),
                ("sunshine_hours", s.sunshine_hours, "h"),
            ):
                if value is None:
                    continue
                logging.log_observation(
                    ga.storage,
                    metric=metric,
                    value_numeric=value,
                    unit=unit,
                    location_id=loc.id,
                    occurred_at=s.timestamp,
                    source=f"provider:{ga.weather.name}",
                )
                stored += 1

    if no_store:
        console.print("[dim]--no-store: nothing written[/dim]")
    else:
        console.print(f"[green]✓[/green] Stored {stored} observations across {len(locs)} beds")

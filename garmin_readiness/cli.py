from __future__ import annotations

import logging
import os
import sys
from datetime import date, timedelta
from typing import Optional

from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .client import get_api
from .history import (
    baseline_stats,
    composite_score,
    history_for_chart,
    load,
    save,
    z_score,
    LOWER_IS_BETTER,
    SCORED_FIELDS,
)
from .metrics import DailyMetrics, available_count, fetch_metrics

console = Console()

FIELD_LABELS: dict[str, tuple[str, str]] = {
    # field: (display name, unit)
    "sleep_score":           ("Sleep Score",          "/100"),
    "sleep_seconds":         ("Sleep Duration",       ""),
    "hrv_last_night":        ("HRV Last Night",       " ms"),
    "hrv_weekly_avg":        ("HRV Weekly Avg",       " ms"),
    "body_battery_morning":  ("Body Battery",         "/100"),
    "avg_stress":            ("Avg Stress",           "/100"),
    "rest_stress":           ("Rest Stress",          "/100"),
    "acwr":                  ("Acute:Chronic Ratio",  ""),
    "training_load_acute":   ("Acute Load (7d)",      ""),
    "training_load_chronic": ("Chronic Load (28d)",   ""),
    "vo2_max":               ("VO2 Max",              " ml/kg/min"),
}


def _fmt_value(field: str, value: Optional[float]) -> str:
    if value is None:
        return "—"
    if field == "sleep_seconds":
        h, rem = divmod(int(value), 3600)
        m = rem // 60
        return f"{h}h {m:02d}m"
    if field in ("sleep_score", "body_battery_morning", "avg_stress", "rest_stress"):
        return f"{value:.0f}"
    if field in ("hrv_last_night", "hrv_weekly_avg", "vo2_max"):
        return f"{value:.1f}"
    if field == "acwr":
        return f"{value:.2f}"
    if field in ("training_load_acute", "training_load_chronic"):
        return f"{value:.0f}"
    return f"{value:.1f}"


def _z_bar(z: Optional[float], width: int = 12) -> Text:
    """Compact text bar centred at 0, coloured by z-score."""
    if z is None:
        return Text("—", style="dim")
    clamped = max(-2.0, min(2.0, z))
    filled = int(abs(clamped) / 2.0 * (width // 2))
    bar = [" "] * width
    mid = width // 2
    if clamped >= 0:
        for i in range(mid, mid + filled):
            bar[i] = "█"
    else:
        for i in range(mid - filled, mid):
            bar[i] = "█"

    colour = "green" if z >= 0.5 else ("red" if z <= -0.5 else "yellow")
    sign = "+" if z >= 0 else ""
    label = f"{sign}{z:.2f}σ"
    t = Text("".join(bar), style=colour)
    t.append(f" {label}", style=colour)
    return t


def _readiness_label(z: Optional[float]) -> tuple[str, str]:
    """Returns (label, colour) for the composite z-score."""
    if z is None:
        return "Building baseline…", "dim"
    if z >= 1.0:
        return "ABOVE AVERAGE", "bold green"
    if z >= 0.25:
        return "GOOD", "green"
    if z >= -0.25:
        return "AVERAGE", "yellow"
    if z >= -1.0:
        return "BELOW AVERAGE", "red"
    return "LOW", "bold red"


def _sparkline(points: list[Optional[float]], width: int = 20) -> Text:
    bars = " ▁▂▃▄▅▆▇█"
    values = [p for p in points if p is not None]
    if not values:
        return Text("no data", style="dim")
    lo, hi = min(values), max(values)
    span = hi - lo or 1

    result = Text()
    for p in points[-width:]:
        if p is None:
            result.append("·", style="dim")
        else:
            idx = int((p - lo) / span * (len(bars) - 1))
            colour = "green" if p >= 0.25 else ("red" if p <= -0.25 else "yellow")
            result.append(bars[idx], style=colour)
    return result


def _render_dashboard(m: DailyMetrics, stats: dict, comp_z: Optional[float]) -> None:
    target = m.date

    # ── Header ──────────────────────────────────────────────────────────────
    label, colour = _readiness_label(comp_z)
    tags = []
    if m.hrv_status:
        tags.append(f"HRV {m.hrv_status.title()}")
    if m.training_status_label:
        tags.append(f"Training {m.training_status_label}")
    if m.acwr is not None:
        acwr_tag = f"ACWR {m.acwr:.2f}"
        if m.acwr_status:
            acwr_tag += f" ({m.acwr_status.replace('_', ' ').lower()})"
        tags.append(acwr_tag)
    header = Text()
    header.append(f"Trading Readiness  {target.strftime('%a %d %b %Y')}", style="bold")
    if comp_z is not None:
        header.append(f"\nComposite: ", style="dim")
        header.append(f"{comp_z:+.2f}σ  {label}", style=colour)
    else:
        header.append(f"\n{label}", style=colour)
    if tags:
        header.append(f"\n{' · '.join(tags)}", style="dim")

    console.print()
    console.print(Panel(header, box=box.ROUNDED, expand=False))

    # ── Metrics table ────────────────────────────────────────────────────────
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
    table.add_column("Metric", style="", min_width=22)
    table.add_column("Today", justify="right", min_width=10)
    table.add_column("30d Avg", justify="right", min_width=10)
    table.add_column("Deviation", min_width=18)

    for field, (label_str, unit) in FIELD_LABELS.items():
        value = getattr(m, field)
        val_str = _fmt_value(field, value) + (unit if value is not None else "")

        # ACWR: append Garmin's own status badge next to the value
        if field == "acwr" and m.acwr_status and value is not None:
            badge = m.acwr_status.replace("_", " ").title()
            val_str = f"{val_str}  [{badge}]"

        if field in stats:
            mean, std = stats[field]
            avg_str = _fmt_value(field, mean) + unit
            z = z_score(value, mean, std, field) if value is not None else None
            bar = _z_bar(z)
        elif field in ("training_load_chronic", "vo2_max") and value is not None:
            # Context-only fields: show value but no deviation scored
            avg_str = "—"
            bar = Text("(not scored)", style="dim")
        else:
            avg_str = "—"
            bar = Text("—", style="dim")

        table.add_row(label_str, val_str, avg_str, bar)

    console.print(table)

    # ── Trend sparkline ──────────────────────────────────────────────────────
    history = history_for_chart(days=14)
    spark_vals = [v for _, v in history]
    spark = _sparkline(spark_vals)
    console.print(f"  14-day trend  ", end="")
    console.print(spark)

    n_metrics = len(stats)
    status = "building — need more history" if not stats else f"{n_metrics} metrics tracked"
    console.print(f"\n  [dim]Baseline: {status} (30-day rolling window)[/dim]")
    console.print()


def _load_or_fetch(target: date, api=None, force: bool = False) -> DailyMetrics:
    if not force:
        cached = load(target)
        if cached is not None and available_count(cached) > 0:
            return cached

    if api is None:
        raise RuntimeError("API client required to fetch data")

    m = fetch_metrics(api, target)
    save(m)
    return m


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.WARNING)

    import argparse

    parser = argparse.ArgumentParser(description="Garmin → Trading Readiness")
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Target date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Force re-fetch from Garmin Connect even if cached",
    )
    parser.add_argument(
        "--backfill",
        type=int,
        metavar="DAYS",
        help="Fetch and store the last N days to build a baseline",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show debug logs",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, force=True)

    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    if not email or not password:
        console.print(
            "[red]GARMIN_EMAIL and GARMIN_PASSWORD must be set "
            "(copy .env.example → .env)[/red]"
        )
        sys.exit(1)

    target = date.fromisoformat(args.date)

    # Backfill mode: fetch historical days to prime the baseline
    if args.backfill:
        console.print(f"[bold]Backfilling {args.backfill} days…[/bold]")
        api = get_api(email, password)
        for i in range(args.backfill, 0, -1):
            d = date.today() - timedelta(days=i)
            cached = load(d)
            if cached and available_count(cached) > 0 and not args.fetch:
                console.print(f"  {d.isoformat()}  [dim]cached[/dim]")
                continue
            console.print(f"  {d.isoformat()}  fetching…", end="")
            try:
                m = fetch_metrics(api, d)
                save(m)
                n = available_count(m)
                console.print(f"  [green]{n} metrics[/green]")
            except Exception as e:
                console.print(f"  [red]error: {e}[/red]")
        console.print("[green]Backfill complete.[/green]\n")
        if not args.fetch and target == date.today():
            # Also fetch today after backfill
            pass

    # Fetch / load today's metrics
    needs_api = args.fetch or load(target) is None
    api = get_api(email, password) if needs_api else None

    with console.status("Fetching metrics…") if needs_api else _null_ctx():
        m = _load_or_fetch(target, api=api, force=args.fetch)

    if available_count(m) == 0:
        console.print(
            f"[yellow]No metrics available for {target}. "
            "Sync your watch and try again.[/yellow]"
        )
        sys.exit(0)

    stats = baseline_stats(target)
    comp_z = composite_score(m, stats)

    _render_dashboard(m, stats, comp_z)


class _null_ctx:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


if __name__ == "__main__":
    main()

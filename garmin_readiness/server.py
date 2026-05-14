from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

from .client import get_api
from .display import FIELD_LABELS, fmt_value, readiness_label, enrich_activity
from .report import generate_advice
from .history import (
    baseline_stats,
    composite_score,
    history_for_chart,
    load,
    load_recent_activities,
    save,
    save_activities,
    seven_day_composite_trend_csv,
    z_score,
)
from .metrics import DailyMetrics, available_count, fetch_metrics, fetch_activities, TEXT_FIELDS

load_dotenv()

_advice_cache: dict[str, str] = {}

# Training calendar — 12 weeks starting Mon 18 May 2026
_PLAN_START = date(2026, 5, 18)
assert _PLAN_START.weekday() == 0, "Plan must start on Monday"

# Each week: list of 7 sessions Mon–Sun, each (type, label, duration_min)
# Types: rest | strength | bike | tempo | ftp | ruck | long
_TRAINING_WEEKS: list[list[tuple[str, str, int]]] = [
    # WK 01
    [
        ("rest",     "Rest",                  0),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Easy Spin",            60),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Easy Spin",            60),
        ("ruck",     "Ruck  8 kg",           60),
        ("long",     "Long Ride",            90),
    ],
    # WK 02
    [
        ("rest",     "Rest",                  0),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Zone 2 Steady",        60),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Zone 2 Steady",        60),
        ("ruck",     "Ruck  8–10 kg",        70),
        ("long",     "Long Ride",           105),
    ],
    # WK 03
    [
        ("rest",     "Rest",                  0),
        ("strength", "Light KB",             35),
        ("ftp",      "FTP Test",             60),
        ("strength", "Easy MaxiClimber",     20),
        ("bike",     "Recovery Spin",        60),
        ("ruck",     "Ruck  10 kg",          80),
        ("long",     "Long Ride",           120),
    ],
    # WK 04 (deload)
    [
        ("rest",     "Rest",                  0),
        ("strength", "Light KB",             30),
        ("bike",     "Easy Spin",            45),
        ("strength", "MaxiClimber",          20),
        ("bike",     "Easy Spin",            45),
        ("ruck",     "Ruck  8 kg",           45),
        ("long",     "Long Ride",            75),
    ],
    # WK 05
    [
        ("rest",     "Rest",                  0),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Structured Z2",        60),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Z2 + Hills",           60),
        ("ruck",     "Ruck  10 kg",          75),
        ("long",     "Long Ride",           135),
    ],
    # WK 06
    [
        ("rest",     "Rest",                  0),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Cadence Drills",       60),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Hilly Z2",             60),
        ("ruck",     "Ruck  10–12 kg",       85),
        ("long",     "Long Ride",           140),
    ],
    # WK 07
    [
        ("rest",     "Rest",                  0),
        ("strength", "Light KB",             35),
        ("ftp",      "FTP Re-test",          60),
        ("strength", "Easy MaxiClimber",     25),
        ("tempo",    "Tempo Intervals",      60),
        ("ruck",     "Ruck  12 kg",          95),
        ("long",     "Long Ride",           150),
    ],
    # WK 08 (deload)
    [
        ("rest",     "Rest",                  0),
        ("strength", "Light KB",             30),
        ("bike",     "Easy Spin",            45),
        ("strength", "MaxiClimber",          20),
        ("bike",     "Easy Spin",            45),
        ("ruck",     "Ruck  10 kg",          50),
        ("long",     "Long Ride",            80),
    ],
    # WK 09
    [
        ("rest",     "Rest",                  0),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Z2 Endurance",         60),
        ("strength", "KB + MaxiClimber",     45),
        ("tempo",    "Tempo Intervals",      60),
        ("ruck",     "Ruck  12–15 kg",      105),
        ("long",     "Long Ride",           165),
    ],
    # WK 10
    [
        ("rest",     "Rest",                  0),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Low Cadence",          60),
        ("strength", "KB + MaxiClimber",     45),
        ("tempo",    "Tempo Intervals",      60),
        ("ruck",     "Ruck  12–15 kg",      110),
        ("long",     "Long Ride",           180),
    ],
    # WK 11
    [
        ("rest",     "Rest",                  0),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Z2 Endurance",         60),
        ("strength", "Light KB",             35),
        ("bike",     "Easy Prep Ride",       60),
        ("ruck",     "Easy Ruck  8 kg",      60),
        ("long",     "Long Ride",           210),
    ],
    # WK 12
    [
        ("rest",     "Rest",                  0),
        ("strength", "Light KB",             30),
        ("ftp",      "Final FTP Test",       60),
        ("strength", "Easy MaxiClimber",     20),
        ("bike",     "Easy Spin",            45),
        ("ruck",     "Celebration Ruck",     60),
        ("long",     "Long Ride (Easy)",    120),
    ],
]


def _build_calendar_ctx() -> dict[str, Any]:
    today = date.today()
    weeks = []
    for wk_idx, sessions in enumerate(_TRAINING_WEEKS):
        wk_start = _PLAN_START + timedelta(weeks=wk_idx)
        days = []
        for day_offset, (stype, label, dur) in enumerate(sessions):
            d = wk_start + timedelta(days=day_offset)
            is_today = d == today
            is_past = d < today
            dur_fmt = f"{dur}m" if dur and dur < 60 else (f"{dur // 60}h{dur % 60:02d}m" if dur % 60 else f"{dur // 60}h") if dur else ""
            days.append({
                "date": d,
                "day_num": d.day,
                "month_abbr": d.strftime("%b"),
                "type": stype,
                "label": label,
                "dur_fmt": dur_fmt,
                "is_today": is_today,
                "is_past": is_past,
            })
        weeks.append({"week_num": wk_idx + 1, "start": wk_start, "days": days})
    return {"weeks": weeks, "today": today, "plan_start": _PLAN_START}

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


app = FastAPI(title="Daily Readiness", docs_url=None, redoc_url=None)

_UNSCORED = {"training_load_chronic", "vo2_max"}

_BADGE_STYLES: dict[str, str] = {
    # HRV status
    "BALANCED":   "border-emerald-600 text-emerald-300 bg-emerald-900/30",
    "UNBALANCED": "border-yellow-600 text-yellow-300 bg-yellow-900/30",
    "LOW":        "border-orange-600 text-orange-300 bg-orange-900/30",
    "POOR":       "border-red-600 text-red-300 bg-red-900/30",
    # Training status
    "PRODUCTIVE":    "border-emerald-600 text-emerald-300 bg-emerald-900/30",
    "PEAKING":       "border-emerald-600 text-emerald-300 bg-emerald-900/30",
    "MAINTAINING":   "border-blue-600 text-blue-300 bg-blue-900/30",
    "RECOVERING":    "border-blue-600 text-blue-300 bg-blue-900/30",
    "UNPRODUCTIVE":  "border-yellow-600 text-yellow-300 bg-yellow-900/30",
    "DETRAINING":    "border-orange-600 text-orange-300 bg-orange-900/30",
    "OVERREACHING":  "border-red-600 text-red-300 bg-red-900/30",
    "BELOW TARGET":  "border-yellow-600 text-yellow-300 bg-yellow-900/30",
    # ACWR
    "OPTIMAL":    "border-emerald-600 text-emerald-300 bg-emerald-900/30",
    "HIGH":       "border-orange-600 text-orange-300 bg-orange-900/30",
    "VERY HIGH":  "border-red-600 text-red-300 bg-red-900/30",
}
_DEFAULT_BADGE = "border-slate-600 text-slate-300 bg-slate-800/50"


def _badge_cls(text: str) -> str:
    return _BADGE_STYLES.get(text.upper(), _DEFAULT_BADGE)


def _value_colour(z: Optional[float]) -> str:
    if z is None:
        return "text-white"
    if z >= 1.0:
        return "text-emerald-400"
    if z >= 0.25:
        return "text-green-400"
    if z >= -0.25:
        return "text-yellow-400"
    if z >= -1.0:
        return "text-orange-400"
    return "text-red-400"


def _activity_context_blurb(activities: list[dict]) -> str:
    if not activities:
        return "No workouts cached — use force refresh to load from Garmin."
    n = len(activities)
    latest = activities[0]
    title = (latest.get("name") or latest.get("type_label") or "Activity").strip()
    d = latest.get("date") or ""
    tail = f" ({d[5:].replace('-', ' ')})" if len(d) >= 10 else ""
    if n == 1:
        return f"1 workout in last 7 days · latest: {title}{tail}"
    return f"{n} workouts in last 7 days · latest: {title}{tail}"
    if z >= 0.5:
        return "text-emerald-400"
    if z <= -0.5:
        return "text-red-400"
    return "text-yellow-400"


def _build_context(target: date, force_fetch: bool = False) -> dict[str, Any]:
    api = None
    # Load or fetch
    if force_fetch:
        email = os.getenv("GARMIN_EMAIL", "")
        password = os.getenv("GARMIN_PASSWORD", "")
        if email and password:
            api = get_api(email, password)
            m = fetch_metrics(api, target)
            save(m)
        else:
            m = load(target) or DailyMetrics(date=target)
    else:
        m = load(target) or DailyMetrics(date=target)

    stats = baseline_stats(target)
    comp_z = composite_score(m, stats)
    comp_label, comp_colour = readiness_label(comp_z)

    # Status badges
    badges: list[tuple[str, str]] = []
    if m.hrv_status:
        text = f"HRV {m.hrv_status.title()}"
        badges.append((text, _badge_cls(m.hrv_status)))
    if m.training_status_label:
        text = f"Training {m.training_status_label}"
        badges.append((text, _badge_cls(m.training_status_label)))
    if m.acwr is not None and m.acwr_status:
        status_text = m.acwr_status.replace("_", " ").title()
        text = f"ACWR {m.acwr:.2f} · {status_text}"
        badges.append((text, _badge_cls(status_text)))

    # Metric rows
    metric_rows = []
    for field, (label_str, unit) in FIELD_LABELS.items():
        value = getattr(m, field)
        val_str = fmt_value(field, value)
        context_only = field in _UNSCORED

        if field == "acwr" and m.acwr_status and value is not None:
            badge = m.acwr_status.replace("_", " ").title()
            unit = f" [{badge}]"

        if field in stats and value is not None:
            mean, std = stats[field]
            z = z_score(value, mean, std, field)
            avg_str = fmt_value(field, mean)
            col = _value_colour(z)
        else:
            z = None
            avg_str = "—"
            col = "text-white"

        metric_rows.append({
            "label": label_str,
            "value": val_str,
            "unit": unit if value is not None else "",
            "avg": avg_str,
            "z_val": z,
            "value_colour": col,
            "context_only": context_only,
        })

    # Chart data — last 14 days
    history = history_for_chart(days=14)
    chart_labels = [d.strftime("%d %b") for d, _ in history]
    chart_values = [round(v, 3) if v is not None else None for _, v in history]

    # Activities — last 7 days, fetch fresh if force_fetch
    if force_fetch:
        email_addr = os.getenv("GARMIN_EMAIL", "")
        password = os.getenv("GARMIN_PASSWORD", "")
        if email_addr and password:
            try:
                if api is None:
                    api = get_api(email_addr, password)
                acts_raw = fetch_activities(api, days=7)
                save_activities(acts_raw)
            except Exception:
                pass
    activities = [enrich_activity(a) for a in load_recent_activities(days=7)]

    date_key = target.isoformat()
    if date_key not in _advice_cache:
        _advice_cache[date_key] = generate_advice(m, stats, comp_z)

    return {
        "date": date_key,
        "date_long": target.strftime("%A, %-d %B %Y"),
        "comp_z": comp_z,
        "comp_label": comp_label,
        "comp_colour": comp_colour,
        "badges": badges,
        "metrics": metric_rows,
        "chart_labels": chart_labels,
        "chart_values": chart_values,
        "baseline_count": len(stats),
        "activities": activities,
        "trend_note": seven_day_composite_trend_csv(),
        "activity_blurb": _activity_context_blurb(activities),
        "advice": _advice_cache[date_key],
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, date: Optional[str] = None):
    target = date_fromisoformat_safe(date) if date else _today()
    ctx = _build_context(target)
    return TEMPLATES.TemplateResponse(request=request, name="dashboard.html", context=ctx)


@app.get("/calendar", response_class=HTMLResponse)
async def calendar_view(request: Request):
    ctx = _build_calendar_ctx()
    return TEMPLATES.TemplateResponse(request=request, name="calendar.html", context=ctx)


@app.get("/training", response_class=HTMLResponse)
async def training_plan(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="training.html", context={})


@app.get("/nutrition", response_class=HTMLResponse)
async def nutrition_plan(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="nutrition.html", context={})


@app.get("/refresh", response_class=RedirectResponse)
async def refresh(date: Optional[str] = None):
    target = date_fromisoformat_safe(date) if date else _today()
    _build_context(target, force_fetch=True)
    redirect_url = f"/?date={target.isoformat()}"
    return RedirectResponse(url=redirect_url, status_code=303)


def _today() -> date:
    from datetime import date as _date
    return _date.today()


def date_fromisoformat_safe(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return _today()


def run(host: str = "0.0.0.0", port: int = 8080) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="warning")

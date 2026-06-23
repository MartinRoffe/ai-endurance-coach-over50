from __future__ import annotations

import json
import logging
import os
import secrets
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

import anthropic as _anthropic
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pydantic import BaseModel, Field

from .alerts import check_fatigue_alerts
from .analysis import default_fuelling_plan, generate_recovery_suggestion, load_analyses_for_activities, prefetch_fuelling_plans, prefetch_nutrition_targets, prefetch_workout_descriptions, refresh_analyses, refresh_power_backfill, retrieve_relevant_analyses
from .client import get_api
from .display import FIELD_LABELS, fmt_value, readiness_label, enrich_activity
from .plan import (PLAN_START as _PLAN_START, build_calendar_weeks, build_camp_weeks,
                   build_combined_event_weeks, COMPOUND_SESSIONS,
                   CAMP_GRID_WORKOUTS, EVENT_PREP_DAYS, TENERIFE_DAYS, session_for_date,
                   session_for_date_extended,
                   CAMP_START, CAMP_END)
from .hr_plan import (HR_PHASES, HR_PLAN_START, HR_TRAINING_WEEKS,
                      build_hr_calendar_weeks, build_hr_event_weeks,
                      HR_EVENT_START, HR_EVENT_END, HR_HEAT_PROTOCOL, LESSONS_2012)
from .mersea_routes import MERSEA_TARGET_DATE
from .report import generate_advice, generate_body_analysis, generate_dashboard_explainer, generate_pmc_analysis, generate_pmc_explainer, generate_sleep_analysis
from .body import bp_classification, fetch_body_composition, fetch_blood_pressure
from .history import (
    ACTIVITY_MATCH,
    acclimation_latest,
    baseline_stats,
    clear_coach_history,
    composite_score,
    delete_advice,
    delete_plan_override,
    estimated_wkg_history,
    ftp_retest_due,
    get_coach_memory,
    get_plan_override,
    history_for_chart,
    intensity_distribution_by_week,
    intensity_distribution_by_week_power,
    latest_estimated_wkg,
    latest_measured_wkg,
    list_plan_overrides,
    load,
    load_activities_by_date,
    load_body_metrics,
    load_blood_pressure,
    load_btb_summary,
    load_coach_history,
    load_durability,
    load_ftp_tests,
    load_fuelling_logs,
    load_power_durability,
    measured_wkg_history,
    power_activation_status,
    power_meter_active,
    gut_training_summary,
    load_recent_activities,
    load_session_rpe,
    pmc_history,
    save_btb_note,
    save_fuelling_log,
    save_session_rpe,
    weekly_monotony_strain,
    vo2_history,
    zone_distribution,
    raw_history,
    save,
    save_activities,
    save_body_metrics,
    save_blood_pressure,
    save_coach_message,
    set_coach_memory,
    set_plan_override,
    seven_day_composite_trend_csv,
    sleep_history,
    z_score,
    get_cached_text,
    set_cached_text,
)
from .metrics import DailyMetrics, available_count, fetch_metrics, fetch_activities, TEXT_FIELDS, needs_metrics_refetch
from .coach_context import ATHLETE_CONSTRAINTS, build_coach_context as _build_coach_context
from .llm import MODEL_FAST, MODEL_SMART

load_dotenv()

logger = logging.getLogger(__name__)

# In-process AI-text caches. Routes are plain `def` (threadpool workers), so
# guard check-and-generate with a lock — also stops two concurrent page loads
# firing duplicate billable Claude calls for the same date.
_advice_cache: dict[str, str] = {}
_pmc_cache: dict[str, str] = {}
_ai_cache_lock = threading.Lock()

_BIKE_TYPE_KEYS = {"road_biking", "cycling", "virtual_ride", "indoor_cycling", "mountain_biking"}
_HARD_LABELS = {"Tempo Intervals", "FTP Test", "FTP Re-test"}
_HARD_SESSION_TYPES = {"tempo", "ftp", "long"}

QUALITY_BIKE_LABELS = {
    "Tempo Intervals", "Hill Repeats", "Sweetspot Ride", "Over-Unders",
    "Threshold Ride", "FTP Test", "FTP Re-test", "Final FTP Test",
}

def _week_completion() -> dict[str, Any]:
    """Return week completion stats for the dashboard card."""
    today = date.today()
    mon = today - timedelta(days=today.weekday())
    plan_min = 0
    for i in range(7):
        session = session_for_date(mon + timedelta(days=i))
        if session:
            stype, _, dur = session
            if stype != "rest" and dur:
                plan_min += dur
    if plan_min == 0:
        return {}
    acts = load_activities_by_date(mon, today - timedelta(days=1))
    done_min = 0
    for day_acts in acts.values():
        for a in day_acts:
            if any(a["type_key"] in keys for keys in ACTIVITY_MATCH.values()):
                done_min += int((a.get("duration_seconds", 0) or 0) / 60)
    pct = int(done_min / plan_min * 100)
    return {
        "plan_min_fmt": _fmt_min(plan_min),
        "done_min_fmt": _fmt_min(done_min),
        "pct": pct,
        "day_of_week": today.weekday() + 1,  # 1=Mon … 7=Sun
        "bar_filled": min(pct, 100),
    }


_OVERRIDE_ICONS = {
    "bike": "🚴", "tempo": "🚴", "ftp": "🚴", "long": "🚴",
    "strength": "🏋️", "ruck": "🎒", "rest": "—",
}


def _apply_overrides(weeks: list[dict]) -> list[dict]:
    """Patch type/label/dur_min/dur_fmt/icon for any day with a plan override."""
    overrides = {o["date"]: o for o in list_plan_overrides()}
    if not overrides:
        return weeks
    for week in weeks:
        for day in week["days"]:
            key = day["date"].isoformat()
            if key not in overrides:
                continue
            ov = overrides[key]
            dur = ov["duration_min"]
            day["dur_min"] = dur
            day["dur_fmt"] = _fmt_min(dur)
            if ov.get("session_type"):
                day["type"]  = ov["session_type"]
                day["icon"]  = _OVERRIDE_ICONS.get(ov["session_type"], "📋")
                if ov["session_type"] != "ruck":
                    day["ruck_spec"]      = None
                    day["mersea_build"]   = False
                if ov["session_type"] not in ("strength",):
                    day["kb_spec"]        = None
                    day["maxi_intervals"] = None
                day["sub_sessions"] = None
            if ov.get("label"):
                day["label"] = ov["label"]
    return weeks


def _calendar_weeks() -> list[dict]:
    return _apply_overrides(build_calendar_weeks())


def _build_calendar_ctx() -> dict[str, Any]:
    return {
        "weeks": _calendar_weeks(),
        "today": date.today(),
        "plan_start": _PLAN_START,
        "camp_weeks": build_camp_weeks(),
        "combined_event_weeks": build_combined_event_weeks(),
    }

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
TEMPLATES.env.filters["format_thousands"] = lambda v: f"{int(v):,}" if v is not None else "—"

_security = HTTPBasic(auto_error=False)

def _require_auth(credentials: Optional[HTTPBasicCredentials] = Depends(_security)) -> None:
    expected_user = os.getenv("DASHBOARD_USER", "")
    expected_pass = os.getenv("DASHBOARD_PASSWORD", "")
    if not expected_user or not expected_pass:
        return  # auth not configured — open access (local-only use)
    if credentials is None or not (
        secrets.compare_digest(credentials.username.encode(), expected_user.encode())
        and secrets.compare_digest(credentials.password.encode(), expected_pass.encode())
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )


app = FastAPI(
    title="AI Endurance Coach (50+)",
    docs_url=None,
    redoc_url=None,
    dependencies=[Depends(_require_auth)],
)

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
            from .hr_profile import refresh_hr_profile_if_needed
            refresh_hr_profile_if_needed(api, force=True)
        else:
            m = load(target) or DailyMetrics(date=target)
    else:
        m = load(target) or DailyMetrics(date=target)
        if needs_metrics_refetch(m):
            email = os.getenv("GARMIN_EMAIL", "")
            password = os.getenv("GARMIN_PASSWORD", "")
            if email and password:
                api = get_api(email, password)
                m = fetch_metrics(api, target)
                save(m)
                from .hr_profile import refresh_hr_profile_if_needed
                refresh_hr_profile_if_needed(api, force=False)

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

    # Sparklines — last 14 days of key recovery metrics
    spark_rows = raw_history(14)
    sparklines = {
        "hrv":    [r["hrv_last_night"] for r in spark_rows],
        "sleep":  [r["sleep_score"]    for r in spark_rows],
        "stress": [r["avg_stress"]     for r in spark_rows],
        "labels": [r["date"].strftime("%-d %b") for r in spark_rows],
    }

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
    with _ai_cache_lock:
        if force_fetch:
            # Pop in-process cache so advice is re-read from SQLite, but keep the
            # SQLite row — re-generating advice on every refresh causes inconsistency.
            _advice_cache.pop(date_key, None)
        if date_key not in _advice_cache:
            _advice_cache[date_key] = generate_advice(m, stats, comp_z)
        advice_text = _advice_cache[date_key]

    # Today's planned session
    _SESSION_ICONS = {
        "bike": "🚴", "tempo": "🚴", "ftp": "🚴", "long": "🚴",
        "strength": "🏋️", "ruck": "🎒",
    }
    _session = session_for_date(target)
    if _session and _session[0] != "rest":
        _stype, _slabel, _sdur = _session
        today_plan: Optional[dict] = {
            "type":     _stype,
            "label":    _slabel,
            "dur_fmt":  _fmt_min(_sdur),
            "icon":     _SESSION_ICONS.get(_stype, "📋"),
            "compound": COMPOUND_SESSIONS.get(_slabel),
            "note":     get_cached_text(f"session_note_{target.isoformat()}"),
        }
    else:
        today_plan = None

    # Readiness-adjusted swap suggestion
    swap_suggestion = None
    if (today_plan and today_plan["type"] in _HARD_SESSION_TYPES
            and comp_z is not None and comp_z < -0.5):
        days_left = 6 - target.weekday()
        for offset in range(1, days_left + 1):
            candidate = target + timedelta(days=offset)
            csess = session_for_date(candidate)
            if csess and csess[0] == "bike" and csess[1] not in _HARD_LABELS:
                swap_suggestion = {
                    "from_label": today_plan["label"],
                    "to_date_str": candidate.strftime("%-d %b"),
                    "to_label": csess[1],
                    "severity": "high" if comp_z < -1.0 else "moderate",
                }
                break
        if not swap_suggestion:
            swap_suggestion = {
                "from_label": today_plan["label"],
                "to_date_str": None,
                "to_label": None,
                "severity": "high" if comp_z < -1.0 else "moderate",
            }

    # Event readiness tracker
    _EVENT_DATE = date(2026, 9, 13)
    _PLAN_DAYS  = 84
    _days_into  = (target - _PLAN_START).days
    _ws = _week_summary()
    if target >= _PLAN_START and (_EVENT_DATE - target).days > 0:
        _week_pct = _ws.get("pct") if _ws else None
        if _week_pct is None:
            _on_label, _on_col = "No data yet", "text-zinc-500"
        elif _week_pct >= 80:
            _on_label, _on_col = "On track", "text-emerald-400"
        elif _week_pct >= 50:
            _on_label, _on_col = "Slightly behind", "text-yellow-400"
        else:
            _on_label, _on_col = "Behind", "text-red-400"
        event_tracker: Optional[dict] = {
            "week_num":        min(12, max(1, _days_into // 7 + 1)),
            "plan_pct":        min(100, max(0, int(_days_into / _PLAN_DAYS * 100))),
            "days_to_event":   (_EVENT_DATE - target).days,
            "on_track_label":  _on_label,
            "on_track_colour": _on_col,
        }
    else:
        event_tracker = None

    # Fatigue alerts
    fatigue_alerts = check_fatigue_alerts(target)

    # HRV traffic light + session modulation suggestion (recovery gate first)
    traffic_light = None
    modulation = None
    try:
        from .modulation import resolve_modulation
        traffic_light, modulation = resolve_modulation(target, m, comp_z)
    except Exception:
        pass

    # FTP retest prompt: last test stale → suggest a slot via the override flow
    ftp_retest = None
    try:
        due = ftp_retest_due(target, plan_start=_PLAN_START)
        if due:
            slot = None
            for offset in range(1, 11):
                cand = target + timedelta(days=offset)
                csess = session_for_date(cand)
                if csess and csess[0] in ("tempo", "ftp", "bike"):
                    slot = {"date": cand.isoformat(),
                            "date_str": cand.strftime("%a %-d %b"),
                            "current_label": csess[1]}
                    break
            ftp_retest = {**due, "slot": slot}
    except Exception:
        pass

    # Weekly briefing (Monday only)
    weekly_briefing: Optional[str] = None
    is_monday = target.weekday() == 0
    if is_monday:
        week_sessions = []
        for i in range(7):
            d = target + timedelta(days=i)
            sess = session_for_date(d)
            if sess and sess[0] != "rest":
                day_name = d.strftime("%a")
                week_sessions.append((day_name, sess[0], sess[1], sess[2]))
        # Use the most recent entry that actually has PMC numbers — today's
        # training-load row may not have synced from the watch yet on Monday AM.
        _pmc_recent = pmc_history(days=7)
        _pmc_today = next(
            (e for e in reversed(_pmc_recent) if e.get("ctl") is not None),
            _pmc_recent[-1] if _pmc_recent else {},
        )
        try:
            from .report import generate_weekly_briefing
            weekly_briefing = generate_weekly_briefing(week_sessions, _pmc_today, comp_z)
        except Exception:
            pass

    # Nutrition snapshot for readiness tab
    nutrition_today = None
    if m.calories_consumed is not None:
        nutrition_today = {
            "calories": int(m.calories_consumed),
            "tdee":     int(m.calorie_goal_adjusted) if m.calorie_goal_adjusted else None,
            "goal":     int(m.calorie_goal) if m.calorie_goal else None,
            "carbs":    round(m.carbs_consumed) if m.carbs_consumed is not None else None,
            "protein":  round(m.protein_consumed) if m.protein_consumed is not None else None,
        }
        if nutrition_today["tdee"] and nutrition_today["calories"]:
            nutrition_today["balance"] = nutrition_today["tdee"] - nutrition_today["calories"]

    gut_training = None
    try:
        gut_training = gut_training_summary(target)
    except Exception:
        pass

    power_snapshot = None
    try:
        if power_meter_active():
            tests = load_ftp_tests()
            ftp_w = next((t["ftp_w"] for t in reversed(tests) if t.get("ftp_w")), None)
            if ftp_w:
                for act in load_recent_activities(14):
                    if act.get("type_key") not in _BIKE_TYPE_KEYS:
                        continue
                    np_w = act.get("norm_power_w")
                    if not np_w:
                        continue
                    try:
                        sess = session_for_date_extended(date.fromisoformat(act["date"]))
                    except Exception:
                        sess = None
                    label = sess[1] if sess else ""
                    if label not in QUALITY_BIKE_LABELS:
                        continue
                    power_snapshot = {
                        "label": label,
                        "date": act["date"],
                        "norm_power_w": round(np_w),
                        "ftp_w": ftp_w,
                        "pct_ftp": round(np_w / ftp_w * 100),
                    }
                    break
    except Exception:
        pass

    return {
        "date": date_key,
        "date_long": target.strftime("%A, %-d %B %Y"),
        "comp_z": comp_z,
        "comp_label": comp_label,
        "comp_colour": comp_colour,
        "badges": badges,
        "acwr": m.acwr,
        "metrics": metric_rows,
        "chart_labels": chart_labels,
        "chart_values": chart_values,
        "baseline_count": len(stats),
        "activities": activities,
        "trend_note": seven_day_composite_trend_csv(),
        "activity_blurb": _activity_context_blurb(activities),
        "advice": advice_text,
        "week_summary": _ws,
        "metric_explainer": generate_dashboard_explainer(),
        "sparklines": sparklines,
        "today_plan": today_plan,
        "swap_suggestion": swap_suggestion,
        "event_tracker": event_tracker,
        "fatigue_alerts": fatigue_alerts,
        "traffic_light": traffic_light,
        "modulation": modulation,
        "ftp_retest": ftp_retest,
        "weekly_briefing": weekly_briefing,
        "is_monday": is_monday,
        "nutrition_today": nutrition_today,
        "gut_training": gut_training,
        "power_snapshot": power_snapshot,
    }


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, date: Optional[str] = None, msg: Optional[str] = None,
                    n: Optional[int] = None):
    target = date_fromisoformat_safe(date) if date else _today()
    ctx = _build_context(target)
    ctx["flash_msg"] = msg
    ctx["flash_n"] = n
    return TEMPLATES.TemplateResponse(request=request, name="dashboard.html", context=ctx)


@app.get("/send-email", response_class=RedirectResponse)
def send_email_now():
    from pathlib import Path
    today = _today()
    sentinel = Path.home() / ".ai_endurance_coach_over50" / f"sent_{today.isoformat()}"
    if sentinel.exists():
        return RedirectResponse(url="/?msg=already_sent", status_code=303)

    email_addr = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")
    m = None
    if email_addr and password:
        try:
            api = get_api(email_addr, password)
            raw = fetch_metrics(api, today)
            if raw:
                save(raw)
                m = raw
        except Exception:
            pass
    if m is None:
        m = load(today)

    if m is None or (m.sleep_score is None and m.body_battery_morning is None):
        return RedirectResponse(url="/?msg=no_data", status_code=303)

    # Sentinel before send: a crash after SMTP delivery must not allow a
    # duplicate; on a clean failure the sentinel is removed so retry works.
    sentinel.touch()
    try:
        from .report import run_report
        run_report(m, dry_run=False)
        return RedirectResponse(url="/?msg=sent", status_code=303)
    except Exception as e:
        sentinel.unlink(missing_ok=True)
        logger.error("send-email failed: %s", e)
        return RedirectResponse(url="/?msg=error", status_code=303)


@app.get("/sync-workouts", response_class=RedirectResponse)
async def sync_workouts_now():
    """Re-upload and re-schedule all plan cycling workouts to Garmin, applying any
    coach plan overrides. Manual trigger only (button / CLI). Outward-facing — mutates
    the athlete's Garmin Connect calendar."""
    from fastapi.concurrency import run_in_threadpool
    from .workouts import upload_and_schedule

    email_addr = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")
    if not (email_addr and password):
        return RedirectResponse(url="/?msg=no_garmin", status_code=303)

    try:
        api = get_api(email_addr, password)
        summary = await run_in_threadpool(upload_and_schedule, api)
        n = summary.get("scheduled", 0)
        return RedirectResponse(url=f"/?msg=synced&n={n}", status_code=303)
    except Exception as e:
        logger.error("sync-workouts failed: %s", e)
        return RedirectResponse(url="/?msg=sync_error", status_code=303)


def _merge_compound_activities(activities: list[dict]) -> list[dict]:
    """Collapse compound session pairs (e.g. KB + MaxiClimber) into one card."""
    # Build a reverse lookup: garmin type_key → compound session label
    key_to_label: dict[str, str] = {}
    for label, subs in COMPOUND_SESSIONS.items():
        for sub in subs:
            key_to_label[sub["garmin_key"]] = label

    # Index activities by (date, compound_label) to find pairs
    compound_groups: dict[tuple[str, str], list[dict]] = {}
    non_compound: list[dict] = []
    for act in activities:
        label = key_to_label.get(act.get("type_key", ""))
        if label:
            key = (act.get("date", ""), label)
            compound_groups.setdefault(key, []).append(act)
        else:
            non_compound.append(act)

    merged: list[dict] = []
    for (act_date, label), group in compound_groups.items():
        if len(group) == 1:
            non_compound.append(group[0])
            continue
        # Primary = the one with analysis_text (prefer strength_training)
        subs = COMPOUND_SESSIONS[label]
        primary_key = subs[0]["garmin_key"]
        primary = next((a for a in group if a.get("type_key") == primary_key), group[0])
        others = [a for a in group if a["activity_id"] != primary["activity_id"]]

        combined = dict(primary)
        combined["name"] = label
        # Sum duration and calories
        total_secs = sum(a.get("duration_seconds") or 0 for a in group)
        combined["duration_seconds"] = total_secs
        from .display import fmt_duration
        combined["duration_fmt"] = fmt_duration(total_secs)
        combined["calories"] = sum((a.get("calories") or 0) for a in group)
        # Attach companion HR zones for template rendering
        # Build ordered zone sections (one per sub-session) for the template
        acts_by_key = {a["type_key"]: a for a in group}
        combined["zone_sections"] = [
            {"label": sub["label"], "zones": acts_by_key.get(sub["garmin_key"], {}).get("hr_zones", [])}
            for sub in subs
        ]
        merged.append(combined)

    # Restore original order (newest first)
    all_acts = non_compound + merged
    all_acts.sort(key=lambda a: a.get("start_time") or a.get("date", ""), reverse=True)
    return all_acts


@app.get("/analysis", response_class=HTMLResponse)
def analysis_view(request: Request):
    activities_raw = load_recent_activities(days=14)
    activities = load_analyses_for_activities(
        [enrich_activity(a) for a in activities_raw]
    )
    activities = _merge_compound_activities(activities)
    rpe_rows = load_session_rpe(30)
    rpe_by_activity = {str(r["activity_id"]): r for r in rpe_rows if r.get("activity_id") is not None}

    # Fuelling compliance: attach in-ride plan target + any logged actuals to
    # qualifying endurance rides (bike types, ≥75 min). Uses cached AI plans
    # when available; otherwise a duration-based default so the log widget
    # always appears (prefetch was never wired up before).
    try:
        from .analysis import fuelling_session_key
        from .plan import session_for_date_extended
        _BIKE_TYPES = {"road_biking", "cycling", "virtual_ride", "indoor_cycling", "mountain_biking"}
        _FUEL_MIN_SECS = 75 * 60
        prefetch_sessions: set[tuple[str, int]] = set()
        for a in activities:
            if a.get("type_key") not in _BIKE_TYPES:
                continue
            if (a.get("duration_seconds") or 0) < _FUEL_MIN_SECS:
                continue
            try:
                sess = session_for_date_extended(date.fromisoformat(a["date"]))
            except Exception:
                sess = None
            if sess and sess[0] != "rest" and sess[2] >= 75:
                prefetch_sessions.add((sess[0], sess[2]))
        fuel_plans = prefetch_fuelling_plans(list(prefetch_sessions)) if prefetch_sessions else {}
        fuel_logs = {str(r["activity_id"]): r for r in load_fuelling_logs(90)
                     if r.get("activity_id") is not None}
        for a in activities:
            if a.get("type_key") not in _BIKE_TYPES:
                continue
            if (a.get("duration_seconds") or 0) < _FUEL_MIN_SECS:
                continue
            actual_min = int((a.get("duration_seconds") or 0) / 60)
            ref_min = actual_min
            try:
                sess = session_for_date_extended(date.fromisoformat(a["date"]))
            except Exception:
                sess = None
            if sess and sess[0] != "rest" and sess[2]:
                ref_min = sess[2]
                plan = fuel_plans.get(fuelling_session_key(sess[0], sess[2]))
                if plan:
                    a["planned_fuel"] = plan
            if not a.get("planned_fuel"):
                a["planned_fuel"] = default_fuelling_plan(ref_min)
            a["fuel_log"] = fuel_logs.get(str(a.get("activity_id")))
    except Exception:
        pass

    # FTP watts + W/kg for FTP test cards
    try:
        from .history import _weight_kg_on_date, load_body_metrics
        weight_rows = [(r["date"], r["weight_kg"]) for r in load_body_metrics(365) if r.get("weight_kg")]
        weights = [(d, float(w)) for d, w in weight_rows]
        for a in activities:
            effort_w = a.get("ftp_effort_avg_w")
            if effort_w:
                w = _weight_kg_on_date(a["date"], weights)
                ftp_w = a.get("ftp_w") or round(effort_w * 0.95)
                a["ftp_w"] = ftp_w
                if w:
                    a["ftp_wkg"] = round(ftp_w / w, 2)
    except Exception:
        pass

    return TEMPLATES.TemplateResponse(
        request=request,
        name="analysis.html",
        context={
            "activities": activities,
            "zone_dist": zone_distribution(days=7),
            "rpe_by_activity": rpe_by_activity,
        },
    )


@app.post("/log-rpe")
async def log_rpe_endpoint(request: Request, _=Depends(_require_auth)):
    body = await request.json()
    save_session_rpe(body["date"], body.get("activity_id"), body["rpe"], body.get("note"))
    return JSONResponse({"ok": True})


class _FuellingLogRequest(BaseModel):
    date: str
    activity_id: Optional[int] = None
    planned_carbs_g_per_hr: Optional[float] = Field(None, ge=0, le=300)
    actual_carbs_g_per_hr: Optional[float] = Field(None, ge=0, le=300)
    fluid_ok: bool = False
    note: Optional[str] = None


@app.post("/log-fuelling")
async def log_fuelling_endpoint(body: _FuellingLogRequest, _=Depends(_require_auth)):
    try:
        date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")
    save_fuelling_log(
        body.date,
        body.activity_id,
        body.planned_carbs_g_per_hr,
        body.actual_carbs_g_per_hr,
        body.fluid_ok,
        body.note,
    )
    return JSONResponse({"ok": True})


@app.get("/api/ftp-tests")
async def api_ftp_tests(_=Depends(_require_auth)):
    return JSONResponse(load_ftp_tests())


@app.post("/log-btb")
async def log_btb_endpoint(request: Request, _=Depends(_require_auth)):
    body = await request.json()
    save_btb_note(body["date"], body.get("day_number", 1), body.get("fatigue_rating"), body.get("note"))
    return JSONResponse({"ok": True})


@app.get("/btb-summary")
async def btb_summary_view(_=Depends(_require_auth)):
    return JSONResponse(load_btb_summary())


@app.get("/activate-power", response_class=RedirectResponse)
def activate_power(days: int = 30):
    """Phase 6: backfill activities and mine power metrics on historical rides."""
    email_addr = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")
    if email_addr and password:
        api = get_api(email_addr, password)
        try:
            refresh_power_backfill(api, days=max(7, min(days, 90)))
        except Exception:
            pass
    return RedirectResponse(url="/performance", status_code=303)


@app.get("/analysis-refresh", response_class=RedirectResponse)
def analysis_refresh():
    email_addr = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")
    if email_addr and password:
        api = get_api(email_addr, password)
        activities_raw = load_recent_activities(days=14)
        if activities_raw:
            try:
                from .metrics import fetch_activities
                acts_raw = fetch_activities(api, days=14)
                save_activities(acts_raw)
            except Exception:
                pass
        try:
            refresh_analyses(api, days=14)
        except Exception:
            pass
    return RedirectResponse(url="/analysis", status_code=303)


@app.get("/performance", response_class=HTMLResponse)
async def performance_view(request: Request):
    history = pmc_history(days=90)
    today_entry = history[-1] if history else {}
    date_key = date.today().isoformat()
    with _ai_cache_lock:
        if date_key not in _pmc_cache:
            m_today = load(date.today()) or DailyMetrics(date=date.today())
            stats_today = baseline_stats(date.today())
            comp_z_today = composite_score(m_today, stats_today)
            _pmc_cache[date_key] = generate_pmc_analysis(history, m_today, comp_z_today)
        pmc_analysis_text = _pmc_cache[date_key]

    plan_acts = load_activities_by_date(_PLAN_START, date.today())
    z2_points: list[dict] = []
    for date_str, acts in sorted(plan_acts.items()):
        for act in acts:
            if act["type_key"] in _BIKE_TYPE_KEYS and act.get("avg_hr"):
                d = date.fromisoformat(date_str)
                plan_sess = session_for_date(d)
                sess_label = plan_sess[1] if plan_sess else (act.get("name") or "Bike")
                z2_points.append({
                    "date": date_str,
                    "avg_hr": round(act["avg_hr"]),
                    "label": sess_label,
                    "hard": sess_label in _HARD_LABELS,
                })

    proj_data: list[dict] = []
    event_ctl: Optional[float] = None
    _ctl_now = today_entry.get("ctl")
    _atl_now = today_entry.get("atl")
    if _ctl_now is not None and _atl_now is not None:
        proj_data, event_ctl = _ctl_projection(_ctl_now, _atl_now)

    # Per-activity training load for bar chart (last 60 days)
    load_acts = load_activities_by_date(date.today() - timedelta(days=60), date.today())
    load_chart_data = []
    _BIKE_KEYS = {"road_biking", "cycling", "virtual_ride", "indoor_cycling", "mountain_biking"}
    _RUCK_KEYS = {"hiking", "walking", "rucking", "load_carry"}
    _STR_KEYS  = {"strength_training", "stair_climbing", "fitness_equipment"}
    for date_str in sorted(load_acts.keys()):
        for a in load_acts[date_str]:
            if not a.get("training_load"):
                continue
            tk = a.get("type_key", "")
            colour = (
                "rgba(96,165,250,0.75)"  if tk in _BIKE_KEYS else
                "rgba(163,230,53,0.75)"  if tk in _RUCK_KEYS else
                "rgba(167,139,250,0.75)" if tk in _STR_KEYS  else
                "rgba(251,146,60,0.75)"
            )
            load_chart_data.append({
                "label":  date.fromisoformat(date_str).strftime("%-d %b"),
                "load":   round(a["training_load"], 1),
                "name":   a.get("name") or a.get("type_key", ""),
                "colour": colour,
            })

    # Z2 cardiac drift trend: server-side regression on easy rides only
    easy_points = [p for p in z2_points if not p.get("hard")]
    z2_trend_line: list[dict] = []
    z2_drift_annotation: Optional[str] = None
    if len(easy_points) >= 3:
        fit = _ols([p["avg_hr"] for p in easy_points])
        if fit:
            slope, intercept = fit
            n = len(easy_points)
            z2_trend_line = [
                {"date": easy_points[0]["date"], "hr": round(intercept, 1)},
                {"date": easy_points[-1]["date"], "hr": round(slope * (n - 1) + intercept, 1)},
            ]
            drop = round(intercept - (slope * (n - 1) + intercept), 1)
            if slope < 0:
                z2_drift_annotation = f"−{abs(drop):.1f} bpm since {easy_points[0]['date']}"
            else:
                z2_drift_annotation = "No improvement yet"

    # Durability: late-ride HR drift trend (≥90 min rides)
    durability_points = load_durability(180)
    durability_trend: list[dict] = []
    if len(durability_points) >= 3:
        fit = _ols([p["drift_pct"] for p in durability_points])
        if fit:
            slope, intercept = fit
            n = len(durability_points)
            durability_trend = [
                {"date": durability_points[0]["date"], "v": round(intercept, 2)},
                {"date": durability_points[-1]["date"], "v": round(slope * (n - 1) + intercept, 2)},
            ]

    # Estimated W/kg + monotony + acclimation
    wkg_history = estimated_wkg_history(180)
    monotony_weeks = weekly_monotony_strain(8)
    acclimation = acclimation_latest()

    # Taper scenario simulator (presets over the final 14 days)
    taper_scenarios: list[dict] = []
    if _ctl_now is not None and _atl_now is not None:
        try:
            taper_scenarios = _taper_scenarios(_ctl_now, _atl_now)
        except Exception:
            pass

    # Intensity distribution by week
    zone_dist_by_week = intensity_distribution_by_week(_PLAN_START, date.today())
    zone_dist_block = _block_zone_totals(zone_dist_by_week)
    zone_dist_by_week_power = intensity_distribution_by_week_power(_PLAN_START, date.today())
    zone_dist_block_power = _block_zone_totals(zone_dist_by_week_power)

    # Measured FTP / W/kg (power tests + weight)
    measured_wkg = measured_wkg_history(180)
    est_by_date = {r["date"]: r for r in wkg_history}
    for row in measured_wkg:
        row["est_ftp_w"] = est_by_date.get(row["date"], {}).get("est_ftp_w")

    # Pw:HR decoupling on long power rides
    power_durability_points = load_power_durability(180)
    power_durability_trend: list[dict] = []
    if len(power_durability_points) >= 3:
        fit = _ols([p["decoupling_pct"] for p in power_durability_points])
        if fit:
            slope, intercept = fit
            n = len(power_durability_points)
            power_durability_trend = [
                {"date": power_durability_points[0]["date"], "v": round(intercept, 2)},
                {"date": power_durability_points[-1]["date"], "v": round(slope * (n - 1) + intercept, 2)},
            ]

    return TEMPLATES.TemplateResponse(
        request=request,
        name="performance.html",
        context={
            "history": history,
            "today": today_entry,
            "pmc_analysis": pmc_analysis_text,
            "pmc_explainer": generate_pmc_explainer(),
            "z2_points": z2_points,
            "z2_trend_line": z2_trend_line,
            "z2_drift_annotation": z2_drift_annotation,
            "proj_data": proj_data,
            "event_ctl": event_ctl,
            "load_chart_data": load_chart_data,
            "event_date_label": _PLAN_EVENT_DATE.strftime("%-d %b %Y"),
            "camp_start_label": date(2026, 8, 13).strftime("%-d %b"),
            "camp_end_label":   date(2026, 8, 27).strftime("%-d %b"),
            "event_prep_label": date(2026, 8, 31).strftime("%-d %b"),
            "vo2_history": vo2_history(days=90),
            "zone_dist_by_week": zone_dist_by_week,
            "zone_dist_block": zone_dist_block,
            "zone_dist_by_week_power": zone_dist_by_week_power,
            "zone_dist_block_power": zone_dist_block_power,
            "durability_points": durability_points,
            "durability_trend": durability_trend,
            "power_durability_points": power_durability_points,
            "power_durability_trend": power_durability_trend,
            "wkg_history": wkg_history,
            "measured_wkg": measured_wkg,
            "power_meter_active": power_meter_active(),
            "power_activation": power_activation_status(),
            "monotony_weeks": monotony_weeks,
            "acclimation": acclimation,
            "taper_scenarios": taper_scenarios,
        },
    )


def _ols(ys: list[float]) -> Optional[tuple[float, float]]:
    """Ordinary least squares on (index, value). Returns (slope, intercept) or None."""
    n = len(ys)
    if n < 2:
        return None
    xs = list(range(n))
    sx, sy = sum(xs), sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sx2 = sum(x * x for x in xs)
    denom = n * sx2 - sx * sx
    if not denom:
        return None
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    return slope, intercept


_PLAN_EVENT_DATE = date(2026, 9, 13)

# CTL delta per training minute by session type.
# Calibrated from week-1 observed data: Easy Spin 60min→+15, Zone2 60min→+26,
# KB+MaxiClimber 45min→+33, Ruck+KB 105min→+33. Rest days average -3.
_CTL_PER_MIN: dict[str, float] = {
    "bike":     0.32,   # easy spin / Z2
    "long":     0.40,   # Z2 long ride
    "tempo":    0.58,   # tempo effort
    "ftp":      0.78,   # threshold
    "strength": 0.70,   # KB / strength (high EPOC)
    "ruck":     0.30,   # hiking / ruck
}
_CTL_REST_DECLINE = -3.5


_TENERIFE_BY_DATE: dict = {}   # populated lazily below
_EVENT_PREP_BY_DATE: dict = {}

def _build_lookup_dicts() -> None:
    global _TENERIFE_BY_DATE, _EVENT_PREP_BY_DATE
    # Intensity → session type mapping for Tenerife days
    _intensity_type = {"easy": "bike", "medium": "bike", "hard": "long"}
    for day in TENERIFE_DAYS:
        intensity = day.get("intensity", "rest")
        stype = _intensity_type.get(intensity)
        if stype:
            km = day.get("km", 0) or 0
            elev = day.get("elev_m", 0) or 0
            # Duration estimate: flat km at 25 km/h + climbing at 700 m/h
            dur_min = int((km / 25 + elev / 700) * 60)
            _TENERIFE_BY_DATE[day["date"]] = (stype, day["label"], max(dur_min, 30))
    for day in EVENT_PREP_DAYS:
        _EVENT_PREP_BY_DATE[day["date"]] = (day["type"], day["label"], day["dur_min"])
    for day in CAMP_GRID_WORKOUTS.values():
        pass  # handled via session_for_date for the pre/post camp days

_build_lookup_dicts()


def _session_for_projection(d) -> tuple[str, str, int] | None:
    """Return (type, label, dur_min) for any plan day — 12-week plan, camp, or event prep."""
    sess = session_for_date(d)
    if sess:
        return sess
    if d in _TENERIFE_BY_DATE:
        return _TENERIFE_BY_DATE[d]
    if d in _EVENT_PREP_BY_DATE:
        return _EVENT_PREP_BY_DATE[d]
    # CAMP_GRID_WORKOUTS (pre/post camp activation rides)
    cg = CAMP_GRID_WORKOUTS.get(d)
    if cg:
        return (cg["type"], cg["label"], cg["dur_min"])
    return None


def _ctl_projection(current_ctl: float, current_atl: float,
                    modifier=None) -> tuple[list[dict], float]:
    """Project CTL/ATL/TSB from today to event day using all plan sessions including Tenerife camp.

    Uses additive deltas calibrated against observed week-1 data rather than
    the standard Coggan EMA, because Garmin's CTL units don't follow the
    standard TSS-based scale. A soft ceiling (diminishing returns above CTL 300)
    prevents runaway growth.

    `modifier` (optional) is applied to each (date, session_tuple) before the
    rate maths: return a replacement tuple, or None to treat the day as rest.
    Used by the taper scenario simulator.
    """
    import math as _math
    today = date.today()
    days_ahead = (_PLAN_EVENT_DATE - today).days
    if days_ahead <= 0:
        return [], round(current_ctl, 1)

    ctl = current_ctl
    atl = current_atl
    result = []
    for i in range(1, days_ahead + 1):
        d = today + timedelta(days=i)
        sess = _session_for_projection(d)
        if modifier is not None and sess is not None:
            sess = modifier(d, sess)
        if sess and sess[0] != "rest":
            stype, _, dur_min = sess
            rate = _CTL_PER_MIN.get(stype, 0.35)
            ceiling = (300 / max(ctl, 300)) ** 2
            delta = rate * (dur_min or 0) * ceiling
            atl_delta = rate * (dur_min or 0)
            atl = max(0.0, atl * _math.exp(-1 / 7) + atl_delta)
        else:
            delta = _CTL_REST_DECLINE
            atl = max(0.0, atl * _math.exp(-1 / 7))
        ctl = max(0.0, ctl + delta)
        tsb = round(ctl - atl, 1)
        result.append({
            "label": d.strftime("%-d %b"),
            "ctl":   round(ctl, 1),
            "atl":   round(atl, 1),
            "tsb":   tsb,
        })
    return result, round(result[-1]["ctl"], 1) if result else round(current_ctl, 1)


def _taper_scenarios(current_ctl: float, current_atl: float) -> list[dict]:
    """Three preset what-if projections over the final 14 days before the event.

    Turns the TSB projection from a chart into a decision tool: target landing
    zone on event morning is roughly TSB −5 to +15.
    """
    taper_start = _PLAN_EVENT_DATE - timedelta(days=14)
    final_week = _PLAN_EVENT_DATE - timedelta(days=7)

    scenarios = []

    # 1. As planned
    series, ctl_event = _ctl_projection(current_ctl, current_atl)
    if not series:
        return []
    scenarios.append({"name": "As planned", "series": series,
                      "tsb_event": series[-1]["tsb"], "ctl_event": ctl_event})

    # 2. Drop the first quality session (tempo/ftp) inside the final 14 days
    dropped = {"done": False}

    def _drop_quality(d, sess):
        if (not dropped["done"] and d >= taper_start
                and sess and sess[0] in ("tempo", "ftp")):
            dropped["done"] = True
            return None
        return sess

    series2, ctl2 = _ctl_projection(current_ctl, current_atl, modifier=_drop_quality)
    scenarios.append({"name": "Drop one quality session", "series": series2,
                      "tsb_event": series2[-1]["tsb"] if series2 else None,
                      "ctl_event": ctl2})

    # 3. Halve final-week volume
    def _halve_final_week(d, sess):
        if d >= final_week and sess and sess[0] != "rest":
            stype, label, dur = sess
            return (stype, label, max(15, (dur or 0) // 2))
        return sess

    series3, ctl3 = _ctl_projection(current_ctl, current_atl, modifier=_halve_final_week)
    scenarios.append({"name": "Halve final-week volume", "series": series3,
                      "tsb_event": series3[-1]["tsb"] if series3 else None,
                      "ctl_event": ctl3})

    return scenarios


def _block_zone_totals(weeks: list[dict]) -> dict:
    """Aggregate zone distribution across all weeks to block-level percentages."""
    totals = [0.0] * 5
    for w in weeks:
        for i in range(1, 6):
            totals[i - 1] += w.get(f"z{i}_sec", 0.0)
    total = sum(totals)
    if total == 0:
        return {}
    return {
        "z1_pct": round(totals[0] / total * 100, 1),
        "z2_pct": round(totals[1] / total * 100, 1),
        "z3_pct": round(totals[2] / total * 100, 1),
        "z4_pct": round(totals[3] / total * 100, 1),
        "z5_pct": round(totals[4] / total * 100, 1),
    }


_BIKE_TYPES = {"bike", "tempo", "ftp", "long"}

# CTL rates for Haute Route plan session types.
# Reuses calibrated values from _CTL_PER_MIN where keys overlap.
_HR_CTL_PER_MIN: dict[str, float] = {
    "endurance":    0.32,   # Z2 steady (same as "bike")
    "recovery":     0.25,   # recovery spin / easy core
    "sweetspot":    0.45,   # sweetspot intervals
    "tempo":        0.58,   # tempo / under-overs (same as "tempo")
    "vo2":          0.65,   # VO2max intervals
    "long":         0.40,   # long ride (same as "long")
    "back_to_back": 0.40,   # multi-hour back-to-back days
    "ftp":          0.78,   # threshold test (same as "ftp")
    "gym":          0.55,   # gym strength session
}


def _hr_ctl_projection(starting_ctl: float) -> list[dict]:
    """Project CTL across all 46 HR plan weeks, returning one point per week (Sunday)."""
    ctl = starting_ctl
    result = []
    for wk_idx, sessions in enumerate(HR_TRAINING_WEEKS):
        week_num = wk_idx + 1
        for stype, _, dur_min in sessions:
            if stype != "rest":
                rate = _HR_CTL_PER_MIN.get(stype, 0.35)
                ceiling = (300 / max(ctl, 300)) ** 2
                ctl = max(0.0, ctl + rate * dur_min * ceiling)
            else:
                ctl = max(0.0, ctl + _CTL_REST_DECLINE)
        week_end = HR_PLAN_START + timedelta(weeks=wk_idx, days=6)
        result.append({
            "label":    week_end.strftime("%-d %b"),
            "ctl":      round(ctl, 1),
            "week":     week_num,
        })
    return result

# Map Garmin type_key → display session type for pre-plan activity cells
_TYPE_KEY_SESSION: dict[str, str] = {
    "road_biking": "bike", "cycling": "bike", "virtual_ride": "bike",
    "indoor_cycling": "bike", "mountain_biking": "bike",
    "strength_training": "strength", "stair_climbing": "strength", "fitness_equipment": "strength",
    "hiking": "ruck", "walking": "ruck", "trail_running": "ruck", "running": "ruck",
}

_PRE_PLAN_WEEKS = 4


def _fmt_dur(seconds: float) -> str:
    m = int(seconds / 60)
    if m < 60:
        return f"{m}m"
    return f"{m // 60}h{m % 60:02d}m" if m % 60 else f"{m // 60}h"


def _fmt_min(minutes: int) -> str:
    if minutes == 0:
        return "—"
    if minutes < 60:
        return f"{minutes}m"
    h, m = divmod(minutes, 60)
    return f"{h}h{m:02d}m" if m else f"{h}h"


def _build_preplan_weeks(acts_by_date: dict) -> list[dict]:
    today = date.today()
    start = _PLAN_START - timedelta(weeks=_PRE_PLAN_WEEKS)
    start -= timedelta(days=start.weekday())
    weeks = []
    d = start
    while d < _PLAN_START:
        wk_days = []
        done_min = 0
        for i in range(7):
            day_date = d + timedelta(days=i)
            if day_date >= _PLAN_START:
                break
            day_acts = acts_by_date.get(day_date.isoformat(), [])
            primary = max(day_acts, key=lambda a: a.get("duration_seconds") or 0) if day_acts else None
            if primary:
                stype = _TYPE_KEY_SESSION.get(primary["type_key"], "rest")
                dur_fmt = _fmt_dur(primary.get("duration_seconds") or 0)
                label = primary.get("name") or stype.title()
                extra = len(day_acts) - 1
                actual_min = int(sum(a.get("duration_seconds", 0) or 0 for a in day_acts) / 60)
                done_min += actual_min
            else:
                stype, dur_fmt, label, extra, actual_min = "rest", "", "", 0, 0
            wk_days.append({
                "date": day_date,
                "day_num": day_date.day,
                "month_abbr": day_date.strftime("%b"),
                "is_today": day_date == today,
                "type": stype,
                "label": label,
                "dur_fmt": dur_fmt,
                "extra": extra,
                "actual_min": actual_min,
            })
        weeks.append({"start": d, "days": wk_days, "done_min_fmt": _fmt_min(done_min)})
        d += timedelta(weeks=1)
    return weeks


@app.get("/calendar", response_class=HTMLResponse)
async def calendar_view(request: Request):
    ctx = _build_calendar_ctx()
    _CLICKABLE_TYPES = _BIKE_TYPES | {"strength"}
    session_labels = {
        day["label"]
        for week in ctx["weeks"]
        for day in week["days"]
        if day["type"] in _CLICKABLE_TYPES
    }
    session_labels |= {d["label"] for d in EVENT_PREP_DAYS if d["type"] in _BIKE_TYPES}
    session_labels |= {v["label"] for v in CAMP_GRID_WORKOUTS.values() if v["type"] in _BIKE_TYPES}
    ctx["workout_descs"] = prefetch_workout_descriptions(list(session_labels))

    # Pre-plan history (4 weeks before plan start)
    pre_start = _PLAN_START - timedelta(weeks=_PRE_PLAN_WEEKS)
    pre_start -= timedelta(days=pre_start.weekday())
    preplan_acts = load_activities_by_date(pre_start, _PLAN_START - timedelta(days=1))
    ctx["preplan_weeks"] = _build_preplan_weeks(preplan_acts)

    # Load all activities across the plan window and mark completion + actual durations
    plan_end = ctx["weeks"][-1]["days"][-1]["date"]
    acts_by_date = load_activities_by_date(_PLAN_START, plan_end)
    today = date.today()
    for week in ctx["weeks"]:
        plan_min = sum(d["dur_min"] for d in week["days"] if d["type"] != "rest")
        done_min = 0
        for day in week["days"]:
            stype = day["type"]
            if stype == "rest" or day["date"] > today:
                day["completed"] = None
                day["actual_min"] = None
                for sub in (day.get("sub_sessions") or []):
                    sub["completed"] = None
                    sub["actual_min"] = None
            else:
                day_acts = acts_by_date.get(day["date"].isoformat(), [])
                if day.get("sub_sessions"):
                    for sub in day["sub_sessions"]:
                        sub_matched = [a for a in day_acts if a["type_key"] == sub["garmin_key"]]
                        sub["completed"] = bool(sub_matched)
                        sub["actual_min"] = (
                            int(sum(a.get("duration_seconds", 0) or 0 for a in sub_matched) / 60)
                            if sub_matched else None
                        )
                    day["completed"] = any(s["completed"] for s in day["sub_sessions"])
                    actual = sum(s["actual_min"] or 0 for s in day["sub_sessions"])
                    day["actual_min"] = actual if actual else None
                    done_min += actual
                else:
                    valid_keys = ACTIVITY_MATCH.get(stype, set())
                    matched = [a for a in day_acts if a["type_key"] in valid_keys]
                    day["completed"] = bool(matched)
                    actual = int(sum(a.get("duration_seconds", 0) or 0 for a in matched) / 60)
                    day["actual_min"] = actual if matched else None
                    done_min += actual

            # Extra standalone session (e.g. the Saturday "Rucksack then Kettlebell"
            # circuit) — display-only completion; deliberately excluded from done_min
            # / compliance so it doesn't skew plan-adherence numbers.
            ex = day.get("extra_session")
            if ex:
                if stype == "rest" or day["date"] > today:
                    ex["completed"] = None
                    ex["actual_min"] = None
                else:
                    ex_acts = [a for a in acts_by_date.get(day["date"].isoformat(), [])
                               if a["type_key"] == ex["garmin_key"]]
                    ex["completed"] = bool(ex_acts)
                    ex["actual_min"] = (int(sum(a.get("duration_seconds", 0) or 0 for a in ex_acts) / 60)
                                        if ex_acts else None)
        week["plan_min_fmt"] = _fmt_min(plan_min)
        week["done_min_fmt"] = _fmt_min(done_min) if done_min else None
        week["completion_pct"] = int(done_min / plan_min * 100) if plan_min and done_min else None
        week["days_hit"]   = sum(1 for d in week["days"] if d.get("completed") == True)
        week["days_total"] = sum(1 for d in week["days"] if d["type"] != "rest" and d["date"] <= today)

    # Current streak: consecutive completed (or rest) days up to and including today
    all_plan_days = [d for week in ctx["weeks"] for d in week["days"]]
    current_streak = 0
    for day in reversed(all_plan_days):
        if day["date"] > today:
            continue
        if day["type"] == "rest" or day.get("completed") == True:
            current_streak += 1
        else:
            break
    ctx["current_streak"] = current_streak

    # Interference flags: quality bike session within 24h of strength
    _STRENGTH_KEYS = {"strength_training", "stair_climbing"}
    for week in ctx["weeks"]:
        for day in week["days"]:
            if day["label"] not in QUALITY_BIKE_LABELS:
                continue
            date_str = day["date"].isoformat()
            prev_date_str = (day["date"] - timedelta(days=1)).isoformat()
            same_day_acts = acts_by_date.get(date_str, [])
            prev_day_acts = acts_by_date.get(prev_date_str, [])
            if any(a["type_key"] in _STRENGTH_KEYS for a in same_day_acts + prev_day_acts):
                day["interference"] = True
                day["interference_note"] = "Strength logged within 24h of quality bike session"

    # Back-to-back consecutive cycling day pairs
    btb_pairs = load_btb_summary()
    yesterday = (today - timedelta(days=1)).isoformat()
    btb_log_available = bool(acts_by_date.get(yesterday)) and any(
        a["type_key"] in _BIKE_TYPE_KEYS for a in acts_by_date.get(yesterday, [])
    )
    ctx["btb_pairs"] = btb_pairs
    ctx["btb_log_available"] = btb_log_available

    # Build single unified weeks list (plan → camp → event prep) with phase tags.
    # Plan weeks are reused after completion tracking, so their day dicts already have
    # completed/actual_min populated.
    unified: list[dict] = []
    for w in ctx["weeks"]:
        unified.append({**w, "phase": "plan", "phase_start": w["week_num"] == 1})
    for i, w in enumerate(ctx["camp_weeks"]):
        unified.append({**w, "phase": "camp", "phase_start": i == 0})
    for i, w in enumerate(ctx["combined_event_weeks"]):
        unified.append({**w, "phase": "event_prep", "phase_start": i == 0})
    ctx["unified_weeks"] = unified

    # Per-day pacing & fuelling plans for the two charity-ride days (AI, cached).
    charity_plans: list[dict] = []
    try:
        from .analysis import generate_charity_day_plans
        from .plan import CHARITY_DAYS
        plans = generate_charity_day_plans()
        for cd in CHARITY_DAYS:
            plan = plans.get(cd["day"])
            if plan:
                charity_plans.append({**cd, "plan": plan})
    except Exception:
        pass
    ctx["charity_plans"] = charity_plans

    return TEMPLATES.TemplateResponse(request=request, name="calendar.html", context=ctx)


def _plan_completion_stats() -> dict:
    """Compute per-week plan vs actual completion stats for the training page."""
    today = date.today()
    weeks_data = _calendar_weeks()
    plan_end = weeks_data[-1]["days"][-1]["date"]
    acts_by_date = load_activities_by_date(_PLAN_START, min(today, plan_end))

    completion_weeks = []
    total_plan_sessions = total_done_sessions = 0
    total_plan_min = total_done_min = 0

    for week in weeks_data:
        wk_start: date = week["start"]
        wk_end: date = wk_start + timedelta(days=6)

        # Date range label
        if wk_start.month == wk_end.month:
            date_range = f"{wk_start.day}–{wk_end.day} {wk_start.strftime('%b')}"
        else:
            date_range = f"{wk_start.strftime('%-d %b')}–{wk_end.strftime('%-d %b')}"

        plan_sessions = plan_min = done_sessions = done_min = 0
        day_statuses = []

        for day in week["days"]:
            d: date = day["date"]
            stype = day["type"]
            is_future = d > today
            is_rest = stype == "rest"

            status = "rest" if is_rest else ("future" if is_future else "pending")
            completed = None

            if not is_rest and not is_future:
                plan_sessions += 1
                plan_min += day["dur_min"]
                day_acts = acts_by_date.get(d.isoformat(), [])
                if day.get("sub_sessions"):
                    matched = any(
                        any(a["type_key"] == sub["garmin_key"] for a in day_acts)
                        for sub in day["sub_sessions"]
                    )
                    actual = int(sum(a.get("duration_seconds", 0) or 0 for a in day_acts) / 60)
                else:
                    valid_keys = ACTIVITY_MATCH.get(stype, set())
                    matched_acts = [a for a in day_acts if a["type_key"] in valid_keys]
                    matched = bool(matched_acts)
                    actual = int(sum(a.get("duration_seconds", 0) or 0 for a in matched_acts) / 60)
                completed = matched
                if matched:
                    done_sessions += 1
                    done_min += actual
                status = "done" if matched else "missed"

            day_statuses.append({
                "type": stype,
                "date": d,
                "status": status,
                "is_today": d == today,
            })

        total_plan_sessions += plan_sessions
        total_done_sessions += done_sessions
        total_plan_min += plan_min
        total_done_min += done_min

        if wk_start > today:
            wk_status = "future"
        elif wk_end >= today:
            wk_status = "current"
        else:
            wk_status = "past"

        completion_weeks.append({
            "week_num": week["week_num"],
            "date_range": date_range,
            "plan_sessions": plan_sessions,
            "done_sessions": done_sessions,
            "plan_min": plan_min,
            "done_min": done_min,
            "pct": int(done_min / plan_min * 100) if plan_min else 0,
            "status": wk_status,
            "days": day_statuses,
        })

    overall_pct = int(total_done_min / total_plan_min * 100) if total_plan_min else 0
    return {
        "completion_weeks": completion_weeks,
        "total_plan_sessions": total_plan_sessions,
        "total_done_sessions": total_done_sessions,
        "total_plan_min": total_plan_min,
        "total_done_min": total_done_min,
        "overall_pct": overall_pct,
    }


@app.get("/training", response_class=HTMLResponse)
async def training_plan(request: Request):
    ctx = _plan_completion_stats()
    return TEMPLATES.TemplateResponse(request=request, name="training.html", context=ctx)


_BIKE_SESSION_TYPES = {"bike", "tempo", "ftp", "long"}


@app.get("/compliance", response_class=HTMLResponse)
async def compliance_view(request: Request):
    ctx = _plan_completion_stats()

    # Per-discipline breakdown from day statuses
    by_type: dict[str, dict] = {
        "bike":     {"label": "Bike", "icon": "🚴", "plan": 0, "done": 0},
        "strength": {"label": "Strength", "icon": "🏋️", "plan": 0, "done": 0},
        "ruck":     {"label": "Ruck", "icon": "🎒", "plan": 0, "done": 0},
    }
    for wk in ctx["completion_weeks"]:
        for day in wk["days"]:
            if day["status"] not in ("done", "missed"):
                continue
            bucket = "bike" if day["type"] in _BIKE_SESSION_TYPES else day["type"]
            if bucket not in by_type:
                continue
            by_type[bucket]["plan"] += 1
            if day["status"] == "done":
                by_type[bucket]["done"] += 1
    for bt in by_type.values():
        bt["pct"] = int(bt["done"] / bt["plan"] * 100) if bt["plan"] else 0
    ctx["by_type"] = list(by_type.values())

    # Current streak (consecutive done/rest days working backwards from today)
    streak = 0
    all_days = [d for wk in ctx["completion_weeks"] for d in wk["days"]]
    for day in reversed(all_days):
        if day["status"] == "future":
            continue
        if day["status"] in ("done", "rest"):
            streak += 1
        else:
            break
    ctx["streak"] = streak

    # Cumulative adherence % per week (None for future weeks)
    cum_plan = cum_done = 0
    cumulative: list[Optional[int]] = []
    for wk in ctx["completion_weeks"]:
        if wk["status"] == "future":
            cumulative.append(None)
        else:
            cum_plan += wk["plan_min"]
            cum_done += wk["done_min"]
            cumulative.append(int(cum_done / cum_plan * 100) if cum_plan else 0)
    ctx["cumulative_pcts"] = cumulative

    return TEMPLATES.TemplateResponse(request=request, name="compliance.html", context=ctx)


@app.get("/nutrition", response_class=HTMLResponse)
async def nutrition_plan(request: Request):
    today = _today()
    days_since_start = (today - _PLAN_START).days
    cycle_week = max(0, days_since_start // 7) % 4  # 0-indexed: 0=w1, 1=w2, 2=w3, 3=w4

    recent = raw_history(3)
    today_nut = next((r for r in reversed(recent) if r.get("calories_consumed") is not None), None)

    from .nutrition_plan import SUPPLEMENTS, _SUPPLEMENT_DISCLAIMER, protein_target_g

    return TEMPLATES.TemplateResponse(
        request=request,
        name="nutrition.html",
        context={
            "today": today.isoformat(),
            "cycle_week": cycle_week,
            "cal_today":     int(today_nut["calories_consumed"])    if today_nut and today_nut.get("calories_consumed")    else None,
            "tdee_today":    int(today_nut["calorie_goal_adjusted"]) if today_nut and today_nut.get("calorie_goal_adjusted") else None,
            "carbs_today":   round(today_nut["carbs_consumed"])     if today_nut and today_nut.get("carbs_consumed")       else None,
            "protein_today": round(today_nut["protein_consumed"])   if today_nut and today_nut.get("protein_consumed")     else None,
            "supplements":   [{"name": n, "dose": d, "why": w} for n, d, w in SUPPLEMENTS],
            "supplement_disclaimer": _SUPPLEMENT_DISCLAIMER,
            "protein_target": protein_target_g(),
        },
    )


@app.get("/nutrition/meals", response_class=HTMLResponse)
async def nutrition_meals(request: Request):
    today = _today()
    days_since_start = (today - _PLAN_START).days
    cycle_week = max(0, days_since_start // 7) % 4
    return TEMPLATES.TemplateResponse(
        request=request,
        name="meals.html",
        context={"cycle_week": cycle_week},
    )


@app.get("/nutrition/fuelling", response_class=HTMLResponse)
async def nutrition_fuelling(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="fuelling.html", context={})


@app.get("/nutrition/recipes", response_class=HTMLResponse)
async def nutrition_recipes(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="recipes.html", context={})


@app.get("/nutrition/recipes/weekend-fuel", response_class=HTMLResponse)
async def nutrition_recipes_weekend_fuel(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="recipes-weekend-fuel.html", context={})


@app.get("/nutrition/recipes/griddle", response_class=HTMLResponse)
async def nutrition_recipes_griddle(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="recipes-griddle.html", context={})


@app.get("/nutrition/shopping-list", response_class=HTMLResponse)
async def nutrition_shopping_list(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="asda-shopping-list.html", context={})


@app.get("/nutrition/lidl-shopping-list", response_class=HTMLResponse)
async def nutrition_lidl_shopping_list(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="lidl-shopping-list.html", context={})


_ARCHITECTURE_HTML = Path(__file__).resolve().parent / "architecture.html"


@app.get("/architecture", response_class=HTMLResponse)
async def architecture_diagram(_=Depends(_require_auth)):
    if not _ARCHITECTURE_HTML.is_file():
        raise HTTPException(status_code=404, detail="architecture.html not found")
    return HTMLResponse(content=_ARCHITECTURE_HTML.read_text(encoding="utf-8"))


@app.get("/tenerife", response_class=HTMLResponse)
async def tenerife_view(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="tenerife.html", context={})


@app.get("/haute-route", response_class=HTMLResponse)
def haute_route_view(request: Request):
    today = date.today()
    history = pmc_history(days=1)
    today_pmc = history[-1] if history else {}
    ctl_now = today_pmc.get("ctl")
    atl_now = today_pmc.get("atl")

    hr_proj_data: list[dict] = []
    hr_start_ctl: Optional[float] = None
    hr_event_ctl: Optional[float] = None

    if ctl_now is not None:
        if today < _PLAN_EVENT_DATE:
            # Before charity ride: project through the remaining 12-week plan, then apply rest gap
            _, event_ctl = _ctl_projection(ctl_now, atl_now or ctl_now)
            gap_days = (HR_PLAN_START - _PLAN_EVENT_DATE).days  # 22
            hr_start_ctl = max(0.0, event_ctl + _CTL_REST_DECLINE * gap_days)
        elif today < HR_PLAN_START:
            # Between charity ride and HR plan start: apply remaining rest days
            gap_days = (HR_PLAN_START - today).days
            hr_start_ctl = max(0.0, ctl_now + _CTL_REST_DECLINE * gap_days)
        else:
            hr_start_ctl = ctl_now

        hr_proj_data = _hr_ctl_projection(hr_start_ctl)
        hr_event_ctl = hr_proj_data[-1]["ctl"] if hr_proj_data else None

    stage_plans: dict = {}
    peak_decoupling_flags: dict = {}
    try:
        from .analysis import generate_hr_stage_plans, peak_sim_decoupling_flags
        weeks = build_hr_calendar_weeks()
        stage_plans = generate_hr_stage_plans()
        peak_decoupling_flags = peak_sim_decoupling_flags(weeks)
    except Exception:
        weeks = build_hr_calendar_weeks()

    ctx = {
        "active_tab":    "haute_route",
        "hr_subnav":     "plan",
        "phases":        HR_PHASES,
        "weeks":         weeks,
        "event_weeks":   build_hr_event_weeks(),
        "event_start":   HR_EVENT_START,
        "event_end":     HR_EVENT_END,
        "hr_proj_data":  hr_proj_data,
        "hr_start_ctl":  round(hr_start_ctl, 1) if hr_start_ctl is not None else None,
        "hr_event_ctl":  round(hr_event_ctl, 1) if hr_event_ctl is not None else None,
        "heat_protocol": HR_HEAT_PROTOCOL,
        "lessons_2012":  LESSONS_2012,
        "stage_plans":   stage_plans,
        "peak_decoupling_flags": peak_decoupling_flags,
        "power_meter_active": power_meter_active(),
    }
    return TEMPLATES.TemplateResponse(request=request, name="hr_calendar.html", context=ctx)


@app.get("/haute-route/2012-postmortem", response_class=HTMLResponse)
def haute_route_2012_postmortem(request: Request):
    return TEMPLATES.TemplateResponse(
        request=request,
        name="hr_2012_postmortem.html",
        context={"active_tab": "haute_route", "hr_subnav": "postmortem"},
    )


@app.get("/haute-route/power-protocol", response_class=HTMLResponse)
def haute_route_power_protocol(request: Request):
    return TEMPLATES.TemplateResponse(
        request=request,
        name="hr_power_protocol.html",
        context={"active_tab": "haute_route", "hr_subnav": "power"},
    )



def _week_summary() -> Optional[dict]:
    """Per-day training breakdown for the current Mon–Sun week."""
    today = date.today()
    mon = today - timedelta(days=today.weekday())
    sun = mon + timedelta(days=6)

    acts_by_date = load_activities_by_date(mon, min(sun, today))

    plan_min_total = 0
    done_min_total = 0
    day_rows = []

    for i in range(7):
        d = mon + timedelta(days=i)
        is_today = d == today
        is_future = d > today

        session = session_for_date(d)
        stype = session[0] if session else "rest"
        slabel = session[1] if session else "Rest"
        sdur = session[2] if session else 0

        if stype != "rest" and sdur:
            plan_min_total += sdur

        actual_min = None
        completed = None
        if not is_future and stype != "rest":
            day_acts = acts_by_date.get(d.isoformat(), [])
            compound = COMPOUND_SESSIONS.get(slabel)
            if compound:
                matched = [a for a in day_acts
                           if any(a["type_key"] == s["garmin_key"] for s in compound)]
            else:
                valid_keys = ACTIVITY_MATCH.get(stype, set())
                matched = [a for a in day_acts if a["type_key"] in valid_keys]
            completed = bool(matched)
            if matched:
                actual_min = int(sum(a.get("duration_seconds", 0) or 0 for a in matched) / 60)
                done_min_total += actual_min

        readiness = None
        if not is_future and not is_today:
            m = load(d)
            if m:
                stats = baseline_stats(d)
                readiness = composite_score(m, stats)

        day_rows.append({
            "date": d,
            "day_name": d.strftime("%a"),
            "type": stype,
            "label": slabel,
            "dur_min": sdur,
            "actual_min": actual_min,
            "completed": completed,
            "is_today": is_today,
            "is_future": is_future,
            "readiness": readiness,
        })

    readiness_vals = [r["readiness"] for r in day_rows if r["readiness"] is not None]
    avg_readiness = sum(readiness_vals) / len(readiness_vals) if readiness_vals else None

    # Last week total training minutes for comparison
    last_mon = mon - timedelta(weeks=1)
    last_acts = load_activities_by_date(last_mon, mon - timedelta(days=1))
    last_done_min = sum(
        int((a.get("duration_seconds", 0) or 0) / 60)
        for d_acts in last_acts.values()
        for a in d_acts
        if any(a["type_key"] in keys for keys in ACTIVITY_MATCH.values())
    )

    days_into = (today - _PLAN_START).days
    week_num = max(1, days_into // 7 + 1) if today >= _PLAN_START else None
    pct = int(done_min_total / plan_min_total * 100) if plan_min_total else 0

    return {
        "days": day_rows,
        "plan_min_fmt": _fmt_min(plan_min_total),
        "done_min_fmt": _fmt_min(done_min_total) if done_min_total else "0m",
        "pct": pct,
        "bar_filled": min(pct, 100),
        "avg_readiness": avg_readiness,
        "last_done_fmt": _fmt_min(last_done_min) if last_done_min else "0m",
        "week_num": week_num,
        "week_start": mon,
    }


def _body_context() -> dict[str, Any]:
    body_rows = load_body_metrics(days=180)
    bp_rows = load_blood_pressure(days=90)

    # Latest body metrics
    latest_body = body_rows[-1] if body_rows else None
    # Latest BP (most recent timestamp)
    latest_bp = bp_rows[-1] if bp_rows else None

    bp_class_label, bp_class_colour = None, None
    if latest_bp and latest_bp.get("systolic") and latest_bp.get("diastolic"):
        bp_class_label, bp_class_colour = bp_classification(
            latest_bp["systolic"], latest_bp["diastolic"]
        )

    # Chart series: one point per day (latest reading wins)
    weight_by_date: dict[str, Optional[float]] = {}
    fat_by_date: dict[str, Optional[float]] = {}
    muscle_by_date: dict[str, Optional[float]] = {}
    hydration_by_date: dict[str, Optional[float]] = {}
    for r in body_rows:
        d = r["date"]
        if r.get("weight_kg") is not None:
            weight_by_date[d] = r["weight_kg"]
        if r.get("fat_pct") is not None:
            fat_by_date[d] = r["fat_pct"]
        if r.get("muscle_mass_kg") is not None:
            muscle_by_date[d] = r["muscle_mass_kg"]
        if r.get("hydration_pct") is not None:
            hydration_by_date[d] = r["hydration_pct"]

    weight_dates = sorted(weight_by_date)
    weight_values = [weight_by_date[d] for d in weight_dates]
    fat_dates = sorted(fat_by_date)
    fat_values = [fat_by_date[d] for d in fat_dates]
    muscle_dates = sorted(muscle_by_date)
    muscle_values = [muscle_by_date[d] for d in muscle_dates]
    hydration_dates = sorted(hydration_by_date)
    hydration_values = [hydration_by_date[d] for d in hydration_dates]

    # BP chart: one point per reading
    bp_dates = [r["date"] for r in bp_rows]
    bp_sys = [r.get("systolic") for r in bp_rows]
    bp_dia = [r.get("diastolic") for r in bp_rows]

    # Tick labels — abbreviated dates
    def _short(ds: list[str]) -> list[str]:
        from datetime import date as _date
        out = []
        for s in ds:
            try:
                d = _date.fromisoformat(s)
                out.append(d.strftime("%-d %b"))
            except Exception:
                out.append(s)
        return out

    pmc_today = pmc_history(days=1)[-1] if pmc_history(days=1) else {}
    recent_metrics = raw_history(14)
    body_analysis = generate_body_analysis(body_rows, latest_body or {}, pmc_today, recent_metrics)

    # Calorie intake from food log (last 14 days of data)
    con_vals = [r.get("calories_consumed")     for r in recent_metrics if r.get("calories_consumed")     is not None]
    adj_vals = [r.get("calorie_goal_adjusted") for r in recent_metrics if r.get("calorie_goal_adjusted") is not None]
    cal_ctx: dict = {}
    if con_vals:
        cal_ctx["avg_consumed"]   = round(sum(con_vals) / len(con_vals))
        cal_ctx["avg_tdee"]       = round(sum(adj_vals) / len(adj_vals)) if adj_vals else None
        cal_ctx["days_logged"]    = len(con_vals)
        if cal_ctx["avg_tdee"]:
            cal_ctx["avg_deficit"] = cal_ctx["avg_tdee"] - cal_ctx["avg_consumed"]
    # Today's specific values (most recent row with data)
    today_nut = next((r for r in reversed(recent_metrics) if r.get("calories_consumed") is not None), None)
    if today_nut:
        cal_ctx["today_consumed"] = today_nut.get("calories_consumed")
        cal_ctx["today_tdee"]     = today_nut.get("calorie_goal_adjusted")
        cal_ctx["today_goal"]     = today_nut.get("calorie_goal")
        if today_nut.get("carbs_consumed") is not None:
            cal_ctx["today_carbs"] = round(today_nut["carbs_consumed"])
        if today_nut.get("protein_consumed") is not None:
            cal_ctx["today_protein"] = round(today_nut["protein_consumed"])
    # 14-day macro averages
    carbs_vals   = [r["carbs_consumed"]   for r in recent_metrics if r.get("carbs_consumed")   is not None]
    protein_vals = [r["protein_consumed"] for r in recent_metrics if r.get("protein_consumed") is not None]
    if carbs_vals:
        cal_ctx["avg_carbs"]   = round(sum(carbs_vals) / len(carbs_vals))
    if protein_vals:
        cal_ctx["avg_protein"] = round(sum(protein_vals) / len(protein_vals))

    # Calorie chart (last 14 days) — convert date objects to ISO strings for _short()
    _cal_rows   = [r for r in recent_metrics if r.get("calories_consumed") is not None]
    _cal_isos   = [r["date"].isoformat() if hasattr(r["date"], "isoformat") else str(r["date"]) for r in _cal_rows]
    cal_values  = [r["calories_consumed"] for r in _cal_rows]
    tdee_values = [r.get("calorie_goal_adjusted") for r in _cal_rows]
    cal_labels  = _short(_cal_isos)

    est_wkg = None
    measured_wkg = None
    try:
        est_wkg = latest_estimated_wkg()
        measured_wkg = latest_measured_wkg()
    except Exception:
        pass

    return {
        "latest_body": latest_body,
        "latest_bp": latest_bp,
        "est_wkg": est_wkg,
        "measured_wkg": measured_wkg,
        "bp_class_label": bp_class_label,
        "bp_class_colour": bp_class_colour,
        "weight_dates": _short(weight_dates),
        "weight_values": weight_values,
        "fat_dates": _short(fat_dates),
        "fat_values": fat_values,
        "muscle_dates": _short(muscle_dates),
        "muscle_values": muscle_values,
        "hydration_dates": _short(hydration_dates),
        "hydration_values": hydration_values,
        "bp_dates": _short(bp_dates),
        "bp_sys": bp_sys,
        "bp_dia": bp_dia,
        "has_body": bool(body_rows),
        "has_bp": bool(bp_rows),
        "body_analysis": body_analysis,
        "cal_ctx": cal_ctx,
        "cal_dates": cal_labels,
        "cal_values": cal_values,
        "tdee_values": tdee_values,
    }


@app.get("/body", response_class=HTMLResponse)
async def body_view(request: Request, msg: Optional[str] = None):
    ctx = _body_context()
    ctx["flash_msg"] = msg
    return TEMPLATES.TemplateResponse(request=request, name="body.html", context=ctx)


@app.get("/body-refresh", response_class=RedirectResponse)
def body_refresh():
    email_addr = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")
    if email_addr and password:
        try:
            api = get_api(email_addr, password)
            body_readings = fetch_body_composition(api, days=90)
            if body_readings:
                save_body_metrics(body_readings)
            bp_readings = fetch_blood_pressure(api, days=90)
            if bp_readings:
                save_blood_pressure(bp_readings)
        except Exception:
            pass
    return RedirectResponse(url="/body", status_code=303)


@app.get("/withings-sync", response_class=RedirectResponse)
def withings_sync():
    """Push Withings measurements to Garmin Connect, then refresh body data from Garmin."""
    email_addr = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")
    msg = "error"
    if email_addr and password:
        try:
            api = get_api(email_addr, password)
            from .withings import sync_withings_to_garmin
            synced = sync_withings_to_garmin(api, days=30)
            body_readings = fetch_body_composition(api, days=90)
            if body_readings:
                save_body_metrics(body_readings)
            bp_readings = fetch_blood_pressure(api, days=90)
            if bp_readings:
                save_blood_pressure(bp_readings)
            msg = "synced" if synced else "no_data"
        except Exception:
            logger.exception("Withings sync failed")
    return RedirectResponse(url=f"/body?msg={msg}", status_code=303)


@app.get("/sleep", response_class=HTMLResponse)
async def sleep_view(request: Request):
    data = sleep_history(30)

    # Last night (most recent non-None sleep_score row)
    last = next((d for d in reversed(data) if d["sleep_score"] is not None), None)

    # 7-day and 30-day averages for summary cards
    def _avg(key, rows):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    recent = [d for d in data if d["sleep_score"] is not None][-7:]
    avgs_7 = {k: _avg(k, recent) for k in ("sleep_score", "sleep_hours", "deep_pct", "rem_pct", "spo2", "hrv", "respiration")}
    avgs_30 = {k: _avg(k, data) for k in ("sleep_score", "sleep_hours", "deep_pct", "rem_pct", "spo2", "hrv", "respiration")}

    analysis = generate_sleep_analysis(data, avgs_7, avgs_30)

    return TEMPLATES.TemplateResponse(request=request, name="sleep.html", context={
        "request":    request,
        "data":       data,
        "last":       last,
        "avgs_7":     avgs_7,
        "avgs_30":    avgs_30,
        "analysis":   analysis,
        "has_stages": any(d["deep_hours"] is not None for d in data),
        "has_spo2":   any(d["spo2"] is not None for d in data),
        "has_resp":   any(d["respiration"] is not None for d in data),
        "has_hrv":    any(d["hrv"] is not None for d in data),
    })


@app.get("/nutrition-test")
def nutrition_test():
    """Debug endpoint: return raw Garmin nutrition API responses for today."""
    import json as _json
    email_addr = os.getenv("GARMIN_EMAIL", "")
    password   = os.getenv("GARMIN_PASSWORD", "")
    today_str  = date.today().isoformat()
    out: dict = {"date": today_str}
    if not (email_addr and password):
        out["error"] = "GARMIN_EMAIL / GARMIN_PASSWORD not set"
        return JSONResponse(out)
    try:
        api = get_api(email_addr, password)
        for method in ("get_nutrition_daily_food_log",
                        "get_nutrition_daily_meals",
                        "get_nutrition_daily_settings"):
            try:
                out[method] = getattr(api, method)(today_str)
            except Exception as exc:
                out[method] = {"error": str(exc)}
    except Exception as exc:
        out["error"] = f"API init failed: {exc}"
    return JSONResponse(out)


@app.get("/refresh", response_class=RedirectResponse)
def refresh(date: Optional[str] = None):
    target = date_fromisoformat_safe(date) if date else _today()
    _build_context(target, force_fetch=True)
    redirect_url = f"/?date={target.isoformat()}"
    return RedirectResponse(url=redirect_url, status_code=303)


@app.get("/recovery-suggestion")
def recovery_suggestion_view(date: Optional[str] = None):
    if not date:
        raise HTTPException(status_code=400, detail="date parameter required")
    target = date_fromisoformat_safe(date)
    session = session_for_date(target)
    if not session:
        raise HTTPException(status_code=404, detail="no plan session for this date")

    # Remaining non-rest sessions this week (after the missed day, up to Sunday)
    upcoming: list[tuple] = []
    for i in range(1, 7 - target.weekday()):
        d = target + timedelta(days=i)
        s = session_for_date(d)
        if s and s[0] != "rest":
            upcoming.append((d, s))

    recent = raw_history(3)
    text = generate_recovery_suggestion(target, session, upcoming, recent)
    return JSONResponse({"suggestion": text})


def _today() -> date:
    from datetime import date as _date
    return _date.today()


def date_fromisoformat_safe(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return _today()


# ── AI Coach chat ─────────────────────────────────────────────────────────────

def _coach_system() -> str:
    base = (
        "You are an experienced endurance coach working with an amateur athlete preparing for "
        "a 2-day charity cycling event (Ghent to Amsterdam, ~310 km total, 13–14 Sep 2026). "
        "The athlete is 50+, training 6+ hours/week mixing cycling, kettlebells, rucking, and MaxiClimber. "
        "They also have a longer-term goal: Haute Route Alpes 2027 (7 stages, ~900 km, ~25,000 m elevation).\n\n"
        "You have access to their live Garmin data in the context block below. "
        "Use it to give specific, evidence-based advice referencing actual numbers.\n\n"
        "Response style: direct and concise (2–4 short paragraphs). Use **bold** for key numbers/points.\n\n"
        "When you recommend modifying a planned session, call propose_plan_change once per date — "
        "each call renders its own confirmation card. For multi-day swaps (e.g. defer quality to tomorrow), "
        "call the tool separately for every date that changes. After the tool call(s), briefly explain "
        "the proposed change(s) in your text (do not say 'above' or 'below' — just refer to 'the proposal card(s)').\n\n"
        "The context block below already summarises EVERY dashboard tab — readiness, training load, "
        "sleep, body composition, nutrition (today + this week), compliance, zone distribution, "
        "durability, monotony/strain, acclimation, FTP history, interference flags, the 12-week plan, "
        "Tenerife camp, event prep and the Haute Route phases. For full detail behind any of these, call "
        "a read tool: get_meal_cycle (full 4-week meals + shopping list), get_activity_analysis (a past "
        "session's full analysis), get_sleep_history, get_performance_detail, get_hr_plan (full 46-week "
        "plan), get_compliance_detail, get_workout_description, get_fuelling_plan, get_event_plans "
        "(charity & Haute Route pacing). You have full visibility — never tell the athlete you can't see "
        "their data; if you need depth, fetch it with a read tool.\n\n"
        "Training plan context: 12-week plan runs 18 May – 9 Aug 2026, followed by Tenerife cycling camp "
        "(13–27 Aug) and event prep block (Aug 31 – Sep 12). Builds from Zone 2 base to back-to-back long "
        "rides simulating the 2-day event. Key sessions: Zone 2 rides, FTP tests (wks 3/7/12), hill repeats "
        "and tempo from wk 5, progressive rucking (Mersea Coastal Spur build in wks 9–10), KB + MaxiClimber strength.\n\n"
        "PMC note: Garmin TSB units differ from Coggan TSS. Rough bands: "
        "fresh > −50, moderate load −50 to −150, heavy load −150 to −250, very high fatigue < −250.\n\n"
    )
    if power_meter_active():
        return base + (
            "HR-vs-power note: the athlete has a power meter and trains on BOTH channels. "
            "Use watts for climb and interval execution feedback; keep HR primary for readiness, "
            "fatigue, heat, altitude and variable conditions. HR drifts with heat, dehydration, sleep "
            "and altitude — on hot days or above 2000 m, defer to the HR cap when HR exceeds "
            "power-predicted effort. The measured FTP/W/kg in context is the primary number; "
            "the VO2max-derived estimate is a secondary cross-check only."
            + "\n\n" + ATHLETE_CONSTRAINTS
        )
    return base + (
        "HR-vs-power note: this athlete trains and races on HEART RATE, not power. HR drifts with heat, "
        "dehydration, fatigue, sleep, caffeine and altitude, and rises late in long climbs (cardiac drift) "
        "at steady effort — so treat HR zones as a guide, not a hard ceiling, and cross-check with perceived "
        "effort, especially on hot days and mountain stages. The estimated W/kg is a coarse VO2max-derived "
        "proxy (no power meter) — discuss it as a trend, never as a measured number."
        + "\n\n" + ATHLETE_CONSTRAINTS
    )

_COACH_TOOL = {
    "name": "propose_plan_change",
    "description": (
        "Propose changing a planned session — duration, type, or both. The athlete must confirm "
        "before the change is applied. Use session_type and new_label when swapping to a different "
        "activity type (e.g. ruck → bike ride). Omit them when only the duration is changing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "date":         {"type": "string",  "description": "Session date (YYYY-MM-DD)"},
            "duration_min": {"type": "integer", "description": "New duration in minutes"},
            "reason":       {"type": "string",  "description": "Why this change is recommended (1–2 sentences)"},
            "session_type": {"type": "string",  "description": "New session type only if swapping activity type. One of: bike, long, tempo, ftp, strength, ruck, rest"},
            "new_label":    {"type": "string",  "description": "New session label only if swapping activity type, e.g. 'Z2 Ride', 'Easy Ride'"},
        },
        "required": ["date", "duration_min", "reason"],
    },
}


# Read-only tools: the always-on context carries a summary of every tab; these let
# the coach pull the full detail behind any of them on demand (so we don't bloat
# every message). Each returns a plain-text string via `_dispatch_read_tool`.
_READ_TOOLS = [
    {
        "name": "get_meal_cycle",
        "description": "Full 4-week nutrition cycle (every meal + macros) plus a per-week shopping tally. Use this to build a weekly shopping list or compare meals across days/weeks.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_activity_analysis",
        "description": "Full post-workout AI analysis (plus interval-rep HR data if present) for a past session. Identify it by date (YYYY-MM-DD) or activity_id; omit both for the most recent analysed session.",
        "input_schema": {"type": "object", "properties": {
            "date":        {"type": "string",  "description": "Activity date YYYY-MM-DD"},
            "activity_id": {"type": "integer", "description": "Garmin activity id"},
        }},
    },
    {
        "name": "get_sleep_history",
        "description": "Nightly sleep table (score, duration, stage %, HRV) for the last N days (default 30).",
        "input_schema": {"type": "object", "properties": {
            "days": {"type": "integer", "description": "Days back (default 30)"},
        }},
    },
    {
        "name": "get_performance_detail",
        "description": "Performance-tab detail: durability (late-ride HR drift), Foster monotony/strain, estimated FTP/W-kg history, and weekly zone distribution.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_hr_plan",
        "description": "Full 46-week Haute Route Alpes 2027 plan: phases and week-by-week sessions, plus the 7 event stages (km/elevation/key climb).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_compliance_detail",
        "description": "Full per-week plan-vs-actual compliance breakdown across the 12-week plan.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_workout_description",
        "description": "Cached coaching description for a planned session label (e.g. 'Sweetspot Ride').",
        "input_schema": {"type": "object", "properties": {
            "label": {"type": "string"},
        }, "required": ["label"]},
    },
    {
        "name": "get_fuelling_plan",
        "description": "Cached in-ride fuelling plan (carbs/fluid/sodium) for a session type and duration in minutes.",
        "input_schema": {"type": "object", "properties": {
            "session_type": {"type": "string"},
            "dur_min":      {"type": "integer"},
        }, "required": ["session_type", "dur_min"]},
    },
    {
        "name": "get_event_plans",
        "description": "AI pacing & fuelling plans for the two Ghent→Amsterdam charity-ride days and the Haute Route stages. May take a moment if not yet generated.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

_READ_TOOL_NAMES = {t["name"] for t in _READ_TOOLS}


def _dispatch_read_tool(name: str, tool_input: dict) -> str:
    """Run one read tool and return its result as plain text. Never raises."""
    try:
        if name == "get_meal_cycle":
            from .nutrition_plan import meal_cycle_full
            return meal_cycle_full()

        if name == "get_activity_analysis":
            from .analysis import load_analysis
            recent = load_recent_activities(days=60)
            act_id = tool_input.get("activity_id")
            if act_id:
                target_ids = [int(act_id)]
            elif tool_input.get("date"):
                target_ids = [a["activity_id"] for a in recent if a.get("date") == tool_input["date"]]
            else:
                target_ids = next(([a["activity_id"]] for a in recent if load_analysis(a["activity_id"])), [])
            if not target_ids:
                return "No matching activity found (try a date shown in 'Recent Activities')."
            out: list[str] = []
            for aid in target_ids:
                an = load_analysis(aid)
                if not an:
                    out.append(f"Activity {aid}: no analysis on file yet.")
                    continue
                out.append(f"### {an.get('date','')} — {an.get('name') or an.get('type_key','activity')}")
                out.append(an.get("analysis_text") or an.get("summary") or "(no analysis text)")
                for i, rep in enumerate(an.get("interval_reps") or [], 1):
                    out.append(f"  Rep {i}: " + ", ".join(f"{k} {v}" for k, v in rep.items()))
            return "\n".join(out)

        if name == "get_sleep_history":
            days = int(tool_input.get("days") or 30)
            lines = [f"Sleep — last {days} nights (most recent last):"]
            for r in sleep_history(days):
                if r.get("sleep_score") is None:
                    continue
                seg = f"  {r['date']}: score {r['sleep_score']}, {r.get('sleep_hours')}h"
                if r.get("deep_pct") is not None:
                    seg += f", deep {r['deep_pct']}% / REM {r['rem_pct']}%"
                if r.get("hrv") is not None:
                    seg += f", HRV {r['hrv']}"
                lines.append(seg)
            return "\n".join(lines) if len(lines) > 1 else "No sleep data recorded."

        if name == "get_performance_detail":
            today = date.today()
            lines = ["## Performance detail"]
            dur = load_durability(180)
            if dur:
                lines.append("Durability (late-ride HR drift, rides ≥90min):")
                for r in dur[-8:]:
                    lines.append(f"  {r['date']}: {r['first_third_hr']:.0f}→{r['final_third_hr']:.0f}bpm, drift {r['drift_pct']:+.1f}%")
            for r in weekly_monotony_strain(8):
                if "Foster monotony/strain (last 8 weeks):" not in lines:
                    lines.append("Foster monotony/strain (last 8 weeks):")
                mono_s = f"{r['monotony']:.2f}" if r.get("monotony") is not None else "—"
                strain_s = f"{r['strain']:.0f}" if r.get("strain") is not None else "—"
                lines.append(f"  wk {r['label']}: load {r['weekly_load']:.0f}, monotony {mono_s}, strain {strain_s}")
            if power_meter_active():
                mwkg = measured_wkg_history(180)
                if mwkg:
                    lines.append("Measured FTP / W-kg (from FTP tests):")
                    for r in mwkg[-8:]:
                        lines.append(f"  {r['date']}: {r['ftp_w']}W, {r['wkg']} W/kg ({r['weight_kg']}kg)")
                pdec = load_power_durability(180)
                if pdec:
                    lines.append("Pw:HR decoupling (rides ≥90min):")
                    for r in pdec[-5:]:
                        lines.append(
                            f"  {r['date']}: decoupling {r['decoupling_pct']:+.1f}%  "
                            f"(HR drift {r['hr_drift_pct']:+.1f}%, power drift {r['power_drift_pct']:+.1f}%)"
                        )
                pzd = intensity_distribution_by_week_power(today - timedelta(days=56), today)
                if pzd:
                    lines.append("Power zone distribution by week:")
                    for w in pzd:
                        lines.append(
                            f"  {w['week_label']}: Z1 {w['z1_pct']}% Z2 {w['z2_pct']}% "
                            f"Z3 {w['z3_pct']}% Z4 {w['z4_pct']}% Z5 {w['z5_pct']}% ({w['total_min']}min)"
                        )
            wkg = estimated_wkg_history(180)
            if wkg:
                est_label = "Estimated FTP / W-kg (VO2max proxy"
                est_label += ", secondary)" if power_meter_active() else ", no power meter)"
                lines.append(est_label + ":")
                for r in wkg[-8:]:
                    lines.append(f"  {r['date']}: VO2max {r['vo2_max']}, ~{r['est_ftp_w']}W, {r['wkg']} W/kg ({r['weight_kg']}kg)")
            zd = intensity_distribution_by_week(today - timedelta(days=56), today)
            if zd:
                lines.append("Zone distribution by week (cycling):")
                for w in zd:
                    lines.append(f"  {w['week_label']}: Z1 {w['z1_pct']}% Z2 {w['z2_pct']}% Z3 {w['z3_pct']}% Z4 {w['z4_pct']}% Z5 {w['z5_pct']}% ({w['total_min']}min)")
            return "\n".join(lines) if len(lines) > 1 else "No performance detail available yet."

        if name == "get_hr_plan":
            from .hr_plan import hr_session_for_date as _hrs, HR_PLAN_START as _HRS, HR_EVENT_STAGES
            lines = ["## Haute Route Alpes 2027 — full plan"]
            for ph in HR_PHASES:
                lines.append(f"Phase {ph['label']}: weeks {ph['week_start']}–{ph['week_end']}")
            for wk in range(46):
                wk_start = _HRS + timedelta(days=wk * 7)
                day_lines = []
                for off in range(7):
                    d = wk_start + timedelta(days=off)
                    sess = _hrs(d)
                    if sess and sess[0] != "rest":
                        day_lines.append(f"{d.strftime('%a')} {sess[1]} ({sess[2]}min)")
                if day_lines:
                    lines.append(f"Wk{wk+1} ({wk_start.isoformat()}): " + "; ".join(day_lines))
            lines.append("Event stages:")
            for s in HR_EVENT_STAGES:
                lines.append(f"  Stage {s['day']} ({s['date'].isoformat()}) {s['label']}: "
                             f"{s['km']}km, {s['elev_m']}m, key climb {s['key_climb']}")
            return "\n".join(lines)

        if name == "get_compliance_detail":
            stats = _plan_completion_stats()
            lines = [f"## Plan compliance — full breakdown (overall {stats.get('overall_pct', 0)}% by volume)"]
            for w in stats.get("completion_weeks", []):
                lines.append(f"  Wk{w['week_num']} ({w['date_range']}) [{w['status']}]: "
                             f"{w['done_sessions']}/{w['plan_sessions']} sessions, {w['pct']}% volume "
                             f"({w['done_min']}/{w['plan_min']}min)")
            return "\n".join(lines)

        if name == "get_workout_description":
            from .analysis import _load_workout_descs
            label = (tool_input.get("label") or "").strip()
            desc = _load_workout_descs().get(label)
            return f"{label}: {desc}" if desc else f"No cached description for '{label}'."

        if name == "get_fuelling_plan":
            from .analysis import _load_fuelling_plans, fuelling_session_key
            stype = (tool_input.get("session_type") or "").strip()
            dur_min = int(tool_input.get("dur_min") or 0)
            plan = _load_fuelling_plans().get(fuelling_session_key(stype, dur_min))
            if not plan:
                return f"No cached fuelling plan for {stype} {dur_min}min (only generated for endurance sessions ≥75min)."
            return "\n".join(f"{k}: {v}" for k, v in plan.items() if v not in (None, ""))

        if name == "get_event_plans":
            from .analysis import generate_charity_day_plans, generate_hr_stage_plans
            lines = ["## Charity ride (Ghent→Amsterdam) — day plans"]
            charity = generate_charity_day_plans()
            if charity:
                for day in sorted(charity):
                    p = charity[day]
                    lines.append(f"Day {day}: " + "; ".join(f"{k}: {v}" for k, v in p.items()))
            else:
                lines.append("  (not generated yet)")
            lines.append("## Haute Route — stage plans")
            stages = generate_hr_stage_plans()
            if stages:
                for day in sorted(stages):
                    p = stages[day]
                    lines.append(f"Stage {day}: " + "; ".join(f"{k}: {v}" for k, v in p.items()))
            else:
                lines.append("  (not generated yet)")
            return "\n".join(lines)

        return f"Unknown tool: {name}"
    except Exception as exc:
        logger.exception("read-tool %s failed", name)
        return f"({name} is temporarily unavailable: {exc})"



_COACH_MAX_TOOL_TURNS = 6


def _base_plan_session(d: date) -> tuple[str, str, int] | None:
    """Plan session for a date ignoring plan_overrides (for proposal 'before' state)."""
    from .plan import PLAN_START, TRAINING_WEEKS, _PLAN_DAYS

    delta = (d - PLAN_START).days
    if 0 <= delta < _PLAN_DAYS:
        week_idx, day_idx = divmod(delta, 7)
        return TRAINING_WEEKS[week_idx][day_idx]
    from .hr_plan import hr_session_for_date
    from .plan import session_for_date_extended

    return session_for_date_extended(d) or hr_session_for_date(d)


def _enrich_plan_proposal(raw: dict) -> dict:
    """Normalise a propose_plan_change tool payload for the confirmation UI."""
    proposal = dict(raw)
    try:
        d = date.fromisoformat(proposal["date"])
        ov = get_plan_override(proposal["date"])
        base = _base_plan_session(d)
        if ov:
            current_type, current_label, current_dur = ov["session_type"], ov["label"], ov["duration_min"]
        elif base:
            current_type, current_label, current_dur = base
        else:
            current_type = current_label = current_dur = None
        proposal["session_type"] = proposal.pop("session_type", None) or current_type
        proposal["session_label"] = proposal.pop("new_label", None) or current_label
        proposal["current_session_label"] = current_label
        proposal["current_duration_min"] = current_dur
    except Exception:
        proposal.setdefault("session_label", None)
        proposal.setdefault("current_session_label", None)
    return proposal


def _ensure_hr_profile_cached() -> None:
    from .hr_profile import load_hr_profile, refresh_hr_profile_if_needed
    if load_hr_profile():
        return
    email = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")
    if not email or not password:
        return
    try:
        api = get_api(email, password)
        refresh_hr_profile_if_needed(api, force=True)
    except Exception as e:
        logger.debug("HR profile lazy fetch failed: %s", e)


def _call_coach(messages: list[dict], api_key: str) -> tuple[str, list[dict]]:
    _ensure_hr_profile_cached()
    context = _build_coach_context()
    system = _coach_system() + f"\n\n## Current Context\n{context}"

    client = _anthropic.Anthropic(api_key=api_key)
    all_tools = [_COACH_TOOL, *_READ_TOOLS]

    convo = list(messages)
    text_parts: list[str] = []
    proposals: list[dict] = []

    for _ in range(_COACH_MAX_TOOL_TURNS):
        response = client.messages.create(
            model=MODEL_SMART,
            max_tokens=1000,
            system=system,
            tools=all_tools,
            messages=convo,
        )
        tool_results: list[dict] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                if block.name == "propose_plan_change":
                    proposals.append(_enrich_plan_proposal(dict(block.input)))
                    content = "Proposal ready for athlete confirmation."
                elif block.name in _READ_TOOL_NAMES:
                    content = _dispatch_read_tool(block.name, dict(block.input))
                else:
                    content = f"Unknown tool: {block.name}"
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})

        if response.stop_reason != "tool_use":
            break
        convo = convo + [
            {"role": "assistant", "content": response.content},
            {"role": "user", "content": tool_results},
        ]

    return "\n\n".join(filter(None, text_parts)), proposals


class _CoachChatRequest(BaseModel):
    message: str


@app.post("/coach-chat")
async def coach_chat(body: _CoachChatRequest):
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return JSONResponse({"reply": "No API key configured.", "proposal": None, "proposals": []})

    user_message = body.message.strip()
    if not user_message:
        return JSONResponse({"reply": "", "proposal": None, "proposals": []})

    history = load_coach_history(limit=20)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_message})

    reply, proposals = _call_coach(messages, api_key)

    save_coach_message("user", user_message)
    save_coach_message("assistant", reply, json.dumps(proposals) if proposals else None)

    return JSONResponse({"reply": reply, "proposal": proposals[0] if proposals else None, "proposals": proposals})


_MEMO_MIN_MESSAGES = 3
_MEMO_STALE_HOURS = 4


def _should_update_memo() -> bool:
    from datetime import datetime as _dt
    memo = get_coach_memory()
    if memo is None:
        return len(load_coach_history(limit=_MEMO_MIN_MESSAGES)) >= _MEMO_MIN_MESSAGES
    try:
        age_h = (_dt.utcnow() - _dt.fromisoformat(memo["updated_at"])).total_seconds() / 3600
        return age_h >= _MEMO_STALE_HOURS
    except Exception:
        return False


def _regenerate_coach_memory(api_key: str) -> None:
    history = load_coach_history(limit=40)
    if len(history) < _MEMO_MIN_MESSAGES:
        return
    current = get_coach_memory()
    current_memo = current["memo"] if current else ""
    context = _build_coach_context()
    recent = history[-20:]
    conv_text = "\n\n".join(
        f"{'Coach' if m['role'] == 'assistant' else 'Athlete'}: {m['content'][:300]}"
        for m in recent
    )
    prompt = (
        "Update the coaching memo with DURABLE cross-session information — goals, tendencies, past decisions, "
        "long-term patterns. Omit anything visible in live session data (current CTL/ATL, today's readiness, "
        "upcoming sessions) since the coach already receives that every turn.\n\n"
        f"Current memo:\n{current_memo if current_memo else '(none)'}\n\n"
        f"Recent conversations:\n{conv_text}\n\n"
        f"Live context summary (for reference only — don't repeat this):\n{context[:600]}\n\n"
        "Write a replacement memo (150–250 words) covering:\n"
        "- Goals and timeline (Ghent to Amsterdam charity ride 13–14 Sep 2026, Haute Route Alpes 2027)\n"
        "- Tendencies (e.g. pushes through fatigue, HRV baseline, training response)\n"
        "- Plan decisions made via coach chat\n"
        "- Long-term patterns worth watching\n"
        "Third person (athlete/they). Specific, not generic. Replace the previous memo entirely."
    )
    try:
        client = _anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=MODEL_FAST,
            max_tokens=400,
            system="You are maintaining a compact coaching notes file. Be specific and concise.",
            messages=[{"role": "user", "content": prompt}],
        )
        set_coach_memory(resp.content[0].text)
    except Exception:
        pass


def _maybe_update_memo_bg(api_key: str) -> None:
    if _should_update_memo():
        threading.Thread(
            target=_regenerate_coach_memory,
            args=(api_key,),
            daemon=True,
        ).start()


def _stream_coach_sse(messages: list[dict], user_message: str, api_key: str):
    """Sync generator yielding SSE events for the coach chat stream."""
    # Save user message immediately so it survives connection drops or server restarts.
    save_coach_message("user", user_message)

    _ensure_hr_profile_cached()
    context = _build_coach_context()
    system = _coach_system() + f"\n\n## Current Context\n{context}"
    client = _anthropic.Anthropic(api_key=api_key)
    all_tools = [_COACH_TOOL, *_READ_TOOLS]

    full_text: list[str] = []
    proposals: list[dict] = []
    convo = list(messages)

    try:
        for _ in range(_COACH_MAX_TOOL_TURNS):
            with client.messages.stream(
                model=MODEL_SMART,
                max_tokens=1000,
                system=system,
                tools=all_tools,
                messages=convo,
            ) as stream:
                for chunk in stream.text_stream:
                    full_text.append(chunk)
                    yield f"data: {json.dumps({'type': 'text', 'chunk': chunk})}\n\n"
                final = stream.get_final_message()

            if final.stop_reason != "tool_use":
                break

            tool_results: list[dict] = []
            for block in final.content:
                if block.type != "tool_use":
                    continue
                if block.name == "propose_plan_change":
                    enriched = _enrich_plan_proposal(dict(block.input))
                    proposals.append(enriched)
                    yield f"data: {json.dumps({'type': 'proposal', 'data': enriched})}\n\n"
                    content = "Proposal ready for athlete confirmation."
                elif block.name in _READ_TOOL_NAMES:
                    yield f"data: {json.dumps({'type': 'tool', 'name': block.name})}\n\n"
                    content = _dispatch_read_tool(block.name, dict(block.input))
                else:
                    content = f"Unknown tool: {block.name}"
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})

            convo = convo + [
                {"role": "assistant", "content": final.content},
                {"role": "user", "content": tool_results},
            ]

        full_reply = "".join(full_text)
        save_coach_message("assistant", full_reply, json.dumps(proposals) if proposals else None)
        _maybe_update_memo_bg(api_key)

    except Exception:
        # Don't leak raw exception text (may contain key/account details)
        logger.exception("coach-chat-stream failed")
        yield f"data: {json.dumps({'type': 'error', 'message': 'Coach is temporarily unavailable — check the server logs.'})}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@app.post("/coach-chat-stream")
async def coach_chat_stream(body: _CoachChatRequest):
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return JSONResponse({"error": "No API key configured."})

    user_message = body.message.strip()
    if not user_message:
        return JSONResponse({"error": "Empty message."})

    history = load_coach_history(limit=20)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_message})

    return StreamingResponse(
        _stream_coach_sse(messages, user_message, api_key),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/coach")
async def coach_tab_view(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="coach_tab.html", context={"active_tab": "coach"})


@app.get("/coach-history")
async def get_coach_history():
    return JSONResponse(load_coach_history(limit=30))


@app.delete("/coach-history")
async def delete_coach_history_endpoint():
    clear_coach_history()
    return JSONResponse({"ok": True})


_VALID_SESSION_TYPES = {"bike", "ftp", "long", "rest", "ruck", "strength", "tempo",
                        # Haute Route plan vocabulary (hr_plan.py)
                        "endurance", "recovery", "vo2", "sweetspot", "gym", "back_to_back"}


class _ApplyChangeRequest(BaseModel):
    date: str
    duration_min: int = Field(..., gt=0, le=600)
    reason: str = Field("", max_length=500)
    session_type: Optional[str] = None  # if provided, overrides the plan session type
    label: Optional[str] = Field(None, max_length=100)  # overrides the plan session label


@app.post("/apply-plan-change")
async def apply_plan_change(body: _ApplyChangeRequest):
    try:
        d = date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format")
    if body.session_type is not None and body.session_type not in _VALID_SESSION_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown session_type '{body.session_type}'")

    from .hr_plan import hr_session_for_date
    from .plan import session_for_date_extended
    sess = session_for_date_extended(d) or hr_session_for_date(d)
    if not sess:
        raise HTTPException(status_code=404, detail="No plan session on that date")

    stype = body.session_type or sess[0]
    label = body.label or sess[1]
    set_plan_override(body.date, stype, label, body.duration_min, body.reason)

    # Surgically reflect this single date on the Garmin calendar: unschedule the
    # old plan workout(s) for that day and schedule the new one. The local override
    # above is the source of truth and is saved regardless; the Garmin push is
    # best-effort, so a failure never fails the request (the next full /sync-workouts
    # will reconcile it).
    garmin: dict = {"pushed": False}
    email_addr = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")
    if email_addr and password:
        from fastapi.concurrency import run_in_threadpool
        try:
            from .workouts import apply_override_to_garmin
            api = get_api(email_addr, password)
            push = await run_in_threadpool(apply_override_to_garmin, api, body.date)
            garmin = {"pushed": push.get("ok", False), "unscheduled": push.get("unscheduled", 0),
                      "scheduled": push.get("scheduled", 0), "error": push.get("error")}
        except Exception as e:
            logger.error("apply-plan-change Garmin push failed: %s", e)
            garmin = {"pushed": False, "error": str(e)}

    return JSONResponse({"ok": True, "date": body.date, "label": label,
                         "duration_min": body.duration_min, "garmin": garmin})


@app.post("/regenerate-advice")
def regenerate_advice_endpoint():
    today = _today()
    delete_advice(today)
    ctx = _build_context(today, force_fetch=True)
    return JSONResponse({"advice": ctx["advice"]})


@app.post("/regenerate-body-advice")
def regenerate_body_advice_endpoint():
    set_cached_text(f"body_analysis_v1_{_today().isoformat()}", "")
    ctx = _body_context()
    return JSONResponse({"analysis": ctx["body_analysis"]})


@app.get("/memory", response_class=HTMLResponse)
async def coach_memory_tab(request: Request):
    memo = get_coach_memory()
    return TEMPLATES.TemplateResponse(request=request, name="memory.html", context={
        "active_tab": "memory",
        "memo": memo["memo"] if memo else "",
        "updated_at": memo.get("updated_at") if memo else None,
    })


@app.get("/coach-memory")
async def coach_memory_get():
    memo = get_coach_memory()
    return JSONResponse({"memo": memo["memo"] if memo else "", "updated_at": memo.get("updated_at") if memo else None})


@app.post("/coach-memory/update")
async def coach_memory_update():
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return JSONResponse({"error": "No API key"}, status_code=503)
    _regenerate_coach_memory(api_key)
    memo = get_coach_memory()
    return JSONResponse({"memo": memo["memo"] if memo else ""})


def run(host: str = "0.0.0.0", port: int = 8743) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="warning")

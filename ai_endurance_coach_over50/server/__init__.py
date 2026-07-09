"""FastAPI dashboard server.

Facade package: the app, every route, and run() live here; helpers are in
shared/context/projection/coach, whose names are re-exported for callers
and tests that import them from ai_endurance_coach_over50.server."""
from __future__ import annotations

import json
import os

from datetime import date, timedelta
from fastapi import Depends, FastAPI, HTTPException
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional

from ..analysis import (
    default_fuelling_plan,
    enrich_activities_power,
    generate_recovery_suggestion,
    load_analyses_for_activities,
    prefetch_fuelling_plans,
    prefetch_workout_descriptions,
    refresh_analyses,
    refresh_power_backfill,
    sync_power_data,
)
from ..body import fetch_blood_pressure, fetch_body_composition
from ..client import get_api
from ..coach_context import build_coach_context as _build_coach_context
from ..display import enrich_activity
from ..history import (
    ACTIVITY_MATCH,
    acclimation_latest,
    baseline_stats,
    clear_coach_history,
    composite_score,
    delete_advice,
    estimated_wkg_history,
    get_coach_memory,
    history_for_chart,
    intensity_distribution_by_week,
    intensity_distribution_by_week_power,
    latest_estimated_wkg,
    latest_weight_kg,
    load,
    load_activities_by_date,
    load_body_metrics,
    load_btb_summary,
    load_coach_history,
    load_durability,
    load_ftp_tests,
    load_fuelling_logs,
    load_power_durability,
    load_recent_activities,
    load_session_rpe,
    load_wkg_goal,
    measured_wkg_history,
    save_wkg_goal,
    pmc_history,
    power_activation_status,
    power_meter_active,
    power_pmc_history,
    raw_history,
    save,
    save_activities,
    save_blood_pressure,
    save_body_metrics,
    save_btb_note,
    save_coach_message,
    save_fuelling_log,
    save_session_rpe,
    set_cached_text,
    set_plan_override,
    sleep_history,
    tdee_history,
    vo2_history,
    weekly_monotony_strain,
    weekly_tss,
    zone_distribution,
)
from ..hr_plan import (
    HR_EVENT_END,
    HR_EVENT_START,
    HR_HEAT_PROTOCOL,
    HR_PHASES,
    HR_PLAN_START,
    LESSONS_2012,
    build_hr_calendar_weeks,
    build_hr_event_weeks,
)
from ..metrics import DailyMetrics, fetch_activities, fetch_metrics
from ..plan import (
    CAMP_GRID_WORKOUTS,
    EVENT_PREP_DAYS,
    PLAN_START as _PLAN_START,
    session_for_date,
    session_for_date_extended,
)
from ..report import generate_pmc_analysis, generate_pmc_explainer, generate_sleep_analysis
from ..energy import weight_trend_kg_per_day
from ..wkg_projection import (
    REALISTIC_BAND_WKG,
    _ftp_anchor,
    build_wkg_path,
    performance_guard,
)

from .shared import (  # noqa: F401
    QUALITY_BIKE_LABELS,
    TEMPLATES,
    _BADGE_STYLES,
    _BIKE_TYPE_KEYS,
    _DEFAULT_BADGE,
    _HARD_LABELS,
    _HARD_SESSION_TYPES,
    _UNSCORED,
    _advice_cache,
    _ai_cache_lock,
    _badge_cls,
    _fmt_dur,
    _fmt_min,
    _pmc_cache,
    _require_auth,
    _security,
    _today,
    _value_colour,
    date_fromisoformat_safe,
    logger,
)
from .context import (  # noqa: F401
    _OVERRIDE_ICONS,
    _PRE_PLAN_WEEKS,
    _TYPE_KEY_SESSION,
    _activity_context_blurb,
    _apply_overrides,
    _body_context,
    _build_calendar_ctx,
    build_event_tracker,
    build_nutrition_today,
    build_trends_context,
    _build_context,
    _build_preplan_weeks,
    _calendar_weeks,
    _merge_compound_activities,
    _plan_completion_stats,
    _shopping_list_context,
    _travel_checklist_context,
    _week_completion,
    _week_summary,
)
from .projection import (  # noqa: F401
    _BIKE_TYPES,
    _CTL_PER_MIN,
    _CTL_REST_DECLINE,
    _EVENT_PREP_BY_DATE,
    _HR_CTL_PER_MIN,
    _PLAN_EVENT_DATE,
    _TENERIFE_BY_DATE,
    _block_zone_totals,
    _build_lookup_dicts,
    _ctl_projection,
    _hr_ctl_projection,
    _ols,
    _session_for_projection,
    _taper_scenarios,
)
from .coach import (  # noqa: F401
    _ApplyChangeRequest,
    _COACH_MAX_TOOL_TURNS,
    _COACH_TOOL,
    _CoachChatRequest,
    _MEMO_MIN_MESSAGES,
    _MEMO_STALE_HOURS,
    _READ_TOOLS,
    _READ_TOOL_NAMES,
    _VALID_SESSION_TYPES,
    _base_plan_session,
    _call_coach,
    _coach_system,
    _dispatch_read_tool,
    _enrich_plan_proposal,
    _ensure_hr_profile_cached,
    _maybe_update_memo_bg,
    _regenerate_coach_memory,
    _should_update_memo,
    _stream_coach_sse,
)


app = FastAPI(
    title="AI Endurance Coach (50+)",
    docs_url=None,
    redoc_url=None,
    dependencies=[Depends(_require_auth)],
)


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
        from ..report import run_report
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
    from ..workouts import upload_and_schedule

    email_addr = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")
    if not (email_addr and password):
        return RedirectResponse(url="/?msg=no_garmin", status_code=303)

    try:
        api = get_api(email_addr, password)
        summary = await run_in_threadpool(upload_and_schedule, api)
        n = summary.get("scheduled", 0)
        from ..history import set_cached_text
        set_cached_text("workouts_stale_ftp", "")
        return RedirectResponse(url=f"/?msg=synced&n={n}", status_code=303)
    except Exception as e:
        logger.error("sync-workouts failed: %s", e)
        return RedirectResponse(url="/?msg=sync_error", status_code=303)


@app.get("/analysis", response_class=HTMLResponse)
def analysis_view(request: Request):
    email_addr = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")
    if email_addr and password:
        try:
            api = get_api(email_addr, password)
            sync_power_data(api, days=14)
        except Exception:
            pass
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
        from ..analysis import fuelling_session_key
        from ..plan import session_for_date_extended
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
        from ..history import _weight_kg_on_date, load_body_metrics
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

    gut_training = None
    try:
        from ..history import gut_training_summary
        gut_training = gut_training_summary(date.today())
    except Exception:
        pass

    return TEMPLATES.TemplateResponse(
        request=request,
        name="analysis.html",
        context={
            "activities": activities,
            "zone_dist": zone_distribution(days=7),
            "rpe_by_activity": rpe_by_activity,
            "gut_training": gut_training,
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


class _WkgGoalRequest(BaseModel):
    target_wkg: float = Field(..., ge=2.0, le=6.0)
    target_date: str  # ISO YYYY-MM-DD, validated in the handler


@app.post("/wkg-goal")
async def wkg_goal_endpoint(body: _WkgGoalRequest, _=Depends(_require_auth)):
    try:
        td = date.fromisoformat(body.target_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="target_date must be YYYY-MM-DD")
    if td <= date.today():
        raise HTTPException(status_code=422, detail="target_date must be in the future")
    save_wkg_goal(body.target_wkg, body.target_date)
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
                from ..metrics import fetch_activities
                acts_raw = fetch_activities(api, days=14)
                save_activities(acts_raw)
                enrich_activities_power(api, acts_raw)
            except Exception:
                pass
        try:
            sync_power_data(api, days=14)
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
    # Prefer the most recent entry with real CTL/ATL: today's Garmin data often
    # hasn't synced yet (early morning), leaving history[-1] null which would
    # otherwise blank out the CTL/ATL/TSB tiles and drop the projection.
    today_entry = next(
        (e for e in reversed(history)
         if e.get("ctl") is not None and e.get("atl") is not None),
        history[-1] if history else {},
    )
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

    # Path to target W/kg (goal projection + race-weight discovery guard)
    wkg_goal = None
    try:
        goal = load_wkg_goal()

        estimated_anchor = False
        anchor = _ftp_anchor(load_ftp_tests())
        if anchor is None:
            est = latest_estimated_wkg()
            if est and est.get("est_ftp_w"):
                anchor = (est["date"], int(est["est_ftp_w"]))
                estimated_anchor = True

        w0 = latest_weight_kg()
        if anchor is not None and w0 is not None:
            readings = [
                (r["date"], r["weight_kg"])
                for r in load_body_metrics(90)
                if r.get("weight_kg")
            ]
            weight_slope = weight_trend_kg_per_day(readings)

            path = build_wkg_path(
                anchor_date_iso=anchor[0],
                anchor_ftp_w=anchor[1],
                latest_weight_kg=w0,
                weight_slope_kg_per_day=weight_slope,
                target_wkg=goal["target_wkg"],
                target_date_iso=goal["target_date"],
            )
            if path is not None:
                comp_z_series = [c for (_d, c) in history_for_chart(14)]
                guard = performance_guard(load_ftp_tests(), weight_slope, comp_z_series)
                wkg_goal = {
                    "target_wkg": goal["target_wkg"],
                    "target_date": goal["target_date"],
                    "path": path,
                    "band_lo": REALISTIC_BAND_WKG[0],
                    "band_hi": REALISTIC_BAND_WKG[1],
                    "guard": guard,
                    "estimated_anchor": estimated_anchor,
                    "anchor_date": anchor[0],
                    "anchor_ftp_w": anchor[1],
                }
    except Exception:
        logger.exception("wkg_goal projection failed")
        wkg_goal = None

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

    power_tss_weekly = weekly_tss(12) if power_meter_active() else []
    power_pmc = power_pmc_history(90) if power_meter_active() else []

    today = date.today()
    m_today = load(today) or DailyMetrics(date=today)
    trends = build_trends_context(today, m_today)

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
            "wkg_goal": wkg_goal,
            "power_meter_active": power_meter_active(),
            "power_activation": power_activation_status(),
            "monotony_weeks": monotony_weeks,
            "acclimation": acclimation,
            "taper_scenarios": taper_scenarios,
            "power_tss_weekly": power_tss_weekly,
            "power_pmc": power_pmc,
            **trends,
        },
    )


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
        from ..analysis import generate_charity_day_plans
        from ..plan import CHARITY_DAYS
        plans = generate_charity_day_plans()
        for cd in CHARITY_DAYS:
            plan = plans.get(cd["day"])
            if plan:
                charity_plans.append({**cd, "plan": plan})
    except Exception:
        pass
    ctx["charity_plans"] = charity_plans

    ctx["plan_section"] = "calendar"
    ctx["week_summary"] = _week_summary()
    ctx["event_tracker"] = build_event_tracker(date.today())

    return TEMPLATES.TemplateResponse(request=request, name="calendar.html", context=ctx)


@app.get("/training", response_class=HTMLResponse)
async def training_plan(request: Request):
    ctx = _plan_completion_stats()
    ctx["plan_section"] = "programme"
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
    ctx["plan_section"] = "compliance"

    return TEMPLATES.TemplateResponse(request=request, name="compliance.html", context=ctx)


@app.get("/nutrition", response_class=HTMLResponse)
async def nutrition_plan(request: Request):
    today = _today()
    from ..nutrition_plan import (
        SUPPLEMENTS, _SUPPLEMENT_DISCLAIMER, protein_target_g,
        SIMPLE_RULES, today_checklist, cycle_week_index,
        fuel_prep_for_ride, _sunday_planned_ride_min,
    )

    recent = raw_history(3)
    today_nut = next((r for r in reversed(recent) if r.get("calories_consumed") is not None), None)
    _tdee_today = None
    try:
        _rows = tdee_history(1)
        if _rows:
            _tdee_today = _rows[-1].get("tdee")
    except Exception:
        pass
    cycle_week = cycle_week_index(_PLAN_START, today)
    checklist = today_checklist(_PLAN_START, today)
    sunday_ride_min = _sunday_planned_ride_min(_PLAN_START, today)
    sunday_fuel = fuel_prep_for_ride(sunday_ride_min) if sunday_ride_min else None

    m = load(today) or DailyMetrics(date=today)
    nutrition_today = build_nutrition_today(m, today)

    return TEMPLATES.TemplateResponse(
        request=request,
        name="nutrition.html",
        context={
            "today": today.isoformat(),
            "cycle_week": cycle_week,
            "simple_rules": SIMPLE_RULES,
            "checklist": checklist,
            "sunday_fuel": sunday_fuel,
            "sunday_ride_min": sunday_ride_min,
            "nutrition_today": nutrition_today,
            "cal_today":     int(today_nut["calories_consumed"])    if today_nut and today_nut.get("calories_consumed")    else None,
            "tdee_today":    int(round(_tdee_today)) if _tdee_today else None,
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
    from ..nutrition_plan import build_meal_week, cycle_week_index
    cycle_week = cycle_week_index(_PLAN_START, today)
    weeks = [build_meal_week(i) for i in range(4)]
    return TEMPLATES.TemplateResponse(
        request=request,
        name="meals.html",
        context={"cycle_week": cycle_week, "weeks": weeks},
    )


@app.get("/nutrition/fuelling", response_class=HTMLResponse)
async def nutrition_fuelling(request: Request):
    today = _today()
    from ..nutrition_plan import fuel_prep_for_ride, _sunday_planned_ride_min
    sunday_ride_min = _sunday_planned_ride_min(_PLAN_START, today)
    sunday_fuel = fuel_prep_for_ride(sunday_ride_min) if sunday_ride_min else None
    fuel_tiers = [fuel_prep_for_ride(m) for m in (90, 120, 180, 240, 300, 360)]
    return TEMPLATES.TemplateResponse(
        request=request,
        name="fuelling.html",
        context={
            "sunday_fuel": sunday_fuel,
            "sunday_ride_min": sunday_ride_min,
            "fuel_tiers": fuel_tiers,
        },
    )


@app.get("/nutrition/recipes", response_class=HTMLResponse)
async def nutrition_recipes(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="recipes.html", context={})


@app.get("/nutrition/recipes/weekend-fuel", response_class=HTMLResponse)
async def nutrition_recipes_weekend_fuel(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="recipes-weekend-fuel.html", context={})


@app.get("/nutrition/recipes/overnight-oats", response_class=HTMLResponse)
async def nutrition_recipes_overnight_oats(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="recipes-overnight-oats.html", context={})


@app.get("/nutrition/recipes/griddle", response_class=HTMLResponse)
async def nutrition_recipes_griddle(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="recipes-griddle.html", context={})


@app.get("/nutrition/recipes/travel", response_class=HTMLResponse)
async def nutrition_recipes_travel(request: Request):
    ctx = _travel_checklist_context()
    return TEMPLATES.TemplateResponse(request=request, name="recipes-travel.html", context=ctx)


@app.get("/nutrition/shopping-list", response_class=HTMLResponse)
async def nutrition_shopping_list(request: Request):
    ctx = _shopping_list_context()
    return TEMPLATES.TemplateResponse(request=request, name="asda-shopping-list.html", context=ctx)


@app.get("/nutrition/lidl-shopping-list", response_class=HTMLResponse)
async def nutrition_lidl_shopping_list(request: Request):
    ctx = _shopping_list_context()
    return TEMPLATES.TemplateResponse(request=request, name="lidl-shopping-list.html", context=ctx)


_ARCHITECTURE_HTML = Path(__file__).resolve().parent.parent / "architecture.html"


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
        from ..analysis import generate_hr_stage_plans, peak_sim_decoupling_flags
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
        "power_familiarization_note": (
            "Power familiarization bridge (14 Sep – 4 Oct 2026): "
            "bed in the pedals and learn to pace by watts before the formal Haute Route base block. "
            "Not part of projected CTL — display only."
        ),
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
    from ..power_profile import build_power_profile
    return TEMPLATES.TemplateResponse(
        request=request,
        name="hr_power_protocol.html",
        context={
            "active_tab": "haute_route",
            "hr_subnav": "power",
            "power_profile": build_power_profile(),
        },
    )


@app.get("/body", response_class=HTMLResponse)
async def body_view(request: Request, msg: Optional[str] = None):
    ctx = _body_context()
    ctx["flash_msg"] = msg
    ctx["recovery_section"] = "body"
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
            from ..withings import sync_withings_to_garmin
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
        "recovery_section": "sleep",
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


@app.post("/apply-plan-change")
async def apply_plan_change(body: _ApplyChangeRequest):
    try:
        d = date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format")
    if body.session_type is not None and body.session_type not in _VALID_SESSION_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown session_type '{body.session_type}'")

    from ..hr_plan import hr_session_for_date
    from ..plan import session_for_date_extended
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
            from ..workouts import apply_override_to_garmin
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
def regenerate_advice_endpoint(mode: str = "post"):
    today = _today()
    if mode not in ("pre", "post"):
        mode = "post"
    delete_advice(today, mode=mode)
    ctx = _build_context(today, force_fetch=True)
    key = "advice_pre" if mode == "pre" else "advice_post"
    return JSONResponse({"advice": ctx.get(key), "mode": mode})


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

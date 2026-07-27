"""Page context builders for dashboard, calendar, body, nutrition and summaries."""
from __future__ import annotations

import os

from datetime import date, timedelta
from fastapi import status
from typing import Any, Optional

from ..alerts import check_fatigue_alerts
from ..analysis import enrich_activities_power
from ..body import bp_classification
from ..client import get_api
from ..coach_context import build_advice_timing
from ..display import FIELD_LABELS, enrich_activity, fmt_value, readiness_label
from ..history import (
    ACTIVITY_MATCH,
    baseline_stats,
    composite_score,
    delete_advice,
    field_baseline,
    ftp_retest_due,
    get_cached_text,
    gut_training_summary,
    history_for_chart,
    latest_estimated_wkg,
    latest_measured_wkg,
    list_plan_overrides,
    load,
    load_activities_by_date,
    load_blood_pressure,
    load_body_metrics,
    load_ftp_tests,
    load_morning_snapshot,
    load_recent_activities,
    metrics_from_snapshot,
    metrics_row_for_date,
    morning_snapshot_premature,
    pmc_history,
    power_meter_active,
    raw_history,
    save,
    save_activities,
    seven_day_composite_trend_csv,
    stable_tdee_kcal,
    tdee_calibration,
    tdee_history,
    z_score,
)
from ..metrics import DailyMetrics, fetch_activities, fetch_metrics, local_today, morning_metrics_ready, needs_metrics_refetch
from ..nutrition_plan import (
    cycle_week_index,
    protein_target_g,
    today_targets as nutrition_today_targets,
)
from ..plan import (
    COMPOUND_SESSIONS,
    PLAN_START as _PLAN_START,
    build_bridge_weeks,
    build_calendar_weeks,
    build_camp_weeks,
    build_combined_event_weeks,
    session_for_date,
    session_for_date_extended,
)
from ..hr_plan import hr_session_for_date
from ..power_profile import build_power_profile
from ..report import generate_advice, generate_body_analysis, generate_dashboard_explainer

from .shared import (
    QUALITY_BIKE_LABELS,
    _BIKE_TYPE_KEYS,
    _HARD_LABELS,
    _HARD_SESSION_TYPES,
    _UNSCORED,
    _advice_cache,
    _ai_cache_lock,
    _badge_cls,
    _fmt_dur,
    _fmt_min,
    _today,
    _value_colour,
)


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
    from ..hr_plan import build_hr_calendar_weeks
    hr_weeks = build_hr_calendar_weeks()
    return {
        "weeks": _calendar_weeks(),
        "today": date.today(),
        "plan_start": _PLAN_START,
        "camp_weeks": build_camp_weeks(),
        "combined_event_weeks": build_combined_event_weeks(),
        "bridge_weeks": build_bridge_weeks(),
        # Continuity teaser — first 4 Haute Route Base weeks (full hub stays at /haute-route)
        "hr_teaser_weeks": hr_weeks[:4],
    }


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


_VERDICT_ICONS = {
    "bike": "🚴", "tempo": "🚴", "ftp": "🚴", "long": "🚴",
    "strength": "🏋️", "ruck": "🎒", "recovery": "🧘", "rest": "😴",
}


def _build_today_verdict(
    target: date,
    today_plan: Optional[dict],
    traffic_light: Optional[dict],
    modulation: Optional[dict],
    post_workout: bool,
    swap_suggestion: Optional[dict] = None,
) -> dict:
    """Collapse gates + modulation + plan into one athlete-facing answer.

    Presentation only — the gate hierarchy is already resolved by
    ``modulation.resolve_modulation``; this just decides what single card the
    dashboard shows and wires the Apply proposal for the existing
    ``/apply-plan-change`` flow.
    """
    status = (traffic_light or {}).get("status") or "unknown"
    if modulation and modulation.get("gate_type") == "illness":
        status = "red"
    elif modulation and modulation.get("gate"):
        status = "amber" if status in ("green", "unknown") else status

    has_swap = bool(modulation and modulation.get("label"))
    changed = has_swap and not post_workout

    if changed:
        final_session = {
            "type": modulation["session_type"],
            "label": modulation["label"],
            "dur_fmt": _fmt_min(modulation.get("duration_min") or 0),
            "icon": _VERDICT_ICONS.get(modulation["session_type"], "📋"),
            "compound": None,
            "note": (today_plan or {}).get("note"),
            "changed": True,
            "from_label": modulation.get("planned_label") or (today_plan or {}).get("label"),
        }
    elif today_plan:
        final_session = {**today_plan, "changed": False, "from_label": None}
    else:
        final_session = {
            "type": "rest", "label": "Rest day", "dur_fmt": "",
            "icon": _VERDICT_ICONS["rest"], "compound": None, "note": None,
            "changed": False, "from_label": None,
        }

    # One-line reason for the status strip.
    if modulation and modulation.get("headline"):
        reason = modulation["headline"]
        if modulation.get("reason"):
            reason += " — " + modulation["reason"]
    elif traffic_light and traffic_light.get("reason") and status != "green":
        reason = traffic_light["reason"]
    elif status == "green":
        reason = "HRV and readiness in normal range — session as planned"
    else:
        reason = "No morning readiness signal yet"

    # Apply proposal (existing plan_change_card / /apply-plan-change flow).
    apply = None
    if changed:
        apply = {
            "date": modulation.get("date") or target.isoformat(),
            "duration_min": modulation.get("duration_min") or 0,
            "session_type": modulation["session_type"],
            "label": modulation["label"],
            "reason": ("Recovery gate: " if modulation.get("gate") else "HRV traffic light: ")
                      + (modulation.get("reason") or reason),
            "from_label": modulation.get("planned_label") or "",
        }

    # Tertiary hint only when no modulation fired (old swap_suggestion card).
    hint = None
    if not has_swap and swap_suggestion:
        if swap_suggestion.get("to_date_str"):
            hint = (
                f"Readiness is low — consider swapping with "
                f"{swap_suggestion['to_label']} on {swap_suggestion['to_date_str']}."
            )
        else:
            hint = "Readiness is low — consider reducing intensity or cutting this session short."

    # One-line nutrition prescription from the single resolver.
    nutrition = None
    try:
        tt = nutrition_today_targets(target)
        nutrition = {
            "kcal": tt["kcal"],
            "protein_low": tt["protein_low"],
            "protein_high": tt["protein_high"],
            "carbs_g_per_hr": tt["carbs_g_per_hr"],
            "maintenance": tt["maintenance"],
        }
    except Exception:
        pass

    return {
        "status": status,
        "final_session": final_session,
        "reason": reason,
        "apply": apply,
        "hint": hint,
        "nutrition": nutrition,
    }


def _build_context(target: date, force_fetch: bool = False) -> dict[str, Any]:
    api = None
    email = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")
    has_garmin = bool(email and password)

    # Load or fetch
    if force_fetch:
        if has_garmin:
            api = get_api(email, password)
            m = fetch_metrics(api, target)
            save(m)
            from ..hr_profile import refresh_hr_profile_if_needed
            refresh_hr_profile_if_needed(api, force=True)
        else:
            m = load(target) or DailyMetrics(date=target)
    else:
        m = load(target) or DailyMetrics(date=target)
        if needs_metrics_refetch(m) or (
            target == local_today() and not morning_metrics_ready(m) and has_garmin
        ):
            if has_garmin:
                api = get_api(email, password)
                m = fetch_metrics(api, target)
                save(m)
                from ..hr_profile import refresh_hr_profile_if_needed
                refresh_hr_profile_if_needed(api, force=False)

    morning_snapshot = load_morning_snapshot(target)
    if morning_snapshot and morning_snapshot_premature(morning_snapshot) and morning_metrics_ready(m):
        delete_advice(target, mode="pre")
        morning_snapshot = None

    if force_fetch:
        delete_advice(target, mode="pre")

    stats = baseline_stats(target)
    # Resting HR is intentionally excluded from the composite (SCORED_FIELDS), but
    # we still want a baseline + z-score for its dashboard tile. Inject it here for
    # display only — composite_score() iterates SCORED_FIELDS, so this is a no-op there.
    _rhr_base = field_baseline("resting_hr", target)
    if _rhr_base:
        stats["resting_hr"] = _rhr_base
    comp_z = composite_score(m, stats)
    comp_label, comp_colour = readiness_label(comp_z)
    live_comp_z = comp_z
    live_comp_label, live_comp_colour = comp_label, comp_colour

    if morning_snapshot is None:
        morning_snapshot = load_morning_snapshot(target)
    if morning_snapshot:
        morning_m = metrics_from_snapshot(morning_snapshot, target)
        morning_comp_z = morning_snapshot.get("composite_z")
        morning_comp_label = morning_snapshot.get("readiness_label") or comp_label
        morning_comp_colour = readiness_label(morning_comp_z)[1] if morning_comp_z is not None else comp_colour
        morning_captured_at = morning_snapshot.get("captured_at")
    else:
        morning_m = m
        morning_comp_z = comp_z
        morning_comp_label = comp_label
        morning_comp_colour = comp_colour
        morning_captured_at = None

    # Morning gate uses frozen snapshot metrics when available
    comp_z = morning_comp_z
    comp_label = morning_comp_label
    comp_colour = morning_comp_colour

    # Status badges (morning recovery signals)
    badges: list[tuple[str, str]] = []
    if morning_m.hrv_status:
        text = f"HRV {morning_m.hrv_status.title()}"
        badges.append((text, _badge_cls(morning_m.hrv_status)))
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

    # Chart data, sparklines, and resting-HR history moved to build_trends_context()
    # (Performance tab). Dashboard no longer computes them.

    # Activities — refresh on force_fetch (ride kJ etc. computed on Nutrition tab)
    if force_fetch:
        email_addr = os.getenv("GARMIN_EMAIL", "")
        password = os.getenv("GARMIN_PASSWORD", "")
        if email_addr and password:
            try:
                if api is None:
                    api = get_api(email_addr, password)
                acts_raw = fetch_activities(api, days=7)
                save_activities(acts_raw)
                enrich_activities_power(api, acts_raw)
            except Exception:
                pass

    timing = build_advice_timing(target)
    post_workout = timing["post_workout"]
    date_key = target.isoformat()
    today_activities = [enrich_activity(a) for a in timing.get("matched_activities") or []]

    # HRV traffic light + session modulation (morning gate metrics)
    traffic_light = None
    modulation = None
    try:
        from ..modulation import resolve_modulation
        traffic_light, modulation = resolve_modulation(target, morning_m, morning_comp_z)
    except Exception:
        pass
    if morning_snapshot and morning_snapshot.get("traffic_light_status"):
        traffic_light = {
            "status": morning_snapshot["traffic_light_status"],
            "reason": morning_snapshot.get("traffic_light_reason"),
            "hrv_z": None,
            "ratio": None,
        }

    with _ai_cache_lock:
        if force_fetch:
            _advice_cache.pop(f"{date_key}:pre", None)
            _advice_cache.pop(f"{date_key}:post", None)
        pre_key = f"{date_key}:pre"
        if pre_key not in _advice_cache:
            _advice_cache[pre_key] = generate_advice(
                m, stats, live_comp_z,
                mode="pre",
                traffic_light=traffic_light,
            )
        advice_pre = _advice_cache[pre_key]
        advice_post = None
        if post_workout:
            post_key = f"{date_key}:post"
            if post_key not in _advice_cache:
                _advice_cache[post_key] = generate_advice(
                    m, stats, live_comp_z,
                    mode="post",
                    traffic_light=traffic_light,
                )
            advice_post = _advice_cache[post_key]

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

    # Event tracker, weekly briefing, power profile, gut training — other tabs

    # One-verdict summary: the final answer after all gates resolve.
    today_verdict = _build_today_verdict(
        target, today_plan, traffic_light, modulation, post_workout, swap_suggestion
    )

    # Fatigue alerts
    fatigue_alerts = check_fatigue_alerts(target)

    # FTP retest / power baseline prompt
    ftp_retest = None
    try:
        def _scan_ftp_slot(start: date, days: int = 10) -> Optional[dict]:
            for offset in range(1, days + 1):
                cand = start + timedelta(days=offset)
                for resolver in (session_for_date, hr_session_for_date):
                    csess = resolver(cand)
                    if csess and csess[0] in ("tempo", "ftp", "bike", "sweetspot"):
                        return {
                            "date": cand.isoformat(),
                            "date_str": cand.strftime("%a %-d %b"),
                            "current_label": csess[1],
                        }
            return None

        due = ftp_retest_due(target, plan_start=_PLAN_START)
        has_ftp_w = any(t.get("ftp_w") for t in load_ftp_tests())
        if power_meter_active() and not has_ftp_w:
            ftp_retest = {
                "reason": "power_baseline",
                "last_date": None,
                "age_days": None,
                "message": "Power meter active but FTP watts never measured — schedule a test",
                "slot": _scan_ftp_slot(target),
            }
        elif due:
            ftp_retest = {**due, "reason": "stale", "slot": _scan_ftp_slot(target)}
    except Exception:
        pass

    # FIT threshold-evidence: stale FTP proposal from recent interval analysis
    stale_ftp = None
    try:
        from ..history import latest_stale_ftp_flag
        flag = latest_stale_ftp_flag()
        if flag and flag.get("proposed_ftp_w"):
            stale_ftp = {
                **flag,
                "slot": None,
            }
            # Offer schedule-retest slot like ftp_retest
            def _scan_ftp_slot2(start: date, days: int = 10) -> Optional[dict]:
                for offset in range(1, days + 1):
                    cand = start + timedelta(days=offset)
                    for resolver in (session_for_date, hr_session_for_date):
                        csess = resolver(cand)
                        if csess and csess[0] in ("tempo", "ftp", "bike", "sweetspot"):
                            return {
                                "date": cand.isoformat(),
                                "date_str": cand.strftime("%a %-d %b"),
                                "current_label": csess[1],
                            }
                return None
            stale_ftp["slot"] = _scan_ftp_slot2(target)
    except Exception:
        pass

    # HR calibration discrepancies from recent FIT meta
    hr_calibration = None
    try:
        from ..history import latest_hr_calibration
        hr_calibration = latest_hr_calibration()
    except Exception:
        pass

    # Nutrition pill for Today gate (full tile lives on /nutrition)
    nutrition_pill = None
    if m.calories_consumed is not None:
        nutrition_pill = {"calories": int(m.calories_consumed)}

    post_fatigue = {
        "body_battery": m.body_battery_current if m.body_battery_current is not None else m.body_battery_morning,
        "acwr": m.acwr,
        "training_load_acute": m.training_load_acute,
    }

    return {
        "date": date_key,
        "date_long": target.strftime("%A, %-d %B %Y"),
        "comp_z": comp_z,
        "comp_label": comp_label,
        "comp_colour": comp_colour,
        "live_comp_z": live_comp_z,
        "live_comp_label": live_comp_label,
        "live_comp_colour": live_comp_colour,
        "morning_comp_z": morning_comp_z,
        "morning_comp_label": morning_comp_label,
        "morning_comp_colour": morning_comp_colour,
        "morning_captured_at": morning_captured_at,
        "morning_snapshot": morning_snapshot,
        "post_workout": post_workout,
        "today_activities": today_activities,
        "post_fatigue": post_fatigue,
        "advice_pre": advice_pre,
        "advice_post": advice_post,
        "badges": badges,
        "acwr": m.acwr,
        "metrics": metric_rows,
        "baseline_count": len(stats),
        "nutrition_pill": nutrition_pill,
        "today_plan": today_plan,
        "swap_suggestion": swap_suggestion,
        "today_verdict": today_verdict,
        "fatigue_alerts": fatigue_alerts,
        "traffic_light": traffic_light,
        "modulation": modulation,
        "ftp_retest": ftp_retest,
        "stale_ftp": stale_ftp,
        "hr_calibration": hr_calibration,
    }


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
        from ..display import fmt_duration
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


# Map Garmin type_key → display session type for pre-plan activity cells
_TYPE_KEY_SESSION: dict[str, str] = {
    "road_biking": "bike", "cycling": "bike", "virtual_ride": "bike",
    "indoor_cycling": "bike", "mountain_biking": "bike",
    "strength_training": "strength", "stair_climbing": "strength", "fitness_equipment": "strength",
    "hiking": "ruck", "walking": "ruck", "trail_running": "ruck", "running": "ruck",
}

_PRE_PLAN_WEEKS = 4


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


def _camp_day_dur_min(km: int, elev_m: int) -> int:
    """Tenerife ride duration estimate — matches projection.py."""
    return max(int((km / 25 + elev_m / 700) * 60), 30)


def _charity_day_dur_min(km: int) -> int:
    return max(int(km / 25 * 60), 60)


def _compliance_weeks_unified() -> list[dict]:
    """12-week plan + Tenerife camp grid + event-prep/charity weeks for compliance."""
    unified: list[dict] = []
    for w in _calendar_weeks():
        unified.append({
            "phase": "plan",
            "week_num": w["week_num"],
            "week_label": f"Wk {w['week_num']:02d}",
            "start": w["start"],
            "days": w["days"],
            "phase_start": w["week_num"] == 1,
        })
    for i, w in enumerate(build_camp_weeks()):
        days = []
        for day in w["days"]:
            if day.get("is_camp") and day.get("intensity") in ("easy", "medium", "hard"):
                km = day.get("km", 0) or 0
                elev = day.get("elev_m", 0) or 0
                stype = "long" if day["intensity"] == "hard" else "bike"
                days.append({
                    "date": day["date"],
                    "type": stype,
                    "dur_min": _camp_day_dur_min(km, elev),
                    "sub_sessions": None,
                })
            elif day.get("is_workout"):
                days.append({
                    "date": day["date"],
                    "type": day["type"],
                    "dur_min": day["dur_min"],
                    "sub_sessions": None,
                })
            else:
                days.append({
                    "date": day["date"],
                    "type": "rest",
                    "dur_min": 0,
                    "sub_sessions": None,
                })
        unified.append({
            "phase": "camp",
            "week_num": None,
            "week_label": w["week_label"],
            "start": days[0]["date"],
            "days": days,
            "phase_start": i == 0,
        })
    for i, w in enumerate(build_combined_event_weeks()):
        days = []
        for day in w["days"]:
            if day.get("is_event") and not day.get("is_mersea"):
                km = day.get("km", 0) or 0
                days.append({
                    "date": day["date"],
                    "type": "long",
                    "dur_min": _charity_day_dur_min(km),
                    "sub_sessions": None,
                })
            elif day.get("is_event") and day.get("is_mersea"):
                km = day.get("km", 0) or 0
                days.append({
                    "date": day["date"],
                    "type": "ruck",
                    "dur_min": max(int(km / 5 * 60), 60),
                    "sub_sessions": None,
                })
            elif day.get("type") not in (None, "rest") and day.get("label"):
                days.append({
                    "date": day["date"],
                    "type": day["type"],
                    "dur_min": day.get("dur_min", 0),
                    "sub_sessions": None,
                })
            else:
                days.append({
                    "date": day["date"],
                    "type": "rest",
                    "dur_min": 0,
                    "sub_sessions": None,
                })
        unified.append({
            "phase": "event_prep",
            "week_num": None,
            "week_label": w["week_label"],
            "start": days[0]["date"],
            "days": days,
            "phase_start": i == 0,
        })
    for i, w in enumerate(build_bridge_weeks()):
        days = []
        for day in w["days"]:
            if day.get("out_of_bridge") or day.get("type") in (None, "rest") or not day.get("label"):
                days.append({
                    "date": day["date"],
                    "type": "rest",
                    "dur_min": 0,
                    "sub_sessions": None,
                })
            else:
                days.append({
                    "date": day["date"],
                    "type": day["type"],
                    "dur_min": day.get("dur_min", 0),
                    "sub_sessions": None,
                })
        unified.append({
            "phase": "bridge",
            "week_num": None,
            "week_label": w["week_label"],
            "start": days[0]["date"],
            "days": days,
            "phase_start": i == 0,
        })
    return unified


def _plan_completion_stats() -> dict:
    """Compute per-week plan vs actual completion stats for the training/compliance pages."""
    today = date.today()
    weeks_data = _compliance_weeks_unified()
    block_end = weeks_data[-1]["days"][-1]["date"]
    acts_by_date = load_activities_by_date(_PLAN_START, min(today, block_end))

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
            "phase": week["phase"],
            "phase_start": week["phase_start"],
            "week_num": week["week_num"],
            "week_label": week["week_label"],
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


def _travel_checklist_context() -> dict:
    """Upcoming weekend sessions + fuel counts for the away checklist."""
    today = _today()
    from ..nutrition_plan import cycle_week_index, fuel_prep_for_ride, _sunday_planned_ride_min
    from ..plan import session_for_date_extended

    cycle_week = cycle_week_index(_PLAN_START, today)
    labels = [
        "Week 1 — build",
        "Week 2 — build",
        "Week 3 — build",
        "Week 4 — recovery",
    ]
    week_mode = "recovery" if cycle_week == 3 else "build"

    days_to_sat = (5 - today.weekday()) % 7
    saturday = today if days_to_sat == 0 else today + timedelta(days=days_to_sat)
    sunday = saturday + timedelta(days=1)

    sat_sess = session_for_date_extended(saturday)
    sun_sess = session_for_date_extended(sunday)
    sunday_ride_min = _sunday_planned_ride_min(_PLAN_START, today) or 120

    return {
        "cycle_week": cycle_week,
        "cycle_week_label": labels[cycle_week],
        "week_mode": week_mode,
        "sunday_ride_min": sunday_ride_min,
        "sunday_fuel": fuel_prep_for_ride(sunday_ride_min, ref_date=today),
        "sat_label": sat_sess[1] if sat_sess else "Saturday ruck",
        "sat_dur_min": sat_sess[2] if sat_sess else None,
        "sun_label": sun_sess[1] if sun_sess else "Sunday long ride",
    }


def _shopping_list_context() -> dict:
    """Cycle week for nutrition shopping lists (Fri–Sun → next Monday's week)."""
    today = _today()
    from ..nutrition_plan import prep_cycle_week_index
    cycle_week = prep_cycle_week_index(_PLAN_START, today)
    labels = [
        "Week 1 — build",
        "Week 2 — build",
        "Week 3 — build",
        "Week 4 — recovery",
    ]
    return {
        "cycle_week": cycle_week,
        "cycle_week_label": labels[cycle_week],
        "week_mode": "recovery" if cycle_week == 3 else "build",
    }


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


_EVENT_DATE = date(2026, 9, 13)
_PLAN_BLOCK_DAYS = 84


def build_event_tracker(target: date) -> Optional[dict]:
    """Charity event countdown for Calendar / plan views."""
    _days_into = (target - _PLAN_START).days
    _ws = _week_summary()
    if target < _PLAN_START or (_EVENT_DATE - target).days <= 0:
        return None
    _week_pct = _ws.get("pct") if _ws else None
    if _week_pct is None:
        _on_label, _on_col = "No data yet", "text-zinc-500"
    elif _week_pct >= 80:
        _on_label, _on_col = "On track", "text-emerald-400"
    elif _week_pct >= 50:
        _on_label, _on_col = "Slightly behind", "text-yellow-400"
    else:
        _on_label, _on_col = "Behind", "text-red-400"
    return {
        "week_num": min(12, max(1, _days_into // 7 + 1)),
        "plan_pct": min(100, max(0, int(_days_into / _PLAN_BLOCK_DAYS * 100))),
        "days_to_event": (_EVENT_DATE - target).days,
        "on_track_label": _on_label,
        "on_track_colour": _on_col,
    }


def build_nutrition_today(m: DailyMetrics, target: date) -> Optional[dict]:
    """Full nutrition tile for /nutrition overview."""
    if m.calories_consumed is None:
        return None
    _tdee = None
    try:
        _rows = tdee_history(1)
        if _rows:
            _tdee = _rows[-1].get("tdee")
    except Exception:
        pass
    nutrition_today = {
        "calories": int(m.calories_consumed),
        "tdee": int(round(_tdee)) if _tdee else None,
        "goal": int(m.calorie_goal) if m.calorie_goal else None,
        "carbs": round(m.carbs_consumed) if m.carbs_consumed is not None else None,
        "protein": round(m.protein_consumed) if m.protein_consumed is not None else None,
    }
    if nutrition_today["tdee"] and nutrition_today["calories"]:
        nutrition_today["balance"] = nutrition_today["tdee"] - nutrition_today["calories"]
    try:
        from ..energy import ride_kj, ride_kcal_from_kj
        today_iso = target.isoformat()
        kj_total = 0.0
        for act in load_recent_activities(days=7):
            if act.get("date") != today_iso:
                continue
            pwr = act.get("norm_power_w") or act.get("avg_power_w")
            secs = act.get("duration_seconds") or 0
            if pwr and secs and act.get("has_power_meter"):
                kj_total += ride_kj(float(pwr), float(secs))
        if kj_total > 0:
            nutrition_today["ride_work_kj"] = round(kj_total)
            nutrition_today["ride_work_kcal"] = ride_kcal_from_kj(kj_total)
    except Exception:
        pass
    return nutrition_today


def build_trends_context(target: date, m: Optional[DailyMetrics] = None) -> dict[str, Any]:
    """Charts, trends, and depth content for Performance tab."""
    if m is None:
        m = load(target) or DailyMetrics(date=target)
    stats = baseline_stats(target)
    _rhr_base = field_baseline("resting_hr", target)
    if _rhr_base:
        stats["resting_hr"] = _rhr_base

    history = history_for_chart(days=14)
    chart_labels = [d.strftime("%d %b") for d, _ in history]
    chart_values = [round(v, 3) if v is not None else None for _, v in history]

    spark_rows = raw_history(14)
    sparklines = {
        "hrv": [r["hrv_last_night"] for r in spark_rows],
        "sleep": [r["sleep_score"] for r in spark_rows],
        "stress": [r["avg_stress"] for r in spark_rows],
        "labels": [r["date"].strftime("%-d %b") for r in spark_rows],
    }

    rhr_rows = raw_history(30)
    resting_hr_history = {
        "labels": [r["date"].strftime("%-d %b") for r in rhr_rows],
        "values": [r["resting_hr"] for r in rhr_rows],
        "baseline": round(_rhr_base[0], 1) if _rhr_base else None,
    }

    activities = [enrich_activity(a) for a in load_recent_activities(days=7)]
    comp_z = composite_score(m, stats)

    metric_rows = []
    for field, (label_str, unit) in FIELD_LABELS.items():
        value = getattr(m, field)
        val_str = fmt_value(field, value)
        context_only = field in _UNSCORED
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

    weekly_briefing: Optional[str] = None
    is_monday = target.weekday() == 0
    if is_monday:
        week_sessions = []
        for i in range(7):
            d = target + timedelta(days=i)
            sess = session_for_date(d)
            if sess and sess[0] != "rest":
                week_sessions.append((d.strftime("%a"), sess[0], sess[1], sess[2]))
        _pmc_recent = pmc_history(days=7)
        _pmc_today = next(
            (e for e in reversed(_pmc_recent) if e.get("ctl") is not None),
            _pmc_recent[-1] if _pmc_recent else {},
        )
        try:
            from ..report import generate_weekly_briefing
            weekly_briefing = generate_weekly_briefing(week_sessions, _pmc_today, comp_z)
        except Exception:
            pass

    power_profile = None
    try:
        power_profile = build_power_profile()
    except Exception:
        pass

    power_snapshot = None
    try:
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

    workouts_stale_ftp = None
    try:
        stale = get_cached_text("workouts_stale_ftp")
        if stale:
            workouts_stale_ftp = int(stale)
    except Exception:
        pass

    moderate_alerts = [
        a for a in check_fatigue_alerts(target) if a.get("severity") != "HIGH"
    ]

    return {
        "chart_labels": chart_labels,
        "chart_values": chart_values,
        "sparklines": sparklines,
        "resting_hr_history": resting_hr_history,
        "trend_note": seven_day_composite_trend_csv(),
        "activity_blurb": _activity_context_blurb(activities),
        "activities": activities,
        "metrics": metric_rows,
        "metric_explainer": generate_dashboard_explainer(),
        "weekly_briefing": weekly_briefing,
        "is_monday": is_monday,
        "power_profile": power_profile,
        "power_snapshot": power_snapshot,
        "workouts_stale_ftp": workouts_stale_ftp,
        "moderate_fatigue_alerts": moderate_alerts,
        "acwr": m.acwr,
        "baseline_count": len(stats),
    }


# ---------------------------------------------------------------------------
# /position — strength programme page
#
# The page used to hardcode a Mon/Thu week. Every block schedules strength
# differently (charity Tue+Thu, event prep 1×, bridge Tue+Thu, HR Base Thu+Sat,
# HR Build Wed-only), so the schedule is derived from the same resolvers the
# calendars use. Nothing here adds plan data — it only reads it.
# ---------------------------------------------------------------------------

# Days that are too valuable to bolt mobility onto: the strength days themselves
# carry the trunk block, and key rides want the legs left alone.
_POSITION_KEY_TYPES = {"long", "tempo", "ftp", "sweetspot", "vo2", "back_to_back"}


def _session_contains(spec: Optional[dict]) -> str:
    """Human summary of a KB spec, derived from the exercise id groups.

    Avoids inventing "Strength 1 / 2" names: those only exist in the bridge and
    the HR plan, while charity weeks 9–12 give both days the same week-keyed spec.
    """
    if not spec:
        return ""
    ids = "".join(ex.get("id", "") for ex in spec.get("exercises", []))
    extras = []
    if "L" in ids:
        extras.append("single-leg block")
    if "C" in ids:
        extras.append("carries")
    base = "20-min video" if "V" in ids else "KB circuit"
    return f"{base} + {' + '.join(extras)}" if extras else base


def _strength_on(d: date) -> Optional[dict]:
    """Return {label, dur_min, spec, contains} if `d` carries strength, else None.

    A non-None KB spec *is* the definition of a strength day — there is no
    second list of labels to drift out of step with the calendars.
    """
    from ..plan import kb_spec_for_date
    from ..hr_plan import _hr_strength_spec

    sess = session_for_date_extended(d)
    if sess:
        spec = kb_spec_for_date(d)
        if spec:
            return {"label": sess[1], "dur_min": sess[2], "spec": spec,
                    "contains": _session_contains(spec)}
        return None

    sess = hr_session_for_date(d)
    if sess:
        spec = _hr_strength_spec(sess[1])
        if spec:
            return {"label": sess[1], "dur_min": sess[2], "spec": spec,
                    "contains": _session_contains(spec)}
    return None


def _position_day(d: date, today: date) -> dict[str, Any]:
    """One row of the derived week table."""
    sess = session_for_date_extended(d) or hr_session_for_date(d)
    strength = _strength_on(d)
    stype = sess[0] if sess else "rest"
    return {
        "date": d,
        "iso": d.isoformat(),
        "weekday": d.strftime("%a"),
        "day_str": d.strftime("%-d %b"),
        "type": stype,
        "label": (sess[1] if sess else None),
        "dur_min": (sess[2] if sess else 0),
        "dur_fmt": _fmt_min(sess[2]) if sess and sess[2] else None,
        "is_strength": strength is not None,
        "contains": strength["contains"] if strength else None,
        "is_today": d == today,
        "is_past": d < today,
        "mobility": False,  # filled in by _mark_mobility once the week is known
    }


# Mobility is 3×/week and lives on no plan — it is placed, not scheduled.
_POSITION_MOBILITY_TARGET = 3


def _mobility_rank(day: dict) -> tuple[int, int]:
    """Lower ranks make better mobility slots: rest first, then easy days."""
    stype, dur = day["type"], day["dur_min"]
    if stype == "rest":
        return (0, 0)
    # Camp and charity-ride days carry no duration because they are all-day
    # efforts — they are the worst place to add anything, not the best.
    if stype == "bike" and dur == 0:
        return (3, 0)
    return (2, dur)


def _mark_mobility(week: list[dict]) -> None:
    """Mark up to three mobility days in place.

    Strength days already carry the trunk block and key rides want the legs
    left alone, so mobility goes wherever it competes with nothing.
    """
    candidates = [
        d for d in week
        if not d["is_strength"] and d["type"] not in _POSITION_KEY_TYPES
    ]
    for day in sorted(candidates, key=_mobility_rank)[:_POSITION_MOBILITY_TARGET]:
        day["mobility"] = True


def _next_strength(after: date, limit: int = 5, horizon: int = 400) -> list[dict]:
    """The next `limit` strength dates from `after` inclusive."""
    out: list[dict] = []
    for offset in range(horizon):
        d = after + timedelta(days=offset)
        s = _strength_on(d)
        if s:
            out.append({
                **s,
                "date": d,
                "iso": d.isoformat(),
                "date_str": d.strftime("%a %-d %b"),
                "dur_fmt": _fmt_min(s["dur_min"]) if s["dur_min"] else None,
                "days_away": (d - after).days,
            })
            if len(out) >= limit:
                break
    return out


def _position_gap_reason(start: date, end: date) -> str:
    """Why there is no strength between two dates, in the plan's own words."""
    from ..plan import CAMP_START, CAMP_END, CHARITY_DAYS

    labels: list[str] = []
    if start <= CAMP_END and end >= CAMP_START:
        labels.append("Tenerife camp")
    if any(start <= c["date"] <= end for c in CHARITY_DAYS):
        labels.append("charity ride")
    return " and ".join(labels) if labels else "no strength scheduled"


def _position_cadence(week: list[dict]) -> str:
    """One-liner describing this week's strength dose."""
    days = [d["weekday"] for d in week if d["is_strength"]]
    if not days:
        return "No strength this week"
    if len(days) == 1:
        return f"1 session this week — {days[0]}"
    return f"{len(days)} sessions this week — {' and '.join([', '.join(days[:-1]), days[-1]])}"


def _position_context() -> dict[str, Any]:
    """Context for /position: today's answer plus a week derived from the plan."""
    today = _today()
    monday = today - timedelta(days=today.weekday())
    week = [_position_day(monday + timedelta(days=i), today) for i in range(7)]
    _mark_mobility(week)

    today_row = week[today.weekday()]
    upcoming = _next_strength(today)

    # Only call it a gap when the wait is long enough to be worth explaining.
    gap = None
    if upcoming and upcoming[0]["days_away"] > 10:
        nxt = upcoming[0]["date"]
        gap = {
            "days": upcoming[0]["days_away"],
            "until_str": nxt.strftime("%a %-d %b"),
            "reason": _position_gap_reason(today, nxt - timedelta(days=1)),
        }

    return {
        "pos_today": today_row,
        "pos_next": upcoming[0] if upcoming else None,
        "pos_week": week,
        "pos_upcoming": upcoming,
        "pos_gap": gap,
        "pos_cadence": _position_cadence(week),
        "pos_mobility_days": [d["weekday"] for d in week if d["mobility"]],
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

    # Today's fluid intake from Garmin hydration log (distinct from body-water %)
    today_iso = local_today().isoformat()
    water_today = next(
        (r for r in reversed(recent_metrics)
         if (r["date"].isoformat() if hasattr(r["date"], "isoformat") else str(r["date"])) == today_iso
         and r.get("water_intake_ml") is not None),
        None,
    )
    water_intake_l = (water_today["water_intake_ml"] / 1000.0) if water_today else None
    water_goal_l = (
        water_today["water_goal_ml"] / 1000.0
        if water_today and water_today.get("water_goal_ml") is not None
        else None
    )

    # TDEE per day = Katch-McArdle BMR (body comp) + measured active calories.
    _tdee_by_date = {}
    _bmr_by_date = {}
    _active_by_date = {}
    _active_est_by_date = {}
    try:
        for _t in tdee_history(14):
            _d = _t["date"]
            _di = _d.isoformat() if hasattr(_d, "isoformat") else str(_d)
            _tdee_by_date[_di] = _t.get("tdee")
            _bmr_by_date[_di] = _t.get("bmr")
            _active_by_date[_di] = _t.get("active_calories")
            _active_est_by_date[_di] = _t.get("active_estimated")
    except Exception:
        pass

    def _row_iso(r):
        _d = r["date"]
        return _d.isoformat() if hasattr(_d, "isoformat") else str(_d)

    # Calorie intake from food log (last 14 days of data)
    con_vals = [r.get("calories_consumed")     for r in recent_metrics if r.get("calories_consumed")     is not None]
    adj_vals = [
        _tdee_by_date.get(_row_iso(r))
        for r in recent_metrics
        if r.get("calories_consumed") is not None and _tdee_by_date.get(_row_iso(r)) is not None
    ]
    cal_ctx: dict = {}
    if con_vals:
        cal_ctx["avg_consumed"]   = round(sum(con_vals) / len(con_vals))
        cal_ctx["avg_tdee"]       = round(sum(adj_vals) / len(adj_vals)) if adj_vals else None
        cal_ctx["days_logged"]    = len(con_vals)
        if cal_ctx["avg_tdee"]:
            cal_ctx["avg_deficit"] = cal_ctx["avg_tdee"] - cal_ctx["avg_consumed"]
    # Today's specific values (calendar today — not the most recent logged day)
    _today = date.today()
    today_nut = metrics_row_for_date(recent_metrics, _today)
    if today_nut:
        _today_iso = _today.isoformat()
        if today_nut.get("calories_consumed") is not None:
            cal_ctx["today_consumed"] = today_nut.get("calories_consumed")
            cal_ctx["today_goal"]     = today_nut.get("calorie_goal")
            if today_nut.get("carbs_consumed") is not None:
                cal_ctx["today_carbs"] = round(today_nut["carbs_consumed"])
            if today_nut.get("protein_consumed") is not None:
                cal_ctx["today_protein"] = round(today_nut["protein_consumed"])
        if _tdee_by_date.get(_today_iso) is not None:
            cal_ctx["today_tdee"]     = _tdee_by_date.get(_today_iso)
            cal_ctx["today_bmr"]      = _bmr_by_date.get(_today_iso)
            cal_ctx["today_active"]   = _active_by_date.get(_today_iso)
            cal_ctx["today_active_estimated"] = _active_est_by_date.get(_today_iso)
        # Activities that rolled up into today's Garmin active-calorie total
        try:
            _acts = load_activities_by_date(_today, _today).get(_today_iso, [])
            _contrib = []
            for a in _acts:
                if a.get("calories") is None:
                    continue
                _e = enrich_activity(a)
                _contrib.append({
                    "name": a.get("name") or _e.get("type_label") or "Activity",
                    "icon": _e.get("icon", "🏅"),
                    "calories": int(round(a["calories"])),
                })
            _contrib.sort(key=lambda x: x["calories"], reverse=True)
            if _contrib:
                cal_ctx["today_activities"] = _contrib
        except Exception:
            pass
    # Intake target from the single resolver (stable TDEE, maintenance/camp aware).
    try:
        _tt = nutrition_today_targets(_today)
        if _tt.get("kcal_source") != "tier" or _tt.get("stable_tdee"):
            cal_ctx["today_intake_target"] = _tt["kcal"]
            cal_ctx["intake_from_tdee"] = _tt["kcal_source"] in ("tdee", "camp")
            if _tt.get("stable_tdee"):
                cal_ctx["stable_tdee"] = _tt["stable_tdee"]
            if _tt.get("planned_deficit") is not None:
                cal_ctx["today_plan_deficit"] = _tt["planned_deficit"]
            cal_ctx["maintenance"] = _tt["maintenance"]
    except Exception:
        pass
    # Protein floor (lean-mass based) for the Protein Today tile.
    try:
        _pt = protein_target_g()
        cal_ctx["protein_low"] = _pt["low"]
        cal_ctx["protein_high"] = _pt["high"]
    except Exception:
        pass
    # 14-day macro averages
    carbs_vals   = [r["carbs_consumed"]   for r in recent_metrics if r.get("carbs_consumed")   is not None]
    protein_vals = [r["protein_consumed"] for r in recent_metrics if r.get("protein_consumed") is not None]
    if carbs_vals:
        cal_ctx["avg_carbs"]   = round(sum(carbs_vals) / len(carbs_vals))
    if protein_vals:
        cal_ctx["avg_protein"] = round(sum(protein_vals) / len(protein_vals))

    try:
        _cal = tdee_calibration()
        if _cal:
            cal_ctx["tdee_correction"] = _cal["correction"]
            cal_ctx["empirical_tdee"] = _cal["empirical_tdee"]
            cal_ctx["tdee_model_avg"] = _cal["model_avg"]
            cal_ctx["calibration_n_days"] = _cal["n_intake_days"]
            conf = _cal.get("confidence") or {}
            cal_ctx["calibration_confidence"] = conf.get("level", "inactive")
            cal_ctx["calibration_reasons"] = conf.get("reasons", [])
            cal_ctx["calibration_coverage_pct"] = conf.get("intake_coverage_pct")
        else:
            cal_ctx["calibration_confidence"] = "inactive"
            cal_ctx["calibration_reasons"] = ["guardrails not met — using uncorrected model TDEE"]
    except Exception:
        pass

    # Calorie chart (last 14 days) — convert date objects to ISO strings for _short()
    _cal_rows   = [r for r in recent_metrics if r.get("calories_consumed") is not None]
    _cal_isos   = [r["date"].isoformat() if hasattr(r["date"], "isoformat") else str(r["date"]) for r in _cal_rows]
    cal_values  = [r["calories_consumed"] for r in _cal_rows]
    tdee_values = [_tdee_by_date.get(_row_iso(r)) for r in _cal_rows]
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
        "water_intake_l": water_intake_l,
        "water_goal_l": water_goal_l,
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

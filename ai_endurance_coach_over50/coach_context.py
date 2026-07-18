"""Shared coaching context for daily advice and coach chat."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from .alerts import check_fatigue_alerts
from .analysis import (
    load_analyses_for_activities,
    retrieve_relevant_analyses,
)
from .hr_profile import format_hr_profile_lines
from .power_profile import build_power_profile, format_power_profile_lines
from .history import (
    ACTIVITY_MATCH,
    acclimation_latest,
    baseline_stats,
    composite_score,
    ftp_retest_due,
    get_cached_text,
    get_coach_memory,
    get_plan_override,
    intensity_distribution_by_week,
    intensity_distribution_by_week_power,
    latest_estimated_wkg,
    latest_measured_wkg,
    list_plan_overrides,
    load,
    load_activities_by_date,
    load_advice,
    load_body_metrics,
    load_blood_pressure,
    load_btb_summary,
    load_durability,
    load_ftp_tests,
    load_fuelling_logs,
    load_morning_snapshot,
    load_power_durability,
    load_recent_activities,
    load_session_rpe,
    pmc_history,
    power_meter_active,
    power_pmc_history,
    raw_history,
    sleep_history,
    tdee_calibration,
    tdee_history,
    weekly_monotony_strain,
)
from .coach_voice import ATHLETE_CONSTRAINTS, COACH_VOICE, hr_channel_note
from .hr_plan import HR_EVENT_NAME, HR_PHASES, HR_PLAN_START, hr_session_for_date, hr_2012_lessons_context
from .metrics import DailyMetrics
from .plan import (
    PLAN_START,
    build_calendar_weeks,
    CAMP_END,
    CAMP_GRID_WORKOUTS,
    CHARITY_EVENT_NAME,
    COMPOUND_SESSIONS,
    EVENT_PREP_DAYS,
    TENERIFE_DAYS,
    charity_event_summary,
    session_for_date,
    session_for_date_extended,
)

_BIKE_TYPES = frozenset({"bike", "tempo", "ftp", "long"})
_STRENGTH_TYPES = frozenset({"strength", "gym"})
_RUCK_TYPES = frozenset({"ruck"})

QUALITY_BIKE_LABELS = {
    "Tempo Intervals", "Hill Repeats", "Sweetspot Ride", "Over-Unders",
    "Threshold Ride", "FTP Test", "FTP Re-test", "Final FTP Test",
}

_DISCIPLINE_MAP = {
    "bike": "cycling", "tempo": "cycling", "ftp": "cycling", "long": "cycling",
    "strength": "strength", "ruck": "rucking / load-carry",
}


def session_discipline(stype: str) -> str:
    if stype in _BIKE_TYPES:
        return "cycling"
    if stype in _STRENGTH_TYPES:
        return "strength (kettlebells / MaxiClimber)"
    if stype in _RUCK_TYPES:
        return "rucking (weighted pack walk/hike — NOT running)"
    if stype == "recovery":
        return "recovery / easy cycling"
    if stype == "rest":
        return "rest"
    return stype


def coach_persona_brief(has_power: bool, *, post_workout: bool = False) -> str:
    if post_workout:
        task = (
            "Right now: the athlete has ALREADY completed today's planned workout (or trained on a "
            "rest day). Give a concise post-workout debrief and recovery guidance for the dashboard — "
            "NOT a morning pre-session briefing. Readiness metrics in context are from this morning "
            "before the session; do not describe them as post-workout or 'the morning after'. "
            "Never refer to today's session as yesterday. Keep it specific and grounded in the "
            "actual numbers — warm and motivating, but never vague."
        )
    else:
        task = (
            "Right now: give a concise train/rest/modify-today recommendation for the morning "
            "readiness dashboard. Keep it specific and grounded in the actual numbers from the "
            "context — warm and motivating, but never vague."
        )
    return (
        COACH_VOICE + "\n\n"
        + ATHLETE_CONSTRAINTS + "\n\n"
        + task + "\n\n"
        + "When referring to A-events, use only the official names in context "
        f"(e.g. \"{CHARITY_EVENT_NAME}\", \"{HR_EVENT_NAME}\"). "
        "Never invent alternative names or nicknames.\n\n"
        + hr_channel_note(has_power)
    )


def _te_clean(label: Optional[str]) -> str:
    return (label or "").replace("_", " ").title()


def _load_day_state(target: date):
    history = pmc_history(days=7)
    today_pmc = history[-1] if history else {}
    m = load(target) or DailyMetrics(date=target)
    stats = baseline_stats(target)
    comp_z = composite_score(m, stats)
    from .modulation import resolve_modulation
    traffic_light, modulation = resolve_modulation(target, m, comp_z)
    return m, stats, comp_z, traffic_light, modulation, today_pmc


def _acwr_line(m: Optional["DailyMetrics"]) -> Optional[str]:
    """Garmin's own acute:chronic ratio (unitless — comparable to standard thresholds)."""
    acwr = getattr(m, "acwr", None) if m else None
    if acwr is None:
        return None
    status = getattr(m, "acwr_status", None)
    status_txt = f" ({status.replace('_', ' ').lower()})" if status else ""
    return f"ACWR (acute:chronic, unitless): {acwr:.2f}{status_txt}"


def _truncate_advice(text: str, max_chars: int = 500) -> str:
    """First two paragraphs of locked morning advice, capped for context size."""
    paras = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    clipped = "\n\n".join(paras[:2]) if paras else text.strip()
    if len(clipped) > max_chars:
        return clipped[: max_chars - 1].rstrip() + "…"
    return clipped


def _section_today_readiness(m: DailyMetrics, comp_z: Optional[float]) -> list[str]:
    """Live readiness from daily_metrics — AM BB labelled separately from current."""
    lines = [
        "## Today's Readiness",
        f"Composite z-score: {f'{comp_z:+.2f}σ' if comp_z is not None else 'n/a'}",
        f"HRV: {m.hrv_last_night}  |  Sleep score: {m.sleep_score}  |  "
        f"Body battery (AM): {m.body_battery_morning}  |  "
        f"Body battery (now): {m.body_battery_current}",
        f"Avg stress: {m.avg_stress}  |  Rest stress: {m.rest_stress}  |  "
        f"Resting HR: {m.resting_hr}  |  VO2max: {m.vo2_max}",
    ]
    extra: list[str] = []
    if m.hrv_weekly_avg is not None or m.hrv_status:
        bits = []
        if m.hrv_weekly_avg is not None:
            bits.append(f"HRV weekly avg {m.hrv_weekly_avg}")
        if m.hrv_status:
            bits.append(f"status {m.hrv_status}")
        extra.append("  " + "  |  ".join(bits))
    if m.training_status_label:
        extra.append(f"  Training status: {m.training_status_label}")
    if m.training_load_acute is not None or m.training_load_chronic is not None:
        extra.append(
            f"  Load acute: {m.training_load_acute}  |  chronic: {m.training_load_chronic}"
        )
    if m.total_steps is not None or m.active_calories is not None:
        bits = []
        if m.total_steps is not None:
            bits.append(f"steps {int(m.total_steps)}")
        if m.active_calories is not None:
            bits.append(f"active kcal {int(m.active_calories)}")
        extra.append("  " + "  |  ".join(bits))
    lines.extend(extra)
    return lines


def _section_morning_gate(today: date) -> list[str]:
    """Frozen morning snapshot + truncated locked pre-advice for alignment with Today tab."""
    snap = load_morning_snapshot(today)
    advice = load_advice(today, mode="pre")
    if snap is None and not advice:
        return []
    lines = ["## Morning Gate (locked)"]
    if snap:
        captured = snap.get("captured_at") or "—"
        label = snap.get("readiness_label") or "—"
        comp = snap.get("composite_z")
        comp_str = f"{comp:+.2f}σ" if comp is not None else "n/a"
        lines.append(f"  Captured: {captured}  |  readiness {label} ({comp_str})")
        tl = snap.get("traffic_light_status")
        if tl:
            reason = snap.get("traffic_light_reason") or ""
            lines.append(f"  Traffic light: {tl.upper()}" + (f" — {reason}" if reason else ""))
        lines.append(
            f"  AM: HRV {snap.get('hrv_last_night')}  |  sleep {snap.get('sleep_score')}  |  "
            f"body battery {snap.get('body_battery_morning')}  |  RHR {snap.get('resting_hr')}"
        )
        if advice is None and snap.get("advice_pre"):
            advice = snap["advice_pre"]
    if advice:
        lines.append("  Locked advice (excerpt):")
        for para in _truncate_advice(advice).split("\n\n"):
            lines.append(f"    {para}")
    return lines


def _section_power_pmc() -> list[str]:
    """Coggan TSS CTL/ATL/TSB — separate units from Garmin PMC."""
    if not power_meter_active():
        return []
    try:
        hist = power_pmc_history(days=14)
    except Exception:
        return []
    if not hist:
        return []
    latest = hist[-1]
    lines = [
        "## Power PMC (Coggan TSS)",
        f"  CTL: {latest.get('ctl')}  |  ATL: {latest.get('atl')}  |  "
        f"TSB: {latest.get('tsb')}  (as of {latest.get('date')})",
    ]
    if len(hist) >= 8:
        week_ago = hist[-8]
        lines.append(
            f"  7d ago: CTL {week_ago.get('ctl')}  |  ATL {week_ago.get('atl')}  |  "
            f"TSB {week_ago.get('tsb')}"
        )
    return lines


def _section_weekly_briefing(today: date) -> list[str]:
    monday = today - timedelta(days=today.weekday())
    text = get_cached_text(f"weekly_briefing_v3_{monday.isoformat()}")
    if not text:
        return []
    lines = ["## Weekly Briefing (this week)", "  " + text.replace("\n", "\n  ")]
    return lines


def _section_today_session_prescriptions(today: date) -> list[str]:
    """Cached nutrition targets + in-ride fuelling for today's planned session."""
    from .nutrition_plan import camp_nutrition_window

    if camp_nutrition_window(today):
        return []  # camp macros come from nutrition_coach_context camp mode

    sess = session_for_date_extended(today) or hr_session_for_date(today)
    if sess is None or sess[0] == "rest":
        return []
    stype, label, dur = sess
    ov = get_plan_override(today.isoformat())
    if ov:
        stype = ov.get("session_type") or stype
        label = ov.get("label") or label
        dur = ov.get("duration_min") or dur
    lines: list[str] = []
    try:
        from .analysis import _load_fuelling_plans, _load_nutrition_targets, fuelling_session_key
        goal = "perform" if today >= HR_PLAN_START else "cut"
        targets = _load_nutrition_targets()
        key = f"{goal}_v2_{stype}_{dur}"
        tgt = targets.get(key)
        if tgt is None:
            other = "cut" if goal == "perform" else "perform"
            tgt = targets.get(f"{other}_v2_{stype}_{dur}")
        if tgt:
            lines += [
                "## Today's Nutrition Target (cached)",
                f"  Session: {label} ({stype}, {dur}min)",
                f"  {tgt.get('kcal')} kcal  |  P {tgt.get('protein_g')}g  |  "
                f"C {tgt.get('carbs_g')}g  |  F {tgt.get('fat_g')}g",
            ]
            if tgt.get("brief"):
                lines.append(f"  {tgt['brief']}")
        if stype in _BIKE_TYPES and dur >= 75:
            plan = _load_fuelling_plans().get(fuelling_session_key(stype, dur))
            if plan:
                if not lines:
                    lines.append(f"## Today's Fuelling Plan (cached) — {label} ({dur}min)")
                else:
                    lines.append("## Today's Fuelling Plan (cached)")
                lines.append(
                    f"  {plan.get('carbs_g_per_hr')}g carbs/h  |  "
                    f"total {plan.get('total_carbs_g')}g  |  "
                    f"{plan.get('fluid_ml_per_hr')}ml/h  |  "
                    f"{plan.get('sodium_mg_per_hr')}mg sodium/h"
                )
                if plan.get("brief"):
                    lines.append(f"  {plan['brief']}")
    except Exception:
        return lines
    return lines


def _section_recent_analyses(recent_acts: list[dict], limit: int = 3) -> list[str]:
    """Last few activity analyses regardless of discipline (complements RAG)."""
    if not recent_acts:
        return []
    try:
        enriched = load_analyses_for_activities(recent_acts[:8])
    except Exception:
        return []
    with_text = [a for a in enriched if (a.get("analysis_text") or "").strip()]
    if not with_text:
        return []
    lines = ["## Recent Session Analyses (last few, any discipline)"]
    for a in with_text[:limit]:
        text = (a.get("analysis_text") or "").strip().replace("\n", " ")
        summary = (text[:280] + "…") if len(text) > 280 else text
        lines.append(f"  {a.get('date')} — {a.get('name') or a.get('type_key')}")
        lines.append(f"    {summary}")
    return lines


def _section_ftp_flags(today: date) -> list[str]:
    lines: list[str] = []
    try:
        due = ftp_retest_due(today, plan_start=PLAN_START)
        if due:
            if due.get("last_date"):
                lines.append(
                    f"  FTP retest due: last test {due['last_date']} "
                    f"({due['age_days']} days ago)"
                )
            else:
                lines.append("  FTP retest due: no test on record (3+ weeks into plan)")
    except Exception:
        pass
    try:
        stale = get_cached_text("workouts_stale_ftp")
        if stale:
            lines.append(
                f"  Garmin workouts stale after new FTP ({stale}W) — re-sync %FTP targets"
            )
    except Exception:
        pass
    if not lines:
        return []
    return ["## FTP / Workout Sync Flags", *lines]


def _section_pmc(today_pmc: dict, m: Optional["DailyMetrics"] = None) -> list[str]:
    lines = [
        "## Training Load (PMC)  (Garmin training-load units, NOT Coggan TSS — absolute values not comparable to standard thresholds)",
        f"CTL (fitness): {today_pmc.get('ctl')}  |  ATL (fatigue): {today_pmc.get('atl')}  |  TSB (form): {today_pmc.get('tsb')}",
    ]
    acwr_line = _acwr_line(m)
    if acwr_line:
        lines.append(acwr_line)
    try:
        from .history import power_meter_active, weekly_tss
        if power_meter_active():
            wk = weekly_tss(2)
            if wk:
                lines.append(f"Power TSS this week: {round(wk[-1]['total_tss'])}")
    except Exception:
        pass
    return lines


def _section_traffic_light(traffic_light: dict, modulation: Optional[dict]) -> list[str]:
    tl_status = traffic_light.get("status", "unknown")
    tl_reason = traffic_light.get("reason", "")
    hrv_z_str = f"z={traffic_light['hrv_z']:+.2f}" if traffic_light.get("hrv_z") is not None else ""
    parts = [
        "## HRV Traffic Light",
        f"  Status: {tl_status.upper()}  {hrv_z_str}  — {tl_reason}",
    ]
    if modulation and modulation.get("label"):
        gate_tag = "Recovery gate" if modulation.get("gate") else "HRV modulation"
        parts.append(
            f"  Suggested swap ({gate_tag}): {modulation['planned_label']} -> {modulation['label']} "
            f"({modulation['duration_min']}min) — {modulation.get('headline', '')}"
        )
    elif modulation and modulation.get("gate"):
        parts.append(f"  Recovery gate: {modulation.get('reason', modulation.get('headline', ''))}")
    return parts


def _section_alerts(target: date) -> list[str]:
    try:
        alerts = check_fatigue_alerts(target)
        if alerts:
            parts = ["## Active Fatigue Alerts"]
            for a in alerts:
                parts.append(f"  [{a['severity']}] {a['type']}: {a['message']}")
            return parts
    except Exception:
        pass
    return []


def resolve_today_session(target: date) -> Optional[tuple[str, str, int]]:
    """Planned session for `target` with overrides applied; None if rest or out of plan."""
    session = session_for_date_extended(target)
    if not session or session[0] == "rest":
        return None
    stype, label, dur = session
    ov = get_plan_override(target.isoformat())
    if ov:
        stype = ov.get("session_type") or stype
        label = ov.get("label") or label
        dur = ov["duration_min"]
    return stype, label, dur


def session_logged_for_plan(target: date, stype: str, label: str) -> tuple[bool, list[dict]]:
    """True when today's Garmin activities satisfy the planned session type."""
    day_acts = load_activities_by_date(target, target).get(target.isoformat(), [])
    if not day_acts:
        return False, []
    compound = COMPOUND_SESSIONS.get(label)
    if compound:
        matched = [a for a in day_acts if any(a["type_key"] == s["garmin_key"] for s in compound)]
    else:
        valid_keys = ACTIVITY_MATCH.get(stype, set())
        matched = [a for a in day_acts if a["type_key"] in valid_keys]
    return bool(matched), matched


def build_advice_timing(
    target: date,
    *,
    now: Optional[datetime] = None,
    today: Optional[date] = None,
) -> dict[str, Any]:
    """Clock time + whether today's planned workout is already logged."""
    now = now or datetime.now()
    today = today or date.today()
    is_today = target == today
    session = resolve_today_session(target)
    completed = False
    matched: list[dict] = []
    if session:
        completed, matched = session_logged_for_plan(target, session[0], session[1])

    day_acts = load_activities_by_date(target, target).get(target.isoformat(), []) if is_today else []
    post_workout = bool(is_today and ((session and completed) or (not session and day_acts)))

    part_of_day = None
    local_time = None
    if is_today:
        local_time = now.strftime("%H:%M")
        hour = now.hour
        if hour < 12:
            part_of_day = "morning"
        elif hour < 17:
            part_of_day = "afternoon"
        else:
            part_of_day = "evening"

    return {
        "is_today": is_today,
        "local_time": local_time,
        "part_of_day": part_of_day,
        "session": session,
        "completed": completed,
        "matched_activities": matched or day_acts,
        "post_workout": post_workout,
    }


def _section_timing(timing: dict[str, Any], target: date) -> list[str]:
    lines = ["## Time & Session Status"]
    if timing["is_today"] and timing["local_time"]:
        lines.append(f"  Now: {timing['local_time']} local ({timing['part_of_day']})")
    else:
        lines.append("  Historical view (not today)")
    if timing["post_workout"]:
        lines.append("  Status: POST-WORKOUT — training already logged today")
        lines.append(
            "  Readiness metrics below are from THIS MORNING before the session — "
            "they do NOT reflect post-workout fatigue"
        )
        for a in timing["matched_activities"][:3]:
            dur = int((a.get("duration_seconds") or 0) / 60)
            name = a.get("name") or a.get("type_key")
            lines.append(f"  Logged today: {name} — {dur}min")
    elif timing["session"]:
        _stype, label, _dur = timing["session"]
        lines.append(f"  Status: PRE-WORKOUT — {label} not yet logged today")
    else:
        lines.append("  Status: rest day (no session scheduled)")
    return lines


def _section_today_session(target: date, timing: Optional[dict[str, Any]] = None) -> list[str]:
    session = resolve_today_session(target)
    if not session:
        if timing and timing.get("post_workout"):
            return ["## Today's Planned Workout", "  Rest day — athlete trained anyway (see logged activities)"]
        return ["## Today's Planned Workout", "  Rest / not in plan period"]
    stype, label, dur = session
    ov = get_plan_override(target.isoformat())
    note = f" [override: {ov.get('note', '')}]" if ov and ov.get("note") else (" [override active]" if ov else "")
    dur_str = f"{dur}m" if dur and dur < 60 else (f"{dur // 60}h{dur % 60:02d}m" if dur and dur % 60 else f"{dur // 60}h") if dur else "—"
    discipline = session_discipline(stype)
    status = ""
    if timing:
        if timing.get("completed"):
            status = " — COMPLETED today"
        elif timing.get("is_today"):
            status = " — not yet logged"
    lines = [
        "## Today's Planned Workout",
        f"  {label} — {discipline} ({stype}, {dur_str}){note}{status}",
    ]
    try:
        from .history import list_session_notes
        day_note = list_session_notes().get(target.isoformat())
        if day_note:
            lines.append(f"  Coach note for this day: {day_note}")
    except Exception:
        pass
    return lines


def _section_week_ahead(target: date) -> list[str]:
    lines = ["## Next 7 Days (non-rest sessions)"]
    found = False
    for i in range(1, 8):
        d = target + timedelta(days=i)
        sess = session_for_date_extended(d)
        if not sess or sess[0] == "rest":
            continue
        stype, label, dur = sess
        ov = get_plan_override(d.isoformat())
        if ov:
            dur = ov["duration_min"]
            label = f"{label} [MODIFIED]"
        lines.append(
            f"  {d.strftime('%a %d %b')}: {label} — {session_discipline(stype)} ({dur}min)"
        )
        found = True
    if not found:
        lines.append("  None scheduled")
    return lines


def _section_recent_activities(days: int = 7, limit: int = 5) -> list[str]:
    recent_acts = load_recent_activities(days=days)
    lines = [f"## Recent Activities (last {days} days)"]
    if not recent_acts:
        lines.append("  None recorded")
        return lines
    for a in recent_acts[:limit]:
        dur_min = int((a.get("duration_seconds") or 0) / 60)
        parts = [f"{a['date']}: {a.get('name') or a.get('type_key')} — {dur_min}min"]
        if a.get("avg_hr"):
            parts.append(f"avg HR {int(a['avg_hr'])}bpm")
        if a.get("training_load") is not None:
            parts.append(f"load {int(a['training_load'])}")
        lines.append("  " + ", ".join(parts))
    return lines


def _section_coach_memory() -> list[str]:
    memo = get_coach_memory()
    if memo:
        return ["## Coach Memory (cross-session context)", memo["memo"]]
    return []


def _section_power_profile() -> list[str]:
    return format_power_profile_lines()


def _section_hr_profile(resting_hr_today: Optional[float] = None) -> list[str]:
    lines = format_hr_profile_lines(resting_hr_today=resting_hr_today)
    if lines and build_power_profile():
        lines.insert(1, "(Secondary strain/readiness channel — power is primary for prescription.)")
    return lines


def _section_ftp(limit: int = 1) -> list[str]:
    ftp_rows = load_ftp_tests()
    if not ftp_rows:
        return []
    title = "## FTP / LTHR (latest)" if limit == 1 else "## FTP Test History"
    if limit != 1 and not power_meter_active():
        title += " (LTHR)"
    parts = [title]
    for r in ftp_rows[-limit:]:
        line = f"  {r['date']}: LTHR {r['ftp_hr']}bpm"
        if r.get("ftp_hr_max"):
            line += f" (max {r['ftp_hr_max']}bpm)"
        if r.get("ftp_w"):
            line += f"  |  FTP {r['ftp_w']}W"
        parts.append(line)
    return parts


def _section_rag(session_type: Optional[str], limit: int = 2) -> list[str]:
    if not session_type:
        return []
    discipline = _DISCIPLINE_MAP.get(session_type, session_type)
    past = retrieve_relevant_analyses(session_type, limit=limit)
    if not past:
        return []
    lines = [
        f"## Relevant Past Sessions (recent {discipline})",
        f"Recent {discipline} sessions — NOT necessarily the same workout type as today.",
    ]
    for p in past:
        hdr = f"  {p['date']} — {p.get('name') or p.get('type_key')}"
        stats = []
        if p.get("avg_hr"):
            stats.append(f"avg HR {int(p['avg_hr'])}")
        if p.get("training_load") is not None:
            stats.append(f"load {int(p['training_load'])}")
        if stats:
            hdr += " (" + ", ".join(stats) + ")"
        lines.append(hdr)
        if p.get("summary"):
            lines.append(f"    {p['summary']}")
    return lines


def _section_key_dates(today: date) -> list[str]:
    """Canonical timing block. The coach is instructed to read plan/camp/event/test
    timing from here and never reason about dates from memory (kills the
    'it lands before/after Tenerife' error class)."""
    from .plan import CAMP_START, CHARITY_DAYS, _PLAN_DAYS
    from .hr_plan import HR_EVENT_STAGES

    def _until(d: date) -> str:
        n = (d - today).days
        if n > 1:
            return f"in {n} days"
        if n == 1:
            return "tomorrow"
        if n == 0:
            return "TODAY"
        return f"{-n} days ago"

    lines = ["## Key Dates (canonical — read timing from here, never from memory)"]
    plan_end = PLAN_START + timedelta(days=_PLAN_DAYS - 1)
    lines.append(
        f"  12-week charity plan: {PLAN_START.isoformat()} → {plan_end.isoformat()} "
        f"(ends {_until(plan_end)})"
    )
    next_ftp = None
    for i in range(400):
        d = today + timedelta(days=i)
        sess = session_for_date_extended(d) or hr_session_for_date(d)
        if sess and sess[0] == "ftp":
            next_ftp = (d, sess[1])
            break
    if next_ftp:
        lines.append(
            f"  Next FTP test: {next_ftp[0].strftime('%a %d %b %Y')} ({next_ftp[0].isoformat()}) "
            f"— {next_ftp[1]} ({_until(next_ftp[0])})"
        )
    lines.append(
        f"  Tenerife camp: {CAMP_START.isoformat()} → {CAMP_END.isoformat()} "
        f"(starts {_until(CAMP_START)})"
    )
    if CHARITY_DAYS:
        c1, c2 = CHARITY_DAYS[0]["date"], CHARITY_DAYS[-1]["date"]
        lines.append(f"  {CHARITY_EVENT_NAME}: {c1.isoformat()} → {c2.isoformat()} (starts {_until(c1)})")
    lines.append(f"  Haute Route 46-week plan starts: {HR_PLAN_START.isoformat()} ({_until(HR_PLAN_START)})")
    if HR_EVENT_STAGES:
        h1, h2 = HR_EVENT_STAGES[0]["date"], HR_EVENT_STAGES[-1]["date"]
        lines.append(f"  {HR_EVENT_NAME}: {h1.isoformat()} → {h2.isoformat()} (starts {_until(h1)})")
    return lines


def _section_canonical_baselines(today: date, m: "DailyMetrics") -> list[str]:
    """Single source of truth for baseline numbers. The coach is instructed to
    quote ONLY these when citing HRV/RHR/weight/muscle/FTP baselines, so the
    same conversation can't drift between two different 'baselines'."""
    import statistics as _st
    lines: list[str] = []
    rows = raw_history(31)
    hrv_vals = [r["hrv_last_night"] for r in rows if r.get("hrv_last_night") is not None]
    if hrv_vals:
        mean30 = _st.mean(hrv_vals)
        sd30 = _st.pstdev(hrv_vals) if len(hrv_vals) > 1 else 0.0
        seg = f"  HRV: 30d baseline {mean30:.1f} ± {sd30:.1f} ms  |  7d avg {_st.mean(hrv_vals[-7:]):.1f} ms"
        if m.hrv_last_night is not None:
            seg += f"  |  last night {m.hrv_last_night:.0f} ms"
        lines.append(seg)
    rhr_vals = [r["resting_hr"] for r in rows if r.get("resting_hr") is not None]
    if rhr_vals:
        seg = f"  Resting HR: 30d avg {_st.mean(rhr_vals):.0f} bpm"
        if m.resting_hr is not None:
            seg += f"  |  today {m.resting_hr:.0f} bpm"
        lines.append(seg)
    body_rows = load_body_metrics(days=14)
    w_rows = [(r["date"], r["weight_kg"]) for r in body_rows if r.get("weight_kg") is not None]
    mm_rows = [(r["date"], r["muscle_mass_kg"]) for r in body_rows if r.get("muscle_mass_kg") is not None]
    avg_w = None
    if w_rows:
        avg_w = sum(v for _, v in w_rows) / len(w_rows)
        lines.append(
            f"  Weight: 14d rolling avg {avg_w:.1f} kg  |  latest {w_rows[-1][1]:.1f} kg ({w_rows[-1][0]})"
        )
    if mm_rows:
        avg_mm = sum(v for _, v in mm_rows) / len(mm_rows)
        lines.append(
            f"  Muscle mass: 14d rolling avg {avg_mm:.1f} kg  |  latest {mm_rows[-1][1]:.1f} kg ({mm_rows[-1][0]})"
        )
    ftp_w = ftp_date = None
    for t in reversed(load_ftp_tests()):
        if t.get("ftp_w"):
            ftp_w, ftp_date = int(t["ftp_w"]), t["date"]
            break
    if ftp_w:
        seg = f"  FTP: {ftp_w} W (test {ftp_date})"
        if avg_w:
            seg += f"  |  {ftp_w / avg_w:.2f} W/kg on 14d avg weight"
        lines.append(seg)
    if not lines:
        return []
    return [
        "## Canonical Baselines (single source of truth — when citing baselines, quote ONLY these)",
        *lines,
        "  Noise bands: judge weight/muscle on the 14d averages (single scale readings swing ±0.5–1 kg); "
        "FTP retest within ±3% of previous = FLAT; HRV via z-score and 7d/30d ratio, never one night.",
    ]


def _section_commitments(today: date) -> list[str]:
    """Open durable commitments (checkpoints / guardrails / decision rules)."""
    try:
        from .history import list_coach_commitments
        rows = list_coach_commitments("open")
    except Exception:
        return []
    if not rows:
        return []
    lines = ["## Open Coach Commitments (durable — evaluate & resolve_commitment when DUE)"]
    for r in rows:
        due = ""
        if r.get("review_date"):
            try:
                rd = date.fromisoformat(r["review_date"])
                due = "  ⚠ DUE NOW" if rd <= today else f"  (review {r['review_date']})"
            except ValueError:
                due = f"  (review {r['review_date']})"
        lines.append(f"  [{r['id']}] {r['title']}{due}")
        if r.get("decision_rule"):
            lines.append(f"      Rule: {r['decision_rule']}")
        if r.get("baseline"):
            lines.append(f"      Baseline: {r['baseline']}")
    return lines


def _section_session_notes(today: date, days: int = 14) -> list[str]:
    """Upcoming per-date coaching notes (shown on calendar tiles)."""
    try:
        from .history import list_session_notes
        notes = list_session_notes()
    except Exception:
        return []
    end = (today + timedelta(days=days)).isoformat()
    upcoming = sorted((d, n) for d, n in notes.items() if today.isoformat() <= d <= end)
    if not upcoming:
        return []
    lines = [f"## Session Notes (on calendar tiles, next {days} days)"]
    for d, n in upcoming:
        lines.append(f"  {d}: {n}")
    return lines


def _current_training_phase(today: date) -> tuple[str, str]:
    """(label, category); category ∈ base/build/peak/taper/camp/transition."""
    from .plan import CAMP_START, CHARITY_DAYS, _PLAN_DAYS
    if CAMP_START <= today <= CAMP_END:
        return ("Tenerife camp (concentrated overload)", "camp")
    if CHARITY_DAYS and CHARITY_DAYS[0]["date"] - timedelta(days=14) <= today <= CHARITY_DAYS[-1]["date"]:
        return (f"{CHARITY_EVENT_NAME} taper/event window", "taper")
    delta = (today - PLAN_START).days
    if 0 <= delta < _PLAN_DAYS:
        wk = delta // 7 + 1
        if wk in (4, 8):
            return (f"12-week charity plan, week {wk}/12 (deload)", "base")
        cat = "base" if wk <= 4 else "build"
        return (f"12-week charity plan, week {wk}/12 ({cat})", cat)
    if today >= HR_PLAN_START:
        wk = (today - HR_PLAN_START).days // 7 + 1
        for ph in HR_PHASES:
            if ph["week_start"] <= wk <= ph["week_end"]:
                low = ph["label"].lower()
                cat = ("taper" if "taper" in low
                       else "peak" if "peak" in low
                       else "build" if "build" in low
                       else "base")
                return (f"Haute Route plan, week {wk}/46 — {ph['label']}", cat)
    return ("transition (between plan blocks)", "transition")


def _section_phase_nutrition(today: date) -> list[str]:
    """Current phase + 14-day energy balance, with an explicit conflict flag when a
    sustained deficit coincides with a build/peak/camp block (deficits belong in base)."""
    from .nutrition_plan import camp_nutrition_window

    label, cat = _current_training_phase(today)
    lines = ["## Training Phase & Nutrition Periodization", f"  Current phase: {label}"]
    camp = camp_nutrition_window(today)
    if camp:
        lines.append(
            f"  CAMP WINDOW ACTIVE — {camp['label']} ({camp['start'].isoformat()} → "
            f"{camp['end'].isoformat()}): suspend UK deficit; hard days "
            f"{camp['hard_day_kcal']} kcal, {camp['carbs_g_per_kg']} g/kg carbs."
        )
        cat = "camp"
    try:
        rows = raw_history(14)
        tdee_by: dict[str, Any] = {}
        for t in tdee_history(14):
            d = t["date"]
            tdee_by[d.isoformat() if hasattr(d, "isoformat") else str(d)] = t.get("tdee")
        deltas = []
        for r in rows:
            c = r.get("calories_consumed")
            di = r["date"].isoformat() if hasattr(r["date"], "isoformat") else str(r["date"])
            t = tdee_by.get(di)
            if c is not None and t:
                deltas.append(c - t)
        if deltas:
            avg_bal = sum(deltas) / len(deltas)
            lines.append(f"  14d avg energy balance: {avg_bal:+.0f} kcal/day ({len(deltas)} logged days)")
            if avg_bal <= -300 and cat in ("build", "peak", "camp"):
                lines.append(
                    "  ⚠ CONFLICT: sustained deficit during a build/peak/camp block — calorie cuts and "
                    "peak adaptation pull against each other at 50+. Steer toward maintenance for this "
                    "block; place the deficit in base weeks."
                )
            elif avg_bal <= -300 and cat == "taper":
                lines.append("  ⚠ Deficit during taper/event window — fuel the event; do not cut into it.")
            elif avg_bal <= -300:
                lines.append(
                    "  Deficit is appropriately placed (base/transition) — protect the protein floor "
                    "and watch the muscle-mass rolling average."
                )
    except Exception:
        pass
    return lines


def _section_athlete_goals() -> list[str]:
    return [
        "## Athlete Goals",
        f"  Primary A-event: {charity_event_summary()}",
        f"  Secondary A-event: {HR_EVENT_NAME} (23–29 Aug 2027)",
    ]


def build_advice_context(target: date, timing: Optional[dict[str, Any]] = None) -> str:
    """Focused context for daily readiness advice (today's decision)."""
    timing = timing or build_advice_timing(target)
    m, _, _, traffic_light, modulation, today_pmc = _load_day_state(target)
    session = timing.get("session")
    session_type = session[0] if session else None

    parts: list[str] = [
        "",
        "## Coaching Context",
        *_section_athlete_goals(),
        "",
        *_section_timing(timing, target),
        "",
        *_section_pmc(today_pmc, m),
        "",
        *_section_traffic_light(traffic_light, modulation),
        "",
        *(_section_canonical_baselines(target, m) or []),
        "",
        *_section_alerts(target),
        "",
        *_section_today_session(target, timing),
        "",
        *_section_week_ahead(target),
        "",
        *_section_recent_activities(days=7, limit=5),
    ]
    mem = _section_coach_memory()
    if mem:
        parts += ["", *mem]
    power_prof = _section_power_profile()
    if power_prof:
        parts += ["", *power_prof]
    ftp = _section_ftp(limit=1)
    if ftp:
        parts += ["", *ftp]
    hr = _section_hr_profile(m.resting_hr)
    if hr:
        parts += ["", *hr]
    rag = _section_rag(session_type, limit=2)
    if rag:
        parts += ["", *rag]
    # Share the same 2012 Haute Route lessons the chat coach gets, so daily advice
    # is anchored to what actually went wrong last time.
    try:
        parts += ["", *hr_2012_lessons_context()]
    except Exception:
        pass
    parts += ["", ATHLETE_CONSTRAINTS]
    return "\n".join(parts)


def _apply_overrides_to_weeks(weeks: list[dict]) -> list[dict]:
    overrides = {o["date"]: o for o in list_plan_overrides()}
    if not overrides:
        return weeks
    for week in weeks:
        for day in week["days"]:
            key = day["date"].isoformat()
            if key not in overrides:
                continue
            ov = overrides[key]
            day["dur_min"] = ov["duration_min"]
            if ov.get("session_type"):
                day["type"] = ov["session_type"]
            if ov.get("label"):
                day["label"] = ov["label"]
    return weeks


def _plan_completion_stats() -> dict:
    from .server.context import _plan_completion_stats as _stats
    return _stats()


def _interference_flags(days: int = 14) -> list[str]:
    """Upcoming quality-bike days with strength logged in the prior 24h.

    Same condition the Calendar tab flags inline (see `calendar_view`), surfaced
    forward-looking for the coach so it can warn before the clash happens.
    """
    today = date.today()
    _STRENGTH_KEYS = {"strength_training", "stair_climbing"}
    acts_by_date = load_activities_by_date(today - timedelta(days=1), today + timedelta(days=days))
    flagged: list[str] = []
    for i in range(days):
        d = today + timedelta(days=i)
        sess = session_for_date(d)
        if not sess or sess[1] not in QUALITY_BIKE_LABELS:
            continue
        nearby = (acts_by_date.get((d - timedelta(days=1)).isoformat(), [])
                  + acts_by_date.get(d.isoformat(), []))
        if any(a.get("type_key") in _STRENGTH_KEYS for a in nearby):
            flagged.append(f"  {d.strftime('%a %d %b')}: {sess[1]} — strength logged within prior 24h")
    return [f"## Training Interference Flags (next {days} days)", *flagged] if flagged else []


def build_coach_context() -> str:
    today = date.today()
    history = pmc_history(days=7)
    today_pmc = history[-1] if history else {}
    m = load(today) or DailyMetrics(date=today)
    stats = baseline_stats(today)
    comp_z = composite_score(m, stats)
    from .modulation import resolve_modulation
    traffic_light, modulation = resolve_modulation(today, m, comp_z)

    # Show all remaining sessions across the full plan + Tenerife camp + event prep.
    upcoming_lines = []
    next_session_type: Optional[str] = None  # first upcoming non-rest session — drives RAG

    # 12-week training plan sessions
    for i in range(90):
        d = today + timedelta(days=i)
        sess = session_for_date(d)
        if sess is None:
            break
        stype, label, dur = sess
        if stype == "rest":
            continue
        if next_session_type is None:
            next_session_type = stype
        ov = get_plan_override(d.isoformat())
        if ov:
            dur = ov["duration_min"]
            label = f"{label} [MODIFIED]"
        upcoming_lines.append(f"  {d.strftime('%a %d %b')} ({d.isoformat()}): {label} ({dur}min) [{stype}]")

    # Camp grid workouts (Aug 10–11, Aug 28–30 — pre/post Tenerife buffer days)
    for camp_date, s in sorted(CAMP_GRID_WORKOUTS.items()):
        if camp_date >= today:
            upcoming_lines.append(
                f"  {camp_date.strftime('%a %d %b')} ({camp_date.isoformat()}): "
                f"{s['label']} ({s['dur_min']}min) [{s['type']}]"
            )

    # Tenerife cycling camp (Aug 13–27)
    if today <= CAMP_END:
        upcoming_lines.append("  --- Tenerife Cycling Camp (13–27 Aug) ---")
        for day in TENERIFE_DAYS:
            d = day["date"]
            if d >= today:
                km = day.get("km", 0)
                elev = day.get("elev_m", 0)
                detail = f"{km}km, {elev}m elev" if km else "travel/rest"
                upcoming_lines.append(
                    f"  {d.strftime('%a %d %b')} ({d.isoformat()}): "
                    f"{day['label']} — {detail} [{day['intensity']}]"
                )

    # Event prep days (Aug 31 – Sep 6)
    event_prep_future = [ep for ep in EVENT_PREP_DAYS if ep["date"] >= today]
    if event_prep_future:
        upcoming_lines.append(f"  --- Event Prep ({CHARITY_EVENT_NAME}, 13–14 Sep 2026) ---")
        for ep in event_prep_future:
            upcoming_lines.append(
                f"  {ep['date'].strftime('%a %d %b')} ({ep['date'].isoformat()}): "
                f"{ep['label']} ({ep['dur_min']}min) [{ep['type']}]"
            )

    # Haute Route 46-week plan (Oct 2026 – Aug 2027): show next 8 weeks of sessions
    from .hr_plan import HR_PLAN_START as _HR_START, hr_session_for_date as _hr_sess
    if today >= _HR_START or (_HR_START - today).days <= 56:
        hr_upcoming: list[str] = []
        for i in range(56):
            d = today + timedelta(days=i)
            sess = _hr_sess(d)
            if sess is None:
                continue
            stype, label, dur = sess
            if stype == "rest":
                continue
            hr_upcoming.append(
                f"  {d.strftime('%a %d %b')} ({d.isoformat()}): {label} ({dur}min) [{stype}]"
            )
        if hr_upcoming:
            upcoming_lines.append("  --- Haute Route 2027 Plan (next 8 weeks) ---")
            upcoming_lines.extend(hr_upcoming)

    recent_acts = load_recent_activities(days=14)
    act_lines = []
    for a in recent_acts[:12]:
        dur_min = int((a.get("duration_seconds") or 0) / 60)
        parts = [f"{a['date']}: {a.get('name') or a.get('type_key')} — {dur_min}min"]
        if a.get("avg_hr"):
            parts.append(f"avg HR {int(a['avg_hr'])}bpm")
        if a.get("aerobic_te") is not None:
            te_label = (a.get("training_effect_label") or "").replace("_", " ").title()
            parts.append(f"TE {a['aerobic_te']:.1f} {te_label}".strip())
        if a.get("training_load") is not None:
            parts.append(f"load {int(a['training_load'])}")
        z45 = int(((a.get("hr_zone_4_sec") or 0) + (a.get("hr_zone_5_sec") or 0)) / 60)
        if z45 > 0:
            parts.append(f"Z4+5 {z45}min")
        np_w = a.get("norm_power_w")
        avg_w = a.get("avg_power_w")
        if np_w:
            parts.append(f"NP {int(np_w)}W")
        elif avg_w:
            parts.append(f"avg {int(avg_w)}W")
        if a.get("tss") is not None:
            parts.append(f"TSS {a['tss']:.0f}" if isinstance(a["tss"], float) else f"TSS {a['tss']}")
        if a.get("intensity_factor") is not None:
            parts.append(f"IF {a['intensity_factor']:.2f}")
        act_lines.append("  " + ", ".join(parts))

    overrides = list_plan_overrides()
    ov_lines = [f"  {o['date']}: {o['label']} → {o['duration_min']}min ({o['note']})" for o in overrides]

    # Body composition context
    body_rows = load_body_metrics(days=180)
    body_parts: list[str] = []
    if body_rows:
        latest_b = body_rows[-1]
        def _bf(v, dp=1): return f"{v:.{dp}f}" if v is not None else "—"
        body_parts += [
            "## Body Composition (latest reading)",
            f"Weight: {_bf(latest_b.get('weight_kg'))} kg  |  "
            f"Body fat: {_bf(latest_b.get('fat_pct'))}%  |  "
            f"Muscle mass: {_bf(latest_b.get('muscle_mass_kg'))} kg",
            f"Visceral fat: {_bf(latest_b.get('visceral_fat'), 0)}  |  "
            f"Body water (bioimpedance TBW): {_bf(latest_b.get('hydration_pct'))}%  |  "
            f"BMI: {_bf(latest_b.get('bmi'))}  |  "
            f"Metabolic age: {_bf(latest_b.get('metabolic_age'), 0)}",
            "Note: Body water % is scale bioimpedance, NOT fluid intake "
            "(typical adult male ~50–65%). Do not advise drinking more from this number alone.",
        ]
        # Weight trend: first vs last reading
        weight_rows = [r for r in body_rows if r.get("weight_kg") is not None]
        if len(weight_rows) >= 2:
            first_w, last_w = weight_rows[0]["weight_kg"], weight_rows[-1]["weight_kg"]
            n_weeks = max(1, (len(weight_rows)) / 7)
            rate = (last_w - first_w) / n_weeks
            from datetime import date as _date
            weeks_to_tenerife = max(0, (_date(2026, 8, 13) - today).days // 7)
            projected = last_w + rate * weeks_to_tenerife
            body_parts += [
                f"Trend: {first_w:.1f} kg ({weight_rows[0]['date']}) → {last_w:.1f} kg ({weight_rows[-1]['date']}) "
                f"= {rate:+.2f} kg/week",
                f"Projected weight at Tenerife (13 Aug, {weeks_to_tenerife} weeks): {projected:.1f} kg",
            ]
        # Fluid intake from Garmin hydration log
        history_14 = raw_history(14)
        intake_rows = [r for r in history_14 if r.get("water_intake_ml") is not None]
        if intake_rows:
            today_iso = today.isoformat()
            today_intake = next(
                (r for r in reversed(history_14)
                 if (r["date"].isoformat() if hasattr(r["date"], "isoformat") else str(r["date"])) == today_iso
                 and r.get("water_intake_ml") is not None),
                None,
            )
            src = today_intake or intake_rows[-1]
            avg_ml = sum(r["water_intake_ml"] for r in intake_rows) / len(intake_rows)
            fluid_line = f"Today: {src['water_intake_ml'] / 1000:.1f} L"
            if src.get("water_goal_ml"):
                fluid_line += f" (goal {src['water_goal_ml'] / 1000:.1f} L)"
            fluid_line += f"  |  14-day avg (logged days): {avg_ml / 1000:.1f} L"
            body_parts += [
                "## Fluid Intake (Garmin hydration log)",
                fluid_line,
                "Use this for fluid advice — not body-water %.",
            ]
        # Calorie intake from Garmin food log
        # TDEE = Katch-McArdle BMR (body comp) + measured active calories, per day.
        _tdee_by_date = {}
        try:
            for _t in tdee_history(14):
                _d = _t["date"]
                _di = _d.isoformat() if hasattr(_d, "isoformat") else str(_d)
                _tdee_by_date[_di] = _t.get("tdee")
        except Exception:
            pass

        def _row_iso(r):
            _d = r["date"]
            return _d.isoformat() if hasattr(_d, "isoformat") else str(_d)

        con_vals = [r.get("calories_consumed") for r in history_14 if r.get("calories_consumed") is not None]
        adj_vals = [
            _tdee_by_date.get(_row_iso(r))
            for r in history_14
            if r.get("calories_consumed") is not None and _tdee_by_date.get(_row_iso(r)) is not None
        ]
        if con_vals:
            avg_consumed = round(sum(con_vals) / len(con_vals))
            avg_tdee     = round(sum(adj_vals) / len(adj_vals)) if adj_vals else None
            body_parts += ["## Calorie & Macro Intake (Garmin food log)"]
            body_parts.append(f"Avg consumed (last {len(con_vals)} days): {avg_consumed:,} kcal/day")
            if avg_tdee:
                deficit = avg_tdee - avg_consumed
                body_parts.append(f"Avg TDEE: {avg_tdee:,} kcal  |  Avg deficit: {deficit:+,} kcal/day")
                try:
                    _cal = tdee_calibration()
                    if _cal:
                        body_parts.append(
                            f"TDEE calibrated {_cal['correction']:+,} kcal/day vs "
                            f"Katch-McArdle+Garmin model (28-day weight trend)"
                        )
                except Exception:
                    pass
            carbs_vals   = [r["carbs_consumed"]   for r in history_14 if r.get("carbs_consumed")   is not None]
            protein_vals = [r["protein_consumed"] for r in history_14 if r.get("protein_consumed") is not None]
            if carbs_vals:
                avg_c = round(sum(carbs_vals) / len(carbs_vals))
                avg_p = round(sum(protein_vals) / len(protein_vals)) if protein_vals else None
                macro_line = f"Avg carbs: {avg_c}g/day"
                if avg_p:
                    macro_line += f"  |  Avg protein: {avg_p}g/day"
                body_parts.append(macro_line)
            # Today's macros (calendar today — not the most recent logged day)
            from .history import metrics_row_for_date
            today_nut_c = metrics_row_for_date(history_14, today)
            if today_nut_c and today_nut_c.get("calories_consumed") is not None:
                today_c = int(today_nut_c["calories_consumed"])
                today_carbs_c = round(today_nut_c["carbs_consumed"]) if today_nut_c.get("carbs_consumed") is not None else None
                today_prot_c  = round(today_nut_c["protein_consumed"]) if today_nut_c.get("protein_consumed") is not None else None
                _tt = _tdee_by_date.get(today.isoformat())
                today_tdee_c  = int(round(_tt)) if _tt else None
                parts = [f"Today logged: {today_c:,} kcal"]
                if today_tdee_c:
                    parts.append(f"TDEE {today_tdee_c:,} ({today_tdee_c - today_c:+,})")
                if today_carbs_c is not None:
                    parts.append(f"carbs {today_carbs_c}g")
                if today_prot_c is not None:
                    parts.append(f"protein {today_prot_c}g")
                try:
                    from .energy import ride_kj, ride_kcal_from_kj
                    today_acts = load_recent_activities(1)
                    kj_total = 0.0
                    for act in today_acts:
                        if act.get("date") != today.isoformat():
                            continue
                        pwr = act.get("norm_power_w") or act.get("avg_power_w")
                        secs = act.get("duration_seconds") or 0
                        if pwr and secs and act.get("has_power_meter"):
                            kj_total += ride_kj(float(pwr), float(secs))
                    if kj_total > 0:
                        parts.append(
                            f"ride work {round(kj_total)} kJ (~{ride_kcal_from_kj(kj_total)} kcal mechanical)"
                        )
                except Exception:
                    pass
                body_parts.append("  |  ".join(parts))

        # Inject cached AI advisor text if available
        cached_body = get_cached_text(f"body_analysis_v2_{today.isoformat()}")
        if cached_body:
            body_parts += ["", "Coach's body composition analysis (from Body tab):", cached_body]
        body_parts.append("")

    # Recent RPE logs
    rpe_rows = load_session_rpe(7)
    rpe_parts: list[str] = []
    if rpe_rows:
        rpe_parts = ["## Recent RPE Logs (last 7 days)"]
        for r in rpe_rows:
            rpe_str = f"RPE {r['rpe']}/5"
            note_str = f" — {r['note']}" if r.get("note") else ""
            rpe_parts.append(f"  {r['date']}: {rpe_str}{note_str}")

    # Fuelling compliance logs
    fuel_parts: list[str] = []
    try:
        fuel_rows = load_fuelling_logs(90)
        if fuel_rows:
            fuel_parts = ["## Fuelling Compliance (recent logged rides)"]
            for r in fuel_rows[:5]:
                planned = f"planned {r['planned_carbs_g_per_hr']:.0f}g/h" if r.get("planned_carbs_g_per_hr") else "no plan"
                actual = f"actual {r['actual_carbs_g_per_hr']:.0f}g/h" if r.get("actual_carbs_g_per_hr") is not None else "actual not given"
                fluid = "fluid ok" if r.get("fluid_ok") else "fluid short"
                note_str = f" — {r['note']}" if r.get("note") else ""
                fuel_parts.append(f"  {r['date']}: {planned} → {actual}, {fluid}{note_str}")
    except Exception:
        pass

    # Back-to-back training history
    btb_rows = load_btb_summary()
    btb_parts: list[str] = []
    if btb_rows:
        btb_parts = ["## Back-to-Back Training History (most recent pairs)"]
        for pair in btb_rows[:5]:
            hr1 = f"avg HR {pair['avg_hr_1']}bpm" if pair.get("avg_hr_1") else ""
            hr2 = f"avg HR {pair['avg_hr_2']}bpm" if pair.get("avg_hr_2") else ""
            fat1 = f"fatigue {pair['fatigue_rating_1']}/5" if pair.get("fatigue_rating_1") else ""
            fat2 = f"fatigue {pair['fatigue_rating_2']}/5" if pair.get("fatigue_rating_2") else ""
            d1_parts = ", ".join(filter(None, [hr1, fat1]))
            d2_parts = ", ".join(filter(None, [hr2, fat2]))
            btb_parts.append(
                f"  Day 1: {pair['date1']} ({d1_parts or 'no data'})  →  "
                f"Day 2: {pair['date2']} ({d2_parts or 'no data'})"
            )

    # Sleep history (7-day pattern with stage breakdown)
    sleep_history_rows = raw_history(8)
    sleep_parts: list[str] = []
    sleep_hist_lines: list[str] = []
    for r in sleep_history_rows:
        if r.get("sleep_score") is None:
            continue
        score = int(r["sleep_score"])
        total_h = round((r.get("sleep_seconds") or 0) / 3600, 1)
        deep_m  = int((r.get("deep_sleep_seconds")  or 0) / 60)
        rem_m   = int((r.get("rem_sleep_seconds")   or 0) / 60)
        light_m = int((r.get("light_sleep_seconds") or 0) / 60)
        stage_str = f"deep {deep_m}m / REM {rem_m}m / light {light_m}m" if deep_m or rem_m else ""
        line = f"  {r['date']}: score {score}  {total_h}h total"
        if stage_str:
            line += f"  ({stage_str})"
        sleep_hist_lines.append(line)
    if sleep_hist_lines:
        sleep_parts = ["## Sleep History (last 7 days)", *sleep_hist_lines]

    # Fatigue alerts
    alert_parts: list[str] = []
    try:
        alerts = check_fatigue_alerts(today)
        if alerts:
            alert_parts = ["## Active Fatigue Alerts"]
            for a in alerts:
                alert_parts.append(f"  [{a['severity']}] {a['type']}: {a['message']}")
    except Exception:
        pass

    # HRV traffic light + modulation
    tl_parts: list[str] = []
    tl_status = traffic_light.get("status", "unknown")
    tl_reason = traffic_light.get("reason", "")
    hrv_z_str = f"z={traffic_light['hrv_z']:+.2f}" if traffic_light.get("hrv_z") is not None else ""
    tl_parts = [
        "## HRV Traffic Light",
        f"  Status: {tl_status.upper()}  {hrv_z_str}  — {tl_reason}",
    ]
    if modulation and modulation.get("label"):
        gate_tag = "Recovery gate" if modulation.get("gate") else "HRV modulation"
        tl_parts.append(
            f"  Suggested swap ({gate_tag}): {modulation['planned_label']} → {modulation['label']} "
            f"({modulation['duration_min']}min) — {modulation.get('headline', '')}"
        )
    elif modulation and modulation.get("gate"):
        tl_parts.append(f"  Recovery gate: {modulation.get('reason', modulation.get('headline', ''))}")

    # FTP test history
    ftp_parts: list[str] = []
    ftp_rows = load_ftp_tests()
    if ftp_rows:
        ftp_title = "## FTP Test History"
        if not power_meter_active():
            ftp_title += " (LTHR)"
        ftp_parts = [ftp_title]
        for r in ftp_rows[-4:]:
            line = f"  {r['date']}: LTHR {r['ftp_hr']}bpm"
            if r.get("ftp_hr_max"):
                line += f" (max {r['ftp_hr_max']}bpm)"
            if r.get("ftp_w"):
                line += f"  |  FTP {r['ftp_w']}W"
            ftp_parts.append(line)

    hr_profile_parts = _section_hr_profile(m.resting_hr)
    power_profile_parts = _section_power_profile()

    # Durability drift (late-ride HR drift, last 5 rides ≥ 90 min)
    dur_parts: list[str] = []
    dur_rows = load_durability(90)
    if dur_rows:
        dur_parts = ["## Durability (late-ride HR drift, rides ≥ 90 min)"]
        for r in dur_rows[-5:]:
            dur_parts.append(
                f"  {r['date']}: first-third HR {r['first_third_hr']:.0f}bpm "
                f"→ final-third {r['final_third_hr']:.0f}bpm  drift {r['drift_pct']:+.1f}%"
            )

    # Foster monotony / strain (last 6 weeks)
    monotony_parts: list[str] = []
    try:
        mono_rows = weekly_monotony_strain(6)
        if mono_rows:
            monotony_parts = ["## Training Monotony & Strain (Foster, last 6 weeks)"]
            for r in mono_rows:
                mono_str = f"{r['monotony']:.2f}" if r.get("monotony") is not None else "—"
                strain_str = f"{r['strain']:.0f}" if r.get("strain") is not None else "—"
                monotony_parts.append(
                    f"  wk {r['label']}: load {r['weekly_load']:.0f}  monotony {mono_str}  strain {strain_str}"
                )
    except Exception:
        pass

    # Blood pressure (latest)
    bp_parts: list[str] = []
    bp_rows = load_blood_pressure(90)
    if bp_rows:
        bp = bp_rows[-1]
        bp_parts = [
            "## Blood Pressure (latest)",
            f"  {bp['date']}: {bp.get('systolic')}/{bp.get('diastolic')} mmHg  "
            f"pulse {bp.get('pulse')}bpm"
        ]

    # Measured / estimated W/kg
    wkg_parts: list[str] = []
    measured = latest_measured_wkg() if power_meter_active() else None
    if measured:
        wkg_parts = [
            "## Measured FTP / W/kg (from FTP test)",
            f"  {measured['date']}: FTP {measured['ftp_w']}W  {measured['wkg']:.2f} W/kg  "
            f"(weight {measured['weight_kg']:.1f} kg)",
        ]
    wkg = latest_estimated_wkg()
    if wkg:
        est_title = "## Estimated FTP / W/kg (ACSM formula"
        est_title += ", secondary cross-check)" if measured else ", no power meter)"
        wkg_parts += [
            est_title,
            f"  {wkg['date']}: VO2max {wkg['vo2_max']} ml/kg/min  "
            f"est. FTP {wkg['est_ftp_w']:.0f}W  {wkg['wkg']:.2f} W/kg  "
            f"(weight {wkg['weight_kg']:.1f} kg)",
        ]

    # Power meter summary (polarisation + decoupling)
    power_parts: list[str] = []
    if power_meter_active():
        try:
            pzd = intensity_distribution_by_week_power(today - timedelta(days=28), today)
            if pzd:
                power_parts = ["## Power Zone Distribution (cycling, recent weeks)"]
                for w in pzd[-4:]:
                    power_parts.append(
                        f"  {w['week_label']}: Z1 {w['z1_pct']}%  Z2 {w['z2_pct']}%  "
                        f"Z3 {w['z3_pct']}%  Z4 {w['z4_pct']}%  Z5 {w['z5_pct']}%  "
                        f"({w['total_min']}min, {w['activity_count']} rides)"
                    )
        except Exception:
            pass
        try:
            pdec_rows = load_power_durability(90)
            if pdec_rows:
                power_parts += ["## Pw:HR Decoupling (last 3 rides ≥ 90 min)"]
                for r in pdec_rows[-3:]:
                    power_parts.append(
                        f"  {r['date']}: decoupling {r['decoupling_pct']:+.1f}%  "
                        f"(HR drift {r['hr_drift_pct']:+.1f}%, power drift {r['power_drift_pct']:+.1f}%)"
                    )
        except Exception:
            pass

    # Plan compliance summary (full block: 12-week plan + camp + event prep)
    compliance_parts: list[str] = []
    try:
        comp_stats = _plan_completion_stats()
        total_p = comp_stats.get("total_plan_sessions", 0)
        total_d = comp_stats.get("total_done_sessions", 0)
        total_pm = comp_stats.get("total_plan_min", 0)
        total_dm = comp_stats.get("total_done_min", 0)
        if total_p:
            pct = int(total_d / total_p * 100)
            compliance_parts = [
                "## Plan Compliance (12-week plan + Tenerife camp + event prep, elapsed weeks)",
                f"  Sessions: {total_d}/{total_p} ({pct}%)  |  "
                f"Volume: {total_dm//60}h{total_dm%60:02d}m of {total_pm//60}h{total_pm%60:02d}m planned",
            ]
            recent_weeks = [w for w in comp_stats.get("completion_weeks", [])
                            if w["status"] in ("past", "current")][-4:]
            if recent_weeks:
                compliance_parts.append("  Recent weeks:")
                for w in recent_weeks:
                    wk_lbl = w.get("week_label") or f"Wk{w['week_num']:02d}"
                    compliance_parts.append(
                        f"    {wk_lbl} ({w['date_range']}): "
                        f"{w['done_sessions']}/{w['plan_sessions']} sessions, {w['pct']}% volume"
                    )
                missed = [f"{d['date'].isoformat()} ({d['type']})"
                          for w in recent_weeks for d in w["days"] if d["status"] == "missed"]
                if missed:
                    compliance_parts.append("  Recently missed: " + ", ".join(missed[-6:]))
    except Exception:
        pass

    # Sleep trend (30-day averages) — complements the 7-day detail above
    sleep_trend_parts: list[str] = []
    try:
        sh = sleep_history(30)
        scored = [r for r in sh if r.get("sleep_score") is not None]
        def _savg(rows, key):
            vals = [r[key] for r in rows if r.get(key) is not None]
            return round(sum(vals) / len(vals), 1) if vals else None
        if scored:
            last7 = scored[-7:]
            sleep_trend_parts = [
                "## Sleep Trend (30-day)",
                f"  Score: 7d avg {_savg(last7, 'sleep_score')}  |  30d avg {_savg(scored, 'sleep_score')}",
                f"  Duration: 7d avg {_savg(last7, 'sleep_hours')}h  |  30d avg {_savg(scored, 'sleep_hours')}h",
                f"  Stage mix (30d avg): deep {_savg(scored, 'deep_pct')}%  REM {_savg(scored, 'rem_pct')}%",
            ]
            cached_sleep = get_cached_text(f"sleep_analysis_v1_{today.isoformat()}")
            if cached_sleep:
                sleep_trend_parts += ["  Coach's sleep analysis (from Sleep tab):",
                                      "  " + cached_sleep.replace("\n", "\n  ")]
    except Exception:
        pass

    # Heat / altitude acclimation
    accl_parts: list[str] = []
    try:
        accl = acclimation_latest()
        if accl:
            bits = []
            if accl.get("heat_acclimation_pct") is not None:
                bits.append(f"heat {accl['heat_acclimation_pct']}%")
            if accl.get("altitude_acclimation") is not None:
                bits.append(f"altitude {accl['altitude_acclimation']}")
            if bits:
                accl_parts = ["## Heat / Altitude Acclimation",
                              f"  {accl.get('date')}: " + ", ".join(bits)]
    except Exception:
        pass

    # Zone distribution (recent weeks) — polarisation check
    zone_parts: list[str] = []
    try:
        zd = intensity_distribution_by_week(today - timedelta(days=28), today)
        if zd:
            zone_parts = ["## Zone Distribution (cycling, recent weeks)"]
            for w in zd[-4:]:
                zone_parts.append(
                    f"  {w['week_label']}: Z1 {w['z1_pct']}%  Z2 {w['z2_pct']}%  "
                    f"Z3 {w['z3_pct']}%  Z4 {w['z4_pct']}%  Z5 {w['z5_pct']}%  "
                    f"({w['total_min']}min, {w['activity_count']} rides)"
                )
    except Exception:
        pass

    # Haute Route phase overview
    hr_phase_parts: list[str] = []
    try:
        cur_hr_week = (today - HR_PLAN_START).days // 7 + 1 if today >= HR_PLAN_START else None
        hr_phase_parts = [f"## Haute Route 2027 — Plan Phases (46 weeks, starts {HR_PLAN_START.isoformat()})"]
        for ph in HR_PHASES:
            marker = (f"  ← current (wk {cur_hr_week})"
                      if cur_hr_week and ph["week_start"] <= cur_hr_week <= ph["week_end"] else "")
            hr_phase_parts.append(f"  {ph['label']}: weeks {ph['week_start']}–{ph['week_end']}{marker}")
        hr_phase_parts.append(
            "  Camps: Christmas Tenerife volume (wks 12–13, bike 23–31 Dec 2026); "
            "May Tenerife race-sim (wk 31)."
        )
        hr_phase_parts.append("  Full week-by-week sessions available via the get_hr_plan tool.")
        hr_phase_parts.append("")
        hr_phase_parts += hr_2012_lessons_context()
    except Exception:
        pass

    # Training interference flags (next 14 days)
    interference_parts = _interference_flags(14)

    # Nutrition plan — simple rules + today's meals + week overview
    from .nutrition_plan import (
        SIMPLE_RULES, today_checklist, nutrition_coach_context, nutrition_week_context,
    )
    simple_rules_lines = ["## Nutrition — Follow This (simple rules)"] + [
        f"  • {r}" for r in SIMPLE_RULES
    ]
    checklist_lines = ["## Today's Nutrition Checklist"] + [
        f"  • {item}" for item in today_checklist(PLAN_START, today)
    ]
    nutrition_ctx = nutrition_coach_context(PLAN_START, today)
    nutrition_week_ctx = nutrition_week_context(PLAN_START, today)

    key_dates_parts = _section_key_dates(today)
    baseline_parts = _section_canonical_baselines(today, m)
    commitment_parts = _section_commitments(today)
    session_note_parts = _section_session_notes(today)
    phase_nutrition_parts = _section_phase_nutrition(today)
    morning_gate_parts = _section_morning_gate(today)
    power_pmc_parts = _section_power_pmc()
    weekly_briefing_parts = _section_weekly_briefing(today)
    session_rx_parts = _section_today_session_prescriptions(today)
    recent_analysis_parts = _section_recent_analyses(recent_acts)
    ftp_flag_parts = _section_ftp_flags(today)

    parts = [
        f"Today: {today.strftime('%A %d %B %Y')}",
        "",
        *key_dates_parts,
        "",
        *([*commitment_parts, ""] if commitment_parts else []),
        *([*session_note_parts, ""] if session_note_parts else []),
        *_section_pmc(today_pmc, m),
        *(["", *power_pmc_parts] if power_pmc_parts else []),
        "",
        *_section_today_readiness(m, comp_z),
        *tl_parts,
        *(["", *morning_gate_parts] if morning_gate_parts else []),
        "",
        *([*baseline_parts, ""] if baseline_parts else []),
        *([*weekly_briefing_parts, ""] if weekly_briefing_parts else []),
        *([*session_rx_parts, ""] if session_rx_parts else []),
        *([*ftp_flag_parts, ""] if ftp_flag_parts else []),
        *([*phase_nutrition_parts, ""] if phase_nutrition_parts else []),
        *([*alert_parts, ""] if alert_parts else []),
        *([*interference_parts, ""] if interference_parts else []),
        *([*sleep_parts, ""] if sleep_parts else []),
        *([*sleep_trend_parts, ""] if sleep_trend_parts else []),
        *body_parts,
        *([*bp_parts, ""] if bp_parts else []),
        *([*wkg_parts, ""] if wkg_parts else []),
        *([*power_parts, ""] if power_parts else []),
        *([*accl_parts, ""] if accl_parts else []),
        *([*power_profile_parts, ""] if power_profile_parts else []),
        *([*ftp_parts, ""] if ftp_parts else []),
        *([*hr_profile_parts, ""] if hr_profile_parts else []),
        *([*dur_parts, ""] if dur_parts else []),
        *([*monotony_parts, ""] if monotony_parts else []),
        *([*zone_parts, ""] if zone_parts else []),
        *([*compliance_parts, ""] if compliance_parts else []),
        *simple_rules_lines,
        "",
        *checklist_lines,
        "",
        nutrition_ctx,
        "",
        nutrition_week_ctx,
        "",
        *([*hr_phase_parts, ""] if hr_phase_parts else []),
        "## Upcoming Plan Sessions (full remaining plan)",
        *upcoming_lines,
        "",
        "## Recent Activities (last 14 days)",
        *(act_lines or ["  None recorded"]),
        *([" ", *recent_analysis_parts] if recent_analysis_parts else []),
        *([" ", *rpe_parts] if rpe_parts else []),
        *([" ", *fuel_parts] if fuel_parts else []),
        *([" ", *btb_parts] if btb_parts else []),
    ]
    if ov_lines:
        parts += ["", "## Active Plan Overrides", *ov_lines]

    memo = get_coach_memory()
    if memo:
        parts += ["", "## Coach Memory (cross-session context)", memo["memo"]]

    # Ground the coach in the athlete's own past sessions in the same discipline as the next
    # one up. NB: retrieval is by discipline (cycling/strength/rucking), not workout sub-type —
    # bike/tempo/ftp/long all map to the same cycling activities, so don't imply sub-type match.
    if next_session_type:
        _DISCIPLINE = {
            "bike": "cycling", "tempo": "cycling", "ftp": "cycling", "long": "cycling",
            "strength": "strength", "ruck": "rucking / load-carry",
        }
        discipline = _DISCIPLINE.get(next_session_type, next_session_type)
        past = retrieve_relevant_analyses(next_session_type, limit=3)
        if past:
            rag_lines = [
                "", f"## Relevant Past Sessions (your recent {discipline} sessions)",
                f"These are your most recent {discipline} sessions — NOT necessarily the same "
                "workout type as the one coming up. Reference them for context and cite specific "
                "dates/numbers, but do not claim they were the same session type.",
            ]
            for p in past:
                hdr = f"  {p['date']} — {p.get('name') or p.get('type_key')}"
                stats = []
                if p.get("avg_hr"):
                    stats.append(f"avg HR {int(p['avg_hr'])}")
                if p.get("training_effect") is not None:
                    stats.append(f"TE {p['training_effect']:.1f} {_te_clean(p.get('training_effect_label'))}".strip())
                if p.get("training_load") is not None:
                    stats.append(f"load {int(p['training_load'])}")
                if p.get("z45_min"):
                    stats.append(f"Z4+5 {p['z45_min']}min")
                if stats:
                    hdr += " (" + ", ".join(stats) + ")"
                rag_lines.append(hdr)
                if p.get("summary"):
                    rag_lines.append(f"    {p['summary']}")
            parts += rag_lines

    return "\n".join(parts)



# Alias for tests / backward compatibility
_build_coach_context = build_coach_context

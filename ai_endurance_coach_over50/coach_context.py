"""Shared coaching context for daily advice and coach chat."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .alerts import check_fatigue_alerts
from .analysis import retrieve_relevant_analyses
from .hr_profile import format_hr_profile_lines
from .history import (
    ACTIVITY_MATCH,
    acclimation_latest,
    baseline_stats,
    composite_score,
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
    load_body_metrics,
    load_blood_pressure,
    load_btb_summary,
    load_durability,
    load_ftp_tests,
    load_fuelling_logs,
    load_power_durability,
    load_recent_activities,
    load_session_rpe,
    pmc_history,
    power_meter_active,
    raw_history,
    sleep_history,
    tdee_history,
    weekly_monotony_strain,
)
from .hr_plan import HR_PHASES, HR_PLAN_START, hr_session_for_date, hr_2012_lessons_context
from .metrics import DailyMetrics
from .plan import (
    PLAN_START,
    build_calendar_weeks,
    CAMP_END,
    CAMP_GRID_WORKOUTS,
    EVENT_PREP_DAYS,
    TENERIFE_DAYS,
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

ATHLETE_CONSTRAINTS = (
    "Athlete constraints (NEVER violate): preparing for a charity cycling event; "
    "programme is cycling, kettlebells, MaxiClimber, and rucking ONLY. "
    "NO RUNNING — running causes injury and is excluded entirely. "
    "Never suggest running, jogging, or trail running as training or as a workout modification. "
    "When modifying a session, swap within the same discipline (e.g. hard bike -> easy bike)."
)

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


def coach_persona_brief(has_power: bool) -> str:
    base = (
        "You are an experienced endurance coach for an amateur athlete preparing for "
        "a 2-day charity cycling event (Ghent to Amsterdam, ~310 km, 13–14 Sep 2026). "
        "The athlete is 50+, training on cycling, kettlebells, MaxiClimber, and rucking only. "
        + ATHLETE_CONSTRAINTS + " "
        "Give a concise train/rest/modify-today recommendation for the morning email dashboard. "
        "Reference actual numbers from the context. Never be vague."
    )
    if has_power:
        return base + (
            " The athlete has a power meter — use watts for interval cues when relevant; "
            "keep HR primary for readiness."
        )
    return base + (
        " The athlete trains on heart rate (no power meter) — cue intensity in HR zones / RPE, never watts."
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


def _section_pmc(today_pmc: dict, m: Optional["DailyMetrics"] = None) -> list[str]:
    lines = [
        "## Training Load (PMC)  (Garmin training-load units, NOT Coggan TSS — absolute values not comparable to standard thresholds)",
        f"CTL (fitness): {today_pmc.get('ctl')}  |  ATL (fatigue): {today_pmc.get('atl')}  |  TSB (form): {today_pmc.get('tsb')}",
    ]
    acwr_line = _acwr_line(m)
    if acwr_line:
        lines.append(acwr_line)
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


def _section_today_session(target: date) -> list[str]:
    session = session_for_date_extended(target)
    if not session:
        return ["## Today's Planned Workout", "  Not in plan period"]
    stype, label, dur = session
    ov = get_plan_override(target.isoformat())
    if ov:
        stype = ov.get("session_type") or stype
        label = ov.get("label") or label
        dur = ov["duration_min"]
        note = f" [override: {ov.get('note', '')}]" if ov.get("note") else " [override active]"
    else:
        note = ""
    dur_str = f"{dur}m" if dur and dur < 60 else (f"{dur // 60}h{dur % 60:02d}m" if dur and dur % 60 else f"{dur // 60}h") if dur else "—"
    discipline = session_discipline(stype)
    return [
        "## Today's Planned Workout",
        f"  {label} — {discipline} ({stype}, {dur_str}){note}",
    ]


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


def _section_hr_profile(resting_hr_today: Optional[float] = None) -> list[str]:
    return format_hr_profile_lines(resting_hr_today=resting_hr_today)


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


def build_advice_context(target: date) -> str:
    """Focused context for daily readiness advice (today's decision)."""
    m, _, _, traffic_light, modulation, today_pmc = _load_day_state(target)
    session = session_for_date_extended(target)
    session_type = session[0] if session and session[0] != "rest" else None

    parts: list[str] = [
        "",
        "## Coaching Context",
        *_section_pmc(today_pmc, m),
        "",
        *_section_traffic_light(traffic_light, modulation),
        "",
        *_section_alerts(target),
        "",
        *_section_today_session(target),
        "",
        *_section_week_ahead(target),
        "",
        *_section_recent_activities(days=7, limit=5),
    ]
    mem = _section_coach_memory()
    if mem:
        parts += ["", *mem]
    ftp = _section_ftp(limit=1)
    if ftp:
        parts += ["", *ftp]
    hr = _section_hr_profile(m.resting_hr)
    if hr:
        parts += ["", *hr]
    rag = _section_rag(session_type, limit=2)
    if rag:
        parts += ["", *rag]
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
    today = date.today()
    weeks_data = _apply_overrides_to_weeks(build_calendar_weeks())
    plan_end = weeks_data[-1]["days"][-1]["date"]
    acts_by_date = load_activities_by_date(PLAN_START, min(today, plan_end))
    completion_weeks = []
    total_plan_sessions = total_done_sessions = 0
    total_plan_min = total_done_min = 0
    for week in weeks_data:
        wk_start = week["start"]
        wk_end = wk_start + timedelta(days=6)
        if wk_start.month == wk_end.month:
            date_range = f"{wk_start.day}–{wk_end.day} {wk_start.strftime('%b')}"
        else:
            date_range = f"{wk_start.strftime('%-d %b')}–{wk_end.strftime('%-d %b')}"
        plan_sessions = plan_min = done_sessions = done_min = 0
        day_statuses = []
        for day in week["days"]:
            d = day["date"]
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
            day_statuses.append({"type": stype, "date": d, "status": status, "is_today": d == today})
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
            "week_num": week["week_num"], "date_range": date_range,
            "plan_sessions": plan_sessions, "done_sessions": done_sessions,
            "plan_min": plan_min, "done_min": done_min,
            "pct": int(done_min / plan_min * 100) if plan_min else 0,
            "status": wk_status, "days": day_statuses,
        })
    return {
        "completion_weeks": completion_weeks,
        "total_plan_sessions": total_plan_sessions,
        "total_done_sessions": total_done_sessions,
        "total_plan_min": total_plan_min,
        "total_done_min": total_done_min,
        "overall_pct": int(total_done_min / total_plan_min * 100) if total_plan_min else 0,
    }


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
        upcoming_lines.append("  --- Event Prep (Ghent to Amsterdam charity ride, 13–14 Sep 2026) ---")
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
            f"Hydration: {_bf(latest_b.get('hydration_pct'))}%  |  "
            f"BMI: {_bf(latest_b.get('bmi'))}  |  "
            f"Metabolic age: {_bf(latest_b.get('metabolic_age'), 0)}",
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
        # Calorie intake from Garmin food log
        history_14 = raw_history(14)
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
            carbs_vals   = [r["carbs_consumed"]   for r in history_14 if r.get("carbs_consumed")   is not None]
            protein_vals = [r["protein_consumed"] for r in history_14 if r.get("protein_consumed") is not None]
            if carbs_vals:
                avg_c = round(sum(carbs_vals) / len(carbs_vals))
                avg_p = round(sum(protein_vals) / len(protein_vals)) if protein_vals else None
                macro_line = f"Avg carbs: {avg_c}g/day"
                if avg_p:
                    macro_line += f"  |  Avg protein: {avg_p}g/day"
                body_parts.append(macro_line)
            # Today's macros
            today_nut_c = next((r for r in reversed(history_14) if r.get("calories_consumed") is not None), None)
            if today_nut_c:
                today_c = int(today_nut_c["calories_consumed"])
                today_carbs_c = round(today_nut_c["carbs_consumed"]) if today_nut_c.get("carbs_consumed") is not None else None
                today_prot_c  = round(today_nut_c["protein_consumed"]) if today_nut_c.get("protein_consumed") is not None else None
                _tt = _tdee_by_date.get(_row_iso(today_nut_c))
                today_tdee_c  = int(round(_tt)) if _tt else None
                parts = [f"Today logged: {today_c:,} kcal"]
                if today_tdee_c:
                    parts.append(f"TDEE {today_tdee_c:,} ({today_tdee_c - today_c:+,})")
                if today_carbs_c is not None:
                    parts.append(f"carbs {today_carbs_c}g")
                if today_prot_c is not None:
                    parts.append(f"protein {today_prot_c}g")
                body_parts.append("  |  ".join(parts))

        # Inject cached AI advisor text if available
        cached_body = get_cached_text(f"body_analysis_v1_{today.isoformat()}")
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

    # Plan compliance summary (12-week plan)
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
                "## Plan Compliance (12-week plan, elapsed weeks)",
                f"  Sessions: {total_d}/{total_p} ({pct}%)  |  "
                f"Volume: {total_dm//60}h{total_dm%60:02d}m of {total_pm//60}h{total_pm%60:02d}m planned",
            ]
            recent_weeks = [w for w in comp_stats.get("completion_weeks", [])
                            if w["status"] in ("past", "current")][-4:]
            if recent_weeks:
                compliance_parts.append("  Recent weeks:")
                for w in recent_weeks:
                    compliance_parts.append(
                        f"    Wk{w['week_num']} ({w['date_range']}): "
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

    parts = [
        f"Today: {today.strftime('%A %d %B %Y')}",
        "",
        *_section_pmc(today_pmc, m),
        "",
        "## Today's Readiness",
        f"Composite z-score: {f'{comp_z:+.2f}σ' if comp_z is not None else 'n/a'}",
        f"HRV: {m.hrv_last_night}  |  Sleep score: {m.sleep_score}  |  Body battery (AM): {m.body_battery_morning}  "
        f"|  Avg stress: {m.avg_stress}  |  Resting HR: {m.resting_hr}  |  VO2max: {m.vo2_max}",
        *tl_parts,
        "",
        *([*alert_parts, ""] if alert_parts else []),
        *([*interference_parts, ""] if interference_parts else []),
        *([*sleep_parts, ""] if sleep_parts else []),
        *([*sleep_trend_parts, ""] if sleep_trend_parts else []),
        *body_parts,
        *([*bp_parts, ""] if bp_parts else []),
        *([*wkg_parts, ""] if wkg_parts else []),
        *([*power_parts, ""] if power_parts else []),
        *([*accl_parts, ""] if accl_parts else []),
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

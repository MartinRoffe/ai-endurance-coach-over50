"""AI analysis generation, refresh loop, retrieval, recovery suggestions."""
from __future__ import annotations

import os
import sqlite3
from datetime import date
from typing import Any, Optional

from ..coach_voice import COACH_VOICE
from ..history import _conn, get_cached_text, set_cached_text
from ..llm import MODEL_FAST, MODEL_SMART
from ..plan import COMPOUND_SESSIONS, session_for_date_extended
from .db import _ensure_analysis_schema, load_analysis, save_detail
from .intervals import (
    _ALL_FTP_LABELS,
    _CYCLING_TYPES,
    _extract_durability,
    _extract_power_durability,
)
from .power import _mark_workouts_stale, _session_label_for_date, fetch_activity_detail
from .prompts import (
    _activity_has_power_data,
    _build_analysis_prompt,
    _coach_system_prompt,
    _rule_based_analysis,
    _rule_based_recovery,
)


# ── Claude analysis ──────────────────────────────────────────────────────────

def generate_analysis(activity: dict, detail: dict, companion: Optional[dict] = None) -> str:
    """Call Claude Haiku to analyse the workout and return a short commentary."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return _rule_based_analysis(activity, detail)

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    prompt = _build_analysis_prompt(activity, detail, companion=companion)
    type_key = activity.get("type_key", "")
    name = activity.get("name") or ""
    has_power = _activity_has_power_data(activity, detail)
    try:
        msg = client.messages.create(
            model=MODEL_SMART,
            max_tokens=600 if has_power else 500,
            system=_coach_system_prompt(type_key, name, has_power=has_power),
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception:
        return _rule_based_analysis(activity, detail)


def _find_compound_companion(activity: dict, day_acts: list[dict]) -> Optional[dict]:
    """Return the companion activity if this is one half of a compound plan session."""
    act_date = activity.get("date", "")
    if not act_date:
        return None
    d_obj = date.fromisoformat(act_date)
    session = session_for_date_extended(d_obj)
    if not session:
        return None
    _, slabel, _ = session
    compound = COMPOUND_SESSIONS.get(slabel)
    if not compound:
        return None
    act_key = activity.get("type_key")
    if not any(s["garmin_key"] == act_key for s in compound):
        return None
    companion_key = next(s["garmin_key"] for s in compound if s["garmin_key"] != act_key)
    return next(
        (a for a in day_acts if a["activity_id"] != activity["activity_id"]
         and a["type_key"] == companion_key),
        None,
    )


# ── Main entry point used by server ─────────────────────────────────────────

def refresh_analyses(api: Any, days: int = 14) -> None:
    """Fetch detail + generate analysis for any unanalysed activities in the window."""
    from ..history import load_recent_activities
    activities = load_recent_activities(days=days)
    acts_by_date: dict[str, list[dict]] = {}
    for act in activities:
        acts_by_date.setdefault(act["date"], []).append(act)
    for act in activities:
        act_id = act["activity_id"]
        # Durability extraction is independent of the AI analysis — run it for
        # any long cycling activity not yet measured (≥90 min, lap splits only).
        try:
            from ..history import durability_exists, save_durability
            if (act.get("type_key") in _CYCLING_TYPES
                    and (act.get("duration_seconds") or 0) >= 90 * 60
                    and not durability_exists(act_id)):
                dur_row = _extract_durability(api, act)
                if dur_row:
                    save_durability(act_id, dur_row)
        except Exception:
            pass
        try:
            from ..history import power_durability_exists, save_power_durability
            if (act.get("type_key") in _CYCLING_TYPES
                    and act.get("has_power_meter")
                    and (act.get("duration_seconds") or 0) >= 90 * 60
                    and not power_durability_exists(act_id)):
                pd_row = _extract_power_durability(api, act)
                if pd_row:
                    save_power_durability(act_id, pd_row)
        except Exception:
            pass
        # Backfill ftp_tests for already-analysed FTP sessions that pre-date the auto-population logic
        existing = load_analysis(act_id)
        if existing is not None:
            try:
                act_date = act.get("date")
                if act_date:
                    session_label = _session_label_for_date(date.fromisoformat(act_date))
                    if session_label in _ALL_FTP_LABELS and (
                        existing.get("ftp_effort_avg_hr") or existing.get("ftp_w")
                    ):
                        from ..history import save_ftp_test, load_ftp_tests
                        d_obj = date.fromisoformat(act_date)
                        if not any(t["date"] == d_obj.isoformat() for t in load_ftp_tests()):
                            ftp_w = existing.get("ftp_w")
                            if not ftp_w and existing.get("ftp_effort_avg_w"):
                                ftp_w = round(existing["ftp_effort_avg_w"] * 0.95)
                            save_ftp_test(
                                d_obj.isoformat(), act_id,
                                int(existing["ftp_effort_avg_hr"]) if existing.get("ftp_effort_avg_hr") else None,
                                int(existing["ftp_effort_max_hr"]) if existing.get("ftp_effort_max_hr") else None,
                                None,
                                ftp_w=ftp_w,
                            )
                            if ftp_w:
                                _mark_workouts_stale(int(ftp_w))
            except Exception:
                pass
            continue  # already analysed — nothing more to do
        try:
            companion = _find_compound_companion(act, acts_by_date.get(act["date"], []))
            act_date = act.get("date")
            session_label = _session_label_for_date(date.fromisoformat(act_date)) if act_date else None
            detail = fetch_activity_detail(api, act_id, activity=act, session_label=session_label)
            text = generate_analysis(act, detail, companion=companion)
            save_detail(act_id, detail, text)
            # Auto-populate FTP trend table for FTP test sessions
            if session_label in _ALL_FTP_LABELS and (
                detail.get("ftp_effort_avg_hr") or detail.get("ftp_w")
            ):
                try:
                    from ..history import save_ftp_test, load_ftp_tests
                    d_obj = date.fromisoformat(act_date) if act_date else None
                    if d_obj and not any(t["date"] == d_obj.isoformat() for t in load_ftp_tests()):
                        ftp_w = detail.get("ftp_w")
                        if not ftp_w and detail.get("ftp_effort_avg_w"):
                            ftp_w = round(detail["ftp_effort_avg_w"] * 0.95)
                        save_ftp_test(
                            d_obj.isoformat(), act_id,
                            int(detail["ftp_effort_avg_hr"]) if detail.get("ftp_effort_avg_hr") else None,
                            int(detail["ftp_effort_max_hr"]) if detail.get("ftp_effort_max_hr") else None,
                            None,
                            ftp_w=ftp_w,
                        )
                        if ftp_w:
                            _mark_workouts_stale(int(ftp_w))
                except Exception:
                    pass
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("analysis failed for %s: %s", act_id, exc)


def load_analyses_for_activities(activities: list[dict]) -> list[dict]:
    """Return activities enriched with analysis data (hr_zones, analysis_text, etc.)."""
    result = []
    for act in activities:
        a = dict(act)
        analysis = load_analysis(act["activity_id"])
        if analysis:
            a.update(analysis)
        result.append(a)
    return result


def retrieve_relevant_analyses(session_type: str, limit: int = 3) -> list[dict]:
    """Return the most recent past activity analyses matching a plan session type.

    Structured retrieval (no embeddings): joins activity_analyses → activities and
    filters to the Garmin type_keys that satisfy `session_type` (via ACTIVITY_MATCH).
    Used to ground the coach chat — "last time you did this kind of session…".
    Returns compact dicts; empty list if no matches or no analyses yet.
    """
    from ..history import ACTIVITY_MATCH

    keys = ACTIVITY_MATCH.get(session_type)
    if not keys:
        return []
    placeholders = ",".join("?" * len(keys))
    with _conn() as con:
        _ensure_analysis_schema(con)
        try:
            rows = con.execute(
                f"""SELECT ac.date AS date, ac.name AS name, ac.type_key AS type_key,
                           ac.avg_hr AS avg_hr, ac.hr_zone_4_sec AS z4, ac.hr_zone_5_sec AS z5,
                           an.training_effect AS training_effect,
                           an.training_effect_label AS training_effect_label,
                           an.training_load AS training_load,
                           an.analysis_text AS analysis_text
                    FROM activity_analyses an
                    JOIN activities ac ON ac.activity_id = an.activity_id
                    WHERE ac.type_key IN ({placeholders})
                      AND an.analysis_text IS NOT NULL AND an.analysis_text != ''
                    ORDER BY ac.date DESC
                    LIMIT ?""",
                (*keys, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    out = []
    for r in rows:
        d = dict(r)
        text = (d.get("analysis_text") or "").strip().replace("\n", " ")
        d["summary"] = (text[:280] + "…") if len(text) > 280 else text
        d["z45_min"] = round(((d.get("z4") or 0) + (d.get("z5") or 0)) / 60)
        out.append(d)
    return out


# ── Missed session recovery suggestions ─────────────────────────────────────

def generate_recovery_suggestion(
    missed_date: date,
    session: tuple,
    upcoming: list[tuple],
    recent_metrics: list[dict],
) -> str:
    """Return coach advice on whether to make up, skip, or adjust after a missed session.

    Cached in text_cache with key 'recovery_{date}'; subsequent calls are instant.
    """
    cache_key = f"recovery_{missed_date.isoformat()}"
    cached = get_cached_text(cache_key)
    if cached:
        return cached

    stype, slabel, sdur = session
    days_left_in_week = 6 - missed_date.weekday()  # Mon=0, Sun=6 → 0 on Sunday

    prompt_lines = [
        f"Missed session: {slabel} ({stype}, planned {sdur}m)",
        f"Day missed: {missed_date.strftime('%A %-d %B %Y')}",
        f"Days remaining in this week after today: {days_left_in_week}",
        "",
    ]

    if upcoming:
        prompt_lines.append("Remaining sessions planned this week:")
        for d, (utype, ulabel, udur) in upcoming:
            prompt_lines.append(f"  {d.strftime('%A')}: {ulabel} ({utype}, {udur}m)")
        prompt_lines.append("")
    else:
        prompt_lines += ["No further sessions planned this week.", ""]

    readiness_lines = []
    for r in recent_metrics:
        hrv = r.get("hrv_last_night")
        sleep = r.get("sleep_score")
        stress = r.get("avg_stress")
        parts = []
        if hrv is not None:
            parts.append(f"HRV {hrv:.0f}ms")
        if sleep is not None:
            parts.append(f"sleep {sleep:.0f}/100")
        if stress is not None:
            parts.append(f"stress {stress:.0f}/100")
        if parts:
            readiness_lines.append(f"  {r['date'].strftime('%-d %b')}: {', '.join(parts)}")

    if readiness_lines:
        prompt_lines += ["Recent readiness (last 3 days):"] + readiness_lines + [""]

    prompt_lines.append(
        "Should the athlete make this session up, skip it, or adjust the rest of the week? "
        "Give a clear recommendation with specific, actionable reasoning."
    )

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return _rule_based_recovery(stype, days_left_in_week)

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    try:
        msg = client.messages.create(
            model=MODEL_FAST,
            max_tokens=350,
            system=(
                COACH_VOICE + "\n\n"
                "Right now: Martin missed a planned training session. Give a clear, reassuring "
                "recommendation: make it up, skip it, or adjust the rest of the week. Be specific "
                "and practical — and don't let a single miss become guilt. Two short paragraphs "
                "maximum. No bullet points. Address the athlete as 'you'."
            ),
            messages=[{"role": "user", "content": "\n".join(prompt_lines)}],
        )
        text = msg.content[0].text
        set_cached_text(cache_key, text)
        return text
    except Exception:
        return _rule_based_recovery(stype, days_left_in_week)

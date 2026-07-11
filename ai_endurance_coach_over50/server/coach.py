"""AI coach engine: system prompt, read tools, chat loop, memo, SSE streaming."""
from __future__ import annotations

import anthropic as _anthropic
import json
import os
import threading

from datetime import date, timedelta
from pydantic import BaseModel, Field
from typing import Optional

from ..client import get_api
from ..coach_context import build_coach_context as _build_coach_context
from ..coach_voice import ATHLETE_CONSTRAINTS, COACH_VOICE, hr_channel_note
from ..history import (
    estimated_wkg_history,
    get_coach_memory,
    get_plan_override,
    intensity_distribution_by_week,
    intensity_distribution_by_week_power,
    load_coach_history,
    load_durability,
    load_power_durability,
    load_recent_activities,
    measured_wkg_history,
    power_meter_active,
    save_coach_message,
    set_coach_memory,
    sleep_history,
    weekly_monotony_strain,
)
from ..hr_plan import HR_PHASES
from ..llm import MODEL_COACH, MODEL_FAST
from ..plan import session_for_date_extended

from .shared import (
    logger,
)
from .context import (
    _plan_completion_stats,
)


# ── AI Coach chat ─────────────────────────────────────────────────────────────

def _coach_system() -> str:
    base = (
        COACH_VOICE + "\n\n"
        "You have access to their live Garmin data in the context block below. "
        "Use it to give specific, evidence-based advice referencing actual numbers.\n\n"
        "Response style: 2–4 short paragraphs. Use **bold** for key numbers/points.\n\n"
        "Durable state & capabilities: your write powers are EXACTLY these — propose_plan_change "
        "(athlete confirms; also pushes that date to Garmin), save_commitment / resolve_commitment "
        "(durable checkpoint, guardrail and decision-rule log), and add_session_note (short note "
        "shown on a date's calendar tile). You can NOT set reminders or alarms, send emails, edit "
        "Garmin workout structure directly, or schedule anything else — never offer an action "
        "outside this list; if the athlete needs one, tell them how to do it themselves. When you "
        "agree a checkpoint, guardrail or decision rule with the athlete, persist it with "
        "save_commitment rather than just saying 'locked in' — unsaved agreements do not survive "
        "between conversations. When a commitment in context is flagged DUE, evaluate it against "
        "its decision rule and baseline, then call resolve_commitment with the outcome.\n\n"
        "Grounding: the Key Dates and Canonical Baselines sections in context are the single "
        "source of truth. Never state camp/event/test timing from memory — read Key Dates. When "
        "citing a baseline (HRV, resting HR, weight, muscle mass, FTP, W/kg), quote ONLY the "
        "Canonical Baselines numbers, never values recalled from earlier in the conversation — "
        "they may be stale or wrong.\n\n"
        "Measurement noise: never trigger a decision off a single data point. Judge weight and "
        "muscle mass on the 14-day rolling averages in Canonical Baselines (bio-impedance swings "
        "±0.5–1 kg day to day). Treat an FTP retest within ±3% of the previous result as FLAT "
        "(test noise), not a real gain or loss. Judge HRV on the z-score and 7d/30d ratio in "
        "context, never on one night. Guardrails and decision rules must be framed on rolling "
        "averages and noise bands, not raw single readings.\n\n"
        "Nutrition periodization: sustained calorie deficits belong in BASE phases. During "
        "build/peak blocks and training camps, steer toward maintenance so quality work is "
        "fuelled and absorbed — at 50+ a hard cut and a hard block don't mix. If the Training "
        "Phase & Nutrition Periodization section flags a conflict, raise it whenever weight, "
        "fuelling or trajectory targets come up.\n\n"
        "Projections: when sketching trajectories (FTP, weight, W/kg, CTL), give RANGES anchored "
        "to scheduled checkpoints (FTP retests, camps), state the assumptions, and recalibrate at "
        "each test. A solid training block yields roughly 5–15W — do not compound best-case block "
        "gains into a precise long-range point estimate.\n\n"
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
        "Nutrition: lead with the SIMPLE RULES and Today's Nutrition Checklist in context when discussing "
        "food; only cite full meal-level detail if asked. Weekend in-ride solids are for long rides only — "
        "use fuel_prep_for_ride batch counts (rice cakes + electrolyte bottles) keyed to planned ride length.\n\n"
        "Training plan context: 12-week plan runs 18 May – 9 Aug 2026, followed by Tenerife cycling camp "
        "(13–27 Aug; bike hire 14–24 Aug) and event prep block (Aug 31 – Sep 12). Builds from Zone 2 base "
        "to back-to-back long rides simulating the 2-day event. Key sessions: Zone 2 rides, FTP tests "
        "(wks 3/7/12), hill repeats and tempo from wk 5, progressive rucking (Mersea Coastal Spur build in "
        "wks 9–10), KB + MaxiClimber strength.\n\n"
        "Haute Route 2027 also has two Tenerife camps inside the 46-week plan: (1) Christmas volume camp "
        "wks 12–13 (arrive 22 Dec 2026, bike 23–31 Dec, home 2 Jan) — August-style Teide overload as a "
        "Base aerobic boost, then wk 14 absorption before Build quality; (2) May race-simulation camp "
        "wk 31 — consecutive stage-sim days rehearsing Haute Route pacing/fuelling/back-to-back fatigue.\n\n"
        "PMC note: Garmin TSB units differ from Coggan TSS. Rough bands: "
        "fresh > −50, moderate load −50 to −150, heavy load −150 to −250, very high fatigue < −250.\n\n"
        "Build-phase framing: during a build block, a deeply negative TSB and ACWR above ~1.3 are the "
        "INTENDED stimulus, not a red flag — deliberately driving acute load above chronic (functional "
        "overreaching) is how CTL grows. Do not treat planned overreaching as a mistake or call it 'load "
        "outpacing fitness'. The real risk signal is CTL ramp rate (CTL gain per week) plus suppressed "
        "body signals (HRV down, readiness negative, resting HR up), not the absolute TSB number — and "
        "ramp matters more at 50+ where recovery capacity is lower. If readiness/HRV are balanced or "
        "positive, the overload is still functional; only flag non-functional overreaching when the body "
        "signals corroborate the load. ACWR is a unitless ratio (acute ÷ chronic), so it IS comparable to "
        "standard thresholds; the absolute CTL/ATL/TSB values are NOT (Garmin units). A practical exception: "
        "an imminent FTP/LTHR retest needs a genuine recovery window regardless of build intent, since a "
        "fatigued test suppresses the result and mis-anchors zones.\n\n"
        "Escalation contract: the athlete's **Today** tab (/) is the daily gate — morning readiness, "
        "HRV traffic light, today's session, and post-workout debrief live there. Do NOT repeat today's "
        "gate advice or post-debrief unless they explicitly ask. Do NOT re-summarise the latest activity "
        "analysis — point them to the Analysis tab or call get_activity_analysis. For vague questions, "
        "clarify scope first (today vs next two weeks). Your default lane is multi-day plan swaps, event "
        "pacing, fuelling depth, and programme philosophy — not 'should I train today?'\n\n"
    )
    return base + hr_channel_note(power_meter_active()) + "\n\n" + ATHLETE_CONSTRAINTS

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


# Action tools: execute immediately (no confirmation card) and persist durable
# coaching state. Together with propose_plan_change and the read tools below,
# this is the coach's COMPLETE power set — _coach_system() states this so the
# coach never offers actions it can't take (reminders, emails, etc.).
_ACTION_TOOLS = [
    {
        "name": "save_commitment",
        "description": (
            "Persist a durable coaching commitment — a checkpoint, guardrail or decision rule "
            "agreed with the athlete. Open commitments are re-injected into your context every "
            "conversation until resolved, so use this whenever you'd otherwise say 'locked in' "
            "or 'we'll track that'."
        ),
        "input_schema": {"type": "object", "properties": {
            "title":         {"type": "string", "description": "Short name, e.g. 'Guardrail checkpoint #1 — 5 Aug FTP test'"},
            "review_date":   {"type": "string", "description": "When to evaluate it (YYYY-MM-DD), if date-bound"},
            "decision_rule": {"type": "string", "description": "The agreed rule verbatim: thresholds/noise bands, which signal governs, what action follows"},
            "baseline":      {"type": "string", "description": "Baseline numbers captured now for later comparison, e.g. 'FTP 202W; muscle 14d avg 64.8kg; HRV 30d 42.2ms'"},
        }, "required": ["title"]},
    },
    {
        "name": "resolve_commitment",
        "description": "Mark an open commitment as resolved once its checkpoint has been evaluated. Record the outcome.",
        "input_schema": {"type": "object", "properties": {
            "commitment_id": {"type": "integer", "description": "The [id] shown in the Open Coach Commitments context section"},
            "resolution":    {"type": "string", "description": "Outcome vs the decision rule, e.g. 'FTP 208W (+3%, up); muscle held — deficit continues'"},
        }, "required": ["commitment_id", "resolution"]},
    },
    {
        "name": "add_session_note",
        "description": (
            "Attach a short coaching note to a specific date — it appears on that day's calendar "
            "tile (✦ badge) and in your own context. Use for pre-test reminders and execution "
            "cues, e.g. 'Keep genuinely easy — FTP test + guardrail checkpoint Wednesday'. "
            "One note per date; a new note replaces the old."
        ),
        "input_schema": {"type": "object", "properties": {
            "date": {"type": "string", "description": "YYYY-MM-DD"},
            "note": {"type": "string", "description": "One or two short sentences"},
        }, "required": ["date", "note"]},
    },
]

_ACTION_TOOL_NAMES = {t["name"] for t in _ACTION_TOOLS}


def _dispatch_action_tool(name: str, tool_input: dict) -> str:
    """Run one action tool and return a plain-text result. Never raises."""
    try:
        if name == "save_commitment":
            from ..history import save_coach_commitment
            title = (tool_input.get("title") or "").strip()[:200]
            if not title:
                return "Commitment title is empty — nothing saved."
            cid = save_coach_commitment(
                title=title,
                decision_rule=tool_input.get("decision_rule"),
                review_date=tool_input.get("review_date"),
                baseline=tool_input.get("baseline"),
            )
            return f"Commitment saved (id {cid}). It will appear in context every conversation until resolved."

        if name == "resolve_commitment":
            from ..history import resolve_coach_commitment
            ok = resolve_coach_commitment(
                int(tool_input["commitment_id"]),
                (tool_input.get("resolution") or "").strip()[:500],
            )
            return "Commitment resolved." if ok else "No open commitment with that id."

        if name == "add_session_note":
            from ..history import set_session_note
            d = date.fromisoformat(tool_input["date"])  # validates format
            note = (tool_input.get("note") or "").strip()[:300]
            if not note:
                return "Note text is empty — nothing saved."
            set_session_note(d.isoformat(), note)
            return f"Note saved for {d.isoformat()} — it will show on that day's calendar tile."

        return f"Unknown tool: {name}"
    except Exception as exc:
        logger.exception("action-tool %s failed", name)
        return f"({name} failed: {exc})"


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
        "description": "Full per-week plan-vs-actual compliance breakdown across the 12-week plan, Tenerife camp, and event prep.",
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
            from ..nutrition_plan import meal_cycle_full
            return meal_cycle_full()

        if name == "get_activity_analysis":
            from ..analysis import load_analysis
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
            from ..hr_plan import (
                hr_session_for_date as _hrs,
                HR_PLAN_START as _HRS,
                HR_EVENT_STAGES,
                power_target_for,
                power_watts_range,
            )
            from ..history import load_ftp_tests
            ftp_w = None
            for t in reversed(load_ftp_tests()):
                if t.get("ftp_w"):
                    ftp_w = int(t["ftp_w"])
                    break
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
                        pt = power_target_for(sess[0], sess[1])
                        pw = power_watts_range(ftp_w, pt) if ftp_w else (
                            f"{pt[0]}–{pt[1]}% FTP" if isinstance(pt, tuple) else pt
                        )
                        extra = f" [{pw}]" if pw else ""
                        day_lines.append(f"{d.strftime('%a')} {sess[1]} ({sess[2]}min){extra}")
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
                wk_lbl = w.get("week_label") or f"Wk{w['week_num']:02d}"
                lines.append(f"  {wk_lbl} ({w['date_range']}) [{w['status']}]: "
                             f"{w['done_sessions']}/{w['plan_sessions']} sessions, {w['pct']}% volume "
                             f"({w['done_min']}/{w['plan_min']}min)")
            return "\n".join(lines)

        if name == "get_workout_description":
            from ..analysis import _load_workout_descs
            label = (tool_input.get("label") or "").strip()
            desc = _load_workout_descs().get(label)
            return f"{label}: {desc}" if desc else f"No cached description for '{label}'."

        if name == "get_fuelling_plan":
            from ..analysis import _load_fuelling_plans, fuelling_session_key
            stype = (tool_input.get("session_type") or "").strip()
            dur_min = int(tool_input.get("dur_min") or 0)
            plan = _load_fuelling_plans().get(fuelling_session_key(stype, dur_min))
            if not plan:
                return f"No cached fuelling plan for {stype} {dur_min}min (only generated for endurance sessions ≥75min)."
            return "\n".join(f"{k}: {v}" for k, v in plan.items() if v not in (None, ""))

        if name == "get_event_plans":
            from ..analysis import generate_charity_day_plans, generate_hr_stage_plans
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
_COACH_MAX_TOKENS = 2048


def _base_plan_session(d: date) -> tuple[str, str, int] | None:
    """Plan session for a date ignoring plan_overrides (for proposal 'before' state)."""
    from ..plan import PLAN_START, TRAINING_WEEKS, _PLAN_DAYS

    delta = (d - PLAN_START).days
    if 0 <= delta < _PLAN_DAYS:
        week_idx, day_idx = divmod(delta, 7)
        return TRAINING_WEEKS[week_idx][day_idx]
    from ..hr_plan import hr_session_for_date
    from ..plan import session_for_date_extended

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
    from ..hr_profile import load_hr_profile, refresh_hr_profile_if_needed
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
    all_tools = [_COACH_TOOL, *_ACTION_TOOLS, *_READ_TOOLS]

    convo = list(messages)
    text_parts: list[str] = []
    proposals: list[dict] = []

    for _ in range(_COACH_MAX_TOOL_TURNS):
        response = client.messages.create(
            model=MODEL_COACH,
            max_tokens=_COACH_MAX_TOKENS,
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
                elif block.name in _ACTION_TOOL_NAMES:
                    content = _dispatch_action_tool(block.name, dict(block.input))
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
        "- Plan decisions made via coach chat (formal checkpoints/guardrails live in the "
        "coach_commitments store and are injected separately — don't duplicate them here)\n"
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
    all_tools = [_COACH_TOOL, *_ACTION_TOOLS, *_READ_TOOLS]

    full_text: list[str] = []
    proposals: list[dict] = []
    convo = list(messages)

    try:
        for _ in range(_COACH_MAX_TOOL_TURNS):
            with client.messages.stream(
                model=MODEL_COACH,
                max_tokens=_COACH_MAX_TOKENS,
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
                elif block.name in _ACTION_TOOL_NAMES:
                    yield f"data: {json.dumps({'type': 'tool', 'name': block.name})}\n\n"
                    content = _dispatch_action_tool(block.name, dict(block.input))
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


_VALID_SESSION_TYPES = {"bike", "ftp", "long", "rest", "ruck", "strength", "tempo",
                        # Haute Route plan vocabulary (hr_plan.py)
                        "endurance", "recovery", "vo2", "sweetspot", "gym", "back_to_back"}


class _ApplyChangeRequest(BaseModel):
    date: str
    duration_min: int = Field(..., ge=0, le=600)  # rest days use 0 in plan.py
    reason: str = Field("", max_length=500)
    session_type: Optional[str] = None  # if provided, overrides the plan session type
    label: Optional[str] = Field(None, max_length=100)  # overrides the plan session label

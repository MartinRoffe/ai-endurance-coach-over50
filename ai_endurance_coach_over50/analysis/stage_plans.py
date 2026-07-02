"""Haute Route stage plans, charity-day plans, peak-sim decoupling flags."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

from ..coach_voice import COACH_VOICE
from ..llm import MODEL_SMART


# ── Haute Route per-stage pacing & fuelling plans ────────────────────────────

HR_STAGE_PLAN_CACHE_VER = "v2"
_PEAK_DECOUPLING_THRESHOLD = 8.0

def peak_sim_decoupling_flags(weeks: list[dict]) -> dict[int, dict]:
    """Flag upcoming peak-phase simulation weeks when recent Pw:HR decoupling is elevated."""
    from ..history import load_power_durability, power_meter_active

    if not power_meter_active():
        return {}
    rows = load_power_durability(90)
    if not rows:
        return {}
    recent = rows[-3:]
    if not any((r.get("decoupling_pct") or 0) > _PEAK_DECOUPLING_THRESHOLD for r in recent):
        return {}
    latest_pct = recent[-1]["decoupling_pct"]
    today = date.today()
    flags: dict[int, dict] = {}
    for week in weeks:
        wn = week.get("week_num", 0)
        if wn < 36 or wn > 43:
            continue
        if not any("Simulation Day" in d.get("label", "") for d in week.get("days", [])):
            continue
        wk_start = week["start"]
        if wk_start + timedelta(days=6) < today:
            continue
        flags[wn] = {
            "decoupling_pct": latest_pct,
            "message": (
                f"Recent Pw:HR decoupling +{latest_pct}% on long rides — "
                "pace simulation days conservatively or add recovery before this block."
            ),
        }
    return flags


def generate_hr_stage_plans() -> dict[int, dict]:
    """Return {stage_day: plan_dict} for the 7 Haute Route Alpes stages.

    Cached per stage in text_cache (key hr_stage_plan_v2_{day}, JSON string).
    When any stage is missing and an API key is set, makes ONE batched
    claude-sonnet-4-6 call for all missing stages, grounded in the athlete's
    latest LTHR and measured or estimated FTP. Returns whatever is cached on failure.
    """
    import json as _json
    from ..hr_plan import HR_EVENT_STAGES
    from ..history import (
        get_cached_text, set_cached_text, load_ftp_tests,
        latest_estimated_wkg, latest_measured_wkg, power_meter_active,
    )

    plans: dict[int, dict] = {}
    missing: list[dict] = []
    for stage in HR_EVENT_STAGES:
        cached = get_cached_text(f"hr_stage_plan_{HR_STAGE_PLAN_CACHE_VER}_{stage['day']}")
        if cached:
            try:
                plans[stage["day"]] = _json.loads(cached)
                continue
            except Exception:
                pass
        missing.append(stage)

    if not missing:
        return plans
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return plans

    # Negative cache: after a failed generation, don't re-fire a blocking
    # Sonnet call on every page view — back off for an hour.
    _FAIL_KEY = f"hr_stage_plan_{HR_STAGE_PLAN_CACHE_VER}_fail_until"
    fail_until = get_cached_text(_FAIL_KEY)
    if fail_until:
        try:
            if datetime.now() < datetime.fromisoformat(fail_until):
                return plans
        except ValueError:
            pass

    has_power = power_meter_active()
    lthr_note = "LTHR unknown — express HR caps as % of LTHR"
    try:
        tests = load_ftp_tests()
        if tests and tests[-1].get("ftp_hr"):
            lthr_note = f"LTHR ≈ {tests[-1]['ftp_hr']} bpm (from FTP test {tests[-1]['date']})"
    except Exception:
        pass

    if has_power:
        measured = latest_measured_wkg()
        ftp_w = measured["ftp_w"] if measured else None
        if not ftp_w:
            tests = load_ftp_tests()
            if tests and tests[-1].get("ftp_w"):
                ftp_w = tests[-1]["ftp_w"]
        wkg_str = f"{measured['wkg']} W/kg" if measured else "unknown"
        athlete_note = (
            f"Athlete has a power meter. Measured FTP = {ftp_w or 'unknown'} W ({wkg_str}). "
            f"{lthr_note}. Dual-channel coaching: HR + watts."
        )
        json_schema = (
            '{"pacing": "2-3 sentence stage pacing strategy", '
            '"hr_cap_first_climb": "specific HR cap or %LTHR for the first climb", '
            '"wkg_cap_first_climb": "W/kg cap for the first climb (e.g. 2.8 W/kg)", '
            '"steady_state_w": "target watts for flat/rolling sections between climbs", '
            '"carbs_g_per_hr": int, "total_carbs_g": int, "fluid_ml_per_hr": int, '
            '"brief": "one-sentence key reminder"}'
        )
        climb_rule = (
            "On climbs >8%, anchor by W/kg; on hot days (>25°C) or above 2000 m, "
            "defer to the HR cap when HR exceeds power-predicted effort."
        )
    else:
        athlete_note = f"Athlete: male, 50+, HR-based training (no power meter). {lthr_note}."
        ftp_note = ""
        try:
            wkg = latest_estimated_wkg()
            if wkg:
                ftp_note = f" Estimated FTP ≈ {wkg['est_ftp_w']} W ({wkg['wkg']} W/kg) — estimate only."
        except Exception:
            pass
        athlete_note += ftp_note
        json_schema = (
            '{"pacing": "2-3 sentence stage pacing strategy", '
            '"hr_cap_first_climb": "specific HR cap or %LTHR for the first climb", '
            '"carbs_g_per_hr": int, "total_carbs_g": int, "fluid_ml_per_hr": int, '
            '"brief": "one-sentence key reminder"}'
        )
        climb_rule = "Express all pacing caps in HR / %LTHR terms."

    lines = [
        "Plan pacing and in-ride fuelling for each stage of the Haute Route Alpes "
        "(7-day amateur stage race, timed climbs, untimed descents).",
        athlete_note,
        "Key stage-race principles: the event is won in the final 3 stages, not the first 2 — "
        "cap effort on day 1–2 climbs; fuel from the first 30 minutes; respect altitude above 2000 m "
        "(HR runs higher for the same effort).",
        climb_rule,
        "Reply ONLY with valid JSON: a dict mapping stage day number (as string) -> " + json_schema,
        "No extra text, no markdown fences.",
        "",
        "Stages:",
    ]
    for s in missing:
        lines.append(
            f'Day {s["day"]}: {s["label"]} — {s["km"]} km, {s["elev_m"]} m climbing, '
            f'key climb {s["key_climb"]}'
        )

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    try:
        msg = client.messages.create(
            model=MODEL_SMART,
            max_tokens=3000,
            system=(
                COACH_VOICE + "\n\n"
                "Right now: drawing on deep experience guiding amateur riders through multi-day "
                "alpine stage races, build Martin's per-stage Haute Route pacing and fuelling "
                "plans. Be specific and practical."
            ),
            messages=[{"role": "user", "content": "\n".join(lines)}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0].strip()
        result: dict = _json.loads(raw)
        for day_str, plan in result.items():
            if not isinstance(plan, dict):
                continue
            try:
                day = int(day_str)
            except (TypeError, ValueError):
                continue
            set_cached_text(f"hr_stage_plan_{HR_STAGE_PLAN_CACHE_VER}_{day}", _json.dumps(plan))
            plans[day] = plan
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("HR stage plan generation failed: %s", exc)
        set_cached_text(_FAIL_KEY, (datetime.now() + timedelta(hours=1)).isoformat())

    return plans


def generate_charity_day_plans() -> dict[int, dict]:
    """Return {day_num: plan_dict} for the two Ghent→Amsterdam charity-ride days.

    Cached per day in text_cache (key charity_day_plan_v1_{day}, JSON string).
    When any day is missing and an API key is set, makes ONE batched
    claude-sonnet-4-6 call for all missing days, grounded in the athlete's
    latest LTHR and estimated FTP. Returns whatever is cached on failure.
    Mirrors generate_hr_stage_plans().
    """
    import json as _json
    from ..plan import CHARITY_DAYS
    from ..history import get_cached_text, set_cached_text, load_ftp_tests, latest_estimated_wkg, latest_measured_wkg, power_meter_active

    plans: dict[int, dict] = {}
    missing: list[dict] = []
    for cd in CHARITY_DAYS:
        cached = get_cached_text(f"charity_day_plan_v1_{cd['day']}")
        if cached:
            try:
                plans[cd["day"]] = _json.loads(cached)
                continue
            except Exception:
                pass
        missing.append(cd)

    if not missing:
        return plans
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return plans

    # Negative cache: back off for an hour after a failed generation so we don't
    # re-fire a blocking Sonnet call on every calendar page view.
    _FAIL_KEY = "charity_day_plan_fail_until"
    fail_until = get_cached_text(_FAIL_KEY)
    if fail_until:
        try:
            if datetime.now() < datetime.fromisoformat(fail_until):
                return plans
        except ValueError:
            pass

    # Athlete context: LTHR from the most recent FTP test, measured/estimated FTP watts
    lthr_note = "LTHR unknown — express HR caps as % of LTHR"
    try:
        tests = load_ftp_tests()
        if tests and tests[-1].get("ftp_hr"):
            lthr_note = f"LTHR ≈ {tests[-1]['ftp_hr']} bpm (from FTP test {tests[-1]['date']})"
    except Exception:
        pass

    has_power = power_meter_active()
    if has_power:
        measured = latest_measured_wkg()
        ftp_w = measured["ftp_w"] if measured else None
        if not ftp_w:
            tests = load_ftp_tests()
            if tests and tests[-1].get("ftp_w"):
                ftp_w = tests[-1]["ftp_w"]
        wkg_str = f"{measured['wkg']} W/kg" if measured else "unknown"
        athlete_line = (
            f"Athlete: male, 50+, power meter active. Measured FTP = {ftp_w or 'unknown'} W ({wkg_str}). "
            f"{lthr_note}. Dual-channel: watts for steady-state pacing, HR for readiness and heat."
        )
        json_schema = (
            '{"pacing": "3-4 sentence pacing strategy for the day", '
            '"hr_cap": "specific HR cap or %LTHR for the early hours", '
            '"steady_state_w": "target watts for flat/rolling sections", '
            '"carb_load": "1-2 sentence pre-event carb-load note for this day", '
            '"carbs_g_per_hr": int, "fluid_ml_per_hr": int, "sodium_mg_per_hr": int, '
            '"brief": "one-sentence key reminder"}'
        )
    else:
        ftp_note = ""
        try:
            wkg = latest_estimated_wkg()
            if wkg:
                ftp_note = f" Estimated FTP ≈ {wkg['est_ftp_w']} W ({wkg['wkg']} W/kg) — estimate only, no power meter."
        except Exception:
            pass
        athlete_line = f"Athlete: male, 50+, HR-based training (no power meter). {lthr_note}.{ftp_note}"
        json_schema = (
            '{"pacing": "3-4 sentence pacing strategy for the day", '
            '"hr_cap": "specific HR cap or %LTHR for the early hours", '
            '"carb_load": "1-2 sentence pre-event carb-load note for this day", '
            '"carbs_g_per_hr": int, "fluid_ml_per_hr": int, "sodium_mg_per_hr": int, '
            '"brief": "one-sentence key reminder"}'
        )

    lines = [
        "Plan pacing and in-ride fuelling for a 2-day supported charity cycling event "
        "(Ghent → Amsterdam, ~310 km total, flat-to-rolling, group riding).",
        athlete_line,
        "Critical context: the athlete's LONGEST training ride is ~5 hours, so Day 1 "
        "(190 km) exceeds the longest training ride by roughly 30–40%. Pacing and fuelling "
        "— not fitness — are the levers that determine whether Day 1 succeeds.",
        "Key principles to encode in the plan:",
        "- 2-day carb load beforehand at 8–10 g/kg/day.",
        "- Fuel from hour 1: 80–90 g carbs/hr the whole ride (gut already trained in the build).",
        "- 500–750 ml fluid/hr with 500–800 mg sodium/hr.",
        "- Day 1: ride the first 3 hours strictly below the Z2 ceiling — bank no early fatigue.",
        "- Day 2: legs will be tired from Day 1; start very easy and let them come good.",
        "Reply ONLY with valid JSON: a dict mapping day number (as string) -> " + json_schema,
        "No extra text, no markdown fences.",
        "",
        "Days:",
    ]
    for cd in missing:
        lines.append(f'Day {cd["day"]}: {cd["label"]} — {cd["km"]} km')

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    try:
        msg = client.messages.create(
            model=MODEL_SMART,
            max_tokens=2000,
            system=(
                COACH_VOICE + "\n\n"
                "Right now: build Martin's per-day pacing and fuelling plans for his first "
                "2-day, 310 km charity ride (Ghent to Amsterdam). Be specific and practical."
            ),
            messages=[{"role": "user", "content": "\n".join(lines)}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0].strip()
        result: dict = _json.loads(raw)
        for day_str, plan in result.items():
            if not isinstance(plan, dict):
                continue
            try:
                day = int(day_str)
            except (TypeError, ValueError):
                continue
            set_cached_text(f"charity_day_plan_v1_{day}", _json.dumps(plan))
            plans[day] = plan
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Charity day plan generation failed: %s", exc)
        set_cached_text(_FAIL_KEY, (datetime.now() + timedelta(hours=1)).isoformat())

    return plans

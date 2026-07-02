"""Prefetched AI caches: workout descriptions, nutrition targets, fuelling plans."""
from __future__ import annotations

import os
import sqlite3
from typing import Optional

from ..history import _conn
from ..llm import MODEL_FAST


# ── Workout descriptions (calendar modal coaching notes) ─────────────────────

# Exact step structure of each session type — mirrors workouts.py
_STEP_SUMMARIES: dict[str, str] = {
    "Easy Spin":        "10m warm-up → Z1–2 easy riding → 10m cool-down",
    "Zone 2 Steady":    "10m warm-up → sustained Z2 main block → 10m cool-down",
    "Recovery Spin":    "10m warm-up → Z1 only (very easy) → 10m cool-down",
    "Structured Z2":    "10m warm-up → 3 × (12m Z2 + 2m easy recovery) → 10m cool-down",
    "Hill Repeats":     "10m warm-up → 5 × (3m Z4–5 hill effort + 3m Z1 descent recovery) → 10m cool-down",
    "Sweetspot Ride":   "15m warm-up → 3 × (15m at 88–93% FTP sweetspot + 5m Z2 recovery) → 10m cool-down",
    "Over-Unders":      "15m warm-up → 2 sets × [4 × (2m over @ 105% FTP + 2m under @ 95% FTP)], 5m Z1 between sets → 10m cool-down",
    "Threshold Ride":   "15m warm-up → 2 × 20m at Z4 (100% FTP) with 5m Z2 recovery → 10m cool-down",
    "Low Cadence Ride": "10m warm-up → 6 × (4m at 60–70 rpm Z3 + 2m Z1 recovery) → 20m Z2 steady → 10m cool-down",
    "Z2 Ride":          "10m warm-up → sustained Z2 steady-state → 10m cool-down",
    "Easy Ride":        "10m warm-up → easy Z1–2 riding (active recovery) → 10m cool-down",
    "Cadence Drills":   "10m warm-up → 5 × (3m at 90–110 rpm + 2m Z2) → 15m Z2 steady → 10m cool-down",
    "Z2 Endurance":     "10m warm-up → sustained Z2 main block → 10m cool-down",
    "Low Cadence":      "10m warm-up → 5 × (4m at 60–70 rpm + 2m Z1 recovery) → 10m Z2 → 10m cool-down",
    "Easy Prep Ride":   "10m warm-up → Z1–2 very easy → 10m cool-down",
    "FTP Test":         "15m warm-up → 3m priming effort → 5m Z1 easy → 20-min all-out effort → 17m cool-down",
    "FTP Re-test":      "15m warm-up → 3m priming effort → 5m Z1 easy → 20-min all-out effort → 17m cool-down",
    "Final FTP Test":   "15m warm-up → 3m priming effort → 5m Z1 easy → 20-min all-out effort → 17m cool-down",
    "Tempo Intervals":  "15m warm-up → 3 × (10m Z4 + 5m Z1 recovery) → 5m cool-down",
    "Long Ride":        "15m warm-up → sustained Z2 main block → 15m cool-down",
    "Long Ride (Easy)": "15m warm-up → easy Z1–2 riding → 15m cool-down",
    "KB + MaxiClimber": "Kettlebell strength work (swings, presses, carries) then MaxiClimber full-body climbing intervals — arms and legs simultaneously. Interval protocol progresses each phase toward Norwegian 4×4 in the peak block.",
    "MaxiClimber":      "MaxiClimber full-body vertical climbing (arms and legs) at easy pace — deload or recovery week session.",
    "Easy MaxiClimber": "Easy-pace MaxiClimber full-body climbing for active recovery — low intensity, focus on movement quality.",
    "Light KB":         "Light kettlebell technique and conditioning work emphasising form and movement quality over load.",
}

def _ensure_workout_desc_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS workout_descriptions (
            label TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            generated_at TEXT DEFAULT (datetime('now'))
        )
    """)


def _load_workout_descs() -> dict[str, str]:
    with _conn() as con:
        _ensure_workout_desc_schema(con)
        rows = con.execute("SELECT label, description FROM workout_descriptions").fetchall()
    return {r["label"]: r["description"] for r in rows}


def prefetch_workout_descriptions(labels: list[str]) -> dict[str, str]:
    """Return {label: coaching_description} for all labels; generate missing ones via Claude."""
    existing = _load_workout_descs()
    missing = [l for l in labels if l not in existing]
    if not missing:
        return existing

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return existing

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    lines = [
        "You are an experienced endurance and conditioning coach. For each workout below write exactly 2 sentences:",
        "Sentence 1: what physiological adaptation this session targets and why it's in the plan.",
        "Sentence 2: the single most important execution tip for getting it right.",
        "Reply ONLY with valid JSON mapping label → two-sentence string. No extra keys or text.",
        "",
        "Workouts:",
    ]
    for label in missing:
        summary = _STEP_SUMMARIES.get(label, label)
        lines.append(f'"{label}": {summary}')

    try:
        msg = client.messages.create(
            model=MODEL_FAST,
            max_tokens=2000,
            messages=[{"role": "user", "content": "\n".join(lines)}],
        )
        import json as _json
        raw = msg.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0].strip()
        result: dict[str, str] = _json.loads(raw)
        with _conn() as con:
            _ensure_workout_desc_schema(con)
            for label, desc in result.items():
                if isinstance(desc, str):
                    con.execute(
                        "INSERT OR REPLACE INTO workout_descriptions (label, description) VALUES (?,?)",
                        (label, desc),
                    )
        existing.update(result)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("workout desc generation failed: %s", exc)

    return existing


# ── Nutrition targets (Claude-calculated kcal per session type+duration) ─────

_SESSION_TYPE_DESC: dict[str, str] = {
    "rest":     "complete rest day",
    "strength": "kettlebell and MaxiClimber strength training",
    "bike":     "Zone 2 steady cycling",
    "tempo":    "tempo intervals cycling (high intensity)",
    "ftp":      "FTP test — maximal 20-minute cycling effort",
    "ruck":     "weighted rucking carrying 8–15 kg pack",
    "long":     "long Zone 2 cycling endurance ride",
}

def _ensure_nutrition_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS nutrition_targets (
            session_key  TEXT PRIMARY KEY,
            kcal         INTEGER,
            protein_g    INTEGER,
            carbs_g      INTEGER,
            fat_g        INTEGER,
            brief        TEXT,
            generated_at TEXT DEFAULT (datetime('now'))
        )
    """)


def _load_nutrition_targets() -> dict[str, dict]:
    with _conn() as con:
        _ensure_nutrition_schema(con)
        rows = con.execute("SELECT * FROM nutrition_targets").fetchall()
    return {r["session_key"]: dict(r) for r in rows}


def prefetch_nutrition_targets(sessions: list[tuple[str, int]], goal: str = "cut") -> dict[str, dict]:
    """Return {f"{goal}_{type}_{dur}": {kcal, protein_g, carbs_g, fat_g, brief}} for every session.

    `goal` switches the energy strategy and is part of the cache key so the two
    training blocks never collide:
      - "cut"     — Block A (12-week reset → Tenerife → charity ride): a
                    lean-mass-sparing fat-loss deficit for a returning 50+ athlete
                    with high body fat.
      - "perform" — Block B (Haute Route build): energy balance, no deliberate
                    deficit, key sessions fully fuelled.
    """
    existing = _load_nutrition_targets()
    missing = [(t, d) for t, d in sessions if f"{goal}_{t}_{d}" not in existing]
    if not missing:
        return existing

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return existing

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    from ..history import latest_weight_kg
    weight = latest_weight_kg()
    weight_str = f"~{weight:.0f} kg body weight" if weight else "body weight unknown (assume ~90 kg)"

    if goal == "perform":
        goal_lines = [
            "Goal: ENERGY BALANCE to support a demanding multi-day alpine build — no deliberate "
            "deficit. Fully fuel the long and quality sessions; match intake to the day's load.",
        ]
    else:  # "cut"
        goal_lines = [
            "Goal: a MODERATE, LEAN-MASS-SPARING calorie deficit for steady fat loss (~0.5 kg/week) "
            "in a returning 50+ athlete with high body fat — the deficit is safe here given ample fat "
            "reserves. Keep protein high to protect muscle, concentrate carbohydrate around the long "
            "ride and quality sessions so they are NOT under-fuelled, and take the deficit mainly from "
            "rest/recovery days; keep the long-ride day close to energy balance.",
        ]

    from ..nutrition_plan import protein_target_g
    pt = protein_target_g()

    lines = [
        f"You are a sports nutritionist for a male athlete aged 50+, {weight_str}.",
        *goal_lines,
        f"Protein target: at least {pt['low']}–{pt['high']} g/day ({pt['basis']}) to preserve muscle; "
        "distribute ~0.4 g/kg across 4+ meals plus a ~40 g pre-sleep casein/dairy dose.",
        "For each training session below provide TOTAL DAILY nutrition targets (all meals + snacks combined).",
        "Reply ONLY with valid JSON: a dict mapping session_key -> {\"kcal\": int, \"protein_g\": int, \"carbs_g\": int, \"fat_g\": int, \"brief\": \"one-sentence tip\"}",
        "No extra text, no markdown fences.",
        "",
        "Sessions (key: description, duration):",
    ]
    for stype, dur in missing:
        desc = _SESSION_TYPE_DESC.get(stype, stype)
        key = f"{goal}_{stype}_{dur}"
        dur_str = f"{dur} min" if dur > 0 else "no exercise"
        lines.append(f'"{key}": {desc}, {dur_str}')

    try:
        msg = client.messages.create(
            model=MODEL_FAST,
            max_tokens=3000,
            messages=[{"role": "user", "content": "\n".join(lines)}],
        )
        import json as _json
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0].strip()
        result: dict = _json.loads(raw)
        with _conn() as con:
            _ensure_nutrition_schema(con)
            for key, data in result.items():
                if isinstance(data, dict):
                    con.execute(
                        """INSERT OR REPLACE INTO nutrition_targets
                           (session_key, kcal, protein_g, carbs_g, fat_g, brief)
                           VALUES (?,?,?,?,?,?)""",
                        (
                            key,
                            data.get("kcal"),
                            data.get("protein_g"),
                            data.get("carbs_g"),
                            data.get("fat_g"),
                            data.get("brief"),
                        ),
                    )
        existing.update(result)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("nutrition target generation failed: %s", exc)

    return existing


# ── In-session fuelling plans (carbs/hr, fluid, sodium during the ride) ───────

# Endurance session types where in-ride fuelling matters, and the minimum duration
# (minutes) below which fuelling is just water (no plan generated).
_FUEL_TYPES = {"long", "bike", "tempo", "ftp"}
_FUEL_MIN_DURATION = 75

def _ensure_fuelling_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS fuelling_plans (
            session_key      TEXT PRIMARY KEY,
            carbs_g_per_hr   INTEGER,
            total_carbs_g    INTEGER,
            fluid_ml_per_hr  INTEGER,
            sodium_mg_per_hr INTEGER,
            timeline         TEXT,
            brief            TEXT,
            generated_at     TEXT DEFAULT (datetime('now'))
        )
    """)


def _load_fuelling_plans() -> dict[str, dict]:
    with _conn() as con:
        _ensure_fuelling_schema(con)
        rows = con.execute("SELECT * FROM fuelling_plans").fetchall()
    return {r["session_key"]: dict(r) for r in rows}


def fuelling_session_key(stype: str, dur_min: int) -> str:
    """Single source of truth for fuelling_plans cache keys (plan type + planned minutes)."""
    return f"{stype}_{dur_min}"


def default_fuelling_plan(dur_min: int) -> dict:
    """Rule-based carbs/hr target when no cached AI fuelling plan exists."""
    if dur_min >= 240:
        carbs = 90
    elif dur_min >= 150:
        carbs = 80
    else:
        carbs = 60
    return {"carbs_g_per_hr": carbs, "fluid_ml_per_hr": 600}


def prefetch_fuelling_plans(sessions: list[tuple[str, int]], weight_kg: Optional[float] = None) -> dict[str, dict]:
    """Return {f"{type}_{dur}": fuelling_plan} for qualifying endurance sessions.

    Only generates for `_FUEL_TYPES` sessions ≥ `_FUEL_MIN_DURATION` minutes; shorter
    or non-endurance sessions don't need a structured in-ride plan. Mirrors the
    `prefetch_nutrition_targets` cache pattern (per session_key). Scales to rider
    weight: uses the passed `weight_kg`, else the latest measured weight, else
    falls back to 90 kg with a note when no body-comp data is available.
    """
    if weight_kg is None:
        from ..history import latest_weight_kg
        weight_kg = latest_weight_kg()
    weight = weight_kg or 90.0
    weight_known = weight_kg is not None

    qualifying = [
        (t, d) for t, d in sessions
        if t in _FUEL_TYPES and d >= _FUEL_MIN_DURATION
    ]
    existing = _load_fuelling_plans()
    missing = [(t, d) for t, d in qualifying if fuelling_session_key(t, d) not in existing]
    if not missing:
        return existing

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return existing

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    weight_note = f"{weight:.0f} kg" + ("" if weight_known else " (assumed — no body-comp data)")
    lines = [
        f"You are a sports nutritionist planning IN-RIDE fuelling for a male cyclist, ~{weight_note}.",
        "These are targets for what to consume DURING the session itself (not daily meals).",
        "Use evidence-based ranges: ~60 g carbs/hr for rides 1–2.5 h, rising to 80–90 g/hr for "
        "longer/harder rides (use a 1:0.8 glucose:fructose mix above ~60 g/hr to raise the "
        "absorption ceiling); 500–750 ml fluid/hr; 300–700 mg sodium/hr depending on duration and "
        "intensity. The gut is trainable — bias the longest sessions toward the high end so the "
        "athlete rehearses event-day fuelling (90+ g/hr). Fuel these endurance sessions fully even "
        "during a weight-loss block: the deficit belongs to rest days, not the key ride. "
        "Schedule context: weekend long rides (2–6 h) start very early with minimal pre-ride breakfast "
        "(carbs from minute 0 on the bike); weekday evening rides are shorter, post-lunch, and usually "
        "need lighter during-ride fuelling unless duration ≥75 min.",
        "For each session provide a short hour-by-hour timeline (e.g. '0–60min: 1 bottle + 1 gel; ...').",
        "Reply ONLY with valid JSON: a dict mapping session_key -> "
        "{\"carbs_g_per_hr\": int, \"total_carbs_g\": int, \"fluid_ml_per_hr\": int, "
        "\"sodium_mg_per_hr\": int, \"timeline\": \"short string\", \"brief\": \"one-sentence tip\"}",
        "No extra text, no markdown fences.",
        "",
        "Sessions (key: description, duration):",
    ]
    for stype, dur in missing:
        desc = _SESSION_TYPE_DESC.get(stype, stype)
        key = fuelling_session_key(stype, dur)
        lines.append(f'"{key}": {desc}, {dur} min')

    try:
        msg = client.messages.create(
            model=MODEL_FAST,
            max_tokens=3000,
            messages=[{"role": "user", "content": "\n".join(lines)}],
        )
        import json as _json
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0].strip()
        result: dict = _json.loads(raw)
        with _conn() as con:
            _ensure_fuelling_schema(con)
            for key, data in result.items():
                if isinstance(data, dict):
                    con.execute(
                        """INSERT OR REPLACE INTO fuelling_plans
                           (session_key, carbs_g_per_hr, total_carbs_g, fluid_ml_per_hr,
                            sodium_mg_per_hr, timeline, brief)
                           VALUES (?,?,?,?,?,?,?)""",
                        (
                            key,
                            data.get("carbs_g_per_hr"),
                            data.get("total_carbs_g"),
                            data.get("fluid_ml_per_hr"),
                            data.get("sodium_mg_per_hr"),
                            data.get("timeline"),
                            data.get("brief"),
                        ),
                    )
        existing.update({k: v for k, v in result.items() if isinstance(v, dict)})
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("fuelling plan generation failed: %s", exc)

    return existing

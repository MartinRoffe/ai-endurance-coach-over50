"""Nutrition plan data — 4-week repeatable cycle.

Encoded here so the AI coach can reference the exact prescribed meals for
today rather than only seeing what was logged after the fact.

Protein targets are anchored to the athlete's measured bodyweight (carried
from the most recent body_metrics reading via `current_weight_kg()`), not a
hardcoded figure — the Block-A weight-loss reset means weight is falling over
the plan and a static number would drift out of date.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import html
import re
from collections import Counter
from datetime import date, timedelta

# Fallback used only before any body_metrics reading exists. The athlete is
# returning from a sedentary decade with high body fat; targets recalibrate
# automatically once a real weigh-in is logged.
_FALLBACK_WEIGHT_KG = 92.0


def current_weight_kg() -> float:
    """Latest measured bodyweight, falling back to `_FALLBACK_WEIGHT_KG`."""
    try:
        from .history import latest_weight_kg
        w = latest_weight_kg()
        return w if w else _FALLBACK_WEIGHT_KG
    except Exception:
        logger.warning("current_weight_kg failed", exc_info=True)
        return _FALLBACK_WEIGHT_KG


# Protein is prescribed on a FAT-FREE-MASS basis, not total bodyweight: at high
# body fat, g/kg of total weight over-prescribes. 2.2–2.6 g/kg of lean mass is
# the evidence-based range to preserve muscle in a deficit, and the upper end
# suits a 50+ athlete (anabolic resistance). Falls back to 1.8 g/kg of total
# weight when no body-fat reading exists to derive lean mass.
_PROTEIN_G_PER_KG_LEAN_LOW = 2.2
_PROTEIN_G_PER_KG_LEAN_HIGH = 2.6


# One static intake used only when a stable TDEE is not available yet.
FALLBACK_INTAKE_KCAL = 2200

from .coach_voice import STONE_SAFE_LINE
from .energy import (
    CUT_TARGET_KG,
    LONG_RIDE_EXTRA_KCAL_PER_HOUR,
    MIN_INTAKE_KCAL,
    active_cut_phase,
    day_kind,
    deficit_for_tier,
    fluid_target_litres,
    in_maintenance_window,
    intake_target_kcal,
    ride_kcal_from_kj,
)

# Snapshot of fat-free mass at Base Cut start — protein stays locked to this
# floor so g/kg targets do not ratchet down as lean mass inches lower.
_CUT_LEAN_CACHE_KEY = "cut_lean_kg_v1"


def _ensure_cut_lean_snapshot(lean: float | None) -> float | None:
    """Persist lean mass once when a cut phase is first active; return locked value."""
    if lean is None or lean <= 0:
        return None
    try:
        from .history import get_cached_text, set_cached_text

        cached = get_cached_text(_CUT_LEAN_CACHE_KEY)
        if cached is not None:
            try:
                return float(cached)
            except (TypeError, ValueError):
                pass
        set_cached_text(_CUT_LEAN_CACHE_KEY, f"{lean:.2f}")
        return round(lean, 2)
    except Exception:
        logger.warning("_ensure_cut_lean_snapshot failed", exc_info=True)
        return lean


def protein_target_g(ref_date: date | None = None) -> dict:
    """Daily protein floor/ceiling in grams, on a fat-free-mass basis.

    Returns {"low", "high", "basis", "lean_kg"}; `basis` documents how it was
    derived so the coach text can be honest about the input. During an active
    cut phase, lean mass is ``max(current, lean_at_cut_start)``.
    """
    try:
        from .history import latest_lean_mass_kg
        lean = latest_lean_mass_kg()
    except Exception:
        logger.warning("protein_target_g failed", exc_info=True)
        lean = None
    locked = False
    ref = ref_date or date.today()
    if lean and active_cut_phase(ref):
        snap = _ensure_cut_lean_snapshot(lean)
        if snap is not None:
            if snap > lean:
                locked = True
            lean = max(lean, snap)
            locked = locked or abs(snap - lean) < 0.05
    if lean:
        basis = (
            f"{_PROTEIN_G_PER_KG_LEAN_LOW:g}–{_PROTEIN_G_PER_KG_LEAN_HIGH:g} g/kg of fat-free mass, "
            f"~{lean:.0f} kg"
        )
        if locked:
            basis += " (locked at cut start)"
        return {
            "low": round(lean * _PROTEIN_G_PER_KG_LEAN_LOW),
            "high": round(lean * _PROTEIN_G_PER_KG_LEAN_HIGH),
            "basis": basis,
            "lean_kg": round(lean, 1),
            "lean_locked": locked,
        }
    # No body-fat reading — fall back to total-weight estimate.
    w = current_weight_kg()
    return {
        "low": round(w * 1.8),
        "high": round(w * 2.0),
        "basis": f"1.8–2.0 g/kg of bodyweight, ~{w:.0f} kg — no body-fat reading to derive lean mass",
        "lean_kg": None,
        "lean_locked": False,
    }


def _stable_tdee(days: int = 7) -> float | None:
    """Stable multi-day TDEE used for intake prescriptions (not today's partial burn)."""
    from .history import stable_tdee_kcal

    try:
        return stable_tdee_kcal(days)
    except Exception:
        logger.warning("_stable_tdee failed", exc_info=True)
        return None


def resolve_calorie_target(
    tdee: float | None,
    tier_key: str,
    ref_date: date,
    *,
    session_dur_min: int | None = None,
    session_type: str | None = None,
) -> dict:
    """Intake target for a day: stable-TDEE-derived when possible, else static tier.

    ``tdee`` should be the stable multi-day TDEE (``_stable_tdee()``), not
    today's partial burn. Returns ``kcal``, ``from_tdee``, optional
    ``planned_deficit`` (TDEE − target), ``tier_deficit``, ``long_fuel_topup``,
    and ``static_fallback`` (one number, used when TDEE is unknown).
    """
    static = FALLBACK_INTAKE_KCAL
    cut_phase = active_cut_phase(ref_date)
    camp = camp_nutrition_window(ref_date)
    if camp:
        hard = is_camp_hard_day(ref_date)
        if hard:
            kcal = max(3200, round(float(tdee) * 1.05)) if tdee is not None else 3500
        elif tdee is not None:
            kcal = max(MIN_INTAKE_KCAL, round(float(tdee) * 0.85))
        else:
            kcal = static
        return {
            "kcal": kcal,
            "from_tdee": tdee is not None,
            "tdee": round(float(tdee)) if tdee is not None else None,
            "planned_deficit": round(float(tdee)) - kcal if tdee is not None else None,
            "tier_deficit": 0,
            "long_fuel_topup": 0,
            "static_fallback": static,
            "camp": True,
            "maintenance": False,
            "cut_phase": None,
            "cut_target_kg": CUT_TARGET_KG,
        }

    maintenance = in_maintenance_window(ref_date)
    tier_deficit = deficit_for_tier(tier_key, ref_date)
    long_extra = 0
    long_fuel_topup = 0
    if tier_key == "long" and session_dur_min and session_dur_min > 120:
        long_extra = session_dur_min - 120
        long_fuel_topup = round(
            LONG_RIDE_EXTRA_KCAL_PER_HOUR * (long_extra / 60.0)
        )
    computed = intake_target_kcal(
        tdee, tier_key, long_ride_extra_min=long_extra, ref_date=ref_date
    )
    if computed is None:
        return {
            "kcal": static,
            "from_tdee": False,
            "static_fallback": static,
            "tier_deficit": tier_deficit,
            "long_fuel_topup": long_fuel_topup,
            "camp": False,
            "maintenance": maintenance,
            "cut_phase": None if maintenance else cut_phase,
            "cut_target_kg": CUT_TARGET_KG,
        }
    return {
        "kcal": computed,
        "from_tdee": True,
        "tdee": round(float(tdee)),
        "planned_deficit": round(float(tdee)) - computed,
        "tier_deficit": tier_deficit,
        "long_fuel_topup": long_fuel_topup,
        "static_fallback": static,
        "camp": False,
        "maintenance": maintenance,
        "cut_phase": None if maintenance else cut_phase,
        "cut_target_kg": CUT_TARGET_KG,
    }


# ── Simple rules (the whole cheat sheet) ──────────────────────────────────────
SIMPLE_RULES = [
    "Calories — three day types only. Easy or rest: stable TDEE minus 600. "
    "Hard: minus 250. Long: maintenance plus ride fuel. Floor 1,600 kcal. No cut before 3 Jan 2027.",
    "Protein — one lean-mass target, spread across breakfast, lunch, dinner, and an evening "
    "yoghurt only when the day still needs protein or calcium. Not a fixed 350 g bowl.",
    "Carbs — one figure that fits the day's calories, after protein and about a quarter of the day "
    "for fat. On-bike grams per hour are part of that figure, not a second pile.",
    "Fluids — 2.5–3 L plus 0.5 L per training hour. Urine pale. Lemon or lime in the water.",
    "Habit — veg or fruit at every meal, and creatine 3–5 g every day. Sunday: two one-pots and "
        "one soup for the weekday lunches and for Monday to Thursday dinners. Friday dinner is a "
        "quick griddle plate. Cook the portions the week eats, so the shop list matches the plates. "
        "Chicken at most twice a week.",
]

HABIT_LINE = "Veg or fruit at every meal, plus creatine 3–5 g."

# ── Supplements (evidence-based for 50+; discuss with GP before starting) ─────
# Framed as coach guidance, NOT prescriptions. Each entry: (name, dose, why).
SUPPLEMENTS: list[tuple[str, str, str]] = [
    ("Creatine monohydrate", "3–5 g/day, every day",
     "Best-evidenced supplement for a masters athlete: helps retain lean mass and strength in a "
     "calorie deficit, supports high-intensity work and recovery, and may aid cognition. No loading "
     "needed; take any time of day."),
    ("Vitamin D3", "Per GP / blood test (often 1000–2000 IU/day in winter)",
     "Supports bone density (important for a cyclist — low impact), immune function and muscle. "
     "UK sun is insufficient Oct–Mar; dose to a measured blood level rather than guessing. "
     "Pair with dietary calcium (dairy/yogurt already in the meal plan) — D3 alone is not enough "
     "for bone health."),
    ("Calcium (dietary first)", "1,000–1,200 mg/day from dairy, with meals",
     "Do not cut this. Milk, Greek yoghurt, skyr and kefir cover it when they are eaten with "
     "meals. A calcium pill is only for a day the food does not get there, and only if your GP agrees."),
    ("Vitamin C", "A standard multivitamin dose only",
     "High-dose vitamin C raises oxalate. Stay at a normal supplement dose, or skip it and eat fruit."),
    ("Iron awareness", "Screen if unexplained fatigue / GP directed",
     "Male masters cyclists on high-volume blocks can drift low. Do not self-supplement iron — "
     "test first. Red flags: persistent fatigue despite sleep, rising resting HR, poor ride "
     "quality with adequate fuelling."),
    ("Omega-3 (EPA/DHA)", "~1–2 g combined EPA+DHA/day",
     "Anti-inflammatory; may blunt training soreness and support cardiovascular and joint health. "
     "Oily fish 2–3×/week is an alternative to a capsule."),
]

_SUPPLEMENT_DISCLAIMER = (
    "Guidance only, not medical advice — confirm doses and suitability with your GP, "
    "especially alongside any medication or blood-pressure management."
)

# Breakfasts and the rotating one-pots/soups live in the recipe library.
# BREAKFASTS stays as (name, detail, kcal, protein, carbs) for search.
# The kcal figures are one written plate. The day scaler moves the portion.
from .recipes.catalog import BREAKFASTS as _BREAKFAST_RECIPES
from .recipes.catalog import recipe_by_id as _recipe_by_id
from .recipes.model import portion_macros as _portion_macros

def _breakfast_tuple(recipe) -> tuple[str, str, int, int, int]:
    macros = _portion_macros(recipe, 1)
    return (
        recipe.name,
        recipe.summary,
        int(round(macros["kcal"])),
        int(round(macros["protein"])),
        int(round(macros["carbs"])),
    )

BREAKFASTS: dict[str, tuple[str, str, int, int, int]] = {
    recipe.id: _breakfast_tuple(recipe) for recipe in _BREAKFAST_RECIPES.values()
}

_BREAKFAST_LABEL = (
    "Rotate porridge, overnight oats, eggs on toast, an omelette, a yoghurt bowl, "
    "or cereal. Saturday is a full English."
)

def evening_dinner(cycle_week: int, weekday: int, kind: str = "easy") -> tuple:
    """Dinner plate for this cycle slot, at the written portion."""
    _ = kind
    from .recipes.menu import _plates
    from .recipes.model import numbered_method, portion_macros

    _lunch, dinner, _lunch_fixed, _dinner_fixed = _plates(cycle_week, weekday)
    macros = portion_macros(dinner, 1)
    return (
        "Dinner",
        dinner.name,
        numbered_method(dinner),
        int(round(macros["kcal"])),
        int(round(macros["protein"])),
        int(round(macros["carbs"])),
    )


def weekday_dinner(cycle_week: int, weekday: int) -> tuple | None:
    """Evening one-pot for any weekday 0–6. None only if out of range."""
    if not 0 <= weekday <= 6 or not 0 <= cycle_week <= 3:
        return None
    return evening_dinner(cycle_week, weekday)


def _evening_index() -> dict[int, dict[int, tuple]]:
    """(name, detail, kcal, protein, carbs) for callers that still index by week."""
    out: dict[int, dict[int, tuple]] = {}
    for cw in range(4):
        out[cw] = {}
        for wd in range(7):
            meal = evening_dinner(cw, wd)
            out[cw][wd] = meal[1:]
    return out


EVENING_DINNERS = _evening_index()
WEEKDAY_DINNERS = EVENING_DINNERS


# On-bike solids for long rides (~55 g carbs/h; ~4 kcal per g carbohydrate).
_ON_BIKE_G_PER_HR = 55


def on_bike_fuel_kcal(dur_min: int) -> int:
    """Approximate on-bike fuel kcal for a long ride of ``dur_min`` minutes."""
    return round(_ON_BIKE_G_PER_HR * 4 * dur_min / 60)


# ── Flexible meal scaling (protein anchors fixed) ─────────────────────────────

_MAX_MEAL_SCALE_PCT = 0.25  # max ±25% adjustment vs base plate


def _flexible_kcal_budget(slot: str, name: str, kcal: int, prot: int, carbs: int) -> int:
    """kcal that can move without cutting protein anchors."""
    nl = name.lower()
    if slot == "Protein Shake" or prot >= 55 and ("chicken" in nl or "prawn" in nl):
        return min(180, max(0, carbs * 4))
    if slot == "Breakfast":
        return min(120, max(0, kcal - prot * 4 - 60))
    if slot == "Dinner" and prot >= 50:
        return min(160, max(0, carbs * 4))
    if slot in ("AM Snack", "PM Snack", "Eve Snack", "On Waking"):
        return kcal
    if slot in ("On-Bike", "Recovery", "Post-Ruck"):
        return kcal
    if slot == "Lunch":
        return min(200, max(0, carbs * 4))
    return min(80, max(0, kcal - prot * 4))


def scale_meals_to_target(
    meals: list[tuple],
    target_kcal: int,
    *,
    max_adjust_pct: float = _MAX_MEAL_SCALE_PCT,
) -> tuple[list[tuple], dict]:
    """Scale flexible carb/fat portions toward ``target_kcal``; protein grams stay fixed."""
    base_total = sum(m[3] for m in meals)
    gap = target_kcal - base_total
    meta: dict = {
        "adjusted": False,
        "base_kcal": base_total,
        "target_kcal": target_kcal,
        "gap_kcal": gap,
        "note": None,
    }
    if abs(gap) <= 100 or not meals:
        return meals, meta

    max_delta = round(base_total * max_adjust_pct)
    delta = max(-max_delta, min(max_delta, gap))

    flex_budgets = [_flexible_kcal_budget(m[0], m[1], m[3], m[4], m[5]) for m in meals]
    total_flex = sum(flex_budgets)
    if total_flex <= 0:
        meta["note"] = (
            f"Add ~{gap:+d} kcal via larger carb portions or an extra snack "
            "(protein anchors are fixed)."
        )
        meta["gap_kcal"] = gap
        return meals, meta

    scaled: list[tuple] = []
    applied = 0
    for i, (slot, name, detail, kcal, prot, carbs) in enumerate(meals):
        share = flex_budgets[i] / total_flex if total_flex else 0
        add = round(delta * share)
        if add == 0 or flex_budgets[i] == 0:
            scaled.append((slot, name, detail, kcal, prot, carbs))
            applied += kcal
            continue
        new_kcal = max(prot * 4 + 30, kcal + add)
        carb_delta = round(add / 4)
        new_carbs = max(0, carbs + carb_delta)
        adj_detail = detail
        if abs(add) >= 40:
            adj_detail = detail + f" (portion adjusted {add:+d} kcal vs base recipe)"
        scaled.append((slot, name, adj_detail, new_kcal, prot, new_carbs))
        applied += new_kcal

    remaining = target_kcal - applied
    meta["adjusted"] = True
    meta["gap_kcal"] = remaining
    if abs(remaining) > 100:
        meta["note"] = (
            f"Plate adjusted within recipe limits; still ~{remaining:+d} kcal vs target — "
            "top up with an extra carb snack or slightly larger starch portion."
        )
    return scaled, meta


# ── Camp day classification ───────────────────────────────────────────────────

_CAMP_HARD_INTENSITIES = frozenset({"medium", "hard"})


def camp_day_intensity(d: date) -> tuple[str, str | None]:
    """Return (intensity, session_label) for a date inside a camp window."""
    from .plan import TENERIFE_DAYS, session_for_date_extended

    td = next((x for x in TENERIFE_DAYS if x["date"] == d), None)
    if td:
        return td["intensity"], td["label"]
    sess = session_for_date_extended(d)
    if sess is None:
        return "rest", None
    stype, label, dur = sess
    if stype == "rest" or dur <= 0:
        return "rest", label
    if stype in ("vo2", "ftp", "sweetspot", "tempo") or dur >= 120:
        return "hard", label
    if dur >= 60 or stype in ("long", "bike"):
        return "medium", label
    return "easy", label


def is_camp_hard_day(d: date) -> bool:
    intensity, _ = camp_day_intensity(d)
    return intensity in _CAMP_HARD_INTENSITIES


def camp_day_profile(d: date) -> dict | None:
    """Active camp metadata plus today's intensity classification."""
    camp = camp_nutrition_window(d)
    if not camp:
        return None
    intensity, label = camp_day_intensity(d)
    return {
        **camp,
        "intensity": intensity,
        "session_label": label,
        "hard_day": intensity in _CAMP_HARD_INTENSITIES,
    }


def camp_checklist(today: date, target_kcal: int) -> list[str]:
    """Camp-mode eat list — replaces the UK batch-meal checklist."""
    profile = camp_day_profile(today)
    if not profile:
        return []
    pt = protein_target_g()
    items = [
        f"CAMP — {profile['label']}: {profile.get('session_label') or 'see calendar'} "
        f"({profile['intensity']} day)",
        f"Target: ~{target_kcal:,} kcal · UK batch-meal cycle suspended",
    ]
    if profile["hard_day"]:
        items += [
            f"Pre-ride: substantial breakfast 2–3 h before rolling",
            f"On-bike: {profile['on_bike_g_per_hr']} g/h carbs from minute 0 "
            f"(fluids {profile['fluid_ml_per_hr']} ml/h + sodium)",
            f"Recovery: {profile['recovery_window']}",
            "Evening: carb-rich meal + protein anchor — local restaurant or self-cater",
        ]
    else:
        items += [
            profile["easy_day_note"],
            "Light grazing OK — keep protein at the floor across the day",
        ]
    items.append(
        f"Protein floor: {pt['low']}–{pt['high']} g ({profile['protein_g_per_kg']} g/kg in camp)"
    )
    items.append("Full camp nutrition template: /tenerife (nutrition section)")
    return items


def _resolve_day_meals(
    plan_start: date,
    ref_date: date,
    *,
    session_type: str | None = None,
    session_dur: int | None = None,
    session_label: str | None = None,
) -> tuple[list[tuple], dict]:
    """Assemble, scale, and annotate meals for a non-camp day.

    Meal skeleton follows the planned session; kcal comes from ``today_targets``.
    """
    cycle_week = cycle_week_index(plan_start, ref_date)
    weekday = ref_date.weekday()
    dtype = meal_day_type_for_session(
        session_type, session_label, cycle_week, weekday,
        session_dur=session_dur,
    )
    day_data = DAY_TYPES[dtype]
    # Single crowned kcal — same number as dashboard / Cut / email.
    tt = today_targets(ref_date)
    kind = day_kind(tt["calorie_tier"])
    dur = int((tt.get("session") or {}).get("dur_min") or session_dur or 0)
    if kind not in ("hard", "long"):
        dur = 0
    day = _plan_scaled_day(
        cycle_week,
        weekday,
        target_kcal=tt["kcal"],
        protein_low=tt["protein_low"],
        protein_high=tt["protein_high"],
        kind=kind,
        ride=_session_takes_ride_fuel(session_type, session_label),
        dur_min=dur,
        ref_date=ref_date,
    )
    meals = day["tuples"]
    target = {
        "kcal": tt["kcal"],
        "from_tdee": tt["kcal_source"] in ("tdee", "camp"),
        "tdee": tt.get("stable_tdee"),
        "planned_deficit": tt.get("planned_deficit"),
        "static_fallback": FALLBACK_INTAKE_KCAL,
        "camp": bool(tt.get("camp")),
        "maintenance": bool(tt.get("maintenance")),
        "cut_phase": tt.get("cut_phase"),
        "cut_target_kg": tt.get("cut_target_kg", CUT_TARGET_KG),
        "long_fuel_topup": tt.get("long_fuel_topup", 0),
        "tier_deficit": tt.get("tier_deficit"),
        "why": tt.get("why"),
        "phase": tt.get("phase"),
    }
    scale_meta = _scale_meta(day, target["kcal"])
    return meals, {
        "target": target,
        "scale_meta": scale_meta,
        "dtype": dtype,
        "day_data": day_data,
        "cycle_week": cycle_week,
        "meal_rows": day["meals"],
        "totals": day["totals"],
    }


def _plan_scaled_day(
    cycle_week: int,
    weekday: int,
    *,
    target_kcal: int,
    protein_low: int,
    protein_high: int,
    kind: str,
    dur_min: int = 0,
    ref_date: date | None = None,
    ride: bool = True,
) -> dict:
    from .recipes.menu import meals_as_tuples, plan_day

    day = plan_day(
        cycle_week,
        weekday,
        target_kcal=int(target_kcal),
        protein_low=int(protein_low),
        protein_high=int(protein_high),
        kind=kind,
        dur_min=int(dur_min or 0),
        ref_date=ref_date,
        ride=ride,
    )
    day = dict(day)
    day["tuples"] = meals_as_tuples(day)
    return day


def _scale_meta(day: dict, target_kcal: int) -> dict:
    total = int(day["totals"]["kcal"])
    gap = int(target_kcal) - total
    band = max(1, int(round(target_kcal * 0.05)))
    note = None
    if abs(gap) > band:
        note = (
            f"Planned meals are {total:,} kcal, {gap:+d} kcal from the {target_kcal:,} kcal target."
        )
    return {
        "adjusted": abs(day["base_kcal"] - total) > 30,
        "base_kcal": day["base_kcal"],
        "target_kcal": int(target_kcal),
        "gap_kcal": gap,
        "note": note,
        "protein_g": int(day["totals"]["protein"]),
        "dairy_calcium_mg": int(round(day["totals"]["dairy_calcium"])),
    }


def _assemble_meals(
    dtype: str,
    cycle_week: int,
    weekday: int,
    *,
    target_kcal: int | None = None,
    protein_low: int | None = None,
    protein_high: int | None = None,
    dur_min: int = 0,
) -> list[tuple]:
    """Breakfast, lunch, dinner, evening dairy, plus training snacks when the day needs them."""
    tier = "easy"
    if dtype in DAY_TYPES:
        tier = day_kind(DAY_TYPES[dtype].get("calorie_tier"))
    pt = protein_target_g()
    day = _plan_scaled_day(
        cycle_week,
        weekday,
        target_kcal=FALLBACK_INTAKE_KCAL if target_kcal is None else target_kcal,
        protein_low=pt["low"] if protein_low is None else protein_low,
        protein_high=pt["high"] if protein_high is None else protein_high,
        kind=tier if dur_min else tier,
        dur_min=dur_min if tier == "long" else 0,
    )
    return day["tuples"]


def _pre_dinner_protein(meals: list[tuple]) -> int:
    """Sum protein for all meals except the last (evening plate)."""
    if len(meals) <= 1:
        return sum(m[4] for m in meals)
    return sum(m[4] for m in meals[:-1])


# ── Day-type templates ────────────────────────────────────────────────────────
# Meal rows come from meal_library. These keys only name the day and its calorie tier.
_DOSE_NOTE = "Protein is spread across the day. Evening yoghurt is a top-up, not a fixed bowl."

def _day_type(label: str, tier: str) -> dict:
    return {
        "label": label,
        "calorie_tier": tier,
        "pre_dinner_protein_g": 120,
        "protein_note": _DOSE_NOTE,
        "meals": [],
    }

DAY_TYPES: dict[str, dict] = {
    "rest": _day_type("Rest day", "rest"),
    "training": _day_type("Training day", "training"),
    "bike": _day_type("Easy ride", "training"),
    "bike_fri": _day_type("Easy ride", "training"),
    "thursday": _day_type("Training day", "training"),
    "ruck": _day_type("Ruck", "ruck"),
    "long": _day_type("Long ride", "long"),
    "recovery_weekday": _day_type("Easy day", "recovery"),
    "recovery_saturday": _day_type("Easy day", "recovery"),
    "recovery_sunday": _day_type("Long ride", "long"),
}

# ── Day-of-week → day type mapping ────────────────────────────────────────────
# weekday(): 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
# cycle_week: 0=w1, 1=w2, 2=w3, 3=w4 (recovery)
_WEEKDAY_TO_TYPE_BUILD = {
    0: "rest",
    1: "training",
    2: "bike",
    3: "thursday",
    4: "bike_fri",
    5: "ruck",
    6: "long",
}

_WEEKDAY_TO_TYPE_RECOVERY = {
    0: "recovery_weekday",
    1: "recovery_weekday",
    2: "recovery_weekday",
    3: "recovery_weekday",
    4: "recovery_weekday",
    5: "recovery_saturday",
    6: "recovery_sunday",
}

# Rice variety rotations removed — plain batch rice all week; optional seasoning at portion time.

def cycle_week_index(plan_start: date, today: date) -> int:
    days_since_start = (today - plan_start).days
    return max(0, days_since_start // 7) % 4


def prep_cycle_week_index(plan_start: date, today: date) -> int:
    """Cycle week for Sunday component-prep / ahead shopping (Mon–Sun evening plates).

    Fri–Sun you shop and prep components for the week that starts next Monday, so
    advance the reference date to that Monday before indexing. Mon–Thu match
    ``cycle_week_index`` (dinners already belong to the current week).
    """
    if today.weekday() >= 4:  # Fri / Sat / Sun
        today = today + timedelta(days=(7 - today.weekday()))
    return cycle_week_index(plan_start, today)


def prep_week_day_targets(plan_start: date, today: date) -> list[dict]:
    """Mon–Sun targets for the week you are shopping and batching.

    Fri–Sun look ahead to next Monday, matching ``prep_cycle_week_index``.
    """
    if today.weekday() >= 4:
        monday = today + timedelta(days=(7 - today.weekday()))
    else:
        monday = today - timedelta(days=today.weekday())
    out = []
    for offset in range(7):
        ref = monday + timedelta(days=offset)
        tt = today_targets(ref)
        kind = day_kind(tt["calorie_tier"])
        dur = int((tt.get("session") or {}).get("dur_min") or 0)
        if kind not in ("hard", "long"):
            dur = 0
        out.append({
            "kcal": int(tt["kcal"]),
            "protein_low": int(tt["protein_low"]),
            "protein_high": int(tt["protein_high"]),
            "kind": kind,
            "dur_min": dur,
            "date": ref,
        })
    return out


def today_day_type(cycle_week: int, weekday: int) -> str:
    if cycle_week == 3:
        return _WEEKDAY_TO_TYPE_RECOVERY[weekday]
    return _WEEKDAY_TO_TYPE_BUILD[weekday]


_WEEKEND_RUCK_LONG = frozenset({"ruck", "recovery_saturday", "long", "recovery_sunday"})


def meal_day_type_for_session(
    stype: str | None,
    label: str | None,
    cycle_week: int,
    weekday: int,
    *,
    session_dur: int | None = None,
) -> str:
    """Pick a DAY_TYPES key from the planned session (not weekday alone).

    Breakfast/dinner rotation still uses cycle_week × weekday inside
    ``_assemble_meals``; this only chooses the meal-slot skeleton so Rest
    Saturdays never get Post-Ruck copy.
    """
    fallback = today_day_type(cycle_week, weekday)
    if not stype and not label:
        return fallback

    label_l = (label or "").lower()
    is_ruck = stype == "ruck" or "ruck" in label_l
    if is_ruck:
        return "recovery_saturday" if cycle_week == 3 else "ruck"

    if stype in ("long", "back_to_back"):
        return "recovery_sunday" if cycle_week == 3 else "long"

    if stype == "rest":
        if cycle_week == 3 and weekday <= 4:
            return "recovery_weekday"
        return "rest"

    # Active non-ruck/non-long session on a weekday that still maps to ruck/long.
    if fallback in _WEEKEND_RUCK_LONG:
        if stype in ("recovery", "strength", "gym") and not (session_dur or 0):
            return "rest"
        if stype in ("recovery", "strength", "gym"):
            return "rest"
        if weekday == 4:
            return "bike_fri"
        return "bike"

    return fallback


def gut_training_target_g_per_hr(ref: date | None = None) -> int:
    """Progressive in-ride carb target (g/h) for longs ≥150 min — closes the rice-cake gap.

    Charity block: wk 1–6 → 60, wk 7–8 → 75, wk 9+ → 90.
    Haute Route: Base wk 1–8 → 60, wk 9–11 → 75, wk 12+ (camps onward) → 90.
    """
    ref = ref or date.today()
    from .plan import PLAN_START
    charity_end = date(2026, 9, 14)
    if PLAN_START <= ref <= charity_end:
        week = (ref - PLAN_START).days // 7 + 1
        if week < 7:
            return 60
        if week < 9:
            return 75
        return 90
    from .hr_plan import HR_PLAN_START
    if ref >= HR_PLAN_START:
        hr_week = (ref - HR_PLAN_START).days // 7 + 1
        if hr_week < 9:
            return 60
        if hr_week < 12:
            return 75
        return 90
    return 60


# Carb drink bottle size used in weekend-fuel recipes (~55 g maltodextrin + fructose).
_CARB_BOTTLE_G = 60


def fuel_prep_for_ride(duration_min: int, *, ref_date: date | None = None) -> dict:
    """Batch counts for a weekend long ride.

    Rice cakes cover the solid carbohydrate, using one savoury cake's computed
    grams. For rides ≥150 min, maltodextrin/fructose
    **carb drink bottles** close the gap to the gut-training target (60→75→90 g/h).
    Electrolyte bottles remain separate (hydration/sodium).
    """
    h = max(duration_min / 60, 0.5)
    if h <= 1.5:
        cakes, bottles, flapjack = 2, ["E1"], False
    elif h <= 2.25:
        cakes, bottles, flapjack = 4, ["E1"], False
    elif h <= 3.25:
        cakes, bottles, flapjack = 6, ["E1", "E2"], False
    elif h <= 4.25:
        cakes, bottles, flapjack = 8, ["E2"], True
    elif h <= 5.25:
        cakes, bottles, flapjack = 10, ["E2", "E3"], True
    else:
        cakes, bottles, flapjack = 12, ["E3", "E4"], True

    carbs_each = float(_portion_macros(_recipe_by_id("standard-rice-cake"), 1)["carbs"])
    solid_g_per_hr = (cakes * carbs_each) / h
    target = 55
    carb_drink_bottles = 0
    carb_drink_g_per_hr = 0.0
    if duration_min >= 150:
        target = gut_training_target_g_per_hr(ref_date)
        gap = max(0.0, target - solid_g_per_hr)
        if gap > 0:
            carb_drink_bottles = max(1, int(round((gap * h) / _CARB_BOTTLE_G)))
            carb_drink_g_per_hr = round((_CARB_BOTTLE_G * carb_drink_bottles) / h, 1)

    total_g_per_hr = round(solid_g_per_hr + carb_drink_g_per_hr, 1)
    prep_note = (
        f"Make {cakes} homemade savoury rice cakes ({round(carbs_each):.0f} g carbohydrate each); "
        f"mix electrolyte bottles {', '.join(bottles)}."
    )
    if carb_drink_bottles:
        prep_note += (
            f" Mix {carb_drink_bottles}× maltodextrin/fructose carb bottle"
            f"{'s' if carb_drink_bottles != 1 else ''} "
            f"(~{_CARB_BOTTLE_G} g each) to hit ~{target} g/h gut-training target "
            f"(solids ~{solid_g_per_hr:.0f} g/h + drink ~{carb_drink_g_per_hr:.0f} g/h)."
        )
    if flapjack:
        prep_note += " Pack 1 protein bar (or flapjack) as bonk insurance."

    return {
        "duration_min": duration_min,
        "ride_hours": round(h, 1),
        "rice_cakes": cakes,
        "carbs_per_cake": round(carbs_each, 1),
        "bottles": bottles,
        "flapjack": flapjack,
        "banana_before": True,
        "target_g_per_hr": target,
        "solid_g_per_hr": round(solid_g_per_hr, 1),
        "carb_drink_bottles": carb_drink_bottles,
        "carb_drink_g_per_hr": carb_drink_g_per_hr,
        "total_g_per_hr": total_g_per_hr,
        "prep_note": prep_note,
    }


# No live camp-nutrition window. Christmas Tenerife is maintenance, not a carb-load camp.
CAMP_NUTRITION_WINDOWS: list[tuple[date, date, str]] = []

CAMP_NUTRITION = {
    "hard_day_kcal": "3,200–3,800",
    "carbs_g_per_kg": "8–10",
    "protein_g_per_kg": "1.8–2.2",
    "on_bike_g_per_hr": "60–90",
    "fluid_ml_per_hr": "500–750",
    "recovery_window": "60–80 g carbs + 20–30 g protein within 30 min",
    "easy_day_note": "Easy/rest days: −15–20% calories; never cut the protein floor.",
}


def camp_nutrition_window(d: date | None = None) -> dict | None:
    """Return active camp nutrition block if `d` falls in a Tenerife camp window."""
    d = d or date.today()
    for start, end, label in CAMP_NUTRITION_WINDOWS:
        if start <= d <= end:
            return {"label": label, "start": start, "end": end, **CAMP_NUTRITION}
    return None


def in_camp_nutrition_window(d: date | None = None) -> bool:
    return camp_nutrition_window(d) is not None


def _sunday_planned_ride_min(plan_start: date, ref: date) -> int | None:
    """Planned Sunday long-ride duration from the training plan, if any."""
    try:
        from .plan import session_for_date_extended
        days_ahead = (6 - ref.weekday()) % 7
        sunday = ref + timedelta(days=days_ahead)
        if sunday == ref and ref.weekday() != 6:
            sunday += timedelta(days=7)
        result = session_for_date_extended(sunday)
        if result is None:
            return None
        stype, _label, dur = result
        if stype in ("long", "bike") and dur >= 75:
            return dur
    except Exception:
        logger.warning("_sunday_planned_ride_min failed", exc_info=True)
    return None


def fuel_prep_context(plan_start: date, today: date) -> str:
    """Friday/Saturday prep line for the coming Sunday long ride."""
    ride_min = _sunday_planned_ride_min(plan_start, today)
    if ride_min is None:
        return ""
    prep = fuel_prep_for_ride(ride_min, ref_date=today)
    h = prep["ride_hours"]
    bottles = " + ".join(prep["bottles"])
    flap = " · pack 1 backstop bar" if prep["flapjack"] else ""
    carb = ""
    if prep.get("carb_drink_bottles"):
        carb = (
            f" · **{prep['carb_drink_bottles']}× carb drink bottle"
            f"{'s' if prep['carb_drink_bottles'] != 1 else ''}** "
            f"(target ~{prep['target_g_per_hr']} g/h)"
        )
    return (
        f"Sunday long ride ~{h} h → make **{prep['rice_cakes']} homemade savoury rice cakes** tonight, "
        f"mix **{bottles}** electrolyte bottles{carb}{flap}."
    )


# Session types that count as rides for in-ride fuelling purposes.
_RIDE_TYPES = {
    "long", "bike", "tempo", "ftp", "vo2", "sweetspot", "endurance",
    "back_to_back", "threshold",
}


def _session_takes_ride_fuel(stype: str | None, label: str | None) -> bool:
    """Outdoor bike days take on-bike fuel. Rower and MaxiClimber do not."""
    low = (label or "").lower()
    if stype in {"rower", "maxiclimber"} or "rower" in low or "maxiclimber" in low:
        return False
    if stype in _RIDE_TYPES or stype in {"long", "bike"}:
        return True
    return stype not in {"rower", "maxiclimber", "strength", "hike", "ruck", "rest"}
_HARD_SESSION_TYPES = {"tempo", "ftp", "vo2", "sweetspot", "threshold"}

# Plan / HR session type → calorie deficit tier.
_SESSION_CALORIE_TIER: dict[str, str] = {
    "long": "long",
    "back_to_back": "long",
    "rest": "rest",
    "recovery": "recovery",
    "gym": "recovery",
    "strength": "recovery",
    "ruck": "ruck",
}


def calorie_tier_for_session(
    stype: str | None,
    weekday_tier: str,
    label: str | None = None,
) -> str:
    """Map a planned session onto easy, hard, or long.

    Easy covers rest, recovery and ordinary training. Threshold and VO2 days
    are hard so the deficit is smaller. Long rides are maintenance plus ride fuel.
    """
    if not stype and not label:
        return day_kind(weekday_tier)
    low = (label or "").lower()
    if stype in _HARD_SESSION_TYPES or any(tok in low for tok in ("threshold", "vo2", "tempo", "sweetspot")):
        return "hard"
    if stype in ("long", "back_to_back"):
        return "long"
    if not stype:
        return day_kind(weekday_tier)
    return "easy"


_TIER_WHY_LABEL = {
    "easy": "Easy day",
    "rest": "Easy day",
    "recovery": "Easy day",
    "training": "Easy day",
    "ruck": "Easy day",
    "long": "Long ride",
    "hard": "Hard day",
}


def _intake_phase(target: dict) -> str:
    if target.get("camp"):
        return "camp"
    if target.get("maintenance"):
        return "maintenance"
    phase = target.get("cut_phase")
    if phase:
        return phase
    return "default"


def format_intake_why(
    target: dict,
    tier: str,
    *,
    session: dict | None = None,
) -> str:
    """Plain-English one-liner for why today's intake target is what it is."""
    _ = session
    phase = _intake_phase(target)
    kcal = target.get("kcal")
    tdee = target.get("tdee")
    tier_deficit = target.get("tier_deficit")
    topup = int(target.get("long_fuel_topup") or 0)
    label = _TIER_WHY_LABEL.get(tier, tier.replace("_", " ").title())

    if phase == "camp":
        return (
            f"Camp day — UK deficit suspended · eat ~{kcal:,} kcal"
            if kcal is not None
            else "Camp day — UK deficit suspended"
        )

    if phase == "maintenance":
        if tdee is not None and kcal is not None:
            return (
                f"Maintenance — no deficit · eat at weekly burn {tdee:,}"
            )
        return "Maintenance — no deficit"

    if tdee is not None and kcal is not None and tier_deficit is not None:
        if topup > 0:
            return (
                f"{label}: weekly burn {tdee:,} − {tier_deficit} "
                f"+ {topup} top-up → eat {kcal:,}"
            )
        if phase == "ease":
            extra = ""
            if tier == "hard":
                extra = " Carbohydrate stays high on this hard day; protein stays at the floor."
            return (
                f"{label} (ease): weekly burn {tdee:,} − {tier_deficit} → eat {kcal:,}.{extra}"
            )
        return f"{label}: weekly burn {tdee:,} − {tier_deficit} → eat {kcal:,}"

    if kcal is not None:
        return f"{label} · ~{kcal:,} kcal target"
    return f"{label} · follow the prescribed plate"


def _optional_session_work_kcal(
    stype: str | None,
    label: str | None,
    dur: int,
) -> int | None:
    """Context-only estimated ride work (kcal); does not change the prescription."""
    if not stype or dur <= 0 or stype not in _RIDE_TYPES:
        return None
    try:
        from .history import load_ftp_tests
        from .hr_plan import power_target_for
        from .energy import planned_session_kj

        tests = load_ftp_tests()
        ftp_w = None
        for row in reversed(tests or []):
            if row.get("ftp_w"):
                ftp_w = int(row["ftp_w"])
                break
        if not ftp_w:
            return None
        pt = power_target_for(stype, label or "")
        if not isinstance(pt, tuple) or len(pt) != 2:
            # Charity-plan defaults by intensity family
            defaults = {
                "long": (56, 75),
                "back_to_back": (56, 75),
                "endurance": (56, 75),
                "bike": (56, 75),
                "tempo": (88, 94),
                "sweetspot": (88, 94),
                "vo2": (106, 120),
                "ftp": (100, 100),
            }
            pt = defaults.get(stype)
            if not pt:
                return None
        lo, hi = pt
        kj = planned_session_kj(ftp_w, lo, hi, dur)
        return ride_kcal_from_kj(kj) if kj else None
    except Exception:
        logger.warning("_optional_session_work_kcal failed", exc_info=True)
        return None


def today_targets(ref_date: date | None = None) -> dict:
    """Single source of truth for today's nutrition numbers.

    Crowns exactly one of each — every surface (dashboard, /nutrition, coach
    context, email) should read from here rather than picking its own number:
      kcal       — resolve_calorie_target (stable TDEE when available, else
                   static tier; camp, maintenance, and cut phases applied)
      protein    — protein_target_g() floor/ceiling (lean-mass based)
      carbs g/h  — gut_training_target_g_per_hr() for rides ≥150 min;
                   55 g/h solids for 75–150 min rides; None otherwise
    The Garmin calorie goal and cached AI nutrition_targets are deliberately
    NOT consulted — they are context, not prescriptions.
    """
    ref = ref_date or date.today()

    # Planned session, override-aware (charity blocks first, then HR plan).
    session = None
    try:
        from .plan import session_for_date_extended
        sess = session_for_date_extended(ref)
        if sess is None:
            from .hr_plan import hr_session_for_date
            sess = hr_session_for_date(ref)
        if sess is not None:
            stype, label, dur = sess
            try:
                from .history import get_plan_override
                ov = get_plan_override(ref.isoformat())
                if ov:
                    stype = ov.get("session_type") or stype
                    label = ov.get("label") or label
                    dur = ov.get("duration_min") or dur
            except Exception:
                logger.warning("today_targets failed", exc_info=True)
            session = {"type": stype, "label": label, "dur_min": dur}
    except Exception:
        logger.warning("today_targets failed", exc_info=True)
    stype = session["type"] if session else None
    label = session["label"] if session else None
    dur = session["dur_min"] if session else 0

    # One kcal number — session type drives the deficit tier.
    from .plan import PLAN_START
    cycle_week = cycle_week_index(PLAN_START, ref)
    weekday_tier = DAY_TYPES[today_day_type(cycle_week, ref.weekday())]["calorie_tier"]
    tier = calorie_tier_for_session(stype, weekday_tier, label)
    long_dur = dur if tier == "long" or stype in ("long", "back_to_back") else None
    target = resolve_calorie_target(
        _stable_tdee(), tier, ref,
        session_dur_min=long_dur,
        session_type=stype,
    )

    pt = protein_target_g(ref)

    # One in-ride carbs number (+ prep detail for long rides).
    # Rower and MaxiClimber never get an on-bike number, including short hard rows.
    carbs_g_per_hr = None
    fuel_prep = None
    is_ride = (
        _session_takes_ride_fuel(stype, label)
        and stype in _RIDE_TYPES
        and dur >= 75
    )
    if is_ride:
        if dur >= 150:
            carbs_g_per_hr = gut_training_target_g_per_hr(ref)
            fuel_prep = fuel_prep_for_ride(dur, ref_date=ref)
        else:
            carbs_g_per_hr = _ON_BIKE_G_PER_HR

    # Cached AI fuelling plan — expandable detail only, never the headline number.
    ai_fuel_plan = None
    if is_ride:
        try:
            from .analysis import _load_fuelling_plans, fuelling_session_key
            ai_fuel_plan = _load_fuelling_plans().get(fuelling_session_key(stype, dur))
        except Exception:
            logger.warning("today_targets failed", exc_info=True)

    phase = _intake_phase(target)
    why = format_intake_why(target, tier, session=session)
    session_work = _optional_session_work_kcal(stype, label, dur)

    return {
        "date": ref.isoformat(),
        "session": session,
        "kcal": target["kcal"],
        "kcal_source": "camp" if target.get("camp") else ("tdee" if target.get("from_tdee") else "tier"),
        "calorie_tier": tier,
        "stable_tdee": target.get("tdee"),
        "planned_deficit": target.get("planned_deficit"),
        "tier_deficit": target.get("tier_deficit"),
        "long_fuel_topup": target.get("long_fuel_topup", 0),
        "maintenance": bool(target.get("maintenance")),
        "cut_phase": target.get("cut_phase"),
        "cut_target_kg": target.get("cut_target_kg", CUT_TARGET_KG),
        "phase": phase,
        "why": why,
        "session_work_kcal": session_work,
        "protein_low": pt["low"],
        "protein_high": pt["high"],
        "protein_g": round((pt["low"] + pt["high"]) / 2),
        "protein_basis": pt["basis"],
        "protein_lean_locked": bool(pt.get("lean_locked")),
        "carbs_g_per_hr": carbs_g_per_hr,
        "fuel_prep": fuel_prep,
        "ai_fuel_plan": ai_fuel_plan,
        "camp": camp_day_profile(ref),
    }


_CARB_LINE = {
    "easy": "fits today's calories, after protein and some fat",
    "hard": "fits today's calories, with more of them around the session",
    "long": "fits today's calories. On-bike grams per hour are part of this, not extra",
}


def carbs_g_for_kcal(kcal: int, protein_g: int) -> int:
    """Carbohydrate grams that still fit the day's calories.

    Protein is 4 kcal/g. About a quarter of the day is left for fat. The
    rest is carbohydrate. If protein and that fat floor already use the
    day, carbohydrate is whatever is left after protein.
    """
    if kcal <= 0:
        return 0
    protein_kcal = max(int(protein_g), 0) * 4
    fat_kcal = int(round(kcal * 0.25))
    if protein_kcal + fat_kcal >= kcal:
        return max(kcal - protein_kcal, 0) // 4
    return (kcal - protein_kcal - fat_kcal) // 4
_KIND_LABEL = {"easy": "Easy", "hard": "Hard", "long": "Long"}


def _litres(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def today_card(ref_date: date | None = None) -> dict:
    """The four numbers and one habit for Today and the email."""
    ref = ref_date or date.today()
    tt = today_targets(ref)
    kind = day_kind(tt["calorie_tier"])
    protein_g = int(tt["protein_g"])
    protein_line = (
        f"{tt['protein_low']}–{tt['protein_high']} g across breakfast, lunch, dinner, "
        "and evening yoghurt if the day still needs it"
    )
    carbs_g = carbs_g_for_kcal(int(tt["kcal"]), protein_g)
    sess = tt.get("session") or {}
    dur = 0
    if sess.get("type") not in (None, "rest") and sess.get("dur_min"):
        dur = int(sess["dur_min"])
    fluid = fluid_target_litres(dur)
    fluids_note = "urine pale"
    if fluid["extra_l"]:
        fluids_note = "includes 0.5 L per training hour · urine pale"
    return {
        "kind": kind,
        "kind_label": _KIND_LABEL[kind],
        "kcal": tt["kcal"],
        "protein_g": protein_g,
        "protein_line": protein_line,
        "carbs_g": carbs_g,
        "carbs_line": _CARB_LINE[kind],
        "fluids": f"{_litres(fluid['low_l'])}–{_litres(fluid['high_l'])} L",
        "fluids_note": fluids_note,
        "habit": HABIT_LINE,
        "stone_line": STONE_SAFE_LINE,
        "why": tt.get("why"),
        "tdee": tt.get("stable_tdee"),
        "deficit": tt.get("planned_deficit"),
        "protein_basis": tt.get("protein_basis"),
        "protein_low": tt["protein_low"],
        "protein_high": tt["protein_high"],
        "maintenance": bool(tt.get("maintenance")),
        "carbs_g_per_hr": tt.get("carbs_g_per_hr"),
    }


def today_checklist(plan_start: date, today: date) -> list[str]:
    """3–6 bullets: what to eat/follow today."""
    camp_profile = camp_day_profile(today)
    if camp_profile:
        target = resolve_calorie_target(
            _stable_tdee(), "training", today,
            session_type="bike" if camp_profile["hard_day"] else "rest",
        )
        return camp_checklist(today, target["kcal"])

    from .plan import session_for_date_extended

    session = session_for_date_extended(today)
    session_type = session[0] if session else None
    session_label = session[1] if session else None
    session_dur = session[2] if session else None
    meals, _ctx = _resolve_day_meals(
        plan_start, today,
        session_type=session_type, session_dur=session_dur, session_label=session_label,
    )
    card = today_card(today)
    items = [
        f"{card['kind_label']} · {card['kcal']:,} kcal",
        f"Protein {card['protein_g']} g · {card['protein_line']}",
        f"Carbs {card['carbs_g']} g · {card['carbs_line']}",
        f"Fluids {card['fluids']} · {card['fluids_note']}",
        card["habit"],
        card["stone_line"],
    ]
    for meal in meals:
        items.append(f"{meal[0]}: {meal[1]}")
    if card.get("carbs_g_per_hr"):
        items.append(f"On the bike: {card['carbs_g_per_hr']} g/h")
    return items


_BADGE_BY_TYPE = {
    "rest": "badge-rest",
    "training": "badge-train",
    "bike": "badge-ride",
    "bike_fri": "badge-ride",
    "thursday": "badge-train",
    "ruck": "badge-ruck",
    "long": "badge-long",
    "recovery_weekday": "badge-recovery",
    "recovery_saturday": "badge-ruck",
    "recovery_sunday": "badge-long",
}

# Plan session types (from plan.py / overrides) → meals.html badge colours.
_BADGE_BY_SESSION_TYPE = {
    "rest": "badge-rest",
    "strength": "badge-train",
    "gym": "badge-train",
    "bike": "badge-ride",
    "tempo": "badge-ride",
    "ftp": "badge-ride",
    "sweetspot": "badge-ride",
    "recovery": "badge-recovery",
    "ruck": "badge-ruck",
    "long": "badge-long",
}

_DELOAD_PLAN_WEEKS = frozenset({4, 8})

_WEEK_BANNERS = {
    i: (
        "<strong>Sunday batch.</strong> Two one-pots and one soup cover the weekday lunches "
        "and Monday to Thursday dinners. Friday dinner is a quick griddle plate. "
        "The batch is sized to those plates. Saturday and Sunday are cooked fresh. "
        "<a href=\"/nutrition#batch\">Batch cook</a>."
    )
    for i in range(4)
}


def _session_badge_label(stype: str, label: str, dur_min: int) -> str:
    """Calendar-style badge text: label plus duration when the session has one."""
    text = label.strip()
    if dur_min > 0:
        return f"{text} · {dur_min} min"
    return text


def _plan_week_meta(plan_start: date, today: date) -> tuple[int | None, bool]:
    """Return (1-based plan week number, is_deload) for today, or (None, False) outside the 12-week block."""
    from .plan import _PLAN_DAYS
    delta = (today - plan_start).days
    if delta < 0 or delta >= _PLAN_DAYS:
        return None, False
    week_num = delta // 7 + 1
    return week_num, week_num in _DELOAD_PLAN_WEEKS


def build_this_meal_week(plan_start: date, today: date) -> dict:
    """Date-anchored week for meals.html — badges from the training calendar, meals from the nutrition cycle."""
    from .plan import session_for_date_extended

    monday = today - timedelta(days=today.weekday())
    week_num, is_deload = _plan_week_meta(plan_start, monday)
    cycle_week = cycle_week_index(plan_start, today)

    if week_num is not None:
        phase = "deload" if is_deload else "build"
        banner = (
            f"<strong>This week — plan week {week_num} ({phase}).</strong> "
            "Workout badges match the <a href=\"/calendar\">training calendar</a> "
            "(including overrides). Weekday lunches and Monday to Thursday dinners come from "
            "Sunday's batch. Friday dinner is a quick griddle plate. "
            "<a href=\"/nutrition#batch\">Batch cook</a>."
        )
    else:
        banner = (
            "<strong>This week.</strong> Workout badges match the training calendar where a "
            "session is planned. Weekday lunches and Monday to Thursday dinners come from "
            "Sunday's batch. Friday dinner is a quick griddle plate. "
            "<a href=\"/nutrition#batch\">Batch cook</a>."
        )

    days_out = []
    stable = _stable_tdee()
    for wd in range(7):
        d = monday + timedelta(days=wd)
        day_cycle = cycle_week_index(plan_start, d)
        dtype = today_day_type(day_cycle, wd)
        dd = DAY_TYPES[dtype]
        tier_key = dd["calorie_tier"]

        session = session_for_date_extended(d)
        if session is not None:
            stype, label, dur = session
            badge_text = _session_badge_label(stype, label, dur)
            badge = _BADGE_BY_SESSION_TYPE.get(stype, _BADGE_BY_TYPE.get(dtype, "badge-rest"))
            session_type, session_dur, session_label = stype, dur, label
        else:
            badge_text = dd["label"]
            badge = _BADGE_BY_TYPE.get(dtype, "badge-rest")
            session_type, session_dur, session_label = None, None, None

        camp_prof = camp_day_profile(d)
        if camp_prof:
            target = resolve_calorie_target(
                stable, tier_key, d,
                session_dur_min=session_dur,
                session_type=session_type,
            )
            days_out.append({
                "name": f"{_WEEKDAY_LABELS[wd][:3]} {d.day} {d.strftime('%b')}",
                "badge": "badge-long" if camp_prof["hard_day"] else "badge-recovery",
                "type": camp_prof.get("session_label") or camp_prof["label"],
                "kcal": f"~{target['kcal']:,} kcal (camp)",
                "meals": [],
                "camp_mode": True,
                "preDinP": 0,
                "note": f"Camp {camp_prof['intensity']} day — UK plate suspended.",
                "noteWarn": False,
            })
            continue

        meals, ctx = _resolve_day_meals(
            plan_start, d,
            session_type=session_type, session_dur=session_dur, session_label=session_label,
        )
        target = ctx["target"]
        meal_dtype = ctx["dtype"]

        days_out.append({
            "name": f"{_WEEKDAY_LABELS[wd][:3]} {d.day} {d.strftime('%b')}",
            "badge": badge,
            "type": badge_text,
            "kcal": f"~{target['kcal']:,} kcal",
            "meals": [_meal_dict(m) for m in meals],
            "preDinP": _pre_dinner_protein(meals),
            "note": ctx["day_data"]["protein_note"],
            "noteWarn": meal_dtype == "thursday",
        })

    return {
        "banner": banner,
        "recovery": cycle_week == 3,
        "days": days_out,
    }


def build_meal_week(cycle_week: int) -> dict:
    """Structured week data for meals.html (server-rendered)."""
    stable = _stable_tdee()
    days_out = []
    ref_date = date.today()
    for wd in range(7):
        dtype = today_day_type(cycle_week, wd)
        dd = DAY_TYPES[dtype]
        target = resolve_calorie_target(stable, dd["calorie_tier"], ref_date)
        pt_week = protein_target_g(ref_date)
        meals = _assemble_meals(
            dtype, cycle_week, wd,
            target_kcal=target["kcal"],
            protein_low=pt_week["low"],
            protein_high=pt_week["high"],
        )
        days_out.append({
            "name": _WEEKDAY_LABELS[wd],
            "badge": _BADGE_BY_TYPE.get(dtype, "badge-rest"),
            "type": dd["label"],
            "kcal": f"~{target['kcal']:,} kcal",
            "meals": [_meal_dict(m) for m in meals],
            "preDinP": _pre_dinner_protein(meals),
            "note": dd["protein_note"],
            "noteWarn": dtype == "thursday",
        })
    return {
        "banner": _WEEK_BANNERS.get(cycle_week, _WEEK_BANNERS[0]),
        "recovery": False,
        "days": days_out,
    }


def meal_recipe_url(
    slot: str,
    name: str,
    *,
    cycle_week: int | None = None,
    weekday: int | None = None,
) -> str | None:
    """Recipe index anchor for a prescribed meal, or None if the library has no dish."""
    del cycle_week, weekday
    from .meal_library import recipe_url
    return recipe_url(slot, name)


_NUTRITION_PATH_RE = re.compile(r"/nutrition/[^\s.<]+")


def _linkify_meal_detail(detail: str, recipe_url: str | None = None) -> str:
    """Escape detail text and turn /nutrition/... paths into links.

    Generic Sunday hub paths in dinner Methods copy are rewritten to
    ``recipe_url`` (the specific plate card) when that URL is provided.
    """
    if not detail:
        return ""

    parts: list[str] = []
    last = 0
    for match in _NUTRITION_PATH_RE.finditer(detail):
        parts.append(html.escape(detail[last:match.start()]))
        path = match.group(0)
        trail = ""
        while path and path[-1] in ".,);:":
            trail = path[-1] + trail
            path = path[:-1]
        href = path
        if recipe_url and (
            path == "/nutrition/sunday"
            or path.startswith("/nutrition/sunday")
        ):
            href = recipe_url
        parts.append(f'<a href="{html.escape(href)}">{html.escape(path)}</a>')
        if trail:
            parts.append(html.escape(trail))
        last = match.end()
    parts.append(html.escape(detail[last:]))
    from .html_sanitize import sanitize_html
    return sanitize_html("".join(parts))


def _meal_dict(meal: tuple, recipe_url: str | None = None) -> dict:
    slot, name, detail, kcal, prot, carbs = meal
    fat_g = max(0, (kcal - prot * 4 - carbs * 4) // 9)
    return {
        "type": slot,
        "name": name,
        "detail": detail,
        "detail_html": _linkify_meal_detail(detail, recipe_url) if detail else "",
        "recipe_url": recipe_url,
        "prot": prot,
        "macros": {"kcal": str(kcal), "p": str(prot), "c": str(carbs), "f": str(fat_g) if fat_g else ""},
    }


def build_today_food(plan_start: date, today: date) -> dict:
    """Structured today meals for the Nutrition Today page (hero-first eat list)."""
    from .plan import session_for_date_extended

    session = session_for_date_extended(today)
    session_type = session[0] if session else None
    session_label = session[1] if session else None
    session_dur = session[2] if session else None
    if session is not None:
        stype, label, dur = session
        badge_text = _session_badge_label(stype, label, dur)
        badge = _BADGE_BY_SESSION_TYPE.get(stype, _BADGE_BY_TYPE.get("rest", "badge-rest"))
    else:
        badge_text = None
        badge = "badge-rest"

    tt = today_targets(today)
    pt = protein_target_g(today)

    camp_profile = camp_day_profile(today)
    if camp_profile:
        return {
            "camp_mode": True,
            "camp": camp_profile,
            "day_name": today.strftime("%A %-d %B"),
            "badge": "badge-long" if camp_profile["hard_day"] else "badge-recovery",
            "session": camp_profile.get("session_label") or camp_profile["label"],
            "kcal_target": tt["kcal"],
            "kcal_from_tdee": tt["kcal_source"] in ("tdee", "camp"),
            "planned_deficit": tt.get("planned_deficit"),
            "stable_tdee": tt.get("stable_tdee"),
            "maintenance": False,
            "phase": tt.get("phase"),
            "why": tt.get("why"),
            "protein_low": pt["low"],
            "protein_high": pt["high"],
            "carbs_g_per_hr": None,
            "meals": [],
            "meals_kcal_total": None,
            "checklist": camp_checklist(today, tt["kcal"]),
            "pre_din_p": 0,
            "protein_note": camp_profile["easy_day_note"] if not camp_profile["hard_day"] else (
                f"Hard camp day — {camp_profile['carbs_g_per_kg']} g/kg carbs, "
                f"{camp_profile['protein_g_per_kg']} g/kg protein."
            ),
            "cycle_week": cycle_week_index(plan_start, today),
        }

    meals, ctx = _resolve_day_meals(
        plan_start, today,
        session_type=session_type, session_dur=session_dur, session_label=session_label,
    )
    target = ctx["target"]
    scale_meta = ctx["scale_meta"]
    day_data = ctx["day_data"]
    cycle_week = ctx["cycle_week"]
    weekday = today.weekday()
    if badge_text is None:
        badge_text = day_data["label"]
        badge = _BADGE_BY_TYPE.get(ctx["dtype"], "badge-rest")

    meal_dicts = []
    for meal, row in zip(meals, ctx["meal_rows"]):
        item = _meal_dict(
            meal,
            recipe_url=meal_recipe_url(
                meal[0], meal[1], cycle_week=cycle_week, weekday=weekday,
            ),
        )
        item["multiplier"] = row.get("multiplier")
        item["side_multiplier"] = row.get("side_multiplier")
        item["grams_by_food"] = row.get("grams_by_food") or {}
        item["recipe_id"] = row.get("recipe_id")
        if row.get("display_ingredients") is not None:
            item["display_ingredients"] = list(row["display_ingredients"])
        if row.get("rice_cakes"):
            item["rice_cakes"] = row["rice_cakes"]
        meal_dicts.append(item)

    return {
        "camp_mode": False,
        "day_name": today.strftime("%A %-d %B"),
        "badge": badge,
        "session": badge_text,
        "kcal_target": tt["kcal"],
        "kcal_from_tdee": tt["kcal_source"] in ("tdee", "camp"),
        "planned_deficit": tt.get("planned_deficit"),
        "stable_tdee": tt.get("stable_tdee"),
        "maintenance": bool(tt.get("maintenance")),
        "phase": tt.get("phase"),
        "why": tt.get("why"),
        "protein_low": pt["low"],
        "protein_high": pt["high"],
        "carbs_g_per_hr": tt.get("carbs_g_per_hr"),
        "meals": meal_dicts,
        "meals_kcal_total": int(ctx["totals"]["kcal"]),
        "meals_protein_total": int(ctx["totals"]["protein"]),
        "dairy_calcium_mg": int(round(ctx["totals"]["dairy_calcium"])),
        "scale_meta": scale_meta,
        "pre_din_p": _pre_dinner_protein(meals),
        "protein_note": day_data["protein_note"],
        "cycle_week": cycle_week,
    }


def nutrition_coach_context(plan_start: date, today: date) -> str:
    """Return a compact text block describing today's prescribed nutrition."""
    from .plan import session_for_date_extended

    pt = protein_target_g()
    session = session_for_date_extended(today)
    if session is not None:
        stype, label, dur = session
        plan_line = f"Plan session: {_session_badge_label(stype, label, dur)}"
        session_type, session_dur, session_label = stype, dur, label
    else:
        plan_line = "Plan session: (none scheduled)"
        session_type, session_dur, session_label = None, None, None

    camp_profile = camp_day_profile(today)
    if camp_profile:
        target = resolve_calorie_target(
            _stable_tdee(), "training", today,
            session_dur_min=session_dur, session_type=session_type,
        )
        lines = [
            "## Nutrition Plan — CAMP MODE (UK cycle suspended)",
            f"Camp: {camp_profile['label']}  |  {plan_line}",
            f"Intensity: {camp_profile['intensity']}  |  "
            f"Target today: {target['kcal']:,} kcal",
            f"Hard-day band: {camp_profile['hard_day_kcal']} kcal  |  "
            f"Carbs: {camp_profile['carbs_g_per_kg']} g/kg  |  "
            f"Protein: {camp_profile['protein_g_per_kg']} g/kg",
            f"On-bike: {camp_profile['on_bike_g_per_hr']} g/h carbs  |  "
            f"Fluids: {camp_profile['fluid_ml_per_hr']} ml/h",
            f"Recovery: {camp_profile['recovery_window']}",
            camp_profile["easy_day_note"],
            f"Protein floor: {pt['low']}–{pt['high']}g/day ({pt['basis']}).",
            "Eat locally / self-cater — see /tenerife nutrition template. "
            "Do NOT follow the UK batch-meal plate during camp.",
            "",
            "Today's camp checklist:",
        ]
        for item in camp_checklist(today, target["kcal"]):
            lines.append(f"  • {item}")
        return "\n".join(lines)

    meals, ctx = _resolve_day_meals(
        plan_start, today,
        session_type=session_type, session_dur=session_dur, session_label=session_label,
    )
    target = ctx["target"]
    scale_meta = ctx["scale_meta"]
    day_data = ctx["day_data"]
    dtype = ctx["dtype"]
    cycle_week = ctx["cycle_week"]
    tier = {"label": day_kind(day_data["calorie_tier"]).title(), "note": None}
    cycle_label = f"Week {cycle_week + 1}"

    total_protein = sum(m[4] for m in meals)
    pre_din = _pre_dinner_protein(meals)

    if target.get("from_tdee"):
        if target.get("maintenance"):
            target_line = (
                f"Target: {target['kcal']:,} kcal (stable TDEE {target['tdee']:,} — "
                f"MAINTENANCE WINDOW, deficits suspended)"
            )
        else:
            target_line = (
                f"Target: {target['kcal']:,} kcal (stable TDEE {target['tdee']:,} − {target['planned_deficit']} kcal "
                f"{day_data['label'].lower()})"
            )
        tier_note = tier.get("note")
        if tier_note:
            target_line += f" — {tier_note}"
    else:
        target_line = (
            f"Target: {target['kcal']} kcal (plate-sized; TDEE unavailable)"
            + (f" ({tier['note']})" if tier.get("note") else "")
        )

    card = today_card(today)
    lines = [
        "## Nutrition — four numbers",
        f"Calories ({card['kind_label']}): {card['kcal']:,} kcal",
        f"Protein: {card['protein_g']} g. {card['protein_line']}",
        f"Carbs: {card['carbs_g']} g. {card['carbs_line']}",
        f"Fluids: {card['fluids']}. {card['fluids_note']}",
        f"Habit: {card['habit']}",
        card["stone_line"],
        "",
        "## Nutrition Plan — Today's Prescribed Meals",
        f"Cycle: {cycle_label}  |  Day type: {day_data['label']}  |  {target_line}",
        plan_line,
    ]
    if scale_meta.get("adjusted"):
        lines.append(
            f"Portions scaled to target (base plate {scale_meta['base_kcal']} kcal)."
        )
    if scale_meta.get("note"):
        lines.append(f"Note: {scale_meta['note']}")
    lines.append(f"Breakfast pattern: {_BREAKFAST_LABEL}")
    fuel_line = fuel_prep_context(plan_start, today)
    if fuel_line and today.weekday() in (4, 5):
        lines.append(f"Weekend fuel prep: {fuel_line.replace('**', '')}")
    lines += [
        f"Protein floor: {pt['low']}–{pt['high']}g/day ({pt['basis']}).",
        f"Today's meals deliver: {total_protein}g total  |  "
        f"Pre-dinner: {pre_din}g  — {day_data['protein_note']}",
        "",
        "Meals:",
    ]

    for slot, name, detail, _kcal, _prot, _carbs in meals:
        lines.append(f"  {slot}: {name}")
        lines.append(f"    {detail}")

    lines += ["", "Simple rules:"]
    for r in SIMPLE_RULES:
        lines.append(f"  • {r}")

    lines += ["", f"Supplements ({_SUPPLEMENT_DISCLAIMER}):"]
    for name, dose, why in SUPPLEMENTS:
        lines.append(f"  • {name} — {dose}: {why}")

    return "\n".join(lines)


_WEEKDAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def nutrition_week_context(plan_start: date, today: date) -> str:
    """Compact Mon–Sun overview of this week's prescribed meals."""
    cycle_week = cycle_week_index(plan_start, today)
    cycle_label = f"Week {cycle_week + 1}" + (" — Recovery" if cycle_week == 3 else "")
    monday = today - timedelta(days=today.weekday())

    lines = [
        "## Nutrition Plan — This Week (Mon–Sun)",
        f"Cycle: {cycle_label}. {_BREAKFAST_LABEL}. "
        "For the full 4-week cycle and shopping tally, call get_meal_cycle.",
    ]
    for wd in range(7):
        d = monday + timedelta(days=wd)
        dtype = today_day_type(cycle_week, wd)
        day_data = DAY_TYPES[dtype]
        meals, day_ctx = _resolve_day_meals(plan_start, d)
        target = day_ctx["target"]
        total_protein = sum(meal[4] for meal in meals)
        marker = "  ← today" if d == today else ""
        lines.append(
            f"  {_WEEKDAY_LABELS[wd][:3]} {d.strftime('%d %b')}: {day_data['label']} "
            f"— {target['kcal']} kcal, ~{total_protein}g protein{marker}"
        )
        for slot, name, _detail, kcal, prot, _carbs in meals:
            lines.append(f"      {slot}: {name} ({kcal} kcal, {prot}g P)")
    ride_min = _sunday_planned_ride_min(plan_start, today)
    if ride_min:
        prep = fuel_prep_for_ride(ride_min, ref_date=today)
        carb = ""
        if prep.get("carb_drink_bottles"):
            carb = (
                f", {prep['carb_drink_bottles']}× carb drink "
                f"(~{prep['target_g_per_hr']} g/h)"
            )
        lines.append(
            f"  Sunday fuel prep (Fri eve): {prep['rice_cakes']} homemade savoury rice cakes, "
            f"bottles {', '.join(prep['bottles'])}{carb}"
            + (" + backstop bar" if prep["flapjack"] else "")
        )
    return "\n".join(lines)


def _meal_components(name: str) -> list[str]:
    """Split a composite meal name (joined with ' + ') into shopping items."""
    return [p.strip() for p in re.split(r"\s*\+\s*", name) if p.strip()]


def _week_shopping_tally(cycle_week: int) -> list[tuple[str, int]]:
    """Count how many times each meal component recurs across one cycle week."""
    counter: Counter[str] = Counter()
    for wd in range(7):
        dtype = today_day_type(cycle_week, wd)
        day_data = DAY_TYPES[dtype]
        for _slot, name, _detail, _kcal, _prot, _carbs in _assemble_meals(dtype, cycle_week, wd):
            for comp in _meal_components(name):
                counter[comp] += 1
    return counter.most_common()


def meal_cycle_full() -> str:
    """Full 4-week meal cycle with every meal plus a per-week shopping tally.

    Backs the coach's `get_meal_cycle` read tool. The structured per-meal data
    lets the coach compose an accurate weekly shopping list; the tally is a
    convenience seed (components split on ' + ', counted per week).
    """
    pt = protein_target_g()
    lines = [
        "FULL 4-WEEK NUTRITION CYCLE (repeats every 28 days).",
        f"Protein floor: {pt['low']}–{pt['high']}g/day ({pt['basis']}).",
        f"Breakfast: {_BREAKFAST_LABEL}.",
        "Sunday cooks two one-pots and one soup for the weekday lunches and for Monday to "
        "Thursday dinners. Friday dinner is cooked fresh that evening. The batch is the plates "
        "you eat. Chicken is at most twice in the week.",
        "",
    ]
    stable = _stable_tdee()
    ref_date = date.today()
    for cw in range(4):
        cycle_label = f"WEEK {cw + 1}" + (" (Recovery)" if cw == 3 else "")
        lines.append(f"=== {cycle_label} ===")
        for wd in range(7):
            dtype = today_day_type(cw, wd)
            day_data = DAY_TYPES[dtype]
            anchor = ref_date + timedelta(days=(wd - ref_date.weekday()))
            meals = _assemble_meals(
                dtype, cw, wd,
                target_kcal=resolve_calorie_target(
                    stable, day_data["calorie_tier"], anchor
                )["kcal"],
            )
            target = resolve_calorie_target(
                stable, day_data["calorie_tier"], anchor
            )
            total_protein = sum(meal[4] for meal in meals)
            lines.append(
                f"{_WEEKDAY_LABELS[wd][:3]} — {day_data['label']} "
                f"({target['kcal']} kcal, ~{total_protein}g protein):"
            )
            for slot, name, _detail, kcal, prot, carbs in meals:
                lines.append(f"  {slot}: {name} — {kcal} kcal, {prot}g P, {carbs}g C")
        lines.append(f"Shopping tally for Week {cw + 1} (component → times/week):")
        for comp, n in _week_shopping_tally(cw):
            lines.append(f"  {comp} ×{n}")
        lines.append("")
    return "\n".join(lines)

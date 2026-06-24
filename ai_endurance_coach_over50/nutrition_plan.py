"""Nutrition plan data — 4-week repeatable cycle.

Encoded here so the AI coach can reference the exact prescribed meals for
today rather than only seeing what was logged after the fact.

Protein targets are anchored to the athlete's measured bodyweight (carried
from the most recent body_metrics reading via `current_weight_kg()`), not a
hardcoded figure — the Block-A weight-loss reset means weight is falling over
the plan and a static number would drift out of date.
"""
from __future__ import annotations

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
        return _FALLBACK_WEIGHT_KG


# Protein is prescribed on a FAT-FREE-MASS basis, not total bodyweight: at high
# body fat, g/kg of total weight over-prescribes. 2.2–2.6 g/kg of lean mass is
# the evidence-based range to preserve muscle in a deficit, and the upper end
# suits a 50+ athlete (anabolic resistance). Falls back to 1.8 g/kg of total
# weight when no body-fat reading exists to derive lean mass.
_PROTEIN_G_PER_KG_LEAN_LOW = 2.2
_PROTEIN_G_PER_KG_LEAN_HIGH = 2.6


def protein_target_g() -> dict:
    """Daily protein floor/ceiling in grams, on a fat-free-mass basis.

    Returns {"low", "high", "basis", "lean_kg"}; `basis` documents how it was
    derived so the coach text can be honest about the input.
    """
    try:
        from .history import latest_lean_mass_kg
        lean = latest_lean_mass_kg()
    except Exception:
        lean = None
    if lean:
        return {
            "low": round(lean * _PROTEIN_G_PER_KG_LEAN_LOW),
            "high": round(lean * _PROTEIN_G_PER_KG_LEAN_HIGH),
            "basis": f"{_PROTEIN_G_PER_KG_LEAN_LOW:g}–{_PROTEIN_G_PER_KG_LEAN_HIGH:g} g/kg of fat-free mass, ~{lean:.0f} kg",
            "lean_kg": round(lean, 1),
        }
    # No body-fat reading — fall back to total-weight estimate.
    w = current_weight_kg()
    return {
        "low": round(w * 1.8),
        "high": round(w * 2.0),
        "basis": f"1.8–2.0 g/kg of bodyweight, ~{w:.0f} kg — no body-fat reading to derive lean mass",
        "lean_kg": None,
    }

# ── Calorie tiers ─────────────────────────────────────────────────────────────
CALORIE_TIERS = {
    "rest":     {"label": "Rest / Monday",            "kcal": 2050},
    "training": {"label": "Training days (Tue–Fri)",  "kcal": 2350},
    "ruck":     {"label": "Ruck Saturday",             "kcal": 2500},
    "long":     {"label": "Long ride Sunday",          "kcal": 2700,
                 "note": "baseline ~2 h; +150–200 kcal per extra hour beyond 2 h"},
    "recovery": {"label": "Recovery week Mon–Fri",     "kcal": 2050},
}

# ── Simple rules (primary athlete-facing cheat sheet) ─────────────────────────
SIMPLE_RULES = [
    "Protein anchor every meal — chicken, scotch egg, tuna, prawns, Greek yogurt, or whey "
    "(~180–190 g on training days).",
    "Breakfast is fixed — overnight oats Mon/Wed/Fri; scotch egg + 200 g yogurt Tue/Thu "
    "(egg muffins Tue/Thu in recovery week only).",
    "Weekday rides ≤90 min — banana 45 min before, nothing on the bike. Whey shake after as planned.",
    "Lunch = Sunday batch — rice or pasta + protein + yogurt; assemble in 2 min.",
    "Dinner — Gousto Mon–Thu (pick ≥65 g protein), Blackstone griddle Fri–Sun.",
    "Protein oat bar — Tue/Thu mid-morning only.",
    "Weekend long rides — rice cakes + electrolyte bottles only (no carb powder). "
    "Prep Friday eve: see fuel_prep_for_ride() for batch count from planned ride length.",
]

# ── Principles (detail behind the simple rules) ───────────────────────────────
PRINCIPLES = [
    "Cost strategy (bulk-staple rebuild): batch-roasted chicken, scotch eggs, a 1 kg Greek yogurt "
    "tub, a 1 kg whey tub, bulk oats and basmati. Target ≈£28–32/week.",
    "Energy strategy (Block A — weight-loss reset): moderate lean-mass-sparing deficit on rest days; "
    "long-ride day stays close to energy balance — never under-fuel the key endurance session.",
    "Protein target: lean-mass based (≈2.2 g/kg fat-free mass). Greek yogurt at lunch Mon–Thu; "
    "whey shake Wed/Thu/Fri/Sat/Sun as prescribed.",
    "Carbs around training: batch rice/pasta lunches; banana 45 min pre-session on weekdays. "
    "Saturday griddle dinner fuels Sunday — not breakfast.",
    "Dinners: Gousto Mon–Thu; Blackstone griddle Fri/Sat/Sun (≥65 g protein).",
    "Sunday long ride: half banana before rolling; rice cakes on the bike from minute 0; "
    "electrolyte bottles only. Recovery: chocolate milk → protein overnight oats jar.",
    "In-ride solids are weekends only (Sunday long ride ≥75 min). Weekday 60 min rides: banana only.",
    "Recovery week (W4): same structure, fewer snacks, lighter dinner. Protein floor holds; "
    "egg muffins replace scotch eggs Tue/Thu.",
    "Thursday: lowest pre-dinner protein — Gousto MUST be ≥65 g protein (chicken/beef/salmon).",
    "Saturday: chicken lunch (not eggs on toast), yogurt post-ruck, evening whey shake.",
]

# ── Supplements (evidence-based for 50+; discuss with GP before starting) ─────
# Framed as coach guidance, NOT prescriptions. Each entry: (name, dose, why).
SUPPLEMENTS: list[tuple[str, str, str]] = [
    ("Creatine monohydrate", "3–5 g/day, every day",
     "Best-evidenced supplement for a masters athlete: helps retain lean mass and strength in a "
     "calorie deficit, supports high-intensity work and recovery, and may aid cognition. No loading "
     "needed; take any time of day."),
    ("Vitamin D3", "Per GP / blood test (often 1000–2000 IU/day in winter)",
     "Supports bone density (important for a cyclist — low impact), immune function and muscle. "
     "UK sun is insufficient Oct–Mar; dose to a measured blood level rather than guessing."),
    ("Omega-3 (EPA/DHA)", "~1–2 g combined EPA+DHA/day",
     "Anti-inflammatory; may blunt training soreness and support cardiovascular and joint health. "
     "Oily fish 2–3×/week is an alternative to a capsule."),
]

_SUPPLEMENT_DISCLAIMER = (
    "Guidance only, not medical advice — confirm doses and suitability with your GP, "
    "especially alongside any medication or blood-pressure management."
)

# ── Weekday breakfasts (fixed pattern; recovery week swaps Tue/Thu to muffins) ─
# Each entry: (name, detail, kcal, protein_g, carbs_g)
BREAKFASTS: dict[str, tuple[str, str, int, int, int]] = {
    "mwf": (
        "High-Protein Overnight Oats",
        "Per 350ml jar: 50g oats + 1 scoop whey + 120ml milk + 90g Greek yogurt + 1 tbsp chia + "
        "1 tsp honey; 100g berries in a separate pot. Spoon, pour, seal — no cooking. Mon/Wed/Fri.",
        470, 42, 48,
    ),
    "scotch_tuth": (
        "Scotch Egg + Greek Yogurt",
        "1 baked scotch egg (lean turkey/chicken mince wrap) + 200g Greek yogurt. "
        "Batch 6 on Sunday alongside oat bars.",
        420, 32, 18,
    ),
    "muffin_tuth": (
        "Egg & Veg Muffins ×2",
        "10-egg tray bake with potato, pepper, spinach and bacon/ham. Bake Sunday; "
        "2 muffins per breakfast Tue/Thu. Recovery week only.",
        340, 28, 12,
    ),
}

_WEEKDAY_BREAKFAST_TYPES = frozenset({
    "rest", "training", "bike", "bike_fri", "thursday", "recovery_weekday",
})

_BREAKFAST_LABEL = (
    "Overnight oats Mon/Wed/Fri · scotch egg + yogurt Tue/Thu "
    "(egg muffins Tue/Thu in recovery week)"
)


def breakfast_key(cycle_week: int, weekday: int) -> str:
    """Mon–Fri breakfast slot. Recovery week (index 3) uses egg muffins Tue/Thu."""
    if weekday in (0, 2, 4):
        return "mwf"
    if cycle_week == 3:
        return "muffin_tuth"
    return "scotch_tuth"


def _skip_am_snack(_cycle_week: int, weekday: int) -> bool:
    """Protein oat bar is Tue/Thu mid-morning only."""
    return weekday not in (1, 3)


def _assemble_meals(dtype: str, cycle_week: int, weekday: int) -> list[tuple]:
    """Merge A/B breakfast rotation into weekday day-type meal lists."""
    raw = DAY_TYPES[dtype]["meals"]
    if dtype not in _WEEKDAY_BREAKFAST_TYPES:
        return list(raw)
    key = breakfast_key(cycle_week, weekday)
    name, detail, kcal, prot, carbs = BREAKFASTS[key]
    result: list[tuple] = [("Breakfast", name, detail, kcal, prot, carbs)]
    for slot, mname, mdetail, mkcal, mprot, mcarbs in raw:
        if slot == "AM Snack" and _skip_am_snack(cycle_week, weekday):
            continue
        result.append((slot, mname, mdetail, mkcal, mprot, mcarbs))
    return result


def _pre_dinner_protein(meals: list[tuple]) -> int:
    """Sum protein for all meals except the last (dinner / griddle)."""
    if len(meals) <= 1:
        return sum(m[4] for m in meals)
    return sum(m[4] for m in meals[:-1])


# ── Day-type templates ────────────────────────────────────────────────────────
# Each meal: (slot, name, detail, kcal, protein_g, carbs_g)
# Weekday breakfasts are injected by `_assemble_meals()` — not stored here.
DAY_TYPES: dict[str, dict] = {

    "rest": {
        "label": "Rest day",
        "calorie_tier": "rest",
        "pre_dinner_protein_g": 113,
        "protein_note": "~113g pre-dinner; Gousto must deliver 60g+ to hit protein floor.",
        "meals": [
            ("AM Snack", "Protein Oat Bar", "Batch-baked (oats + PB + honey + whey). Tue/Thu mid-morning only.", 200, 10, 15),
            ("Lunch", "Batch Rice + Chicken 240g + Greek Yogurt",
             "Batch-cooked basmati + 240g batch-roasted chicken, Greek-yogurt portion alongside "
             "for the protein top-up. Replaces the rice pouch + GetPro.", 680, 73, 70),
            ("PM Snack", "Banana", "Afternoon energy.", 90, 1, 23),
            ("Eve Snack", "Apple or orange", "Light evening snack.", 70, 1, 18),
            ("Dinner", "Gousto — 60g+ protein pick",
             "~660 kcal, 60g+ protein. Weekday Gousto night. Rest day — any strong pick "
             "(chicken, beef, salmon). Veggie or pasta-only dishes don't hit target.", 660, 60, 55),
        ],
    },

    "training": {
        "label": "Kettlebell + MaxiClimber",
        "calorie_tier": "training",
        "pre_dinner_protein_g": 113,
        "protein_note": "~113g pre-dinner; Gousto at 65g closes the day at protein floor.",
        "meals": [
            ("AM Snack", "Protein Oat Bar", "Tue mid-morning only.", 200, 10, 15),
            ("Lunch", "Batch Rice + Chicken 240g + Greek Yogurt",
             "Full 240g batch-roasted chicken + Greek-yogurt portion. Same as rest day lunch — "
             "protein floor needs the yogurt on training days too.", 700, 73, 70),
            ("PM Snack", "Banana", "45 min before evening session.", 90, 1, 23),
            ("Eve Snack", "Apple or orange", "Post-session.", 70, 1, 18),
            ("Dinner", "Gousto — 65g protein pick",
             "~730 kcal, 65g protein. Weekday Gousto night. Chicken thighs, beef ragu or salmon. "
             "Training day — recovery depends on this meal.", 730, 65, 70),
        ],
    },

    "bike": {
        "label": "Outdoor Bike 60 min",
        "calorie_tier": "training",
        "pre_dinner_protein_g": 128,
        "protein_note": "~103g pre-dinner (includes whey shake). Gousto at 65g closes the day.",
        "meals": [
            ("Lunch", "Bulk Pasta + Tuna + Greek Yogurt",
             "Bulk dried pasta with a stir-through tin of tuna; Greek-yogurt portion alongside. "
             "Good carbs for the afternoon ride.", 600, 53, 78),
            ("PM Snack", "Banana", "45 min before riding — nothing on the bike for a 60 min weekday ride.", 90, 1, 23),
            ("Protein Shake", "Whey shake — 25g protein (home-mixed)",
             "Post-ride or between PM snack and dinner. One scoop from the 1kg tub. Closes the "
             "protein gap on ride days where lunch is tuna/pasta rather than chicken.", 150, 25, 5),
            ("Eve Snack", "Apple or orange", "Post-ride.", 70, 1, 18),
            ("Dinner", "Gousto — 65g protein pick",
             "~730 kcal, 65g protein. Weekday Gousto night (Wednesday). Pasta, rice or noodle "
             "Gousto works on ride evenings if the protein source is chicken, fish or beef.", 730, 65, 72),
        ],
    },

    "bike_fri": {
        "label": "Outdoor Bike 60 min — Friday griddle",
        "calorie_tier": "training",
        "pre_dinner_protein_g": 128,
        "protein_note": "~118g pre-dinner (whey shake + chicken lunch). Griddle at 65g. Friday griddle night.",
        "meals": [
            ("Lunch", "Batch Rice + Chicken 240g",
             "Full batch-roasted chicken pack. Strong protein lunch.", 550, 58, 58),
            ("PM Snack", "Banana", "45 min before ride — nothing on the bike for a 60 min weekday ride.", 90, 1, 23),
            ("Protein Shake", "Whey shake — 25g protein (home-mixed)",
             "Post-ride or between PM snack and dinner. Brings pre-dinner total to 130g so any "
             "65g+ griddle dinner hits 195g.", 150, 25, 5),
            ("Eve Snack", "Apple or orange", "Post-ride.", 70, 1, 18),
            ("Dinner", "Blackstone griddle — 65g protein, end-of-week",
             "~730 kcal, 65g protein. First griddle night of the weekend. Griddled chicken, "
             "lean steak or salmon + veg + flatbreads or rice. You've earned the Friday cook.", 730, 65, 65),
        ],
    },

    "thursday": {
        "label": "Kettlebell + MaxiClimber — Paprika Rice Thursday",
        "calorie_tier": "training",
        "pre_dinner_protein_g": 112,
        "protein_note": "~112g pre-dinner — lowest pre-dinner day. Gousto MUST be ≥65g protein.",
        "meals": [
            ("AM Snack", "Protein Oat Bar", "Thu mid-morning only.", 200, 10, 15),
            ("Lunch", "Paprika Batch Rice + Prawns 150g + Greek Yogurt",
             "Homemade 'paella' — batch rice with paprika and peas, cold prawns stirred in, "
             "Greek-yogurt portion alongside. Replaces the Ben's pouch; same carb base for "
             "evening kettlebell.", 480, 47, 62),
            ("PM Snack", "Banana", "45 min before session. Carbs matter tonight.", 90, 1, 23),
            ("Protein Shake", "Whey shake — 25g protein (home-mixed)",
             "Between session and dinner — closes the protein gap left by the lower-protein "
             "rice-and-prawn lunch. Non-negotiable on Thursdays.", 150, 25, 5),
            ("Eve Snack", "Apple or orange", "Post-session.", 70, 1, 18),
            ("Dinner", "Gousto — strongest pick of the week, ≥65g protein",
             "~730 kcal, 65g protein. Weekday Gousto night. Lowest pre-dinner protein day — "
             "Gousto must deliver. Chicken, beef or salmon. NOT a pasta-only or veggie dish.", 730, 65, 68),
        ],
    },

    "ruck": {
        "label": "Rucking 60–90 min",
        "calorie_tier": "ruck",
        "pre_dinner_protein_g": 137,
        "protein_note": "Saturday was the biggest protein gap (old plan: 97g, need 197g). "
                        "Chicken lunch + Greek yogurt at breakfast + shake are all required to hit target.",
        "meals": [
            ("On Waking", "Banana out the door (or fasted)",
             "Very early start — fasted at easy pace is fine. Banana if you want fuel.", 150, 3, 30),
            ("Post-Ruck", "Porridge 80g + Milk + 2 Eggs + Banana + Greek Yogurt",
             "On return — the recovery meal. 80g oats, semi-skimmed milk, 2 eggs, banana, "
             "Greek-yogurt portion. The yogurt is essential here — without it Saturday protein collapses.", 680, 37, 72),
            ("Lunch", "Chicken 240g + Batch Rice + Salad",
             "Full 240g batch-roasted chicken — NOT eggs on toast (22g vs 58g protein). "
             "This single swap adds 36g protein to Saturday. Non-negotiable.", 550, 58, 46),
            ("PM Snack", "Banana + Apple + Protein Oat Bar",
             "Afternoon. Add the oat bar on Saturday to keep the total moving.", 360, 12, 56),
            ("Protein Shake", "Whey shake — 25g protein (home-mixed)",
             "Evening, before dinner. Saturday's structure makes it hard to hit 185g without "
             "a shake — treat this as a planned meal, not optional.", 150, 25, 5),
            ("Dinner", "Blackstone griddle — carb-rich pick (tomorrow's pre-ride meal)",
             "~730 kcal, 62g protein. Saturday griddle night, biased carb-rich: griddled chicken "
             "thighs or steak + flatbreads or rice + griddled veg. This dinner fuels Sunday's ride.", 730, 62, 82),
        ],
    },

    "long": {
        "label": "Long Ride — building to 3h30",
        "calorie_tier": "long",
        "pre_dinner_protein_g": 126,
        "protein_note": "126g pre-dinner (whey now in recovery meal + 240g chicken at lunch). "
                        "Griddle at 65g closes the day at ~190g.",
        "meals": [
            ("On Waking", "Half banana or rice cake square",
             "15–40 g fast carbs, 10–15 min before rolling. Saturday griddle dinner was the real pre-ride meal.", 120, 2, 28),
            ("On-Bike", "Standard rice cakes + electrolyte bottles (E1, E2…)",
             "Weekend long ride only. Pack count from fuel_prep_for_ride(planned duration). "
             "~55 g carbs/hr from solids; sip electrolyte bottles from minute 0. No carb powder in bottles.", 450, 6, 104),
            ("Recovery", "Chocolate Milk → Protein Overnight Oats Jar",
             "Chocolate milk in car first, then recovery oats jar with whey (≥30 g protein) within 60 min.", 720, 42, 75),
            ("Lunch", "Chicken 240g + Batch Rice + Salad",
             "A few hours after the ride. Increased from 150g to 240g chicken — adds 10g protein "
             "and improves afternoon recovery before the next training day.", 550, 58, 56),
            ("Dinner", "Blackstone griddle — 65g protein recovery pick",
             "~700 kcal, 65g protein. Sunday griddle night. Griddled salmon, chicken or lean "
             "steak + veg + potatoes or rice. Strong protein close to a big ride day.", 700, 65, 64),
        ],
    },

    "recovery_weekday": {
        "label": "Recovery week Mon–Fri",
        "calorie_tier": "recovery",
        "pre_dinner_protein_g": 110,
        "protein_note": "Recovery week: protein holds at 185g minimum — cut from carbs/fat only. "
                        "Whey shake stays in even on recovery week.",
        "meals": [
            ("Snack", "Protein oat bar on training days, skip on rest days",
             "Keep protein snacks. Drop fruit snacks on rest days. Oat bar on training days only.", 200, 10, 15),
            ("Lunch", "Same lunch choices — no change",
             "Lunch stays identical to Weeks 1–3 (batch rice + chicken). The calorie cut comes "
             "from a lighter dinner and snack reduction, not lunch.", 500, 45, 60),
            ("Protein Shake", "Whey shake — 25g protein (home-mixed)",
             "Keep the shake even in recovery week — protein target doesn't drop.", 150, 25, 5),
            ("Dinner", "Lighter pick (Gousto Mon–Thu / griddle Fri) — still 55g+ protein",
             "~560 kcal, 55g protein. Thai prawn salad, baked cod with greens, or a light "
             "griddled chicken-and-veg bowl. Lean protein, less carb. Don't pick a low-protein "
             "option just because it's recovery week.", 560, 55, 48),
        ],
    },

    "recovery_saturday": {
        "label": "Recovery week Saturday — easy ruck",
        "calorie_tier": "recovery",
        "pre_dinner_protein_g": 117,
        "protein_note": "Recovery Saturday still needs 165g+ protein. Chicken lunch and Greek yogurt "
                        "at breakfast are required — same rules as build-week Saturday.",
        "meals": [
            ("On Waking", "Fasted or banana", "Easy recovery ruck — fasted at easy pace is fine.", 90, 1, 23),
            ("Post-Ruck", "60g Porridge + 2 Eggs + Greek Yogurt",
             "On return — smaller than a build week (60g oats vs 80g) but the yogurt stays in.", 570, 43, 48),
            ("Lunch", "Chicken 150g + Batch Rice + Salad",
             "Chicken not eggs on toast — same rule as build Saturday. 150g chicken (not 240g) "
             "reflects the lighter recovery day.", 450, 40, 42),
            ("Protein Shake", "Whey shake — 25g protein (home-mixed)",
             "Saturday protein gap exists even in recovery week. Shake stays in.", 150, 25, 5),
            ("Dinner", "Blackstone griddle — lighter recovery pick, still 58g+ protein",
             "~650 kcal, 58g protein. Saturday griddle night. Bias carbs if Sunday is still a ride.", 650, 58, 58),
        ],
    },

    "recovery_sunday": {
        "label": "Recovery week Sunday — shorter ride 75–90 min",
        "calorie_tier": "recovery",
        "pre_dinner_protein_g": 119,
        "protein_note": "Whey added to recovery meal; griddle raised to 62g. "
                        "Closes the day at ~165g — acceptable for recovery week.",
        "meals": [
            ("On Waking", "Half banana", "Small fast carbs only.", 90, 1, 23),
            ("On-Bike", "Rice cakes + electrolyte (E1)",
             "Recovery-pace ride ≥75 min — pack count from fuel_prep_for_ride(planned duration).", 120, 3, 28),
            ("Recovery", "Chocolate Milk → Protein Overnight Oats Jar",
             "Same two-tier stack as build-week Sunday.", 650, 38, 68),
            ("Lunch", "Chicken 150g + Batch Rice + Salad",
             "Recovery ride: 150g chicken (lighter than build week 240g). "
             "Still essential to get protein in post-ride.", 480, 42, 46),
            ("Dinner", "Blackstone griddle — end-of-cycle pick, 62g+ protein",
             "~680 kcal, 62g protein. Sunday griddle night, final meal before cycle repeats. "
             "Salmon, chicken or lean steak. Raise the protein target vs old plan (was 48g, now 62g).", 680, 62, 62),
        ],
    },
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


def today_day_type(cycle_week: int, weekday: int) -> str:
    if cycle_week == 3:
        return _WEEKDAY_TO_TYPE_RECOVERY[weekday]
    return _WEEKDAY_TO_TYPE_BUILD[weekday]


def fuel_prep_for_ride(duration_min: int) -> dict:
    """Batch counts for a weekend long ride (~27 g carbs per rice cake, ~55 g/hr target)."""
    h = duration_min / 60
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
    return {
        "duration_min": duration_min,
        "ride_hours": round(h, 1),
        "rice_cakes": cakes,
        "bottles": bottles,
        "flapjack": flapjack,
        "banana_before": True,
        "prep_note": (
            f"Make {cakes} standard rice cakes; mix electrolyte bottles "
            f"{', '.join(bottles)}."
            + (" Pack 1 flapjack bar as bonk insurance." if flapjack else "")
        ),
    }


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
        pass
    return None


def fuel_prep_context(plan_start: date, today: date) -> str:
    """Friday/Saturday prep line for the coming Sunday long ride."""
    ride_min = _sunday_planned_ride_min(plan_start, today)
    if ride_min is None:
        return ""
    prep = fuel_prep_for_ride(ride_min)
    h = prep["ride_hours"]
    bottles = " + ".join(prep["bottles"])
    flap = " · pack 1 flapjack" if prep["flapjack"] else ""
    return (
        f"Sunday long ride ~{h} h → make **{prep['rice_cakes']} rice cakes** tonight, "
        f"mix **{bottles}** electrolyte bottles{flap}."
    )


def today_checklist(plan_start: date, today: date) -> list[str]:
    """3–6 bullets: what to eat/follow today."""
    cw = cycle_week_index(plan_start, today)
    wd = today.weekday()
    dtype = today_day_type(cw, wd)
    meals = _assemble_meals(dtype, cw, wd)
    pt = protein_target_g()

    items: list[str] = []
    breakfast = next((m for m in meals if m[0] == "Breakfast"), None)
    if breakfast:
        items.append(f"Breakfast: {breakfast[1]}")
    elif dtype in ("ruck", "long", "recovery_saturday", "recovery_sunday"):
        waking = next((m for m in meals if m[0] == "On Waking"), None)
        if waking:
            items.append(f"On waking: {waking[1]}")

    lunch = next((m for m in meals if m[0] == "Lunch"), None)
    if lunch:
        items.append(f"Lunch: {lunch[1]}")
    elif dtype == "recovery_weekday":
        items.append("Lunch: batch rice + chicken (same as build weeks)")

    if dtype in ("bike", "bike_fri"):
        items.append("Pre-ride: banana 45 min before — nothing on the bike (60 min weekday ride)")
    elif dtype in ("training", "thursday"):
        items.append("Pre-session: banana 45 min before evening KB")
    elif dtype == "long":
        ride_min = _sunday_planned_ride_min(plan_start, today) or 120
        prep = fuel_prep_for_ride(ride_min)
        items.append(
            f"On the bike: {prep['rice_cakes']} rice cakes + "
            f"{' + '.join(prep['bottles'])} electrolyte bottles"
        )
        items.append("Recovery: chocolate milk → protein overnight oats jar")

    shake = next((m for m in meals if m[0] == "Protein Shake"), None)
    if shake:
        items.append("Whey shake today (planned)")

    dinner = meals[-1] if meals else None
    if dinner:
        items.append(f"Dinner: {dinner[1]}")

    if today.weekday() in (4, 5):  # Fri/Sat — flag Sunday prep
        fuel_line = fuel_prep_context(plan_start, today)
        if fuel_line:
            items.append(fuel_line.replace("**", ""))

    items.append(f"Protein floor today: {pt['low']}–{pt['high']} g")
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

_WEEK_BANNERS = {
    0: "<strong>Week 1 — build.</strong> Fixed breakfasts; Gousto Mon–Thu, griddle Fri–Sun. "
       "Friday eve: prep Sunday ride fuel per batch calculator.",
    1: "<strong>Week 2 — same as Week 1.</strong> Identical meals and prep rhythm.",
    2: "<strong>Week 3 — same as Week 1.</strong> Identical meals and prep rhythm.",
    3: "<strong>Week 4 — recovery.</strong> Egg muffins Tue/Thu; lighter dinners; protein floor holds.",
}


def build_meal_week(cycle_week: int) -> dict:
    """Structured week data for meals.html (server-rendered)."""
    if cycle_week == 3:
        days_out = []
        rw = DAY_TYPES["recovery_weekday"]
        meals_rw = _assemble_meals("recovery_weekday", cycle_week, 0)
        days_out.append({
            "name": "Mon–Fri",
            "badge": _BADGE_BY_TYPE["recovery_weekday"],
            "type": rw["label"],
            "kcal": "~2,000–2,100 kcal",
            "meals": [_meal_dict(m) for m in meals_rw],
            "preDinP": _pre_dinner_protein(meals_rw),
            "note": rw["protein_note"],
            "noteWarn": False,
        })
        for wd, key in ((5, "recovery_saturday"), (6, "recovery_sunday")):
            dd = DAY_TYPES[key]
            meals = _assemble_meals(key, cycle_week, wd)
            days_out.append({
                "name": _WEEKDAY_LABELS[wd],
                "badge": _BADGE_BY_TYPE[key],
                "type": dd["label"],
                "kcal": f"~{CALORIE_TIERS[dd['calorie_tier']]['kcal']:,} kcal".replace(",", ","),
                "meals": [_meal_dict(m) for m in meals],
                "preDinP": _pre_dinner_protein(meals),
                "note": dd["protein_note"],
                "noteWarn": False,
            })
        return {
            "banner": _WEEK_BANNERS[3],
            "recovery": True,
            "days": days_out,
        }

    days_out = []
    for wd in range(7):
        dtype = today_day_type(cycle_week, wd)
        dd = DAY_TYPES[dtype]
        meals = _assemble_meals(dtype, cycle_week, wd)
        tier = CALORIE_TIERS[dd["calorie_tier"]]
        days_out.append({
            "name": _WEEKDAY_LABELS[wd],
            "badge": _BADGE_BY_TYPE.get(dtype, "badge-rest"),
            "type": dd["label"],
            "kcal": f"~{tier['kcal']:,} kcal",
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


def _meal_dict(meal: tuple) -> dict:
    slot, name, detail, kcal, prot, carbs = meal
    fat_g = max(0, (kcal - prot * 4 - carbs * 4) // 9)
    return {
        "type": slot,
        "name": name,
        "detail": detail,
        "prot": prot,
        "macros": {"kcal": str(kcal), "p": str(prot), "c": str(carbs), "f": str(fat_g) if fat_g else ""},
    }


def nutrition_coach_context(plan_start: date, today: date) -> str:
    """Return a compact text block describing today's prescribed nutrition."""
    cycle_week = cycle_week_index(plan_start, today)
    weekday = today.weekday()
    dtype = today_day_type(cycle_week, weekday)
    day_data = DAY_TYPES[dtype]
    meals = _assemble_meals(dtype, cycle_week, weekday)
    tier = CALORIE_TIERS[day_data["calorie_tier"]]
    cycle_label = f"Week {cycle_week + 1}" + (" — Recovery" if cycle_week == 3 else "")

    total_protein = sum(m[4] for m in meals)
    pre_din = _pre_dinner_protein(meals)
    pt = protein_target_g()

    lines = [
        "## Nutrition Plan — Today's Prescribed Meals",
        f"Cycle: {cycle_label}  |  Day type: {day_data['label']}  |  "
        f"Target: {tier['kcal']} kcal" + (f" ({tier['note']})" if tier.get("note") else ""),
    ]
    if dtype in _WEEKDAY_BREAKFAST_TYPES:
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

    for slot, name, detail, kcal, prot, carbs in meals:
        lines.append(f"  {slot}: {name} — {kcal} kcal, {prot}g protein, {carbs}g carbs")
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
        meals = _assemble_meals(dtype, cycle_week, wd)
        tier = CALORIE_TIERS[day_data["calorie_tier"]]
        total_protein = sum(meal[4] for meal in meals)
        marker = "  ← today" if d == today else ""
        lines.append(
            f"  {_WEEKDAY_LABELS[wd][:3]} {d.strftime('%d %b')}: {day_data['label']} "
            f"— {tier['kcal']} kcal, ~{total_protein}g protein{marker}"
        )
        for slot, name, _detail, kcal, prot, _carbs in meals:
            lines.append(f"      {slot}: {name} ({kcal} kcal, {prot}g P)")
    ride_min = _sunday_planned_ride_min(plan_start, today)
    if ride_min:
        prep = fuel_prep_for_ride(ride_min)
        lines.append(
            f"  Sunday fuel prep (Fri eve): {prep['rice_cakes']} rice cakes, "
            f"bottles {', '.join(prep['bottles'])}"
            + (" + flapjack" if prep["flapjack"] else "")
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
        "Weeks 1–3: identical build-week meals. Week 4: recovery portions.",
        "",
    ]
    for cw in range(4):
        cycle_label = f"WEEK {cw + 1}" + (" (Recovery)" if cw == 3 else "")
        lines.append(f"=== {cycle_label} ===")
        for wd in range(7):
            dtype = today_day_type(cw, wd)
            day_data = DAY_TYPES[dtype]
            meals = _assemble_meals(dtype, cw, wd)
            tier = CALORIE_TIERS[day_data["calorie_tier"]]
            total_protein = sum(meal[4] for meal in meals)
            lines.append(
                f"{_WEEKDAY_LABELS[wd][:3]} — {day_data['label']} "
                f"({tier['kcal']} kcal, ~{total_protein}g protein):"
            )
            for slot, name, _detail, kcal, prot, carbs in meals:
                lines.append(f"  {slot}: {name} — {kcal} kcal, {prot}g P, {carbs}g C")
        lines.append(f"Shopping tally for Week {cw + 1} (component → times/week):")
        for comp, n in _week_shopping_tally(cw):
            lines.append(f"  {comp} ×{n}")
        lines.append("")
    return "\n".join(lines)

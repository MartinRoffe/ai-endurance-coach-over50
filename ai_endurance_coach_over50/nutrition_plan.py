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

from .energy import ride_kcal_from_kj


def adjust_for_session_kj(tier_kcal: int, planned_kj: float) -> dict:
    """Annotate a static calorie tier with estimated session mechanical work."""
    if not planned_kj or planned_kj <= 0:
        return {"tier_kcal": tier_kcal, "planned_kj": None, "note": None}
    kcal = ride_kcal_from_kj(planned_kj)
    return {
        "tier_kcal": tier_kcal,
        "planned_kj": round(planned_kj),
        "planned_kcal_equiv": kcal,
        "note": f"planned ride work ≈ {round(planned_kj)} kJ (~{kcal} kcal mechanical)",
    }

# ── Simple rules (primary athlete-facing cheat sheet) ─────────────────────────
SIMPLE_RULES = [
    "Protein anchor every meal — chicken, scotch egg, tuna, prawns, Greek yogurt, or whey "
    "(~180–190 g on training days).",
    "Breakfast is fixed — overnight oats Mon/Wed/Fri; scotch egg + 200 g yogurt Tue/Thu "
    "(egg muffins Tue/Thu in recovery week only).",
    "Weekday rides ≤90 min — banana 45 min before, nothing on the bike. Whey shake after as planned.",
    "Lunch = Sunday batch — batch rice + chicken + yogurt Mon/Tue/Thu; Wednesday Chinese chicken "
    "+ egg fried rice (day-old batch rice); Friday is a ready-made paella pouch + prawns; weekend "
    "is chicken + salad with griddle leftovers. Assemble in 2 min (Wed: fry rice Tue night, microwave Wed).",
    "Dinner — Sunday batch Mon–Thu (Batch A Mon/Tue, Batch B Wed/Thu; protein dessert "
    "included), Blackstone griddle Fri–Sun.",
    "Protein dessert (150 g skyr / 0% Greek yogurt) closes every weekday dinner; short on "
    "protein? cottage cheese pot or half-scoop whey in yogurt.",
    "Protein bar (Nature Valley or home-baked #03) — Tue/Thu mid-morning only.",
    "Weekend long rides — rice cakes + electrolyte bottles; from rides ≥150 min add "
    "maltodextrin/fructose carb drink bottles to hit the gut-training target (60→75→90 g/h). "
    "Prep Friday eve: see fuel_prep_for_ride() for batch counts.",
    "Carb periodization: Z2 rides ≤75 min may run lower-carb; VO2/threshold days are high-carb "
    "(glycogen-dependent). Match carbs to session mechanical work when power data is available.",
    "Strength days (KB / MaxiClimber): 20–40 g protein within ~1 h peri-session (whey shake or "
    "yogurt) to hit the leucine threshold for 50+ muscle retention.",
    "Tenerife camp windows (Aug / Christmas / May): suspend UK deficit tiers — hard days "
    "3,200–3,800 kcal, 8–10 g/kg carbs, protein floor holds; easy days −15–20% only.",
]

# ── Principles (detail behind the simple rules) ───────────────────────────────
PRINCIPLES = [
    "Cost strategy (bulk-staple rebuild): batch-roasted chicken, scotch eggs, a 1 kg Greek yogurt "
    "tub, a 1 kg whey tub, bulk oats and basmati. Target ≈£28–32/week.",
    "Energy strategy (Block A — weight-loss reset): moderate lean-mass-sparing deficit on rest days; "
    "long-ride day stays close to energy balance — never under-fuel the key endurance session.",
    "Protein target: lean-mass based (≈2.2 g/kg fat-free mass). Greek yogurt at lunch Mon–Thu; "
    "whey shake Wed/Thu/Fri/Sat/Sun as prescribed.",
    "Carbs around training: batch rice + chicken lunches Mon/Tue/Thu; Wednesday Chinese chicken "
    "+ egg fried rice from day-old batch rice; banana 45 min pre-session on weekdays. "
    "Saturday griddle dinner fuels Sunday — not breakfast.",
    "Dinners: Sunday batch Mon–Thu (A fridge Mon/Tue, B freeze→fridge Tue eve; no spice; "
    "protein dessert standard); Blackstone griddle Fri/Sat/Sun (≥65 g protein).",
    "Sunday long ride: half banana before rolling; rice cakes on the bike from minute 0; "
    "electrolyte bottles for hydration; on rides ≥150 min add maltodextrin/fructose carb "
    "drink bottles to close the gap to 60→75→90 g/h gut-training targets. "
    "Recovery: chocolate milk → protein overnight oats jar.",
    "In-ride solids are weekends only (Sunday long ride ≥75 min). Weekday 60 min rides: banana only.",
    "Tenerife camps (Aug charity, Christmas HR volume, May HR race-sim): energy availability "
    "first — no calorie deficit. Hard days 3,200–3,800 kcal and 8–10 g/kg carbs; easy/rest "
    "−15–20% calories only; protein floor never cut.",
    "Recovery week (W4): same structure, fewer snacks, lighter ~560 kcal batch dinners. "
    "Protein floor holds; egg muffins replace scotch eggs Tue/Thu.",
    "Thursday: batch dinner + protein dessert closes the day at 60–68 g protein. "
    "KB/MaxiClimber days: 20–40 g peri-session protein (whey or yogurt).",
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
     "UK sun is insufficient Oct–Mar; dose to a measured blood level rather than guessing. "
     "Pair with dietary calcium (dairy/yogurt already in the meal plan) — D3 alone is not enough "
     "for bone health."),
    ("Calcium (dietary first)", "Aim ~1000–1200 mg/day from food",
     "Masters bone health for a low-impact cyclist. Greek yogurt, milk, cheese and fortified "
     "alternatives in the meal plan usually cover this; supplement only if intake is low or "
     "DEXA/GP advises."),
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
        "Make 2 on Sunday (Tue/Thu) — they only keep 4 days.",
        420, 32, 18,
    ),
    "muffin_tuth": (
        "Egg & Veg Muffins ×2",
        "5-egg, 6-muffin tray bake with potato, pepper, spinach and bacon/ham. Bake Sunday; "
        "2 muffins per breakfast Tue/Thu. Recovery week only.",
        340, 28, 12,
    ),
}

# ── Weekday dinners (Sunday batch A/B; macros include 150 g protein dessert) ──
# Each entry: (name, detail, kcal, protein_g, carbs_g). Names use " + " for shopping tally.
_DINNER_DETAIL = (
    "Sunday-cooked batch, serves 2 people × 2 nights. Reheat piping hot. "
    "Macros include 150 g skyr / 0% Greek yogurt protein dessert. "
    "Recipes: /nutrition/recipes/weekday-dinners."
)

WEEKDAY_DINNERS: dict[int, dict[str, tuple[str, str, int, int, int]]] = {
    0: {
        "A": (
            "Chicken & root-veg traybake + roast potatoes",
            _DINNER_DETAIL + " Batch A — fridge, eat Mon/Tue.",
            700, 66, 52,
        ),
        "B": (
            "Beef 5% & red-lentil ragù + basmati",
            _DINNER_DETAIL + " Batch B — freeze Sun, fridge Tue eve; eat Wed/Thu.",
            730, 64, 84,
        ),
    },
    1: {
        "A": (
            "Mild coconut chicken curry + basmati",
            _DINNER_DETAIL + " Korma-style, no chilli. Batch A — fridge, eat Mon/Tue.",
            720, 65, 58,
        ),
        "B": (
            "Beef 5% bolognese + wholewheat spaghetti",
            _DINNER_DETAIL + " Batch B — freeze Sun, fridge Tue eve; eat Wed/Thu.",
            700, 68, 62,
        ),
    },
    2: {
        "A": (
            "One-pot chicken & chorizo rice",
            _DINNER_DETAIL + " Mild, no chilli. Batch A — fridge, eat Mon/Tue. Cool fast; reheat once.",
            740, 65, 60,
        ),
        "B": (
            "Smoky bean & beef stew + mash or bread",
            _DINNER_DETAIL + " No heat. Batch B — freeze Sun, fridge Tue eve; eat Wed/Thu.",
            710, 62, 66,
        ),
    },
    3: {
        "A": (
            "Lean cottage pie + half-cauli mash",
            _DINNER_DETAIL + " Recovery week lighter. Batch A — fridge, eat Mon/Tue.",
            560, 62, 40,
        ),
        "B": (
            "Chicken & veg casserole + small potatoes",
            _DINNER_DETAIL + " Recovery week lighter. Batch B — freeze Sun, fridge Tue eve; eat Wed/Thu.",
            560, 60, 40,
        ),
    },
}

_DINNER_BATCH_BY_WEEKDAY = {0: "A", 1: "A", 2: "B", 3: "B"}

_WEEKDAY_DINNER_TYPES = frozenset({
    "rest", "training", "bike", "thursday", "recovery_weekday",
})

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


def weekday_dinner(cycle_week: int, weekday: int) -> tuple | None:
    """Mon–Thu batch dinner for the cycle week, or None for Fri–Sun."""
    batch = _DINNER_BATCH_BY_WEEKDAY.get(weekday)
    if batch is None:
        return None
    name, detail, kcal, prot, carbs = WEEKDAY_DINNERS[cycle_week][batch]
    return ("Dinner", name, detail, kcal, prot, carbs)


def _recovery_dinner_summary() -> tuple:
    """Synthetic dinner row for the W4 Mon–Fri collapsed meals card."""
    return (
        "Dinner",
        "Lean cottage pie Mon/Tue · chicken casserole Wed/Thu · lighter griddle Fri",
        "Recovery week: Batch A cottage pie Mon/Tue, Batch B chicken casserole Wed/Thu "
        "(both ~560 kcal with protein dessert); Friday is a lighter Blackstone griddle pick. "
        "Recipes: /nutrition/recipes/weekday-dinners.",
        560, 62, 40,
    )


def _skip_am_snack(_cycle_week: int, weekday: int) -> bool:
    """Protein bar (Nature Valley or home-baked) is Tue/Thu mid-morning only."""
    return weekday not in (1, 3)


def _assemble_meals(dtype: str, cycle_week: int, weekday: int) -> list[tuple]:
    """Inject weekday breakfast + Mon–Thu batch dinner into day-type meal lists."""
    raw = list(DAY_TYPES[dtype]["meals"])
    if dtype in _WEEKDAY_DINNER_TYPES:
        dinner = weekday_dinner(cycle_week, weekday)
        if dinner is not None and raw and raw[-1][0] == "Dinner":
            raw[-1] = dinner
    if dtype not in _WEEKDAY_BREAKFAST_TYPES:
        return raw
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
        "protein_note": "~113g pre-dinner; Sunday batch dinner + protein dessert closes at 60g+.",
        "meals": [
            ("AM Snack", "Protein Bar (Nature Valley)", "Grab-and-go Nature Valley Protein bar (or home-baked #03). Tue/Thu mid-morning only.", 200, 10, 15),
            ("Lunch", "Batch Rice + Chicken 240g + Greek Yogurt",
             "Batch-cooked basmati + 240g batch-roasted chicken, Greek-yogurt portion alongside "
             "for the protein top-up. Replaces the rice pouch + GetPro.", 680, 73, 70),
            ("PM Snack", "Banana", "Afternoon energy.", 90, 1, 23),
            ("Eve Snack", "Apple or orange", "Light evening snack.", 70, 1, 18),
            ("Dinner", "Sunday batch dinner — see rotation",
             "Fallback only — replaced by WEEKDAY_DINNERS via _assemble_meals. "
             "Mon/Tue Batch A, Wed/Thu Batch B.", 700, 66, 52),
        ],
    },

    "training": {
        "label": "Kettlebell + MaxiClimber",
        "calorie_tier": "training",
        "pre_dinner_protein_g": 113,
        "protein_note": "~113g pre-dinner; Sunday batch dinner + protein dessert closes at protein floor.",
        "meals": [
            ("AM Snack", "Protein Bar (Nature Valley)", "Grab-and-go (or home-baked #03). Tue mid-morning only.", 200, 10, 15),
            ("Lunch", "Batch Rice + Chicken 240g + Greek Yogurt",
             "Full 240g batch-roasted chicken + Greek-yogurt portion. Same as rest day lunch — "
             "protein floor needs the yogurt on training days too.", 700, 73, 70),
            ("PM Snack", "Banana", "45 min before evening session.", 90, 1, 23),
            ("Eve Snack", "Apple or orange", "Post-session.", 70, 1, 18),
            ("Dinner", "Sunday batch dinner — see rotation",
             "Fallback only — replaced by WEEKDAY_DINNERS via _assemble_meals. "
             "Mon/Tue Batch A, Wed/Thu Batch B.", 730, 65, 70),
        ],
    },

    "bike": {
        "label": "Outdoor Bike 60 min",
        "calorie_tier": "training",
        "pre_dinner_protein_g": 142,
        "protein_note": "~154g pre-dinner (Chinese lunch + whey shake). Batch dinner closes the day.",
        "meals": [
            ("Lunch", "Chinese Chicken + Egg Fried Rice + Greek Yogurt",
             "Soy-glazed batch chicken (#01b) with egg fried rice from cold batch basmati — "
             "fried Tuesday night at home, reheated Wednesday at the office (microwave only). "
             "Same carb base as Mon/Tue — good fuel for the afternoon ride.", 720, 85, 72),
            ("PM Snack", "Banana", "45 min before riding — nothing on the bike for a 60 min weekday ride.", 90, 1, 23),
            ("Protein Shake", "Whey shake — 25g protein (home-mixed)",
             "Post-ride or between PM snack and dinner. One scoop from the 1kg tub. Aids recovery "
             "on the Wednesday ride day.", 150, 25, 5),
            ("Eve Snack", "Apple or orange", "Post-ride.", 70, 1, 18),
            ("Dinner", "Sunday batch dinner — see rotation",
             "Fallback only — replaced by WEEKDAY_DINNERS via _assemble_meals. "
             "Wed/Thu = Batch B.", 730, 65, 72),
        ],
    },

    "bike_fri": {
        "label": "Outdoor Bike 60 min — Friday griddle",
        "calorie_tier": "training",
        "pre_dinner_protein_g": 108,
        "protein_note": "~108g pre-dinner (paella pouch + prawns + whey shake). Griddle at 65g. Friday griddle night.",
        "meals": [
            ("Lunch", "Ready-made Paella Pouch + Prawns 150g",
             "Microwave paella pouch with ~150g cooked & peeled prawns stirred through — zero prep. "
             "The prawns lift the low-protein pouch back toward target.", 420, 40, 58),
            ("PM Snack", "Banana", "45 min before ride — nothing on the bike for a 60 min weekday ride.", 90, 1, 23),
            ("Protein Shake", "Whey shake — 25g protein (home-mixed)",
             "Post-ride or between PM snack and dinner. Closes the gap left by the lower-protein "
             "pouch lunch so any 65g+ griddle dinner hits target.", 150, 25, 5),
            ("Eve Snack", "Apple or orange", "Post-ride.", 70, 1, 18),
            ("Dinner", "Blackstone griddle — 65g protein, end-of-week",
             "~730 kcal, 65g protein. First griddle night of the weekend. Griddled chicken, "
             "lean steak or salmon + veg + flatbreads or rice. You've earned the Friday cook.", 730, 65, 65),
        ],
    },

    "thursday": {
        "label": "Kettlebell + MaxiClimber",
        "calorie_tier": "training",
        "pre_dinner_protein_g": 142,
        "protein_note": "~140g pre-dinner (rice + chicken lunch; shake optional). Chicken lunch means "
                        "Thursday is no longer the low-protein day; batch dinner closes the day.",
        "meals": [
            ("AM Snack", "Protein Bar (Nature Valley)", "Grab-and-go (or home-baked #03). Thu mid-morning only.", 200, 10, 15),
            ("Lunch", "Batch Rice + Chicken 240g + Greek Yogurt",
             "Full 240g batch-roasted chicken on batch basmati; Greek-yogurt portion alongside. "
             "Same rice base as Mon/Tue — solid carbs for the evening kettlebell.", 700, 73, 70),
            ("PM Snack", "Banana", "45 min before session. Carbs matter tonight.", 90, 1, 23),
            ("Protein Shake", "Whey shake — 25g protein (home-mixed)",
             "Optional top-up between session and dinner — the chicken lunch already carries the "
             "protein, but the shake aids evening recovery.", 150, 25, 5),
            ("Eve Snack", "Apple or orange", "Post-session.", 70, 1, 18),
            ("Dinner", "Sunday batch dinner — see rotation",
             "Fallback only — replaced by WEEKDAY_DINNERS via _assemble_meals. "
             "Wed/Thu = Batch B.", 730, 65, 68),
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
            ("Lunch", "Chicken 240g + Salad + Griddle Leftovers",
             "Full 240g batch-roasted chicken — NOT eggs on toast (22g vs 58g protein). "
             "No batch rice at the weekend; lean on leftover griddle carbs (flatbread/potatoes) "
             "from Friday's cook for the carbohydrate.", 520, 58, 38),
            ("PM Snack", "Banana + Apple + Protein Bar (Nature Valley)",
             "Afternoon. Add the protein bar on Saturday to keep the total moving.", 360, 12, 56),
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
            ("Lunch", "Chicken 240g + Salad + Griddle Leftovers",
             "A few hours after the ride. Full 240g chicken for recovery; no batch rice at the "
             "weekend — lean on leftover griddle carbs (potatoes/flatbread/rice) for the carbohydrate.", 520, 58, 42),
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
            ("Snack", "Protein bar on training days, skip on rest days",
             "Keep protein snacks. Drop fruit snacks on rest days. Protein bar on training days only.", 200, 10, 15),
            ("Lunch", "Same lunch choices — no change",
             "Lunch stays identical to Weeks 1–3 (batch rice + chicken). The calorie cut comes "
             "from a lighter dinner and snack reduction, not lunch.", 500, 45, 60),
            ("Protein Shake", "Whey shake — 25g protein (home-mixed)",
             "Keep the shake even in recovery week — protein target doesn't drop.", 150, 25, 5),
            ("Dinner", "Lighter griddle pick (Fri)",
             "~560 kcal, 55g+ protein. Friday-only fallback when batch injection does not apply. "
             "Lean griddled chicken-and-veg bowl or similar. Mon–Thu use WEEKDAY_DINNERS recovery batches.", 560, 55, 48),
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
            ("Lunch", "Chicken 150g + Salad + Griddle Leftovers",
             "Chicken not eggs on toast — same rule as build Saturday. 150g chicken (not 240g) "
             "reflects the lighter recovery day. No batch rice at the weekend; light griddle "
             "leftovers for carbs.", 420, 40, 30),
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
            ("Lunch", "Chicken 150g + Salad + Griddle Leftovers",
             "Recovery ride: 150g chicken (lighter than build week 240g). "
             "Still essential to get protein in post-ride. No batch rice at the weekend; "
             "light griddle leftovers for carbs.", 440, 42, 34),
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

    Rice cakes cover ~55 g/h solids. For rides ≥150 min, maltodextrin/fructose
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

    solid_g_per_hr = (cakes * 27) / h
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
        f"Make {cakes} standard rice cakes; mix electrolyte bottles "
        f"{', '.join(bottles)}."
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


# ── Tenerife camp nutrition windows (suspend UK deficit tiers) ────────────────
# August charity camp + Haute Route Christmas / May camps.
CAMP_NUTRITION_WINDOWS: list[tuple[date, date, str]] = [
    (date(2026, 8, 13), date(2026, 8, 27), "August Tenerife (charity prep)"),
    (date(2026, 12, 22), date(2027, 1, 2), "Christmas Tenerife (HR volume camp)"),
    (date(2027, 5, 3), date(2027, 5, 9), "May Tenerife (HR race-sim camp)"),
]

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
        pass
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
        f"Sunday long ride ~{h} h → make **{prep['rice_cakes']} rice cakes** tonight, "
        f"mix **{bottles}** electrolyte bottles{carb}{flap}."
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
        prep = fuel_prep_for_ride(ride_min, ref_date=today)
        bike = (
            f"On the bike: {prep['rice_cakes']} rice cakes + "
            f"{' + '.join(prep['bottles'])} electrolyte bottles"
        )
        if prep.get("carb_drink_bottles"):
            bike += (
                f" + {prep['carb_drink_bottles']}× carb drink "
                f"(~{prep['target_g_per_hr']} g/h target)"
            )
        items.append(bike)
        items.append("Recovery: chocolate milk → protein overnight oats jar")

    camp = camp_nutrition_window(today)
    if camp:
        items.insert(
            0,
            f"CAMP DAY ({camp['label']}): energy availability — "
            f"hard days {camp['hard_day_kcal']} kcal, {camp['carbs_g_per_kg']} g/kg carbs; "
            f"NO deficit. {camp['easy_day_note']}",
        )

    if dtype in ("training", "thursday"):
        items.append("Peri-strength: 20–40 g protein within ~1 h of KB/MaxiClimber")

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
    0: "<strong>Cycle week 1 — build.</strong> Fixed breakfasts; batch dinners: chicken traybake Mon/Tue, "
       "beef &amp; lentil ragù Wed/Thu; griddle Fri–Sun. "
       "Friday eve: prep Sunday ride fuel per batch calculator. "
       "<a href=\"/nutrition/sunday\">Sunday Prep</a>.",
    1: "<strong>Cycle week 2 — build.</strong> Batch dinners: mild coconut chicken curry Mon/Tue, "
       "beef bolognese Wed/Thu; griddle Fri–Sun. "
       "<a href=\"/nutrition/sunday\">Sunday Prep</a>.",
    2: "<strong>Cycle week 3 — build.</strong> Batch dinners: chicken &amp; chorizo rice Mon/Tue, "
       "smoky bean &amp; beef stew Wed/Thu; griddle Fri–Sun. "
       "<a href=\"/nutrition/sunday\">Sunday Prep</a>.",
    3: "<strong>Cycle week 4 — recovery.</strong> Egg muffins Tue/Thu; lighter batch dinners "
       "(cottage pie Mon/Tue, chicken casserole Wed/Thu); protein floor holds. "
       "<a href=\"/nutrition/sunday\">Sunday Prep</a>.",
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
            "(including overrides). Meals follow the nutrition cycle "
            f"(cycle week {cycle_week + 1}"
            + (" — recovery" if cycle_week == 3 else "")
            + "). "
            "<a href=\"/nutrition/sunday\">Sunday Prep</a>."
        )
    else:
        banner = (
            "<strong>This week.</strong> Workout badges match the training calendar where a "
            "session is planned; meals follow the nutrition cycle. "
            "<a href=\"/nutrition/sunday\">Sunday Prep</a>."
        )

    days_out = []
    for wd in range(7):
        d = monday + timedelta(days=wd)
        day_cycle = cycle_week_index(plan_start, d)
        dtype = today_day_type(day_cycle, wd)
        dd = DAY_TYPES[dtype]
        meals = _assemble_meals(dtype, day_cycle, wd)
        tier = CALORIE_TIERS[dd["calorie_tier"]]

        session = session_for_date_extended(d)
        if session is not None:
            stype, label, dur = session
            badge_text = _session_badge_label(stype, label, dur)
            badge = _BADGE_BY_SESSION_TYPE.get(stype, _BADGE_BY_TYPE.get(dtype, "badge-rest"))
        else:
            badge_text = dd["label"]
            badge = _BADGE_BY_TYPE.get(dtype, "badge-rest")

        days_out.append({
            "name": f"{_WEEKDAY_LABELS[wd][:3]} {d.day} {d.strftime('%b')}",
            "badge": badge,
            "type": badge_text,
            "kcal": f"~{tier['kcal']:,} kcal",
            "meals": [_meal_dict(m) for m in meals],
            "preDinP": _pre_dinner_protein(meals),
            "note": dd["protein_note"],
            "noteWarn": dtype == "thursday",
        })

    return {
        "banner": banner,
        "recovery": cycle_week == 3,
        "days": days_out,
    }


def build_meal_week(cycle_week: int) -> dict:
    """Structured week data for meals.html (server-rendered)."""
    if cycle_week == 3:
        days_out = []
        rw = DAY_TYPES["recovery_weekday"]
        meals_rw = _assemble_meals("recovery_weekday", cycle_week, 0)
        # Collapsed Mon–Fri card: show both W4 batches + Fri griddle, not only Batch A.
        if meals_rw and meals_rw[-1][0] == "Dinner":
            meals_rw = list(meals_rw)
            meals_rw[-1] = _recovery_dinner_summary()
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


def build_today_food(plan_start: date, today: date) -> dict:
    """Structured today meals for the Nutrition Today page (hero-first eat list)."""
    from .plan import session_for_date_extended

    cycle_week = cycle_week_index(plan_start, today)
    weekday = today.weekday()
    dtype = today_day_type(cycle_week, weekday)
    day_data = DAY_TYPES[dtype]
    meals = _assemble_meals(dtype, cycle_week, weekday)
    tier = CALORIE_TIERS[day_data["calorie_tier"]]

    session = session_for_date_extended(today)
    if session is not None:
        stype, label, dur = session
        badge_text = _session_badge_label(stype, label, dur)
        badge = _BADGE_BY_SESSION_TYPE.get(stype, _BADGE_BY_TYPE.get(dtype, "badge-rest"))
    else:
        badge_text = day_data["label"]
        badge = _BADGE_BY_TYPE.get(dtype, "badge-rest")

    return {
        "day_name": today.strftime("%A %-d %B"),
        "badge": badge,
        "session": badge_text,
        "kcal_target": tier["kcal"],
        "meals": [_meal_dict(m) for m in meals],
        "pre_din_p": _pre_dinner_protein(meals),
        "protein_note": day_data["protein_note"],
        "cycle_week": cycle_week,
    }


def nutrition_coach_context(plan_start: date, today: date) -> str:
    """Return a compact text block describing today's prescribed nutrition."""
    from .plan import session_for_date_extended

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

    session = session_for_date_extended(today)
    if session is not None:
        stype, label, dur = session
        plan_line = f"Plan session: {_session_badge_label(stype, label, dur)}"
    else:
        plan_line = "Plan session: (none scheduled)"

    camp = camp_nutrition_window(today)
    if camp:
        target_line = (
            f"CAMP NUTRITION ({camp['label']}): hard days {camp['hard_day_kcal']} kcal, "
            f"{camp['carbs_g_per_kg']} g/kg carbs, protein {camp['protein_g_per_kg']} g/kg — "
            f"UK deficit tiers SUSPENDED. {camp['easy_day_note']}"
        )
    else:
        target_line = (
            f"Target: {tier['kcal']} kcal"
            + (f" ({tier['note']})" if tier.get("note") else "")
        )

    lines = [
        "## Nutrition Plan — Today's Prescribed Meals",
        f"Cycle: {cycle_label}  |  Day type: {day_data['label']}  |  {target_line}",
        plan_line,
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
        prep = fuel_prep_for_ride(ride_min, ref_date=today)
        carb = ""
        if prep.get("carb_drink_bottles"):
            carb = (
                f", {prep['carb_drink_bottles']}× carb drink "
                f"(~{prep['target_g_per_hr']} g/h)"
            )
        lines.append(
            f"  Sunday fuel prep (Fri eve): {prep['rice_cakes']} rice cakes, "
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
        "Weekday dinners: Sunday batch A (Mon/Tue) + B (Wed/Thu), week-specific rotation; "
        "griddle Fri–Sun. Week 4: lighter recovery batches.",
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

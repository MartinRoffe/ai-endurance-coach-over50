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

# ── Principles ────────────────────────────────────────────────────────────────
PRINCIPLES = [
    "Cost strategy (bulk-staple rebuild): the plan is built on bulk staples, not single-serve "
    "convenience packs. Whole protein comes from batch-roasted chicken, eggs, a 1 kg Greek yogurt "
    "tub portioned at home, and a 1 kg whey tub mixed yourself — replacing GetPro pots, Arla "
    "protein milk and shop protein bars. Carbs come from a 1 kg bag of basmati and 1 kg of oats, "
    "not microwave rice pouches or breakfast-drink bottles. Target ≈£28–32/week, down from ~£48.",
    "Energy strategy (Block A — weight-loss reset): a moderate, LEAN-MASS-SPARING deficit. "
    "Take the deficit from rest and recovery days; keep the long-ride day close to energy "
    "balance so the key endurance session is never under-fuelled. The deficit is safe here — "
    "ample fat reserves mean low under-fuelling risk — but protein and recovery are protected.",
    "Protein target: lean-mass based (≈2.2 g/kg of fat-free mass), held high to preserve muscle "
    "in the deficit. Every meal anchored to a protein source. A portion of Greek yogurt (from the "
    "tub) at breakfast and at lunch Mon–Thu, a home-mixed whey shake on Wed/Thu/Fri/Sat, and eggs "
    "on the weekend. Add a pre-sleep casein/dairy dose (~40 g, e.g. Greek yogurt) on training days.",
    "Carbs around training: batch-cooked rice/pasta lunches on ride and KB days. Banana 45 min "
    "pre-session. Batch paprika rice + prawns on Thursday fuels evening kettlebell. Saturday's "
    "carb-rich Blackstone griddle dinner is the real pre-ride fuel for Sunday — not breakfast.",
    "Dinners: Gousto on the four weekday evenings (Mon–Thu); the Blackstone griddle handles "
    "Fri/Sat/Sun through the summer (griddled chicken, lean steak or salmon + veg + rice or "
    "flatbreads). Hit the same protein/carb targets the old Gousto picks did — the griddle just "
    "does it more cheaply and is the carb-rich pre-ride fuel on Saturday.",
    "Sunday fuelling: 100–150 kcal fast carbs on waking only. On-bike from minute 0: "
    "45–60 g carbs/hr for rides 75 min–2 h (lower for easy Z2, upper for quality), ~60 g/hr for "
    "2–2.5 h, 75–90 g/hr beyond 2.5 h. Recovery meal within 45 min "
    "(chocolate milk first, then big porridge + whey + eggs + banana + PB toast).",
    "Gut training (start early — the gut is trainable and Block B / the alpine event will demand "
    "90+ g/hr): weeks 1–4 practise 60 g/hr on every ride ≥75 min; weeks 5–8 push long rides to "
    "70–80 g/hr; weeks 9+ rehearse 90 g/hr on the long ride (1:0.8 glucose:fructose to raise the "
    "absorption ceiling). The long ride is FUELLED even on the weight-loss block — the calorie "
    "deficit comes from rest/recovery days, never from under-fuelling the key endurance session.",
    "Recovery week (W4): protein holds at 185g minimum — cut comes from carbs/fat only. "
    "Snacks reduce to 1–2/day. Lighter dinner (<550 kcal, Gousto Mon–Thu / lighter griddle Fri). "
    "Whey shake stays in.",
    "Breakfast rotation (Weeks 1 & 3 = Set A, Week 2 = Set B, Week 4 = Set A recovery portions): "
    "two breakfasts batched each Sunday (~60–75 min). Set A: overnight oats Mon/Wed/Fri + egg muffins "
    "Tue/Thu. Set B: banana oat bar + 200g Skyr Mon/Wed/Fri + yoghurt pot + 2 eggs Tue/Thu. "
    "Skyr pot is mandatory with Week B bars — bar alone is carb-only. Arla Skyr backup any morning.",
    "Thursday warning: lowest pre-dinner protein day (~112g Set A / ~116g Set B). "
    "Gousto MUST be chicken/beef/salmon ≥65g protein — not a pasta-only dish.",
    "Saturday is the highest-risk protein day. Lunch must be chicken+rice (not eggs on toast). "
    "Greek yogurt at post-ruck breakfast. Whey shake as evening snack. These are non-negotiable.",
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

# ── Breakfast A/B rotation (Week 2 = Set B; all other weeks = Set A) ─────────
# Each entry: (name, detail, kcal, protein_g, carbs_g)
BREAKFASTS: dict[str, tuple[str, str, int, int, int]] = {
    "a_mwf": (
        "High-Protein Overnight Oats",
        "Per jar: 60g oats + 1 scoop whey + 200ml milk + 100g Greek yogurt + 1 tbsp chia + "
        "100g berries + 1 tsp honey. Spoon, pour, seal — no cooking. Covers Mon/Wed/Fri.",
        480, 38, 50,
    ),
    "a_tuth": (
        "Egg & Veg Muffins ×2",
        "10-egg tray bake with potato, pepper, spinach and bacon/ham. Bake Sunday; "
        "2 muffins per breakfast Tue/Thu. Freezes well.",
        340, 28, 12,
    ),
    "b_mwf": (
        "Banana Oat Bar + Skyr Pot",
        "1 baked banana oat bar + 200g Skyr pot. Bar alone is carb-only — Skyr is required "
        "for protein on Week B Mon/Wed/Fri.",
        420, 34, 44,
    ),
    "b_tuth": (
        "Yoghurt Pot + 2 Boiled Eggs",
        "250g Greek yogurt or Skyr + 40g granola + berries + honey + 2 boiled eggs on the side. "
        "Granola kept separate until eating so it stays crunchy.",
        410, 32, 38,
    ),
}

_WEEKDAY_BREAKFAST_TYPES = frozenset({
    "rest", "training", "bike", "bike_fri", "thursday", "recovery_weekday",
})

_BREAKFAST_ROTATION_LABEL = {
    0: "Set A (overnight oats + egg muffins)",
    1: "Set B (oat bars + Skyr / yoghurt + eggs)",
    2: "Set A (overnight oats + egg muffins)",
    3: "Set A (recovery portions — same recipes)",
}


def breakfast_key(cycle_week: int, weekday: int) -> str:
    """Rotation slot for Mon–Fri breakfasts. Week 2 (index 1) = Set B."""
    rot = "b" if cycle_week == 1 else "a"
    slot = "mwf" if weekday in (0, 2, 4) else "tuth"
    return f"{rot}_{slot}"


def _skip_am_snack(cycle_week: int, weekday: int) -> bool:
    """Drop the separate AM oat bar when breakfast is already 480 kcal overnight oats."""
    return breakfast_key(cycle_week, weekday) == "a_mwf"


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
        "protein_note": "~113g pre-dinner (Set A Mon); Gousto must deliver 60g+ to hit 185g.",
        "meals": [
            ("AM Snack", "Homemade Oat Bar", "Batch-baked flapjack (oats + PB + honey + whey). ~10g protein. Skipped on overnight-oats mornings (Mon/Wed/Fri Set A).", 200, 10, 15),
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
        "protein_note": "~113g pre-dinner (Set A Tue). Gousto at 65g closes the day at 185g.",
        "meals": [
            ("AM Snack", "Homemade Oat Bar", "Mid-morning. Skipped on overnight-oats mornings (Set A Mon/Wed/Fri).", 200, 10, 15),
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
        "protein_note": "~128g pre-dinner (includes whey shake). Gousto at 65g closes the day at 190g.",
        "meals": [
            ("AM Snack", "Homemade Oat Bar", "Mid-morning. Skipped on overnight-oats mornings (Set A Mon/Wed/Fri).", 200, 10, 15),
            ("Lunch", "Bulk Pasta + Tuna + Greek Yogurt",
             "Bulk dried pasta with a stir-through tin of tuna; Greek-yogurt portion alongside. "
             "Good carbs for the afternoon ride, far cheaper than the sachet pasta.", 600, 53, 78),
            ("PM Snack", "Banana", "45 min before riding.", 90, 1, 23),
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
        "protein_note": "~128g pre-dinner (whey shake + strong chicken lunch). Griddle at 65g = 193g. Friday griddle night.",
        "meals": [
            ("AM Snack", "Homemade Oat Bar", "Mid-morning.", 200, 10, 15),
            ("Lunch", "Batch Rice + Chicken 240g",
             "Full batch-roasted chicken pack. Strong protein lunch — rice + chicken gives 58g "
             "without needing the yogurt top-up.", 550, 58, 58),
            ("PM Snack", "Banana", "45 min before ride.", 90, 1, 23),
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
        "protein_note": "⚠ ~112g pre-dinner (Set A) — lowest pre-dinner day. Gousto MUST be ≥65g protein. No exceptions.",
        "meals": [
            ("AM Snack", "Homemade Oat Bar", "Mid-morning. Skipped on overnight-oats mornings only.", 200, 10, 15),
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
            ("PM Snack", "Banana + Apple + Homemade Oat Bar",
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
            ("On Waking", "Banana + honey toast, or carb drink in bottle 1",
             "100–150 kcal fast carbs only, 10–20 min before rolling. Last night's carb-rich "
             "griddle dinner was the real pre-ride meal.", 160, 3, 32),
            ("On-Bike", "Carb drink mix + banana + oat bar (from minute 0)",
             "45–60 g carbs/hr for 75 min–2 h, ~60 g/hr for 2–2.5 h, 75–90 g/hr beyond 2.5 h. "
             "Start in first 15 min, something every 20–30 min. 500 ml bottle with 40–60 g carb drink, "
             "banana (~25 g), homemade oat bar (~28 g). 500–750 ml fluid/hr.", 450, 6, 104),
            ("Recovery", "Big Porridge + Whey + 2 Eggs + Banana + PB Toast + Chocolate Milk",
             "Within 45 min of finishing. Chocolate milk first, then 80g oats + whey scoop + "
             "2 eggs + banana + PB toast. Whey is the protein anchor here — Sunday recovery meal "
             "was 40g protein before, now 55g.", 850, 55, 82),
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
            ("Snack", "Oat bar on training days, skip on rest days",
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
            ("On Waking", "Banana or carb drink", "Small fast carbs only.", 150, 3, 32),
            ("On-Bike", "Carb drink or banana + half oat bar",
             "Even short recovery ride: ~40–60 g carbs/hr once it passes 75 min.", 150, 3, 32),
            ("Recovery", "Full Sunday Porridge + Whey + 2 Eggs + Banana + Chocolate Milk",
             "Chocolate milk first, then 80g oats + whey scoop + 2 eggs + banana. "
             "Whey added here — protein was missing from recovery Sunday.", 750, 51, 74),
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

# Rice variety rotations (weeks 2+3 season the batch rice differently, same macros
# and same bulk basmati — just a different spice mix to keep lunches interesting)
_RICE_SWAP: dict[int, dict[int, str]] = {
    1: {0: "Mexican-Spiced Batch Rice", 4: "Golden Turmeric Batch Rice"},
    2: {0: "Golden Turmeric Batch Rice", 1: "Mexican-Spiced Batch Rice"},
}


def today_day_type(cycle_week: int, weekday: int) -> str:
    if cycle_week == 3:
        return _WEEKDAY_TO_TYPE_RECOVERY[weekday]
    return _WEEKDAY_TO_TYPE_BUILD[weekday]


def nutrition_coach_context(plan_start: date, today: date) -> str:
    """Return a compact text block describing today's prescribed nutrition."""
    days_since_start = (today - plan_start).days
    cycle_week = max(0, days_since_start // 7) % 4
    weekday = today.weekday()
    dtype = today_day_type(cycle_week, weekday)
    day_data = DAY_TYPES[dtype]
    meals = _assemble_meals(dtype, cycle_week, weekday)
    tier = CALORIE_TIERS[day_data["calorie_tier"]]
    cycle_label = f"Week {cycle_week + 1}" + (" — Recovery" if cycle_week == 3 else "")
    rot_label = _BREAKFAST_ROTATION_LABEL.get(cycle_week, "")

    total_protein = sum(m[4] for m in meals)
    pre_din = _pre_dinner_protein(meals)
    pt = protein_target_g()

    lines = [
        "## Nutrition Plan — Today's Prescribed Meals",
        f"Cycle: {cycle_label}  |  Day type: {day_data['label']}  |  "
        f"Target: {tier['kcal']} kcal" + (f" ({tier['note']})" if tier.get("note") else ""),
    ]
    if rot_label and dtype in _WEEKDAY_BREAKFAST_TYPES:
        lines.append(f"Breakfast rotation: {rot_label}")
    lines += [
        f"Protein floor: {pt['low']}–{pt['high']}g/day ({pt['basis']}), distributed ~0.4 g/kg "
        f"across 4+ meals plus a ~40 g pre-sleep casein/dairy dose to preserve muscle in the deficit.",
        f"Today's meals deliver: {total_protein}g total  |  "
        f"Pre-dinner: {pre_din}g  — {day_data['protein_note']}",
        "",
        "Meals:",
    ]

    for slot, name, detail, kcal, prot, carbs in meals:
        name = _apply_rice_swap(name, cycle_week, weekday)
        lines.append(f"  {slot}: {name} — {kcal} kcal, {prot}g protein, {carbs}g carbs")
        lines.append(f"    {detail}")

    lines += ["", "Key principles:"]
    for p in PRINCIPLES:
        lines.append(f"  • {p}")

    lines += ["", f"Supplements ({_SUPPLEMENT_DISCLAIMER}):"]
    for name, dose, why in SUPPLEMENTS:
        lines.append(f"  • {name} — {dose}: {why}")

    return "\n".join(lines)


_WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _apply_rice_swap(name: str, cycle_week: int, weekday: int) -> str:
    """Apply the rice-variety rotation, swapping only the rice component.

    The batch-rice lunches are composite (e.g. "Batch Rice + Chicken 240g +
    Greek Yogurt"); we replace just the first " + "-separated part when it names
    the rice, leaving the protein components intact.
    """
    swap = _RICE_SWAP.get(cycle_week, {}).get(weekday)
    if not swap:
        return name
    parts = [p.strip() for p in re.split(r"\s*\+\s*", name)]
    if parts and "Rice" in parts[0]:
        parts[0] = swap
        return " + ".join(parts)
    return swap if "Rice" in name else name


def nutrition_week_context(plan_start: date, today: date) -> str:
    """Compact Mon–Sun overview of this week's prescribed meals.

    Gives the coach the whole week at a glance (day type + per-meal name and
    protein) so it can answer week-level questions — e.g. building a shopping
    list — without the athlete pasting anything. The full 4-week cycle and a
    per-week shopping tally are available on demand via `meal_cycle_full()`.
    """
    days_since_start = (today - plan_start).days
    cycle_week = max(0, days_since_start // 7) % 4
    cycle_label = f"Week {cycle_week + 1}" + (" — Recovery" if cycle_week == 3 else "")
    monday = today - timedelta(days=today.weekday())

    lines = [
        "## Nutrition Plan — This Week (Mon–Sun)",
        f"Cycle: {cycle_label}. Breakfast: {_BREAKFAST_ROTATION_LABEL.get(cycle_week, 'n/a')}. "
        "Meals below show name + kcal + protein per day. "
        "For the full 4-week cycle and an aggregated shopping list, call the "
        "get_meal_cycle tool.",
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
            f"  {_WEEKDAY_LABELS[wd]} {d.strftime('%d %b')}: {day_data['label']} "
            f"— {tier['kcal']} kcal, ~{total_protein}g protein{marker}"
        )
        for slot, name, _detail, kcal, prot, _carbs in meals:
            name = _apply_rice_swap(name, cycle_week, wd)
            lines.append(f"      {slot}: {name} ({kcal} kcal, {prot}g P)")
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
            name = _apply_rice_swap(name, cycle_week, wd)
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
        "Weeks 1 & 3: Set A breakfasts (overnight oats + egg muffins). "
        "Week 2: Set B breakfasts (oat bars + Skyr / yoghurt + eggs). "
        "Week 4: recovery week. Rice varieties rotate weeks 2–3.",
        "",
    ]
    for cw in range(4):
        cycle_label = f"WEEK {cw + 1}" + (" (Recovery)" if cw == 3 else "")
        lines.append(f"=== {cycle_label} — {_BREAKFAST_ROTATION_LABEL.get(cw, '')} ===")
        for wd in range(7):
            dtype = today_day_type(cw, wd)
            day_data = DAY_TYPES[dtype]
            meals = _assemble_meals(dtype, cw, wd)
            tier = CALORIE_TIERS[day_data["calorie_tier"]]
            total_protein = sum(meal[4] for meal in meals)
            lines.append(
                f"{_WEEKDAY_LABELS[wd]} — {day_data['label']} "
                f"({tier['kcal']} kcal, ~{total_protein}g protein):"
            )
            for slot, name, _detail, kcal, prot, carbs in meals:
                name = _apply_rice_swap(name, cw, wd)
                lines.append(f"  {slot}: {name} — {kcal} kcal, {prot}g P, {carbs}g C")
        lines.append(f"Shopping tally for Week {cw + 1} (component → times/week):")
        for comp, n in _week_shopping_tally(cw):
            lines.append(f"  {comp} ×{n}")
        lines.append("")
    return "\n".join(lines)

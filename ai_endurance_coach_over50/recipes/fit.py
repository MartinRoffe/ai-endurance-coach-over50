"""Fit one day's portions to a calorie target and a protein range.

Breakfast stays a real plate (0.75×, 1×, or 1.25×). Lunch and dinner move in
quarter-plate steps. Rice, pasta, potato, and bread scale on their own.
Evening yoghurt stays at or under 250 g. Easy days get one modest snack or none.
Hard and long days take the ride food the session length already asks for.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .catalog import recipe_by_id
from .model import Recipe, numbered_method, portion_grams_by_food, portion_macros
from .nutrition_table import add_macros, empty_macros, food, macros_for

_BF_STEPS = (0.75, 1.0, 1.25)
_PLATE_STEPS = (0.75, 1.0, 1.25, 1.5)
_SIDE_STEPS = (0.0, 0.5, 1.0, 1.5, 2.0)
_YOG_STEPS = (0, 50, 100, 150, 200, 250)
_MILK_STEPS = (0, 100, 150, 200, 250, 300, 350, 400)
# One modest snack, or none. Both sit inside 150–250 kcal.
_SNACKS = (
    ("none", {}),
    ("toast", {"bread": 60.0, "honey": 16.0}),
    ("toast", {"bread": 75.0, "honey": 22.0}),
)
_BANANA_G = 120.0
_BOTTLE_G = 60.0
# The day calorie card prices this homemade cake. Sweet cakes are the other batch.
_SAVOURY_CAKE_ID = "standard-rice-cake"


@dataclass(frozen=True)
class PortionPlan:
    bf: float
    lunch: float
    dinner: float
    lunch_side: float
    dinner_side: float
    yoghurt: int
    milk: int
    snack_foods: dict[str, float]
    training: dict


def _pack(macros: dict[str, float]) -> tuple[float, float, float, float]:
    return (macros["kcal"], macros["protein"], macros["carbs"], macros["dairy_calcium"])


def _add(a: tuple[float, float, float, float], b: tuple[float, float, float, float]):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2], a[3] + b[3])


def _foods_pack(foods: dict[str, float]) -> tuple[float, float, float, float]:
    return _pack(_foods_macros(foods))


def _foods_macros(foods: dict[str, float], cakes: int = 0) -> dict[str, float]:
    """Nutrients in a snack or ride slot.

    Rice cakes are the homemade savoury recipe, one serving per cake. The
    shop rice-cake row is not the piece the day is priced on.
    """
    total = empty_macros()
    for food_id, grams in foods.items():
        if food_id == "rice_cake" or grams <= 0:
            continue
        add_macros(total, macros_for(food_id, grams))
    if cakes:
        add_macros(total, portion_macros(recipe_by_id(_SAVOURY_CAKE_ID), cakes))
    return total


def _meal_ints(kcal: float, protein: float, carbs: float) -> tuple[int, int]:
    k = int(round(kcal))
    p = int(round(protein))
    c = int(round(carbs))
    floor = p * 4 + c * 4
    if k < floor:
        k = floor
    return k, p


def _times(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{text}×"


def _has_side(recipe: Recipe) -> bool:
    from .model import STARCH_IDS
    if recipe.serve_with:
        return True
    return any(item.food_id in STARCH_IDS for item in recipe.ingredients)


def training_foods(
    kind: str,
    dur_min: int,
    ref_date: date | None,
    *,
    ride: bool = True,
) -> dict:
    """Pre, during, and post food fixed by the session length.

    ``ride`` is an outdoor bike day. A short rower or MaxiClimber session
    keeps the pre/post snack on a hard day and skips during-session carbs.
    """
    pre: dict[str, float] = {}
    on_bike: dict[str, float] = {}
    post: dict[str, float] = {}
    cakes = 0
    bottles = 0
    note = ""
    if kind == "hard":
        pre["banana"] = _BANANA_G
        post["milk_semi"] = 300.0 if dur_min >= 60 else 250.0
        # Short indoor sessions (rower, MaxiClimber) do not take ride fuel.
        if ride or dur_min >= 75:
            if dur_min >= 120:
                cakes = 2
            elif dur_min >= 75:
                cakes = 1
    elif kind == "long" and dur_min >= 75 and ride:
        from ..nutrition_plan import fuel_prep_for_ride
        prep = fuel_prep_for_ride(dur_min, ref_date=ref_date)
        if prep.get("banana_before"):
            pre["banana"] = _BANANA_G
        cakes = int(prep["rice_cakes"])
        bottles = int(prep.get("carb_drink_bottles") or 0)
        post["milk_semi"] = 300.0
        note = prep.get("prep_note") or ""
    if bottles:
        on_bike["maltodextrin"] = bottles * _BOTTLE_G
    return {
        "pre": pre,
        "on_bike": on_bike,
        "post": post,
        "cakes": cakes,
        "bottles": bottles,
        "note": note,
        "allow_snack": kind == "easy" or (kind == "long" and dur_min < 75),
        "ride": ride,
    }


def on_bike_slot_totals(
    kind: str,
    dur_min: int,
    ref_date: date | None,
    *,
    ride: bool = True,
) -> tuple[int, int]:
    """Rounded kcal and protein of the on-bike slot. Zeros when it is empty."""
    training = training_foods(kind, int(dur_min or 0), ref_date, ride=ride)
    if not training["cakes"] and not training["on_bike"]:
        return 0, 0
    macros = _foods_macros(training["on_bike"], int(training["cakes"]))
    kcal, protein, _carbs = _meal_triple(macros)
    return kcal, protein


def on_bike_slot_kcal(
    kind: str,
    dur_min: int,
    ref_date: date | None,
    *,
    ride: bool = True,
) -> int:
    """Rounded kcal of the on-bike slot. Zero when that slot is empty."""
    return on_bike_slot_totals(kind, dur_min, ref_date, ride=ride)[0]


def _component_table(recipe: Recipe) -> tuple[dict, dict]:
    """Non-starch pot and carbohydrate side, packed for each step."""
    from .model import STARCH_IDS
    pot: dict[float, tuple[float, float, float, float]] = {}
    side: dict[float, tuple[float, float, float, float]] = {}
    for mult in _PLATE_STEPS:
        total = empty_macros()
        for item in recipe.ingredients:
            if item.food_id in STARCH_IDS:
                continue
            add_macros(total, macros_for(item.food_id, item.grams * mult / recipe.servings))
        pot[mult] = _pack(total)
    for scale in _SIDE_STEPS:
        total = empty_macros()
        for item in recipe.ingredients:
            if item.food_id not in STARCH_IDS:
                continue
            add_macros(total, macros_for(item.food_id, item.grams * scale / recipe.servings))
        for item in recipe.serve_with:
            add_macros(total, macros_for(item.food_id, item.grams * scale))
        side[scale] = _pack(total)
    return pot, side


def solve(
    breakfast: Recipe,
    lunch: Recipe,
    dinner: Recipe,
    *,
    lunch_fixed: bool = False,
    dinner_fixed: bool = False,
    target_kcal: int,
    protein_low: int,
    protein_high: int,
    kind: str,
    dur_min: int,
    ref_date: date | None = None,
    ride: bool = True,
    evening: tuple[int, int, int] | None = None,
) -> PortionPlan:
    """Pick the closest real portions. Slightly under the calorie target beats an oversized plate."""
    del lunch_fixed, dinner_fixed
    training = training_foods(kind, int(dur_min or 0), ref_date, ride=ride)
    if kind == "long":
        # Cake protein is eaten, so it must not push the plates under the protein ceiling.
        fuel_macros = _foods_macros(training["on_bike"], int(training["cakes"]))
        _fuel_kcal, fuel_protein, _fuel_carbs = _meal_triple(fuel_macros)
        protein_high = int(protein_high) + fuel_protein
    bf_pack = {mult: _pack(portion_macros(breakfast, mult)) for mult in _BF_STEPS}
    lunch_pot, lunch_side = _component_table(lunch)
    dinner_pot, dinner_side = _component_table(dinner)
    yog_pack = {grams: _pack(macros_for("yoghurt_hp", grams)) for grams in _YOG_STEPS}
    milk_pack = {grams: _pack(macros_for("milk_semi", grams)) for grams in _MILK_STEPS}
    snack_opts = _SNACKS if training["allow_snack"] else _SNACKS[:1]

    # Ride foods are separate meals, so round each one, not the sum.
    fixed_k = 0
    fixed_p = 0
    fixed_ca = 0.0
    for key in ("pre", "on_bike", "post"):
        foods = training[key]
        cakes = int(training["cakes"]) if key == "on_bike" else 0
        if not foods and not cakes:
            continue
        packed = _pack(_foods_macros(foods, cakes))
        ki, pi = _meal_ints(packed[0], packed[1], packed[2])
        # A long ride adds on-bike food on top of the base. Its protein still
        # counts. Its calories do not come out of breakfast, lunch, or dinner.
        if not (key == "on_bike" and kind == "long"):
            fixed_k += ki
        fixed_p += pi
        fixed_ca += packed[3]

    lunch_opts = []
    for mult in _PLATE_STEPS:
        for scale in _SIDE_STEPS:
            raw = _add(lunch_pot[mult], lunch_side[scale])
            ki, pi = _meal_ints(raw[0], raw[1], raw[2])
            lunch_opts.append((mult, scale, ki, pi, raw[3]))
    dinner_opts = []
    for mult in _PLATE_STEPS:
        for scale in _SIDE_STEPS:
            raw = _add(dinner_pot[mult], dinner_side[scale])
            ki, pi = _meal_ints(raw[0], raw[1], raw[2])
            dinner_opts.append((mult, scale, ki, pi, int(round(raw[2])), raw[3]))
    bf_opts = []
    for mult in _BF_STEPS:
        raw = bf_pack[mult]
        ki, pi = _meal_ints(raw[0], raw[1], raw[2])
        bf_opts.append((mult, ki, pi, raw[3]))
    evening_opts = []
    for yog in _YOG_STEPS:
        for milk in _MILK_STEPS:
            raw = _add(yog_pack[yog], milk_pack[milk])
            if yog == 0 and milk == 0:
                evening_opts.append((yog, milk, 0, 0, 0.0))
                continue
            ki, pi = _meal_ints(raw[0], raw[1], raw[2])
            evening_opts.append((yog, milk, ki, pi, raw[3]))
    snack_rows = []
    for name, foods in snack_opts:
        if not foods:
            snack_rows.append((name, foods, 0, 0, 0.0))
            continue
        raw = _foods_pack(foods)
        ki, pi = _meal_ints(raw[0], raw[1], raw[2])
        snack_rows.append((name, foods, ki, pi, raw[3]))

    band = max(1, int(round(target_kcal * 0.05)))
    best_score = float("inf")
    best: tuple | None = None
    for bf, bk, bp, bca in bf_opts:
        bf_pref = 0 if abs(bf - 1.0) < 0.01 else 100
        for lm, ls, lk, lp, lca in lunch_opts:
            for dm, ds, dk, dp, dc, dca in dinner_opts:
                plate_k = bk + lk + dk
                plate_p = bp + lp + dp
                plate_ca = bca + lca + dca
                for yog, milk, ek, ep, eca in evening_opts:
                    for sname, sfoods, sk, sp, sca in snack_rows:
                        kcal = fixed_k + plate_k + ek + sk
                        protein = fixed_p + plate_p + ep + sp
                        dairy = fixed_ca + plate_ca + eca + sca
                        score = bf_pref
                        score += abs(lm - 1.0) * 4 + abs(dm - 1.0) * 4
                        score += abs(ls - 1.0) * 2 + abs(ds - 1.0) * 2
                        if evening is not None:
                            # Prefer the dinner that matches this day's load.
                            # Missing the day calorie band or the protein range
                            # still costs more than missing the plate.
                            tek, tep, tec = evening
                            score += abs(dk - tek) * 2
                            score += abs(dp - tep) * 6
                            score += abs(dc - tec) * 3
                        # Yoghurt and milk top up calcium. They are expensive enough that a day
                        # which is already on target does not pour either one in for calories.
                        # Yoghurt is the cheaper calcium source, and it is capped at 250 g.
                        score += yog * 0.8 + milk * 0.9
                        if sfoods:
                            score += 25
                        gap = abs(kcal - target_kcal)
                        if kcal > target_kcal + band:
                            # Over the band is worse than being a bit short. Stay inside the portion caps.
                            score += 9000 + (kcal - target_kcal)
                        elif kcal < target_kcal - band:
                            score += 2000 + (target_kcal - kcal)
                        else:
                            score += gap
                        if protein < protein_low:
                            score += 8000 + (protein_low - protein) * 30
                        elif protein > protein_high:
                            score += 8000 + (protein - protein_high) * 30
                        if dairy < 1000:
                            score += 3000 + (1000 - dairy)
                        if score < best_score:
                            best_score = score
                            best = (bf, lm, dm, ls, ds, yog, milk, sfoods, kcal, protein)
    assert best is not None
    bf, lm, dm, ls, ds, yog, milk, sfoods, _kcal, _protein = best
    return PortionPlan(
        bf=bf,
        lunch=lm,
        dinner=dm,
        lunch_side=ls,
        dinner_side=ds,
        yoghurt=yog,
        milk=milk,
        snack_foods=dict(sfoods),
        training=training,
    )


def build_meals(
    plan: PortionPlan,
    breakfast: Recipe,
    lunch: Recipe,
    dinner: Recipe,
    *,
    kind: str,
    target_kcal: int | None = None,
) -> list[dict]:
    """Ordered slots. Macros are the rounded per-slot figures the pages show."""
    del kind
    meals: list[dict] = []
    meals.append(_recipe_meal("Breakfast", breakfast, plan.bf, plan.bf))
    training = plan.training
    ride = bool(training.get("ride", True))
    pre_slot = "Pre-ride" if ride else "Pre-session"
    during_slot = "On-bike" if ride else "During"
    post_slot = "Post-ride" if ride else "Post-session"
    if training["pre"]:
        meals.append(_food_meal(
            pre_slot,
            "Banana",
            training["pre"],
            "Eat the banana about 30–60 minutes before you start. One medium banana is about 120 g.",
        ))
    meals.append(_recipe_meal("Lunch", lunch, plan.lunch, plan.lunch_side))
    if training["cakes"] or training["on_bike"]:
        cakes = training["cakes"]
        bottles = training["bottles"]
        bits = []
        place = "the ride" if ride else "the session"
        if cakes:
            carbs_each = portion_macros(recipe_by_id(_SAVOURY_CAKE_ID), 1)["carbs"]
            bits.append(
                f"Take {cakes} homemade savoury rice cake{'s' if cakes != 1 else ''} "
                f"({round(carbs_each):.0f} g carbohydrate each) and eat them across {place}, with water. "
                "Cook a full batch in the small rice cooker. The method is on the recipe page."
            )
        if bottles:
            bits.append(
                f"Mix {bottles} maltodextrin bottle{'s' if bottles != 1 else ''} "
                f"({int(bottles * _BOTTLE_G)} g powder) so {place} hits the carb target."
            )
        name = "Savoury rice cakes"
        if bottles and cakes:
            name = "Savoury rice cakes and carb drink"
        elif bottles:
            name = "Carb drink"
        meal = _food_meal(
            during_slot, name, training["on_bike"], " ".join(bits), cakes=cakes,
        )
        if cakes:
            shown = _shown_ride_lines(training["on_bike"], cakes)
            meal["display_ingredients"] = shown
            meal["recipe_id"] = _SAVOURY_CAKE_ID
            meal["rice_cakes"] = cakes
            meal["multiplier"] = None
        meals.append(meal)
    if training["post"]:
        ml = int(round(training["post"]["milk_semi"]))
        meals.append(_food_meal(
            post_slot,
            "Milk",
            training["post"],
            f"Drink {ml} ml semi-skimmed milk within an hour of finishing. That is the recovery drink.",
        ))
    if plan.snack_foods:
        meals.append(_food_meal(
            "Snack",
            "Toast and honey",
            plan.snack_foods,
            _snack_detail(plan.snack_foods),
        ))
    meals.append(_recipe_meal("Dinner", dinner, plan.dinner, plan.dinner_side))
    if plan.yoghurt or plan.milk:
        foods: dict[str, float] = {}
        if plan.yoghurt:
            foods["yoghurt_hp"] = float(plan.yoghurt)
        if plan.milk:
            foods["milk_semi"] = float(plan.milk)
        if plan.yoghurt and plan.milk:
            name = f"Evening yoghurt, {plan.yoghurt} g, and milk"
            detail = (
                f"Weigh {plan.yoghurt} g plain high-protein yoghurt and drink {plan.milk} ml "
                "semi-skimmed milk with it. Evening yoghurt stays at or under 250 g. "
                "It tops up calcium. It is not the main meal."
            )
        elif plan.yoghurt:
            name = f"Evening yoghurt, {plan.yoghurt} g"
            detail = (
                f"Weigh {plan.yoghurt} g plain high-protein yoghurt into a bowl. "
                "Evening yoghurt stays at or under 250 g. It tops up calcium. It is not the main meal."
            )
        else:
            name = "Evening milk"
            detail = (
                f"Drink {plan.milk} ml semi-skimmed milk in the evening. "
                "It tops up calcium. It is not a second dinner."
            )
        meals.append(_food_meal("Evening", name, foods, detail))
    if target_kcal is not None:
        _annotate_shortfall(meals, target_kcal)
    return meals


def _annotate_shortfall(meals: list[dict], target_kcal: int) -> None:
    total = sum(meal["kcal"] for meal in meals)
    band = max(1, int(round(target_kcal * 0.05)))
    if abs(total - target_kcal) <= band:
        return
    gap = target_kcal - total
    direction = "under" if gap > 0 else "over"
    sentence = (
        f" Portions stay at real plate sizes, so this day is {abs(gap)} kcal {direction} "
        f"the {target_kcal:,} kcal target."
    )
    for meal in meals:
        if meal["slot"] == "Dinner":
            meal["detail"] += sentence
            return


def _side_sentence(recipe: Recipe, side: float) -> str:
    if not _has_side(recipe):
        return ""
    if side <= 0:
        return " No carbohydrate side with this plate today."
    if abs(side - 1.0) < 0.01:
        return ""
    return f" Carbohydrate side {_times(side)} the written amount."


def _recipe_meal(slot: str, recipe: Recipe, multiplier: float, side: float) -> dict:
    macros = portion_macros(recipe, multiplier, side_multiplier=side)
    grams = portion_grams_by_food(recipe, multiplier, side_multiplier=side)
    kcal, protein, carbs = _meal_triple(macros)
    portion_bit = ""
    if abs(multiplier - 1) >= 0.03:
        portion_bit = f" Portion {_times(multiplier)} the meat, vegetables, and sauce."
    side_bit = _side_sentence(recipe, side)
    if recipe.batch:
        how = (
            f"About {int(round(macros['grams']))} g raw. "
            "Reheat until piping hot: microwave 3 minutes, stir, then 1 minute more, or simmer 5 minutes."
            f"{portion_bit}{side_bit} {recipe.summary}"
        )
    else:
        how = f"About {int(round(macros['grams']))} g raw.{portion_bit}{side_bit} {numbered_method(recipe)}"
    return {
        "slot": slot,
        "name": recipe.name,
        "detail": how,
        "kcal": kcal,
        "protein": protein,
        "carbs": carbs,
        "fat": macros["fat"],
        "calcium": macros["calcium"],
        "dairy_calcium": macros["dairy_calcium"],
        "grams_by_food": grams,
        "recipe_id": recipe.id,
        "multiplier": multiplier,
        "side_multiplier": side,
    }


def _meal_triple(macros: dict[str, float]) -> tuple[int, int, int]:
    k, p = _meal_ints(macros["kcal"], macros["protein"], macros["carbs"])
    c = int(round(macros["carbs"]))
    return k, p, c


def _food_meal(
    slot: str,
    name: str,
    foods: dict[str, float],
    detail: str,
    *,
    cakes: int = 0,
) -> dict:
    macros = _foods_macros(foods, cakes)
    kcal, protein, carbs = _meal_triple(macros)
    return {
        "slot": slot,
        "name": name,
        "detail": detail,
        "kcal": kcal,
        "protein": protein,
        "carbs": carbs,
        "fat": macros["fat"],
        "calcium": macros["calcium"],
        "dairy_calcium": macros["dairy_calcium"],
        "grams_by_food": {k: v for k, v in foods.items() if v > 0},
        "recipe_id": None,
        "multiplier": 1.0,
        "side_multiplier": 1.0,
    }


def _shown_ride_lines(foods: dict[str, float], cakes: int) -> list[str]:
    """What the page lists for the on-bike slot. Cake calories come from the recipe."""
    lines = [f"Homemade savoury rice cakes — {cakes}"]
    for food_id, grams in sorted(foods.items(), key=lambda pair: food(pair[0]).name):
        if food_id == "rice_cake" or grams < 0.5:
            continue
        row = food(food_id)
        unit = "ml" if row.liquid else "g"
        lines.append(f"{row.name} — {int(round(grams))} {unit}")
    return lines


def _snack_detail(foods: dict[str, float]) -> str:
    bread = int(round(foods.get("bread", 0)))
    honey = int(round(foods.get("honey", 0)))
    return (
        f"Toast {bread} g white bread and spread {honey} g honey on it. "
        "One snack, between meals. Easy days do not add a second snack."
    )


def published_totals(meals: list[dict]) -> dict[str, float]:
    return {
        "kcal": sum(m["kcal"] for m in meals),
        "protein": sum(m["protein"] for m in meals),
        "carbs": sum(m["carbs"] for m in meals),
        "calcium": sum(m["calcium"] for m in meals),
        "dairy_calcium": sum(m["dairy_calcium"] for m in meals),
    }

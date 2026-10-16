"""Fit one day's portions to a calorie target and a protein range.

Batch lunch and dinner stay at the written portion (you cooked equal tubs).
Breakfast, weekend plates, evening yoghurt, milk, and training snacks move.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .model import Recipe, numbered_method, portion_grams_by_food, portion_macros
from .nutrition_table import add_macros, empty_macros, macros_for

_BF_MIN, _BF_MAX = 0.60, 1.45
_PLATE_MIN, _PLATE_MAX = 0.60, 1.40
_YOG_MAX = 750.0
_MILK_MAX = 750.0
_HONEY_MAX = 100.0
_OIL_MAX = 25.0
_BANANA_G = 120.0
_BREAD_G = 40.0
_CAKE_G = 25.0
_APPLE_G = 150.0


@dataclass
class Flex:
    bf: float = 1.0
    lunch: float = 1.0
    dinner: float = 1.0
    yoghurt: float = 0.0
    milk: float = 0.0
    banana: int = 0
    bread: int = 0
    honey: float = 0.0
    cakes: int = 0
    apple: int = 0
    oil: float = 0.0


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def minimums(kind: str, dur_min: int) -> Flex:
    """Training food that has to be on the plate. Easy days start empty."""
    base = Flex()
    if kind == "hard":
        base.banana = 1
        base.milk = 250
    elif kind == "long":
        base.bread = 1
        base.honey = 15
        base.milk = 300
        if dur_min >= 75:
            base.cakes = max(1, int(round(dur_min / 60)))
    return base


def _clamp(flex: Flex, mins: Flex, *, lunch_fixed: bool, dinner_fixed: bool) -> Flex:
    return Flex(
        bf=_clip(flex.bf, _BF_MIN, _BF_MAX),
        lunch=1.0 if lunch_fixed else _clip(flex.lunch, _PLATE_MIN, _PLATE_MAX),
        dinner=1.0 if dinner_fixed else _clip(flex.dinner, _PLATE_MIN, _PLATE_MAX),
        yoghurt=_clip(max(flex.yoghurt, mins.yoghurt), 0, _YOG_MAX),
        milk=_clip(max(flex.milk, mins.milk), 0, _MILK_MAX),
        banana=int(_clip(max(flex.banana, mins.banana), 0, 4)),
        bread=int(_clip(max(flex.bread, mins.bread), 0, 6)),
        honey=_clip(max(flex.honey, mins.honey), 0, _HONEY_MAX),
        cakes=int(_clip(max(flex.cakes, mins.cakes), 0, 14)),
        apple=int(_clip(max(flex.apple, mins.apple), 0, 2)),
        oil=_clip(max(flex.oil, mins.oil), 0, _OIL_MAX),
    )


def _totals(
    flex: Flex,
    breakfast: Recipe,
    lunch: Recipe,
    dinner: Recipe,
) -> dict[str, float]:
    total = empty_macros()
    add_macros(total, portion_macros(breakfast, flex.bf))
    add_macros(total, portion_macros(lunch, flex.lunch))
    add_macros(total, portion_macros(dinner, flex.dinner))
    add_macros(total, macros_for("yoghurt_hp", flex.yoghurt))
    add_macros(total, macros_for("milk_semi", flex.milk))
    add_macros(total, macros_for("banana", flex.banana * _BANANA_G))
    add_macros(total, macros_for("bread", flex.bread * _BREAD_G))
    add_macros(total, macros_for("honey", flex.honey))
    add_macros(total, macros_for("rice_cake", flex.cakes * _CAKE_G))
    add_macros(total, macros_for("apple", flex.apple * _APPLE_G))
    add_macros(total, macros_for("olive_oil", flex.oil))
    return total


def _rounded_kcal_protein(total: dict[str, float]) -> tuple[int, int]:
    """Match the integers stored on each meal, summed."""
    # One rounding pass on the day is close enough for the search; the
    # published meals round per slot, so the polish below checks that sum.
    return int(round(total["kcal"])), int(round(total["protein"]))


def _score(
    flex: Flex,
    breakfast: Recipe,
    lunch: Recipe,
    dinner: Recipe,
    *,
    target_kcal: int,
    protein_low: int,
    protein_high: int,
) -> float:
    total = _totals(flex, breakfast, lunch, dinner)
    kcal, protein = _rounded_kcal_protein(total)
    dairy = total["dairy_calcium"]
    penalty = abs(kcal - target_kcal)
    if protein < protein_low:
        penalty += (protein_low - protein) * 40
    elif protein > protein_high:
        penalty += (protein - protein_high) * 40
    else:
        mid = (protein_low + protein_high) / 2
        penalty += abs(protein - mid) * 0.4
    if dairy < 1000:
        penalty += (1000 - dairy) * 2
    elif dairy > 1400:
        penalty += (dairy - 1400) * 0.05
    # Prefer not to pour oil or honey on an ordinary day.
    penalty += flex.oil * 0.4
    penalty += max(0.0, flex.honey - 40) * 0.15
    return penalty


def _neighbours(flex: Flex) -> list[Flex]:
    steps: list[Flex] = []
    steps.append(replace(flex, bf=flex.bf + 0.05))
    steps.append(replace(flex, bf=flex.bf - 0.05))
    steps.append(replace(flex, lunch=flex.lunch + 0.05))
    steps.append(replace(flex, lunch=flex.lunch - 0.05))
    steps.append(replace(flex, dinner=flex.dinner + 0.05))
    steps.append(replace(flex, dinner=flex.dinner - 0.05))
    steps.append(replace(flex, yoghurt=flex.yoghurt + 25))
    steps.append(replace(flex, yoghurt=flex.yoghurt - 25))
    steps.append(replace(flex, milk=flex.milk + 50))
    steps.append(replace(flex, milk=flex.milk - 50))
    steps.append(replace(flex, banana=flex.banana + 1))
    steps.append(replace(flex, banana=flex.banana - 1))
    steps.append(replace(flex, bread=flex.bread + 1))
    steps.append(replace(flex, bread=flex.bread - 1))
    steps.append(replace(flex, honey=flex.honey + 10))
    steps.append(replace(flex, honey=flex.honey - 10))
    steps.append(replace(flex, cakes=flex.cakes + 1))
    steps.append(replace(flex, cakes=flex.cakes - 1))
    steps.append(replace(flex, apple=flex.apple + 1))
    steps.append(replace(flex, apple=flex.apple - 1))
    steps.append(replace(flex, oil=flex.oil + 5))
    steps.append(replace(flex, oil=flex.oil - 5))
    return steps


def _search(
    start: Flex,
    breakfast: Recipe,
    lunch: Recipe,
    dinner: Recipe,
    mins: Flex,
    *,
    lunch_fixed: bool,
    dinner_fixed: bool,
    target_kcal: int,
    protein_low: int,
    protein_high: int,
    rounds: int = 40,
) -> Flex:
    current = _clamp(start, mins, lunch_fixed=lunch_fixed, dinner_fixed=dinner_fixed)
    best = current
    best_score = _score(
        best, breakfast, lunch, dinner,
        target_kcal=target_kcal, protein_low=protein_low, protein_high=protein_high,
    )
    for _ in range(rounds):
        improved = False
        for nxt in _neighbours(current):
            nxt = _clamp(nxt, mins, lunch_fixed=lunch_fixed, dinner_fixed=dinner_fixed)
            score = _score(
                nxt, breakfast, lunch, dinner,
                target_kcal=target_kcal, protein_low=protein_low, protein_high=protein_high,
            )
            if score + 0.01 < best_score:
                best = nxt
                best_score = score
                improved = True
        current = best
        if not improved:
            break
    return best


def _starts(mins: Flex, kind: str) -> list[Flex]:
    starts = [
        Flex(bf=1.0, lunch=1.0, dinner=1.0, yoghurt=200, milk=200),
        Flex(bf=0.65, lunch=0.7, dinner=0.7, yoghurt=500, milk=200),
        Flex(bf=0.6, lunch=1.0, dinner=1.0, yoghurt=650),
        Flex(bf=1.3, lunch=1.2, dinner=1.2, yoghurt=150, milk=250, banana=2, bread=2, honey=30, cakes=4),
        Flex(bf=1.15, lunch=1.0, dinner=1.0, yoghurt=100, milk=400, cakes=8, honey=40, banana=2),
    ]
    if kind == "easy":
        starts.append(Flex(bf=0.85, lunch=0.85, dinner=0.85, yoghurt=350, milk=150, apple=1))
    starts.append(Flex(bf=0.6, lunch=0.6, dinner=0.6, yoghurt=700, milk=250))
    starts.append(Flex(bf=0.6, lunch=0.85, dinner=1.1, yoghurt=650, milk=200))
    return starts


def solve(
    breakfast: Recipe,
    lunch: Recipe,
    dinner: Recipe,
    *,
    lunch_fixed: bool,
    dinner_fixed: bool,
    target_kcal: int,
    protein_low: int,
    protein_high: int,
    kind: str,
    dur_min: int,
) -> Flex:
    mins = minimums(kind, dur_min)
    best: Flex | None = None
    best_score = float("inf")
    for start in _starts(mins, kind):
        found = _search(
            start, breakfast, lunch, dinner, mins,
            lunch_fixed=lunch_fixed, dinner_fixed=dinner_fixed,
            target_kcal=target_kcal, protein_low=protein_low, protein_high=protein_high,
        )
        score = _score(
            found, breakfast, lunch, dinner,
            target_kcal=target_kcal, protein_low=protein_low, protein_high=protein_high,
        )
        if score < best_score:
            best = found
            best_score = score
    assert best is not None
    return _polish_rounded(
        best, breakfast, lunch, dinner, mins,
        lunch_fixed=lunch_fixed, dinner_fixed=dinner_fixed,
        target_kcal=target_kcal, protein_low=protein_low, protein_high=protein_high,
        kind=kind,
    )


def _meal_ints(kcal: float, protein: float, carbs: float) -> tuple[int, int, int]:
    k = int(round(kcal))
    p = int(round(protein))
    c = int(round(carbs))
    floor = p * 4 + c * 4
    if k < floor:
        k = floor
    return k, p, c


def build_meals(
    flex: Flex,
    breakfast: Recipe,
    lunch: Recipe,
    dinner: Recipe,
    *,
    kind: str,
) -> list[dict]:
    """Ordered slots. Macros are the rounded per-slot figures the pages show."""
    meals: list[dict] = []
    meals.append(_recipe_meal("Breakfast", breakfast, flex.bf, extra_oil=flex.oil))

    pre_banana = 1 if kind == "hard" and flex.banana >= 1 else 0
    pre_bread = 1 if kind == "long" and flex.bread >= 1 else 0
    pre_honey = min(flex.honey, 20.0) if kind == "long" and flex.honey > 0 else 0.0
    if kind == "hard" and pre_banana:
        meals.append(_food_meal(
            "Pre-ride",
            "Banana",
            {"banana": _BANANA_G},
            "Eat the banana 30–60 minutes before you start. One medium banana is about 120 g.",
        ))
    elif kind == "long" and pre_bread:
        meals.append(_food_meal(
            "Pre-ride",
            "Toast and honey",
            {"bread": _BREAD_G, "honey": pre_honey or 15},
            "Toast one slice (40 g) and spread the honey on it. Eat it 60–90 minutes before a long session.",
        ))

    meals.append(_recipe_meal("Lunch", lunch, flex.lunch))

    snack_cakes = 0
    if kind == "long" and flex.cakes:
        meals.append(_food_meal(
            "On-bike",
            "Rice cakes" if flex.cakes > 1 else "Rice cake",
            {"rice_cake": flex.cakes * _CAKE_G},
            (
                f"Take {flex.cakes} plain rice cake{'s' if flex.cakes != 1 else ''} "
                f"({int(flex.cakes * _CAKE_G)} g). Eat them across the session, with water."
            ),
        ))
    elif flex.cakes:
        snack_cakes = flex.cakes

    post_milk = 0.0
    if kind in ("hard", "long") and flex.milk > 0:
        post_milk = min(flex.milk, 400 if kind == "long" else 300)
        meals.append(_food_meal(
            "Post-ride",
            "Milk",
            {"milk_semi": post_milk},
            (
                f"Drink {int(round(post_milk))} ml semi-skimmed milk within an hour of finishing. "
                "That is the recovery drink."
            ),
        ))

    snack_foods: dict[str, float] = {}
    extra_banana = flex.banana - pre_banana
    if extra_banana > 0:
        snack_foods["banana"] = extra_banana * _BANANA_G
    extra_bread = flex.bread - pre_bread
    if extra_bread > 0:
        snack_foods["bread"] = extra_bread * _BREAD_G
    extra_honey = flex.honey - pre_honey
    if extra_honey > 0.5:
        snack_foods["honey"] = extra_honey
    extra_milk = flex.milk - post_milk
    if extra_milk > 10:
        snack_foods["milk_semi"] = extra_milk
    if snack_cakes:
        snack_foods["rice_cake"] = snack_cakes * _CAKE_G
    if flex.apple:
        snack_foods["apple"] = flex.apple * _APPLE_G
    if snack_foods:
        meals.append(_food_meal("Snack", _snack_name(snack_foods), snack_foods, _snack_detail(snack_foods)))

    meals.append(_recipe_meal("Dinner", dinner, flex.dinner))

    if flex.yoghurt >= 20:
        meals.append(_food_meal(
            "Evening",
            f"Evening yoghurt, {int(round(flex.yoghurt))} g",
            {"yoghurt_hp": flex.yoghurt},
            (
                f"Weigh {int(round(flex.yoghurt))} g plain high-protein yoghurt into a bowl. "
                "Eat it in the evening, on its own. It is the calcium top-up, not a spoon on dinner."
            ),
        ))
    return meals


def _recipe_meal(slot: str, recipe: Recipe, multiplier: float, extra_oil: float = 0.0) -> dict:
    macros = portion_macros(recipe, multiplier)
    grams = portion_grams_by_food(recipe, multiplier)
    if extra_oil > 0.5 and slot == "Breakfast":
        add_macros(macros, macros_for("olive_oil", extra_oil))
        grams["olive_oil"] = grams.get("olive_oil", 0.0) + extra_oil
    kcal, protein, carbs = _meal_ints(macros["kcal"], macros["protein"], macros["carbs"])
    mult_bit = ""
    if abs(multiplier - 1) >= 0.03:
        mult_bit = f" Portion {multiplier:.2f}× the written plate."
    oil_bit = ""
    if extra_oil > 0.5 and slot == "Breakfast":
        oil_bit = f" Use an extra {int(round(extra_oil))} g olive oil in the pan."
    if recipe.batch:
        how = (
            f"About {int(round(macros['grams']))} g raw, one equal portion of the Sunday batch. "
            "Reheat until piping hot: microwave 3 minutes, stir, then 1 minute more, or simmer 5 minutes."
            f"{mult_bit} {recipe.summary}"
        )
    else:
        how = f"About {int(round(macros['grams']))} g raw.{mult_bit}{oil_bit} {numbered_method(recipe)}"
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
    }


def _food_meal(slot: str, name: str, foods: dict[str, float], detail: str) -> dict:
    macros = empty_macros()
    for food_id, grams in foods.items():
        if grams > 0:
            add_macros(macros, macros_for(food_id, grams))
    kcal, protein, carbs = _meal_ints(macros["kcal"], macros["protein"], macros["carbs"])
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
    }


def _snack_name(foods: dict[str, float]) -> str:
    labels = []
    if foods.get("banana"):
        labels.append("banana")
    if foods.get("bread") and foods.get("honey"):
        labels.append("toast and honey")
    elif foods.get("bread"):
        labels.append("toast")
    elif foods.get("honey"):
        labels.append("honey")
    if foods.get("apple"):
        labels.append("apple")
    if foods.get("rice_cake"):
        labels.append("rice cakes")
    if foods.get("milk_semi"):
        labels.append("milk")
    if not labels:
        return "Snack"
    if len(labels) == 1 and labels[0] == "banana":
        return "Banana"
    if labels == ["toast and honey"]:
        return "Toast and honey"
    if labels == ["apple"]:
        return "Apple"
    if labels == ["milk"]:
        return "Glass of milk"
    if labels == ["rice cakes"]:
        return "Rice cakes"
    return "Snack — " + ", ".join(labels)


def _snack_detail(foods: dict[str, float]) -> str:
    bits = []
    if foods.get("banana"):
        bits.append(f"{int(round(foods['banana']))} g banana")
    if foods.get("bread"):
        bits.append(f"{int(round(foods['bread']))} g white bread")
    if foods.get("honey"):
        bits.append(f"{int(round(foods['honey']))} g honey")
    if foods.get("apple"):
        bits.append(f"{int(round(foods['apple']))} g apple")
    if foods.get("rice_cake"):
        bits.append(f"{int(round(foods['rice_cake']))} g plain rice cakes")
    if foods.get("milk_semi"):
        bits.append(f"{int(round(foods['milk_semi']))} ml semi-skimmed milk")
    return "Snack: " + ", ".join(bits) + ". Eat it between meals."


def published_totals(meals: list[dict]) -> dict[str, float]:
    return {
        "kcal": sum(m["kcal"] for m in meals),
        "protein": sum(m["protein"] for m in meals),
        "carbs": sum(m["carbs"] for m in meals),
        "calcium": sum(m["calcium"] for m in meals),
        "dairy_calcium": sum(m["dairy_calcium"] for m in meals),
    }


def _polish_rounded(
    flex: Flex,
    breakfast: Recipe,
    lunch: Recipe,
    dinner: Recipe,
    mins: Flex,
    *,
    lunch_fixed: bool,
    dinner_fixed: bool,
    target_kcal: int,
    protein_low: int,
    protein_high: int,
    kind: str,
) -> Flex:
    """Nudge yoghurt, milk, and honey so the summed rounded meals land in range."""
    best = flex
    best_score = _published_score(
        flex, breakfast, lunch, dinner, kind,
        target_kcal=target_kcal, protein_low=protein_low, protein_high=protein_high,
    )
    yoghurt_steps = range(-120, 121, 20)
    milk_steps = range(-150, 151, 50)
    honey_steps = range(-40, 41, 10)
    for dy in yoghurt_steps:
        for dm in milk_steps:
            for dh in honey_steps:
                trial = _clamp(
                    replace(
                        flex,
                        yoghurt=flex.yoghurt + dy,
                        milk=flex.milk + dm,
                        honey=flex.honey + dh,
                    ),
                    mins,
                    lunch_fixed=lunch_fixed,
                    dinner_fixed=dinner_fixed,
                )
                score = _published_score(
                    trial, breakfast, lunch, dinner, kind,
                    target_kcal=target_kcal, protein_low=protein_low, protein_high=protein_high,
                )
                if score < best_score:
                    best = trial
                    best_score = score
    return _fine_tune(
        best, breakfast, lunch, dinner, mins,
        lunch_fixed=lunch_fixed, dinner_fixed=dinner_fixed,
        target_kcal=target_kcal, protein_low=protein_low, protein_high=protein_high,
        kind=kind,
    )


def _published_score(
    flex: Flex,
    breakfast: Recipe,
    lunch: Recipe,
    dinner: Recipe,
    kind: str,
    *,
    target_kcal: int,
    protein_low: int,
    protein_high: int,
) -> float:
    meals = build_meals(flex, breakfast, lunch, dinner, kind=kind)
    totals = published_totals(meals)
    kcal = totals["kcal"]
    protein = totals["protein"]
    dairy = totals["dairy_calcium"]
    band = max(1, int(round(target_kcal * 0.05)))
    penalty = abs(kcal - target_kcal)
    if abs(kcal - target_kcal) > band:
        penalty += 1000 + abs(kcal - target_kcal)
    if protein < protein_low or protein > protein_high:
        gap = protein_low - protein if protein < protein_low else protein - protein_high
        penalty += 1000 + gap * 20
    if dairy < 1000:
        penalty += 1000 + (1000 - dairy)
    return penalty


def _fine_tune(
    flex: Flex,
    breakfast: Recipe,
    lunch: Recipe,
    dinner: Recipe,
    mins: Flex,
    *,
    lunch_fixed: bool,
    dinner_fixed: bool,
    target_kcal: int,
    protein_low: int,
    protein_high: int,
    kind: str,
) -> Flex:
    """Small steps so rounding does not leave the day just outside the band."""
    current = flex
    best_score = _published_score(
        current, breakfast, lunch, dinner, kind,
        target_kcal=target_kcal, protein_low=protein_low, protein_high=protein_high,
    )
    for _ in range(30):
        improved = False
        trials = [
            replace(current, yoghurt=current.yoghurt + 10),
            replace(current, yoghurt=current.yoghurt - 10),
            replace(current, milk=current.milk + 25),
            replace(current, milk=current.milk - 25),
            replace(current, honey=current.honey + 5),
            replace(current, honey=current.honey - 5),
            replace(current, bf=current.bf + 0.02),
            replace(current, bf=current.bf - 0.02),
            replace(current, lunch=current.lunch + 0.02),
            replace(current, lunch=current.lunch - 0.02),
            replace(current, dinner=current.dinner + 0.02),
            replace(current, dinner=current.dinner - 0.02),
            replace(current, oil=current.oil + 3),
            replace(current, oil=current.oil - 3),
            replace(current, cakes=current.cakes + 1),
            replace(current, cakes=current.cakes - 1),
            replace(current, bf=current.bf - 0.05, yoghurt=current.yoghurt + 25),
            replace(current, bf=current.bf + 0.05, yoghurt=current.yoghurt - 20),
            replace(current, milk=current.milk - 50, yoghurt=current.yoghurt + 20),
            replace(current, lunch=current.lunch - 0.05, yoghurt=current.yoghurt + 25),
            replace(current, dinner=current.dinner - 0.05, yoghurt=current.yoghurt + 25),
        ]
        for trial in trials:
            trial = _clamp(trial, mins, lunch_fixed=lunch_fixed, dinner_fixed=dinner_fixed)
            score = _published_score(
                trial, breakfast, lunch, dinner, kind,
                target_kcal=target_kcal, protein_low=protein_low, protein_high=protein_high,
            )
            if score + 0.01 < best_score:
                current = trial
                best_score = score
                improved = True
                break
        if not improved:
            break
    return current

"""Four-week menu: Sunday batch feeds Mon–Fri, weekends are cooked fresh."""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache

from .catalog import (
    BATCHES,
    BREAKFASTS,
    COOKED_SERVINGS,
    WEEKDAY_BREAKFAST_IDS,
    WEEKDAY_PLATE,
    WEEKEND,
    WEEKS,
    recipe_by_id,
)
from .fit import build_meals, published_totals, solve
from .model import batch_grams_by_food, numbered_method, portion_macros, shop_line
from .nutrition_table import AISLE_ORDER, food

_WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def breakfast_for(cycle_week: int, weekday: int):
    if weekday == 5:
        return BREAKFASTS["full-english"]
    if weekday == 6:
        return BREAKFASTS[WEEKDAY_BREAKFAST_IDS[(cycle_week + 3) % len(WEEKDAY_BREAKFAST_IDS)]]
    return BREAKFASTS[WEEKDAY_BREAKFAST_IDS[(cycle_week * 5 + weekday) % len(WEEKDAY_BREAKFAST_IDS)]]


def _plates(cycle_week: int, weekday: int):
    week = WEEKS[cycle_week % 4]
    if weekday <= 4:
        lunch_key, dinner_key = WEEKDAY_PLATE[weekday]
        return recipe_by_id(week[lunch_key]), recipe_by_id(week[dinner_key]), True, True
    if weekday == 5:
        return recipe_by_id(week["sat_lunch"]), recipe_by_id(week["sat_dinner"]), False, False
    return recipe_by_id(week["sun_lunch"]), recipe_by_id(week["sun_dinner"]), False, False


@lru_cache(maxsize=512)
def plan_day(
    cycle_week: int,
    weekday: int,
    *,
    target_kcal: int,
    protein_low: int,
    protein_high: int,
    kind: str = "easy",
    dur_min: int = 0,
) -> dict:
    """One day's meals, scaled so kcal and protein land on the targets."""
    breakfast = breakfast_for(cycle_week, weekday)
    lunch, dinner, lunch_fixed, dinner_fixed = _plates(cycle_week, weekday)
    flex = solve(
        breakfast,
        lunch,
        dinner,
        lunch_fixed=lunch_fixed,
        dinner_fixed=dinner_fixed,
        target_kcal=int(target_kcal),
        protein_low=int(protein_low),
        protein_high=int(protein_high),
        kind=kind,
        dur_min=int(dur_min or 0),
    )
    meals = build_meals(flex, breakfast, lunch, dinner, kind=kind)
    totals = published_totals(meals)
    base = (
        portion_macros(breakfast, 1)["kcal"]
        + portion_macros(lunch, 1)["kcal"]
        + portion_macros(dinner, 1)["kcal"]
    )
    return {
        "meals": meals,
        "totals": totals,
        "base_kcal": int(round(base)),
        "target_kcal": int(target_kcal),
        "kind": kind,
        "breakfast_id": breakfast.id,
        "lunch_id": lunch.id,
        "dinner_id": dinner.id,
    }


def meals_as_tuples(day: dict) -> list[tuple]:
    return [
        (m["slot"], m["name"], m["detail"], m["kcal"], m["protein"], m["carbs"])
        for m in day["meals"]
    ]


def portion_ledger(cycle_week: int) -> dict[str, dict]:
    """Cooked portions, portions eaten Mon–Fri, and the freezer remainder."""
    week = WEEKS[cycle_week % 4]
    out: dict[str, dict] = {}
    for key, cooked in COOKED_SERVINGS.items():
        recipe = recipe_by_id(week[key])
        eaten = sum(1 for pair in WEEKDAY_PLATE for slot in pair if slot == key)
        frozen = cooked - eaten
        out[recipe.id] = {
            "id": recipe.id,
            "name": recipe.name,
            "key": key,
            "cooked": cooked,
            "eaten": eaten,
            "frozen": frozen,
            "servings_on_recipe": recipe.servings,
        }
    return out


def _freezer_line(recipe_id: str, info: dict) -> str:
    recipe = recipe_by_id(recipe_id)
    frozen = info["frozen"]
    if frozen <= 0:
        return "Eat every portion this week. " + recipe.freezer
    return (
        f"Cook {info['cooked']} portions. Eat {info['eaten']} this week. "
        f"Freeze {frozen}. " + recipe.freezer
    )


def _card(recipe_id: str, info: dict) -> dict:
    recipe = recipe_by_id(recipe_id)
    macros = portion_macros(recipe, 1)
    shop = []
    for food_id, grams in batch_grams_by_food(recipe).items():
        shop.append(shop_line(food_id, grams))
    if recipe.serve_with and info["eaten"]:
        for item in recipe.serve_with:
            shop.append(shop_line(item.food_id, item.grams * info["eaten"]) + " (with the bowls you eat)")
    return {
        "id": recipe.id,
        "name": recipe.name,
        "method": _freezer_line(recipe.id, info),
        "steps": numbered_method(recipe),
        "method_steps": list(recipe.method),
        "shop": shop,
        "kind": "soup" if recipe.slot == "soup" else "dinner",
        "protein": recipe.protein,
        "equipment": list(recipe.equipment),
        "fridge": recipe.fridge,
        "freezer": _freezer_line(recipe.id, info),
        "summary": recipe.summary,
        "servings": info["cooked"],
        "eaten": info["eaten"],
        "frozen": info["frozen"],
        "per_portion": {
            "kcal": int(round(macros["kcal"])),
            "protein": int(round(macros["protein"])),
            "carbs": int(round(macros["carbs"])),
            "fat": int(round(macros["fat"])),
            "calcium_mg": int(round(macros["calcium"])),
            "grams": int(round(macros["grams"])),
        },
    }


def cook_plan(cycle_week: int) -> dict:
    """Two one-pots and one soup for this cycle week, plus how the week eats them."""
    week = WEEKS[cycle_week % 4]
    ledger = portion_ledger(cycle_week)
    days = []
    for weekday, name in enumerate(_WEEKDAY_NAMES):
        if weekday <= 4:
            lunch_key, dinner_key = WEEKDAY_PLATE[weekday]
            lunch = recipe_by_id(week[lunch_key]).name
            dinner = recipe_by_id(week[dinner_key]).name
        elif weekday == 5:
            lunch = recipe_by_id(week["sat_lunch"]).name
            dinner = recipe_by_id(week["sat_dinner"]).name
        else:
            lunch = recipe_by_id(week["sun_lunch"]).name
            dinner = recipe_by_id(week["sun_dinner"]).name
        days.append({
            "weekday": name,
            "breakfast": breakfast_for(cycle_week, weekday).name,
            "lunch": lunch,
            "dinner": dinner,
        })
    return {
        "pots": [_card(week["pot_a"], ledger[week["pot_a"]]), _card(week["pot_b"], ledger[week["pot_b"]])],
        "soups": [_card(week["soup"], ledger[week["soup"]])],
        "days": days,
    }


def week_menu(cycle_week: int) -> dict:
    plan = cook_plan(cycle_week)
    return {
        "week": cycle_week + 1,
        "breakfasts": [day["breakfast"] for day in plan["days"]],
        "soup": plan["soups"][0]["name"],
        "pot_a": plan["pots"][0]["name"],
        "pot_b": plan["pots"][1]["name"],
        "saturday": f"{plan['days'][5]['lunch']} / {plan['days'][5]['dinner']}",
        "sunday": f"{plan['days'][6]['lunch']} / {plan['days'][6]['dinner']}",
        "days": plan["days"],
    }


def eaten_protein_counts(cycle_week: int) -> dict[str, int]:
    """How many Mon–Sun plates use each protein family. Frozen spares are not eaten."""
    week = WEEKS[cycle_week % 4]
    counts: dict[str, int] = defaultdict(int)
    ledger = portion_ledger(cycle_week)
    for info in ledger.values():
        recipe = recipe_by_id(info["id"])
        counts[recipe.protein] += info["eaten"]
    for key in ("sat_lunch", "sat_dinner", "sun_lunch", "sun_dinner"):
        counts[recipe_by_id(week[key]).protein] += 1
    return dict(counts)


_DEFAULT_DAY = {"kcal": 2200, "protein_low": 166, "protein_high": 184, "kind": "easy", "dur_min": 0}


def default_week_targets() -> list[dict]:
    """Stand-in week when the page has no measured TDEE: Tue hard, Sun long."""
    days = [dict(_DEFAULT_DAY) for _ in range(7)]
    days[1] = {**_DEFAULT_DAY, "kind": "hard", "dur_min": 40}
    days[6] = {**_DEFAULT_DAY, "kind": "long", "dur_min": 150}
    return days


def shopping_list(cycle_week: int, day_targets: list[dict] | None = None) -> list[dict]:
    """Aisle groups for one cycle week. Grams are what you buy, not a guess at brands."""
    targets = day_targets or default_week_targets()
    week = WEEKS[cycle_week % 4]
    grams: dict[str, float] = defaultdict(float)

    ledger = portion_ledger(cycle_week)
    for key in ("soup", "pot_a", "pot_b"):
        recipe = recipe_by_id(week[key])
        for food_id, amount in batch_grams_by_food(recipe).items():
            grams[food_id] += amount
        # Bread on the side is per eaten bowl, added from the planned plates below
        # only when the plate is not skipped. Add it here at the written weight
        # times bowls eaten, and do not add it again from the plate.
        _ = ledger

    for weekday in range(7):
        spec = targets[weekday]
        day = plan_day(
            cycle_week,
            weekday,
            target_kcal=spec["kcal"],
            protein_low=spec["protein_low"],
            protein_high=spec["protein_high"],
            kind=spec.get("kind") or "easy",
            dur_min=spec.get("dur_min") or 0,
        )
        for meal in day["meals"]:
            recipe_id = meal["recipe_id"]
            if recipe_id and recipe_id in BATCHES:
                recipe = BATCHES[recipe_id]
                for item in recipe.serve_with:
                    grams[item.food_id] += item.grams * meal["multiplier"]
                continue
            for food_id, amount in meal["grams_by_food"].items():
                grams[food_id] += amount

    grouped: dict[str, list[str]] = {aisle: [] for aisle in AISLE_ORDER}
    for food_id, amount in sorted(grams.items(), key=lambda pair: food(pair[0]).name):
        if amount < 1:
            continue
        row = food(food_id)
        grouped.setdefault(row.aisle, []).append(shop_line(food_id, amount))
    return [
        {"group": aisle, "items": items}
        for aisle, items in grouped.items()
        if items
    ]


# Re-exports used by the meal-library facade.
COOK_WEEKS = [
    {"pots": [week["pot_a"], week["pot_b"]], "soups": [week["soup"]]}
    for week in WEEKS
]
BREAKFAST_RECIPES = list(BREAKFASTS.values())
BATCH_RECIPES = list(BATCHES.values())
WEEKEND_RECIPES = list(WEEKEND.values())

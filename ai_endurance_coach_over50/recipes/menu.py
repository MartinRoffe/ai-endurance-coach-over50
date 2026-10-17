"""Four-week menu: the Sunday batch feeds weekday lunches and Mon–Thu dinners.

Friday dinner is a quick griddle plate. Saturday and Sunday are cooked fresh.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
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
from .model import numbered_method, portion_macros, shop_line
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
        return (
            recipe_by_id(week[lunch_key]),
            recipe_by_id(week[dinner_key]),
            lunch_key in COOKED_SERVINGS,
            dinner_key in COOKED_SERVINGS,
        )
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
    ref_date: date | None = None,
    ride: bool = True,
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
        ref_date=ref_date,
        ride=ride,
    )
    meals = build_meals(
        flex, breakfast, lunch, dinner, kind=kind, target_kcal=int(target_kcal),
    )
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


def _fmt_portions(value: float) -> str:
    rounded = round(float(value), 2)
    if abs(rounded - round(rounded)) < 0.001:
        return str(int(round(rounded)))
    text = f"{rounded:.2f}".rstrip("0").rstrip(".")
    return text


def _as_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _week_plans(cycle_week: int, day_targets: list[dict] | None) -> list[dict]:
    targets = day_targets or default_week_targets()
    plans = []
    for weekday, spec in enumerate(targets):
        plans.append(plan_day(
            cycle_week,
            weekday,
            target_kcal=int(spec["kcal"]),
            protein_low=int(spec["protein_low"]),
            protein_high=int(spec["protein_high"]),
            kind=spec.get("kind") or "easy",
            dur_min=int(spec.get("dur_min") or 0),
            ref_date=_as_date(spec.get("date")),
        ))
    return plans


def portion_ledger(cycle_week: int, day_targets: list[dict] | None = None) -> dict[str, dict]:
    """Monday–Friday batch portions, summed from the plates actually eaten.

    ``cooked`` is the sum of portion multipliers (a 1.25 plate counts as 1.25).
    ``eaten`` is still the number of plates, which is what the chicken and fish
    limits use. Nothing is frozen: the pot is cooked to that sum.
    """
    week = WEEKS[cycle_week % 4]
    plans = _week_plans(cycle_week, day_targets)
    out: dict[str, dict] = {}
    for key in COOKED_SERVINGS:
        recipe = recipe_by_id(week[key])
        portion_sum = 0.0
        side_sum = 0.0
        plates = 0
        grams: dict[str, float] = defaultdict(float)
        for weekday in range(5):
            lunch_key, dinner_key = WEEKDAY_PLATE[weekday]
            for meal in plans[weekday]["meals"]:
                if meal.get("recipe_id") != recipe.id:
                    continue
                slot_key = lunch_key if meal["slot"] == "Lunch" else dinner_key
                if meal["slot"] not in ("Lunch", "Dinner") or slot_key != key:
                    continue
                portion_sum += float(meal["multiplier"])
                side_sum += float(meal.get("side_multiplier") or 0.0)
                plates += 1
                for food_id, amount in meal["grams_by_food"].items():
                    grams[food_id] += amount
        out[recipe.id] = {
            "id": recipe.id,
            "name": recipe.name,
            "key": key,
            "cooked": portion_sum,
            "portion_sum": portion_sum,
            "side_sum": side_sum,
            "eaten": plates,
            "frozen": 0,
            "servings_on_recipe": recipe.servings,
            "grams": dict(grams),
        }
    return out


def _freezer_line(recipe_id: str, info: dict) -> str:
    recipe = recipe_by_id(recipe_id)
    base = recipe.servings
    factor = (info["portion_sum"] / base) if base else 1.0
    side_factor = (info["side_sum"] / base) if base else 1.0
    side_note = ""
    if abs(info["side_sum"] - info["portion_sum"]) > 0.05:
        side_note = (
            f" Weigh the rice, pasta, potato, or bread at {_fmt_portions(info['side_sum'])} portions "
            f"(×{_fmt_portions(side_factor)} the method)."
        )
    return (
        f"Cook {_fmt_portions(info['portion_sum'])} portions of the meat and vegetables "
        f"(×{_fmt_portions(factor)} the method, which is written for {base})."
        f"{side_note} "
        f"That is the {info['eaten']} Monday-to-Friday plates added up. Freeze nothing. "
        "The shop weights are this week's totals."
    )


def _card(recipe_id: str, info: dict) -> dict:
    recipe = recipe_by_id(recipe_id)
    macros = portion_macros(recipe, 1)
    shop = []
    for food_id, grams in sorted(info["grams"].items(), key=lambda pair: food(pair[0]).name):
        if grams < 1:
            continue
        shop.append(shop_line(food_id, grams))
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
        "servings": _fmt_portions(info["cooked"]),
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


def cook_plan(cycle_week: int, day_targets: list[dict] | None = None) -> dict:
    """Two one-pots and one soup for this cycle week, plus how the week eats them."""
    week = WEEKS[cycle_week % 4]
    ledger = portion_ledger(cycle_week, day_targets)
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
    """How many Mon–Sun plates use each protein family. The batch is what gets eaten."""
    week = WEEKS[cycle_week % 4]
    counts: dict[str, int] = defaultdict(int)
    ledger = portion_ledger(cycle_week)
    for info in ledger.values():
        recipe = recipe_by_id(info["id"])
        counts[recipe.protein] += info["eaten"]
    for key in ("fri_dinner", "sat_lunch", "sat_dinner", "sun_lunch", "sun_dinner"):
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
    """Aisle groups for one cycle week. Grams are the portions actually eaten."""
    grams: dict[str, float] = defaultdict(float)
    for day in _week_plans(cycle_week, day_targets):
        for meal in day["meals"]:
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

"""One nutrition page: today's plates, the week, the batch, and the shop.

The page and the daily email both print ``meal_share_line`` so the names,
portions, and calories cannot drift apart.
"""
from __future__ import annotations

from datetime import date, timedelta

from .nutrition_plan import (
    SUPPLEMENTS,
    _SUPPLEMENT_DISCLAIMER,
    build_today_food,
    prep_cycle_week_index,
    prep_week_day_targets,
    today_card,
)
from .recipes.catalog import all_recipes, recipe_by_id
from .recipes.menu import cook_plan, shopping_list
from .recipes.model import batch_grams_by_food, portion_grams_by_food, portion_macros
from .recipes.nutrition_table import food

RIDE_SLOTS = ("Pre-ride", "On-bike", "Post-ride")
_PLATE_SLOTS = ("Breakfast", "Lunch", "Dinner")


def _times(value: float) -> str:
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return f"{text}×"


def portion_label(meal: dict) -> str:
    """Plate multiplier shared by the page and the email. Empty for a fixed snack."""
    if not meal.get("recipe_id") or meal.get("multiplier") is None:
        return ""
    mult = float(meal["multiplier"])
    label = _times(mult)
    side = meal.get("side_multiplier")
    if side is not None and abs(float(side) - mult) >= 0.03:
        label += f" · side {_times(float(side))}"
    return label


def _kcal(meal: dict) -> int:
    macros = meal.get("macros")
    if isinstance(macros, dict):
        return int(macros["kcal"])
    return int(meal["kcal"])


def _macro(meal: dict, key: str, alt: str) -> int:
    macros = meal.get("macros")
    if isinstance(macros, dict):
        return int(macros[key])
    return int(meal[alt])


def meal_share_line(meal: dict) -> str:
    """One line: slot, name, portion, kcal. The page and the email both print this."""
    slot = meal.get("type") or meal.get("slot") or ""
    name = meal.get("name") or ""
    portion = portion_label(meal)
    portion_bit = f" {portion}" if portion else ""
    return f"{slot} · {name}{portion_bit} · {_kcal(meal)} kcal"


def ingredient_lines(grams_by_food: dict | None) -> list[str]:
    lines = []
    for food_id, grams in sorted((grams_by_food or {}).items(), key=lambda pair: food(pair[0]).name):
        if grams < 0.5:
            continue
        row = food(food_id)
        unit = "ml" if row.liquid else "g"
        lines.append(f"{row.name} — {int(round(grams))} {unit}")
    return lines


def present_meal(meal: dict) -> dict:
    recipe_id = meal.get("recipe_id")
    steps: list[str] = []
    if recipe_id:
        steps = list(recipe_by_id(recipe_id).method)
    elif meal.get("detail"):
        steps = [meal["detail"]]
    if meal.get("display_ingredients") is not None:
        ingredients = list(meal["display_ingredients"])
    else:
        ingredients = ingredient_lines(meal.get("grams_by_food"))
    slot = meal.get("type") or meal.get("slot") or ""
    return {
        "slot": slot,
        "name": meal.get("name") or "",
        "portion": portion_label(meal),
        "kcal": _kcal(meal),
        "protein": _macro(meal, "p", "protein"),
        "carbs": _macro(meal, "c", "carbs"),
        "share": meal_share_line(meal),
        "ingredients": ingredients,
        "steps": steps,
        "recipe_url": f"/nutrition/recipes#{recipe_id}" if recipe_id else None,
        "ride": slot in RIDE_SLOTS,
    }


def _week_monday(today: date) -> date:
    if today.weekday() >= 4:
        return today + timedelta(days=(7 - today.weekday()))
    return today - timedelta(days=today.weekday())


def nutrition_page(
    plan_start: date,
    today: date,
    *,
    logged_kcal: int | None = None,
    logged_protein: int | None = None,
    logged_carbs: int | None = None,
    tdee_today: int | None = None,
    ride_work_kj: int | None = None,
    ea_words: str | None = None,
    cut_line: dict | None = None,
) -> dict:
    """Everything /nutrition renders for one date."""
    card = today_card(today)
    food = build_today_food(plan_start, today)
    meals = [present_meal(meal) for meal in (food.get("meals") or [])]
    monday = today - timedelta(days=today.weekday())
    days = []
    for offset in range(7):
        day = monday + timedelta(days=offset)
        day_food = food if day == today else build_today_food(plan_start, day)
        day_meals = [present_meal(meal) for meal in (day_food.get("meals") or [])]
        days.append({
            "name": day.strftime("%a %-d %b"),
            "iso": day.isoformat(),
            "is_today": day == today,
            "session": day_food.get("session"),
            "kcal": day_food.get("kcal_target"),
            "meals": day_meals,
            "plates": [meal for meal in day_meals if meal["slot"] in _PLATE_SLOTS],
            "camp": bool(day_food.get("camp_mode")),
        })

    prep_week = prep_cycle_week_index(plan_start, today)
    targets = prep_week_day_targets(plan_start, today)
    plan = cook_plan(prep_week, targets)
    shop_monday = _week_monday(today)
    batches = list(plan["pots"]) + list(plan["soups"])
    return {
        "today": today.isoformat(),
        "day_name": food.get("day_name") or today.strftime("%A %-d %B"),
        "session": food.get("session"),
        "camp_mode": bool(food.get("camp_mode")),
        "camp": food.get("camp"),
        "checklist": food.get("checklist") or [],
        "card": card,
        "cut_line": cut_line,
        "meals": meals,
        "plates": [meal for meal in meals if not meal["ride"]],
        "ride": [meal for meal in meals if meal["ride"]],
        "meals_kcal_total": food.get("meals_kcal_total"),
        "meals_protein_total": food.get("meals_protein_total"),
        "dairy_calcium_mg": food.get("dairy_calcium_mg"),
        "logged_kcal": logged_kcal,
        "logged_protein": logged_protein,
        "logged_carbs": logged_carbs,
        "week_label": f"Week of {monday.strftime('%-d %b')}",
        "days": days,
        "shop_label": f"Week of {shop_monday.strftime('%-d %b')}",
        "shop_ahead": today.weekday() >= 4,
        "batches": batches,
        "groups": shopping_list(prep_week, targets),
        "tdee_today": tdee_today,
        "ride_work_kj": ride_work_kj,
        "ea_words": ea_words,
        "supplements": [{"name": name, "dose": dose, "why": why} for name, dose, why in SUPPLEMENTS],
        "supplement_disclaimer": _SUPPLEMENT_DISCLAIMER,
    }


def fuelling_guide(plan_start: date, today: date) -> dict:
    """Current ride-fuel guide: banana, homemade rice cakes, maltodextrin, milk."""
    from .nutrition_plan import fuel_prep_for_ride

    food = build_today_food(plan_start, today)
    meals = [present_meal(meal) for meal in (food.get("meals") or [])]
    savoury = portion_macros(recipe_by_id("standard-rice-cake"), 1)
    sweet = portion_macros(recipe_by_id("sweet-rice-cakes"), 1)
    return {
        "today": today.isoformat(),
        "kind": today_card(today)["kind"],
        "ride": [meal for meal in meals if meal["ride"]],
        "savoury_carbs": round(savoury["carbs"]),
        "sweet_carbs": round(sweet["carbs"]),
        "tiers": [
            fuel_prep_for_ride(minutes, ref_date=today)
            for minutes in (75, 90, 120, 150, 180, 240, 300)
        ],
    }


def recipe_groups() -> list[dict]:
    """Every library recipe, with the written method.

    Plates show one portion. Ride-fuel cakes show the whole batch in grams and
    the macros for one cake.
    """
    order = (
        ("Breakfast", "breakfast"),
        ("Sunday batch", "batch"),
        ("Weekend plates", "weekend"),
        ("Ride fuel", "ride"),
    )
    buckets: dict[str, list[dict]] = {key: [] for _label, key in order}
    for recipe in all_recipes():
        if recipe.slot == "ride":
            key = "ride"
        elif recipe.slot == "breakfast":
            key = "breakfast"
        elif recipe.batch:
            key = "batch"
        else:
            key = "weekend"
        macros = portion_macros(recipe, 1)
        if key == "ride":
            ingredients = ingredient_lines(batch_grams_by_food(recipe))
            servings_note = (
                f"Ingredients are the whole batch, about {recipe.servings} cakes. "
                "The figures beside the name are one cake."
            )
            macro_note = "per cake"
            fat = int(round(macros["fat"]))
        else:
            ingredients = ingredient_lines(portion_grams_by_food(recipe, 1))
            servings_note = (
                f"Ingredients are one portion. The method is written for {recipe.servings}."
                if recipe.servings != 1
                else "Ingredients and method are one portion."
            )
            macro_note = ""
            fat = None
        buckets[key].append({
            "id": recipe.id,
            "name": recipe.name,
            "summary": recipe.summary,
            "servings_note": servings_note,
            "macro_note": macro_note,
            "kcal": int(round(macros["kcal"])),
            "protein": int(round(macros["protein"])),
            "carbs": int(round(macros["carbs"])),
            "fat": fat,
            "ingredients": ingredients,
            "steps": list(recipe.method),
            "equipment": list(recipe.equipment),
            "fridge": recipe.fridge,
        })
    return [{"label": label, "recipes": buckets[key]} for label, key in order if buckets[key]]

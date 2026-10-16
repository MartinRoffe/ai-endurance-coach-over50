"""Guards for the computed recipe library and the day scaler."""
from __future__ import annotations

import re
from datetime import date

import pytest

from ai_endurance_coach_over50.nutrition_plan import build_today_food, today_targets
from ai_endurance_coach_over50.plan import PLAN_START
from ai_endurance_coach_over50.recipes.catalog import all_recipes
from ai_endurance_coach_over50.recipes.menu import eaten_protein_counts, portion_ledger
from ai_endurance_coach_over50.recipes.model import portion_macros

_BANNED = re.compile(
    r"\b("
    r"cheese|parmesan|cheddar|feta|halloumi|mozzarella|"
    r"chilli|chili|cayenne|harissa|jalapeno|jalapeño|chorizo|sriracha|spicy|"
    r"offal|liver|kidneys?|spinach|chia|almonds?|cashews?|walnuts?|"
    r"peanuts?|peanut butter|beetroot|rhubarb"
    r")\b",
    re.IGNORECASE,
)
_CARB_IN_POT = {"rice", "pasta", "couscous", "potato"}


def _ingredient_text(recipe) -> str:
    parts = [recipe.name, recipe.protein]
    for item in tuple(recipe.ingredients) + tuple(recipe.serve_with):
        parts.append(item.food_id.replace("_", " "))
    return " ".join(parts)


def _method_hits(recipe) -> list[str]:
    hits = []
    for step in recipe.method:
        # "No cheese" is an instruction, not an ingredient.
        cleaned = re.sub(r"\bno\s+cheese\b", "", step, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bwithout\s+cheese\b", "", cleaned, flags=re.IGNORECASE)
        found = _BANNED.findall(cleaned)
        if found:
            hits.append(f"{recipe.id}: {found} in {step}")
    return hits


def test_banned_ingredients_absent():
    problems = []
    for recipe in all_recipes():
        blob = _ingredient_text(recipe)
        found = _BANNED.findall(blob)
        if found:
            problems.append(f"{recipe.id} ingredients: {found}")
        problems.extend(_method_hits(recipe))
    assert problems == []


def test_every_recipe_has_method_and_grams():
    for recipe in all_recipes():
        assert recipe.method, recipe.id
        assert recipe.equipment, recipe.id
        assert recipe.servings >= 1
        assert recipe.ingredients, recipe.id
        for item in recipe.ingredients:
            assert item.grams > 0, recipe.id
        macros = portion_macros(recipe, 1)
        assert macros["grams"] > 0
        assert macros["kcal"] > 0


def test_batch_portions_match_the_week():
    for week in range(4):
        ledger = portion_ledger(week)
        assert len(ledger) == 3
        for info in ledger.values():
            assert info["cooked"] >= 4, info
            assert info["cooked"] == info["servings_on_recipe"]
            assert info["eaten"] + info["frozen"] == info["cooked"]
            assert info["frozen"] >= 0


def test_chicken_and_fish_counts():
    for week in range(4):
        counts = eaten_protein_counts(week)
        assert counts.get("chicken", 0) <= 2, counts
        assert 1 <= counts.get("fish", 0) <= 2, counts


def test_no_yoghurt_on_batch_dinners_and_no_extra_carb_side():
    for recipe in all_recipes():
        if not recipe.batch:
            continue
        ids = {item.food_id for item in recipe.ingredients}
        assert "yoghurt_hp" not in ids
        if ids & _CARB_IN_POT:
            assert recipe.serve_with == (), recipe.id


def _assert_on_target(day: date):
    food = build_today_food(PLAN_START, day)
    target = today_targets(day)
    assert food["camp_mode"] is False
    total = food["meals_kcal_total"]
    assert abs(total - target["kcal"]) <= target["kcal"] * 0.05 + 0.01
    assert target["protein_low"] <= food["meals_protein_total"] <= target["protein_high"]
    assert food["dairy_calcium_mg"] >= 1000
    slots = [meal["type"] for meal in food["meals"]]
    assert "Breakfast" in slots and "Lunch" in slots and "Dinner" in slots
    for meal in food["meals"]:
        assert int(meal["macros"]["kcal"]) > 0
        assert meal["name"]


def test_saturday_17_oct_2026_and_cut_week(monkeypatch):
    monkeypatch.setattr(
        "ai_endurance_coach_over50.nutrition_plan._stable_tdee",
        lambda days=7: None,
    )
    _assert_on_target(date(2026, 10, 17))
    _assert_on_target(date(2027, 1, 4))

    monkeypatch.setattr(
        "ai_endurance_coach_over50.nutrition_plan._stable_tdee",
        lambda days=7: 2000,
    )
    # Easy cut day lands on the 1,600 kcal floor. Friday is two portions of pot A.
    _assert_on_target(date(2027, 1, 4))
    _assert_on_target(date(2027, 1, 8))
    # Hard and long use the real session on those dates when one exists,
    # and a forced session when the plan day is quiet.
    from ai_endurance_coach_over50 import plan as plan_mod

    monkeypatch.setattr(
        plan_mod, "session_for_date_extended", lambda d: ("threshold", "Threshold", 50)
    )
    _assert_on_target(date(2027, 1, 5))
    monkeypatch.setattr(
        plan_mod, "session_for_date_extended", lambda d: ("long", "Long ride", 180)
    )
    _assert_on_target(date(2027, 1, 10))


@pytest.mark.parametrize("kind_date", [date(2026, 10, 17), date(2027, 1, 6)])
def test_published_meals_are_not_formula_forties(kind_date):
    food = build_today_food(PLAN_START, kind_date)
    proteins = [int(meal["macros"]["p"]) for meal in food["meals"]]
    assert proteins != [40, 40, 40, 40]

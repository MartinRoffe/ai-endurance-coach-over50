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
    """Cooked grams follow the sum of portion multipliers, not a fixed tub count."""
    from ai_endurance_coach_over50.recipes.menu import default_week_targets, shopping_list

    for week in range(4):
        targets = default_week_targets()
        ledger = portion_ledger(week, targets)
        assert len(ledger) == 3
        for info in ledger.values():
            assert info["eaten"] >= 1, info
            assert info["frozen"] == 0
            assert info["cooked"] == info["portion_sum"]
            assert info["cooked"] > 0
        groups = shopping_list(week, targets)
        listed = " ".join(item for group in groups for item in group["items"])
        # Courgette is only in turkey, rice and peppers. Week index 1 cooks that pot.
        if week == 1:
            turkey = next(info for info in ledger.values() if info["id"] == "turkey-rice-peppers")
            courgette = int(round(turkey["grams"]["courgette"]))
            assert f"Courgettes — {courgette} g" in listed


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


_BREAKFAST_MULTIPLIERS = {0.75, 1.0, 1.25}
_PLATE_MULTIPLIERS = {0.75, 1.0, 1.25, 1.5}


def _assert_portion_caps(food: dict, *, easy: bool):
    breakfast = next(meal for meal in food["meals"] if meal["type"] == "Breakfast")
    assert breakfast["multiplier"] in _BREAKFAST_MULTIPLIERS
    evening = 0.0
    for meal in food["meals"]:
        if meal["type"] == "Evening":
            evening += float(meal["grams_by_food"].get("yoghurt_hp", 0))
        if meal["type"] in ("Lunch", "Dinner") and meal.get("multiplier") is not None:
            assert meal["multiplier"] in _PLATE_MULTIPLIERS
    assert evening <= 250.0 + 0.01
    snacks = [meal for meal in food["meals"] if meal["type"] == "Snack"]
    assert len(snacks) <= 1
    for snack in snacks:
        assert int(snack["macros"]["kcal"]) <= 250
    if easy:
        # Rest and easy days do not carry a ride snack on top of that one item.
        assert "Pre-ride" not in [meal["type"] for meal in food["meals"]]
        assert "Post-ride" not in [meal["type"] for meal in food["meals"]]


def _assert_on_target(day: date, *, easy: bool | None = None):
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
    from ai_endurance_coach_over50.energy import day_kind
    if easy is None:
        easy = day_kind(target.get("calorie_tier")) == "easy"
    _assert_portion_caps(food, easy=easy)


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


def test_explicit_1965_kcal_target(monkeypatch):
    """Martin's easy-day maintenance is about 1,965 kcal, not the 2,200 fallback."""
    monkeypatch.setattr(
        "ai_endurance_coach_over50.nutrition_plan._stable_tdee",
        lambda days=7: 1965,
    )
    day = date(2026, 10, 17)
    target = today_targets(day)
    assert target["kcal"] == 1965
    _assert_on_target(day, easy=True)
    food = build_today_food(PLAN_START, day)
    breakfast = next(meal for meal in food["meals"] if meal["type"] == "Breakfast")
    assert breakfast["multiplier"] == 1.0 or breakfast["multiplier"] in _BREAKFAST_MULTIPLIERS
    snacks = [meal for meal in food["meals"] if meal["type"] == "Snack"]
    assert len(snacks) <= 1
    if snacks:
        assert int(snacks[0]["macros"]["kcal"]) <= 250

    from ai_endurance_coach_over50.recipes.menu import plan_day
    planned = plan_day(
        1, 5,
        target_kcal=1965,
        protein_low=166,
        protein_high=184,
        kind="easy",
        ref_date=day,
    )
    assert abs(planned["totals"]["kcal"] - 1965) <= 1965 * 0.05
    assert 166 <= planned["totals"]["protein"] <= 184


def test_cut_week_easy_hard_and_long_inside_1600_to_2000(monkeypatch):
    monkeypatch.setattr(
        "ai_endurance_coach_over50.nutrition_plan._stable_tdee",
        lambda days=7: 2000,
    )
    from ai_endurance_coach_over50 import plan as plan_mod

    monkeypatch.setattr(
        plan_mod, "session_for_date_extended", lambda d: ("rest", "Rest", 0),
    )
    easy = today_targets(date(2027, 1, 4))
    assert easy["kcal"] == 1600
    _assert_on_target(date(2027, 1, 4), easy=True)

    monkeypatch.setattr(
        plan_mod, "session_for_date_extended", lambda d: ("threshold", "Threshold", 50),
    )
    hard = today_targets(date(2027, 1, 5))
    assert hard["kcal"] == 1750
    _assert_on_target(date(2027, 1, 5), easy=False)

    monkeypatch.setattr(
        plan_mod, "session_for_date_extended", lambda d: ("long", "Long ride", 120),
    )
    long_day = today_targets(date(2027, 1, 10))
    assert long_day["kcal"] == 2000
    _assert_on_target(date(2027, 1, 10), easy=False)


def test_unreachable_high_target_stays_under_and_says_so():
    """Past the portion caps, the day stays under the calorie target and says so."""
    from ai_endurance_coach_over50.recipes.menu import plan_day
    planned = plan_day(
        0, 0,
        target_kcal=4000,
        protein_low=166,
        protein_high=184,
        kind="easy",
    )
    dinner = next(meal for meal in planned["meals"] if meal["slot"] == "Dinner")
    assert planned["totals"]["kcal"] < 4000
    assert "under" in dinner["detail"]
    assert all(meal["multiplier"] <= 1.5 for meal in planned["meals"] if meal["slot"] in ("Lunch", "Dinner"))

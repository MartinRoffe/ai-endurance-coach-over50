"""One-pot and soup rotation."""
from __future__ import annotations

import json

from ai_endurance_coach_over50.energy import CUT_DEFICIT_BY_PHASE
from ai_endurance_coach_over50.meal_library import (
    ONE_POTS,
    SOUPS,
    banned_foods_in_library,
)
from ai_endurance_coach_over50.recipes.menu import COOK_WEEKS, eaten_protein_counts
from ai_endurance_coach_over50.nutrition_plan import (
    EVENING_DINNERS,
    SIMPLE_RULES,
    WEEKDAY_DINNERS,
    _assemble_meals,
    build_meal_week,
    meal_cycle_full,
    today_day_type,
    weekday_dinner,
)


def test_library_size_and_stone_foods():
    assert len(ONE_POTS) == 8
    assert len(SOUPS) == 4
    assert banned_foods_in_library() == []
    assert "cheese" not in meal_cycle_full().lower()


def test_chicken_stays_in_rotation_but_not_every_day():
    assert any(p["protein"] == "chicken" for p in ONE_POTS)
    seen = []
    for week in range(4):
        serves = eaten_protein_counts(week).get("chicken", 0)
        seen.append(serves)
        assert 0 <= serves <= 2
    assert any(serves >= 1 for serves in seen)
    for block in COOK_WEEKS:
        names = block["pots"] + block["soups"]
        chicken = [n for n in names if "chicken" in n]
        assert len(chicken) <= 1


def test_simple_rules_are_five_and_stews_are_allowed():
    assert len(SIMPLE_RULES) == 5
    assert "hard" not in CUT_DEFICIT_BY_PHASE
    blob = json.dumps([build_meal_week(i) for i in range(4)]).lower()
    assert "slow cooker" in blob or "slow-cooker" in blob
    assert "gousto" not in blob


def test_day_has_three_meals_and_computed_dinner_protein():
    meals = _assemble_meals(today_day_type(0, 0), 0, 0)
    slots = [m[0] for m in meals]
    assert slots[0] == "Breakfast"
    assert "Lunch" in slots and "Dinner" in slots
    assert "AM Snack" not in slots
    assert sum(m[4] for m in meals) >= 140
    dinner = weekday_dinner(0, 0)
    assert dinner is not None
    assert dinner[0] == "Dinner"
    assert dinner[4] >= 30


def test_evening_dinners_alias():
    assert WEEKDAY_DINNERS is EVENING_DINNERS
    assert EVENING_DINNERS[0][0][0]


def test_recovery_week_is_seven_days():
    week = build_meal_week(3)
    assert week["recovery"] is False
    assert len(week["days"]) == 7
    slots = [m["type"] for m in week["days"][0]["meals"]]
    assert slots[0] == "Breakfast"
    assert "Lunch" in slots and "Dinner" in slots

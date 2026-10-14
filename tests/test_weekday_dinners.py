"""One-pot and soup rotation."""
from __future__ import annotations

import json

from ai_endurance_coach_over50.energy import CUT_DEFICIT_BY_PHASE
from ai_endurance_coach_over50.meal_library import (
    COOK_WEEKS,
    EAT_ROTATION,
    ONE_POTS,
    SOUPS,
    banned_foods_in_library,
    chicken_serves,
)
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
    assert len(SOUPS) == 6
    assert banned_foods_in_library() == []
    assert "cheese" not in meal_cycle_full().lower()


def test_chicken_stays_in_rotation_but_not_every_day():
    assert any(p["protein"] == "chicken" for p in ONE_POTS)
    for start in range(len(EAT_ROTATION)):
        indexes = [(start + i) % len(EAT_ROTATION) for i in range(7)]
        serves = chicken_serves(indexes)
        assert 0 <= serves <= 2
    assert any(chicken_serves([(start + i) % len(EAT_ROTATION) for i in range(7)]) >= 1
               for start in range(len(EAT_ROTATION)))
    for block in COOK_WEEKS:
        names = block["pots"] + block["soups"]
        chicken = [n for n in names if n.startswith("chicken")]
        assert len(chicken) <= 1


def test_simple_rules_are_five_and_stews_are_allowed():
    assert len(SIMPLE_RULES) == 5
    assert "hard" not in CUT_DEFICIT_BY_PHASE
    blob = json.dumps([build_meal_week(i) for i in range(4)]).lower()
    assert "stew" in blob
    assert "gousto" not in blob


def test_four_doses_and_dinner_protein():
    meals = _assemble_meals(today_day_type(0, 0), 0, 0)
    assert [m[0] for m in meals] == ["Breakfast", "Lunch", "Dinner", "Evening"]
    assert sum(m[4] for m in meals) == 160
    dinner = weekday_dinner(0, 0)
    assert dinner is not None
    assert dinner[0] == "Dinner"
    assert dinner[4] == 40


def test_evening_dinners_alias():
    assert WEEKDAY_DINNERS is EVENING_DINNERS
    assert EVENING_DINNERS[0][0][0]


def test_recovery_week_is_seven_days():
    week = build_meal_week(3)
    assert week["recovery"] is False
    assert len(week["days"]) == 7
    assert [m["type"] for m in week["days"][0]["meals"]] == [
        "Breakfast", "Lunch", "Dinner", "Evening",
    ]

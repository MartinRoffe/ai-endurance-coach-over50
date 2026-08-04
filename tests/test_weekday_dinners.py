"""Evening Mon–Sun plates — Gousto-style component prep."""
from __future__ import annotations

import json

import pytest

from ai_endurance_coach_over50.nutrition_plan import (
    EVENING_DINNERS,
    PRINCIPLES,
    SIMPLE_RULES,
    WEEKDAY_DINNERS,
    _assemble_meals,
    build_meal_week,
    meal_cycle_full,
    today_day_type,
    weekday_dinner,
)


@pytest.mark.parametrize("cycle_week", range(4))
@pytest.mark.parametrize("weekday", range(7))
def test_evening_dinner_slot_and_protein(cycle_week: int, weekday: int):
    dtype = today_day_type(cycle_week, weekday)
    meals = _assemble_meals(dtype, cycle_week, weekday)
    assert meals[-1][0] == "Dinner"
    assert meals[-1][4] >= 60
    assert "griddle" not in meals[-1][1].lower()


@pytest.mark.parametrize("cycle_week", range(4))
def test_nights_are_unique_within_week(cycle_week: int):
    names = [weekday_dinner(cycle_week, wd)[1] for wd in range(7)]
    assert len(names) == len(set(names))
    # No consecutive duplicates either
    for a, b in zip(names, names[1:]):
        assert a != b


@pytest.mark.parametrize("cycle_week", range(3))
@pytest.mark.parametrize("weekday", range(5))
def test_build_week_dinner_kcal_mon_fri(cycle_week: int, weekday: int):
    dinner = weekday_dinner(cycle_week, weekday)
    assert dinner is not None
    assert 600 <= dinner[3] <= 650


@pytest.mark.parametrize("cycle_week", range(3))
def test_build_weekend_carb_bias(cycle_week: int):
    sat = weekday_dinner(cycle_week, 5)
    sun = weekday_dinner(cycle_week, 6)
    assert sat is not None and sun is not None
    assert sat[5] >= sun[5]  # carbs
    assert sat[3] >= 580
    assert sun[3] <= 540


@pytest.mark.parametrize("weekday", range(5))
def test_recovery_week_dinner_kcal(weekday: int):
    dinner = weekday_dinner(3, weekday)
    assert dinner is not None
    assert dinner[3] <= 580


def test_friday_is_evening_plate_not_griddle():
    fri_build = _assemble_meals("bike_fri", 0, 4)
    assert fri_build[-1][0] == "Dinner"
    assert "griddle" not in fri_build[-1][1].lower()
    assert weekday_dinner(0, 4) is not None

    fri_rec = _assemble_meals("recovery_weekday", 3, 4)
    assert fri_rec[-1][0] == "Dinner"
    assert "griddle" not in fri_rec[-1][1].lower()


def test_no_gousto_stew_or_griddle_in_plan_surfaces():
    blob = "\n".join(SIMPLE_RULES + PRINCIPLES) + "\n" + meal_cycle_full()
    blob += "\n" + json.dumps([build_meal_week(i) for i in range(4)])
    low = blob.lower()
    assert "gousto" not in low
    assert "ragù" not in low and "ragu" not in low
    assert "cottage pie" not in low
    assert "casserole" not in low
    assert "blackstone griddle" not in low


def test_evening_dinners_alias():
    assert WEEKDAY_DINNERS is EVENING_DINNERS
    assert EVENING_DINNERS[1][3][0].lower().startswith("mediterranean turkey")


def test_recovery_collapsed_card_lists_plates():
    week = build_meal_week(3)
    assert week["recovery"] is True
    mon_fri = week["days"][0]
    dinner = next(m for m in mon_fri["meals"] if m["type"] == "Dinner")
    name = dinner["name"].lower()
    assert "mon–fri" in name or "mon-fri" in name or "plates" in name
    assert "griddle" not in name
    assert "cottage pie" not in name

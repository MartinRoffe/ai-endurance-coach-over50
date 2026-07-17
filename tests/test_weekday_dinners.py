"""Sunday batch weekday dinners — replace Gousto Mon–Thu slots."""
from __future__ import annotations

import json

import pytest

from ai_endurance_coach_over50.nutrition_plan import (
    PRINCIPLES,
    SIMPLE_RULES,
    WEEKDAY_DINNERS,
    _assemble_meals,
    build_meal_week,
    meal_cycle_full,
    today_day_type,
    weekday_dinner,
)

_BUILD_DINNER_TYPES = ("rest", "training", "bike", "thursday")


@pytest.mark.parametrize("cycle_week", range(4))
@pytest.mark.parametrize("weekday", range(4))
def test_weekday_dinner_slot_and_protein(cycle_week: int, weekday: int):
    dtype = today_day_type(cycle_week, weekday)
    assert dtype in _WEEKDAY_DINNER_TYPES_OR_RECOVERY(cycle_week, weekday)
    meals = _assemble_meals(dtype, cycle_week, weekday)
    assert meals[-1][0] == "Dinner"
    assert meals[-1][4] >= 58


def _WEEKDAY_DINNER_TYPES_OR_RECOVERY(cycle_week: int, weekday: int) -> frozenset:
    if cycle_week == 3:
        return frozenset({"recovery_weekday"})
    return frozenset(_BUILD_DINNER_TYPES)


@pytest.mark.parametrize("cycle_week", range(4))
def test_mon_tue_share_batch_a_wed_differs(cycle_week: int):
    mon = weekday_dinner(cycle_week, 0)
    tue = weekday_dinner(cycle_week, 1)
    wed = weekday_dinner(cycle_week, 2)
    assert mon is not None and tue is not None and wed is not None
    assert mon[1] == tue[1]
    assert wed[1] != mon[1]
    assert mon[1] == WEEKDAY_DINNERS[cycle_week]["A"][0]
    assert wed[1] == WEEKDAY_DINNERS[cycle_week]["B"][0]


@pytest.mark.parametrize("cycle_week", range(3))
@pytest.mark.parametrize("weekday", range(4))
def test_build_week_dinner_kcal(cycle_week: int, weekday: int):
    # Build-week dinners are sized to the stable-TDEE targets (~620 kcal)
    # and stay heavier than the ~560 kcal recovery-week batches.
    dinner = weekday_dinner(cycle_week, weekday)
    assert dinner is not None
    assert 600 <= dinner[3] <= 650


@pytest.mark.parametrize("weekday", range(4))
def test_recovery_week_dinner_kcal(weekday: int):
    dinner = weekday_dinner(3, weekday)
    assert dinner is not None
    assert dinner[3] <= 600


def test_friday_keeps_griddle():
    fri_build = _assemble_meals("bike_fri", 0, 4)
    assert fri_build[-1][0] == "Dinner"
    assert "griddle" in fri_build[-1][1].lower()
    assert weekday_dinner(0, 4) is None

    fri_rec = _assemble_meals("recovery_weekday", 3, 4)
    assert fri_rec[-1][0] == "Dinner"
    assert "griddle" in fri_rec[-1][1].lower()


def test_no_gousto_in_plan_surfaces():
    blob = "\n".join(SIMPLE_RULES + PRINCIPLES) + "\n" + meal_cycle_full()
    blob += "\n" + json.dumps([build_meal_week(i) for i in range(4)])
    assert "gousto" not in blob.lower()


def test_w2_batch_b_is_beef_bolognese():
    name = WEEKDAY_DINNERS[1]["B"][0].lower()
    assert "beef" in name and "bolognese" in name
    assert "turkey" not in name


def test_recovery_collapsed_card_names_both_batches():
    week = build_meal_week(3)
    assert week["recovery"] is True
    mon_fri = week["days"][0]
    dinner = next(m for m in mon_fri["meals"] if m["type"] == "Dinner")
    name = dinner["name"].lower()
    assert "cottage pie" in name
    assert "casserole" in name
    assert "griddle" in name

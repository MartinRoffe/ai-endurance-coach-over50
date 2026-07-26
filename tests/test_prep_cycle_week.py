"""Sunday/Fri ahead-shopping uses next week's food cycle, not the week ending today."""
from datetime import date, timedelta

import pytest

from ai_endurance_coach_over50.nutrition_plan import (
    cycle_week_index,
    prep_cycle_week_index,
)
from ai_endurance_coach_over50.plan import PLAN_START


def test_sunday_prep_advances_to_next_monday_cycle():
    # Sun 19 Jul 2026 ends cycle week 1; Mon–Thu dinners are cycle week 2.
    sunday = date(2026, 7, 19)
    assert sunday.weekday() == 6
    assert cycle_week_index(PLAN_START, sunday) == 0
    assert prep_cycle_week_index(PLAN_START, sunday) == 1
    monday = sunday + timedelta(days=1)
    assert prep_cycle_week_index(PLAN_START, sunday) == cycle_week_index(
        PLAN_START, monday
    )


@pytest.mark.parametrize(
    "d",
    [
        date(2026, 7, 17),  # Fri
        date(2026, 7, 18),  # Sat
        date(2026, 7, 19),  # Sun
    ],
)
def test_fri_sat_sun_prep_match_next_monday(d: date):
    next_mon = d + timedelta(days=(7 - d.weekday()))
    assert prep_cycle_week_index(PLAN_START, d) == cycle_week_index(
        PLAN_START, next_mon
    )


@pytest.mark.parametrize(
    "d",
    [
        date(2026, 7, 20),  # Mon
        date(2026, 7, 21),  # Tue
        date(2026, 7, 22),  # Wed
        date(2026, 7, 23),  # Thu
    ],
)
def test_mon_thu_prep_matches_today(d: date):
    assert prep_cycle_week_index(PLAN_START, d) == cycle_week_index(PLAN_START, d)

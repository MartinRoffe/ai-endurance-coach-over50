"""Daily Menus 'This week' badges track the training calendar."""
from __future__ import annotations

from datetime import date, timedelta

from ai_endurance_coach_over50.history import set_plan_override
from ai_endurance_coach_over50.nutrition_plan import (
    build_this_meal_week,
    nutrition_coach_context,
)
from ai_endurance_coach_over50.plan import PLAN_START, TRAINING_WEEKS, session_for_date


def test_this_week_badges_match_plan_week_8():
    """2026-07-10 falls in plan week 8 (deload) — badges must match TRAINING_WEEKS."""
    today = date(2026, 7, 10)
    week = build_this_meal_week(PLAN_START, today)
    assert len(week["days"]) == 7
    assert "plan week 8" in week["banner"]
    assert "deload" in week["banner"]

    monday = today - timedelta(days=today.weekday())
    for i, day in enumerate(week["days"]):
        d = monday + timedelta(days=i)
        stype, label, dur = session_for_date(d)
        expected = f"{label.strip()} · {dur} min" if dur > 0 else label.strip()
        assert day["type"] == expected, f"{d}: {day['type']!r} != {expected!r}"
        assert TRAINING_WEEKS[7][i][1].strip() in day["type"]


def test_this_week_honours_plan_override():
    today = date(2026, 7, 10)  # Friday of week 8
    set_plan_override(today.isoformat(), "bike", "Recovery Spin", 30, "test")
    week = build_this_meal_week(PLAN_START, today)
    fri = week["days"][4]
    assert fri["type"] == "Recovery Spin · 30 min"


def test_nutrition_coach_context_includes_plan_session():
    today = date(2026, 7, 10)
    text = nutrition_coach_context(PLAN_START, today)
    assert "Plan session: Easy Spin · 45 min" in text

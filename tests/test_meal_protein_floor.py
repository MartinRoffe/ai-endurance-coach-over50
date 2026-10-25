"""Each main meal aims for 35 g protein without leaving the day's calorie band."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from ai_endurance_coach_over50.recipes.catalog import recipe_by_id
from ai_endurance_coach_over50.server import app
from ai_endurance_coach_over50.recipes.fit import (
    build_meals,
    published_totals,
    recipes_under_protein_floor,
    solve,
)

_REF = date(2026, 11, 3)


def _day(breakfast, lunch, dinner, target, protein_low, protein_high):
    plan = solve(
        breakfast,
        lunch,
        dinner,
        target_kcal=target,
        protein_low=protein_low,
        protein_high=protein_high,
        kind="easy",
        dur_min=0,
        ref_date=_REF,
        ride=False,
    )
    meals = build_meals(
        plan, breakfast, lunch, dinner, kind="easy", target_kcal=target,
    )
    return meals, published_totals(meals)


def _in_band(total: int, target: int) -> bool:
    band = max(1, round(target * 0.05))
    return abs(total - target) <= band


@pytest.fixture
def client():
    return TestClient(app)


def test_porridge_page_says_it_cannot_reach_35g(client):
    html = client.get("/nutrition?date=2026-10-23").text
    assert "Porridge" in html
    assert "stays under 35 g protein at the largest portion" in html


def test_only_two_breakfasts_cannot_reach_35g():
    assert recipes_under_protein_floor() == ["porridge", "overnight-oats"]


def test_incapable_recipe_is_named_on_the_plate():
    meals, totals = _day(
        recipe_by_id("porridge"),
        recipe_by_id("lemon-chicken-rice"),
        recipe_by_id("turkey-tomato-roll"),
        1900,
        120,
        220,
    )
    breakfast = next(meal for meal in meals if meal["slot"] == "Breakfast")
    lunch = next(meal for meal in meals if meal["slot"] == "Lunch")
    assert breakfast["protein"] < 35
    assert "35 g" in breakfast["detail"]
    assert "largest portion" in breakfast["detail"]
    assert "largest portion" not in lunch["detail"]
    assert _in_band(totals["kcal"], 1900)


def test_meal_steps_up_to_35g_when_the_day_still_fits():
    target = 1600
    meals, totals = _day(
        recipe_by_id("scrambled-eggs"),
        recipe_by_id("mushroom-omelette-toast"),
        recipe_by_id("steak-mushroom-potato"),
        target,
        140,
        200,
    )
    assert _in_band(totals["kcal"], target)
    for slot in ("Breakfast", "Lunch", "Dinner"):
        meal = next(item for item in meals if item["slot"] == slot)
        assert meal["protein"] >= 35, slot


def test_calorie_band_wins_when_35g_does_not_fit():
    target = 1100
    meals, totals = _day(
        recipe_by_id("yoghurt-bowl"),
        recipe_by_id("lemon-chicken-rice"),
        recipe_by_id("turkey-tomato-roll"),
        target,
        80,
        250,
    )
    breakfast = next(meal for meal in meals if meal["slot"] == "Breakfast")
    assert _in_band(totals["kcal"], target)
    assert breakfast["protein"] < 35
    assert "largest portion" not in breakfast["detail"]

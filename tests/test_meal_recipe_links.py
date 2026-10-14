"""Today meal → recipe URL resolution and Methods linkify."""
from __future__ import annotations

from ai_endurance_coach_over50.nutrition_plan import (
    _linkify_meal_detail,
    meal_recipe_url,
)


def test_dinner_plate_anchor_w4_mon():
    url = meal_recipe_url("Dinner", "Lemon chicken and rice", cycle_week=3, weekday=0)
    assert url == "/nutrition/recipes/weekday-dinners#chicken-rice"


def test_dinner_plate_anchor_w1_sat():
    url = meal_recipe_url("Dinner", "Turkey and potato stew", cycle_week=0, weekday=5)
    assert url == "/nutrition/recipes/weekday-dinners#turkey-stew"


def test_overnight_oats_breakfast():
    url = meal_recipe_url("Breakfast", "Skyr, oats and fruit")
    assert url == "/nutrition/recipes/overnight-oats"


def test_scotch_egg_breakfast():
    url = meal_recipe_url("Breakfast", "Eggs and Greek yoghurt")
    assert url == "/nutrition/recipes#eggs"


def test_egg_muffin_breakfast():
    url = meal_recipe_url("Lunch", "Chicken and rice soup")
    assert url == "/nutrition/recipes/weekday-dinners#chicken-soup"


def test_chinese_lunch():
    url = meal_recipe_url("Lunch", "Turkey and cabbage soup")
    assert url == "/nutrition/recipes/weekday-dinners#turkey-soup"


def test_batch_rice_chicken_lunch():
    url = meal_recipe_url("Dinner", "Salmon, rice and peas")
    assert url == "/nutrition/recipes/weekday-dinners#salmon-rice"


def test_whey_shake_has_no_recipe():
    assert meal_recipe_url("Protein Shake", "Whey shake — 25g protein (home-mixed)") is None


def test_linkify_methods_rewrites_sunday_to_plate():
    plate = "/nutrition/recipes/weekday-dinners#w4-mon"
    detail = (
        "Serves 1. Methods: /nutrition/sunday. Recovery week — lighter carb side."
    )
    out = _linkify_meal_detail(detail, recipe_url=plate)
    assert f'href="{plate}"' in out
    assert "Methods:" in out
    assert "/nutrition/sunday" in out  # visible link text still shows the path token
    assert "<a href=" in out


def test_linkify_escapes_html():
    out = _linkify_meal_detail('Try <script>alert(1)</script> then /nutrition/recipes#rice')
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert 'href="/nutrition/recipes#rice"' in out

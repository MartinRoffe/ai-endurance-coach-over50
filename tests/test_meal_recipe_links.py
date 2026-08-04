"""Today meal → recipe URL resolution and Methods linkify."""
from __future__ import annotations

from ai_endurance_coach_over50.nutrition_plan import (
    _linkify_meal_detail,
    meal_recipe_url,
)


def test_dinner_plate_anchor_w4_mon():
    url = meal_recipe_url("Dinner", "BBQ chicken + small AF potatoes", cycle_week=3, weekday=0)
    assert url == "/nutrition/recipes/weekday-dinners#w4-mon"


def test_dinner_plate_anchor_w1_sat():
    url = meal_recipe_url("Dinner", "BBQ pork medallions", cycle_week=0, weekday=5)
    assert url == "/nutrition/recipes/weekday-dinners#w1-sat"


def test_overnight_oats_breakfast():
    url = meal_recipe_url("Breakfast", "High-Protein Overnight Oats")
    assert url == "/nutrition/recipes/overnight-oats"


def test_scotch_egg_breakfast():
    url = meal_recipe_url("Breakfast", "Scotch Egg + 200g Greek Yogurt")
    assert url == "/nutrition/recipes#scotch-eggs"


def test_egg_muffin_breakfast():
    url = meal_recipe_url("Breakfast", "Egg & Veg Muffins")
    assert url == "/nutrition/recipes#egg-muffins"


def test_chinese_lunch():
    url = meal_recipe_url("Lunch", "Chinese Chicken + Egg Fried Rice + Greek Yogurt")
    assert url == "/nutrition/recipes#chinese-lunch"


def test_batch_rice_chicken_lunch():
    url = meal_recipe_url("Lunch", "Batch Rice + Chicken 240g + Greek Yogurt")
    assert url == "/nutrition/recipes#chickenrice"


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

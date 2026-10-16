"""Today meal → recipe URL resolution and Methods linkify."""
from __future__ import annotations

from ai_endurance_coach_over50.nutrition_plan import (
    _linkify_meal_detail,
    meal_recipe_url,
)


def test_dinner_plate_anchor_w4_mon():
    url = meal_recipe_url("Dinner", "Lemon chicken and rice", cycle_week=3, weekday=0)
    assert url == "/nutrition/recipes/weekday-dinners#lemon-chicken-rice"


def test_dinner_plate_anchor_w1_sat():
    url = meal_recipe_url("Dinner", "Pork chop, apple and cabbage", cycle_week=0, weekday=6)
    assert url == "/nutrition/sunday#pork-chop-apple-cabbage"


def test_overnight_oats_breakfast():
    url = meal_recipe_url("Breakfast", "Overnight oats")
    assert url == "/nutrition/recipes/overnight-oats"


def test_porridge_breakfast():
    url = meal_recipe_url("Breakfast", "Porridge")
    assert url == "/nutrition/sunday#porridge"


def test_turkey_soup_lunch():
    url = meal_recipe_url("Lunch", "Turkey, leek and potato soup")
    assert url == "/nutrition/recipes/weekday-dinners#turkey-leek-potato-soup"


def test_beef_pasta_dinner():
    url = meal_recipe_url("Dinner", "Beef and mushroom pasta")
    assert url == "/nutrition/recipes/weekday-dinners#beef-mushroom-pasta"


def test_salmon_couscous_dinner():
    url = meal_recipe_url("Dinner", "Salmon, couscous and peas")
    assert url == "/nutrition/recipes/weekday-dinners#salmon-couscous-peas"


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

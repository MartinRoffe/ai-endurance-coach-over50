"""Homemade ride-fuel rice cakes: recipes, macros, shop batches, and the old anchor."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from ai_endurance_coach_over50.nutrition_plan import fuel_prep_for_ride
from ai_endurance_coach_over50.recipes.catalog import recipe_by_id
from ai_endurance_coach_over50.recipes.menu import default_week_targets, shopping_list
from ai_endurance_coach_over50.recipes.model import batch_grams_by_food, portion_macros
from ai_endurance_coach_over50.recipes.nutrition_table import macros_for
from ai_endurance_coach_over50.server import app


def _shop_text(targets) -> str:
    groups = shopping_list(0, targets)
    return " ".join(item for group in groups for item in group["items"])


def test_recipe_index_lists_both_homemade_cakes_with_batch_grams():
    client = TestClient(app)
    html = client.get("/nutrition/recipes").text
    assert 'id="standard-rice-cake"' in html
    assert 'id="sweet-rice-cakes"' in html
    assert "Ride fuel" in html
    assert "small rice cooker" in html.lower()
    assert "Sushi rice, dry — 400 g" in html
    assert "Eggs — 174 g" in html
    assert "Back bacon — 90 g" in html
    assert "Soy sauce — 30 ml" in html
    assert "Sesame oil — 15 ml" in html
    assert "Rice vinegar — 15 ml" in html
    assert "Bananas — 200 g" in html
    assert "Honey — 63 g" in html
    assert "Ground cinnamon — 3 g" in html
    assert "per cake" in html
    savoury = recipe_by_id("standard-rice-cake")
    sweet = recipe_by_id("sweet-rice-cakes")
    assert savoury.servings == 12
    assert sweet.servings == 10
    assert "small rice cooker" in " ".join(savoury.method).lower()
    assert "small rice cooker" in " ".join(sweet.method).lower()
    assert "0.3 g" in " ".join(sweet.method)


def test_per_cake_macros_come_from_the_ingredients():
    for recipe_id in ("standard-rice-cake", "sweet-rice-cakes"):
        recipe = recipe_by_id(recipe_id)
        direct = portion_macros(recipe, 1)
        manual = {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
        for item in recipe.ingredients:
            part = macros_for(item.food_id, item.grams / recipe.servings)
            for key in manual:
                manual[key] += part[key]
        for key, manual_value in manual.items():
            assert abs(direct[key] - manual_value) < 0.01, recipe_id
    savoury = portion_macros(recipe_by_id("standard-rice-cake"), 1)
    sweet = portion_macros(recipe_by_id("sweet-rice-cakes"), 1)
    assert 20 < savoury["carbs"] < 40
    assert sweet["carbs"] > savoury["carbs"]
    # The batch ingredients are what the recipe page weighs out.
    assert batch_grams_by_food(recipe_by_id("standard-rice-cake"))["sushi_rice"] == 400


def test_fuel_prep_uses_the_savoury_cake_carbohydrate():
    carbs = portion_macros(recipe_by_id("standard-rice-cake"), 1)["carbs"]
    prep = fuel_prep_for_ride(180, ref_date=date(2026, 10, 18))
    assert prep["rice_cakes"] == 6
    assert prep["ride_hours"] == 3.0
    assert prep["carbs_per_cake"] == round(carbs, 1)
    assert prep["solid_g_per_hr"] == round((6 * carbs) / 3.0, 1)
    note = prep["prep_note"].lower()
    assert "homemade" in note
    assert "savoury" in note
    assert str(round(carbs)) in prep["prep_note"]


def test_weekend_fuel_anchor_opens_the_savoury_recipe():
    response = TestClient(app).get("/nutrition/recipes/weekend-fuel", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/nutrition/recipes#standard-rice-cake"


def test_long_ride_card_lists_homemade_cakes_not_the_shop_product():
    html = TestClient(app).get("/nutrition?date=2026-11-01").text
    assert "Homemade savoury rice cakes — 2" in html
    assert "small rice cooker" in html.lower()
    assert "Plain rice cakes" not in html
    assert 'href="/nutrition/recipes#standard-rice-cake"' in html


def test_day_calorie_card_prices_homemade_cakes_not_the_shop_cake(monkeypatch):
    """Two on-bike cakes are the savoury recipe, not two 25 g shop cakes (~194 kcal)."""
    import ai_endurance_coach_over50.nutrition_plan as np_mod
    from ai_endurance_coach_over50.nutrition_plan import build_today_food
    from ai_endurance_coach_over50.plan import PLAN_START

    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 1900)
    food = build_today_food(PLAN_START, date(2026, 11, 1))
    on_bike = next(meal for meal in food["meals"] if meal["type"] == "On-bike")
    savoury = portion_macros(recipe_by_id("standard-rice-cake"), 1)
    sweet = portion_macros(recipe_by_id("sweet-rice-cakes"), 1)
    cakes = int(on_bike["rice_cakes"])
    assert cakes == 2
    assert round(savoury["kcal"]) == 166
    assert round(savoury["carbs"]) == 29
    assert round(sweet["kcal"]) == 180
    assert round(sweet["carbs"]) == 44
    assert int(on_bike["macros"]["kcal"]) == round(savoury["kcal"] * cakes)
    assert int(on_bike["macros"]["c"]) == round(savoury["carbs"] * cakes)
    assert int(on_bike["macros"]["kcal"]) != 194


def test_fuelling_card_tables_use_29g_per_cake():
    text = Path(__file__).resolve().parents[1].joinpath("docs/plans/fuelling-card.html").read_text()
    assert "Standard rice cake (your recipe)</td><td class=\"n\">29 g</td>" in text
    assert ">27 g<" not in text
    assert ">27<" not in text


def test_fuelling_page_names_the_homemade_cakes():
    html = TestClient(app).get("/nutrition/fuelling").text.lower()
    assert "homemade" in html
    assert "standard-rice-cake" in html
    assert "sweet-rice-cakes" in html
    assert "plain rice cake" not in html


def test_ride_week_shops_whole_sushi_rice_batches():
    ride_week = _shop_text(default_week_targets())
    assert "Sushi rice, dry — 400 g" in ride_week
    assert "Plain rice cakes" not in ride_week
    assert "Soy sauce — 30 ml" in ride_week

    easy = [
        {"kcal": 2200, "protein_low": 166, "protein_high": 184, "kind": "easy", "dur_min": 0}
        for _ in range(7)
    ]
    assert "Sushi rice" not in _shop_text(easy)

    two_batches = default_week_targets()
    two_batches[1] = {**two_batches[1], "kind": "hard", "dur_min": 120}
    two_batches[6] = {**two_batches[6], "kind": "long", "dur_min": 360}
    assert "Sushi rice, dry — 800 g" in _shop_text(two_batches)

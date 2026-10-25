"""On-bike fuel sits on top of the day's base. Dinner keeps its long-ride target."""
from datetime import date

from ai_endurance_coach_over50.nutrition_plan import (
    build_today_food,
    evening_plate_target,
    today_card,
    today_targets,
)
from ai_endurance_coach_over50.nutrition_view import nutrition_page
from ai_endurance_coach_over50.plan import PLAN_START
from ai_endurance_coach_over50.recipes.catalog import recipe_by_id
from ai_endurance_coach_over50.recipes.model import portion_macros
from ai_endurance_coach_over50.report import _daily_food_html


def _dinner(meals):
    return next(meal for meal in meals if meal["type"] == "Dinner")


def test_long_ride_day_is_base_plus_on_bike_fuel(monkeypatch):
    """1 Nov is an 85-minute long ride: 1,900 plus two homemade cakes, dinner 760/45/90."""
    import ai_endurance_coach_over50.nutrition_plan as np_mod

    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 1900)
    day = date(2026, 11, 1)
    cake = portion_macros(recipe_by_id("standard-rice-cake"), 1)
    fuel = round(cake["kcal"] * 2)
    targets = today_targets(day)
    card = today_card(day)
    food = build_today_food(PLAN_START, day)
    on_bike = next(meal for meal in food["meals"] if meal["type"] == "On-bike")
    dinner = _dinner(food["meals"])
    want = evening_plate_target("long", 1900)

    assert want == (760, 45, 90)
    assert int(on_bike["macros"]["kcal"]) == fuel
    assert targets["plate_kcal"] == 1900
    assert targets["on_bike_kcal"] == fuel
    assert targets["kcal"] == 1900 + fuel
    assert card["kcal"] == 1900 + fuel
    assert food["kcal_target"] == card["kcal"]
    assert abs(food["meals_kcal_total"] - card["kcal"]) <= card["kcal"] * 0.05
    # The plate aims at 760 kcal and 90 g carbohydrate. Protein lands higher:
    # the meat portion that reaches that calorie target is more than 45 g, and
    # cutting it would miss the day's protein range.
    assert abs(int(dinner["macros"]["kcal"]) - want[0]) <= 40
    assert abs(int(dinner["macros"]["c"]) - want[2]) <= 15
    rest_gap = abs(int(dinner["macros"]["kcal"]) - 570) + abs(int(dinner["macros"]["c"]) - 50) * 4
    long_gap = abs(int(dinner["macros"]["kcal"]) - 760) + abs(int(dinner["macros"]["c"]) - 90) * 4
    assert long_gap < rest_gap

    page = nutrition_page(PLAN_START, day)
    sunday = next(item for item in page["days"] if item["iso"] == day.isoformat())
    assert sunday["kcal"] == card["kcal"]
    html = _daily_food_html(day)
    assert f"{card['kcal']:,}" in html
    assert f"{dinner['macros']['kcal']} kcal" in html

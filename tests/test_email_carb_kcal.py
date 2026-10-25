"""Daily carb figure has to fit inside the day's calorie target."""
from datetime import date

from ai_endurance_coach_over50.nutrition_plan import today_card
from ai_endurance_coach_over50.report import _daily_food_html


def test_sunday_25_oct_carbs_fit_the_calorie_target(monkeypatch):
    import ai_endurance_coach_over50.nutrition_plan as np_mod
    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 1903)
    monkeypatch.setattr(np_mod, "current_weight_kg", lambda: 89.8)
    card = today_card(date(2026, 10, 25))
    kcal = card["kcal"]
    carbs = card["carbs_g"]
    protein = card["protein_g"]
    assert 1800 <= kcal <= 2000
    assert carbs * 4 < kcal
    assert protein * 4 + carbs * 4 <= kcal
    assert carbs < 400
    assert carbs != 584
    assert "g/kg" not in card["carbs_line"]
    html = _daily_food_html(date(2026, 10, 25))
    assert f"{carbs} g" in html
    assert "584 g" not in html

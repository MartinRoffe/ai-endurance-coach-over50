"""Nutrition robustness: calibration confidence, meal scaling, camp mode."""

from datetime import date

import pytest

from ai_endurance_coach_over50.history import body_store
from ai_endurance_coach_over50.nutrition_plan import (
    CAMP_NUTRITION_WINDOWS,
    _assemble_meals,
    build_today_food,
    camp_checklist,
    camp_day_intensity,
    camp_day_profile,
    in_camp_nutrition_window,
    is_camp_hard_day,
    nutrition_coach_context,
    scale_meals_to_target,
    today_checklist,
)
from ai_endurance_coach_over50.plan import PLAN_START


def test_calibration_confidence_high_when_data_solid():
    cal = {
        "correction": -200,
        "model_avg": 2500,
        "n_intake_days": 22,
        "span_days": 27,
    }
    conf = body_store._calibration_confidence(
        cal,
        paired_days=22,
        window_days=28,
        readings=[("2026-01-01", 80.0)] * 8,
        body_comp_age_days=3,
    )
    assert conf["level"] == "high"
    assert conf["intake_coverage_pct"] == 79


def test_calibration_confidence_limited_when_sparse():
    cal = {
        "correction": -600,
        "model_avg": 2500,
        "n_intake_days": 10,
        "span_days": 14,
    }
    conf = body_store._calibration_confidence(
        cal,
        paired_days=10,
        window_days=28,
        readings=[("2026-01-01", 80.0)] * 5,
        body_comp_age_days=20,
    )
    assert conf["level"] == "limited"
    assert conf["reasons"]


def test_scale_meals_moves_toward_target_without_cutting_protein():
    meals = _assemble_meals("training", 0, 1)  # Tuesday training
    base_p = sum(m[4] for m in meals)
    target = sum(m[3] for m in meals) + 150
    scaled, meta = scale_meals_to_target(meals, target)
    assert meta["adjusted"] is True
    assert sum(m[4] for m in scaled) == base_p
    assert abs(sum(m[3] for m in scaled) - target) <= 120 or meta.get("note")


def test_scale_meals_within_band_unchanged():
    meals = _assemble_meals("rest", 0, 0)
    total = sum(m[3] for m in meals)
    scaled, meta = scale_meals_to_target(meals, total + 50)
    assert meta["adjusted"] is False
    assert scaled == meals


@pytest.mark.parametrize("d,hard", [
    (date(2026, 8, 15), True),   # Teide hard
    (date(2026, 8, 20), False),  # full rest
    (date(2026, 8, 14), False),  # easy leg openers
])
def test_camp_hard_day_from_tenerife_intensity(d, hard):
    assert is_camp_hard_day(d) is hard


def test_christmas_camp_starts_dec_21():
    assert in_camp_nutrition_window(date(2026, 12, 21))
    assert CAMP_NUTRITION_WINDOWS[1][0] == date(2026, 12, 21)


def test_camp_checklist_suppresses_uk_plate_language():
    d = date(2026, 8, 15)
    items = camp_checklist(d, 3200)
    blob = " ".join(items).lower()
    assert "batch" not in blob or "suspended" in blob
    assert "on-bike" in blob or "g/h" in blob
    assert "/tenerife" in blob


def test_today_checklist_camp_mode_no_weekday_bike_rule():
    d = date(2026, 8, 15)
    items = today_checklist(PLAN_START, d)
    blob = " ".join(items).lower()
    assert "nothing on the bike" not in blob
    assert "camp" in blob


def test_build_today_food_camp_mode():
    d = date(2026, 8, 15)
    out = build_today_food(PLAN_START, d)
    assert out["camp_mode"] is True
    assert out["meals"] == []
    assert out["kcal_target"] >= 3200


def test_nutrition_coach_context_camp_suppresses_uk_meals():
    d = date(2026, 8, 15)
    text = nutrition_coach_context(PLAN_START, d)
    assert "CAMP MODE" in text
    assert "UK cycle suspended" in text
    assert "Batch Rice" not in text


def test_nutrition_coach_context_uk_day_lists_meals():
    d = date(2026, 7, 20)  # Monday outside camp
    text = nutrition_coach_context(PLAN_START, d)
    assert "Prescribed Meals" in text
    assert "Breakfast:" in text or "Lunch:" in text


def test_camp_day_profile_hard_teide():
    prof = camp_day_profile(date(2026, 8, 22))  # Day 9 Teide O&B
    assert prof is not None
    assert prof["hard_day"] is True
    assert "Teide" in (prof.get("session_label") or "")


def test_camp_day_3_chio_is_medium():
    intensity, label = camp_day_intensity(date(2026, 8, 16))
    assert intensity == "medium"
    assert label is not None and "Chío" in label
    prof = camp_day_profile(date(2026, 8, 16))
    assert prof is not None
    # Nutrition treats medium as a camp hard-fuelling day (_CAMP_HARD_INTENSITIES).
    assert prof["hard_day"] is True
    assert "Teide" not in (prof.get("session_label") or "")


def test_camp_day_intensity_rest_day():
    intensity, label = camp_day_intensity(date(2026, 8, 20))
    assert intensity == "rest"
    assert label is not None

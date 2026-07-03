"""Tests for adaptive TDEE calibration (energy.py + body_store)."""
import math
from datetime import date, timedelta

from ai_endurance_coach_over50.energy import (
    apply_tdee_correction,
    empirical_tdee,
    tdee_correction,
    weight_trend_kg_per_day,
)
from ai_endurance_coach_over50.history import (
    save,
    save_body_metrics,
    tdee_calibration,
    tdee_history,
)
from ai_endurance_coach_over50.metrics import DailyMetrics


# ── Pure math ────────────────────────────────────────────────────────────────

def test_weight_trend_linear_decline():
    base = date(2026, 1, 1)
    readings = [
        ((base + timedelta(days=i * 7)).isoformat(), 80.0 - i * 0.5)
        for i in range(5)
    ]
    slope = weight_trend_kg_per_day(readings)
    assert slope is not None
    assert slope < 0
    assert math.isclose(slope, -0.5 / 7, rel_tol=0.02)


def test_weight_trend_none_fewer_than_five_readings():
    base = date(2026, 1, 1)
    readings = [
        ((base + timedelta(days=i * 7)).isoformat(), 80.0 - i * 0.5)
        for i in range(4)
    ]
    assert weight_trend_kg_per_day(readings) is None


def test_weight_trend_none_span_under_fourteen_days():
    base = date(2026, 1, 1)
    readings = [
        ((base + timedelta(days=i * 2)).isoformat(), 80.0 - i * 0.1)
        for i in range(5)
    ]
    assert weight_trend_kg_per_day(readings) is None


def test_empirical_tdee_arithmetic():
    result = empirical_tdee(1841, -0.054)
    assert math.isclose(result, 2257, abs_tol=2)


def test_tdee_correction_clamps_at_twenty_five_percent():
    model = 2650.0
    empirical = 1500.0
    assert tdee_correction(model, empirical) == -0.25 * model


def test_tdee_correction_within_band():
    model = 2650.0
    empirical = 2257.0
    assert math.isclose(tdee_correction(model, empirical), -393, abs_tol=1)


def test_apply_tdee_correction():
    assert apply_tdee_correction(2500, -270) == 2230
    assert apply_tdee_correction(2500, None) == 2500
    assert apply_tdee_correction(None, -270) is None


# ── DB-backed ────────────────────────────────────────────────────────────────

def _seed_losing_trend_with_intake():
    """28-day window: downward weight trend + steady intake + model TDEE inputs."""
    today = date.today()
    weights = []
    for i in range(5):
        d = today - timedelta(days=27 - i * 7)
        weights.append({
            "date": d.isoformat(),
            "weight_kg": 82.0 - i * 0.6,
            "fat_pct": 22.0,
        })
    save_body_metrics(weights)

    for offset in range(28):
        d = today - timedelta(days=27 - offset)
        save(DailyMetrics(
            date=d,
            calories_consumed=1841,
            active_calories=850,
        ))


def test_tdee_calibration_returns_negative_correction():
    _seed_losing_trend_with_intake()
    cal = tdee_calibration(28)
    assert cal is not None
    assert cal["correction"] < 0
    assert cal["n_intake_days"] >= 10
    assert cal["n_weighins"] >= 5
    assert cal["span_days"] >= 14


def test_tdee_history_applies_correction():
    _seed_losing_trend_with_intake()
    cal = tdee_calibration(28)
    assert cal is not None
    rows = [r for r in tdee_history(14) if r.get("tdee_model") is not None]
    assert rows
    for row in rows:
        assert row["calibration_kcal"] == cal["correction"]
        assert row["tdee"] == row["tdee_model"] + cal["correction"]


def test_tdee_calibration_guardrail_insufficient_weighins():
    today = date.today()
    save_body_metrics([
        {"date": (today - timedelta(days=2)).isoformat(), "weight_kg": 80.0, "fat_pct": 22.0},
        {"date": (today - timedelta(days=1)).isoformat(), "weight_kg": 79.8, "fat_pct": 22.0},
        {"date": today.isoformat(), "weight_kg": 79.6, "fat_pct": 22.0},
    ])
    for offset in range(12):
        d = today - timedelta(days=11 - offset)
        save(DailyMetrics(date=d, calories_consumed=2000, active_calories=600))

    assert tdee_calibration(28) is None
    rows = [r for r in tdee_history(7) if r.get("tdee_model") is not None]
    assert rows
    for row in rows:
        assert row["tdee"] == row["tdee_model"]
        assert row["calibration_kcal"] is None


def test_tdee_history_regression_shape():
    today = date.today()
    save_body_metrics([{
        "date": (today - timedelta(days=1)).isoformat(),
        "weight_kg": 78.0,
        "fat_pct": 20.0,
    }])
    save(DailyMetrics(date=today, active_calories=500))

    rows = tdee_history(3)
    assert rows
    row = rows[-1]
    assert "bmr" in row
    assert "active_calories" in row
    assert "active_estimated" in row
    assert "tdee_model" in row
    assert "calibration_kcal" in row
    assert "tdee" in row

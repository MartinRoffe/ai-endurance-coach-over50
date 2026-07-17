"""Stable-TDEE-derived intake targets and meal-plan alignment."""

from datetime import date

from ai_endurance_coach_over50.energy import (
    MIN_INTAKE_KCAL,
    intake_target_kcal,
)
from ai_endurance_coach_over50 import nutrition_plan as np_mod
from ai_endurance_coach_over50.history import body_store
from ai_endurance_coach_over50.nutrition_plan import (
    DAY_TYPES,
    _WEEKDAY_TO_TYPE_BUILD,
    _WEEKDAY_TO_TYPE_RECOVERY,
    _assemble_meals,
    on_bike_fuel_kcal,
    resolve_calorie_target,
)

# A Monday well outside every Tenerife camp window.
_NON_CAMP = date(2026, 7, 20)


# ── intake_target_kcal ────────────────────────────────────────────────────────

def test_intake_target_training_deficit():
    assert intake_target_kcal(2000, "training") == 1750


def test_intake_target_rest_larger_deficit():
    assert intake_target_kcal(2000, "rest") == 1650


def test_intake_target_long_near_maintenance():
    assert intake_target_kcal(2500, "long") == 2450


def test_intake_target_long_scales_with_duration():
    # 3 h ride = 60 min beyond 2 h baseline → +175 kcal
    assert intake_target_kcal(2500, "long", long_ride_extra_min=60) == 2625


def test_intake_target_respects_floor():
    assert MIN_INTAKE_KCAL == 1600
    assert intake_target_kcal(1700, "rest") == MIN_INTAKE_KCAL


def test_intake_target_none_without_tdee():
    assert intake_target_kcal(None, "training") is None


# ── resolve_calorie_target ────────────────────────────────────────────────────

def test_resolve_calorie_target_falls_back_to_static():
    out = resolve_calorie_target(None, "training", _NON_CAMP)
    assert out["kcal"] == 2350
    assert out["from_tdee"] is False


def test_resolve_calorie_target_from_tdee():
    out = resolve_calorie_target(2000, "training", _NON_CAMP)
    assert out["from_tdee"] is True
    assert out["kcal"] == 1750
    assert out["planned_deficit"] == 250
    assert out["tdee"] == 2000


def test_resolve_calorie_target_camp_hard_day():
    out = resolve_calorie_target(2800, "training", date(2026, 8, 15))
    assert out["camp"] is True
    assert out["kcal"] >= 3200
    # Camp hard days fuel above TDEE — planned deficit is negative.
    assert out["planned_deficit"] < 0
    assert out["tdee"] == 2800


# ── stable TDEE helper ───────────────────────────────────────────────────────

def _tdee_rows(values):
    return [
        {"date": date(2026, 7, 10 + i), "tdee": v, "active_estimated": est}
        for i, (v, est) in enumerate(values)
    ]


def test_stable_tdee_prefers_non_estimated_days(monkeypatch):
    rows = _tdee_rows([
        (2000, False), (2100, False), (1900, False),
        (1400, True), (1300, True),
    ])
    monkeypatch.setattr(body_store, "tdee_history", lambda days=7: rows)
    assert body_store.stable_tdee_kcal(7) == 2000  # mean of the 3 solid days


def test_stable_tdee_uses_all_days_when_few_solid(monkeypatch):
    rows = _tdee_rows([(2000, True), (1800, True), (1600, False)])
    monkeypatch.setattr(body_store, "tdee_history", lambda days=7: rows)
    assert body_store.stable_tdee_kcal(7) == 1800  # only 1 solid day → use all


def test_stable_tdee_none_without_data(monkeypatch):
    monkeypatch.setattr(body_store, "tdee_history", lambda days=7: [
        {"date": date(2026, 7, 10), "tdee": None, "active_estimated": False}
    ])
    assert body_store.stable_tdee_kcal(7) is None


# ── meals align with targets ─────────────────────────────────────────────────

def test_meal_sums_match_targets_for_every_day_type():
    """Every day's prescribed meals land within ±100 kcal of its intake target."""
    stable = 2000
    for cw in range(4):
        wd_map = _WEEKDAY_TO_TYPE_BUILD if cw < 3 else _WEEKDAY_TO_TYPE_RECOVERY
        for wd in range(7):
            dtype = wd_map[wd]
            meals = _assemble_meals(dtype, cw, wd)
            total = sum(m[3] for m in meals)
            tier = DAY_TYPES[dtype]["calorie_tier"]
            target = intake_target_kcal(stable, tier)
            assert abs(total - target) <= 100, (
                f"cycle week {cw} weekday {wd} ({dtype}): "
                f"meals sum {total} vs target {target}"
            )


def test_meal_protein_hits_lean_mass_floor():
    """Every day's meals deliver at least ~140 g protein (lean-mass floor)."""
    for cw in range(4):
        wd_map = _WEEKDAY_TO_TYPE_BUILD if cw < 3 else _WEEKDAY_TO_TYPE_RECOVERY
        for wd in range(7):
            dtype = wd_map[wd]
            meals = _assemble_meals(dtype, cw, wd)
            protein = sum(m[4] for m in meals)
            assert protein >= 140, (
                f"cycle week {cw} weekday {wd} ({dtype}): protein {protein}g < 140g"
            )


def test_recovery_week_skips_protein_bar_on_rest_days():
    """Recovery Mon/Wed/Fri drop the AM protein bar; Tue/Thu keep it."""
    for wd, expect_bar in ((0, False), (1, True), (2, False), (3, True), (4, False)):
        meals = _assemble_meals("recovery_weekday", 3, wd)
        has_bar = any(m[0] == "AM Snack" for m in meals)
        assert has_bar is expect_bar, f"weekday {wd}: bar present={has_bar}"


def test_on_bike_fuel_scales_with_duration():
    assert on_bike_fuel_kcal(120) == 440
    assert on_bike_fuel_kcal(210) == 770


def test_build_today_food_scales_on_bike_row(monkeypatch):
    """A 3.5 h planned long ride inflates the On-Bike meal row."""
    from ai_endurance_coach_over50 import plan as plan_mod

    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 2000)
    monkeypatch.setattr(
        plan_mod, "session_for_date_extended", lambda d: ("long", "Long Ride", 210)
    )
    # A Sunday in a build week (cycle week 0 starts at plan start).
    plan_start = date(2026, 5, 18)
    sunday = date(2026, 5, 24)
    out = np_mod.build_today_food(plan_start, sunday)
    on_bike = next(m for m in out["meals"] if m["type"] == "On-Bike")
    assert on_bike["macros"]["kcal"] == str(on_bike_fuel_kcal(210))
    # Target also grows: 2000 − 50 + 175 × 1.5 h
    assert out["kcal_target"] == 2000 - 50 + round(175 * 1.5)

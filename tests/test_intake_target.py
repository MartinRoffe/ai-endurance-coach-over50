"""Stable-TDEE-derived intake targets and meal-plan alignment."""

from datetime import date

from ai_endurance_coach_over50.energy import (
    MIN_INTAKE_KCAL,
    active_cut_phase,
    in_maintenance_window,
    intake_target_kcal,
)
from ai_endurance_coach_over50 import nutrition_plan as np_mod
from ai_endurance_coach_over50.history import body_store
from ai_endurance_coach_over50.nutrition_plan import (
    DAY_TYPES,
    _WEEKDAY_TO_TYPE_BUILD,
    _WEEKDAY_TO_TYPE_RECOVERY,
    _assemble_meals,
    calorie_tier_for_session,
    on_bike_fuel_kcal,
    resolve_calorie_target,
)

# A Monday well outside every Tenerife camp window and cut phase.
_NON_CAMP = date(2026, 7, 20)


# ── intake_target_kcal ────────────────────────────────────────────────────────

def test_intake_target_training_deficit():
    # Easy day. At TDEE 2000 the 600 kcal deficit hits the 1,600 floor.
    assert intake_target_kcal(2000, "training") == 1600


def test_intake_target_rest_larger_deficit():
    # Rest is the same easy day.
    assert intake_target_kcal(2000, "rest") == 1600


def test_intake_target_long_near_maintenance():
    assert intake_target_kcal(2500, "long") == 2500


def test_intake_target_long_scales_with_duration():
    # 3 h ride = 60 min beyond 2 h baseline → +175 kcal
    assert intake_target_kcal(2500, "long", long_ride_extra_min=60) == 2675


def test_intake_target_respects_floor():
    assert MIN_INTAKE_KCAL == 1600
    assert intake_target_kcal(1700, "rest") == MIN_INTAKE_KCAL


def test_intake_target_none_without_tdee():
    assert intake_target_kcal(None, "training") is None


# ── maintenance window (9 Oct 2026 – 3 Jan 2027) ──────────────────────────────

def test_maintenance_window_edges():
    assert not in_maintenance_window(date(2026, 10, 8))
    assert in_maintenance_window(date(2026, 10, 9))
    assert in_maintenance_window(date(2027, 1, 3))
    assert not in_maintenance_window(date(2027, 1, 4))
    assert not in_maintenance_window(None)


def test_intake_target_zero_deficit_in_maintenance_window():
    assert intake_target_kcal(2000, "training", ref_date=date(2026, 12, 1)) == 2000
    assert intake_target_kcal(2000, "rest", ref_date=date(2026, 12, 1)) == 2000
    assert intake_target_kcal(2000, "training") == 1600


def test_resolve_calorie_target_maintenance_flag():
    out = resolve_calorie_target(2000, "training", date(2026, 12, 1))
    assert out["maintenance"] is True
    assert out["planned_deficit"] == 0
    assert out["kcal"] == 2000
    assert out["cut_phase"] is None
    out2 = resolve_calorie_target(2000, "training", _NON_CAMP)
    assert out2["maintenance"] is False


def test_camp_window_wins_over_maintenance():
    # August 2026 is not a live camp window and not maintenance.
    out = resolve_calorie_target(2800, "training", date(2026, 8, 15))
    assert out["camp"] is False
    assert out["maintenance"] is False
    assert out["kcal"] == 2200


# ── Base Cut phases (hard / ease) ─────────────────────────────────────────────

def test_cut_phase_edges():
    assert active_cut_phase(date(2026, 12, 21)) is None
    assert active_cut_phase(date(2027, 1, 3)) is None
    assert active_cut_phase(date(2027, 1, 4)) == "ease"
    assert active_cut_phase(date(2027, 3, 31)) == "ease"
    assert active_cut_phase(date(2027, 4, 1)) is None


def test_hard_cut_deficit():
    # Before the kidney window: easy deficit is 600 for rest and training.
    assert intake_target_kcal(2400, "training", ref_date=date(2026, 10, 5)) == 1800
    assert intake_target_kcal(2400, "rest", ref_date=date(2026, 10, 5)) == 1800
    out = resolve_calorie_target(2400, "training", date(2026, 10, 5))
    assert out["cut_phase"] is None
    assert out["planned_deficit"] == 600
    assert out["tier_deficit"] == 600
    assert out["cut_target_kg"] == 84.5


def test_ease_cut_deficit():
    # 1 Dec sits in the kidney-return maintenance window, so the ease-phase
    # deficit is suspended and intake equals TDEE.
    assert intake_target_kcal(2400, "training", ref_date=date(2026, 12, 1)) == 2400
    out = resolve_calorie_target(2400, "training", date(2026, 12, 1))
    assert out["maintenance"] is True
    assert out["cut_phase"] is None
    assert out["planned_deficit"] == 0


def test_camp_wins_over_hard_cut():
    # Christmas 23 Dec is maintenance, not the old race-camp surplus.
    out = resolve_calorie_target(2800, "training", date(2026, 12, 23))
    assert out["camp"] is False
    assert out["cut_phase"] is None
    assert out["maintenance"] is True
    assert out["kcal"] == 2800


def test_calorie_tier_for_session():
    assert calorie_tier_for_session("long", "training") == "long"
    assert calorie_tier_for_session("rest", "training") == "easy"
    assert calorie_tier_for_session("gym", "training") == "easy"
    assert calorie_tier_for_session("vo2", "rest") == "hard"
    assert calorie_tier_for_session(None, "ruck") == "easy"


# ── today_targets (single-number resolver) ────────────────────────────────────

def test_today_targets_long_ride_crowns_gut_training_carbs(monkeypatch):
    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 2000)
    # Wk 10 Sunday: Long Ride 255 min, charity wk 9+ → 90 g/h.
    out = np_mod.today_targets(date(2026, 7, 26))
    assert out["session"]["type"] == "long"
    assert out["carbs_g_per_hr"] == 90
    assert out["fuel_prep"] is not None
    assert out["kcal_source"] == "tdee"
    assert out["maintenance"] is False
    assert out["protein_low"] > 0
    assert out["calorie_tier"] == "long"


def test_today_targets_maintenance_and_rest(monkeypatch):
    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 2000)
    monkeypatch.setattr(
        "ai_endurance_coach_over50.plan.session_for_date_extended",
        lambda d: ("rest", "Rest", 0),
    )
    monkeypatch.setattr(
        "ai_endurance_coach_over50.hr_plan.hr_session_for_date",
        lambda d: None,
    )
    out = np_mod.today_targets(date(2026, 12, 1))
    assert out["maintenance"] is True
    assert out["planned_deficit"] == 0
    assert out["carbs_g_per_hr"] is None
    assert out["cut_phase"] is None


def test_today_targets_hard_cut_exposes_phase(monkeypatch):
    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 2400)
    out = np_mod.today_targets(date(2026, 10, 6))  # before the March cut, outside maintenance
    assert out["cut_phase"] is None
    assert out["cut_target_kg"] == 84.5
    assert out["planned_deficit"] in (600, 250, 0) or (
        out["calorie_tier"] == "long" and out["planned_deficit"] <= 0
    )


def test_today_targets_tier_fallback_without_tdee(monkeypatch):
    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: None)
    out = np_mod.today_targets(date(2026, 7, 20))
    assert out["kcal_source"] == "tier"
    assert out["kcal"] > 0


def test_protein_floor_locked_during_cut(monkeypatch):
    store = {}

    def fake_get(key):
        return store.get(key)

    def fake_set(key, value):
        store[key] = value

    monkeypatch.setattr(np_mod, "get_cached_text", fake_get, raising=False)
    # Patch where _ensure_cut_lean_snapshot imports from
    import ai_endurance_coach_over50.history as hist

    monkeypatch.setattr(hist, "get_cached_text", fake_get)
    monkeypatch.setattr(hist, "set_cached_text", fake_set)
    monkeypatch.setattr(hist, "latest_lean_mass_kg", lambda: 62.0)

    pt1 = np_mod.protein_target_g(date(2027, 1, 4))
    assert store.get(np_mod._CUT_LEAN_CACHE_KEY) == "62.00"
    assert pt1["lean_kg"] == 62.0

    monkeypatch.setattr(hist, "latest_lean_mass_kg", lambda: 60.0)
    pt2 = np_mod.protein_target_g(date(2027, 1, 15))
    assert pt2["lean_kg"] == 62.0
    assert pt2["lean_locked"] is True
    assert pt2["low"] == round(62.0 * 2.2)


# ── resolve_calorie_target ────────────────────────────────────────────────────

def test_resolve_calorie_target_falls_back_to_static():
    out = resolve_calorie_target(None, "training", _NON_CAMP)
    assert out["kcal"] == 2200
    assert out["from_tdee"] is False


def test_resolve_calorie_target_from_tdee():
    out = resolve_calorie_target(2000, "training", _NON_CAMP)
    assert out["from_tdee"] is True
    assert out["kcal"] == 1600
    assert out["planned_deficit"] == 400
    assert out["tier_deficit"] == 600
    assert out["tdee"] == 2000


def test_resolve_calorie_target_camp_hard_day():
    out = resolve_calorie_target(2800, "training", date(2026, 8, 15))
    assert out["camp"] is False
    assert out["kcal"] == 2200
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
    """Each day scales onto the fallback target and keeps protein in range."""
    for cw in range(4):
        wd_map = _WEEKDAY_TO_TYPE_BUILD if cw < 3 else _WEEKDAY_TO_TYPE_RECOVERY
        for wd in range(7):
            dtype = wd_map[wd]
            meals = _assemble_meals(dtype, cw, wd)
            slots = [m[0] for m in meals]
            assert slots[0] == "Breakfast"
            assert "Lunch" in slots and "Dinner" in slots
            assert "AM Snack" not in slots
            total = sum(m[3] for m in meals)
            assert abs(total - 2200) <= 2200 * 0.05
            assert 166 <= sum(m[4] for m in meals) <= 184


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
    meals = _assemble_meals("recovery_weekday", 3, 0)
    slots = [m[0] for m in meals]
    assert "Breakfast" in slots and "Lunch" in slots and "Dinner" in slots
    assert all(m[0] != "AM Snack" for m in meals)


def test_on_bike_fuel_scales_with_duration():
    assert on_bike_fuel_kcal(120) == 440
    assert on_bike_fuel_kcal(210) == 770


def test_meal_day_type_rest_saturday_not_ruck():
    # Cycle week 3 Saturday normally maps to recovery_saturday
    assert np_mod.today_day_type(3, 5) == "recovery_saturday"
    assert np_mod.meal_day_type_for_session("rest", "Rest", 3, 5) == "rest"
    assert np_mod.meal_day_type_for_session("rest", "Rest", 0, 5) == "rest"


def test_meal_day_type_real_ruck_saturday():
    assert np_mod.meal_day_type_for_session("ruck", "Ruck  8–10 kg", 0, 5) == "ruck"
    assert np_mod.meal_day_type_for_session(
        "ruck", "Easy recovery ruck", 3, 5
    ) == "recovery_saturday"


def test_meal_day_type_bike_on_ruck_saturday_slot():
    assert np_mod.meal_day_type_for_session(
        "bike", "Z2 Endurance", 0, 5, session_dur=75
    ) == "bike"


def test_build_today_food_rest_saturday_no_post_ruck(monkeypatch):
    """A rest day has lunch and dinner, and no post-ruck slot."""
    from ai_endurance_coach_over50.plan import PLAN_START

    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 2000)
    monkeypatch.setattr(
        "ai_endurance_coach_over50.plan.session_for_date_extended",
        lambda d: ("rest", "Rest", 0),
    )
    monkeypatch.setattr(
        "ai_endurance_coach_over50.hr_plan.hr_session_for_date",
        lambda d: None,
    )
    d = date(2026, 12, 5)
    out = np_mod.build_today_food(PLAN_START, d)
    assert "Rest" in out["session"]
    slots = [m["type"] for m in out["meals"]]
    assert "Breakfast" in slots and "Lunch" in slots and "Dinner" in slots
    assert "Post-Ruck" not in slots and "AM Snack" not in slots
    assert out["kcal_target"] == np_mod.today_targets(d)["kcal"]
    assert abs(out["meals_kcal_total"] - out["kcal_target"]) <= out["kcal_target"] * 0.05
    assert out["maintenance"] is True
    assert "maintenance" in (out.get("why") or "").lower()


def test_build_today_food_real_ruck_saturday_keeps_post_ruck(monkeypatch):
    from ai_endurance_coach_over50.plan import PLAN_START

    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 2000)
    out = np_mod.build_today_food(PLAN_START, date(2026, 5, 30))
    slots = [m["type"] for m in out["meals"]]
    assert "Breakfast" in slots and "Lunch" in slots and "Dinner" in slots
    assert "Post-Ruck" not in slots
    assert out["kcal_target"] == np_mod.today_targets(date(2026, 5, 30))["kcal"]
    assert abs(out["meals_kcal_total"] - out["kcal_target"]) <= out["kcal_target"] * 0.05


def test_hard_cut_rest_kcal_below_long(monkeypatch):
    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 2400)
    rest = np_mod.resolve_calorie_target(2400, "rest", date(2026, 10, 5))
    training = np_mod.resolve_calorie_target(2400, "training", date(2026, 10, 5))
    long = np_mod.resolve_calorie_target(
        2400, "long", date(2026, 10, 5), session_dur_min=180
    )
    assert rest["kcal"] == training["kcal"] < long["kcal"]
    assert rest["tier_deficit"] == 600
    assert training["tier_deficit"] == 600
    assert long["tier_deficit"] == 0
    assert long["long_fuel_topup"] == 175


def test_today_targets_exposes_why(monkeypatch):
    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 2000)
    monkeypatch.setattr(
        "ai_endurance_coach_over50.plan.session_for_date_extended",
        lambda d: ("rest", "Rest", 0),
    )
    monkeypatch.setattr(
        "ai_endurance_coach_over50.hr_plan.hr_session_for_date",
        lambda d: None,
    )
    out = np_mod.today_targets(date(2026, 12, 1))
    assert out["phase"] == "maintenance"
    assert out["planned_deficit"] == 0
    assert "maintenance" in out["why"].lower()
    assert out["tier_deficit"] == 0


def test_build_today_food_scales_on_bike_row(monkeypatch):
    """A long ride adds ride fuel to the calorie target. Meals stay four doses."""
    from ai_endurance_coach_over50 import plan as plan_mod

    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 2000)
    monkeypatch.setattr(
        plan_mod, "session_for_date_extended", lambda d: ("long", "Long Ride", 210)
    )
    plan_start = date(2026, 5, 18)
    sunday = date(2026, 5, 24)
    out = np_mod.build_today_food(plan_start, sunday)
    slots = [m["type"] for m in out["meals"]]
    assert "Pre-ride" in slots and "On-bike" in slots and "Post-ride" in slots
    assert "Breakfast" in slots and "Dinner" in slots
    assert out["kcal_target"] == np_mod.today_targets(sunday)["kcal"]
    assert abs(out["meals_kcal_total"] - out["kcal_target"]) <= out["kcal_target"] * 0.05
    assert out["kcal_target"] == 2000 + round(175 * 1.5)
    card = np_mod.today_card(sunday)
    assert card["kind"] == "long"
    assert set(card) >= {"kcal", "protein_g", "carbs_g", "fluids", "habit", "stone_line"}

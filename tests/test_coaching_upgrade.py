"""Camp hours, BUSAR build, cut band, Foster load, wellness, and HRV ln(rMSSD)."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from ai_endurance_coach_over50.energy import (
    CUT_TARGET_KG,
    energy_availability,
    fluid_shortfall_l,
    fluid_target_litres,
    intake_target_kcal,
)
from ai_endurance_coach_over50.fitness_plan import (
    pullup_for_date,
    session_for_date,
)
from ai_endurance_coach_over50.load import foster_load, planned_load
from ai_endurance_coach_over50.metrics import DailyMetrics
from ai_endurance_coach_over50.report import _build_advice_prompt, _rule_based_advice
from ai_endurance_coach_over50.safety import is_hard, prescribed_session
from ai_endurance_coach_over50.server import app


def _hards(monday: date) -> list[date]:
    return [
        monday + timedelta(days=i)
        for i in range(7)
        if is_hard(session_for_date(monday + timedelta(days=i)))
    ]


def test_quality_starts_20_oct_then_two_from_26_oct():
    assert _hards(date(2026, 10, 12)) == []
    assert _hards(date(2026, 10, 19)) == [date(2026, 10, 20)]
    later = _hards(date(2026, 10, 26))
    assert later == [date(2026, 10, 27), date(2026, 10, 29)]
    assert later[1] - later[0] >= timedelta(days=2)
    nov = _hards(date(2026, 11, 2))
    assert nov == [date(2026, 11, 3), date(2026, 11, 5)]
    assert nov[1] - nov[0] >= timedelta(days=2)


def test_three_hour_sunday_survives_the_weekly_cap():
    day = date(2026, 11, 22)
    assert session_for_date(day)[2] == 180
    assert prescribed_session(day).session[2] == 180


def test_camp_week_is_not_trimmed_to_the_home_cap():
    teide = prescribed_session(date(2026, 12, 26))
    assert teide.session == ("long", "Teide — optional long day · outdoor", 300)
    long_quality = prescribed_session(date(2026, 12, 28))
    assert long_quality.session[2] == 240


def test_clearance_week_does_not_cap_the_return():
    ride = prescribed_session(date(2026, 10, 25))
    assert ride.session == ("long", "Long Ride (Easy) · outdoor", 70)


def test_pullups_three_days_a_week_change_phase():
    assert pullup_for_date(date(2026, 10, 26)) is None  # Monday
    assert "negatives" in pullup_for_date(date(2026, 10, 27))
    assert "band-assisted" in pullup_for_date(date(2027, 1, 5))
    assert "strict" in pullup_for_date(date(2027, 2, 2))
    assert pullup_for_date(date(2027, 2, 20)) is None


def test_ruck_reaches_pack_test_load_without_a_kettlebell_deadlift():
    assert "15 kg" in session_for_date(date(2027, 1, 9))[1]
    assert "15 kg" in session_for_date(date(2027, 2, 6))[1]
    assert "20.4" not in session_for_date(date(2027, 2, 6))[1]
    rehearsal = session_for_date(date(2027, 2, 13))
    assert rehearsal[0] == "ruck"
    assert "rehearsal" in rehearsal[1]
    assert "20.4" in rehearsal[1]
    heavy = session_for_date(date(2027, 1, 5))
    assert "sandbag" in heavy[1]
    assert "kettlebell" not in heavy[1].lower()
    skills = session_for_date(date(2027, 2, 9))
    assert "step-overs" in skills[1]
    assert "burpee" in skills[1]
    assert session_for_date(date(2026, 10, 29))[0] == "rower"
    assert session_for_date(date(2026, 11, 26))[0] == "maxiclimber"
    assert session_for_date(date(2026, 10, 20)) == ("rower", "Threshold — rower", 40)
    assert session_for_date(date(2026, 10, 21))[0] == "strength"


def test_foster_load_prefers_rpe_and_terrains_a_ruck():
    assert foster_load(60, 8) == 480
    assert foster_load(60, None) == 60
    assert foster_load(70, None, pack_kg=20.4, terrain=True) == pytest.approx(70 * 1.408)
    assert foster_load(60, None, vert_m=1000, terrain=True) == pytest.approx(60 * 1.20)
    assert planned_load(("ruck", "Hill ruck 10 kg", 70)) == pytest.approx(70 * 1.2)
    assert planned_load(("bike", "Z2 Easy", 60)) == 60


def test_cut_lands_near_84_kg_and_protects_hard_days():
    assert CUT_TARGET_KG == 84.5
    assert intake_target_kcal(2400, "training", ref_date=date(2027, 1, 4)) == 1800
    assert intake_target_kcal(2400, "hard", ref_date=date(2027, 1, 4)) == 2150
    assert intake_target_kcal(2400, "long", ref_date=date(2027, 1, 4)) == 2400


def test_energy_availability_and_fluid_targets():
    ffm = 90 * 0.8
    assert energy_availability(1800, 400, ffm) == pytest.approx((1800 - 400) / ffm)
    assert energy_availability(1800, 400, ffm) < 30
    assert energy_availability(None, 400, ffm) is None
    target = fluid_target_litres(120)
    assert target["low_l"] == 3.5
    assert target["high_l"] == 4.0
    assert fluid_shortfall_l(None, 0) is None
    assert fluid_shortfall_l(2.0, 0) == pytest.approx(0.5)
    assert fluid_shortfall_l(1.4, 0) == pytest.approx(1.1)


def test_low_ea_and_muscle_loss_alert(monkeypatch):
    import ai_endurance_coach_over50.alerts as alerts

    today = date(2026, 6, 20)
    monkeypatch.setattr(alerts, "raw_history", lambda days=5: [])
    monkeypatch.setattr(alerts, "pmc_history", lambda days=6: [])
    monkeypatch.setattr(alerts, "load_activities_by_date", lambda a, b: {})
    monkeypatch.setattr(alerts, "weekly_monotony_strain", lambda weeks=2: [])
    monkeypatch.setattr(alerts, "load_ftp_tests", lambda: [])
    monkeypatch.setattr(alerts, "history_for_chart", lambda days=14: [])
    monkeypatch.setattr(alerts, "load", lambda d: DailyMetrics(
        date=today, calories_consumed=2800, active_calories=2000,
    ))
    monkeypatch.setattr(alerts, "load_body_metrics", lambda days=30: [
        {"date": "2026-06-01", "weight_kg": 90.0, "fat_pct": 20.0, "muscle_mass_kg": 40.0},
        {"date": "2026-06-10", "weight_kg": 89.5, "fat_pct": 20.0, "muscle_mass_kg": 39.7},
        {"date": "2026-06-20", "weight_kg": 89.0, "fat_pct": 20.0, "muscle_mass_kg": 39.2},
    ])
    types = {a["type"] for a in alerts.check_fatigue_alerts(today)}
    # Active calories are high, but no logged session calories, so EA stays comfortable.
    assert "LOW_EA" not in types
    assert "MUSCLE_DOWN" in types


def test_low_ea_uses_session_calories_and_needs_five_logged_days(monkeypatch):
    import ai_endurance_coach_over50.alerts as alerts

    today = date(2026, 6, 20)
    monkeypatch.setattr(alerts, "raw_history", lambda days=5: [])
    monkeypatch.setattr(alerts, "pmc_history", lambda days=6: [])
    monkeypatch.setattr(alerts, "weekly_monotony_strain", lambda weeks=2: [])
    monkeypatch.setattr(alerts, "load_ftp_tests", lambda: [])
    monkeypatch.setattr(alerts, "history_for_chart", lambda days=14: [])
    monkeypatch.setattr(alerts, "load_body_metrics", lambda days=30: [
        {"date": "2026-06-20", "weight_kg": 90.0, "fat_pct": 20.0, "muscle_mass_kg": 40.0},
    ])
    monkeypatch.setattr(alerts, "load", lambda d: DailyMetrics(
        date=d, calories_consumed=2200, active_calories=1800,
    ))
    monkeypatch.setattr(alerts, "load_activities_by_date", lambda a, b: {
        (today - timedelta(days=i)).isoformat(): [{"calories": 900}]
        for i in range(7)
    })
    types = {a["type"] for a in alerts.check_fatigue_alerts(today)}
    assert "LOW_EA" in types
    low = next(a for a in alerts.check_fatigue_alerts(today) if a["type"] == "LOW_EA")
    assert low["severity"] == "MODERATE"

    def sparse(d):
        if (today - d).days < 4:
            return DailyMetrics(date=d, calories_consumed=1500, active_calories=2000)
        return DailyMetrics(date=d, active_calories=2000)

    monkeypatch.setattr(alerts, "load", sparse)
    types = {a["type"] for a in alerts.check_fatigue_alerts(today)}
    assert "LOW_EA" not in types


def test_wellness_red_flag_forces_rest(monkeypatch):
    monkeypatch.setattr(
        "ai_endurance_coach_over50.history.get_morning_wellness",
        lambda day: {"flank_pain": day == "2026-10-27", "fever": False, "blood": False},
    )
    monkeypatch.setattr(
        "ai_endurance_coach_over50.history.list_session_notes",
        lambda: {},
    )
    cap = prescribed_session(date(2026, 10, 27))
    assert cap.session[0] == "rest"
    assert cap.reason


def test_morning_prompt_explains_the_rule_instead_of_choosing(monkeypatch):
    monkeypatch.setattr(
        "ai_endurance_coach_over50.report._modulation_sentence",
        lambda m, comp_z: "Rule-based decision: Recovery Spin (30 min) instead of Threshold — bike.",
    )
    m = DailyMetrics(date=date(2026, 10, 27), hrv_last_night=40, sleep_score=70)
    prompt = _build_advice_prompt(m, {}, None, timing={
        "post_workout": False,
        "is_today": True,
        "local_time": "07:30",
        "part_of_day": "morning",
        "session": ("threshold", "Threshold — bike", 40),
        "completed": False,
        "matched_activities": [],
    })
    assert "Do not choose Train, Rest, or Active Recovery yourself." in prompt
    assert "Train / Rest / Active Recovery" not in prompt
    assert "Recovery Spin" in prompt
    text = _rule_based_advice(m, {}, -0.2, timing={"post_workout": False})
    assert text.startswith("Rule-based decision:")
    assert "Recommendation:" not in text


def test_dashboard_wellness_and_rpe_round_trip():
    client = TestClient(app)
    page = client.get("/?date=2026-10-14")
    assert page.status_code == 200
    assert "Morning check" in page.text
    assert "Fluid target" in page.text
    bad = client.post("/log-rpe", json={"date": "2026-10-14", "activity_id": 1, "rpe": 11})
    assert bad.status_code == 422
    ok = client.post("/log-rpe", json={"date": "2026-10-14", "activity_id": 1, "rpe": 8})
    assert ok.status_code == 200
    saved = client.post("/log-wellness", json={
        "date": "2026-10-14",
        "soreness": 2,
        "mood": 4,
        "energy": 3,
        "flank_pain": False,
        "fever": False,
        "blood": False,
        "fluids_l": 1.2,
    })
    assert saved.status_code == 200
    again = client.get("/?date=2026-10-14")
    assert "Short by" in again.text

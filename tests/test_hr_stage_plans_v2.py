"""Haute Route stage plans v2 and peak decoupling flags."""
from datetime import date, timedelta

from ai_endurance_coach_over50.analysis import (
    HR_STAGE_PLAN_CACHE_VER,
    peak_sim_decoupling_flags,
)
from ai_endurance_coach_over50.history import save_activities, save_power_durability


def _cycling_act(d: date, *, power: bool, act_id: int) -> dict:
    return {
        "activity_id": act_id,
        "date": d.isoformat(),
        "type_key": "cycling",
        "has_power_meter": 1 if power else 0,
        "avg_power_w": 200 if power else None,
    }


def _sim_week(week_num: int, start: date) -> dict:
    return {
        "week_num": week_num,
        "start": start,
        "days": [
            {"label": "Rest", "type": "rest"},
            {"label": "Simulation Day 1", "type": "back_to_back"},
            {"label": "Simulation Day 2", "type": "back_to_back"},
            {"label": "Simulation Day 3", "type": "back_to_back"},
        ],
    }


def test_stage_plan_cache_version_is_v2():
    assert HR_STAGE_PLAN_CACHE_VER == "v2"


def test_peak_decoupling_flags_empty_without_power_meter():
    today = date.today()
    weeks = [_sim_week(37, today + timedelta(days=7))]
    assert peak_sim_decoupling_flags(weeks) == {}


def test_peak_decoupling_flags_when_decoupling_elevated():
    today = date.today()
    save_activities([
        _cycling_act(today - timedelta(days=i), power=True, act_id=30 + i)
        for i in range(3)
    ])
    save_power_durability(1, {
        "date": (today - timedelta(days=2)).isoformat(),
        "duration_min": 120,
        "first_third_hr": 140.0,
        "final_third_hr": 155.0,
        "first_third_power": 200.0,
        "final_third_power": 195.0,
        "hr_drift_pct": 10.7,
        "power_drift_pct": -2.5,
        "decoupling_pct": 13.2,
        "n_laps": 6,
    })
    weeks = [_sim_week(37, today + timedelta(days=14))]
    flags = peak_sim_decoupling_flags(weeks)
    assert 37 in flags
    assert "decoupling" in flags[37]["message"].lower()


def test_peak_decoupling_skips_past_weeks():
    today = date.today()
    save_activities([
        _cycling_act(today - timedelta(days=i), power=True, act_id=40 + i)
        for i in range(3)
    ])
    save_power_durability(2, {
        "date": (today - timedelta(days=1)).isoformat(),
        "duration_min": 120,
        "first_third_hr": 140.0,
        "final_third_hr": 155.0,
        "first_third_power": 200.0,
        "final_third_power": 195.0,
        "hr_drift_pct": 10.0,
        "power_drift_pct": -2.0,
        "decoupling_pct": 12.0,
        "n_laps": 6,
    })
    past_start = today - timedelta(days=14)
    weeks = [_sim_week(37, past_start)]
    assert peak_sim_decoupling_flags(weeks) == {}

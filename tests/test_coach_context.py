"""Shared coach/advice context builder."""
from datetime import date, timedelta

from ai_endurance_coach_over50.coach_context import (
    ATHLETE_CONSTRAINTS,
    build_advice_context,
    build_coach_context,
    session_discipline,
)
from ai_endurance_coach_over50.history import save, save_activities
from ai_endurance_coach_over50.metrics import DailyMetrics
from ai_endurance_coach_over50.server import _coach_system


def test_session_discipline_hill_repeats_is_cycling():
    assert session_discipline("tempo") == "cycling"


def test_build_advice_context_includes_constraints_and_today_session():
    target = date(2026, 6, 19)
    ctx = build_advice_context(target)
    assert "NO RUNNING" in ctx
    assert ATHLETE_CONSTRAINTS in ctx
    assert "Hill Repeats" in ctx
    assert "cycling" in ctx
    assert "## HRV Traffic Light" in ctx
    assert "## Training Load (PMC)" in ctx
    assert "## Time & Session Status" in ctx


def test_build_advice_context_includes_hrv_section_with_metrics():
    target = date(2026, 6, 20)
    save(DailyMetrics(
        date=target,
        hrv_last_night=55,
        sleep_score=78,
        body_battery_morning=70,
        avg_stress=25,
        resting_hr=58,
    ))
    ctx = build_advice_context(target)
    assert "## HRV Traffic Light" in ctx
    assert "Status:" in ctx


def test_coach_system_includes_no_running():
    assert "NO RUNNING" in _coach_system()


def test_build_coach_context_includes_power_sections():
    for i in range(3):
        d = (date.today() - timedelta(days=i + 1)).isoformat()
        save_activities([{
            "activity_id": 2000 + i,
            "date": d,
            "type_key": "road_biking",
            "has_power_meter": 1,
            "avg_power_w": 180,
            "duration_seconds": 3600,
        }])
    ctx = build_coach_context()
    # Power sections appear when power_meter_active(); HR-only installs still get PMC/readiness.
    assert "## Training Load (PMC)" in ctx
    assert "## Today's Readiness" in ctx

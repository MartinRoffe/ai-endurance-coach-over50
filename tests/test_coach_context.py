"""Shared coach/advice context builder."""
from datetime import date, timedelta

from ai_endurance_coach_over50.coach_context import (
    ATHLETE_CONSTRAINTS,
    build_advice_context,
    build_coach_context,
    session_discipline,
)
from ai_endurance_coach_over50.history import (
    capture_morning_snapshot,
    save,
    save_activities,
    save_advice,
)
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


def test_coach_system_includes_live_body_battery_guidance():
    prompt = _coach_system()
    assert "Body battery (now)" in prompt
    assert "evening BB alone is not a hard stop" in prompt
    assert "Morning Gate" in prompt


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


def test_build_coach_context_includes_am_and_current_body_battery():
    today = date.today()
    save(DailyMetrics(
        date=today,
        hrv_last_night=53,
        sleep_score=72,
        body_battery_morning=34,
        body_battery_current=5,
        avg_stress=45,
        rest_stress=9,
        resting_hr=58,
        hrv_weekly_avg=49,
        hrv_status="BALANCED",
        training_status_label="Productive 3",
        training_load_acute=384,
        training_load_chronic=583,
        total_steps=8606,
        active_calories=657,
    ))
    ctx = build_coach_context()
    assert "Body battery (AM): 34" in ctx
    assert "Body battery (now): 5" in ctx
    assert "Rest stress: 9" in ctx
    assert "steps 8606" in ctx
    assert "Training status: Productive 3" in ctx


def test_build_coach_context_includes_morning_gate():
    today = date.today()
    m = DailyMetrics(
        date=today,
        hrv_last_night=50,
        sleep_score=80,
        body_battery_morning=70,
        body_battery_current=20,
        resting_hr=55,
    )
    save(m)
    capture_morning_snapshot(
        today,
        m,
        composite_z=0.4,
        readiness_label="Good",
        traffic_light={"status": "green", "reason": "HRV near baseline"},
    )
    save_advice(today, "Train as planned — readiness is solid this morning.", mode="pre")
    ctx = build_coach_context()
    assert "## Morning Gate (locked)" in ctx
    assert "readiness Good" in ctx
    assert "Traffic light: GREEN" in ctx
    assert "Locked advice (excerpt):" in ctx
    assert "Train as planned" in ctx


def test_build_coach_context_recent_activities_include_power_fields():
    d = (date.today() - timedelta(days=1)).isoformat()
    save_activities([{
        "activity_id": 9101,
        "date": d,
        "name": "Z2 Endurance",
        "type_key": "road_biking",
        "has_power_meter": 1,
        "avg_power_w": 150,
        "norm_power_w": 165,
        "tss": 72.5,
        "intensity_factor": 0.72,
        "duration_seconds": 5400,
        "avg_hr": 128,
    }])
    # Need ≥3 power rides for power_meter_active in some paths; still assert line fields.
    for i in range(2):
        save_activities([{
            "activity_id": 9102 + i,
            "date": (date.today() - timedelta(days=i + 2)).isoformat(),
            "type_key": "road_biking",
            "has_power_meter": 1,
            "avg_power_w": 160,
            "duration_seconds": 3600,
        }])
    ctx = build_coach_context()
    assert "NP 165W" in ctx
    assert "TSS 72" in ctx or "TSS 73" in ctx
    assert "IF 0.72" in ctx
    assert "## Power PMC (Coggan TSS)" in ctx

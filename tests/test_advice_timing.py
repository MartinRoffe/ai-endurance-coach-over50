"""Post-workout vs pre-workout advice timing."""
from datetime import date, datetime

from ai_endurance_coach_over50.coach_context import (
    build_advice_context,
    build_advice_timing,
    coach_persona_brief,
)
from ai_endurance_coach_over50.history import save_activities
from ai_endurance_coach_over50.report import _build_advice_prompt
from ai_endurance_coach_over50.metrics import DailyMetrics
from ai_endurance_coach_over50.history import baseline_stats, composite_score


def test_build_advice_timing_pre_workout():
    target = date(2026, 6, 19)
    timing = build_advice_timing(
        target,
        now=datetime(2026, 6, 19, 7, 30),
        today=target,
    )
    assert timing["post_workout"] is False
    assert timing["local_time"] == "07:30"
    assert timing["part_of_day"] == "morning"
    assert timing["session"][1] == "Hill Repeats"
    assert timing["completed"] is False


def test_build_advice_timing_post_workout_when_session_logged():
    target = date(2026, 6, 19)
    save_activities([{
        "activity_id": 88001,
        "date": target.isoformat(),
        "type_key": "road_biking",
        "name": "Hill Repeats",
        "duration_seconds": 3600,
    }])
    timing = build_advice_timing(
        target,
        now=datetime(2026, 6, 19, 18, 0),
        today=target,
    )
    assert timing["completed"] is True
    assert timing["post_workout"] is True
    assert timing["part_of_day"] == "evening"


def test_build_advice_context_shows_post_workout_status():
    target = date(2026, 6, 19)
    save_activities([{
        "activity_id": 88002,
        "date": target.isoformat(),
        "type_key": "road_biking",
        "duration_seconds": 3600,
    }])
    timing = build_advice_timing(
        target,
        now=datetime(2026, 6, 19, 18, 0),
        today=target,
    )
    ctx = build_advice_context(target, timing)
    assert "## Time & Session Status" in ctx
    assert "POST-WORKOUT" in ctx
    assert "COMPLETED today" in ctx
    assert "THIS MORNING before the session" in ctx


def test_build_advice_prompt_post_workout_instructions():
    target = date(2026, 6, 19)
    m = DailyMetrics(date=target, hrv_last_night=50, sleep_score=80)
    stats = baseline_stats(target)
    comp_z = composite_score(m, stats)
    timing = build_advice_timing(
        target,
        now=datetime(2026, 6, 19, 18, 0),
        today=target,
    )
    timing["post_workout"] = True
    prompt = _build_advice_prompt(m, stats, comp_z, timing=timing)
    assert "Local time now: 18:00 (evening)" in prompt
    assert "debriefing today's completed session" in prompt
    assert "Do NOT say 'yesterday'" in prompt
    assert "morning email" not in prompt


def test_coach_persona_brief_post_workout():
    brief = coach_persona_brief(True, post_workout=True)
    assert "ALREADY completed" in brief
    assert "morning pre-session briefing" in brief

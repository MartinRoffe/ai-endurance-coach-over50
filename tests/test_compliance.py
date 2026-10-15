"""Compliance stats follow the live fitness year."""
from datetime import date

from ai_endurance_coach_over50.server.context import _compliance_weeks_unified, _plan_completion_stats


def test_compliance_weeks_are_the_fitness_year():
    weeks = _compliance_weeks_unified()
    assert weeks
    assert all(w["phase"] == "fitness" for w in weeks)
    assert weeks[0]["start"] == date(2026, 10, 12)
    assert weeks[0]["phase_name"] == "Clearance"
    names = [w["phase_name"] for w in weeks if w["phase_start"]]
    assert "Tenerife" in names
    assert "Keswick build" in names
    assert weeks[-1]["days"][-1]["date"] == date(2027, 10, 3)


def test_christmas_ceiling_ride_is_a_session():
    weeks = _compliance_weeks_unified()
    days = {day["date"]: day for w in weeks for day in w["days"]}
    ride = days[date(2026, 12, 26)]
    assert ride["type"] == "long"
    assert ride["dur_min"] == 300


def test_busar_weekend_is_on_the_fitness_calendar():
    weeks = _compliance_weeks_unified()
    days = {day["date"]: day for w in weeks for day in w["days"]}
    assert days[date(2027, 2, 20)]["type"] == "hike"
    assert days[date(2027, 2, 21)]["type"] == "hike"


def test_plan_completion_stats_shape():
    stats = _plan_completion_stats()
    weeks = _compliance_weeks_unified()
    assert "completion_weeks" in stats
    assert len(stats["completion_weeks"]) == len(weeks)
    assert stats["total_plan_sessions"] >= 0
    assert stats["completion_weeks"][0]["phase"] == "fitness"
    assert stats["completion_weeks"][0]["week_num"] is None

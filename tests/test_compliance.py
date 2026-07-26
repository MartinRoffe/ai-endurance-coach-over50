"""Compliance stats include 12-week plan, Tenerife camp, and event-prep blocks."""
from datetime import date

from ai_endurance_coach_over50.plan import CHARITY_DAYS, EVENT_PREP_DAYS, TENERIFE_DAYS
from ai_endurance_coach_over50.server.context import _compliance_weeks_unified, _plan_completion_stats


def test_compliance_weeks_include_all_phases():
    weeks = _compliance_weeks_unified()
    phases = [w["phase"] for w in weeks]
    assert phases.count("plan") == 12
    assert phases.count("camp") == 3
    assert phases.count("event_prep") == 3
    assert phases.count("bridge") == 2
    assert phases[0] == "plan"
    assert "camp" in phases
    assert phases[-1] == "bridge"


def test_camp_ride_days_count_as_sessions():
    weeks = _compliance_weeks_unified()
    camp_weeks = [w for w in weeks if w["phase"] == "camp"]
    camp_ride_dates = {
        d["date"]
        for d in TENERIFE_DAYS
        if d.get("intensity") in ("easy", "medium", "hard")
    }
    camp_session_dates = {
        day["date"]
        for w in camp_weeks
        for day in w["days"]
        if day["type"] != "rest"
    }
    assert camp_ride_dates <= camp_session_dates


def test_event_prep_includes_charity_and_prep_sessions():
    weeks = _compliance_weeks_unified()
    event_weeks = [w for w in weeks if w["phase"] == "event_prep"]
    session_dates = {
        day["date"]
        for w in event_weeks
        for day in w["days"]
        if day["type"] != "rest"
    }
    for ep in EVENT_PREP_DAYS:
        assert ep["date"] in session_dates
    for cd in CHARITY_DAYS:
        assert cd["date"] in session_dates


def test_plan_completion_stats_shape():
    stats = _plan_completion_stats()
    assert "completion_weeks" in stats
    assert len(stats["completion_weeks"]) == 20  # 12 + 3 + 3 + 2 bridge
    assert stats["total_plan_sessions"] >= 0
    first_camp = next(w for w in stats["completion_weeks"] if w["phase"] == "camp")
    assert first_camp["week_label"]
    assert first_camp["week_num"] is None

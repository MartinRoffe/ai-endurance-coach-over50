"""Hard caps after the plan and after an AI suggestion."""
from datetime import date, timedelta

import pytest

from ai_endurance_coach_over50.fit_upload import DEFAULT_FIT_MAX_BYTES
from ai_endurance_coach_over50.history import get_plan_override, set_session_note
from ai_endurance_coach_over50.report import _planned_session_html
from ai_endurance_coach_over50.safety import (
    EASY_ONLY_MAX_MIN,
    MAX_HARD_SESSIONS_PER_WEEK,
    MAX_WEEKLY_LOAD_INCREASE,
    MEDICAL_RETURN_EASY_DAYS,
    MIN_REST_DAYS_PER_WEEK,
    MIN_USEFUL_MIN,
    apply_caps,
    cap_proposal,
    cap_suggested_session,
    prescribed_session,
    weekly_load_reason,
)
from ai_endurance_coach_over50.server import app
from ai_endurance_coach_over50.server.context import _capped_today_plan

MON = date(2026, 6, 1)  # a Monday outside the procedure and return windows


def _week(sessions: list[tuple]) -> list[tuple]:
    return [(MON + timedelta(days=i), sessions[i]) for i in range(7)]


def _rest_week(overrides: dict[int, tuple] | None = None) -> list[tuple]:
    sessions = [("rest", "Rest", 0)] * 7
    for idx, session in (overrides or {}).items():
        sessions[idx] = session
    return _week(sessions)


def test_default_thresholds():
    assert MAX_WEEKLY_LOAD_INCREASE == 0.10
    assert MAX_HARD_SESSIONS_PER_WEEK == 2
    assert MIN_REST_DAYS_PER_WEEK == 1
    assert MEDICAL_RETURN_EASY_DAYS == 7
    assert EASY_ONLY_MAX_MIN == 75
    assert MIN_USEFUL_MIN == 20
    assert DEFAULT_FIT_MAX_BYTES == 20 * 1024 * 1024
    assert weekly_load_reason() == "Capped: +10% weekly load limit"


def test_exactly_ten_percent_is_allowed():
    days = _rest_week({0: ("bike", "Z2 Easy", 110)})
    capped = apply_caps(days, previous_load=100)
    assert capped[0].changed is False
    assert capped[0].session[2] == 110
    assert capped[0].reason is None


def test_just_over_ten_percent_is_trimmed_to_the_budget():
    days = _rest_week({0: ("bike", "Z2 Easy", 111)})
    capped = apply_caps(days, previous_load=100)
    assert capped[0].session[2] == 110
    assert capped[0].reason == "Capped: +10% weekly load limit"


def test_previous_load_of_zero_or_missing_is_not_percentage_capped():
    days = _rest_week({0: ("long", "Long Ride", 500)})
    for previous in (0, None):
        capped = apply_caps(days, previous_load=previous)
        assert capped[0].session[2] == 500
        assert capped[0].reason is None


def test_explicit_tss_over_the_budget_is_trimmed():
    days = _rest_week({0: ("bike", "Z2 Easy", 150)})
    capped = apply_caps(days, previous_load=100, loads={MON: 150.0})
    assert capped[0].changed is True
    assert capped[0].reason == "Capped: +10% weekly load limit"
    assert capped[0].load == pytest.approx(110.0, abs=0.02)


def test_two_non_adjacent_hard_days_stay():
    days = _rest_week({
        0: ("tempo", "Hill Repeats", 60),
        2: ("ftp", "FTP Test", 50),
    })
    capped = apply_caps(days, previous_load=None)
    assert capped[0].session[0] == "tempo"
    assert capped[2].session[0] == "ftp"
    assert all(day.reason is None for day in capped)


def test_third_hard_day_is_demoted():
    days = _rest_week({
        0: ("tempo", "Hill Repeats", 60),
        2: ("ftp", "FTP Test", 50),
        4: ("tempo", "Over-Unders", 45),
    })
    capped = apply_caps(days, previous_load=None)
    assert capped[0].session[0] == "tempo"
    assert capped[2].session[0] == "ftp"
    assert capped[4].session[0] != "tempo"
    assert capped[4].reason == "Capped: 2 hard sessions per week"


def test_back_to_back_hard_days_demote_the_later_day():
    days = _rest_week({
        0: ("tempo", "Hill Repeats", 60),
        1: ("tempo", "Tempo Intervals", 60),
    })
    capped = apply_caps(days, previous_load=None)
    assert capped[0].session[0] == "tempo"
    assert capped[1].session[0] != "tempo"
    assert capped[1].reason == "Capped: no back-to-back hard days"


def test_monday_cannot_follow_a_hard_sunday():
    days = _rest_week({0: ("tempo", "Hill Repeats", 60)})
    capped = apply_caps(
        days,
        previous_load=None,
        previous_day=("tempo", "Hill Repeats", 60),
    )
    assert capped[0].session[0] != "tempo"
    assert capped[0].reason == "Capped: no back-to-back hard days"


def test_a_week_with_no_rest_gains_sunday():
    sessions = [("bike", "Z2 Easy", 40)] * 7
    capped = apply_caps(_week(sessions), previous_load=None)
    rests = [day for day in capped if day.session[0] == "rest"]
    assert len(rests) == 1
    assert rests[0].date == MON + timedelta(days=6)
    assert rests[0].reason == "Capped: at least one rest day per week"
    assert all(day.reason is None for day in capped if day.date != rests[0].date)


def test_clinic_day_does_not_open_a_medical_return_window():
    from ai_endurance_coach_over50.safety import in_easy_return, _procedure_dates

    day = date(2026, 10, 15)
    assert day not in _procedure_dates()
    assert not in_easy_return(day)
    assert not in_easy_return(date(2026, 10, 16))
    assert not in_easy_return(date(2026, 10, 20))
    # A hard suggestion on the first quality Tuesday is not rewritten to easy-only.
    capped = cap_suggested_session(date(2026, 10, 20), ("threshold", "Threshold — bike", 40))
    assert capped.session[0] == "threshold"
    assert capped.reason != "Capped: easy-only return after procedure"


def test_planned_clinic_day_stays_labelled_when_it_is_already_rest():
    capped = prescribed_session(date(2026, 10, 15))
    assert capped.session[1] == "Attended — no treatment"
    assert capped.changed is False
    assert capped.reason is None


def test_clearance_week_tempo_is_not_medical_return():
    # 15 Oct is not a procedure date, so the week after it is not easy-only.
    capped = cap_suggested_session(date(2026, 10, 16), ("tempo", "Hill Repeats", 60))
    assert capped.reason != "Capped: easy-only return after procedure"
    assert capped.reason != "Capped: rest on procedure day"


def test_return_window_after_stent_removal_is_easy_only():
    # Stent removal is 8 Sep 2026; the next seven days are easy-only.
    capped = cap_suggested_session(date(2026, 9, 10), ("vo2", "VO2 Intervals", 90))
    assert capped.session[0] != "vo2"
    assert capped.session[2] <= EASY_ONLY_MAX_MIN
    assert "easy-only" in (capped.reason or "")


def test_logged_red_flag_symptom_forces_rest():
    set_session_note("2026-06-16", "Woke with flank pain and a fever.")
    capped = prescribed_session(date(2026, 6, 16))
    assert capped.session == ("rest", "Rest", 0)
    assert capped.reason == "Capped: red-flag symptoms — rest"


def test_illness_gate_forces_rest(monkeypatch):
    monkeypatch.setattr(
        "ai_endurance_coach_over50.modulation._illness_triggers",
        lambda _day: (["HRV", "sleep"], True),
    )
    capped = prescribed_session(date(2026, 6, 17))
    assert capped.session[0] == "rest"
    assert capped.reason == "Capped: red-flag symptoms — rest"


def test_ai_proposal_over_the_caps_is_rewritten():
    out = cap_proposal({
        "date": "2026-06-20",
        "session_type": "tempo",
        "session_label": "Tempo Intervals",
        "duration_min": 75,
        "reason": "Athlete asked for a hard Saturday",
    })
    assert out["session_type"] != "tempo"
    assert "back-to-back" in out["safety_line"]
    assert "Capped:" in out["reason"]


def test_ai_proposal_inside_the_caps_is_unchanged():
    proposal = {
        "date": "2026-06-19",
        "session_type": "bike",
        "session_label": "Z2 Ride",
        "duration_min": 60,
        "reason": "Keep it aerobic",
    }
    assert cap_proposal(proposal) == proposal


def test_week_five_long_ride_is_capped_on_the_dashboard_and_in_the_email():
    plan, line = _capped_today_plan(
        date(2026, 6, 21),
        {"type": "long", "label": "Long Ride", "dur_fmt": "2h15m", "icon": "🚴"},
        None,
        {},
    )
    assert line == "Capped: +10% weekly load limit"
    assert plan["label"] != "Long Ride"
    assert plan["type"] == "rest"

    email = _planned_session_html(date(2026, 6, 21))
    assert "Capped: +10% weekly load limit" in email
    assert "Long Ride" not in email


def test_apply_plan_change_persists_the_capped_session(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("GARMIN_EMAIL", "")
    monkeypatch.setenv("GARMIN_PASSWORD", "")
    monkeypatch.delenv("DASHBOARD_USER", raising=False)
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    res = TestClient(app).post("/apply-plan-change", json={
        "date": "2026-06-20",
        "duration_min": 75,
        "reason": "Add a hard Saturday",
        "session_type": "tempo",
        "label": "Tempo Intervals",
    })
    assert res.status_code == 200
    body = res.json()
    assert body["session_type"] != "tempo"
    assert "back-to-back" in body["safety_line"]
    saved = get_plan_override("2026-06-20")
    assert saved["session_type"] != "tempo"
    assert "Capped:" in saved["note"]

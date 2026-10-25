"""No rower: weekday rower sessions become a shorter MaxiClimber session."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from ai_endurance_coach_over50.coach_voice import equipment_note
from ai_endurance_coach_over50.fitness_plan import (
    PLAN_END,
    PLAN_START,
    garmin_allowed,
    session_for_date,
)
from ai_endurance_coach_over50.report import _planned_session_html
from ai_endurance_coach_over50.safety import prescribed_session
from ai_endurance_coach_over50.server import app
from ai_endurance_coach_over50.session_detail import day_detail
from ai_endurance_coach_over50.settings import has_rower
from ai_endurance_coach_over50.workouts import _workout_schedule_row, _workouts_for_date


def _days():
    d = PLAN_START
    while d <= PLAN_END:
        yield d
        d += timedelta(days=1)


def test_has_rower_defaults_off():
    assert has_rower() is False


def test_tuesday_20_oct_is_a_shorter_maxiclimber_threshold():
    assert session_for_date(date(2026, 10, 20)) == (
        "maxiclimber", "Threshold — MaxiClimber", 30,
    )
    detail = day_detail(date(2026, 10, 20))
    text = " ".join(
        [detail["title"], detail["purpose"], detail["rpe_target"]]
        + [b["detail"] for b in detail["blocks"]]
    )
    assert "MaxiClimber" in detail["title"]
    assert "rower" not in text.lower()
    assert "5 × 4 min" not in text
    assert "RPE 7" in text
    assert detail["garmin"] is False
    assert not garmin_allowed(date(2026, 10, 20), detail["type"], detail["title"])
    assert _workouts_for_date(date(2026, 10, 20)) == []


def test_email_for_20_oct_shows_the_shorter_maxiclimber():
    html = _planned_session_html(date(2026, 10, 20))
    assert "Threshold — MaxiClimber" in html
    assert "Threshold — rower" not in html
    assert ">30m</span>" in html


def test_agreed_maxiclimber_days_are_not_shortened_again():
    assert session_for_date(date(2026, 10, 27)) == (
        "maxiclimber", "Threshold — MaxiClimber", 40,
    )
    assert session_for_date(date(2026, 10, 29)) == (
        "maxiclimber", "Z2 — MaxiClimber", 30,
    )
    assert session_for_date(date(2026, 11, 1))[2] == 85


def test_sunday_1_nov_is_not_trimmed_by_the_shorter_tuesday():
    """The MaxiClimber swap is equipment, not a deload, so the cap holds 85."""
    cap = prescribed_session(date(2026, 11, 1))
    assert cap.session[2] == 85
    assert cap.reason is None


def test_camp_quality_day_is_a_shorter_maxiclimber_and_not_pushed():
    # 180 min rower threshold → 135 min on the MaxiClimber.
    assert session_for_date(date(2026, 12, 23)) == (
        "maxiclimber", "Threshold — MaxiClimber", 135,
    )
    assert _workouts_for_date(date(2026, 12, 23)) == []


def test_sandbag_day_keeps_the_lift_and_shortens_only_the_cardio():
    # 30 min of cardio becomes 25; the 20 min of lifting stays. 25 + 20 = 45.
    sess = session_for_date(date(2027, 1, 5))
    assert sess == ("maxiclimber", "Threshold — MaxiClimber, then sandbag", 45)
    detail = day_detail(date(2027, 1, 5))
    blob = " ".join(
        [detail["purpose"]] + [b["detail"] for b in detail["blocks"]]
    ).lower()
    assert "maxiclimber" in blob
    assert "damper" not in blob
    assert "500 m" not in blob
    assert "sandbag" in blob


def test_no_rower_session_is_shown_anywhere_in_the_plan_year():
    for d in _days():
        sess = session_for_date(d)
        if not sess:
            continue
        assert sess[0] != "rower", (d, sess)
        assert "rower" not in sess[1].lower(), (d, sess)


def test_has_rower_restores_the_rower_session(monkeypatch):
    monkeypatch.setattr("ai_endurance_coach_over50.settings.HAS_ROWER", True)
    assert session_for_date(date(2026, 10, 20)) == ("rower", "Threshold — rower", 40)
    assert _workouts_for_date(date(2026, 10, 20)) == [("row", "Threshold — rower", 40)]
    assert session_for_date(date(2026, 12, 23)) == ("rower", "Threshold — rower", 180)
    assert session_for_date(date(2027, 1, 5)) == (
        "rower", "Threshold — rower, then sandbag", 50,
    )
    row_dates = {d for ds in _workout_schedule_row().values() for d in ds}
    assert "2026-10-20" in row_dates
    assert "2026-12-23" in row_dates
    assert "2026-12-30" in row_dates


def test_training_page_says_there_is_no_rower():
    page = TestClient(app).get("/training")
    assert page.status_code == 200
    assert "no rower" in page.text.lower()
    assert "on the rower" not in page.text.lower()


def test_equipment_note_says_maxiclimber_when_there_is_no_rower():
    note = equipment_note(False)
    assert "NO turbo" in note
    assert "MaxiClimber" in note
    assert "no rower" in note.lower()
    assert "indoor rower" not in note.lower()
    restored = equipment_note(False, has_rower=True)
    assert "indoor rower" in restored

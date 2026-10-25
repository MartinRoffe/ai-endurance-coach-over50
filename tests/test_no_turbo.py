"""No turbo trainer: weekday bikes leave the bike; weekends stay outdoors.

With no rower either, those weekday sessions are a shorter MaxiClimber session.
The rower wording below is what comes back when HAS_ROWER is turned on.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from ai_endurance_coach_over50.fitness_plan import (
    PLAN_END,
    PLAN_START,
    garmin_allowed,
    session_for_date,
)
from ai_endurance_coach_over50.session_detail import day_detail
from ai_endurance_coach_over50.settings import has_turbo
from ai_endurance_coach_over50.workouts import _build_row_workout, _workouts_for_date

ROOT = Path(__file__).resolve().parents[1]
_BIKE_TYPES = {
    "bike", "long", "endurance", "tempo", "sweetspot", "ftp",
    "recovery", "threshold", "vo2", "back_to_back",
}
_BANNED = re.compile(r"\b(turbo|rouvy|erg|indoor trainer|indoor-trainer)\b", re.I)


def _days():
    d = PLAN_START
    while d <= PLAN_END:
        yield d
        d += timedelta(days=1)


def test_has_turbo_defaults_off():
    assert has_turbo() is False


def test_no_weekday_bike_in_the_plan_year():
    for d in _days():
        if d.weekday() >= 5:
            continue
        sess = session_for_date(d)
        if not sess:
            continue
        stype, label, _dur = sess
        low = label.lower()
        assert stype not in _BIKE_TYPES, (d, sess)
        assert "bike" not in low, (d, sess)
        assert "long ride" not in low, (d, sess)


def test_tuesday_20_oct_is_a_rower_threshold_when_the_rower_is_available(monkeypatch):
    monkeypatch.setattr("ai_endurance_coach_over50.settings.HAS_ROWER", True)
    assert session_for_date(date(2026, 10, 20)) == ("rower", "Threshold — rower", 40)
    detail = day_detail(date(2026, 10, 20))
    text = " ".join(
        [detail["title"], detail["purpose"], detail["hr_target"], detail["rpe_target"]]
        + [b["detail"] for b in detail["blocks"]]
    )
    assert "2 × 8 min" in text
    assert "7–8" in text
    assert "160" in text and "167" in text
    assert "500 m" in text
    assert "2,000 m" in text
    assert "20-minute" in text
    assert detail["garmin"] is True
    assert detail["garmin_text"] == "Pushed to Garmin"
    assert garmin_allowed(date(2026, 10, 20), detail["type"], detail["title"])


def test_weekend_rides_are_outdoor_and_say_nothing_about_a_trainer():
    for d in _days():
        if d.weekday() < 5:
            continue
        sess = session_for_date(d)
        if not sess:
            continue
        stype, label, _dur = sess
        if stype not in {"bike", "long", "endurance", "threshold", "vo2"}:
            continue
        assert "outdoor" in label.lower(), (d, sess)
        detail = day_detail(d)
        blob = " ".join(
            [label, detail.get("purpose") or "", detail.get("title") or ""]
            + [b.get("detail") or "" for b in detail.get("blocks") or []]
        )
        assert not _BANNED.search(blob), (d, blob)


def test_sunday_25_oct_outdoor_guidance():
    sess = session_for_date(date(2026, 10, 25))
    assert sess[0] == "long"
    assert sess[1].endswith("· outdoor")
    detail = day_detail(date(2026, 10, 25))
    purpose = detail["purpose"].lower()
    assert "outdoor" in purpose
    assert "assioma" in purpose
    assert "lights" in purpose
    assert "rower or maxiclimber" in purpose
    assert not _BANNED.search(purpose)


def test_has_turbo_restores_the_weekday_bike(monkeypatch):
    monkeypatch.setattr("ai_endurance_coach_over50.settings.HAS_TURBO", True)
    assert session_for_date(date(2026, 10, 20)) == ("threshold", "Threshold — bike", 40)


def test_tuesday_20_oct_pushes_as_cardio_not_power(monkeypatch):
    monkeypatch.setattr("ai_endurance_coach_over50.settings.HAS_ROWER", True)
    assert _workouts_for_date(date(2026, 10, 20)) == [("row", "Threshold — rower", 40)]
    workout = _build_row_workout("Threshold — rower", 40)
    assert workout is not None
    assert workout.sportType["sportTypeKey"] == "cardio_training"
    assert workout.workoutName.startswith("Row Threshold ")
    steps = workout.workoutSegments[0].workoutSteps
    keys = [s.targetType.get("workoutTargetTypeKey") for s in steps]
    assert "power.zone" not in keys
    assert "heart.rate.zone" in keys
    assert not _BANNED.search(workout.description or "")
    sunday = _workouts_for_date(date(2026, 10, 18))
    assert sunday == [("bike", "Long Ride (Easy)", 60)]


def test_served_plan_docs_do_not_name_a_trainer():
    paths = [
        ROOT / "docs/plans/fitness-2026-27.md",
        ROOT / "docs/plans/Mountain & Road Build.md",
        ROOT / "docs/tabs/plan.md",
        ROOT / "ai_endurance_coach_over50/templates/fitness_guide.html",
        ROOT / "ai_endurance_coach_over50/templates/hr_calendar.html",
        ROOT / "ai_endurance_coach_over50/templates/hr_power_protocol.html",
        ROOT / "ai_endurance_coach_over50/templates/position.html",
    ]
    for path in paths:
        text = path.read_text()
        assert not _BANNED.search(text), path.name

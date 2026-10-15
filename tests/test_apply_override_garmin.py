"""apply_override_to_garmin reports truthful ok from schedule outcomes."""
from datetime import date
from unittest.mock import MagicMock

from ai_endurance_coach_over50.workouts import apply_override_to_garmin


def test_ok_false_when_push_fails_even_if_fetch_worked(monkeypatch):
    api = MagicMock()
    api.get_scheduled_workouts.return_value = []

    monkeypatch.setattr(
        "ai_endurance_coach_over50.workouts._workouts_for_date",
        lambda d: [("bike", "Z2 Easy", 45)],
    )

    class _W:
        workoutName = "Z2 Endurance 45m"

    monkeypatch.setattr(
        "ai_endurance_coach_over50.workouts._resolve_builder",
        lambda label: (lambda dur: _W()),
    )
    monkeypatch.setattr(
        "ai_endurance_coach_over50.workouts._push_one_workout",
        lambda *a, **k: None,
    )

    result = apply_override_to_garmin(api, date(2026, 10, 21).isoformat())
    assert result["expected"] == 1
    assert result["scheduled"] == 0
    assert result["ok"] is False
    assert result["error"]
    assert "upload/schedule failed" in result["error"]


def test_ok_true_when_schedule_succeeds(monkeypatch):
    api = MagicMock()
    api.get_scheduled_workouts.return_value = []

    monkeypatch.setattr(
        "ai_endurance_coach_over50.workouts._workouts_for_date",
        lambda d: [("bike", "Threshold — bike", 40)],
    )

    class _W:
        workoutName = "Threshold Ride 40m"

    monkeypatch.setattr(
        "ai_endurance_coach_over50.workouts._resolve_builder",
        lambda label: (lambda dur: _W()),
    )
    monkeypatch.setattr(
        "ai_endurance_coach_over50.workouts._push_one_workout",
        lambda *a, **k: 12345,
    )

    result = apply_override_to_garmin(api, date(2026, 10, 27).isoformat())
    assert result["expected"] == 1
    assert result["scheduled"] == 1
    assert result["ok"] is True
    assert result["error"] is None


def test_ok_true_for_rest_day_unschedule_only(monkeypatch):
    api = MagicMock()
    api.get_scheduled_workouts.return_value = [
        {"workoutScheduleId": 9, "workoutName": "Z2 Endurance 45m", "date": "2026-10-15"},
    ]
    monkeypatch.setattr(
        "ai_endurance_coach_over50.workouts._scheduled_items_on",
        lambda sched, date_str: [(9, "Z2 Endurance 45m")],
    )
    monkeypatch.setattr(
        "ai_endurance_coach_over50.workouts._workouts_for_date",
        lambda d: [],
    )

    result = apply_override_to_garmin(api, "2026-10-15")
    assert result["expected"] == 0
    assert result["scheduled"] == 0
    assert result["unscheduled"] == 1
    assert result["ok"] is True
    api.unschedule_workout.assert_called_once_with(9)


def test_ok_false_when_fetch_fails(monkeypatch):
    api = MagicMock()
    api.get_scheduled_workouts.side_effect = RuntimeError("auth expired")
    monkeypatch.setattr(
        "ai_endurance_coach_over50.workouts._workouts_for_date",
        lambda d: [],
    )

    result = apply_override_to_garmin(api, "2026-10-21")
    assert result["ok"] is False
    assert "fetch scheduled failed" in result["error"]

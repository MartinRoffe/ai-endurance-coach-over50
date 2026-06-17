"""Tests for the HRV traffic light and session modulation in modulation.py."""
from datetime import date, timedelta

import pytest

import ai_endurance_coach_over50.modulation as modulation
from ai_endurance_coach_over50.metrics import DailyMetrics
from ai_endurance_coach_over50.modulation import (
    durability_gate,
    hrv_traffic_light,
    recovery_gate,
    resolve_modulation,
    session_modulation,
)

TODAY = date(2026, 6, 10)


def _baseline_rows(end=TODAY, include_today=False, **today_overrides):
    """30 days alternating 58/62 ms → mean 60, pstdev 2."""
    rows = []
    start = end - timedelta(days=30)
    for i in range(30):
        rows.append({
            "date": (start + timedelta(days=i)).isoformat(),
            "hrv_last_night": 58.0 if i % 2 else 62.0,
            "resting_hr": 52.0 if i % 2 else 50.0,
            "sleep_score": 80.0 if i % 2 else 82.0,
            "rest_stress": 20.0 if i % 2 else 18.0,
        })
    if include_today:
        row = {"date": end.isoformat(), "hrv_last_night": 999.0,
               "resting_hr": 50.0, "sleep_score": 80.0, "rest_stress": 18.0}
        row.update(today_overrides)
        rows.append(row)
    return rows


def _metrics(hrv, **kwargs):
    return DailyMetrics(date=TODAY, hrv_last_night=hrv, **kwargs)


@pytest.fixture(autouse=True)
def patched_history(monkeypatch):
    monkeypatch.setattr(modulation, "raw_history", lambda days=31: _baseline_rows())
    monkeypatch.setattr(modulation, "get_plan_override", lambda d: None)
    monkeypatch.setattr(modulation, "session_for_date_extended", lambda d: None)
    monkeypatch.setattr(modulation, "load_session_rpe", lambda days=14: [])
    monkeypatch.setattr(modulation, "load_durability", lambda days=180: [])
    monkeypatch.setattr(modulation, "load_btb_summary", lambda: [])


# ── hrv_traffic_light ────────────────────────────────────────────────────────

def test_red_when_hrv_far_below_baseline():
    light = hrv_traffic_light(_metrics(40.0), comp_z=None)  # z = -10
    assert light["status"] == "red"


def test_amber_when_hrv_moderately_below():
    light = hrv_traffic_light(_metrics(58.0), comp_z=None)  # z = -1.0
    assert light["status"] == "amber"


def test_green_when_hrv_normal():
    light = hrv_traffic_light(_metrics(60.0), comp_z=None)  # z = 0
    assert light["status"] == "green"


def test_unknown_without_history_or_composite():
    light = hrv_traffic_light(DailyMetrics(date=TODAY), comp_z=None)
    assert light["status"] == "unknown"


def test_baseline_excludes_todays_own_row(monkeypatch):
    # A 999 ms row for today must not pollute the baseline (it duplicates m)
    monkeypatch.setattr(modulation, "raw_history",
                        lambda days=31: _baseline_rows(include_today=True))
    light = hrv_traffic_light(_metrics(40.0), comp_z=None)
    assert light["status"] == "red"
    assert light["hrv_z"] == pytest.approx(-10.0)


def test_composite_backstop_turns_amber():
    light = hrv_traffic_light(_metrics(60.0), comp_z=-0.8)  # HRV fine, composite low
    assert light["status"] == "amber"


# ── session_modulation ───────────────────────────────────────────────────────

def _light(status):
    return {"status": status, "hrv_z": None, "ratio": None, "reason": "test"}


def test_red_swaps_to_recovery_spin(monkeypatch):
    monkeypatch.setattr(modulation, "session_for_date_extended",
                        lambda d: ("tempo", "Tempo Intervals", 75))
    mod = session_modulation(TODAY, _metrics(40.0), None, light=_light("red"))
    assert (mod["session_type"], mod["label"], mod["duration_min"]) == ("bike", "Recovery Spin", 30)


def test_amber_keeps_duration_drops_intensity(monkeypatch):
    monkeypatch.setattr(modulation, "session_for_date_extended",
                        lambda d: ("tempo", "Tempo Intervals", 75))
    mod = session_modulation(TODAY, _metrics(58.0), None, light=_light("amber"))
    assert (mod["session_type"], mod["label"], mod["duration_min"]) == ("bike", "Zone 2 Steady", 75)


def test_green_returns_none(monkeypatch):
    monkeypatch.setattr(modulation, "session_for_date_extended",
                        lambda d: ("tempo", "Tempo Intervals", 75))
    assert session_modulation(TODAY, _metrics(60.0), None, light=_light("green")) is None


def test_existing_override_suppresses_suggestion(monkeypatch):
    monkeypatch.setattr(modulation, "session_for_date_extended",
                        lambda d: ("tempo", "Tempo Intervals", 75))
    monkeypatch.setattr(modulation, "get_plan_override",
                        lambda d: {"label": "already decided"})
    assert session_modulation(TODAY, _metrics(40.0), None, light=_light("red")) is None


def test_rest_day_amber_shows_pill_without_swap(monkeypatch):
    monkeypatch.setattr(modulation, "session_for_date_extended",
                        lambda d: ("rest", "Rest", 0))
    mod = session_modulation(TODAY, _metrics(58.0), None, light=_light("amber"))
    assert mod is not None
    assert "label" not in mod  # no swap proposed, just the status pill


# ── Haute Route plan fallback ────────────────────────────────────────────────
# session_for_date_extended is stubbed to None by the autouse fixture, so these
# exercise the hr_session_for_date fallback path.

def test_hr_amber_vo2_swaps_to_z2_endurance(monkeypatch):
    monkeypatch.setattr(modulation, "hr_session_for_date",
                        lambda d: ("vo2", "VO2 Intervals 5×3 min", 60))
    mod = session_modulation(TODAY, _metrics(58.0), None, light=_light("amber"))
    assert (mod["session_type"], mod["label"], mod["duration_min"]) == ("endurance", "Z2 Endurance", 60)


def test_hr_amber_back_to_back_swaps_to_easy_long(monkeypatch):
    monkeypatch.setattr(modulation, "hr_session_for_date",
                        lambda d: ("back_to_back", "Back-to-Back Day 1", 240))
    mod = session_modulation(TODAY, _metrics(58.0), None, light=_light("amber"))
    assert (mod["session_type"], mod["label"], mod["duration_min"]) == ("long", "Long Ride (Easy)", 240)


def test_hr_red_swaps_to_recovery_type(monkeypatch):
    # HR vocabulary: red uses type "recovery", not the 12-week plan's "bike"
    monkeypatch.setattr(modulation, "hr_session_for_date",
                        lambda d: ("sweetspot", "Low Cadence Sweetspot", 90))
    mod = session_modulation(TODAY, _metrics(40.0), None, light=_light("red"))
    assert (mod["session_type"], mod["label"], mod["duration_min"]) == ("recovery", "Recovery Spin", 30)


def test_hr_amber_recovery_session_shows_pill_only(monkeypatch):
    monkeypatch.setattr(modulation, "hr_session_for_date",
                        lambda d: ("recovery", "Strength + Core", 60))
    mod = session_modulation(TODAY, _metrics(58.0), None, light=_light("amber"))
    assert mod is not None
    assert "label" not in mod


def test_hr_amber_already_easy_shows_pill_only(monkeypatch):
    monkeypatch.setattr(modulation, "hr_session_for_date",
                        lambda d: ("endurance", "Z2 Easy", 45))
    mod = session_modulation(TODAY, _metrics(58.0), None, light=_light("amber"))
    assert mod is not None
    assert "label" not in mod


# ── recovery_gate ────────────────────────────────────────────────────────────

def _illness_rows():
    """Today's row included with 2-of-3 illness triggers."""
    rows = _baseline_rows()
    rows.append({
        "date": TODAY.isoformat(),
        "hrv_last_night": 40.0,
        "resting_hr": 65.0,
        "sleep_score": 80.0,
        "rest_stress": 18.0,
    })
    return rows


def test_illness_gate_prescribes_rest(monkeypatch):
    monkeypatch.setattr(modulation, "raw_history", lambda days=31: _illness_rows())
    monkeypatch.setattr(modulation, "session_for_date_extended",
                        lambda d: ("tempo", "Tempo Intervals", 75))
    gate = recovery_gate(TODAY, _metrics(40.0), None, light=_light("green"))
    assert gate["gate_type"] == "illness"
    assert gate["session_type"] == "rest"
    assert gate["label"] == "Rest (illness signals)"


def test_illness_gate_wins_over_green_hrv(monkeypatch):
    monkeypatch.setattr(modulation, "raw_history", lambda days=31: _illness_rows())
    monkeypatch.setattr(modulation, "session_for_date_extended",
                        lambda d: ("tempo", "Tempo Intervals", 75))
    light, mod = resolve_modulation(TODAY, _metrics(60.0), None)
    assert mod["gate_type"] == "illness"
    assert mod["session_type"] == "rest"


def test_illness_gate_suppresses_hrv_red_spin(monkeypatch):
    monkeypatch.setattr(modulation, "raw_history", lambda days=31: _illness_rows())
    monkeypatch.setattr(modulation, "session_for_date_extended",
                        lambda d: ("tempo", "Tempo Intervals", 75))
    light, mod = resolve_modulation(TODAY, _metrics(40.0), None)
    assert mod["gate_type"] == "illness"
    assert mod["label"] != "Recovery Spin"


def test_rhr_early_amber_when_hrv_green(monkeypatch):
    rows = _baseline_rows()
    rows.append({
        "date": TODAY.isoformat(),
        "hrv_last_night": 60.0,
        "resting_hr": 70.0,
        "sleep_score": 80.0,
        "rest_stress": 18.0,
    })
    monkeypatch.setattr(modulation, "raw_history", lambda days=31: rows)
    monkeypatch.setattr(modulation, "session_for_date_extended",
                        lambda d: ("tempo", "Tempo Intervals", 75))
    gate = recovery_gate(TODAY, _metrics(60.0), None, light=_light("green"))
    assert gate["gate_type"] == "rhr_early"
    assert gate["label"] == "Zone 2 Steady"


def test_hrv_trend_drops_quality_session(monkeypatch):
    rows = []
    start = TODAY - timedelta(days=4)
    for i, hrv in enumerate([70.0, 65.0, 60.0, 55.0, 50.0]):
        rows.append({
            "date": (start + timedelta(days=i)).isoformat(),
            "hrv_last_night": hrv,
            "resting_hr": 50.0,
            "sleep_score": 80.0,
            "rest_stress": 18.0,
        })
    monkeypatch.setattr(modulation, "raw_history", lambda days=31: rows)
    monkeypatch.setattr(modulation, "session_for_date_extended",
                        lambda d: ("tempo", "Tempo Intervals", 75))
    gate = recovery_gate(TODAY, _metrics(50.0), None, light=_light("green"))
    assert gate["gate_type"] == "hrv_trend"
    assert gate["label"] == "Zone 2 Steady"


def test_rpe_amber_eases_intensity(monkeypatch):
    monkeypatch.setattr(modulation, "load_session_rpe", lambda days=7: [{"rpe": 5}])
    monkeypatch.setattr(modulation, "session_for_date_extended",
                        lambda d: ("tempo", "Tempo Intervals", 75))
    gate = recovery_gate(TODAY, _metrics(58.0), None, light=_light("amber"))
    assert gate["gate_type"] == "rpe_amber"
    assert gate["label"] == "Zone 2 Steady"


# ── durability_gate ──────────────────────────────────────────────────────────

def test_durability_gate_before_week_9_returns_none(monkeypatch):
    monkeypatch.setattr(modulation, "session_for_date_extended",
                        lambda d: ("long", "Long Ride", 240))
    gate = durability_gate(date(2026, 7, 10), _metrics(60.0), None, light=_light("green"))
    assert gate is None


def test_durability_gate_eases_long_ride(monkeypatch):
    monkeypatch.setattr(modulation, "session_for_date_extended",
                        lambda d: ("long", "Long Ride", 240))
    monkeypatch.setattr(modulation, "load_durability", lambda days=180: [{
        "date": "2026-07-10", "drift_pct": 12.0,
        "first_third_hr": 130.0, "final_third_hr": 145.0,
    }])
    gate = durability_gate(date(2026, 7, 28), _metrics(60.0), None, light=_light("green"))
    assert gate["gate_type"] == "durability"
    assert gate["label"] == "Long Ride (Easy)"

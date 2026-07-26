"""One-verdict dashboard: _build_today_verdict collapses gates into a single answer."""
from datetime import date

from ai_endurance_coach_over50.server.context import _build_today_verdict

_PLAN = {
    "type": "long", "label": "Long Ride", "dur_fmt": "4h15",
    "icon": "🚴", "compound": None, "note": None,
}
_MOD = {
    "session_type": "bike", "label": "Long Ride (Easy)", "duration_min": 255,
    "headline": "Amber day — keep duration, drop intensity", "reason": "HRV z −0.9",
    "planned_label": "Long Ride", "date": "2026-07-26",
}


def test_green_day_session_as_planned():
    v = _build_today_verdict(
        date(2026, 7, 26), _PLAN, {"status": "green", "reason": "ok"}, None, False
    )
    assert v["status"] == "green"
    assert v["final_session"]["changed"] is False
    assert v["final_session"]["label"] == "Long Ride"
    assert v["apply"] is None


def test_amber_modulation_offers_apply():
    v = _build_today_verdict(
        date(2026, 7, 26), _PLAN, {"status": "amber", "reason": "HRV low"}, _MOD, False
    )
    assert v["status"] == "amber"
    assert v["final_session"]["changed"] is True
    assert v["final_session"]["label"] == "Long Ride (Easy)"
    assert v["final_session"]["from_label"] == "Long Ride"
    assert v["apply"]["session_type"] == "bike"
    assert v["apply"]["date"] == "2026-07-26"


def test_illness_gate_forces_red_rest():
    gate = {
        **_MOD, "gate": True, "gate_type": "illness", "session_type": "rest",
        "label": "Rest (illness signals)", "duration_min": 0,
        "headline": "Illness signals — rest today",
    }
    v = _build_today_verdict(
        date(2026, 7, 26), _PLAN, {"status": "green", "reason": "ok"}, gate, False
    )
    assert v["status"] == "red"
    assert v["final_session"]["label"] == "Rest (illness signals)"


def test_post_workout_suppresses_swap_and_apply():
    v = _build_today_verdict(
        date(2026, 7, 26), _PLAN, {"status": "amber", "reason": "x"}, _MOD, True
    )
    assert v["final_session"]["changed"] is False
    assert v["apply"] is None


def test_rest_day_without_plan():
    v = _build_today_verdict(
        date(2026, 8, 1), None, {"status": "green", "reason": "ok"}, None, False
    )
    assert v["final_session"]["type"] == "rest"


def test_swap_hint_only_without_modulation():
    hint_sw = {"from_label": "Long Ride", "to_date_str": "28 Jul",
               "to_label": "Z2 Endurance", "severity": "moderate"}
    v = _build_today_verdict(
        date(2026, 7, 26), _PLAN, {"status": "green", "reason": "ok"}, None, False, hint_sw
    )
    assert v["hint"] and "Z2 Endurance" in v["hint"]
    v2 = _build_today_verdict(
        date(2026, 7, 26), _PLAN, {"status": "amber", "reason": "x"}, _MOD, False, hint_sw
    )
    assert v2["hint"] is None

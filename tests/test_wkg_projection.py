"""Tests for the pure W/kg projection module and the goal settings round-trip."""
from datetime import date, timedelta
from math import log

import pytest

from ai_endurance_coach_over50.wkg_projection import (
    CONSERVATIVE_CEILING_W,
    STRETCH_CEILING_W,
    WEIGHT_HALF_LIFE_DAYS,
    _ftp_anchor,
    build_wkg_path,
    performance_guard,
    project_ftp_w,
    project_weight_kg,
)
from ai_endurance_coach_over50.history import (
    load_wkg_goal,
    save_ftp_test,
    save_wkg_goal,
)


# ── project_weight_kg ────────────────────────────────────────────────────────

def test_project_weight_slope_none_is_flat():
    assert project_weight_kg(91.5, None, 365) == 91.5


def test_project_weight_asymptote():
    w0, slope = 91.5, -0.05
    tau = WEIGHT_HALF_LIFE_DAYS / log(2)
    expected_asymptote = w0 + slope * tau
    far = project_weight_kg(w0, slope, 20000)
    assert far == pytest.approx(expected_asymptote, abs=0.05)


def test_project_weight_decelerates():
    w0, slope = 91.5, -0.05
    loss_month1 = w0 - project_weight_kg(w0, slope, 30)
    loss_month13 = project_weight_kg(w0, slope, 360) - project_weight_kg(w0, slope, 390)
    assert loss_month1 > loss_month13 > 0


def test_project_weight_no_floor_clamp():
    # A steep slope drives the asymptote well below any naive fixed floor (e.g. 75).
    w0, slope = 91.5, -0.12
    far = project_weight_kg(w0, slope, 20000)
    assert far < 75.0


# ── project_ftp_w ────────────────────────────────────────────────────────────

def test_project_ftp_t0_is_ftp0():
    assert project_ftp_w(190, CONSERVATIVE_CEILING_W, 0) == 190


def test_project_ftp_approaches_ceiling():
    assert project_ftp_w(190, STRETCH_CEILING_W, 100000) == STRETCH_CEILING_W


def test_project_ftp_above_ceiling_never_declines():
    # ftp0 above the scenario ceiling: effective ceiling is ftp0+10, so it rises.
    at0 = project_ftp_w(310, STRETCH_CEILING_W, 0)
    later = project_ftp_w(310, STRETCH_CEILING_W, 200)
    assert at0 == 310
    assert later >= 310


# ── _ftp_anchor ──────────────────────────────────────────────────────────────

def test_ftp_anchor_picks_newest_watt_bearing():
    tests = [
        {"date": "2026-01-01", "ftp_w": 180},
        {"date": "2026-03-01", "ftp_w": None},
        {"date": "2026-05-01", "ftp_w": 195},
    ]
    assert _ftp_anchor(tests) == ("2026-05-01", 195)


def test_ftp_anchor_none_when_no_watts():
    assert _ftp_anchor([{"date": "2026-01-01", "ftp_w": None}]) is None
    assert _ftp_anchor([]) is None


# ── build_wkg_path ───────────────────────────────────────────────────────────

def test_build_wkg_path_end_to_end():
    today = date(2026, 7, 7)
    path = build_wkg_path(
        anchor_date_iso="2026-07-01",
        anchor_ftp_w=190,
        latest_weight_kg=91.5,
        weight_slope_kg_per_day=-0.05,
        target_wkg=4.0,
        target_date_iso="2027-08-23",
        today=today,
    )
    assert path is not None
    pts = path["points"]
    assert pts[0]["date"] == today.isoformat()
    assert pts[-1]["date"] == "2027-08-23"
    # race weight is projected/dynamic, not a fixed 78 kg
    assert path["race_weight_kg"] != 78.0
    assert path["race_weight_kg"] < 91.5
    assert path["required_ftp_w"] == round(4.0 * path["race_weight_kg"])
    # required line ends exactly at the target
    assert pts[-1]["wkg_required"] == pytest.approx(4.0, abs=0.01)


def test_build_wkg_path_past_target_returns_none():
    assert build_wkg_path(
        "2026-07-01", 190, 91.5, -0.05, 4.0, "2026-07-01", today=date(2026, 7, 7)
    ) is None


def test_build_wkg_path_slope_none_flat_weight():
    path = build_wkg_path(
        "2026-07-01", 190, 91.5, None, 4.0, "2027-08-23", today=date(2026, 7, 7)
    )
    assert path["weight_flat"] is True
    assert all(p["weight_kg"] == 91.5 for p in path["points"])


def test_build_wkg_path_missing_inputs_returns_none():
    assert build_wkg_path("2026-07-01", None, 91.5, -0.05, 4.0, "2027-08-23",
                          today=date(2026, 7, 7)) is None
    assert build_wkg_path("2026-07-01", 190, None, -0.05, 4.0, "2027-08-23",
                          today=date(2026, 7, 7)) is None


# ── performance_guard ────────────────────────────────────────────────────────

def _ftp_rows(*watts):
    base = date(2026, 1, 1)
    return [
        {"date": (base + timedelta(days=30 * i)).isoformat(), "ftp_w": w}
        for i, w in enumerate(watts)
    ]


def test_guard_fires_on_ftp_drop():
    guard = performance_guard(_ftp_rows(240, 230), -0.05, [])
    assert guard["firing"] is True
    assert any("FTP" in r for r in guard["reasons"])


def test_guard_silent_when_not_cutting():
    assert performance_guard(_ftp_rows(240, 230), None, [])["firing"] is False
    assert performance_guard(_ftp_rows(240, 230), -0.005, [])["firing"] is False


def test_guard_ftp_signal_abstains_without_two_tests():
    guard = performance_guard(_ftp_rows(230), -0.05, [])
    assert guard["firing"] is False


def test_guard_fires_on_readiness_sag():
    guard = performance_guard(_ftp_rows(240, 238), -0.05, [-1.0] * 10)
    assert guard["firing"] is True
    assert any("readiness" in r for r in guard["reasons"])


def test_guard_readiness_abstains_without_enough_samples():
    guard = performance_guard(_ftp_rows(240, 238), -0.05, [-1.0] * 6 + [None] * 8)
    assert guard["firing"] is False


# ── settings round-trip (uses conftest tmp DB) ───────────────────────────────

def test_wkg_goal_defaults_on_empty():
    goal = load_wkg_goal()
    assert goal["target_wkg"] == 4.0
    assert goal["target_date"] == "2027-08-23"


def test_wkg_goal_save_load():
    save_wkg_goal(3.8, "2027-06-01")
    goal = load_wkg_goal()
    assert goal["target_wkg"] == 3.8
    assert goal["target_date"] == "2027-06-01"


def test_wkg_goal_corrupted_json_falls_back():
    from ai_endurance_coach_over50.history.text_cache import set_cached_text
    set_cached_text("wkg_goal_v1", "{not valid json")
    goal = load_wkg_goal()
    assert goal["target_wkg"] == 4.0
    assert goal["target_date"] == "2027-08-23"


def test_ftp_anchor_from_saved_tests():
    save_ftp_test("2026-05-01", None, 150, 165, ftp_w=195)
    save_ftp_test("2026-06-01", None, 152, 167, ftp_w=None)
    from ai_endurance_coach_over50.history import load_ftp_tests
    assert _ftp_anchor(load_ftp_tests()) == ("2026-05-01", 195)

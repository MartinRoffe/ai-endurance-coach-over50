"""Power profile zones and coach/dashboard integration."""
from datetime import date, timedelta

from ai_endurance_coach_over50.coach_context import build_advice_context, build_coach_context
from ai_endurance_coach_over50.history import save_activities, save_body_metrics, save_ftp_test
from ai_endurance_coach_over50.power_profile import (
    _coggan_zones,
    build_power_profile,
    format_power_profile_lines,
)
from ai_endurance_coach_over50.server.context import _build_context


def test_coggan_zones_at_250w():
    zones = _coggan_zones(250)
    assert zones[1] == {"zone": 2, "label": "Endurance", "lo": 140, "hi": 188}
    assert zones[3] == {"zone": 4, "label": "Threshold", "lo": 228, "hi": 262}
    assert zones[6] == {"zone": 7, "label": "Neuromuscular", "lo": 378, "hi": None}


def test_build_power_profile_none_without_ftp_w():
    save_ftp_test("2026-05-01", 1, 158, 172)
    assert build_power_profile() is None


def test_build_power_profile_with_ftp_w():
    save_ftp_test("2026-07-01", 2, 158, 172, ftp_w=250)
    save_body_metrics([{"date": "2026-07-01", "weight_kg": 78.0}])
    profile = build_power_profile()
    assert profile is not None
    assert profile["ftp_w"] == 250
    assert profile["test_date"] == "2026-07-01"
    assert profile["wkg"] == round(250 / 78.0, 2)
    assert len(profile["zones"]) == 7


def test_format_power_profile_lines():
    save_ftp_test("2026-07-01", 3, 158, 172, ftp_w=250)
    lines = format_power_profile_lines()
    text = "\n".join(lines)
    assert "## Power Reference (measured FTP)" in text
    assert "FTP: 250W" in text
    assert "Power is primary for prescription" in text
    assert "Z2 (Endurance): 140" in text


def test_build_coach_context_includes_power_reference():
    save_ftp_test("2026-07-01", 4, 158, 172, ftp_w=250)
    ctx = build_coach_context()
    assert "## Power Reference (measured FTP)" in ctx


def test_build_advice_context_includes_power_reference():
    save_ftp_test("2026-07-01", 5, 158, 172, ftp_w=250)
    ctx = build_advice_context(date.today())
    assert "## Power Reference (measured FTP)" in ctx


def _activate_power_meter(ftp_w: int | None = None):
    acts = []
    for i in range(3):
        d = (date.today() - timedelta(days=i + 1)).isoformat()
        acts.append({
            "activity_id": 4000 + i,
            "date": d,
            "type_key": "cycling",
            "has_power_meter": 1,
            "avg_power_w": 180,
            "duration_seconds": 3600,
        })
    save_activities(acts)
    if ftp_w:
        save_ftp_test(date.today().isoformat(), 100, 168, 175, ftp_w=ftp_w)


def test_power_baseline_card_when_meter_active_no_ftp_w():
    _activate_power_meter()
    ctx = _build_context(date.today())
    assert ctx["ftp_retest"] is not None
    assert ctx["ftp_retest"]["reason"] == "power_baseline"
    assert "never measured" in ctx["ftp_retest"]["message"]


def test_power_baseline_card_absent_when_ftp_w_known():
    _activate_power_meter(ftp_w=250)
    ctx = _build_context(date.today())
    assert ctx.get("ftp_retest") is None or ctx["ftp_retest"].get("reason") != "power_baseline"


def test_build_context_includes_power_profile_tile():
    _activate_power_meter(ftp_w=250)
    save_body_metrics([{"date": date.today().isoformat(), "weight_kg": 78.0}])
    ctx = _build_context(date.today())
    assert ctx["power_profile"] is not None
    assert ctx["power_profile"]["ftp_w"] == 250

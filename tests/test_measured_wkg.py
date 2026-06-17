"""Measured W/kg history from ftp_tests + bodyweight."""
from datetime import date

from ai_endurance_coach_over50.history import (
    latest_measured_wkg,
    measured_wkg_history,
    save_body_metrics,
    save_ftp_test,
)


def test_measured_wkg_history():
    save_body_metrics([{"date": "2026-05-01", "weight_kg": 80.0}])
    save_ftp_test("2026-06-01", 100, 165, 178, ftp_w=240)
    hist = measured_wkg_history(180)
    assert len(hist) == 1
    assert hist[0]["ftp_w"] == 240
    assert hist[0]["wkg"] == 3.0

    latest = latest_measured_wkg()
    assert latest["ftp_w"] == 240
    assert latest["wkg"] == 3.0

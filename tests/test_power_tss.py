"""Coggan TSS/IF computation and aggregation."""
from datetime import date, timedelta

from ai_endurance_coach_over50.analysis.power import compute_tss, ftp_w_on_date
from ai_endurance_coach_over50.history import (
    save_activities,
    save_ftp_test,
    weekly_tss,
    power_pmc_history,
)


def test_compute_tss_formula():
    if_val, tss = compute_tss(200, 3600, 250)
    assert if_val == 0.8
    assert tss == 64.0


def test_ftp_at_date_uses_newest_on_or_before():
    save_ftp_test("2026-06-01", 1, 160, 175, ftp_w=240)
    save_ftp_test("2026-07-01", 2, 165, 178, ftp_w=250)
    assert ftp_w_on_date(date(2026, 6, 15)) == 240
    assert ftp_w_on_date(date(2026, 7, 2)) == 250


def test_weekly_tss_aggregation():
    from datetime import date as d
    today = d.today()
    acts = []
    for i in range(3):
        dd = (today - timedelta(days=i + 1)).isoformat()
        acts.append({
            "activity_id": 5000 + i,
            "date": dd,
            "type_key": "cycling",
            "has_power_meter": 1,
            "norm_power_w": 200,
            "duration_seconds": 3600,
            "tss": 64.0,
            "intensity_factor": 0.8,
        })
    save_activities(acts)
    save_ftp_test(today.isoformat(), 99, 168, 175, ftp_w=250)
    wk = weekly_tss(4)
    assert wk
    assert wk[-1]["total_tss"] >= 64


def test_power_pmc_history_shape():
    from datetime import date as d
    today = d.today()
    acts = []
    for i in range(3):
        dd = (today - timedelta(days=i + 1)).isoformat()
        acts.append({
            "activity_id": 5100 + i,
            "date": dd,
            "type_key": "cycling",
            "has_power_meter": 1,
            "tss": 80,
            "duration_seconds": 3600,
        })
    save_activities(acts)
    save_ftp_test(today.isoformat(), 101, 168, 175, ftp_w=250)
    hist = power_pmc_history(14)
    assert len(hist) == 14
    assert "ctl" in hist[-1] and "tsb" in hist[-1]

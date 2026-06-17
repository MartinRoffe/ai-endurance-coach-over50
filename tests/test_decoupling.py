"""Pw:HR decoupling extraction and weekly power zone aggregation."""
from datetime import date, timedelta

from ai_endurance_coach_over50.analysis import _extract_power_durability, save_detail
from ai_endurance_coach_over50.history import (
    intensity_distribution_by_week_power,
    power_durability_exists,
    save_activities,
    save_power_durability,
)


def _lap(dur: int, hr: int, power: int) -> dict:
    return {"duration": dur, "averageHR": hr, "averagePower": power}


class _SplitsApi:
    def __init__(self, laps):
        self._laps = laps

    def get_activity_splits(self, activity_id):
        return {"lapDTOs": self._laps}


def test_extract_power_durability_decoupling_math():
    # 9 equal laps: first third HR 150→160 (+6.67%), power 200→190 (−5%)
    # decoupling = 6.67 - (-5) = 11.67
    laps = (
        [_lap(600, 150, 200)] * 3
        + [_lap(600, 155, 195)] * 3
        + [_lap(600, 160, 190)] * 3
    )
    activity = {
        "activity_id": 1,
        "date": "2026-06-01",
        "duration_seconds": 9 * 600,
    }
    row = _extract_power_durability(_SplitsApi(laps), activity)
    assert row is not None
    assert row["first_third_hr"] == 150.0
    assert row["final_third_hr"] == 160.0
    assert row["first_third_power"] == 200.0
    assert row["final_third_power"] == 190.0
    assert row["decoupling_pct"] == round(row["hr_drift_pct"] - row["power_drift_pct"], 2)
    assert row["decoupling_pct"] > 0


def test_extract_power_durability_requires_power_laps():
    laps = [_lap(600, 150, 0)] * 6
    activity = {"activity_id": 2, "date": "2026-06-02", "duration_seconds": 3600}
    assert _extract_power_durability(_SplitsApi(laps), activity) is None


def test_power_durability_persist():
    save_power_durability(99, {
        "date": "2026-06-01",
        "duration_min": 120,
        "first_third_hr": 145.0,
        "final_third_hr": 155.0,
        "first_third_power": 210.0,
        "final_third_power": 205.0,
        "hr_drift_pct": 6.9,
        "power_drift_pct": -2.4,
        "decoupling_pct": 9.3,
        "n_laps": 6,
    })
    assert power_durability_exists(99)


def test_intensity_distribution_by_week_power():
    today = date.today()
    mon = today - timedelta(days=today.weekday())
    save_activities([{
        "activity_id": 50,
        "date": mon.isoformat(),
        "type_key": "cycling",
        "has_power_meter": 1,
    }])
    save_detail(50, {
        "hr_zones": [],
        "power_zones": [
            {"zone": 1, "secs": 600, "pct": 17},
            {"zone": 2, "secs": 2400, "pct": 67},
            {"zone": 3, "secs": 600, "pct": 16},
        ],
    }, "test")

    rows = intensity_distribution_by_week_power(mon, today)
    assert len(rows) == 1
    week = rows[0]
    assert week["z1_pct"] == 16.7
    assert week["z2_pct"] == 66.7
    assert week["activity_count"] == 1

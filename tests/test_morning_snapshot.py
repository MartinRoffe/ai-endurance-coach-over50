"""Morning readiness snapshot and body-battery extraction."""
from datetime import date
from unittest.mock import MagicMock

from ai_endurance_coach_over50.history import (
    baseline_stats,
    capture_morning_snapshot,
    composite_score,
    load_morning_snapshot,
    maybe_capture_morning_snapshot,
    save,
    save_activities,
)
from ai_endurance_coach_over50.history.text_cache import load_advice, save_advice
from ai_endurance_coach_over50.metrics import DailyMetrics, fetch_metrics
from ai_endurance_coach_over50.modulation import hrv_traffic_light
from ai_endurance_coach_over50.display import readiness_label


def test_body_battery_morning_uses_earliest_post_sleep_reading():
    """Shuffled API order must not pick a mid-ride depleted reading."""
    api = MagicMock()
    sleep_end_ms = 1_000_000.0
    api.get_sleep_data.return_value = {
        "dailySleepDTO": {
            "sleepEndTimestampGMT": sleep_end_ms,
            "sleepScores": {"overall": {"value": 78}},
        }
    }
    api.get_hrv_data.return_value = {"hrvSummary": {"lastNightAvg": 41, "status": "BALANCED"}}
    api.get_body_battery.return_value = [{
        "bodyBatteryValuesArray": [
            [sleep_end_ms + 60_000, 57.0],
            [sleep_end_ms + 4 * 3600 * 1000, 15.0],
        ]
    }]
    api.get_stress_data.return_value = {}
    api.get_training_status.return_value = {}
    api.get_daily_summary.return_value = {}

    m = fetch_metrics(api, date(2026, 7, 5))
    assert m.body_battery_morning == 57.0
    assert m.body_battery_current == 15.0


def test_morning_snapshot_locks_before_activity():
    target = date(2026, 7, 6)
    m = DailyMetrics(
        date=target,
        hrv_last_night=41,
        sleep_score=78,
        body_battery_morning=57,
        resting_hr=63,
        hrv_status="BALANCED",
        training_load_acute=566,
    )
    save(m)
    stats = baseline_stats(target)
    comp_z = composite_score(m, stats)
    label, _ = readiness_label(comp_z)
    light = hrv_traffic_light(m, comp_z)

    assert maybe_capture_morning_snapshot(
        target, m, stats,
        composite_z=comp_z,
        readiness_label=label,
        traffic_light=light,
        advice_pre="Train as planned.",
    )

    snap = load_morning_snapshot(target)
    assert snap is not None
    assert snap["body_battery_morning"] == 57
    assert snap["composite_z"] == comp_z
    assert snap["advice_pre"] == "Train as planned."

    save_activities([{
        "activity_id": 99001,
        "date": target.isoformat(),
        "type_key": "road_biking",
        "name": "Long Ride",
        "duration_seconds": 4 * 3600,
    }])

    m2 = DailyMetrics(
        date=target,
        hrv_last_night=41,
        sleep_score=78,
        body_battery_morning=15,
        resting_hr=63,
        hrv_status="BALANCED",
        training_load_acute=1140,
        body_battery_current=15,
    )
    save(m2)
    assert maybe_capture_morning_snapshot(
        target, m2, stats,
        composite_z=-1.2,
        readiness_label="Low",
        traffic_light=light,
    ) is False
    assert load_morning_snapshot(target)["body_battery_morning"] == 57


def test_dual_advice_storage():
    target = date(2026, 7, 7)
    save_advice(target, "Morning gate text.", mode="pre")
    save_advice(target, "Post debrief text.", mode="post")
    assert load_advice(target, mode="pre") == "Morning gate text."
    assert load_advice(target, mode="post") == "Post debrief text."


def test_composite_excludes_acute_load():
    from ai_endurance_coach_over50.history import SCORED_FIELDS

    assert "training_load_acute" not in SCORED_FIELDS

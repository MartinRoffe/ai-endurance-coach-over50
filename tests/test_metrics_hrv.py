"""HRV and stress field parsing from Garmin API responses."""
from datetime import date
from unittest.mock import MagicMock

from ai_endurance_coach_over50.metrics import (
    _rest_stress_from_chart,
    fetch_metrics,
)


def _mock_api(stress_payload, sleep_payload=None, hrv_payload=None):
    api = MagicMock()
    api.get_hrv_data.return_value = hrv_payload or {"hrvSummary": {"weeklyAvg": 39.0, "status": "BALANCED"}}
    api.get_stress_data.return_value = stress_payload
    api.get_sleep_data.return_value = sleep_payload or {"dailySleepDTO": {}}
    for method in (
        "get_body_battery", "get_training_status", "get_daily_summary",
        "get_rhr_day", "get_nutrition_daily_food_log",
    ):
        getattr(api, method).return_value = {} if method != "get_body_battery" else []
    return api


def test_hrv_last_night_from_last_night_avg():
    api = _mock_api(
        stress_payload={"avgStressLevel": 19},
        hrv_payload={
            "hrvSummary": {
                "lastNightAvg": 42.0,
                "weeklyAvg": 39.0,
                "status": "BALANCED",
            },
        },
    )
    m = fetch_metrics(api, date(2026, 6, 19))
    assert m.hrv_last_night == 42.0
    assert m.hrv_weekly_avg == 39.0
    assert m.hrv_status == "BALANCED"


def test_hrv_last_night_falls_back_to_last_night():
    api = _mock_api(
        stress_payload={"avgStressLevel": 19},
        hrv_payload={
            "hrvSummary": {"lastNight": 38.0, "weeklyAvg": 37.0, "status": "LOW"},
        },
    )
    m = fetch_metrics(api, date(2026, 6, 19))
    assert m.hrv_last_night == 38.0


def test_rest_stress_from_api_field():
    api = _mock_api({"avgStressLevel": 33, "restStressLevel": 21})
    m = fetch_metrics(api, date(2026, 6, 19))
    assert m.rest_stress == 21.0


def test_rest_stress_derived_from_sleep_window():
    sleep = {
        "dailySleepDTO": {
            "sleepStartTimestampGMT": 1000,
            "sleepEndTimestampGMT": 5000,
        },
    }
    stress = {
        "avgStressLevel": 19,
        "stressValuesArray": [
            [500, 40],    # outside sleep
            [1500, 20],   # inside
            [3000, 16],   # inside
        ],
    }
    api = _mock_api(stress, sleep_payload=sleep)
    m = fetch_metrics(api, date(2026, 6, 19))
    assert m.rest_stress == 18.0


def test_rest_stress_chart_helper():
    stress = {"stressValuesArray": [[1000, 10], [2000, 20], [9000, 99]]}
    assert _rest_stress_from_chart(stress, 500, 2500) == 15.0
    assert _rest_stress_from_chart(stress, None, 2500) is None

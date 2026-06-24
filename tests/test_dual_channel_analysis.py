"""Post-workout analysis uses per-activity HR + power when power data exists."""
from ai_endurance_coach_over50.analysis import (
    _activity_has_power_data,
    _build_analysis_prompt,
    _coach_system_prompt,
    _rule_based_analysis,
)


def test_activity_has_power_data_from_activity_row():
    assert _activity_has_power_data(
        {"has_power_meter": 1, "avg_power_w": 128},
        {},
    )


def test_build_analysis_prompt_includes_power_zones_and_dual_read():
    activity = {
        "name": "Test Ride",
        "date": "2026-06-24",
        "duration_seconds": 4400,
        "distance_meters": 29600,
        "type_key": "road_biking",
        "avg_hr": 70,
        "max_hr": 70,
        "avg_power_w": 128,
        "norm_power_w": 147,
        "max_power_w": 707,
        "has_power_meter": 1,
    }
    detail = {
        "hr_zones": [{"zone": z, "secs": 0, "pct": 0, "low_bpm": 120 + z} for z in range(1, 6)],
        "power_zones": [
            {"zone": 1, "secs": 1200, "pct": 60, "low_w": 100},
            {"zone": 2, "secs": 600, "pct": 30, "low_w": 150},
        ],
        "has_power_meter": True,
        "training_effect": 4.0,
        "training_effect_label": "highly_improving",
        "training_load": 196,
    }
    prompt = _build_analysis_prompt(activity, detail)
    assert "Power: avg 128 W" in prompt
    assert "NP 147 W" in prompt
    assert "Power zone distribution:" in prompt
    assert "cross-reading HR and power" in prompt
    assert "HR zone data is missing or implausible" in prompt


def test_coach_system_prompt_dual_channel_per_activity():
    sys = _coach_system_prompt("road_biking", has_power=True)
    assert "Dual-channel coaching" in sys
    assert "2012 Haute Route" in sys


def test_rule_based_dual_channel_when_hr_missing():
    text = _rule_based_analysis(
        {"norm_power_w": 147},
        {"hr_zones": [{"zone": 1, "secs": 0, "pct": 0}], "training_effect": 4.0,
         "training_effect_label": "highly_improving", "has_power_meter": True},
    )
    assert "NP 147 W" in text
    assert "HR zones are missing" in text

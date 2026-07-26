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
    assert "do not default to 'power zones are wrong'" in sys


def test_rule_based_dual_channel_when_hr_missing():
    text = _rule_based_analysis(
        {"norm_power_w": 147},
        {"hr_zones": [{"zone": 1, "secs": 0, "pct": 0}], "training_effect": 4.0,
         "training_effect_label": "highly_improving", "has_power_meter": True},
    )
    assert "NP 147 W" in text
    assert "HR zones are missing" in text


def _base_activity(**extra):
    act = {
        "name": "Long Ride",
        "date": "2026-07-18",
        "duration_seconds": 13200,
        "distance_meters": 85000,
        "type_key": "road_biking",
        "avg_hr": 128,
        "max_hr": 155,
        "avg_power_w": 165,
        "norm_power_w": 176,
        "max_power_w": 320,
        "has_power_meter": 1,
        "activity_id": 4242,
    }
    act.update(extra)
    return act


def _aligned_power_zones(ftp_w: int = 202):
    """Coggan-ish Z4 low ≈ 91% FTP so mismatch gate stays closed."""
    z4_low = round(ftp_w * 0.91)
    return [
        {"zone": 1, "secs": 1800, "pct": 20, "low_w": 0},
        {"zone": 2, "secs": 3600, "pct": 32, "low_w": round(ftp_w * 0.56)},
        {"zone": 3, "secs": 4200, "pct": 35, "low_w": round(ftp_w * 0.76)},
        {"zone": 4, "secs": 1200, "pct": 10, "low_w": z4_low},
        {"zone": 5, "secs": 400, "pct": 3, "low_w": round(ftp_w * 1.06)},
    ]


def _valid_hr_zones():
    return [
        {"zone": 1, "secs": 3600, "pct": 40, "low_bpm": 100},
        {"zone": 2, "secs": 4800, "pct": 52, "low_bpm": 120},
        {"zone": 3, "secs": 600, "pct": 6, "low_bpm": 140},
        {"zone": 4, "secs": 120, "pct": 1, "low_bpm": 155},
        {"zone": 5, "secs": 80, "pct": 1, "low_bpm": 170},
    ]


def test_calibrated_ftp_prefers_physiology_not_uncalibrated(monkeypatch):
    monkeypatch.setattr(
        "ai_endurance_coach_over50.history.load_ftp_tests",
        lambda: [{"date": "2026-07-02", "ftp_w": 202}],
    )
    monkeypatch.setattr(
        "ai_endurance_coach_over50.history.ftp_retest_due",
        lambda *a, **k: None,
    )
    detail = {
        "hr_zones": _valid_hr_zones(),
        "power_zones": _aligned_power_zones(202),
        "has_power_meter": True,
        "training_effect": 5.0,
        "training_effect_label": "tempo",
        "training_load": 494,
    }
    prompt = _build_analysis_prompt(_base_activity(), detail)
    assert "measured FTP 202 W (tested 2026-07-02)" in prompt
    assert "prefer physiology" in prompt
    assert "UNCALIBRATED" not in prompt
    assert "uncalibrated profile FTP story" in prompt  # ruled-out wording
    assert "Do not default to the physiology" not in prompt


def test_no_ftp_still_flags_uncalibrated(monkeypatch):
    monkeypatch.setattr(
        "ai_endurance_coach_over50.history.load_ftp_tests",
        lambda: [],
    )
    monkeypatch.setattr(
        "ai_endurance_coach_over50.history.ftp_retest_due",
        lambda *a, **k: {"last_date": None, "age_days": None},
    )
    detail = {
        "hr_zones": _valid_hr_zones(),
        "power_zones": _aligned_power_zones(202),
        "has_power_meter": True,
        "training_effect": 4.0,
        "training_effect_label": "improving",
        "training_load": 200,
    }
    prompt = _build_analysis_prompt(_base_activity(), detail)
    assert "UNCALIBRATED" in prompt
    assert "prefer physiology" not in prompt


def test_zone_mismatch_branch(monkeypatch):
    monkeypatch.setattr(
        "ai_endurance_coach_over50.history.load_ftp_tests",
        lambda: [{"date": "2026-07-02", "ftp_w": 202}],
    )
    monkeypatch.setattr(
        "ai_endurance_coach_over50.history.ftp_retest_due",
        lambda *a, **k: None,
    )
    # Z4 low implies ~300 W FTP vs measured 202 W (>7% divergence)
    zones = _aligned_power_zones(202)
    zones[3] = {"zone": 4, "secs": 1200, "pct": 10, "low_w": 273}
    detail = {
        "hr_zones": _valid_hr_zones(),
        "power_zones": zones,
        "has_power_meter": True,
        "training_effect": 4.0,
        "training_effect_label": "improving",
        "training_load": 200,
    }
    prompt = _build_analysis_prompt(_base_activity(), detail)
    assert ">7% divergence" in prompt
    assert "UNCALIBRATED" not in prompt
    assert "prefer physiology" not in prompt
    assert "Measured FTP: 202 W" in prompt

def test_stale_measured_ftp_soft_note_not_uncalibrated(monkeypatch):
    monkeypatch.setattr(
        "ai_endurance_coach_over50.history.load_ftp_tests",
        lambda: [{"date": "2026-05-01", "ftp_w": 202}],
    )
    monkeypatch.setattr(
        "ai_endurance_coach_over50.history.ftp_retest_due",
        lambda *a, **k: {"last_date": "2026-05-01", "age_days": 78},
    )
    detail = {
        "hr_zones": _valid_hr_zones(),
        "power_zones": _aligned_power_zones(202),
        "has_power_meter": True,
        "training_effect": 4.0,
        "training_effect_label": "improving",
        "training_load": 200,
    }
    prompt = _build_analysis_prompt(_base_activity(date="2026-07-18"), detail)
    assert "UNCALIBRATED" not in prompt
    assert "more than 42 days old" in prompt
    assert "measured FTP 202 W" in prompt
    assert "prefer physiology" in prompt


def test_injects_power_decoupling_when_present(monkeypatch):
    monkeypatch.setattr(
        "ai_endurance_coach_over50.history.load_ftp_tests",
        lambda: [{"date": "2026-07-02", "ftp_w": 202}],
    )
    monkeypatch.setattr(
        "ai_endurance_coach_over50.history.ftp_retest_due",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "ai_endurance_coach_over50.history.get_power_durability",
        lambda aid: {
            "activity_id": aid,
            "decoupling_pct": 11.0,
            "hr_drift_pct": 12.9,
            "power_drift_pct": 1.9,
        },
    )
    monkeypatch.setattr(
        "ai_endurance_coach_over50.history.get_durability",
        lambda aid: None,
    )
    detail = {
        "hr_zones": _valid_hr_zones(),
        "power_zones": _aligned_power_zones(202),
        "has_power_meter": True,
        "training_effect": 5.0,
        "training_effect_label": "tempo",
        "training_load": 494,
    }
    prompt = _build_analysis_prompt(_base_activity(), detail)
    assert "Pw:HR decoupling: +11.0%" in prompt
    assert "HR drift +12.9%" in prompt
    assert "power drift +1.9%" in prompt

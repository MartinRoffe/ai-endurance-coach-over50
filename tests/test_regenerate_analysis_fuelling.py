"""Re-analyse after fuelling log uses stored detail + new carb context."""
from ai_endurance_coach_over50.analysis import (
    regenerate_analysis_for_activity,
    save_detail,
    update_analysis_text,
)
from ai_endurance_coach_over50.analysis.db import load_analysis
from ai_endurance_coach_over50.history import save_activities, save_fuelling_log


def _seed_activity(aid=23823077329):
    save_activities([{
        "activity_id": aid,
        "date": "2026-08-02",
        "name": "Long Ride",
        "type_key": "road_biking",
        "duration_seconds": 20488,
        "distance_meters": 125260,
        "avg_hr": 138,
        "max_hr": 169,
        "avg_power_w": 128,
        "norm_power_w": 159,
        "max_power_w": 926,
        "has_power_meter": 1,
        "calories": 3061,
        "elevation_gain": 839,
        "min_temperature": 21,
        "max_temperature": 34,
        "tss": 305.4,
        "intensity_factor": 0.743,
    }])
    save_detail(aid, {
        "hr_zones": [{"zone": 1, "secs": 100, "pct": 40, "low_bpm": 100}],
        "power_zones": [{"zone": 2, "secs": 100, "pct": 50, "low_w": 120}],
        "training_effect": 5.0,
        "training_effect_label": "highly_improving",
        "aerobic_te_message": "significant",
        "training_load": 314,
        "has_power_meter": True,
        "avg_power_w": 128,
        "norm_power_w": 159,
    }, "OLD ANALYSIS — heat drift only.")


def test_update_analysis_text_preserves_zones():
    _seed_activity(99)
    assert update_analysis_text(99, "NEW TEXT")
    row = load_analysis(99)
    assert row["analysis_text"] == "NEW TEXT"
    assert row["power_zones"]
    assert row["training_effect"] == 5.0


def test_regenerate_after_fuelling_injects_carbs(monkeypatch):
    aid = 23823077329
    _seed_activity(aid)
    save_fuelling_log("2026-08-02", aid, 90.0, 29.0, True, "4 cakes")

    captured = {}

    def fake_generate(activity, detail, companion=None):
        from ai_endurance_coach_over50.analysis.prompts import _build_analysis_prompt
        captured["prompt"] = _build_analysis_prompt(activity, detail, companion=companion)
        return "NEW: under-fuelled long ride."

    monkeypatch.setattr(
        "ai_endurance_coach_over50.analysis.generate.generate_analysis",
        fake_generate,
    )
    text = regenerate_analysis_for_activity(aid)
    assert text == "NEW: under-fuelled long ride."
    assert "In-ride fuelling logged: ~29 g carbs/h" in captured["prompt"]
    assert load_analysis(aid)["analysis_text"] == text


def test_regenerate_noop_without_analysis():
    assert regenerate_analysis_for_activity(999999001) is None

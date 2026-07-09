"""Morning advice must wait for Garmin overnight sync."""
from datetime import date
from unittest.mock import patch

from ai_endurance_coach_over50.history import (
    capture_morning_snapshot,
    load_morning_snapshot,
    maybe_capture_morning_snapshot,
)
from ai_endurance_coach_over50.history.text_cache import delete_advice, load_advice, save_advice
from ai_endurance_coach_over50.metrics import DailyMetrics, morning_metrics_ready
from ai_endurance_coach_over50.report import generate_advice, _advice_fingerprint


def test_morning_metrics_ready_matches_email_gate():
    assert morning_metrics_ready(DailyMetrics(date=date.today(), sleep_score=80)) is True
    assert morning_metrics_ready(DailyMetrics(date=date.today(), body_battery_morning=55)) is True
    assert morning_metrics_ready(DailyMetrics(date=date.today(), hrv_last_night=42)) is False


def test_generate_advice_skips_before_morning_sync():
    target = date(2026, 7, 9)
    m = DailyMetrics(date=target, hrv_last_night=41)
    assert generate_advice(m, {}, None, mode="pre") == ""


def test_maybe_capture_waits_for_morning_sync():
    target = date(2026, 7, 10)
    m = DailyMetrics(date=target, hrv_last_night=41, sleep_score=None, body_battery_morning=None)
    assert maybe_capture_morning_snapshot(
        target, m, {},
        composite_z=None,
        readiness_label="Unknown",
        traffic_light=None,
    ) is False
    assert load_morning_snapshot(target) is None


def test_stale_pre_advice_invalidates_when_fingerprint_changes():
    target = date(2026, 7, 11)
    early = DailyMetrics(date=target, hrv_last_night=40)
    late = DailyMetrics(date=target, sleep_score=82, body_battery_morning=60, hrv_last_night=40)
    stats = {"sleep_score": (75.0, 5.0), "hrv_last_night": (40.0, 3.0)}

    save_advice(target, "The baseline is still building so there's no composite score.", mode="pre")
    fp_early = _advice_fingerprint(early, stats, None)

    with patch("ai_endurance_coach_over50.report.get_cached_text") as mock_get:
        mock_get.side_effect = lambda key: {
            f"advice_mode_v1_{target.isoformat()}": "pre",
            f"advice_fp_v1_{target.isoformat()}": fp_early,
        }.get(key)
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with patch("ai_endurance_coach_over50.report._rule_based_advice", return_value="Fresh advice."):
                text = generate_advice(late, stats, 0.4, mode="pre")

    assert text == "Fresh advice."
    assert load_advice(target, mode="pre") == "Fresh advice."


def test_delete_advice_clears_premature_snapshot():
    target = date(2026, 7, 12)
    capture_morning_snapshot(
        target,
        DailyMetrics(date=target, hrv_last_night=39),
        composite_z=None,
        readiness_label="Unknown",
        traffic_light=None,
        advice_pre="Too early.",
    )
    save_advice(target, "Too early.", mode="pre")

    delete_advice(target, mode="pre")

    assert load_morning_snapshot(target) is None
    assert load_advice(target, mode="pre") is None

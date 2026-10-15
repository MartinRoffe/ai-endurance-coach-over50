"""Dashboard exposes morning_ready so incomplete overnight data is visible."""
from datetime import date

from ai_endurance_coach_over50.metrics import DailyMetrics, morning_metrics_ready


def test_morning_metrics_ready_matches_watch_sync_expectation():
    today = date(2026, 10, 20)
    empty = DailyMetrics(date=today)
    assert morning_metrics_ready(empty) is False
    assert morning_metrics_ready(DailyMetrics(date=today, sleep_score=80)) is True
    assert morning_metrics_ready(
        DailyMetrics(date=today, body_battery_morning=55)
    ) is True


def test_dashboard_template_has_watch_sync_banner():
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1]
            / "ai_endurance_coach_over50/templates/dashboard.html").read_text()
    assert "morning_ready" in html
    assert "Watch has not synced overnight" in html
    assert "waiting for watch sync" in html

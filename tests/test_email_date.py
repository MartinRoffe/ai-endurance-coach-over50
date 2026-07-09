"""Daily email must always target the local calendar today."""
from datetime import date
from unittest.mock import patch

from ai_endurance_coach_over50.metrics import DailyMetrics, local_today


def test_local_today_matches_datetime_astimezone():
    from datetime import datetime
    assert local_today() == datetime.now().astimezone().date()


def test_email_live_send_ignores_past_date(monkeypatch):
    """Live --email always uses local_today(), not a stale --date."""
    from ai_endurance_coach_over50 import cli

    today = date(2026, 7, 9)
    past = date(2026, 7, 8)
    m = DailyMetrics(
        date=today,
        sleep_score=80,
        body_battery_morning=70,
        sleep_end_ts=1_700_000_000.0,
    )

    monkeypatch.setattr(cli, "local_today", lambda: today)
    monkeypatch.setattr(cli, "load", lambda _d: m)
    monkeypatch.setattr(cli, "available_count", lambda _m: 5)
    monkeypatch.setattr(cli, "needs_metrics_refetch", lambda _m: False)
    monkeypatch.setattr(cli, "get_api", lambda *_a, **_k: object())

    sent = {"called": False}

    def _fake_run_report(metrics, dry_run=False):
        sent["called"] = True
        assert metrics.date == today

    monkeypatch.setattr("ai_endurance_coach_over50.report.run_report", _fake_run_report)
    monkeypatch.setenv("GARMIN_EMAIL", "u@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "pw")

    sentinel = cli.Path.home() / ".ai_endurance_coach_over50" / f"sent_{today.isoformat()}"
    sentinel.unlink(missing_ok=True)

    with patch.object(cli.sys, "argv", ["endurance-coach", "--email", "--date", past.isoformat()]):
        try:
            cli.main()
        except SystemExit as exc:
            assert exc.code == 0

    assert sent["called"] is True
    assert sentinel.exists()
    sentinel.unlink(missing_ok=True)

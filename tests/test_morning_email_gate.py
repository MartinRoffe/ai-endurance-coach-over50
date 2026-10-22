"""Morning email: wake body battery, and a deadline send when the watch is dark."""
import logging
from datetime import date
from unittest.mock import MagicMock, patch

from ai_endurance_coach_over50.analysis.db import _ensure_analysis_schema
from ai_endurance_coach_over50.fitness_plan import session_for_date
from ai_endurance_coach_over50.history.db import _conn
from ai_endurance_coach_over50.metrics import (
    BODY_BATTERY_MORNING_MIN,
    DailyMetrics,
    email_readiness_gaps,
    fetch_metrics,
    wake_body_battery,
)
from ai_endurance_coach_over50.report import (
    _build_advice_prompt,
    build_html,
    generate_advice,
    missing_morning_notes,
)
from ai_endurance_coach_over50.schedule import render_email_script, render_linux_email_script


# A past sleep end, so a live CLI call (which uses time.time()) is already
# outside the settle window. The gate tests pass now_ts explicitly.
_SLEEP_END_S = 1_700_000_000.0
_SLEEP_END_MS = _SLEEP_END_S * 1000.0


def _readings_22_oct():
    """Peak of 53 on sleep end, evening 90 hours earlier, charged delta unused."""
    return [
        (_SLEEP_END_MS - 6 * 3600 * 1000, 90.0),
        (_SLEEP_END_MS - 3 * 60 * 1000, 48.0),
        (_SLEEP_END_MS, 53.0),
    ]


def _readings_18_oct():
    """Unprocessed 5 at sleep end. The evening max must not be taken instead."""
    return [
        (_SLEEP_END_MS - 6 * 3600 * 1000, 90.0),
        (_SLEEP_END_MS, 5.0),
        (_SLEEP_END_MS + 2 * 60 * 1000, 5.0),
    ]


def test_oct18_early_body_battery_still_defers():
    early = _readings_18_oct()
    assert wake_body_battery(early, _SLEEP_END_MS, now_ts=_SLEEP_END_S + 25 * 60) is None
    # A processed wake value still wins once Garmin posts it.
    with_real = early + [(_SLEEP_END_MS + 25 * 60 * 1000, 78.0)]
    assert wake_body_battery(with_real, _SLEEP_END_MS, now_ts=_SLEEP_END_S + 30 * 60) == 78.0

    waiting = DailyMetrics(
        date=date(2026, 10, 18),
        sleep_end_ts=_SLEEP_END_S,
        sleep_score=80,
        body_battery_morning=5,
        resting_hr=48,
        rest_stress=20,
    )
    gaps = email_readiness_gaps(waiting, now_ts=_SLEEP_END_S + 25 * 60)
    assert any("implausible" in gap for gap in gaps)
    assert not any("20 min" in gap for gap in gaps)


def test_oct22_peak_at_sleep_end_sends_after_twenty_minutes():
    series = _readings_22_oct()
    assert wake_body_battery(series, _SLEEP_END_MS, now_ts=_SLEEP_END_S + 10 * 60) is None
    assert wake_body_battery(series, _SLEEP_END_MS, now_ts=_SLEEP_END_S + 20 * 60) == 53.0
    # A later morning drop is not the wake level, and the +48 charged delta is not either.
    drained = series + [(_SLEEP_END_MS + 60 * 60 * 1000, 40.0)]
    assert wake_body_battery(drained, _SLEEP_END_MS, now_ts=_SLEEP_END_S + 90 * 60) == 53.0

    too_soon = DailyMetrics(
        date=date(2026, 10, 22),
        sleep_end_ts=_SLEEP_END_S,
        sleep_score=80,
        body_battery_morning=53,
        resting_hr=48,
        rest_stress=20,
    )
    assert any("20 min" in gap for gap in email_readiness_gaps(too_soon, now_ts=_SLEEP_END_S + 10 * 60))
    assert email_readiness_gaps(too_soon, now_ts=_SLEEP_END_S + 20 * 60) == []


def test_fetch_metrics_reads_the_sleep_end_peak_not_the_charged_delta(monkeypatch):
    monkeypatch.setattr(
        "ai_endurance_coach_over50.metrics.time.time",
        lambda: _SLEEP_END_S + 25 * 60,
    )
    api = MagicMock()
    api.get_sleep_data.return_value = {
        "dailySleepDTO": {
            "sleepEndTimestampGMT": _SLEEP_END_MS,
            "sleepScores": {"overall": {"value": 80}},
        }
    }
    api.get_hrv_data.return_value = {}
    api.get_body_battery.return_value = [{
        "charged": 48,
        "bodyBatteryValuesArray": [[ts, v] for ts, v in _readings_22_oct()],
    }]
    api.get_stress_data.return_value = {"restStressLevel": 18, "avgStressLevel": 24}
    api.get_training_status.return_value = {}
    api.get_user_summary.return_value = {
        "restingHeartRate": 48,
        "totalSteps": 100,
        "activeKilocalories": 10,
    }
    m = fetch_metrics(api, date(2026, 10, 22))
    assert m.body_battery_morning == 53.0
    assert m.body_battery_morning != 48
    assert email_readiness_gaps(m, now_ts=_SLEEP_END_S + 25 * 60) == []

    monkeypatch.setattr(
        "ai_endurance_coach_over50.metrics.time.time",
        lambda: _SLEEP_END_S + 25 * 60,
    )
    api.get_body_battery.return_value = [{
        "charged": 48,
        "bodyBatteryValuesArray": [[ts, v] for ts, v in _readings_18_oct()],
    }]
    early = fetch_metrics(api, date(2026, 10, 18))
    assert early.body_battery_morning is None
    assert early.body_battery_morning != 90
    assert any(
        "body_battery" in gap
        for gap in email_readiness_gaps(early, now_ts=_SLEEP_END_S + 25 * 60)
    )
    assert BODY_BATTERY_MORNING_MIN == 15.0


def _cli_email(monkeypatch, argv, metrics, today):
    from ai_endurance_coach_over50 import cli

    monkeypatch.setattr(cli, "local_today", lambda: today)
    monkeypatch.setattr(cli, "load", lambda _d: metrics)
    monkeypatch.setattr(cli, "available_count", lambda _m: 5)
    monkeypatch.setattr(cli, "needs_metrics_refetch", lambda _m: False)
    monkeypatch.setattr(cli, "get_api", lambda *_a, **_k: object())
    monkeypatch.setenv("GARMIN_EMAIL", "u@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "pw")
    sent = {}

    def _fake_run_report(m, dry_run=False, incomplete=False):
        sent["called"] = True
        sent["incomplete"] = incomplete
        sent["metrics"] = m

    monkeypatch.setattr("ai_endurance_coach_over50.report.run_report", _fake_run_report)
    with patch.object(cli.sys, "argv", argv):
        try:
            cli.main()
            code = 0
        except SystemExit as exc:
            code = exc.code
    return code, sent


def test_settled_oct22_picture_sends(monkeypatch):
    today = date(2026, 10, 22)
    m = DailyMetrics(
        date=today,
        sleep_end_ts=_SLEEP_END_S,
        sleep_score=80,
        body_battery_morning=53,
        resting_hr=48,
        rest_stress=20,
    )
    code, sent = _cli_email(monkeypatch, ["endurance-coach", "--email"], m, today)
    assert code == 0
    assert sent["called"] is True
    assert sent["incomplete"] is False


def test_oct18_picture_still_defers_the_send(monkeypatch):
    today = date(2026, 10, 18)
    m = DailyMetrics(
        date=today,
        sleep_end_ts=_SLEEP_END_S,
        sleep_score=80,
        body_battery_morning=5,
        resting_hr=48,
        rest_stress=20,
    )
    code, sent = _cli_email(monkeypatch, ["endurance-coach", "--email"], m, today)
    assert code == 2
    assert sent == {}


def test_deadline_sends_with_missing_sleep_marked(monkeypatch):
    today = date(2026, 10, 21)
    # Watch battery died. Resting HR from an earlier sync is real; sleep is not.
    m = DailyMetrics(date=today, resting_hr=52, rest_stress=22, total_steps=400)
    gaps = email_readiness_gaps(m, now_ts=_SLEEP_END_S)
    assert any("sleep" in gap for gap in gaps)
    assert any("body_battery" in gap for gap in gaps)

    held, held_sent = _cli_email(monkeypatch, ["endurance-coach", "--email"], m, today)
    assert held == 2
    assert held_sent == {}
    from ai_endurance_coach_over50 import cli
    if cli._EMAIL_LOCK_FH is not None:
        cli._EMAIL_LOCK_FH.close()
        cli._EMAIL_LOCK_FH = None

    code, sent = _cli_email(
        monkeypatch,
        ["endurance-coach", "--email", "--email-incomplete"],
        m,
        today,
    )
    assert code == 0
    assert sent["called"] is True
    assert sent["incomplete"] is True

    notes = missing_morning_notes(m)
    assert "No sleep data — watch not worn/charged" in notes
    assert "Body battery: not synced" in notes
    assert "Resting HR: not synced" not in notes

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    advice = generate_advice(m, {}, None, mode="pre", missing_notes=notes)
    assert advice.strip()
    prompt = _build_advice_prompt(m, {}, None, missing_notes=notes)
    assert "Do not invent" in prompt
    assert "No sleep data — watch not worn/charged" in prompt
    assert "Body battery: not synced" in prompt
    assert "Sleep Score: 80" not in prompt

    html = build_html(m, {}, None, advice, missing_notes=notes)
    assert "No sleep data — watch not worn/charged" in html
    assert "Body battery: not synced" in html
    assert "not estimated" in html
    label = session_for_date(today)[1]
    assert label in html
    # The real resting HR is shown. No stand-in sleep score or body battery.
    assert "52" in html
    assert "5/100" not in html
    assert ">80<" not in html and "80/100" not in html


def test_scheduler_deadline_sends_incomplete():
    linux = render_linux_email_script()
    mac = render_email_script("/usr/bin/python3", "/tmp/proj", __import__("pathlib").Path("/tmp/.env"))
    for script in (linux, mac):
        deadline = script.split("DEADLINE", 1)[1]
        assert "--email-incomplete" in deadline
        assert "sending with the data on hand" in script


def test_analysis_schema_does_not_warn_when_columns_exist(caplog):
    with caplog.at_level(logging.WARNING):
        with _conn() as con:
            _ensure_analysis_schema(con)
            _ensure_analysis_schema(con)
    assert "duplicate column" not in caplog.text.lower()
    assert "_ensure_analysis_schema failed" not in caplog.text

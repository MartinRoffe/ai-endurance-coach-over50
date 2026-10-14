"""Stale Garmin/Withings data is visible, and tests never touch the real home dir."""
from datetime import datetime, timezone
from pathlib import Path

from ai_endurance_coach_over50.history.db import _conn, _ensure_schema
from ai_endurance_coach_over50.history.sync_status import freshness_warnings, record_sync
from ai_endurance_coach_over50.paths import data_dir


def _insert_metrics(recorded_at: str, day: str = "2026-10-01") -> None:
    with _conn() as con:
        _ensure_schema(con)
        con.execute(
            "INSERT INTO daily_metrics (date, recorded_at) VALUES (?, ?)",
            (day, recorded_at),
        )


def test_data_dir_follows_env_not_real_home():
    assert data_dir() != Path.home() / ".ai_endurance_coach_over50"
    assert data_dir().name == "coachhome"


def test_missing_garmin_data_is_reported():
    notes = freshness_warnings(now=datetime(2026, 10, 14, 7, tzinfo=timezone.utc))
    assert any(n["source"] == "garmin" and n["kind"] == "missing" for n in notes)
    assert not any(n["source"] == "withings" for n in notes)


def test_stale_garmin_data_over_24h():
    _insert_metrics("2026-10-12 06:00:00")
    notes = freshness_warnings(now=datetime(2026, 10, 14, 7, tzinfo=timezone.utc))
    stale = [n for n in notes if n["kind"] == "stale" and n["source"] == "garmin"]
    assert len(stale) == 1
    assert "stale" in stale[0]["message"].lower() or "old" in stale[0]["message"].lower()


def test_fresh_garmin_data_is_quiet():
    _insert_metrics("2026-10-14 06:30:00", day="2026-10-14")
    record_sync("garmin", ok=True, detail="2026-10-14", attempted_at=datetime(2026, 10, 14, 6, 30, tzinfo=timezone.utc))
    notes = freshness_warnings(now=datetime(2026, 10, 14, 7, tzinfo=timezone.utc))
    assert notes == []


def test_failed_sync_is_visible_even_when_cache_is_fresh():
    _insert_metrics("2026-10-14 06:30:00", day="2026-10-14")
    record_sync(
        "garmin",
        ok=False,
        error="GarminConnectConnectionError: timeout",
        attempted_at=datetime(2026, 10, 14, 6, 45, tzinfo=timezone.utc),
    )
    notes = freshness_warnings(now=datetime(2026, 10, 14, 7, tzinfo=timezone.utc))
    assert len(notes) == 1
    assert notes[0]["kind"] == "failed"
    assert "timeout" in notes[0]["message"]


def test_withings_failure_and_stale_success():
    _insert_metrics("2026-10-14 06:30:00", day="2026-10-14")
    record_sync(
        "garmin",
        ok=True,
        attempted_at=datetime(2026, 10, 14, 6, 30, tzinfo=timezone.utc),
    )
    record_sync(
        "withings",
        ok=False,
        error="WithingsAuthError: expired",
        attempted_at=datetime(2026, 10, 14, 6, 40, tzinfo=timezone.utc),
    )
    notes = freshness_warnings(now=datetime(2026, 10, 14, 7, tzinfo=timezone.utc))
    assert any(n["source"] == "withings" and n["kind"] == "failed" for n in notes)

    record_sync(
        "withings",
        ok=True,
        detail="body=1",
        attempted_at=datetime(2026, 10, 12, 6, tzinfo=timezone.utc),
    )
    notes = freshness_warnings(now=datetime(2026, 10, 14, 7, tzinfo=timezone.utc))
    assert any(n["source"] == "withings" and n["kind"] == "stale" for n in notes)


def test_publish_findings_writes_under_env_home(tmp_path):
    from ai_endurance_coach_over50.archive_findings import home_archive, publish_findings

    src = tmp_path / "findings.json"
    src.write_text('{"ok": true}', encoding="utf-8")
    dest = publish_findings(src)
    assert dest == home_archive() / "findings.json"
    assert dest.is_file()
    assert dest.is_relative_to(data_dir())
    assert not str(dest).startswith(str(Path.home() / ".ai_endurance_coach_over50"))

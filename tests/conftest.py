"""Shared fixtures: every test gets a throwaway data dir and SQLite DB.

``ENDURANCE_COACH_HOME`` redirects paths that used to hit
``~/.ai_endurance_coach_over50`` (email sentinels, archive publish, Withings
config, Garmin tokens). ``history.db.DB_PATH`` is patched as well because
``_conn()`` reads that attribute rather than the package-level re-export.
"""
import pytest

from ai_endurance_coach_over50.history import db as history_db


@pytest.fixture(autouse=True)
def isolated_coach_home(tmp_path, monkeypatch):
    home = tmp_path / "coachhome"
    home.mkdir()
    monkeypatch.setenv("ENDURANCE_COACH_HOME", str(home))
    monkeypatch.setattr(history_db, "DB_PATH", home / "history.db")
    return home

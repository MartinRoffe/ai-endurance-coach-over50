"""Shared fixtures: every test gets a throwaway SQLite DB so nothing touches
the real ~/.ai_endurance_coach_over50/history.db."""
import pytest

from ai_endurance_coach_over50.history import db as history_db


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    # _conn() reads DB_PATH from history.db at call time; the package-level
    # history.DB_PATH re-export is a snapshot, so patch the db module.
    monkeypatch.setattr(history_db, "DB_PATH", tmp_path / "history.db")

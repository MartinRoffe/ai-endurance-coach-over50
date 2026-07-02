"""Generic text cache and daily-advice persistence."""
from __future__ import annotations

from datetime import date
from typing import Optional

from .db import _conn


def get_cached_text(key: str) -> Optional[str]:
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS text_cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                recorded_at TEXT DEFAULT (datetime('now'))
            )
        """)
        row = con.execute("SELECT value FROM text_cache WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_cached_text(key: str, value: str) -> None:
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS text_cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                recorded_at TEXT DEFAULT (datetime('now'))
            )
        """)
        con.execute("INSERT OR REPLACE INTO text_cache (key, value) VALUES (?, ?)", (key, value))


def save_advice(target_date: date, text: str) -> None:
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS daily_advice (
                date TEXT PRIMARY KEY,
                advice TEXT NOT NULL,
                recorded_at TEXT DEFAULT (datetime('now'))
            )
        """)
        con.execute(
            "INSERT OR REPLACE INTO daily_advice (date, advice) VALUES (?, ?)",
            (target_date.isoformat(), text),
        )


def delete_advice(target_date: date) -> None:
    with _conn() as con:
        con.execute("DELETE FROM daily_advice WHERE date = ?", (target_date.isoformat(),))
    try:
        set_cached_text(f"advice_mode_v1_{target_date.isoformat()}", "")
    except Exception:
        pass


def load_advice(target_date: date) -> Optional[str]:
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS daily_advice (
                date TEXT PRIMARY KEY,
                advice TEXT NOT NULL,
                recorded_at TEXT DEFAULT (datetime('now'))
            )
        """)
        row = con.execute(
            "SELECT advice FROM daily_advice WHERE date = ?",
            (target_date.isoformat(),),
        ).fetchone()
    return row["advice"] if row else None

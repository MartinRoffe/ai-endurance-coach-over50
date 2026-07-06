"""Generic text cache and daily-advice persistence."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from .db import _conn
from .metrics_store import load_morning_snapshot

AdviceMode = Literal["pre", "post"]


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


def _ensure_daily_advice_schema(con) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS daily_advice (
            date TEXT PRIMARY KEY,
            advice TEXT NOT NULL,
            recorded_at TEXT DEFAULT (datetime('now'))
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS daily_advice_post (
            date TEXT PRIMARY KEY,
            advice TEXT NOT NULL,
            recorded_at TEXT DEFAULT (datetime('now'))
        )
    """)


def save_advice(target_date: date, text: str, mode: AdviceMode = "pre") -> None:
    iso = target_date.isoformat()
    if mode == "post":
        with _conn() as con:
            _ensure_daily_advice_schema(con)
            con.execute(
                "INSERT OR REPLACE INTO daily_advice_post (date, advice) VALUES (?, ?)",
                (iso, text),
            )
        return
    with _conn() as con:
        _ensure_daily_advice_schema(con)
        con.execute(
            "INSERT OR REPLACE INTO daily_advice (date, advice) VALUES (?, ?)",
            (iso, text),
        )


def delete_advice(target_date: date, mode: Optional[AdviceMode] = None) -> None:
    iso = target_date.isoformat()
    with _conn() as con:
        _ensure_daily_advice_schema(con)
        if mode in (None, "pre"):
            con.execute("DELETE FROM daily_advice WHERE date = ?", (iso,))
        if mode in (None, "post"):
            con.execute("DELETE FROM daily_advice_post WHERE date = ?", (iso,))
    if mode in (None, "pre"):
        try:
            set_cached_text(f"advice_mode_v1_{iso}", "")
        except Exception:
            pass
    if mode in (None, "post"):
        try:
            set_cached_text(f"advice_mode_post_v1_{iso}", "")
        except Exception:
            pass


def load_advice(target_date: date, mode: AdviceMode = "pre") -> Optional[str]:
    iso = target_date.isoformat()
    if mode == "pre":
        snap = load_morning_snapshot(target_date)
        if snap and snap.get("advice_pre"):
            return snap["advice_pre"]
        with _conn() as con:
            _ensure_daily_advice_schema(con)
            row = con.execute(
                "SELECT advice FROM daily_advice WHERE date = ?",
                (iso,),
            ).fetchone()
        return row["advice"] if row else None
    with _conn() as con:
        _ensure_daily_advice_schema(con)
        row = con.execute(
            "SELECT advice FROM daily_advice_post WHERE date = ?",
            (iso,),
        ).fetchone()
    return row["advice"] if row else None

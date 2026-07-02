"""Coach chat history, plan overrides, coach memory, and session RPE."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .db import _conn, _ensure_coach_memory_schema, _ensure_coach_schema, _ensure_rpe_schema


# ── Coach chat & plan overrides ──────────────────────────────────────────────

def save_coach_message(role: str, content: str, proposal_json: Optional[str] = None) -> None:
    with _conn() as con:
        _ensure_coach_schema(con)
        con.execute(
            "INSERT INTO coach_conversations (role, content, proposal) VALUES (?, ?, ?)",
            (role, content, proposal_json),
        )


def load_coach_history(limit: int = 30) -> list[dict]:
    with _conn() as con:
        _ensure_coach_schema(con)
        rows = con.execute(
            "SELECT id, role, content, proposal, created_at FROM coach_conversations ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def clear_coach_history() -> None:
    with _conn() as con:
        _ensure_coach_schema(con)
        con.execute("DELETE FROM coach_conversations")


def set_plan_override(date_str: str, session_type: str, label: str, duration_min: int, note: str = "") -> None:
    with _conn() as con:
        _ensure_coach_schema(con)
        con.execute(
            """INSERT OR REPLACE INTO plan_overrides (date, session_type, label, duration_min, note)
               VALUES (?, ?, ?, ?, ?)""",
            (date_str, session_type, label, duration_min, note),
        )


def get_plan_override(date_str: str) -> Optional[dict]:
    with _conn() as con:
        _ensure_coach_schema(con)
        row = con.execute(
            "SELECT * FROM plan_overrides WHERE date = ?", (date_str,)
        ).fetchone()
    return dict(row) if row else None


def list_plan_overrides() -> list[dict]:
    with _conn() as con:
        _ensure_coach_schema(con)
        rows = con.execute("SELECT * FROM plan_overrides ORDER BY date").fetchall()
    return [dict(r) for r in rows]


def delete_plan_override(date_str: str) -> None:
    with _conn() as con:
        _ensure_coach_schema(con)
        con.execute("DELETE FROM plan_overrides WHERE date = ?", (date_str,))


# ── Coach memory ──────────────────────────────────────────────────────────────

def save_session_rpe(activity_date: str, activity_id: Optional[int], rpe: int, note: Optional[str] = None) -> None:
    with _conn() as con:
        _ensure_rpe_schema(con)
        if activity_id is not None:
            con.execute(
                "INSERT OR REPLACE INTO session_rpe (date, activity_id, rpe, note) VALUES (?,?,?,?)",
                (activity_date, activity_id, rpe, note),
            )
        else:
            con.execute("DELETE FROM session_rpe WHERE date = ? AND activity_id IS NULL", (activity_date,))
            con.execute(
                "INSERT INTO session_rpe (date, activity_id, rpe, note) VALUES (?,?,?,?)",
                (activity_date, None, rpe, note),
            )


def load_session_rpe(days: int = 14) -> list[dict]:
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    with _conn() as con:
        _ensure_rpe_schema(con)
        rows = con.execute(
            "SELECT * FROM session_rpe WHERE date >= ? ORDER BY date DESC, created_at DESC",
            (start,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_coach_memory() -> Optional[dict]:
    with _conn() as con:
        _ensure_coach_memory_schema(con)
        row = con.execute("SELECT memo, updated_at FROM coach_memory WHERE id = 1").fetchone()
    return dict(row) if row else None


def set_coach_memory(memo: str) -> None:
    with _conn() as con:
        _ensure_coach_memory_schema(con)
        con.execute(
            "INSERT OR REPLACE INTO coach_memory (id, memo) VALUES (1, ?)",
            (memo,),
        )

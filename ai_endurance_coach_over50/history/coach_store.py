"""Coach chat history, plan overrides, coach memory, and session RPE."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .db import (
    _conn,
    _ensure_coach_memory_schema,
    _ensure_coach_schema,
    _ensure_commitments_schema,
    _ensure_rpe_schema,
    _ensure_session_notes_schema,
)


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


# ── Coach commitments (durable checkpoints / guardrails / decision rules) ────

def save_coach_commitment(
    title: str,
    decision_rule: Optional[str] = None,
    review_date: Optional[str] = None,
    baseline: Optional[str] = None,
) -> int:
    with _conn() as con:
        _ensure_commitments_schema(con)
        cur = con.execute(
            """INSERT INTO coach_commitments (created_date, review_date, title, decision_rule, baseline)
               VALUES (?, ?, ?, ?, ?)""",
            (date.today().isoformat(), review_date, title, decision_rule, baseline),
        )
        return int(cur.lastrowid)


def list_coach_commitments(status: Optional[str] = "open") -> list[dict]:
    with _conn() as con:
        _ensure_commitments_schema(con)
        if status:
            rows = con.execute(
                "SELECT * FROM coach_commitments WHERE status = ? ORDER BY review_date IS NULL, review_date, id",
                (status,),
            ).fetchall()
        else:
            rows = con.execute("SELECT * FROM coach_commitments ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def resolve_coach_commitment(commitment_id: int, resolution: str = "") -> bool:
    with _conn() as con:
        _ensure_commitments_schema(con)
        cur = con.execute(
            """UPDATE coach_commitments
               SET status = 'resolved', resolution = ?, resolved_at = datetime('now')
               WHERE id = ? AND status = 'open'""",
            (resolution, commitment_id),
        )
        return cur.rowcount > 0


# ── Session notes (per-date calendar-tile coaching notes) ────────────────────

def set_session_note(date_str: str, note: str) -> None:
    with _conn() as con:
        _ensure_session_notes_schema(con)
        con.execute(
            "INSERT OR REPLACE INTO session_notes (date, note) VALUES (?, ?)",
            (date_str, note),
        )


def delete_session_note(date_str: str) -> None:
    with _conn() as con:
        _ensure_session_notes_schema(con)
        con.execute("DELETE FROM session_notes WHERE date = ?", (date_str,))


def list_session_notes() -> dict[str, str]:
    """All notes as {iso_date: note} — merged over plan.COACH_NOTES by the calendar."""
    with _conn() as con:
        _ensure_session_notes_schema(con)
        rows = con.execute("SELECT date, note FROM session_notes").fetchall()
    return {r["date"]: r["note"] for r in rows}


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

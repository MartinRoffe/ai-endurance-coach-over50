"""Coach commitments + session notes: stores, action-tool dispatch, and context injection."""
from datetime import date, timedelta

from ai_endurance_coach_over50.history import (
    list_coach_commitments,
    list_session_notes,
    resolve_coach_commitment,
    save_coach_commitment,
    set_session_note,
    delete_session_note,
)


# ── Stores ────────────────────────────────────────────────────────────────────

def test_commitment_round_trip():
    cid = save_coach_commitment(
        title="Guardrail checkpoint #1 — 5 Aug FTP test",
        decision_rule="Watts within ±3% = flat; muscle 14d avg floor 63kg; tightest constraint governs.",
        review_date="2026-08-05",
        baseline="FTP 202W; muscle 14d avg 64.8kg; HRV 30d 42.2ms",
    )
    rows = list_coach_commitments("open")
    assert len(rows) == 1
    assert rows[0]["id"] == cid
    assert rows[0]["status"] == "open"
    assert "±3%" in rows[0]["decision_rule"]

    assert resolve_coach_commitment(cid, "FTP 208W (+3.0%, up); muscle held") is True
    assert list_coach_commitments("open") == []
    resolved = list_coach_commitments("resolved")
    assert len(resolved) == 1
    assert resolved[0]["resolution"].startswith("FTP 208W")
    # Resolving twice is a no-op
    assert resolve_coach_commitment(cid, "again") is False


def test_session_note_round_trip():
    set_session_note("2026-08-03", "Keep genuinely easy — FTP test Wednesday.")
    set_session_note("2026-08-04", "Light KB only.")
    notes = list_session_notes()
    assert notes["2026-08-03"].startswith("Keep genuinely easy")
    # Replace on same date
    set_session_note("2026-08-04", "Rest fully.")
    assert list_session_notes()["2026-08-04"] == "Rest fully."
    delete_session_note("2026-08-04")
    assert "2026-08-04" not in list_session_notes()


# ── Action-tool dispatch ─────────────────────────────────────────────────────

def test_action_tool_dispatch_save_and_resolve():
    from ai_endurance_coach_over50.server.coach import _dispatch_action_tool

    out = _dispatch_action_tool("save_commitment", {
        "title": "Checkpoint",
        "review_date": "2026-08-05",
        "decision_rule": "rule",
        "baseline": "FTP 202W",
    })
    assert "saved" in out.lower()
    cid = list_coach_commitments("open")[0]["id"]
    out = _dispatch_action_tool("resolve_commitment", {"commitment_id": cid, "resolution": "done"})
    assert "resolved" in out.lower()


def test_action_tool_dispatch_session_note_validates():
    from ai_endurance_coach_over50.server.coach import _dispatch_action_tool

    out = _dispatch_action_tool("add_session_note", {"date": "2026-08-03", "note": "Easy day."})
    assert "2026-08-03" in out
    assert list_session_notes()["2026-08-03"] == "Easy day."
    # Bad date must not raise
    out = _dispatch_action_tool("add_session_note", {"date": "not-a-date", "note": "x"})
    assert "failed" in out.lower()
    # Empty note saves nothing
    out = _dispatch_action_tool("add_session_note", {"date": "2026-08-06", "note": "  "})
    assert "2026-08-06" not in list_session_notes()


def test_action_tools_registered_with_coach():
    from ai_endurance_coach_over50.server import coach as coach_mod
    names = {t["name"] for t in coach_mod._ACTION_TOOLS}
    assert names == {"save_commitment", "resolve_commitment", "add_session_note"}
    assert names == coach_mod._ACTION_TOOL_NAMES


# ── Context injection ────────────────────────────────────────────────────────

def test_commitments_section_flags_due():
    from ai_endurance_coach_over50.coach_context import _section_commitments

    today = date.today()
    save_coach_commitment(title="Due checkpoint", review_date=today.isoformat())
    save_coach_commitment(title="Future checkpoint", review_date=(today + timedelta(days=30)).isoformat())
    lines = "\n".join(_section_commitments(today))
    assert "Due checkpoint" in lines and "DUE NOW" in lines
    assert "Future checkpoint" in lines
    assert lines.index("Due checkpoint") < lines.index("Future checkpoint")


def test_session_notes_section_window():
    from ai_endurance_coach_over50.coach_context import _section_session_notes

    today = date.today()
    set_session_note(today.isoformat(), "Today note")
    set_session_note((today + timedelta(days=40)).isoformat(), "Far future note")
    set_session_note((today - timedelta(days=2)).isoformat(), "Past note")
    text = "\n".join(_section_session_notes(today, days=14))
    assert "Today note" in text
    assert "Far future note" not in text
    assert "Past note" not in text


def test_key_dates_section():
    from ai_endurance_coach_over50.coach_context import _section_key_dates

    text = "\n".join(_section_key_dates(date(2026, 7, 6)))
    assert "Tenerife camp: 2026-08-13" in text
    assert "Haute Route" in text
    assert "charity" in text.lower()


def test_phase_categorisation():
    from ai_endurance_coach_over50.coach_context import _current_training_phase

    label, cat = _current_training_phase(date(2026, 7, 6))  # week 8 of the 12-week plan
    assert "12-week" in label
    label, cat = _current_training_phase(date(2026, 8, 15))
    assert cat == "camp"
    label, cat = _current_training_phase(date(2026, 9, 13))
    assert cat == "taper"
    label, cat = _current_training_phase(date(2027, 8, 20))
    assert cat == "taper" and "Haute Route" in label


def test_calendar_merges_db_notes():
    from ai_endurance_coach_over50.plan import PLAN_START, coach_notes_merged

    d = (PLAN_START + timedelta(days=1)).isoformat()
    set_session_note(d, "Pre-test reminder")
    assert coach_notes_merged()[d] == "Pre-test reminder"

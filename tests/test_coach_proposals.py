"""Coach plan-change proposal enrichment."""
from datetime import date

from ai_endurance_coach_over50.history import set_plan_override
from ai_endurance_coach_over50.server import _enrich_plan_proposal


def test_enrich_plan_proposal_shows_swap_from_base_plan():
    raw = {
        "date": "2026-06-19",
        "duration_min": 60,
        "reason": "Easy spin instead of hills",
        "session_type": "bike",
        "new_label": "Z2 Ride",
    }
    p = _enrich_plan_proposal(raw)
    assert p["current_session_label"] == "Hill Repeats"
    assert p["session_label"] == "Z2 Ride"
    assert p["current_duration_min"] == 60


def test_enrich_plan_proposal_uses_existing_override_as_current():
    set_plan_override("2026-06-20", "tempo", "Hill Repeats", 75, "prior swap")
    raw = {
        "date": "2026-06-20",
        "duration_min": 75,
        "reason": "Flat threshold work",
        "session_type": "tempo",
        "new_label": "Tempo Intervals",
    }
    p = _enrich_plan_proposal(raw)
    assert p["current_session_label"] == "Hill Repeats"
    assert p["session_label"] == "Tempo Intervals"

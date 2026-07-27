"""The /position page derives its schedule from the plans rather than hardcoding
a week, so these tests pin it to the blocks that schedule strength differently.
"""
from datetime import date, timedelta

from ai_endurance_coach_over50.server import context as ctx


def week_of(anchor: date) -> list[dict]:
    monday = anchor - timedelta(days=anchor.weekday())
    days = [ctx._position_day(monday + timedelta(days=i), anchor) for i in range(7)]
    ctx._mark_mobility(days)
    return days


def strength_weekdays(anchor: date) -> list[str]:
    return [d["weekday"] for d in week_of(anchor) if d["is_strength"]]


def test_charity_week_11_is_tue_and_thu_not_monday():
    """The old page claimed Mon + Thu. The charity plan says Tue + Thu."""
    assert strength_weekdays(date(2026, 7, 27)) == ["Tue", "Thu"]


def test_hr_base_week_1_is_thu_and_sat():
    """HR Base pairs a Thursday KB session with a 60-min Saturday gym slot."""
    week = week_of(date(2026, 10, 5))
    assert [d["weekday"] for d in week if d["is_strength"]] == ["Thu", "Sat"]
    saturday = next(d for d in week if d["weekday"] == "Sat")
    assert saturday["dur_min"] == 60
    assert saturday["label"] == "Gym — Strength"


def test_hr_build_week_is_a_single_wednesday():
    """_destack_quality() swaps Wed/Thu at import time — the derived week must
    reflect the post-swap order, not the literal in HR_TRAINING_WEEKS."""
    assert strength_weekdays(date(2027, 1, 11)) == ["Wed"]


def test_tenerife_camp_week_has_no_strength():
    week = week_of(date(2026, 8, 15))
    assert not any(d["is_strength"] for d in week)
    assert ctx._position_cadence(week) == "No strength this week"


def test_strength_days_always_resolve_to_a_spec():
    """is_strength is defined by a non-None KB spec, so the two can't disagree."""
    d = date(2026, 7, 27)
    for _ in range(400):
        day = ctx._position_day(d, d)
        assert day["is_strength"] == (ctx._strength_on(d) is not None)
        if day["is_strength"]:
            assert ctx._strength_on(d)["spec"]["exercises"]
            assert day["contains"]
        d += timedelta(days=1)


def test_mobility_is_capped_and_avoids_strength_and_key_rides():
    for anchor in (date(2026, 7, 27), date(2026, 8, 15), date(2026, 10, 5)):
        week = week_of(anchor)
        mobility = [d for d in week if d["mobility"]]
        assert len(mobility) <= ctx._POSITION_MOBILITY_TARGET
        for d in mobility:
            assert not d["is_strength"]
            assert d["type"] not in ctx._POSITION_KEY_TYPES


def test_next_strength_spans_the_tenerife_gap():
    """From mid-camp the next session is in September, and the gap is explained."""
    upcoming = ctx._next_strength(date(2026, 8, 15), limit=2)
    assert upcoming[0]["date"] == date(2026, 9, 2)
    assert upcoming[0]["days_away"] > 10
    reason = ctx._position_gap_reason(date(2026, 8, 15), date(2026, 9, 1))
    assert "Tenerife" in reason


def test_contains_summary_names_the_bolt_ons():
    from ai_endurance_coach_over50.plan import POSITION_KB_SPEC_A, POSITION_KB_SPEC_B

    assert ctx._session_contains(POSITION_KB_SPEC_A) == "20-min video + single-leg block"
    assert ctx._session_contains(POSITION_KB_SPEC_B) == "20-min video + carries"
    assert ctx._session_contains(None) == ""

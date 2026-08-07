"""Future-only filter, August Tenerife push, HR through Dec 31, KB Position FE."""
from datetime import date

from ai_endurance_coach_over50.plan import CAMP_PUSH_WORKOUTS, camp_workout_for_date
from ai_endurance_coach_over50.workouts import (
    HR_WORKOUTS_END,
    _build_strength_ruck_workout,
    _filter_schedule_from,
    _NAME_PREFIXES,
    _resolve_builder,
    _specs_for,
    _workout_schedule,
    _workout_schedule_strength_ruck,
)


def test_filter_schedule_from_drops_past_keeps_future():
    start = date(2026, 8, 8)
    raw = {
        ("Z2 Endurance", 60): ["2026-08-05", "2026-08-08", "2026-08-10"],
        ("Past Only", 45): ["2026-08-01", "2026-08-07"],
    }
    out = _filter_schedule_from(raw, start)
    assert out[("Z2 Endurance", 60)] == ["2026-08-08", "2026-08-10"]
    assert ("Past Only", 45) not in out


def test_camp_push_skips_travel_rest_and_has_builders():
    assert camp_workout_for_date(date(2026, 8, 13)) is None  # travel
    assert camp_workout_for_date(date(2026, 8, 20)) is None  # rest
    assert camp_workout_for_date(date(2026, 8, 26)) is None  # rest
    assert len(CAMP_PUSH_WORKOUTS) == 11
    for d, w in CAMP_PUSH_WORKOUTS.items():
        assert _resolve_builder(w["label"]) is not None, w["label"]
        name = f"{w['label']} {w['dur_min']}m"
        assert any(name.startswith(p) for p in _NAME_PREFIXES), name


def test_camp_teide_prefix_matches_name_prefixes():
    name = "Camp Teide 360m"
    assert any(name.startswith(p) for p in _NAME_PREFIXES)


def test_august_and_hr_appear_in_bike_schedule():
    sched = _workout_schedule()
    dates = {d for ds in sched.values() for d in ds}
    assert "2026-08-14" in dates  # Camp Leg Openers
    assert "2026-08-22" in dates  # Camp Teide
    assert "2026-08-13" not in dates  # travel
    assert "2026-10-05" in dates or any(
        d.startswith("2026-10") for d in dates
    ), "HR Base start week should be scheduled"
    assert "2026-12-31" in dates or "2026-12-30" in dates or "2026-12-28" in dates
    assert HR_WORKOUTS_END == date(2026, 12, 31)
    # Christmas Tenerife labelled day
    assert any(
        "Tenerife" in label or "Camp Finale" in label or "Teide" in label
        for (label, _dur), ds in sched.items()
        if any(d.startswith("2026-12") for d in ds)
    )


def test_kb_trunk_and_gym_are_fe_not_bike():
    assert _specs_for("recovery", "KB + Trunk", 45, 0) == [
        ("sr", "KB Position A", 0, 45)
    ]
    assert _specs_for("gym", "Gym — Strength", 60, 0) == [
        ("sr", "KB Position B", 0, 60)
    ]
    assert _specs_for("gym", "Gym — Maintenance", 45, 0) == [
        ("sr", "KB Position B", 0, 45)
    ]
    assert _resolve_builder("KB + Trunk") is None

    w = _build_strength_ruck_workout("KB Position A", 0, 45)
    assert w is not None
    assert w.workoutName == "KB Position A 45m"
    assert any(w.workoutName.startswith(p) for p in _NAME_PREFIXES)

    wb = _build_strength_ruck_workout("KB Position B", 0, 60)
    assert wb is not None
    assert wb.workoutName == "KB Position B 60m"


def test_hr_strength_in_sr_schedule_through_dec():
    sr = _workout_schedule_strength_ruck()
    dates = {d for ds in sr.values() for d in ds}
    # First KB + Trunk in HR Base is typically a Thursday in week 1 (2026-10-08)
    assert any(d.startswith("2026-10") for d in dates)
    assert any(
        kind.startswith("KB Position")
        for (kind, _wk, _dur) in sr
    )
    # No bike Recovery Spin masquerading: FE kinds only for position templates
    assert ("KB Position A", 0, 45) in sr or any(
        k[0] == "KB Position A" for k in sr
    )

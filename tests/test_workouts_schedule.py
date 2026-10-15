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
    # Year-2 HR block gated off — no Teide / sweetspot labels in Oct–Dec.
    # Fitness-plan easy rides (Z2 Easy, Long Ride Easy) are scheduled.
    labels = {label for (label, _dur) in sched}
    assert "Tenerife — Teide West" not in labels
    assert "Tenerife — Teide Full Loop" not in labels
    assert "Low Cadence Sweetspot" not in labels
    assert "2026-10-15" not in dates  # clinic day (no treatment), not pushed
    assert "2026-10-18" in dates      # clearance-week Long Ride (Easy)
    assert "2026-10-25" in dates      # first return-week Long Ride (Easy)
    assert "2026-12-24" in dates      # camp easy day, still pushed
    assert "2026-12-26" not in dates  # optional Teide day is not pushed
    # Medical pause / cancelled charity — no Sep event-prep quality
    assert "2026-09-05" not in dates
    assert "2026-09-06" not in dates
    assert HR_WORKOUTS_END == date(2026, 12, 31)


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


def test_hr_strength_not_in_sr_schedule_while_year2_gated():
    sr = _workout_schedule_strength_ruck()
    dates = {d for ds in sr.values() for d in ds}
    assert not any(d.startswith("2026-10") for d in dates)
    assert not any(d.startswith("2026-12") for d in dates)

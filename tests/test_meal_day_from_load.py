"""Meal day type and the evening plate follow the session, not the weekday map."""
from datetime import date

from ai_endurance_coach_over50.nutrition_plan import (
    _resolve_day_meals,
    cycle_week_index,
    evening_plate_target,
    meal_day_type_for_session,
    nutrition_week_context,
    today_day_type,
)
from ai_endurance_coach_over50.plan import PLAN_START


def _dinner(meals):
    return next(meal for meal in meals if meal[0] == "Dinner")


def _gap(got, target) -> int:
    kcal, _protein, carbs = got[3], got[4], got[5]
    return abs(kcal - target[0]) + abs(carbs - target[2]) * 4


def test_known_session_does_not_use_the_recovery_weekday_label():
    assert cycle_week_index(PLAN_START, date(2026, 10, 26)) == 3
    assert today_day_type(3, 0) == "recovery_weekday"
    assert meal_day_type_for_session("rest", "Rest", 3, 0, session_dur=0) == "rest"
    assert meal_day_type_for_session(
        "threshold", "Threshold — bike", 3, 1, session_dur=40,
    ) == "training"
    assert meal_day_type_for_session(
        "ruck", "Ruck 15 kg", 3, 5, session_dur=35,
    ) == "ruck"
    assert meal_day_type_for_session(
        "hike", "Easy steps", 3, 3, session_dur=30,
    ) == "training"
    assert meal_day_type_for_session(
        "long", "Long Ride (Easy)", 3, 6, session_dur=85,
    ) == "long"
    # No session: the abstract weekday map still applies.
    assert meal_day_type_for_session(None, None, 3, 1) == "recovery_weekday"


def test_evening_targets_scale_from_a_1900_kcal_day():
    assert evening_plate_target("rest", 1900) == (570, 45, 50)
    assert evening_plate_target("training", 1900) == (665, 45, 70)
    assert evening_plate_target("ruck", 1900) == (665, 45, 70)
    assert evening_plate_target("long", 1900) == (760, 45, 90)
    # A 2,200 kcal day keeps the same shape.
    assert evening_plate_target("rest", 2200) == (660, 52, 58)


def test_week_of_26_oct_labels_follow_the_scheduled_load(monkeypatch):
    import ai_endurance_coach_over50.nutrition_plan as np_mod
    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 1900)
    lines = [
        line for line in nutrition_week_context(PLAN_START, date(2026, 10, 26)).splitlines()
        if line.startswith("  Mon") or line.startswith("  Tue")
        or line.startswith("  Sat") or line.startswith("  Sun")
    ]
    by_day = {line.split()[0]: line for line in lines}
    assert "Rest day" in by_day["Mon"]
    assert "Easy day" not in by_day["Mon"]
    assert "Training day" in by_day["Tue"]
    assert "Easy day" not in by_day["Tue"]
    assert "Ruck" in by_day["Sat"]
    assert "Long ride" in by_day["Sun"]


def test_evening_plate_is_closer_to_the_load_target(monkeypatch):
    import ai_endurance_coach_over50.nutrition_plan as np_mod
    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 1900)
    # Rest and training fit a 1,900 kcal day. A long ride's on-bike food
    # shares that same day, so the Sunday steak cannot also be a 760 kcal plate.
    cases = {
        date(2026, 10, 26): "rest",
        date(2026, 10, 27): "training",
    }
    plates = {}
    for day, key in cases.items():
        meals, ctx = _resolve_day_meals(PLAN_START, day)
        assert ctx["target"]["kcal"] == 1900
        plates[key] = _dinner(meals)
    targets = {
        "rest": evening_plate_target("rest", 1900),
        "training": evening_plate_target("training", 1900),
        "long": evening_plate_target("long", 1900),
    }
    for key, plate in plates.items():
        own = _gap(plate, targets[key])
        for other, target in targets.items():
            if other == key:
                continue
            assert own < _gap(plate, target), (key, plate, targets[key], other, target)

    meals, ctx = _resolve_day_meals(PLAN_START, date(2026, 11, 1))
    assert ctx["dtype"] == "long"
    assert ctx["target"]["kcal"] == 1900
    assert abs(ctx["totals"]["kcal"] - 1900) <= 1900 * 0.05
    on_bike = next(meal for meal in meals if meal[0] == "On-bike")
    assert on_bike[3] == 332
    assert on_bike[5] == 58

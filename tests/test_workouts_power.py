"""Quality and endurance workouts use %FTP power targets when measured FTP exists."""
from datetime import date, timedelta

from ai_endurance_coach_over50.history import save_activities, save_ftp_test
from ai_endurance_coach_over50.workouts import (
    _hill_repeats,
    _long_ride,
    _over_unders,
    _sweetspot_ride,
    _tempo_intervals,
    _threshold_ride,
    _z2_endurance,
)


def _activate_power_meter(ftp_w: int = 250):
    acts = []
    for i in range(3):
        d = (date.today() - timedelta(days=i + 1)).isoformat()
        acts.append({
            "activity_id": 3000 + i,
            "date": d,
            "type_key": "cycling",
            "has_power_meter": 1,
            "avg_power_w": 180,
            "duration_seconds": 3600,
        })
    save_activities(acts)
    save_ftp_test(date.today().isoformat(), 100, 168, 175, ftp_w=ftp_w)


def _work_steps(workout):
    return workout.workoutSegments[0].workoutSteps


def test_sweetspot_uses_power_lap_when_ftp_known():
    _activate_power_meter(250)
    work = _work_steps(_sweetspot_ride(90))[1]
    assert work.targetType["workoutTargetTypeKey"] == "power.zone"
    assert work.targetValueOne == round(250 * 0.88)
    assert work.targetValueTwo == round(250 * 0.93)


def test_tempo_falls_back_to_hr_without_power():
    work = _work_steps(_tempo_intervals(75))[1]
    assert work.targetType["workoutTargetTypeKey"] == "heart.rate.zone"
    assert work.zoneNumber == 3


def test_over_unders_power_targets():
    _activate_power_meter(250)
    steps = _work_steps(_over_unders(75))
    set1 = steps[1].workoutSteps
    over, under = set1[0], set1[1]
    assert steps[1].numberOfIterations == 4
    assert over.targetType["workoutTargetTypeKey"] == "power.zone"
    assert over.targetValueOne == round(250 * 1.05)
    assert under.targetValueOne == round(250 * 0.95)
    # second set (after the 5m recovery) mirrors the first
    set2 = steps[3].workoutSteps
    assert steps[3].numberOfIterations == 4
    assert set2[0].targetValueOne == round(250 * 1.05)


def test_threshold_ride_power_targets():
    _activate_power_meter(250)
    work = _work_steps(_threshold_ride(90))[1]
    assert work.targetType["workoutTargetTypeKey"] == "power.zone"
    assert work.targetValueOne == round(250 * 0.95)
    assert work.targetValueTwo == round(250 * 1.00)


def test_hill_repeats_power_targets():
    _activate_power_meter(250)
    work = _work_steps(_hill_repeats(60))[1]
    assert work.targetType["workoutTargetTypeKey"] == "power.zone"
    assert work.targetValueOne == round(250 * 1.06)
    assert work.targetValueTwo == round(250 * 1.20)


def test_endurance_power_with_hr_backstop_description():
    _activate_power_meter(250)
    work = _work_steps(_z2_endurance(90))[1]
    assert work.targetType["workoutTargetTypeKey"] == "power.zone"
    assert work.targetValueOne == round(250 * 0.56)
    assert work.targetValueTwo == round(250 * 0.75)
    assert "HR backstop" in (work.description or "")


def test_long_ride_hr_fallback_without_ftp():
    work = _work_steps(_long_ride("Long Ride", 120))[1]
    assert work.targetType["workoutTargetTypeKey"] == "heart.rate.zone"
    assert work.zoneNumber == 2

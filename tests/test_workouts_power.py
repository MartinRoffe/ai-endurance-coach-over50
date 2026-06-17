"""Phase 5: quality workouts use %FTP power targets when measured FTP exists."""
from datetime import date, timedelta

from ai_endurance_coach_over50.history import save_activities, save_ftp_test
from ai_endurance_coach_over50.workouts import _sweetspot_ride, _tempo_intervals


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


def test_sweetspot_uses_power_lap_when_ftp_known():
    _activate_power_meter(250)
    w = _sweetspot_ride(90)
    steps = w.workoutSegments[0].workoutSteps
    work = steps[1]
    assert work.targetType["workoutTargetTypeKey"] == "power.lap"
    assert work.targetValueOne == round(250 * 0.88)
    assert work.targetValueTwo == round(250 * 0.94)


def test_tempo_falls_back_to_hr_without_power():
    w = _tempo_intervals(60)
    steps = w.workoutSegments[0].workoutSteps
    work = steps[1]
    assert work.targetType["workoutTargetTypeKey"] == "heart.rate.zone"
    assert work.zoneNumber == 4

"""FTP test watts extraction from lap splits."""
from ai_endurance_coach_over50.analysis import _extract_ftp_effort
from ai_endurance_coach_over50.analysis.intervals import _extract_ramp_ftp
from ai_endurance_coach_over50.analysis.power import _mark_workouts_stale, _try_save_ftp_from_detail
from ai_endurance_coach_over50.history import get_cached_text
from ai_endurance_coach_over50.workouts import _ramp_test


class _SplitsApi:
    def __init__(self, laps):
        self._laps = laps

    def get_activity_splits(self, activity_id):
        return {"lapDTOs": self._laps}


def test_extract_ftp_effort_hr_only():
    laps = [
        {"duration": 300, "averageHR": 140, "maxHR": 155},
        {"duration": 1200, "averageHR": 168, "maxHR": 178},
    ]
    out = _extract_ftp_effort(_SplitsApi(laps), 1)
    assert out["ftp_effort_avg_hr"] == 168
    assert out["ftp_effort_max_hr"] == 178
    assert "ftp_w" not in out


def test_extract_ftp_effort_with_power():
    laps = [
        {"duration": 300, "averageHR": 140, "maxHR": 155, "averagePower": 180},
        {"duration": 1200, "averageHR": 168, "maxHR": 178, "averagePower": 252},
    ]
    out = _extract_ftp_effort(_SplitsApi(laps), 1)
    assert out["ftp_effort_avg_hr"] == 168
    assert out["ftp_effort_avg_w"] == 252
    assert out["ftp_w"] == round(252 * 0.95)


def test_extract_ftp_effort_picks_highest_hr_lap():
    laps = [
        {"duration": 1200, "averageHR": 160, "averagePower": 230},
        {"duration": 1200, "averageHR": 170, "averagePower": 245},
    ]
    out = _extract_ftp_effort(_SplitsApi(laps), 1)
    assert out["ftp_effort_avg_w"] == 245
    assert out["ftp_w"] == round(245 * 0.95)


def test_extract_ftp_effort_structured_workout_laps():
    """Warm-up lap must not win over split 20-min effort (real 2026-07-02 shape)."""
    laps = [
        {"duration": 712, "averageHR": 142, "maxHR": 161, "averagePower": 124, "normalizedPower": 147},
        {"duration": 801, "averageHR": 151, "maxHR": 167, "averagePower": 125, "normalizedPower": 143},
        {"duration": 579, "averageHR": 178, "maxHR": 183, "averagePower": 207, "normalizedPower": 210},
        {"duration": 573, "averageHR": 184, "maxHR": 188, "averagePower": 210, "normalizedPower": 216},
        {"duration": 48, "averageHR": 183, "maxHR": 183, "averagePower": 206, "normalizedPower": 212},
        {"duration": 797, "averageHR": 150, "maxHR": 183, "averagePower": 61, "normalizedPower": 85},
    ]
    out = _extract_ftp_effort(_SplitsApi(laps), 1)
    assert out["ftp_effort_avg_w"] == 213
    assert out["ftp_w"] == round(213 * 0.95)
    assert out["ftp_effort_avg_hr"] == 181
    assert out["ftp_effort_max_hr"] == 188


def test_extract_ramp_ftp_75_rule():
    laps = [
        {"duration": 60, "averagePower": 280, "averageHR": 175, "maxHR": 182},
        {"duration": 60, "averagePower": 300, "averageHR": 180, "maxHR": 188},
        {"duration": 45, "averagePower": 200},
    ]
    out = _extract_ramp_ftp(_SplitsApi(laps), 1)
    assert out["ramp_best_1min_w"] == 300
    assert out["ftp_w"] == round(300 * 0.75)
    assert out["ftp_effort_avg_hr"] == 180


def test_extract_ramp_ftp_filters_lap_duration():
    laps = [{"duration": 30, "averagePower": 400}, {"duration": 120, "averagePower": 350}]
    assert _extract_ramp_ftp(_SplitsApi(laps), 1) == {}


def test_estimate_lthr_from_effort_discounts_20min():
    from ai_endurance_coach_over50.analysis.intervals import estimate_lthr_from_effort
    assert estimate_lthr_from_effort(181, "FTP Re-test") == round(181 * 0.95)
    assert estimate_lthr_from_effort(181, "Ramp Test") is None
    assert estimate_lthr_from_effort(None, "FTP Test") is None


def test_ramp_builder_shape():
    w = _ramp_test(45)
    steps = w.workoutSegments[0].workoutSteps
    work_steps = [s for s in steps if s.targetType.get("workoutTargetTypeKey") == "power.lap"]
    assert len(work_steps) >= 10
    assert work_steps[0].targetValueOne == 100
    assert work_steps[1].targetValueOne == 120


def test_try_save_ftp_ramp_sets_stale_flag():
    detail = {"ftp_w": 225, "ftp_effort_avg_w": 300}
    act = {"date": "2026-07-02", "activity_id": 9999}
    assert _try_save_ftp_from_detail(act, detail, "Ramp Test")
    assert get_cached_text("workouts_stale_ftp") == "225"
    _mark_workouts_stale(225)  # idempotent

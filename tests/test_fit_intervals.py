"""FIT interval metrics, stale-FTP rules, and activity matching."""
from datetime import date, datetime, timedelta, timezone

from ai_endurance_coach_over50.analysis.fit_ingest import (
    FitLap,
    FitRecord,
    FitSession,
    FitWorkoutStep,
    match_activity_by_start,
)
from ai_endurance_coach_over50.analysis.fit_intervals import (
    band_compliance,
    best_contiguous_avg_power,
    compute_interval_metrics,
    detect_stale_ftp,
    half_decoupling,
    rolling_np,
)
from ai_endurance_coach_over50.analysis.intervals import (
    _INTERVAL_CONFIG,
    _extract_interval_data,
)


def _lap(dur, hr, power, intens, step, max_hr=None):
    return {
        "duration": dur,
        "averageHR": hr,
        "maxHR": max_hr or hr + 5,
        "averagePower": power,
        "intensityType": intens,
        "wktStepIndex": step,
    }


def test_low_cadence_ride_in_interval_config():
    assert "Low Cadence Ride" in _INTERVAL_CONFIG
    cfg = _INTERVAL_CONFIG["Low Cadence Ride"]
    assert cfg["effort_min"] <= 480 <= cfg["effort_max"]


def test_extract_low_cadence_four_blocks():
    laps = [
        _lap(600, 120, 100, "WARMUP", 0),
        _lap(480, 140, 159, "ACTIVE", 1),
        _lap(180, 125, 80, "RECOVERY", 2),
        _lap(480, 142, 168, "ACTIVE", 3),
        _lap(180, 128, 85, "RECOVERY", 4),
        _lap(480, 131, 138, "ACTIVE", 5),
        _lap(180, 126, 80, "RECOVERY", 6),
        _lap(480, 135, 151, "ACTIVE", 7),
        _lap(600, 122, 110, "COOLDOWN", 8),
    ]

    class _Api:
        def get_activity_splits(self, activity_id):
            return {"lapDTOs": laps}

    result = _extract_interval_data(_Api(), 1, "Low Cadence Ride", "road_biking")
    reps = result["interval_reps"]
    assert len(reps) == 4
    assert [r["avg_power_w"] for r in reps] == [159, 168, 138, 151]


def test_rolling_np_flat_stream():
    powers = [200.0] * 60
    np_val = rolling_np(powers, window=30)
    assert np_val is not None
    assert abs(np_val - 200.0) < 0.5


def test_half_decoupling_rising_hr_flat_power():
    powers = [200.0] * 600
    hrs = [140.0] * 300 + [154.0] * 300  # +10% HR
    d = half_decoupling(powers, hrs)
    assert d is not None
    assert abs(d - 10.0) < 0.5


def test_half_decoupling_skips_short_or_coasting():
    assert half_decoupling([200.0] * 40, [140.0] * 40) is None  # <5 min
    hrs = [140.0] * 300
    # Second-half coast
    assert half_decoupling([150.0] * 150 + [5.0] * 150, hrs) is None
    # First-half near-zero power
    assert half_decoupling([5.0] * 150 + [150.0] * 150, hrs) is None


def test_long_z2_ignores_post_cooldown_autolaps():
    """Regression: untagged auto-laps after COOLDOWN must not overwrite ACTIVE."""
    t0 = datetime(2026, 8, 2, 5, 27, tzinfo=timezone.utc)
    records: list[FitRecord] = []
    # 15 min warmup + 60 min active + 15 min cooldown + 12 min free
    for i in range(15 * 60):
        records.append(FitRecord(t0 + timedelta(seconds=i), power=120, hr=125, cadence=75))
    t_act = t0 + timedelta(seconds=15 * 60)
    for i in range(60 * 60):
        records.append(FitRecord(t_act + timedelta(seconds=i), power=140, hr=138, cadence=78))
    t_cd = t_act + timedelta(seconds=60 * 60)
    for i in range(15 * 60):
        records.append(FitRecord(t_cd + timedelta(seconds=i), power=90, hr=130, cadence=72))
    t_free = t_cd + timedelta(seconds=15 * 60)
    for i in range(12 * 60):
        records.append(FitRecord(t_free + timedelta(seconds=i), power=100, hr=135, cadence=70))
    # trailing coast fragment
    t_coast = t_free + timedelta(seconds=12 * 60)
    for i in range(140):
        records.append(FitRecord(t_coast + timedelta(seconds=i), power=20, hr=125, cadence=15))

    laps = [
        FitLap(start_time=t0, total_elapsed=15 * 60, wkt_step_index=0, intensity=None),
        FitLap(start_time=t_act, total_elapsed=60 * 60, wkt_step_index=1, intensity=None),
        FitLap(start_time=t_cd, total_elapsed=15 * 60, wkt_step_index=2, intensity=None),
        # Post-workout auto-laps: no step, no intensity (the bug case)
        FitLap(start_time=t_free, total_elapsed=12 * 60, wkt_step_index=None, intensity=None),
        FitLap(start_time=t_coast, total_elapsed=140, wkt_step_index=None, intensity=None),
    ]
    steps = [
        FitWorkoutStep(message_index=0, intensity="WARMUP"),
        FitWorkoutStep(
            message_index=1, intensity="ACTIVE",
            custom_target_low=120, custom_target_high=160,
        ),
        FitWorkoutStep(message_index=2, intensity="COOLDOWN"),
    ]
    fit = FitSession(start_time=t0, records=records, laps=laps, workout_steps=steps)
    intervals = compute_interval_metrics(fit, ftp_w=214)
    assert len(intervals) == 1
    assert intervals[0]["duration_secs"] == 3600
    assert intervals[0]["work_num"] == 1
    assert 130 <= (intervals[0]["avg_power_w"] or 0) <= 150
    assert intervals[0]["band_pct_in"] is not None


def test_band_compliance():
    powers = [180, 190, 200, 210, 220]
    band = band_compliance(powers, 190, 210)
    assert band["pct_in"] == 60.0  # 190,200,210
    assert band["pct_below"] == 20.0
    assert band["pct_above"] == 20.0


def test_best_contiguous_avg_power():
    powers = [100.0] * 100 + [250.0] * 1200 + [100.0] * 100
    best = best_contiguous_avg_power(powers, 1200)
    assert best is not None
    assert abs(best - 250.0) < 0.01


def _synthetic_2x20(ftp: int = 202, p1: float = 216, p2: float = 214) -> FitSession:
    """Build a FIT-like session with two 20-min ACTIVE steps."""
    t0 = datetime(2026, 7, 22, 7, 0, tzinfo=timezone.utc)
    records: list[FitRecord] = []
    # warm-up 10 min
    for i in range(600):
        records.append(FitRecord(t0 + timedelta(seconds=i), power=120, hr=120, cadence=80, temperature=26))
    # interval 1
    t1 = t0 + timedelta(seconds=600)
    for i in range(1200):
        records.append(FitRecord(t1 + timedelta(seconds=i), power=p1, hr=170, cadence=85, temperature=27))
    # recovery 8 min
    t_r = t1 + timedelta(seconds=1200)
    for i in range(480):
        records.append(FitRecord(t_r + timedelta(seconds=i), power=100, hr=130, cadence=80, temperature=27))
    # interval 2
    t2 = t_r + timedelta(seconds=480)
    for i in range(1200):
        records.append(FitRecord(t2 + timedelta(seconds=i), power=p2, hr=172, cadence=85, temperature=28))

    laps = [
        FitLap(start_time=t0, total_elapsed=600, wkt_step_index=0, intensity="WARMUP"),
        FitLap(start_time=t1, total_elapsed=1200, wkt_step_index=1, intensity="ACTIVE"),
        FitLap(start_time=t_r, total_elapsed=480, wkt_step_index=2, intensity="RECOVERY"),
        FitLap(start_time=t2, total_elapsed=1200, wkt_step_index=3, intensity="ACTIVE"),
    ]
    steps = [
        FitWorkoutStep(message_index=0, intensity="WARMUP"),
        FitWorkoutStep(message_index=1, intensity="ACTIVE",
                       custom_target_low=ftp * 0.95, custom_target_high=ftp),
        FitWorkoutStep(message_index=2, intensity="RECOVERY"),
        FitWorkoutStep(message_index=3, intensity="ACTIVE",
                       custom_target_low=ftp * 0.95, custom_target_high=ftp),
    ]
    return FitSession(
        start_time=t0,
        records=records,
        laps=laps,
        workout_steps=steps,
        device_ftp=214,
        device_max_hr=186,
        device_lthr=181,
    )


def test_stale_ftp_two_x_twenty_strong_finish():
    fit = _synthetic_2x20(ftp=202, p1=225, p2=226)
    intervals = compute_interval_metrics(fit, ftp_w=202)
    work = [i for i in intervals if (i.get("duration_secs") or 0) >= 19 * 60]
    assert len(work) >= 2
    stale = detect_stale_ftp(intervals, fit.records, 202)
    assert stale is not None
    # max(best20×0.95, 2×20 mean×0.97) — mean 225.5×0.97 ≈ 219
    assert stale["proposed_ftp_w"] >= 214
    assert stale["proposed_ftp_w"] > 202
    assert stale["two_x_twenty"] is True


def test_stale_ftp_just_below_103_pct_no_flag():
    # 102% of 202 = 206 — should NOT trigger
    fit = _synthetic_2x20(ftp=202, p1=206, p2=206)
    intervals = compute_interval_metrics(fit, ftp_w=202)
    stale = detect_stale_ftp(intervals, fit.records, 202)
    assert stale is None


def test_stale_ftp_fade_on_second_interval_no_2x20_flag():
    # Both supra but second fades — still may flag via ≥19 min >103% rule
    fit = _synthetic_2x20(ftp=202, p1=220, p2=210)
    intervals = compute_interval_metrics(fit, ftp_w=202)
    stale = detect_stale_ftp(intervals, fit.records, 202)
    assert stale is not None
    assert stale["two_x_twenty"] is False


def test_match_activity_by_start_within_two_minutes():
    start = datetime(2026, 7, 22, 7, 0, tzinfo=timezone.utc)
    acts = [
        {"activity_id": 1, "start_time": "2026-07-22T07:01:30+00:00"},
        {"activity_id": 2, "start_time": "2026-07-22T08:00:00+00:00"},
    ]
    matched = match_activity_by_start(start, acts, window_sec=120)
    assert matched is not None
    assert matched["activity_id"] == 1


def test_match_activity_by_start_outside_window():
    start = datetime(2026, 7, 22, 7, 0, tzinfo=timezone.utc)
    acts = [{"activity_id": 1, "start_time": "2026-07-22T07:05:00+00:00"}]
    assert match_activity_by_start(start, acts, window_sec=120) is None


def test_match_activity_naive_local_vs_fit_utc(monkeypatch):
    """Garmin startTimeLocal is naive local; FIT start is UTC (BST = +1h)."""
    from ai_endurance_coach_over50.analysis import fit_ingest as fi

    bst = timezone(timedelta(hours=1))
    monkeypatch.setattr(fi, "_local_tz", lambda: bst)

    fit_start = datetime(2026, 8, 2, 5, 27, 19, tzinfo=timezone.utc)
    acts = [{"activity_id": 23823077329, "start_time": "2026-08-02 06:27:19"}]
    matched = match_activity_by_start(fit_start, acts, window_sec=120)
    assert matched is not None
    assert matched["activity_id"] == 23823077329


def test_activity_id_from_filename():
    from ai_endurance_coach_over50.analysis.fit_ingest import activity_id_from_filename
    assert activity_id_from_filename("23823077329_ACTIVITY.fit") == 23823077329
    assert activity_id_from_filename("/tmp/23823077329_ACTIVITY.FIT") == 23823077329
    assert activity_id_from_filename("random.fit") is None

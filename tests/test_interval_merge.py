"""Same-step ACTIVE lap merges for structured interval mining."""
from ai_endurance_coach_over50.analysis.intervals import (
    _extract_interval_data,
    _lap_dur,
    _merge_same_step_laps,
    _work_laps_from_steps,
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


# Today's Sweetspot Ride shape: each 15-min ACTIVE step split into ~10 + ~5.
_SWEETSPOT_LAPS = [
    _lap(787, 137, 138, "WARMUP", 0),
    _lap(113, 143, 123, "WARMUP", 0),
    _lap(653, 158, 191, "ACTIVE", 1, max_hr=165),
    _lap(247, 156, 173, "ACTIVE", 1, max_hr=159),
    _lap(300, 139, 101, "RECOVERY", 2),
    _lap(600, 161, 189, "ACTIVE", 3, max_hr=173),
    _lap(300, 156, 167, "ACTIVE", 3, max_hr=160),
    _lap(300, 145, 125, "RECOVERY", 4),
    _lap(599, 158, 185, "ACTIVE", 5, max_hr=169),
    _lap(301, 162, 194, "ACTIVE", 5, max_hr=165),
    _lap(675, 131, 52, "COOLDOWN", 6),
]


class _SplitsApi:
    def __init__(self, laps):
        self._laps = laps

    def get_activity_splits(self, activity_id):
        return {"lapDTOs": self._laps}


def test_merge_same_step_collapses_split_active_blocks():
    active = [l for l in _SWEETSPOT_LAPS if l["intensityType"] == "ACTIVE"]
    merged = _merge_same_step_laps(active)
    assert len(merged) == 3
    assert [round(_lap_dur(m)) for m in merged] == [900, 900, 900]
    assert round(merged[0]["averagePower"]) == 186  # (191*653 + 173*247) / 900
    assert round(merged[1]["averagePower"]) == 182
    assert round(merged[2]["averagePower"]) == 188


def test_merge_leaves_unindexed_laps_alone():
    laps = [
        _lap(600, 160, 190, "ACTIVE", None),
        _lap(600, 162, 188, "ACTIVE", None),
    ]
    assert len(_merge_same_step_laps(laps)) == 2


def test_work_laps_from_steps_returns_three_sweetspot_blocks():
    work = _work_laps_from_steps(_SWEETSPOT_LAPS)
    assert work is not None
    assert len(work) == 3
    assert all(round(_lap_dur(l)) == 900 for l in work)


def test_extract_interval_data_three_reps():
    result = _extract_interval_data(
        _SplitsApi(_SWEETSPOT_LAPS), 1, "Sweetspot Ride", "road_biking"
    )
    reps = result["interval_reps"]
    assert len(reps) == 3
    assert [r["duration_secs"] for r in reps] == [900, 900, 900]
    assert [r["avg_power_w"] for r in reps] == [186, 182, 188]
    assert reps[0]["name"] == "Sweetspot block"

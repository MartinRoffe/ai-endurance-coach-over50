"""Haute Route power targets and builder resolution."""
from ai_endurance_coach_over50.hr_plan import (
    HR_TRAINING_WEEKS,
    build_hr_calendar_weeks,
    power_target_for,
    power_watts_range,
)
from ai_endurance_coach_over50.server.projection import _hr_ctl_projection
from ai_endurance_coach_over50.workouts import _resolve_builder


def test_every_non_rest_type_has_power_target():
    types = {s[0] for w in HR_TRAINING_WEEKS for s in w if s[0] not in ("rest", "gym")}
    for stype in types:
        assert stype in {
            "endurance", "sweetspot", "tempo", "vo2", "ftp", "long", "back_to_back", "recovery",
        }
        sample = next(s for w in HR_TRAINING_WEEKS for s in w if s[0] == stype)
        assert power_target_for(stype, sample[1]) is not None


def test_hr_ctl_projection_unchanged_by_metadata():
    before = _hr_ctl_projection(200.0)
    weeks = build_hr_calendar_weeks()
    assert weeks[0]["planned_tss"] > 0
    after = _hr_ctl_projection(200.0)
    assert before == after


def test_every_distinct_hr_label_resolves_builder():
    labels = sorted({s[1] for w in HR_TRAINING_WEEKS for s in w if s[0] not in ("rest", "gym")})
    missing = [l for l in labels if not _resolve_builder(l)]
    assert missing == [], f"missing builders: {missing}"


def test_watt_math_at_fixture_ftp():
    assert power_watts_range(250, (88, 94)) == "220–235 W (88–94% FTP)"
    assert power_watts_range(250, "alternate 95%/105% FTP") == "alternate 95%/105% FTP"

"""HR profile fetch, cache, and coach context formatting."""
from ai_endurance_coach_over50.coach_context import build_coach_context
from ai_endurance_coach_over50.history import save_ftp_test, set_cached_text
from ai_endurance_coach_over50.hr_profile import (
    _parse_garmin_zones,
    fetch_hr_profile,
    format_hr_profile_lines,
    save_hr_profile,
)


GARMIN_SAMPLE = [
    {
        "trainingMethod": "HR_RESERVE",
        "restingHeartRateUsed": 62,
        "lactateThresholdHeartRateUsed": None,
        "zone1Floor": 126,
        "zone2Floor": 139,
        "zone3Floor": 152,
        "zone4Floor": 164,
        "zone5Floor": 177,
        "maxHeartRateUsed": 190,
        "sport": "CYCLING",
    },
    {
        "trainingMethod": "HR_RESERVE",
        "restingHeartRateUsed": 62,
        "zone1Floor": 126,
        "zone2Floor": 139,
        "zone3Floor": 152,
        "zone4Floor": 164,
        "zone5Floor": 177,
        "maxHeartRateUsed": 190,
        "sport": "DEFAULT",
    },
]


def test_parse_garmin_cycling_zones():
    parsed = _parse_garmin_zones(GARMIN_SAMPLE, "CYCLING")
    assert parsed is not None
    assert parsed["max_hr"] == 190
    assert parsed["resting_hr"] == 62
    assert parsed["method"] == "HR_RESERVE"
    assert parsed["zones"][0] == {"zone": 1, "lo": 126, "hi": 138}
    assert parsed["zones"][4] == {"zone": 5, "lo": 177, "hi": 190}


def test_format_hr_profile_includes_garmin_and_lthr():
    save_ftp_test("2026-05-01", 12345, 158, 172)
    profile = {
        "garmin": _parse_garmin_zones(GARMIN_SAMPLE, "CYCLING"),
        "lthr_test": {
            "lthr": 158,
            "date": "2026-05-01",
            "max_hr": 172,
            "zones": [
                {"zone": 1, "label": "Recovery", "lo": None, "hi": 133},
                {"zone": 2, "label": "Endurance", "lo": 134, "hi": 141},
                {"zone": 3, "label": "Tempo", "lo": 142, "hi": 148},
                {"zone": 4, "label": "Threshold", "lo": 150, "hi": 156},
                {"zone": 5, "label": "VO2max", "lo": 158, "hi": None},
            ],
        },
    }
    save_hr_profile(profile)
    lines = format_hr_profile_lines(resting_hr_today=58.0)
    text = "\n".join(lines)
    assert "## Heart Rate Reference" in text
    assert "max HR 190bpm" in text
    assert "Z1: 126" in text
    assert "FTP test LTHR: 158bpm" in text
    assert "Today's resting HR" in text
    assert "58bpm" in text


def test_build_coach_context_includes_hr_reference():
    save_ftp_test("2026-05-01", 12345, 158, 172)
    save_hr_profile({"garmin": _parse_garmin_zones(GARMIN_SAMPLE, "CYCLING")})
    ctx = build_coach_context()
    assert "## Heart Rate Reference" in ctx
    assert "max HR 190bpm" in ctx


def test_fetch_hr_profile_merges_garmin_and_ftp(monkeypatch):
    save_ftp_test("2026-06-01", 999, 160, 175)

    class FakeApi:
        def connectapi(self, url):
            assert url == "/biometric-service/heartRateZones/"
            return GARMIN_SAMPLE

    profile = fetch_hr_profile(FakeApi())
    assert profile["garmin"]["max_hr"] == 190
    assert profile["lthr_test"]["lthr"] == 160

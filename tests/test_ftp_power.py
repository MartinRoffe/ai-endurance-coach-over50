"""FTP test watts extraction from lap splits."""
from ai_endurance_coach_over50.analysis import _extract_ftp_effort


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

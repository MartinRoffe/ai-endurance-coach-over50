"""Phase 5: coach context and system prompt when power meter active."""
from datetime import date, timedelta

from ai_endurance_coach_over50.history import (
    save_activities,
    save_body_metrics,
    save_ftp_test,
    save_power_durability,
)
from ai_endurance_coach_over50.server import _build_coach_context, _coach_system


def _seed_power_rides(n: int = 3):
    acts = []
    for i in range(n):
        d = (date.today() - timedelta(days=i + 1)).isoformat()
        acts.append({
            "activity_id": 1000 + i,
            "date": d,
            "type_key": "road_biking",
            "has_power_meter": 1,
            "avg_power_w": 180,
            "duration_seconds": 3600,
        })
    save_activities(acts)


def test_coach_system_power_active():
    _seed_power_rides()
    text = _coach_system()
    assert "power meter" in text
    assert "watts for climb and interval" in text
    assert "NO RUNNING" in text


def test_coach_system_hr_only_without_power():
    text = _coach_system()
    assert "no power meter" in text.lower() or "not power" in text.lower()


def test_build_coach_context_includes_power_sections():
    _seed_power_rides()
    save_body_metrics([{"date": date.today().isoformat(), "weight_kg": 78.0}])
    save_ftp_test(date.today().isoformat(), 200, 168, 175, ftp_w=250)
    save_power_durability(2001, {
        "date": date.today().isoformat(),
        "duration_min": 120,
        "first_third_hr": 140.0,
        "final_third_hr": 148.0,
        "first_third_power": 200.0,
        "final_third_power": 195.0,
        "hr_drift_pct": 5.7,
        "power_drift_pct": -2.5,
        "decoupling_pct": 8.2,
        "n_laps": 4,
    })
    ctx = _build_coach_context()
    assert "Measured FTP / W/kg" in ctx
    assert "Pw:HR Decoupling" in ctx
    assert "FTP 250W" in ctx

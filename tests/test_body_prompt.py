"""Body-composition prompt must build after the A-event date change."""
from ai_endurance_coach_over50.report import _build_body_prompt


def test_body_prompt_projects_weight_to_a_event():
    rows = [
        {"date": "2026-08-01", "weight_kg": 80.0, "fat_pct": 20.0, "muscle_mass_kg": 35.0},
        {"date": "2026-09-01", "weight_kg": 79.0, "fat_pct": 19.5, "muscle_mass_kg": 35.1},
        {"date": "2026-10-01", "weight_kg": 78.0, "fat_pct": 19.0, "muscle_mass_kg": 35.2},
    ]
    text = _build_body_prompt(rows, rows[-1], {"ctl": 40, "atl": 30, "tsb": 10}, [])
    assert "Projected weight at" in text
    assert "weeks_to_tenerife" not in text
    assert "Tenerife" not in text

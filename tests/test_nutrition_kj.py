"""kJ-grounded nutrition helpers."""
from ai_endurance_coach_over50.energy import planned_session_kj, ride_kcal_from_kj, ride_kj
from ai_endurance_coach_over50.nutrition_plan import adjust_for_session_kj


def test_ride_kj_one_hour_at_200w():
    assert ride_kj(200, 3600) == 720.0


def test_ride_kcal_from_kj_approx_one_to_one():
    assert ride_kcal_from_kj(720) == 720


def test_planned_session_kj_midpoint():
    kj = planned_session_kj(250, 56, 75, 90)
    # 90 min at ~65.5% FTP midpoint → ~884 kJ
    assert 850 < kj < 920


def test_adjust_for_session_kj_annotation():
    out = adjust_for_session_kj(2350, 400)
    assert out["tier_kcal"] == 2350
    assert "400 kJ" in out["note"]

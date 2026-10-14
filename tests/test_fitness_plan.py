"""12-month fitness block: sessions, camp cap, Garmin filter, cut window."""
from datetime import date

from fastapi.testclient import TestClient

from ai_endurance_coach_over50.energy import active_cut_phase, in_maintenance_window, intake_target_kcal
from ai_endurance_coach_over50.server import app
from ai_endurance_coach_over50.fitness_plan import (
    GRAVEL_BIKE_ACTIVE,
    HOME_SUNDAY_CAP_MIN,
    PLAN_END,
    PLAN_START,
    garmin_allowed,
    guide_phases,
    session_for_date,
)
from ai_endurance_coach_over50.medical import XMAS_CAMP_TENTATIVE, YEAR2_PLAN_ACTIVE, should_push_garmin_date
from ai_endurance_coach_over50.plan import session_for_date_extended
from ai_endurance_coach_over50.workouts import _workouts_for_date


def test_procedure_day_is_rest_and_not_pushed():
    sess = session_for_date_extended(date(2026, 10, 15))
    assert sess == ("rest", "Procedure day", 0)
    assert not should_push_garmin_date(date(2026, 10, 15))
    assert _workouts_for_date(date(2026, 10, 15)) == []


def test_december_sunday_reaches_the_cap():
    mid = session_for_date(date(2026, 12, 13))
    assert mid == ("long", "Long Ride (Easy)", 165)
    cap = session_for_date(date(2026, 12, 20))
    assert cap == ("long", "Long Ride (Easy)", HOME_SUNDAY_CAP_MIN)
    assert HOME_SUNDAY_CAP_MIN == 180


def test_camp_day_stays_on_the_cap_and_teide_is_absent():
    assert not XMAS_CAMP_TENTATIVE
    camp = session_for_date_extended(date(2026, 12, 26))
    assert camp == ("long", "Long Ride (Easy)", 180)
    assert camp[2] <= HOME_SUNDAY_CAP_MIN
    assert garmin_allowed(date(2026, 12, 26), camp[0], camp[1])
    assert _workouts_for_date(date(2026, 12, 26)) == [("bike", "Long Ride (Easy)", 180)]
    # Old grid is not what this date returns.
    assert "Teide" not in camp[1]


def test_busar_weekend_replaces_the_last_keswick_ruck():
    sat = session_for_date_extended(date(2027, 2, 20))
    sun = session_for_date_extended(date(2027, 2, 21))
    assert sat[0] == "hike" and "BUSAR" in sat[1]
    assert sun[0] == "hike" and "BUSAR" in sun[1]
    assert "pack test" in sat[1]
    assert not garmin_allowed(date(2027, 2, 20), sat[0], sat[1])
    assert _workouts_for_date(date(2027, 2, 20)) == []
    assert _workouts_for_date(date(2027, 2, 21)) == []


def test_keswick_saturday_is_on_foot_and_not_pushed():
    sess = session_for_date_extended(date(2027, 2, 27))
    assert sess[0] == "hike"
    assert "Skiddaw" in sess[1]
    assert not garmin_allowed(date(2027, 2, 27), sess[0], sess[1])
    assert _workouts_for_date(date(2027, 2, 27)) == []
    sun = session_for_date(date(2027, 2, 28))
    assert sun[0] == "hike"
    assert "Blencathra" in sun[1]


def test_race_quality_override_label_is_not_pushed():
    assert not garmin_allowed(date(2026, 12, 20), "sweetspot", "Low Cadence Sweetspot")
    assert not garmin_allowed(date(2026, 12, 26), "long", "Tenerife — Teide West")


def test_cut_is_maintenance_through_camp_and_off_after():
    assert in_maintenance_window(date(2026, 10, 9))
    assert in_maintenance_window(date(2027, 1, 3))
    assert intake_target_kcal(2400, "training", ref_date=date(2026, 10, 9)) == 2400
    assert not in_maintenance_window(date(2027, 1, 4))
    assert active_cut_phase(date(2027, 1, 4)) == "ease"
    assert active_cut_phase(date(2027, 4, 1)) is None
    # Standing day-type deficit, not the suspended hard cut (450).
    assert intake_target_kcal(2400, "training", ref_date=date(2027, 1, 4)) == 2150


def test_guide_covers_the_block_in_phase_order():
    phases = guide_phases()
    assert [p["name"] for p in phases] == [
        "Procedure", "Return", "Tenerife", "Keswick build",
        "Lakes", "Recovery", "Scotland", "Maintenance",
    ]
    assert phases[0]["start"] == PLAN_START
    assert phases[-1]["end"] == PLAN_END
    ret = phases[1]
    assert ret["days"][2]["text"].startswith("Z2 Easy")
    assert "45m–1h15m" in ret["days"][2]["text"] or "45m–75m" in ret["days"][2]["text"]
    assert phases[3]["weeks"]
    assert any("14 kg" in w["text"] for w in phases[3]["weeks"])
    assert "BUSAR" in phases[3]["weeks"][-1]["text"]


def test_guide_and_charity_archive_routes():
    client = TestClient(app)
    live = client.get("/training")
    assert live.status_code == 200
    assert "FITNESS" in live.text
    assert "Keswick build" in live.text
    assert "/training/charity" in live.text
    old = client.get("/training/charity")
    assert old.status_code == 200
    assert "Archive" in old.text
    assert "BACK IN" in old.text


def test_later_gates_stay_off():
    assert GRAVEL_BIKE_ACTIVE is False
    assert YEAR2_PLAN_ACTIVE is False
    assert session_for_date(date(2027, 8, 23))[0] != "sweetspot"
    assert "VO2" not in session_for_date(date(2027, 8, 23))[1]

"""Agreed restart: week of 19 Oct and week of 26 Oct 2026."""
from datetime import date

from ai_endurance_coach_over50.fitness_plan import session_for_date
from ai_endurance_coach_over50.plan import session_for_date_extended
from ai_endurance_coach_over50.report import _planned_session_html
from ai_endurance_coach_over50.safety import is_hard
from ai_endurance_coach_over50.session_detail import day_detail


def test_week_of_19_oct_matches_the_agreed_weekend():
    assert session_for_date(date(2026, 10, 19)) == ("rest", "Rest", 0)
    assert session_for_date(date(2026, 10, 20)) == ("rower", "Threshold — rower", 40)
    assert session_for_date(date(2026, 10, 21))[0] == "strength"
    assert session_for_date(date(2026, 10, 22)) == ("hike", "Easy steps", 32)
    assert session_for_date(date(2026, 10, 23)) == ("rest", "Rest", 0)
    sat = session_for_date(date(2026, 10, 24))
    assert sat[0] == "ruck"
    assert "10 kg" in sat[1]
    assert "flat" in sat[1].lower()
    assert 35 <= sat[2] <= 40
    sun = session_for_date(date(2026, 10, 25))
    assert sun == ("long", "Long Ride (Easy) · outdoor", 60)
    assert session_for_date_extended(date(2026, 10, 25)) == sun


def test_saturday_24_oct_detail_is_a_flat_easy_ruck():
    detail = day_detail(date(2026, 10, 24))
    blob = " ".join(
        [detail["title"], detail["purpose"], detail["ruck_route"], detail["ruck_elevation"]]
        + [b["detail"] for b in detail["blocks"]]
    ).lower()
    assert detail["ruck_pack"] == "10 kg"
    assert "flat" in blob
    assert "easy" in blob
    assert "35" in blob and "40" in blob
    assert "15 kg hill" not in detail["purpose"].lower() or "not the 15 kg" in detail["purpose"].lower()


def test_week_of_26_oct_matches_the_agreed_sessions():
    assert session_for_date(date(2026, 10, 26)) == ("rest", "Rest", 0)
    tue = session_for_date(date(2026, 10, 27))
    assert tue == ("maxiclimber", "Threshold — MaxiClimber", 40)
    assert is_hard(tue)
    assert session_for_date(date(2026, 10, 28))[0] == "strength"
    thu = session_for_date(date(2026, 10, 29))
    assert thu == ("maxiclimber", "Z2 — MaxiClimber", 30)
    assert not is_hard(thu)
    assert "vo2" not in thu[1].lower()
    assert session_for_date(date(2026, 10, 30)) == ("rest", "Rest", 0)
    assert session_for_date(date(2026, 10, 31)) == ("ruck", "Ruck 10 kg", 35)
    sun = session_for_date(date(2026, 11, 1))
    assert sun[0] == "long"
    assert sun[2] == 85
    assert "easy" in sun[1].lower()


def test_tuesday_27_oct_is_five_by_four_at_rpe_7():
    detail = day_detail(date(2026, 10, 27))
    text = " ".join(b["detail"] for b in detail["blocks"])
    assert "10 min" in text
    assert "5 × 4 min" in text
    assert "RPE 7" in text
    assert "2 min easy" in text
    assert "5 min" in text
    assert detail["duration_min"] == 40


def test_sunday_rides_say_zone_1_to_2():
    for day in (date(2026, 10, 25), date(2026, 11, 1)):
        detail = day_detail(day)
        assert "zone 1–2" in detail["purpose"].lower()
        assert "easy" in detail["purpose"].lower()


def test_email_shows_the_agreed_labels():
    sat = _planned_session_html(date(2026, 10, 24))
    assert "10 kg" in sat
    assert "flat easy" in sat.lower()
    tue = _planned_session_html(date(2026, 10, 27))
    assert "MaxiClimber" in tue
    assert "Threshold" in tue
    thu = _planned_session_html(date(2026, 10, 29))
    assert "MaxiClimber" in thu
    assert "VO2" not in thu
    sun = _planned_session_html(date(2026, 10, 25))
    assert ">1h</span>" in sun
    nov = _planned_session_html(date(2026, 11, 1))
    assert "1h25m" in nov or "85m" in nov

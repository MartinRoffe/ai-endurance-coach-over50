"""Weekly Saturday ruck pack is 10 kg. Time progresses; the pack does not.

The 13 Feb pack-test rehearsal stays 20.4 kg. BUSAR and the Lake District
weekend keep their own loads.
"""
from datetime import date, timedelta

from ai_endurance_coach_over50.fitness_plan import (
    PLAN_END,
    PLAN_START,
    WEEKLY_RUCK_PACK_KG,
    session_for_date,
    weekly_ruck_label,
)
from ai_endurance_coach_over50.report import _planned_session_html
from ai_endurance_coach_over50.server.coach import _coach_system
from ai_endurance_coach_over50.session_detail import day_detail
from ai_endurance_coach_over50.workouts import (
    _build_strength_ruck_workout,
    _specs_for,
    _workout_schedule_strength_ruck,
)


def test_weekly_ruck_pack_constant_is_10kg():
    assert WEEKLY_RUCK_PACK_KG == 10
    assert weekly_ruck_label() == "Ruck 10 kg"
    assert weekly_ruck_label("flat easy") == "Ruck 10 kg — flat easy"


def test_saturday_rucks_use_the_constant_and_keep_their_durations():
    expected = {
        date(2026, 10, 24): ("ruck", "Ruck 10 kg — flat easy", 40),
        date(2026, 10, 31): ("ruck", "Ruck 10 kg", 35),
        date(2026, 11, 7): ("ruck", "Ruck 10 kg", 35),
        date(2026, 11, 14): ("ruck", "Ruck 10 kg", 30),
        date(2026, 11, 21): ("ruck", "Ruck 10 kg", 25),
        date(2026, 11, 28): ("ruck", "Ruck 10 kg", 45),
        date(2026, 12, 5): ("ruck", "Ruck 10 kg", 35),
        date(2026, 12, 12): ("ruck", "Ruck 10 kg", 55),
        date(2026, 12, 19): ("ruck", "Ruck 10 kg", 65),
        date(2027, 1, 9): ("ruck", "Ruck 10 kg", 50),
        date(2027, 1, 16): ("ruck", "Ruck 10 kg", 60),
        date(2027, 1, 23): ("ruck", "Ruck 10 kg", 70),
        date(2027, 1, 30): ("ruck", "Ruck 10 kg", 50),
        date(2027, 2, 6): ("ruck", "Ruck 10 kg", 70),
        date(2027, 4, 3): ("ruck", "Ruck 10 kg", 90),
        date(2027, 4, 24): ("ruck", "Ruck 10 kg", 60),
    }
    for day, sess in expected.items():
        assert session_for_date(day) == sess

    day = PLAN_START
    while day <= PLAN_END:
        sess = session_for_date(day)
        if sess and sess[0] == "ruck" and "rehearsal" not in sess[1].lower():
            assert sess[1].startswith(weekly_ruck_label())
            assert "15 kg" not in sess[1]
        day += timedelta(days=1)


def test_event_packs_stay_off_the_weekly_ruck():
    rehearsal = session_for_date(date(2027, 2, 13))
    assert rehearsal == ("ruck", "Pack test rehearsal 20.4 kg", 60)
    assert "10 kg" not in rehearsal[1]
    busar = session_for_date(date(2027, 2, 20))
    assert "BUSAR" in busar[1]
    assert "10 kg" not in busar[1]
    lakes = day_detail(date(2027, 2, 27))
    assert "15 kg" in lakes["ruck_pack"]
    assert "20.4" in day_detail(date(2027, 2, 13))["ruck_pack"]


def test_dashboard_email_and_coach_say_10kg():
    detail = day_detail(date(2027, 1, 9))
    assert detail["ruck_pack"] == "10 kg"
    assert "The pack stays 10 kg." in detail["purpose"]
    flat = day_detail(date(2026, 10, 24))
    assert flat["ruck_pack"] == "10 kg"
    assert "15 kg" not in flat["purpose"]
    email = _planned_session_html(date(2026, 10, 31))
    assert "Ruck 10 kg" in email
    assert "15 kg" not in email
    system = _coach_system()
    assert "10 kg" in system
    assert "20.4" in system


def test_garmin_ruck_push_names_the_pack_and_keeps_the_rehearsal_separate():
    weekly = _specs_for("ruck", "Ruck 10 kg", 60, 0)
    rehearsal = _specs_for("ruck", "Pack test rehearsal 20.4 kg", 60, 0)
    assert weekly == [("sr", "Ruck 10 kg", 0, 60)]
    assert rehearsal == [("sr", "Ruck 20.4 kg", 0, 60)]
    weekly_hike = _build_strength_ruck_workout("Ruck 10 kg", 0, 60)
    rehearsal_hike = _build_strength_ruck_workout("Ruck 20.4 kg", 0, 60)
    assert weekly_hike.workoutName == "Ruck 10 kg 60m"
    assert "10 kg" in weekly_hike.description
    assert "20.4" not in weekly_hike.description
    assert rehearsal_hike.workoutName == "Ruck 20.4 kg 60m"
    assert "20.4 kg" in rehearsal_hike.description
    assert weekly_hike.workoutName != rehearsal_hike.workoutName
    schedule = _workout_schedule_strength_ruck()
    assert "2027-01-16" in schedule[("Ruck 10 kg", 0, 60)]
    assert "2027-02-13" in schedule[("Ruck 20.4 kg", 0, 60)]
    assert "2027-02-13" not in schedule[("Ruck 10 kg", 0, 60)]

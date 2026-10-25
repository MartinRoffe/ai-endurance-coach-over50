"""Christmas Tenerife arrives 21 Dec 2026 and flies home 2 Jan 2027."""
from datetime import date

from ai_endurance_coach_over50.fitness_plan import session_for_date
from ai_endurance_coach_over50.hr_plan import HR_TRAINING_WEEKS
from ai_endurance_coach_over50.medical import (
    XMAS_CAMP_ARRIVE,
    XMAS_CAMP_HOME,
    medical_context_lines,
)


def test_arrival_constant_is_21_dec_and_home_is_2_jan():
    assert XMAS_CAMP_ARRIVE == date(2026, 12, 21)
    assert XMAS_CAMP_HOME == date(2027, 1, 2)
    assert XMAS_CAMP_ARRIVE.weekday() == 0  # Monday


def test_coach_medical_lines_use_the_arrival_constant():
    blob = "\n".join(medical_context_lines())
    assert "2026-12-21" in blob
    assert "2027-01-02" in blob
    assert "2026-12-22–" not in blob


def test_live_plan_marks_21_dec_as_travel():
    sess = session_for_date(date(2026, 12, 21))
    assert sess[0] == "rest"
    assert "travel" in sess[1].lower()
    # The day after arrival is a ride, not the arrival day.
    nxt = session_for_date(date(2026, 12, 22))
    assert "arrive" not in nxt[1].lower()
    assert "travel" not in nxt[1].lower()


def test_gated_hr_week_puts_arrival_on_monday_21():
    # Week 12 is the Christmas camp week starting Mon 21 Dec (0-based index 11).
    week = HR_TRAINING_WEEKS[11]
    assert "travel arrive" in week[0][1].lower()
    assert "arrive" not in week[1][1].lower()

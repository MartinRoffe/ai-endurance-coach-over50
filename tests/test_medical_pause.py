"""Medical pause + charity cancel + Year-2 gate."""
from datetime import date

from ai_endurance_coach_over50.medical import (
    CHARITY_CANCELLED,
    MEDICAL_PAUSE_END,
    in_medical_pause,
    pause_session_for_date,
    should_push_garmin_date,
    year2_sessions_live,
)
from ai_endurance_coach_over50.plan import session_for_date_extended
from ai_endurance_coach_over50.hr_plan import hr_session_for_date, HR_EVENT_NAME, HR_EVENT_START


def test_medical_pause_window():
    assert in_medical_pause(date(2026, 9, 1))
    assert in_medical_pause(date(2026, 9, 8))
    assert in_medical_pause(MEDICAL_PAUSE_END)
    assert not in_medical_pause(date(2026, 8, 31))
    assert not in_medical_pause(date(2026, 9, 22))


def test_pause_overrides_event_prep_quality():
    # 5 Sep was Sweetspot — must not prescribe during pause
    sess = session_for_date_extended(date(2026, 9, 5))
    assert sess is not None
    assert sess[0] in ("rest", "hike")
    assert "Sweetspot" not in sess[1]


def test_pause_overrides_pre_event_long():
    sess = session_for_date_extended(date(2026, 9, 6))
    assert sess is not None
    assert sess[0] in ("rest", "hike")
    assert "Pre-Event" not in sess[1]


def test_charity_days_cancelled():
    assert CHARITY_CANCELLED
    for d in (date(2026, 9, 13), date(2026, 9, 14)):
        sess = session_for_date_extended(d)
        assert sess is not None
        assert sess[0] == "rest"
        assert "cancelled" in sess[1].lower()


def test_pause_session_walk_days():
    # Wed 2 Sep 2026 and Mon 7 Sep are walk days (Mon/Wed/Fri)
    assert pause_session_for_date(date(2026, 9, 2))[0] == "hike"
    assert pause_session_for_date(date(2026, 9, 7))[0] == "hike"
    # Tue 1 Sep is rest
    assert pause_session_for_date(date(2026, 9, 1))[0] == "rest"


def test_garmin_skip_pause_and_charity():
    assert not should_push_garmin_date(date(2026, 9, 5))
    assert not should_push_garmin_date(date(2026, 9, 13))
    # Historical plan day still pushable
    assert should_push_garmin_date(date(2026, 6, 19))


def test_hr_year2_gated_off():
    assert not year2_sessions_live()
    assert hr_session_for_date(date(2026, 10, 5)) is None
    assert hr_session_for_date(date(2027, 10, 4)) is None
    assert "2028" in HR_EVENT_NAME
    assert HR_EVENT_START.year == 2028


def test_sept_1_not_easy_spin():
    sess = session_for_date_extended(date(2026, 9, 1))
    assert sess is not None
    assert "Easy Spin" not in sess[1]

"""Daily email and coach fixes: stale drift, header, morning gate, equipment, days, ACWR, rucks."""
from datetime import date, timedelta
from unittest.mock import MagicMock

from ai_endurance_coach_over50.coach_context import _acwr_line, _section_week_ahead, coach_persona_brief
from ai_endurance_coach_over50.coach_voice import equipment_note
from ai_endurance_coach_over50.display import ACWR_BREAK_NOTE
from ai_endurance_coach_over50.fitness_plan import (
    PLAN_START,
    route_headline,
    session_for_date,
)
from ai_endurance_coach_over50.history import (
    capture_morning_snapshot,
    load_morning_snapshot,
    maybe_capture_morning_snapshot,
)
from ai_endurance_coach_over50.metrics import DailyMetrics, email_readiness_gaps, fetch_metrics
from ai_endurance_coach_over50.modulation import (
    _amber_variant,
    durability_gate,
    modulation_decision_text,
    recent_durability,
)
from ai_endurance_coach_over50.report import build_html
from ai_endurance_coach_over50.safety import prescribed_week
from ai_endurance_coach_over50.server.coach import _coach_system
from ai_endurance_coach_over50.server.context import build_event_tracker
from ai_endurance_coach_over50.workouts import (
    _build_strength_ruck_workout,
    _workout_schedule_strength_ruck,
    _workouts_for_date,
)


def test_recent_durability_drops_the_august_ride_and_the_break():
    rows = [
        {"date": "2026-08-02", "drift_pct": 8.3},
        {"date": "2026-09-21", "drift_pct": 9.0},
        {"date": "2026-09-28", "drift_pct": 4.0},
        {"date": "2026-10-10", "drift_pct": 3.0},
    ]
    kept = recent_durability(rows, date(2026, 10, 18))
    # 28 Sep is after the break and inside 21 days, so it still counts.
    assert [row["date"] for row in kept] == ["2026-09-28", "2026-10-10"]


def test_durability_gate_ignores_a_pre_break_ride(monkeypatch):
    monkeypatch.setattr(
        "ai_endurance_coach_over50.modulation.session_for_date_extended",
        lambda d: ("long", "Long Ride (Easy) · outdoor", 180),
    )
    monkeypatch.setattr(
        "ai_endurance_coach_over50.modulation.load_durability",
        lambda days=90: [{
            "date": "2026-08-02",
            "drift_pct": 8.3,
            "first_third_hr": 120.0,
            "final_third_hr": 130.0,
        }],
    )
    # 13 Dec 2026 is fitness-plan week 9. The only drift row is 2 Aug.
    gate = durability_gate(date(2026, 12, 13), DailyMetrics(date=date(2026, 12, 13)), None)
    assert gate is None


def test_outdoor_suffix_is_not_a_session_change_and_survives_an_easier_swap():
    same = {
        "label": "Long Ride (Easy) · outdoor",
        "planned_label": "Long Ride (Easy) · outdoor",
        "duration_min": 70,
        "reason": "drift",
    }
    text = modulation_decision_text({"status": "amber"}, same)
    assert "instead of" not in text
    assert "· outdoor" in text

    swap = _amber_variant("long", "Long Ride · outdoor", 90, False)
    assert swap["label"] == "Long Ride (Easy) · outdoor"


def test_header_counts_the_next_goal_not_the_pause():
    assert route_headline(date(2026, 10, 18)) == "Tenerife camp · J–64"
    assert route_headline(date(2026, 12, 25)) == "Tenerife camp"
    assert route_headline(date(2027, 1, 3)) == "BUSAR · J–48"
    assert route_headline(date(2027, 2, 22)) == "Lake District · J–5"
    assert route_headline(date(2027, 3, 1)) == "Scotland · J–21"
    assert route_headline(date(2027, 3, 22)) == "Scotland"
    assert route_headline(date(2027, 3, 29)) is None

    paused = build_event_tracker(date(2026, 9, 10))
    assert paused["title"] == "Medical pause"
    assert "2028" not in paused["subtitle"]
    assert "2028" not in paused["countdown_label"]

    live = build_event_tracker(date(2026, 10, 18))
    assert live["title"] == "Tenerife camp"
    assert live["days_to_event"] == 64
    assert "Haute Route" not in live["countdown_label"]


def test_email_header_and_hidden_acwr():
    m = DailyMetrics(
        date=date(2026, 10, 18),
        acwr=0.0,
        acwr_status="LOW",
        training_load_acute=0,
        sleep_score=80,
        body_battery_morning=78,
        resting_hr=48,
    )
    html = build_html(m, {}, None, "Train as planned.")
    assert "Tenerife camp · J–64" in html
    assert "MEDICAL PAUSE" not in html
    assert "0.00" not in html
    assert ACWR_BREAK_NOTE in html
    assert "No recent load" in html
    assert _acwr_line(m) == ACWR_BREAK_NOTE


def test_email_waits_until_the_morning_picture_has_settled():
    end = 1_700_000_000.0
    early = DailyMetrics(
        date=date(2026, 10, 18),
        sleep_end_ts=end,
        sleep_score=80,
        body_battery_morning=5,
        resting_hr=48,
        rest_stress=20,
    )
    gaps = email_readiness_gaps(early, now_ts=end + 2 * 60)
    assert any("20 min" in gap for gap in gaps)
    assert any("implausible" in gap for gap in gaps)

    settled = DailyMetrics(
        date=date(2026, 10, 18),
        sleep_end_ts=end,
        sleep_score=80,
        body_battery_morning=78,
        resting_hr=48,
        rest_stress=20,
    )
    assert email_readiness_gaps(settled, now_ts=end + 25 * 60) == []

    missing_stress = DailyMetrics(
        date=date(2026, 10, 18),
        sleep_end_ts=end,
        sleep_score=80,
        body_battery_morning=78,
        resting_hr=48,
    )
    assert any(gap == "rest_stress" for gap in email_readiness_gaps(missing_stress, now_ts=end + 25 * 60))


def test_body_battery_ignores_the_unprocessed_wake_reading():
    api = MagicMock()
    sleep_end_ms = 1_000_000.0
    api.get_sleep_data.return_value = {
        "dailySleepDTO": {"sleepEndTimestampGMT": sleep_end_ms, "sleepScores": {"overall": {"value": 80}}}
    }
    api.get_hrv_data.return_value = {}
    api.get_body_battery.return_value = [{
        "bodyBatteryValuesArray": [
            [sleep_end_ms, 5.0],
            [sleep_end_ms + 2 * 60 * 1000, 5.0],
            [sleep_end_ms + 25 * 60 * 1000, 78.0],
            [sleep_end_ms + 4 * 3600 * 1000, 40.0],
        ]
    }]
    api.get_stress_data.return_value = {}
    api.get_training_status.return_value = {}
    api.get_daily_summary.return_value = {}
    m = fetch_metrics(api, date(2026, 10, 18))
    assert m.body_battery_morning == 78.0

    api.get_body_battery.return_value = [{
        "bodyBatteryValuesArray": [
            [sleep_end_ms + 2 * 60 * 1000, 5.0],
        ]
    }]
    early = fetch_metrics(api, date(2026, 10, 18))
    assert early.body_battery_morning is None


def test_early_snapshot_is_replaced_by_a_complete_fetch():
    target = date(2026, 10, 18)
    early = DailyMetrics(
        date=target,
        sleep_score=80,
        body_battery_morning=5,
        resting_hr=48,
    )
    assert capture_morning_snapshot(
        target, early,
        composite_z=0.0,
        readiness_label="OK",
        traffic_light={"status": "green"},
    )
    assert load_morning_snapshot(target)["body_battery_morning"] == 5

    later = DailyMetrics(
        date=target,
        sleep_score=80,
        body_battery_morning=78,
        resting_hr=48,
        hrv_last_night=42,
        hrv_status="BALANCED",
    )
    assert maybe_capture_morning_snapshot(
        target, later, {},
        composite_z=0.4,
        readiness_label="OK",
        traffic_light={"status": "green"},
        advice_pre="Train as planned.",
    )
    assert load_morning_snapshot(target)["body_battery_morning"] == 78


def test_coach_prompt_forbids_a_turbo_and_drops_the_pause():
    note = equipment_note(False)
    assert "NO turbo" in note
    assert "rower" in note
    assert "· outdoor" in note
    brief = coach_persona_brief(False)
    system = _coach_system()
    for text in (brief, system):
        assert "NO turbo" in text
        assert "not the live A-event" in text
        assert "not paused" in text.lower() or "not in a medical pause" in text.lower()
        assert "Tenerife" in text
        assert "BUSAR" in text


def test_next_seven_days_keeps_rest_days_in_the_count():
    lines = _section_week_ahead(date(2026, 10, 18))
    blob = "\n".join(lines)
    assert "Mon 19 Oct (tomorrow): Rest" in blob
    assert "Tue 20 Oct (in 2 days):" in blob
    assert "Threshold — rower" in blob
    assert "tomorrow" not in blob.split("Tue 20 Oct")[1].split("\n")[0]


def test_saturday_rucks_progress_and_push_as_hikes():
    expected = {
        date(2026, 10, 17): ("hike", "light pack", 45),
        date(2026, 10, 24): ("ruck", "Ruck 10 kg", 40),
        date(2026, 10, 31): ("ruck", "Ruck 10 kg", 35),
        date(2026, 11, 7): ("ruck", "Ruck 10 kg", 35),
        date(2026, 11, 14): ("ruck", "Ruck 10 kg", 30),
        date(2026, 11, 21): ("ruck", "Ruck 10 kg", 25),
        date(2026, 11, 28): ("ruck", "Ruck 10 kg", 45),
        date(2026, 12, 5): ("ruck", "Ruck 10 kg", 35),
        date(2026, 12, 12): ("ruck", "Ruck 10 kg", 55),
        date(2026, 12, 19): ("ruck", "Ruck 10 kg", 65),
        date(2026, 12, 26): ("long", "Teide", 300),
        date(2027, 1, 2): ("rest", "Travel home", 0),
        date(2027, 1, 9): ("ruck", "Ruck 10 kg", 50),
        date(2027, 1, 16): ("ruck", "Ruck 10 kg", 60),
        date(2027, 1, 23): ("ruck", "Ruck 10 kg", 70),
        date(2027, 1, 30): ("ruck", "Ruck 10 kg", 50),
        date(2027, 2, 6): ("ruck", "Ruck 10 kg", 70),
        date(2027, 2, 13): ("ruck", "Pack test rehearsal 20.4 kg", 60),
        date(2027, 2, 20): ("hike", "BUSAR", 0),
        date(2027, 2, 27): ("hike", "Skiddaw", 360),
        date(2027, 3, 6): ("hike", "Easy walk", 60),
        date(2027, 4, 3): ("ruck", "Ruck 10 kg", 90),
        date(2027, 4, 24): ("ruck", "Ruck 10 kg", 60),
    }
    for day, (stype, label, dur) in expected.items():
        sess = session_for_date(day)
        assert sess[0] == stype, (day, sess)
        assert label in sess[1], (day, sess)
        assert sess[2] == dur, (day, sess)
        if stype == "strength":
            raise AssertionError(day)

    # The gym load session moved to Wednesday and does not share Saturday.
    wed = session_for_date(date(2026, 10, 21))
    assert wed[0] == "strength"
    assert session_for_date(date(2026, 10, 24))[0] == "ruck"

    specs = _workouts_for_date(date(2026, 10, 24))
    assert specs == [("sr", "Ruck 10 kg", 0, 40)]
    hike = _build_strength_ruck_workout("Ruck 10 kg", 0, 40)
    assert hike.sportType["sportTypeKey"] == "hiking"
    assert hike.workoutName == "Ruck 10 kg 40m"
    assert _workouts_for_date(date(2026, 12, 26)) == []
    assert _workouts_for_date(date(2027, 2, 20)) == []

    schedule = _workout_schedule_strength_ruck()
    assert "2026-10-24" in schedule[("Ruck 10 kg", 0, 40)]
    assert "2026-12-26" not in {day for dates in schedule.values() for day in dates}

    cache: dict = {}
    monday = PLAN_START
    while monday <= date(2027, 2, 16):
        for item in prescribed_week(monday, cache):
            if item.date > date(2027, 2, 21):
                continue
            planned = session_for_date(item.date)
            assert item.session == planned, (item.date, item.session, planned, item.reason)
            assert item.reason is None
        monday += timedelta(days=7)

"""Calendar day detail and the BUSAR strength block, 19 Oct 2026–21 Feb 2027."""
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from ai_endurance_coach_over50.fitness_plan import (
    CAMP_END,
    CAMP_START,
    garmin_allowed,
    pullup_for_date,
    session_for_date,
)
from ai_endurance_coach_over50.safety import is_hard, prescribed_week
from ai_endurance_coach_over50.server import app
from ai_endurance_coach_over50.server.shared import TEMPLATES
from ai_endurance_coach_over50.session_detail import brief_activity, day_detail


ROOT = Path(__file__).resolve().parents[1]
STRENGTH_END = date(2027, 2, 21)


def _days(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def _mondays(start: date, end: date):
    day = start - timedelta(days=start.weekday())
    while day <= end:
        yield day
        day += timedelta(days=7)


def _is_strength(session: tuple) -> bool:
    stype, label, _dur = session
    low = label.lower()
    if stype in ("strength", "kettlebell"):
        return True
    return "sandbag" in low


def _is_load_day(session: tuple) -> bool:
    """The heavier strength day. The lighter endurance day is not this."""
    _stype, label, _dur = session
    low = label.lower()
    if "endurance" in low or "easy" in low or "light" in low:
        return False
    if "strength — load" in low or "step-overs" in low:
        return True
    return False


def test_every_day_through_the_test_has_a_structure_and_an_rpe():
    for day in _days(date(2026, 10, 12), STRENGTH_END):
        detail = day_detail(day)
        assert detail["title"]
        assert detail["rpe_target"]
        assert detail["blocks"]
        names = [block["name"] for block in detail["blocks"]]
        assert names[0] in {"Warm-up", "Today", "Pack test"}
        if detail["exercises"]:
            for ex in detail["exercises"]:
                assert ex["sets_reps"] and ex["load"] and ex["tempo"] and ex["rest"]


def test_strength_days_name_real_kit_and_not_a_trap_bar():
    seen = False
    for day in _days(date(2026, 10, 19), date(2027, 2, 16)):
        session = session_for_date(day)
        if not _is_strength(session):
            continue
        seen = True
        detail = day_detail(day)
        blob = " ".join(ex["load"] + ex["name"] for ex in detail["exercises"]).lower()
        assert "trap bar" not in blob
        assert detail["exercises"]
    assert seen


def test_two_strength_sessions_until_the_taper_except_camp():
    for monday in _mondays(date(2026, 10, 19), date(2027, 2, 8)):
        if CAMP_START <= monday <= CAMP_END or monday + timedelta(days=6) < date(2026, 10, 19):
            continue
        if monday >= CAMP_START and monday <= CAMP_END:
            continue
        # Camp weeks and the travel week are not strength weeks.
        if date(2026, 12, 21) <= monday <= date(2026, 12, 28):
            continue
        count = sum(
            1 for i in range(7) if _is_strength(session_for_date(monday + timedelta(days=i)))
        )
        assert count == 2, (monday, count)
    taper = [
        session_for_date(date(2027, 2, 15) + timedelta(days=i)) for i in range(5)
    ]
    assert sum(1 for sess in taper if _is_strength(sess)) == 1


def test_camp_week_does_not_add_strength():
    for day in _days(CAMP_START, CAMP_END):
        assert not _is_strength(session_for_date(day))


def test_monday_and_friday_stay_rest_outside_camp():
    for day in _days(date(2026, 10, 19), date(2027, 2, 19)):
        if CAMP_START <= day <= date(2027, 1, 3):
            continue
        if day.weekday() in (0, 4):
            assert session_for_date(day)[0] == "rest", day


def test_load_strength_is_not_the_day_before_a_hard_session():
    previous = None
    for day in _days(date(2026, 10, 19), STRENGTH_END):
        session = session_for_date(day)
        if previous is not None and is_hard(session):
            assert not _is_load_day(previous), (day, previous, session)
        previous = session


def test_labels_do_not_use_the_word_heavy_before_the_test():
    for day in _days(date(2026, 10, 19), STRENGTH_END):
        assert "heavy" not in session_for_date(day)[1].lower()


def test_plan_is_not_rewritten_by_the_caps():
    cache: dict = {}
    monday = date(2026, 10, 12)
    while monday <= STRENGTH_END:
        for item in prescribed_week(monday, cache):
            if item.date > STRENGTH_END:
                continue
            planned = session_for_date(item.date)
            assert item.session == planned, (item.date, item.session, planned, item.reason)
            assert item.reason is None
        monday += timedelta(days=7)


def test_deload_weeks_use_lighter_bells():
    before = day_detail(date(2026, 11, 7))
    after = day_detail(date(2026, 11, 14))
    assert after["deload"] is True
    assert before["deload"] is False

    def goblet(detail):
        ex = next(row for row in detail["exercises"] if row["name"] == "Goblet squat")
        return int(ex["load"].split()[0]), ex["sets_reps"]

    assert goblet(after)[0] < goblet(before)[0]
    assert goblet(after)[1].startswith("2×")
    jan = day_detail(date(2027, 1, 26))
    assert jan["deload"] is True
    assert jan["exercises"][0]["sets_reps"].startswith("2×")


def test_pullup_addon_keeps_the_progression_and_names_the_bar():
    assert pullup_for_date(date(2026, 10, 24)) is None
    early = day_detail(date(2026, 10, 27))["addon"]
    assert "negatives" in early
    assert "27 Oct" in early
    assert "band-assisted" in day_detail(date(2027, 1, 5))["addon"]
    assert "strict" in day_detail(date(2027, 2, 2))["addon"]
    skills = day_detail(date(2027, 2, 9))
    assert any("Burpee" in ex["name"] for ex in skills["exercises"])
    assert "No pack" in skills["exercises"][-1]["load"]


def test_ruck_detail_carries_the_pack_and_the_flat_rehearsal():
    ruck = day_detail(date(2027, 1, 9))
    assert ruck["ruck_pack"] == "10 kg"
    assert ruck["ruck_route"]
    assert ruck["ruck_elevation"]
    assert ruck["garmin"] is False
    rehearsal = day_detail(date(2027, 2, 13))
    assert "20.4" in rehearsal["ruck_pack"]
    assert "flat" in rehearsal["ruck_route"].lower()
    assert not garmin_allowed(date(2027, 2, 13), "ruck", rehearsal["title"])


def test_easy_rides_are_the_ones_pushed_to_garmin():
    easy = day_detail(date(2026, 10, 18))
    assert easy["garmin"] is True
    assert easy["garmin_text"] == "Pushed to Garmin"
    assert easy["power_target"]
    assert "220" in easy["power_target"] or "FTP" in easy["power_target"]
    hard = day_detail(date(2026, 10, 20))
    assert hard["garmin"] is True
    assert "Threshold" in hard["title"] or hard["type"] == "threshold"
    assert hard["garmin_text"] == "Pushed to Garmin"
    # Non-bike hard sessions stay calendar-only.
    rower = day_detail(date(2026, 11, 5))
    assert "rower" in (rower["title"] or "").lower()
    assert rower["garmin"] is False


def test_scotland_day_has_conditions_structure_not_placeholder():
    detail = day_detail(date(2027, 3, 22))
    assert "Scotland" in detail["title"]
    assert detail["garmin"] is False
    assert "22 kg" in (detail.get("ruck_pack") or "")
    assert "conditions" in (detail.get("purpose") or "").lower() or "conditions" in (
        detail.get("ruck_route") or ""
    ).lower()
    assert "placeholder" not in (detail.get("purpose") or "").lower()
    assert detail["blocks"]


def test_clinic_day_detail_names_no_treatment_and_the_ct_rule():
    detail = day_detail(date(2026, 10, 15))
    assert "no treatment" in detail["title"].lower() or "attended" in detail["title"].lower()
    assert "confirmation CT" in detail["purpose"]
    sat = day_detail(date(2026, 10, 17))
    assert sat["ruck_pack"]
    assert "optional" not in sat["title"].lower()


def test_logged_activity_brief_is_plain_data():
    brief = brief_activity({
        "name": "Morning ride",
        "type_key": "virtual_ride",
        "duration_seconds": 2400,
        "distance_meters": 18000,
        "avg_hr": 128.4,
        "avg_power_w": 150.2,
        "elevation_gain": 40,
    })
    assert brief["minutes"] == 40
    assert brief["distance_km"] == 18.0
    assert brief["avg_hr"] == 128
    assert brief["avg_power_w"] == 150


def test_day_detail_template_escapes_and_does_not_mark_safe():
    partial = (ROOT / "ai_endurance_coach_over50/templates/partials/day_detail.html").read_text()
    calendar = (ROOT / "ai_endurance_coach_over50/templates/calendar.html").read_text()
    assert "| safe" not in partial
    assert "|safe" not in partial
    assert "day-dialog" in calendar
    detail = day_detail(date(2026, 10, 21))
    detail["title"] = "<img src=x onerror=alert(1)>"
    detail["purpose"] = "<script>alert(1)</script>"
    html = TEMPLATES.env.get_template("partials/day_detail.html").render(day={
        "date": date(2026, 10, 21),
        "show_logged": True,
        "logged": [{
            "name": "<script>alert(1)</script>",
            "minutes": 12,
            "distance_km": None,
            "elevation_m": None,
            "avg_hr": None,
            "avg_power_w": None,
        }],
        "detail": detail,
    })
    assert "<script>" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html
    assert "Goblet squat" in html


def test_calendar_page_makes_every_fitness_day_a_button():
    client = TestClient(app)
    response = client.get("/calendar")
    assert response.status_code == 200
    text = response.text
    assert 'id="day-dialog"' in text
    assert 'data-day-detail="2026-10-20"' in text
    assert 'data-day-detail="2027-02-21"' in text
    assert "Goblet squat" in text
    assert "Sandbag deadlift" in text
    assert "Not pushed to Garmin" in text
    assert "Pushed to Garmin" in text
    assert text.count("<button") > 50

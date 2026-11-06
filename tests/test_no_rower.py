"""From 25 Oct 2026 the rower is gone. Weekday hard work is the MaxiClimber.

Weekend rides stay outdoors. The Saturday ruck stays 10 kg. Sessions on or
before 24 Oct keep the rower prescription they were written with.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from ai_endurance_coach_over50.fitness_plan import (
    PLAN_END,
    PLAN_START,
    WEEKLY_RUCK_PACK_KG,
    session_for_date,
)
from ai_endurance_coach_over50.session_detail import day_detail
from ai_endurance_coach_over50.workouts import _workout_schedule_row, _workouts_for_date

ROOT = Path(__file__).resolve().parents[1]
ROWER_LAST = date(2026, 10, 24)
_ROWER = re.compile(r"rower|concept2|rowing", re.I)
_TURBO = re.compile(r"\b(turbo|rouvy|erg|indoor trainer|indoor-trainer)\b", re.I)


def _days():
    d = PLAN_START
    while d <= PLAN_END:
        yield d
        d += timedelta(days=1)


def test_dates_after_24_oct_are_not_rower_sessions():
    for d in _days():
        if d <= ROWER_LAST:
            continue
        sess = session_for_date(d)
        assert sess is not None
        stype, label, _dur = sess
        assert stype != "rower", (d, sess)
        assert not _ROWER.search(label), (d, sess)


def test_tuesday_20_oct_stays_the_historical_rower():
    assert session_for_date(date(2026, 10, 20)) == ("rower", "Threshold — rower", 40)
    assert _workouts_for_date(date(2026, 10, 20)) == [("row", "Threshold — rower", 40)]


def test_tuesday_3_nov_is_a_short_maxiclimber_not_a_row():
    assert session_for_date(date(2026, 11, 3)) == ("maxiclimber", "VO2 — MaxiClimber", 40)
    detail = day_detail(date(2026, 11, 3))
    text = " ".join(
        [detail["title"], detail["purpose"]]
        + [block["detail"] for block in detail["blocks"]]
    )
    assert "6 × 2 min" in text or "5 ×" in text
    assert "RPE" in text
    assert "2 × 8" not in text
    assert "20 min" not in text
    assert not _ROWER.search(text)
    assert detail["garmin"] is False
    assert _workouts_for_date(date(2026, 11, 3)) == []


def test_threshold_maxiclimber_is_five_by_four_at_rpe_7():
    assert session_for_date(date(2026, 11, 5)) == ("maxiclimber", "Threshold — MaxiClimber", 35)
    detail = day_detail(date(2026, 11, 5))
    text = " ".join(block["detail"] for block in detail["blocks"])
    assert "5 × 4 min" in text
    assert "RPE 7" in text
    assert "2 min easy" in text
    assert "heart rate" in detail["intensity"].lower() or "Heart rate" in detail["intensity"]
    # Measured Karvonen zones, not a percent-of-max estimate.
    assert "180" in detail["hr_target"] and "191" in detail["hr_target"]
    assert "154" not in detail["hr_target"]
    assert not _ROWER.search(text)
    assert detail["garmin"] is False


def test_long_camp_quality_keeps_the_hours_and_shortens_the_reps():
    assert session_for_date(date(2026, 12, 23)) == ("maxiclimber", "Threshold — MaxiClimber", 180)
    detail = day_detail(date(2026, 12, 23))
    text = " ".join(block["detail"] for block in detail["blocks"])
    assert "5 × 4 min" in text
    assert "RPE 7" in text
    assert "zone 2" in text.lower()
    assert "3 ×" not in text
    assert "25 min" not in text
    assert not _ROWER.search(text)
    assert detail["garmin"] is False
    assert _workouts_for_date(date(2026, 12, 23)) == []


def test_sandbag_tuesday_is_a_short_maxiclimber_then_the_lift():
    sess = session_for_date(date(2027, 1, 5))
    assert sess[0] == "maxiclimber"
    assert "sandbag" in sess[1].lower()
    assert "rower" not in sess[1].lower()
    detail = day_detail(date(2027, 1, 5))
    text = " ".join(block["detail"] for block in detail["blocks"])
    assert "5 × 4 min" in text
    assert "RPE 7" in text
    assert "2 × 6" not in text
    assert not _ROWER.search(text)


def test_weekend_rides_stay_outdoor_with_no_trainer():
    for d in _days():
        if d.weekday() < 5 or d <= ROWER_LAST:
            continue
        sess = session_for_date(d)
        if sess[0] not in {"bike", "long", "endurance", "threshold", "vo2"}:
            continue
        assert "outdoor" in sess[1].lower(), (d, sess)
        detail = day_detail(d)
        blob = " ".join(
            [sess[1], detail.get("purpose") or ""]
            + [block.get("detail") or "" for block in detail.get("blocks") or []]
        )
        assert not _TURBO.search(blob), (d, blob)
        assert not _ROWER.search(blob), (d, blob)


def test_saturday_ruck_stays_10_kg():
    assert WEEKLY_RUCK_PACK_KG == 10
    sat = session_for_date(date(2026, 11, 7))
    assert sat[0] == "ruck"
    assert "10 kg" in sat[1]


def test_rower_workouts_stop_after_24_oct():
    dates = {d for rows in _workout_schedule_row().values() for d in rows}
    assert "2026-10-20" in dates
    assert "2026-11-03" not in dates
    assert "2026-12-23" not in dates
    assert all(d <= "2026-10-24" for d in dates)


def test_plan_doc_drops_rower_from_26_oct_onward():
    text = (ROOT / "docs/plans/fitness-2026-27.md").read_text()
    later = text.split("| 26 Oct 2026 |", 1)[1]
    assert "rower" not in later.lower()

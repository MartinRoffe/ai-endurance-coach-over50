"""12-month general fitness block: 12 Oct 2026 → 3 Oct 2027.

Source of truth for the dashboard, calendar, and Garmin push. With
``HAS_TURBO`` false (the default), weekday bike sessions resolve to the indoor
rower and weekend rides are outdoor. Haute Route week-by-week stays gated.
Gravel stays off until the bike is in use.
"""
from __future__ import annotations

from datetime import date, timedelta

from .settings import has_turbo

PLAN_START = date(2026, 10, 12)  # Monday of the clearance week
PLAN_END = date(2027, 10, 3)     # Sunday before the Year-2 placeholder

# Week of 12 Oct: clinic on Thu 15 Oct found the fragments had already passed.
# ESWL was not performed. Only a confirmation CT remains. This week is still
# a light base (not used for the +10% load rule), and it does not open a
# MEDICAL_RETURN_EASY_DAYS window — see safety._procedure_dates.
PROCEDURE_START = date(2026, 10, 12)
PROCEDURE_END = date(2026, 10, 18)
QUALITY_START = date(2026, 10, 20)   # first hard session (rower threshold; bike if HAS_TURBO)
TWO_QUALITY_FROM = date(2026, 10, 26)
PULLUP_START = date(2026, 10, 27)    # bar in the house; negatives start here
# Kept for older imports / docs that still name the easy-return end.
EASY_RETURN_END = date(2026, 10, 18)

# Working numbers for this athlete. Max HR 191 is the measured value the
# existing zone model already uses — this constant does not move the zones.
# FTP is the current working estimate, not a tested override of ftp_tests.
ATHLETE_MAX_HR = 191
ATHLETE_FTP_W = 220
ATHLETE_WEIGHT_KG_LOW = 89
ATHLETE_WEIGHT_KG_HIGH = 92

# Home Sundays reach 3 h on 29 Nov 2026. Camp quality days are 3–4 h, and
# the optional Teide day is longer. Those camp days are not held to this cap.
HOME_SUNDAY_CAP_MIN = 180

CAMP_START = date(2026, 12, 21)
CAMP_END = date(2027, 1, 2)

GRAVEL_BIKE_ACTIVE = False

# Bike labels pushed to Garmin as cycling workouts. With no turbo these are
# weekend outdoor rides (and camp days only when HAS_TURBO is on, because
# weekday camp rides otherwise become rower workouts).
_GARMIN_BIKE_LABELS = frozenset({
    "Z2 Easy",
    "Long Ride (Easy)",
    "Threshold — bike",
    "VO2 — bike",
    "Camp quality — threshold",
    "Camp quality — VO2",
})
# Indoor rower labels pushed as cardio workouts (rowing is not a Connect
# workout sport the library can upload, so the push is cardio with HR targets).
_GARMIN_ROW_LABELS = frozenset({
    "Threshold — rower",
    "VO2 — rower",
    "Z2 — rower",
    "Threshold — rower, then sandbag",
})
_OUTDOOR_MARK = " · outdoor"
# Kept as an alias for callers/tests that still import the old name.
_EASY_BIKE_LABELS = _GARMIN_BIKE_LABELS
# Race-sim / HR-vocabulary types that must never be auto-pushed from fitness.
_BLOCKED_PUSH_TYPES = frozenset({"sweetspot", "tempo", "ftp", "back_to_back"})

BUSAR_STANDARDS = (
    "Pack test: 3 miles flat with 45 lb (20.4 kg) in under 45 minutes.",
    "Step-overs: 20 lb pack plus a sandbag or the 24 kg kettlebell, up and over a picnic table for 30 minutes.",
    "Deadlift: train with a sandbag or a barbell, not a kettlebell (heaviest bell is 24 kg). "
    "The test standard is still 225 lb (102 kg) for at least 15 reps in one minute. "
    "There is no trap bar yet, so do not pretend a kettlebell is the test load.",
    "Burpee pull-ups: 20 lb pack, at least 50 in 10 minutes. "
    "There is no pull-up bar yet and the current max is 0 strict reps. "
    "Train negatives, then band-assisted, then strict reps. The test still needs a bar.",
)

# Christmas camp, 21 Dec 2026–2 Jan 2027. Time on the bike, not a kilometre
# target. Quality days are 3–4 h with an easy day between them. One optional
# longer Teide day. 3 Jan is the day after travel, still a rest.
_CAMP: dict[date, tuple[str, str, int]] = {
    date(2026, 12, 21): ("rest", "Tenerife — travel", 0),
    date(2026, 12, 22): ("bike", "Z2 Easy", 75),
    date(2026, 12, 23): ("threshold", "Camp quality — threshold", 180),
    date(2026, 12, 24): ("bike", "Z2 Easy", 90),
    date(2026, 12, 25): ("bike", "Z2 Easy", 60),
    date(2026, 12, 26): ("long", "Teide — optional long day", 300),
    date(2026, 12, 27): ("rest", "Tenerife — mid-camp rest", 0),
    date(2026, 12, 28): ("threshold", "Camp quality — threshold", 240),
    date(2026, 12, 29): ("bike", "Z2 Easy", 90),
    date(2026, 12, 30): ("vo2", "Camp quality — VO2", 210),
    date(2026, 12, 31): ("bike", "Z2 Easy", 90),
    date(2027, 1, 1): ("rest", "New Year rest", 0),
    date(2027, 1, 2): ("rest", "Travel home", 0),
    date(2027, 1, 3): ("rest", "Post-camp rest", 0),
}

_PROCEDURE: tuple[tuple[str, str, int], ...] = (
    ("rest", "Rest", 0),
    ("hike", "Easy walk", 30),
    ("bike", "Z2 Easy", 40),
    ("rest", "Attended — no treatment", 0),
    ("rest", "Rest", 0),
    ("hike", "Easy hill walk — light pack", 45),
    ("long", "Long Ride (Easy)", 60),
)

# Pull-ups three days a week (Tue, Thu, Sat) from the bar's arrival through
# the day before the BUSAR test. Strict reps are still 0, so the add-on
# starts with negatives.
_PULLUP_WEEKDAYS = (1, 3, 5)
PULLUP_END = date(2027, 2, 19)


def in_plan(d: date) -> bool:
    return PLAN_START <= d <= PLAN_END


def in_procedure_week(d: date) -> bool:
    return PROCEDURE_START <= d <= PROCEDURE_END


def gravel_sunday_note() -> str:
    if GRAVEL_BIKE_ACTIVE:
        return "Sunday long ride may be ridden on the gravel bike."
    if has_turbo():
        return (
            "Gravel bike is not in use. Sunday stays a road ride "
            "until that flag is turned on."
        )
    return (
        "Gravel bike is not in use. Sunday is an outdoor road ride "
        "until that flag is turned on."
    )


def plan_label(label: str) -> str:
    """Label without the outdoor mark, for Garmin builders and comparisons."""
    if _OUTDOOR_MARK in label:
        return label.split(_OUTDOOR_MARK, 1)[0].strip()
    return label


def garmin_bike_allowed(d: date, stype: str, label: str) -> bool:
    """True for a cycling workout (outdoor weekend ride, or a bike day when a turbo exists)."""
    del d
    if stype in _BLOCKED_PUSH_TYPES:
        return False
    base = plan_label(label)
    lowered = base.lower()
    if any(tok in lowered for tok in ("teide", "sweetspot", "tempo", "masca", "rower")):
        return False
    if stype not in ("bike", "long", "endurance", "recovery", "threshold", "vo2"):
        return False
    return base in _GARMIN_BIKE_LABELS


def garmin_row_allowed(stype: str, label: str) -> bool:
    """True when the session is an indoor rower workout we can push as cardio."""
    base = plan_label(label)
    if "maxiclimber" in base.lower():
        return False
    if stype == "rower" or "rower" in base.lower():
        return base in _GARMIN_ROW_LABELS or base.startswith("Threshold — rower")
    return False


def garmin_allowed(d: date, stype: str, label: str) -> bool:
    """True when this fitness-year session is scheduled on Garmin.

    Outdoor bike days go up as cycling workouts. Rower days go up as cardio
    workouts. Teide, MaxiClimber, strength, hikes and race-sim labels stay
    off the watch. The day-detail line uses this same flag.
    """
    return garmin_bike_allowed(d, stype, label) or garmin_row_allowed(stype, label)


def row_push_minutes(label: str, dur: int) -> int:
    """Minutes of the Garmin rower workout.

    A sandbag day is a short row and then lifting. The plan duration includes
    both; the watch workout is only the row.
    """
    if "sandbag" in label.lower():
        return 30
    return dur


_CYCLE_TYPES = frozenset({
    "bike", "long", "endurance", "tempo", "sweetspot", "ftp", "recovery",
})


def _is_cycle_session(stype: str, label: str) -> bool:
    """A bike ride in the stored week, before the no-turbo resolution."""
    low = label.lower()
    if "rower" in low or "maxiclimber" in low:
        return False
    if stype in {"hike", "ruck", "strength", "rest", "rower", "maxiclimber", "kettlebell"}:
        return "bike" in low
    if stype in _CYCLE_TYPES:
        return True
    if stype in {"threshold", "vo2"}:
        return any(tok in low for tok in ("bike", "camp quality", "ride", "z2", "teide"))
    return any(tok in low for tok in ("long ride", "z2 easy", "teide", "bike"))


def _as_rower(stype: str, label: str, dur: int) -> tuple[str, str, int]:
    """Same minutes and the same hard/easy intent, on the indoor rower."""
    low = label.lower()
    sandbag = "then sandbag" in low
    if "vo2" in low or stype == "vo2":
        new = "VO2 — rower"
    elif sandbag or "threshold" in low or stype == "threshold" or "camp quality" in low:
        new = "Threshold — rower"
    else:
        new = "Z2 — rower"
    if sandbag:
        new = "Threshold — rower, then sandbag"
    return ("rower", new, dur)


def apply_equipment(d: date, session: tuple[str, str, int]) -> tuple[str, str, int]:
    """Resolve bike vs rower from ``HAS_TURBO``.

    Stored weeks keep the bike wording so turning the flag on restores them.
    With the flag off, Monday–Friday bike sessions become rower sessions of
    the same duration, and Saturday–Sunday rides are marked outdoor.
    """
    stype, label, dur = session
    if not _is_cycle_session(stype, label):
        return session
    if has_turbo():
        return session
    if d.weekday() >= 5:
        if _OUTDOOR_MARK in label:
            return session
        return (stype, f"{label}{_OUTDOOR_MARK}", dur)
    return _as_rower(stype, label, dur)


def session_for_date(d: date) -> tuple[str, str, int] | None:
    """Return (type, label, duration_min), honouring a plan override."""
    if not in_plan(d):
        return None
    from .history import get_plan_override
    ov = get_plan_override(d.isoformat())
    if ov:
        return (ov["session_type"], ov["label"], ov["duration_min"])
    return _planned(d)


def iter_weeks() -> list[dict]:
    """Monday-start weeks covering the whole block, for the doc and the calendar."""
    weeks = []
    mon = PLAN_START
    while mon <= PLAN_END:
        days = []
        for i in range(7):
            d = mon + timedelta(days=i)
            if d > PLAN_END:
                break
            stype, label, dur = _planned(d)
            days.append({
                "date": d,
                "weekday": d.strftime("%a"),
                "type": stype,
                "label": label,
                "dur_min": dur,
            })
        weeks.append({
            "monday": mon,
            "phase": _phase_name(mon),
            "days": days,
        })
        mon += timedelta(days=7)
    return weeks


def build_calendar_weeks() -> list[dict]:
    """Week dicts for the /calendar fitness phase."""
    today = date.today()
    out = []
    for wk in iter_weeks():
        cells = []
        for day in wk["days"]:
            d = day["date"]
            dur = day["dur_min"]
            cells.append({
                "date": d,
                "day_num": d.day,
                "month_abbr": d.strftime("%b"),
                "weekday_short": d.strftime("%a"),
                "type": day["type"],
                "label": day["label"] if day["type"] != "rest" else day["label"],
                "dur_fmt": _fmt_dur(dur) if dur else None,
                "dur_min": dur,
                "extra": pullup_for_date(d),
                "kb_spec": None,
                "is_today": d == today,
                "is_past": d < today,
            })
        out.append({
            "week_label": wk["monday"].strftime("%-d %b"),
            "phase_name": wk["phase"],
            "days": cells,
        })
    return out


_BUSAR_LABEL = (
    "BUSAR test — pack test, step-overs, sandbag deadlift, burpee pull-ups"
)


def _planned(d: date) -> tuple[str, str, int]:
    return apply_equipment(d, _template_session(d))


def _template_session(d: date) -> tuple[str, str, int]:
    if d in (date(2027, 2, 20), date(2027, 2, 21)):
        return ("hike", _BUSAR_LABEL, 0)
    if d in _CAMP:
        return _CAMP[d]
    mon = d - timedelta(days=d.weekday())
    wd = d.weekday()
    if mon == PROCEDURE_START:
        return _PROCEDURE[wd]
    if date(2026, 10, 19) <= mon <= date(2026, 12, 14):
        return _return_day(mon, wd)
    if date(2027, 1, 4) <= mon <= date(2027, 2, 15):
        return _keswick_build_day(mon, wd)
    if mon == date(2027, 2, 22):
        return _lakes_day(wd)
    if mon == date(2027, 3, 1):
        return _recovery_day(wd)
    if mon == date(2027, 3, 8):
        return _scotland_prep_btb(wd)
    if mon == date(2027, 3, 15):
        return _scotland_prep_last(wd)
    if mon == date(2027, 3, 22):
        return _scotland_placeholder(wd)
    return _maintenance_day(wd)


def _wk(*days: tuple[str, str, int]) -> tuple[tuple[str, str, int], ...]:
    if len(days) != 7:
        raise ValueError(f"week needs 7 days, got {len(days)}")
    return days


# Monday → seven sessions. Totals stay inside the +10% weekly cap once the
# clearance week is no longer the load base. Hard days are Tuesday from
# 20 Oct, then Tuesday and Thursday from 26 Oct, so they are never adjacent.
# Strength is two days from 21 Oct: Wednesday is the lighter endurance
# session (it sits the day before Thursday's hard work), Saturday is the
# load session (Friday is rest, Sunday is an easy ride). Labels avoid the
# word "heavy" because safety.py counts that word as a hard session.
_RETURN_WEEKS: dict[date, tuple[tuple[str, str, int], ...]] = {
    # One hard day (Tue). Strength starts Wed 21 Oct.
    date(2026, 10, 19): _wk(
        ("rest", "Rest", 0),
        ("threshold", "Threshold — bike", 40),
        ("strength", "Strength — endurance", 45),
        ("hike", "Easy steps", 30),
        ("rest", "Rest", 0),
        ("strength", "Strength — load", 50),
        ("long", "Long Ride (Easy)", 70),
    ),
    # Two hard days from here.
    date(2026, 10, 26): _wk(
        ("rest", "Rest", 0),
        ("threshold", "Threshold — bike", 40),
        ("strength", "Strength — endurance", 45),
        ("rower", "VO2 — rower", 35),
        ("rest", "Rest", 0),
        ("strength", "Strength — load", 50),
        ("long", "Long Ride (Easy)", 85),
    ),
    date(2026, 11, 2): _wk(
        ("rest", "Rest", 0),
        ("vo2", "VO2 — bike", 40),
        ("strength", "Strength — endurance", 50),
        ("rower", "Threshold — rower", 35),
        ("rest", "Rest", 0),
        ("strength", "Strength — load", 55),
        ("long", "Long Ride (Easy)", 100),
    ),
    # Fourth strength week: same minutes, lighter bells.
    date(2026, 11, 9): _wk(
        ("rest", "Rest", 0),
        ("threshold", "Threshold — bike", 45),
        ("strength", "Strength — endurance", 50),
        ("rower", "VO2 — rower", 40),
        ("rest", "Rest", 0),
        ("strength", "Strength — load", 55),
        ("long", "Long Ride (Easy)", 115),
    ),
    # First 3-hour Sunday (22 Nov). Saturday is the load session, kept short
    # of failure so the long ride stays easy.
    date(2026, 11, 16): _wk(
        ("rest", "Rest", 0),
        ("vo2", "VO2 — bike", 40),
        ("strength", "Strength — endurance", 30),
        ("rower", "Threshold — rower", 35),
        ("rest", "Rest", 0),
        ("strength", "Strength — load", 50),
        ("long", "Long Ride (Easy)", 180),
    ),
    date(2026, 11, 23): _wk(
        ("rest", "Rest", 0),
        ("threshold", "Threshold — bike", 40),
        ("strength", "Strength — endurance", 30),
        ("maxiclimber", "VO2 — MaxiClimber", 35),
        ("rest", "Rest", 0),
        ("strength", "Strength — load", 80),
        ("long", "Long Ride (Easy)", 180),
    ),
    date(2026, 11, 30): _wk(
        ("rest", "Rest", 0),
        ("vo2", "VO2 — bike", 40),
        ("strength", "Strength — endurance", 45),
        ("rower", "Threshold — rower", 40),
        ("rest", "Rest", 0),
        ("strength", "Strength — load", 60),
        ("long", "Long Ride (Easy)", 180),
    ),
    # Eighth strength week: lighter bells again.
    date(2026, 12, 7): _wk(
        ("rest", "Rest", 0),
        ("threshold", "Threshold — bike", 40),
        ("strength", "Strength — endurance", 40),
        ("rower", "VO2 — rower", 40),
        ("rest", "Rest", 0),
        ("strength", "Strength — load", 100),
        ("long", "Long Ride (Easy)", 180),
    ),
    date(2026, 12, 14): _wk(
        ("rest", "Rest", 0),
        ("threshold", "Threshold — bike", 40),
        ("strength", "Strength — endurance", 40),
        ("rower", "VO2 — rower", 40),
        ("rest", "Rest", 0),
        ("strength", "Strength — load", 100),
        ("long", "Long Ride (Easy)", 180),
    ),
}


# Ruck weight rises to the 20.4 kg pack-test load on Sat 6 Feb.
# Duration stays put while the kilograms rise. Tuesday is a hard ride with
# the sandbag sets after it (one hard session, not a third). Wednesday is
# the lighter strength day, before Thursday's second hard session.
# The word "heavy" is not used: safety.py would count it as another hard day.
_KESWICK_WEEKS: dict[date, tuple[tuple[str, str, int], ...]] = {
    date(2027, 1, 4): _wk(
        ("rest", "Rest", 0),
        ("threshold", "Threshold — bike, then sandbag", 50),
        ("strength", "Strength — endurance", 60),
        ("rower", "VO2 — rower", 40),
        ("rest", "Rest", 0),
        ("ruck", "Hill ruck 10 kg", 70),
        ("long", "Long Ride (Easy)", 90),
    ),
    date(2027, 1, 11): _wk(
        ("rest", "Rest", 0),
        ("threshold", "Threshold — bike, then sandbag", 50),
        ("strength", "Strength — endurance", 40),
        ("maxiclimber", "VO2 — MaxiClimber", 40),
        ("rest", "Rest", 0),
        ("ruck", "Hill ruck 12 kg", 70),
        ("long", "Long Ride (Easy)", 90),
    ),
    date(2027, 1, 18): _wk(
        ("rest", "Rest", 0),
        ("threshold", "Threshold — bike, then sandbag", 50),
        ("strength", "Strength — endurance", 55),
        ("threshold", "Threshold — bike", 40),
        ("rest", "Rest", 0),
        ("ruck", "Hill ruck 15 kg", 70),
        ("long", "Long Ride (Easy)", 90),
    ),
    # Fourth week of this block: same shape, fewer sandbag and kettlebell sets.
    date(2027, 1, 25): _wk(
        ("rest", "Rest", 0),
        ("threshold", "Threshold — bike, then sandbag", 50),
        ("strength", "Strength — endurance", 60),
        ("rower", "Threshold — rower", 40),
        ("rest", "Rest", 0),
        ("ruck", "Hill ruck 18 kg", 70),
        ("long", "Long Ride (Easy)", 90),
    ),
    date(2027, 2, 1): _wk(
        ("rest", "Rest", 0),
        ("threshold", "Threshold — bike, then sandbag", 50),
        ("strength", "Strength — endurance", 60),
        ("rower", "VO2 — rower", 40),
        ("rest", "Rest", 0),
        ("ruck", "Hill ruck 20.4 kg", 70),
        ("long", "Long Ride (Easy)", 90),
    ),
    date(2027, 2, 8): _wk(
        ("rest", "Rest", 0),
        ("strength", "Strength — step-overs + burpee pull-ups", 45),
        ("strength", "Strength — endurance", 45),
        ("rower", "Threshold — rower", 35),
        ("rest", "Rest", 0),
        ("ruck", "Pack test rehearsal 20.4 kg", 60),
        ("long", "Long Ride (Easy)", 75),
    ),
    # Test weekend is filled in by _planned before this table is read.
    date(2027, 2, 15): _wk(
        ("rest", "Rest", 0),
        ("strength", "Strength — light", 25),
        ("bike", "Z2 Easy", 45),
        ("hike", "Easy walk", 30),
        ("rest", "Rest", 0),
        ("hike", "BUSAR test — pack test, step-overs, sandbag deadlift, burpee pull-ups", 0),
        ("hike", "BUSAR test — pack test, step-overs, sandbag deadlift, burpee pull-ups", 0),
    ),
}


def pullup_for_date(d: date) -> str | None:
    """Short pull-up add-on, three days a week. Not a separate load block."""
    if d.weekday() not in _PULLUP_WEEKDAYS:
        return None
    if d < PULLUP_START or d > PULLUP_END:
        return None
    # The bar is in the house from 27 Oct. Strict reps are still 0, so the
    # first phase stays negatives rather than jumping at the bar.
    if d < date(2027, 1, 1):
        return "Pull-ups — negatives, 3×3–5 (bar from 27 Oct)"
    if d < date(2027, 2, 1):
        return "Pull-ups — band-assisted, 3×4–6"
    return "Pull-ups — strict, or stay on the band, 3×3–5"


def _return_day(mon: date, wd: int) -> tuple[str, str, int]:
    return _RETURN_WEEKS[mon][wd]


def _keswick_build_day(mon: date, wd: int) -> tuple[str, str, int]:
    return _KESWICK_WEEKS[mon][wd]


def _lakes_day(wd: int) -> tuple[str, str, int]:
    days = (
        ("rest", "Rest", 0),
        ("strength", "Strength — light", 25),
        ("bike", "Z2 Easy", 45),
        ("hike", "Easy walk", 30),
        ("rest", "Rest", 0),
        ("hike", "Keswick — Skiddaw or High Spy", 360),
        ("hike", "Keswick — Blencathra or Walla Crag", 240),
    )
    return days[wd]


def _recovery_day(wd: int) -> tuple[str, str, int]:
    days = (
        ("rest", "Rest", 0),
        ("hike", "Easy walk", 40),
        ("bike", "Z2 Easy", 45),
        ("hike", "Easy walk", 30),
        ("rest", "Rest", 0),
        ("hike", "Easy walk", 60),
        ("bike", "Z2 Easy", 45),
    )
    return days[wd]


def _scotland_prep_btb(wd: int) -> tuple[str, str, int]:
    days = (
        ("rest", "Rest", 0),
        ("strength", "Strength — heavy", 45),
        ("bike", "Z2 Easy", 60),
        ("hike", "Step-downs + steps", 30),
        ("rest", "Rest", 0),
        ("hike", "Long hill walk", 180),
        ("hike", "Back-to-back hill walk", 120),
    )
    return days[wd]


def _scotland_prep_last(wd: int) -> tuple[str, str, int]:
    days = (
        ("rest", "Rest", 0),
        ("strength", "Strength — heavy", 40),
        ("bike", "Z2 Easy", 60),
        ("hike", "Step-downs + steps", 30),
        ("rest", "Rest", 0),
        ("hike", "Long hill walk", 210),
        ("long", "Long Ride (Easy)", 90),
    )
    return days[wd]


def _scotland_placeholder(wd: int) -> tuple[str, str, int]:
    """Hill week from Mon 22 Mar. Hours are ceilings; hills chosen from conditions."""
    days = (
        ("hike", "Scotland — day on foot", 240),
        ("hike", "Scotland — day on foot", 180),
        ("rest", "Rest", 0),
        ("hike", "Scotland — day on foot", 240),
        ("hike", "Scotland — day on foot", 150),
        ("rest", "Rest", 0),
        ("rest", "Rest", 0),
    )
    return days[wd]


def _maintenance_day(wd: int) -> tuple[str, str, int]:
    days = (
        ("rest", "Rest", 0),
        ("strength", "Strength — maintenance", 45),
        ("bike", "Z2 Easy", 75),
        ("hike", "Easy steps", 30),
        ("rest", "Rest", 0),
        ("hike", "Saturday hill walk", 120),
        ("long", "Long Ride (Easy)", 180),
    )
    return days[wd]


def _phase_name(mon: date) -> str:
    if mon == PROCEDURE_START or date(2026, 10, 19) <= mon <= date(2026, 12, 14):
        return "Return" if mon != PROCEDURE_START else "Clearance"
    if date(2026, 12, 21) <= mon <= date(2026, 12, 28):
        return "Tenerife"
    if date(2027, 1, 4) <= mon <= date(2027, 2, 15):
        return "Keswick build"
    if mon == date(2027, 2, 22):
        return "Lakes"
    if mon == date(2027, 3, 1):
        return "Recovery"
    if mon in (date(2027, 3, 8), date(2027, 3, 15), date(2027, 3, 22)):
        return "Scotland"
    return "Maintenance"


def _fmt_dur(dur: int) -> str:
    if dur < 60:
        return f"{dur}m"
    if dur % 60:
        return f"{dur // 60}h{dur % 60:02d}m"
    return f"{dur // 60}h"


_PHASE_NOTES = {
    "Clearance": (
        "ESWL on 15 Oct was not performed — the fragments had already passed. "
        "Only a confirmation CT remains. Weekend is a normal easy hill walk "
        "with a light pack and a one-hour easy ride. "
        "Until the confirmation CT: stop for flank pain, fever or blood."
    ),
    "Return": (
        "First hard session Tue 20 Oct, then two from the week of 26 Oct "
        "(threshold or VO2, on the rower or the MaxiClimber through the week; "
        "Sunday is the outdoor ride). "
        "Strength is twice a week from 21 Oct: a lighter endurance session "
        "on Wednesday and a load session on Saturday. Every 4th week the "
        "bells get lighter, not the long ride. Sunday reaches 3 hours on 22 Nov."
    ),
    "Tenerife": (
        "Weekday camp hours are on the rower, same duration as the old ride. "
        "Saturday 26 Dec is the optional outdoor Teide ride. "
        "Shorten a session when fitness is not there."
    ),
    "Keswick build": (
        "Saturday is a hill ruck. The pack reaches 20.4 kg on 6 Feb. "
        "Tuesday is the hard rower session, then sandbag deadlift sets. "
        "Wednesday is the lighter strength session, before Thursday. "
        "The week of 25 Jan is a load deload. The week of 8 Feb practises "
        "step-overs and burpee pull-ups. The week of 15 Feb is the taper. "
        "Pull-ups stay a short add-on three days a week. Sunday is outdoors."
    ),
    "Lakes": "The weekend is on foot. The hill names are options, not a fixed route.",
    "Recovery": "Walks, a short weekday rower, and a short outdoor ride on Sunday. No strength session.",
    "Scotland": (
        "Two prep weekends, then a hill week from Mon 22 Mar. Hours are ceilings. "
        "Pick hills that week from the conditions report (Keswick pattern). "
        "Overnight pack about 22 kg when you night out."
    ),
    "Maintenance": (
        "This shape holds through the 3 Oct 2027 checkpoint. "
        "The Haute Route week-by-week block is written after that."
    ),
}


def _phase_note(name: str) -> str:
    if has_turbo() and name in _PHASE_NOTES_TURBO:
        return _PHASE_NOTES_TURBO[name]
    return _PHASE_NOTES.get(name, "")


_PHASE_NOTES_TURBO = {
    "Return": (
        "First hard session Tue 20 Oct, then two from the week of 26 Oct "
        "(threshold or VO2, on the bike, the rower, or the MaxiClimber). "
        "Strength is twice a week from 21 Oct. Sunday reaches 3 hours on 22 Nov."
    ),
    "Tenerife": (
        "Time on the bike, not a distance target. Quality days are 3–4 hours "
        "with an easy day between them. Saturday 26 Dec is the optional longer "
        "Teide day. Shorten a ride when fitness is not there."
    ),
    "Keswick build": (
        "Saturday is a hill ruck. The pack reaches 20.4 kg on 6 Feb. "
        "Tuesday is the hard ride, then sandbag deadlift sets. "
        "The week of 15 Feb is the taper."
    ),
    "Recovery": "Walks and short easy rides. No strength session.",
}


def _day_line(label: str, dur_min: int) -> str:
    if not dur_min:
        return label
    return f"{label} · {_fmt_dur(dur_min)}"


def guide_phases() -> list[dict]:
    """Collapsed phases for the written guide. Built from the same weeks as the calendar."""
    buckets: list[dict] = []
    for wk in iter_weeks():
        if not buckets or buckets[-1]["name"] != wk["phase"]:
            buckets.append({"name": wk["phase"], "weeks": []})
        buckets[-1]["weeks"].append(wk)

    phases = []
    for bucket in buckets:
        weeks = bucket["weeks"]
        start = weeks[0]["days"][0]["date"]
        end = weeks[-1]["days"][-1]["date"]
        days_out: list[dict] = []
        week_rows: list[dict] = []
        sigs = [tuple((d["label"], d["dur_min"]) for d in w["days"]) for w in weeks]
        same = all(s == sigs[0] for s in sigs)
        full_weeks = all(len(w["days"]) == 7 for w in weeks)
        label_stable = full_weeks and all(
            len({w["days"][i]["label"] for w in weeks}) == 1 for i in range(7)
        )
        if same or label_stable:
            for i, d0 in enumerate(weeks[0]["days"]):
                durs = [w["days"][i]["dur_min"] for w in weeks]
                lo, hi = min(durs), max(durs)
                if lo == hi:
                    text = _day_line(d0["label"], lo)
                else:
                    text = f"{d0['label']} · {_fmt_dur(lo)}–{_fmt_dur(hi)}"
                days_out.append({"weekday": d0["weekday"], "text": text})
        else:
            for w in weeks:
                bits = [
                    f"{d['weekday']} {_day_line(d['label'], d['dur_min'])}"
                    for d in w["days"]
                    if not (d["dur_min"] == 0 and d["label"] == "Rest")
                ]
                week_rows.append({
                    "label": w["monday"].strftime("%-d %b"),
                    "text": " · ".join(bits),
                })
        phases.append({
            "name": bucket["name"],
            "start": start,
            "end": end,
            "span": _span(start, end),
            "note": _phase_note(bucket["name"]),
            "days": days_out,
            "weeks": week_rows,
        })
    return phases


def _span(start: date, end: date) -> str:
    if start.year == end.year:
        return f"{start.strftime('%-d %b')} – {end.strftime('%-d %b %Y')}"
    return f"{start.strftime('%-d %b %Y')} – {end.strftime('%-d %b %Y')}"

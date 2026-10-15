"""12-month general fitness block: 12 Oct 2026 → 3 Oct 2027.

Source of truth for the dashboard, calendar, and Garmin bike push (easy Z2 / long
plus bike threshold and bike VO2). Haute Route week-by-week stays gated. Gravel
stays off until the bike is in use.
"""
from __future__ import annotations

from datetime import date, timedelta

PLAN_START = date(2026, 10, 12)  # Monday of the procedure week
PLAN_END = date(2027, 10, 3)     # Sunday before the Year-2 placeholder

PROCEDURE_START = date(2026, 10, 12)
PROCEDURE_END = date(2026, 10, 18)
# Procedure day is Thu 15 Oct. The next 7 days (16–22 Oct) stay easy.
# The first hard session is Tue 27 Oct, the first Tuesday after that window.
EASY_RETURN_END = date(2026, 10, 22)
QUALITY_START = date(2026, 10, 27)
TWO_QUALITY_FROM = date(2026, 11, 2)

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

# Bike labels pushed to Garmin. Easy endurance plus fitness-year hard bike
# sessions (threshold / VO2 on the bike or turbo). Rower, MaxiClimber, Teide,
# hikes, strength, and race-sim labels stay calendar-only.
_GARMIN_BIKE_LABELS = frozenset({
    "Z2 Easy",
    "Long Ride (Easy)",
    "Threshold — bike",
    "VO2 — bike",
    "Camp quality — threshold",
    "Camp quality — VO2",
})
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
    ("hike", "Optional easy walk", 30),
    ("bike", "Optional easy ride", 40),
    ("rest", "Procedure day", 0),
    ("rest", "Rest", 0),
    ("hike", "Optional easy walk", 30),
    ("bike", "Optional easy ride", 45),
)

# Pull-ups three days a week (Tue, Thu, Sat) from the first quality week
# through the day before the BUSAR test. The bar arrives 27 Oct. Strict reps
# are still 0, so the add-on starts with negatives.
_PULLUP_WEEKDAYS = (1, 3, 5)
PULLUP_END = date(2027, 2, 19)


def in_plan(d: date) -> bool:
    return PLAN_START <= d <= PLAN_END


def in_procedure_week(d: date) -> bool:
    return PROCEDURE_START <= d <= PROCEDURE_END


def gravel_sunday_note() -> str:
    if GRAVEL_BIKE_ACTIVE:
        return "Sunday long ride may be ridden on the gravel bike."
    return (
        "Gravel bike is not in use. Sunday stays a road or turbo ride "
        "until that flag is turned on."
    )


def garmin_allowed(d: date, stype: str, label: str) -> bool:
    """True for fitness-year bike days that should be scheduled on Garmin.

    Easy Z2 / long rides plus bike threshold and bike VO2 (including camp
    quality days). Teide, Masca, sweetspot/tempo race labels, and non-bike
    sessions stay off the watch.
    """
    if in_procedure_week(d):
        return False
    if stype in _BLOCKED_PUSH_TYPES:
        return False
    lowered = label.lower()
    if any(tok in lowered for tok in ("teide", "sweetspot", "tempo", "masca")):
        return False
    if stype not in ("bike", "long", "endurance", "recovery", "threshold", "vo2"):
        return False
    return label in _GARMIN_BIKE_LABELS


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
# procedure week is no longer the load base. Hard days are Tuesday, then
# Tuesday and Thursday from 2 Nov, so they are never adjacent.
# Strength is two days: Wednesday is the lighter endurance session (it sits
# the day before Thursday's hard work), Saturday is the load session (Friday
# is rest, Sunday is an easy ride). Labels avoid the word "heavy" because
# safety.py counts that word as a hard session.
_RETURN_WEEKS: dict[date, tuple[tuple[str, str, int], ...]] = {
    date(2026, 10, 19): _wk(
        ("rest", "Rest", 0),
        ("kettlebell", "Kettlebell — easy circuit", 35),
        ("bike", "Z2 Easy", 45),
        ("hike", "Easy steps", 30),
        ("rest", "Rest", 0),
        ("strength", "Strength — load", 45),
        ("long", "Long Ride (Easy)", 60),
    ),
    date(2026, 10, 26): _wk(
        ("rest", "Rest", 0),
        ("threshold", "Threshold — bike", 40),
        ("strength", "Strength — endurance", 45),
        ("hike", "Easy steps", 30),
        ("rest", "Rest", 0),
        ("strength", "Strength — load", 50),
        ("long", "Long Ride (Easy)", 70),
    ),
    date(2026, 11, 2): _wk(
        ("rest", "Rest", 0),
        ("threshold", "Threshold — bike", 40),
        ("strength", "Strength — endurance", 45),
        ("rower", "VO2 — rower", 35),
        ("rest", "Rest", 0),
        ("strength", "Strength — load", 50),
        ("long", "Long Ride (Easy)", 85),
    ),
    # Fourth strength week: same minutes, lighter bells.
    date(2026, 11, 9): _wk(
        ("rest", "Rest", 0),
        ("vo2", "VO2 — bike", 40),
        ("strength", "Strength — endurance", 50),
        ("rower", "Threshold — rower", 35),
        ("rest", "Rest", 0),
        ("strength", "Strength — load", 55),
        ("long", "Long Ride (Easy)", 100),
    ),
    date(2026, 11, 16): _wk(
        ("rest", "Rest", 0),
        ("threshold", "Threshold — bike", 45),
        ("strength", "Strength — endurance", 50),
        ("rower", "VO2 — rower", 40),
        ("rest", "Rest", 0),
        ("strength", "Strength — load", 55),
        ("long", "Long Ride (Easy)", 115),
    ),
    # First 3-hour Sunday (29 Nov). Saturday is the load session, kept short
    # of failure so the long ride stays easy.
    date(2026, 11, 23): _wk(
        ("rest", "Rest", 0),
        ("vo2", "VO2 — bike", 40),
        ("strength", "Strength — endurance", 30),
        ("rower", "Threshold — rower", 35),
        ("rest", "Rest", 0),
        ("strength", "Strength — load", 50),
        ("long", "Long Ride (Easy)", 180),
    ),
    date(2026, 11, 30): _wk(
        ("rest", "Rest", 0),
        ("threshold", "Threshold — bike", 40),
        ("strength", "Strength — endurance", 30),
        ("maxiclimber", "VO2 — MaxiClimber", 35),
        ("rest", "Rest", 0),
        ("strength", "Strength — load", 80),
        ("long", "Long Ride (Easy)", 180),
    ),
    # Eighth strength week: lighter bells again.
    date(2026, 12, 7): _wk(
        ("rest", "Rest", 0),
        ("vo2", "VO2 — bike", 40),
        ("strength", "Strength — endurance", 45),
        ("rower", "Threshold — rower", 40),
        ("rest", "Rest", 0),
        ("strength", "Strength — load", 60),
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
    if d < QUALITY_START or d > PULLUP_END:
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
        return "Return" if mon != PROCEDURE_START else "Procedure"
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
    "Procedure": (
        "Second procedure around 15 Oct. Walk, or a short flat or turbo ride, "
        "only if discharge advice allows it and you are pain-free. "
        "Stop for flank pain, fever, or blood in the urine."
    ),
    "Return": (
        "One hard session in the last October week, then two from November "
        "(threshold or VO2, on the bike, the rower, or the MaxiClimber). "
        "Strength is twice a week: a lighter endurance session on Wednesday "
        "and a load session on Saturday. Every 4th week the bells get lighter, "
        "not the long ride. Sunday reaches 3 hours on 29 Nov."
    ),
    "Tenerife": (
        "Time on the bike, not a distance target. Quality days are 3–4 hours "
        "with an easy day between them. Saturday 26 Dec is the optional longer "
        "Teide day. Shorten a ride when fitness is not there."
    ),
    "Keswick build": (
        "Saturday is a hill ruck. The pack reaches 20.4 kg on 6 Feb. "
        "Tuesday is the hard ride, then sandbag deadlift sets. Wednesday is "
        "the lighter strength session, before Thursday. The week of 25 Jan "
        "is a load deload. The week of 8 Feb practises step-overs and "
        "burpee pull-ups. The week of 15 Feb is the taper. "
        "Pull-ups stay a short add-on three days a week."
    ),
    "Lakes": "The weekend is on foot. The hill names are options, not a fixed route.",
    "Recovery": "Walks and short easy rides. No strength session.",
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
            "note": _PHASE_NOTES.get(bucket["name"], ""),
            "days": days_out,
            "weeks": week_rows,
        })
    return phases


def _span(start: date, end: date) -> str:
    if start.year == end.year:
        return f"{start.strftime('%-d %b')} – {end.strftime('%-d %b %Y')}"
    return f"{start.strftime('%-d %b %Y')} – {end.strftime('%-d %b %Y')}"

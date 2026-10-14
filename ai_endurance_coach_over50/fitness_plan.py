"""12-month general fitness block: 12 Oct 2026 → 3 Oct 2027.

Source of truth for the dashboard, calendar, and Garmin easy-bike push.
Haute Route week-by-week stays gated. Gravel stays off until the bike is in use.
"""
from __future__ import annotations

from datetime import date, timedelta

PLAN_START = date(2026, 10, 12)  # Monday of the procedure week
PLAN_END = date(2027, 10, 3)     # Sunday before the Year-2 placeholder

PROCEDURE_START = date(2026, 10, 12)
PROCEDURE_END = date(2026, 10, 18)

# Home Sunday on 20 Dec 2026. Camp rides do not exceed this.
HOME_SUNDAY_CAP_MIN = 180

GRAVEL_BIKE_ACTIVE = False

# Easy bike labels that already have Garmin builders. Race-quality labels are refused.
_EASY_BIKE_LABELS = frozenset({
    "Z2 Easy",
    "Long Ride (Easy)",
})
_RACE_TYPES = frozenset({"sweetspot", "vo2", "tempo", "ftp", "back_to_back"})

BUSAR_STANDARDS = (
    "Pack test: 3 miles flat with 45 lb (20.4 kg) in under 45 minutes.",
    "Step-overs: 20 lb pack plus a 45 lb kettlebell, up and over a picnic table for 30 minutes.",
    "Trap-bar deadlift: 225 lb (102 kg), at least 15 reps in one minute. Needs a trap bar or a gym.",
    "Burpee pull-ups: 20 lb pack, at least 50 in 10 minutes. Needs a pull-up bar and bodyweight pull-ups first.",
)

# Christmas camp. One day (26 Dec) sits on the 180-minute home-Sunday cap.
# The old 5–6 h Teide / Masca / finale grid is not in this map.
_CAMP: dict[date, tuple[str, str, int]] = {
    date(2026, 12, 21): ("rest", "Tenerife — travel", 0),
    date(2026, 12, 22): ("rest", "Tenerife — arrive", 0),
    date(2026, 12, 23): ("bike", "Z2 Easy", 90),
    date(2026, 12, 24): ("long", "Long Ride (Easy)", 120),
    date(2026, 12, 25): ("bike", "Z2 Easy", 75),
    date(2026, 12, 26): ("long", "Long Ride (Easy)", 180),
    date(2026, 12, 27): ("rest", "Tenerife — mid-camp rest", 0),
    date(2026, 12, 28): ("long", "Long Ride (Easy)", 120),
    date(2026, 12, 29): ("strength", "Strength — easy circuit", 30),
    date(2026, 12, 30): ("long", "Long Ride (Easy)", 150),
    date(2026, 12, 31): ("bike", "Z2 Easy", 120),
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

# (sat_min, sat_kg, sun_min) for the seven Keswick-build weeks starting 4 Jan 2027.
_KESWICK_BUILD = (
    (75, 8, 90),
    (75, 10, 105),
    (90, 10, 120),
    (90, 12, 120),
    (105, 12, 135),
    (105, 14, 150),
    (120, 14, 150),
)


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
    """True only for an easy bike day that should be scheduled on Garmin."""
    if in_procedure_week(d):
        return False
    if stype in _RACE_TYPES:
        return False
    lowered = label.lower()
    if any(tok in lowered for tok in ("teide", "sweetspot", "vo2", "tempo", "masca")):
        return False
    if stype not in ("bike", "long", "endurance", "recovery"):
        return False
    return label in _EASY_BIKE_LABELS


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
                "type": day["type"],
                "label": day["label"] if day["type"] != "rest" else day["label"],
                "dur_fmt": _fmt_dur(dur) if dur else None,
                "dur_min": dur,
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
    "BUSAR test — pack test, step-overs, trap-bar deadlift, burpee pull-ups"
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


def _return_day(mon: date, wd: int) -> tuple[str, str, int]:
    idx = (mon - date(2026, 10, 19)).days // 7
    sun = min(HOME_SUNDAY_CAP_MIN, 60 + idx * 15)
    wed = min(75, 45 + idx * 5)
    sat = min(90, 45 + idx * 5)
    days = (
        ("rest", "Rest", 0),
        ("strength", "Strength — easy circuit", 35),
        ("bike", "Z2 Easy", wed),
        ("hike", "Easy steps", 30),
        ("rest", "Rest", 0),
        ("hike", "Easy hill walk", sat),
        ("long", "Long Ride (Easy)", sun),
    )
    return days[wd]


def _keswick_build_day(mon: date, wd: int) -> tuple[str, str, int]:
    idx = (mon - date(2027, 1, 4)).days // 7
    sat_min, sat_kg, sun = _KESWICK_BUILD[idx]
    days = (
        ("rest", "Rest", 0),
        ("strength", "Strength — heavy", 50),
        ("bike", "Z2 Easy", 60),
        ("hike", "Step-downs + steps", 30),
        ("rest", "Rest", 0),
        ("ruck", f"Hill ruck {sat_kg} kg", sat_min),
        ("long", "Long Ride (Easy)", sun),
    )
    return days[wd]


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
    """Indicative hill week from Mon 22 Mar. Dates and hills are still open."""
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
        "Tuesday is an easy strength circuit. The Wednesday ride, Saturday hill walk, "
        "and Sunday ride get longer each week. Sunday stops at 3 hours."
    ),
    "Tenerife": (
        "Easy rides only. The minutes are a ceiling — shorten the ride when "
        "fitness is not there. A shorter logged ride still counts. "
        "The old 5–6 hour Teide / Masca grid is not in this plan."
    ),
    "Keswick build": (
        "Saturday is a hill ruck. The pack gets heavier across the seven weeks. "
        "Sunday stays an easy ride."
    ),
    "Lakes": "The weekend is on foot. The hill names are options, not a fixed route.",
    "Recovery": "Walks and short easy rides. No strength session.",
    "Scotland": (
        "Two prep weekends, then a hill week. Dates and hills for that week are still open."
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

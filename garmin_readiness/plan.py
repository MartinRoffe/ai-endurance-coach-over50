"""12-week training plan data and lookup helpers."""
from __future__ import annotations

from datetime import date, timedelta

# Each week: list of 7 sessions Mon–Sun, each (type, label, duration_min)
# Types: rest | strength | bike | tempo | ftp | ruck | long
PLAN_START = date(2026, 5, 18)
assert PLAN_START.weekday() == 0, "Plan must start on Monday"

TRAINING_WEEKS: list[list[tuple[str, str, int]]] = [
    # WK 01
    [
        ("rest",     "Rest",                  0),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Easy Spin",            60),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Easy Spin",            60),
        ("ruck",     "Ruck  8 kg",           60),
        ("long",     "Long Ride",            90),
    ],
    # WK 02
    [
        ("rest",     "Rest",                  0),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Zone 2 Steady",        60),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Zone 2 Steady",        60),
        ("ruck",     "Ruck  8–10 kg",        70),
        ("long",     "Long Ride",           105),
    ],
    # WK 03
    [
        ("rest",     "Rest",                  0),
        ("strength", "Light KB",             35),
        ("ftp",      "FTP Test",             60),
        ("strength", "Easy MaxiClimber",     20),
        ("bike",     "Recovery Spin",        60),
        ("ruck",     "Ruck  10 kg",          80),
        ("long",     "Long Ride",           120),
    ],
    # WK 04 (deload)
    [
        ("rest",     "Rest",                  0),
        ("strength", "Light KB",             30),
        ("bike",     "Easy Spin",            45),
        ("strength", "MaxiClimber",          20),
        ("bike",     "Easy Spin",            45),
        ("ruck",     "Ruck  8 kg",           45),
        ("long",     "Long Ride",            75),
    ],
    # WK 05
    [
        ("rest",     "Rest",                  0),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Structured Z2",        60),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Z2 + Hills",           60),
        ("ruck",     "Ruck  10 kg",          75),
        ("long",     "Long Ride",           135),
    ],
    # WK 06
    [
        ("rest",     "Rest",                  0),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Cadence Drills",       60),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Hilly Z2",             60),
        ("ruck",     "Ruck  10–12 kg",       85),
        ("long",     "Long Ride",           140),
    ],
    # WK 07
    [
        ("rest",     "Rest",                  0),
        ("strength", "Light KB",             35),
        ("ftp",      "FTP Re-test",          60),
        ("strength", "Easy MaxiClimber",     25),
        ("tempo",    "Tempo Intervals",      60),
        ("ruck",     "Ruck  12 kg",          95),
        ("long",     "Long Ride",           150),
    ],
    # WK 08 (deload)
    [
        ("rest",     "Rest",                  0),
        ("strength", "Light KB",             30),
        ("bike",     "Easy Spin",            45),
        ("strength", "MaxiClimber",          20),
        ("bike",     "Easy Spin",            45),
        ("ruck",     "Ruck  10 kg",          50),
        ("long",     "Long Ride",            80),
    ],
    # WK 09
    [
        ("rest",     "Rest",                  0),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Z2 Endurance",         60),
        ("strength", "KB + MaxiClimber",     45),
        ("tempo",    "Tempo Intervals",      60),
        ("ruck",     "Ruck  12–15 kg",      105),
        ("long",     "Long Ride",           165),
    ],
    # WK 10
    [
        ("rest",     "Rest",                  0),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Low Cadence",          60),
        ("strength", "KB + MaxiClimber",     45),
        ("tempo",    "Tempo Intervals",      60),
        ("ruck",     "Ruck  12–15 kg",      110),
        ("long",     "Long Ride",           180),
    ],
    # WK 11
    [
        ("rest",     "Rest",                  0),
        ("strength", "KB + MaxiClimber",     45),
        ("bike",     "Z2 Endurance",         60),
        ("strength", "Light KB",             35),
        ("bike",     "Easy Prep Ride",       60),
        ("ruck",     "Easy Ruck  8 kg",      60),
        ("long",     "Long Ride",           210),
    ],
    # WK 12
    [
        ("rest",     "Rest",                  0),
        ("strength", "Light KB",             30),
        ("ftp",      "Final FTP Test",       60),
        ("strength", "Easy MaxiClimber",     20),
        ("bike",     "Easy Spin",            45),
        ("ruck",     "Celebration Ruck",     60),
        ("long",     "Long Ride (Easy)",    120),
    ],
]

_PLAN_DAYS = len(TRAINING_WEEKS) * 7  # 84


def session_for_date(d: date) -> tuple[str, str, int] | None:
    """Return (type, label, duration_min) for the given date, or None if outside the plan."""
    delta = (d - PLAN_START).days
    if delta < 0 or delta >= _PLAN_DAYS:
        return None
    week_idx, day_idx = divmod(delta, 7)
    return TRAINING_WEEKS[week_idx][day_idx]


def build_calendar_weeks() -> list[dict]:
    today = date.today()
    weeks = []
    for wk_idx, sessions in enumerate(TRAINING_WEEKS):
        wk_start = PLAN_START + timedelta(weeks=wk_idx)
        days = []
        for day_offset, (stype, label, dur) in enumerate(sessions):
            d = wk_start + timedelta(days=day_offset)
            dur_fmt = ""
            if dur:
                if dur < 60:
                    dur_fmt = f"{dur}m"
                elif dur % 60:
                    dur_fmt = f"{dur // 60}h{dur % 60:02d}m"
                else:
                    dur_fmt = f"{dur // 60}h"
            days.append({
                "date": d,
                "day_num": d.day,
                "month_abbr": d.strftime("%b"),
                "type": stype,
                "label": label,
                "dur_fmt": dur_fmt,
                "is_today": d == today,
                "is_past": d < today,
            })
        weeks.append({"week_num": wk_idx + 1, "start": wk_start, "days": days})
    return weeks

"""Structured workout detail for one calendar day.

The plan tuple is still (type, label, minutes). This module adds the warm-up,
main set, cool-down, loads, and the notes the Sessions modal shows. Nothing
here changes the stored week. Caps and the HRV modulation note are read, not
applied a second time.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from .fitness_plan import (
    ATHLETE_FTP_W,
    ATHLETE_MAX_HR,
    garmin_allowed,
    pullup_for_date,
    session_for_date,
)
from .load import pack_kg_from_label

Exercise = dict[str, str]
Block = dict[str, str]


def _ex(name: str, sets_reps: str, load: str, tempo: str, rest: str) -> Exercise:
    return {
        "name": name,
        "sets_reps": sets_reps,
        "load": load,
        "tempo": tempo,
        "rest": rest,
    }


def _block(name: str, detail: str) -> Block:
    return {"name": name, "detail": detail}


_TYPE_LABELS = {
    "rest": "Rest",
    "bike": "Bike",
    "long": "Long ride",
    "threshold": "Threshold",
    "vo2": "VO2",
    "rower": "Rower",
    "maxiclimber": "MaxiClimber",
    "kettlebell": "Kettlebell",
    "strength": "Strength",
    "hike": "On foot",
    "ruck": "Ruck",
    "endurance": "Endurance",
    "recovery": "Recovery",
}

# Fourth week of each strength cycle. Minutes stay; the bells and the sets drop.
_DELOAD_DATES = {
    date(2026, 11, 11), date(2026, 11, 14),
    date(2026, 12, 9), date(2026, 12, 12),
    date(2027, 1, 26), date(2027, 1, 27),
}

_KIT = (
    "Kit: kettlebells 8, 12, 14, 16, 20 and 24 kg, one of each, plus a sandbag "
    "or a weighted vest, a rower, and a MaxiClimber. No trap bar. "
    "The pull-up bar is in use from 27 Oct."
)


def _fmt_dur(dur: int) -> str:
    if dur <= 0:
        return ""
    if dur < 60:
        return f"{dur} min"
    hours, mins = divmod(dur, 60)
    if mins:
        return f"{hours} h {mins} min"
    return f"{hours} h"


def _zone_book() -> dict[str, Any]:
    """HR and power targets. Garmin zones and a tested FTP win when they exist."""
    hr: dict[int, tuple[Optional[int], Optional[int]]] = {}
    hr_source = f"percent of max HR {ATHLETE_MAX_HR}"
    try:
        from .hr_profile import load_hr_profile
        profile = load_hr_profile()
    except Exception:
        profile = None
    garmin = (profile or {}).get("garmin") or {}
    zones = garmin.get("zones") or []
    if zones:
        for zone in zones:
            hr[int(zone["zone"])] = (zone.get("lo"), zone.get("hi"))
        method = garmin.get("method_label") or "zones"
        hr_source = f"Garmin {method}"
    else:
        max_hr = ATHLETE_MAX_HR
        z2_lo = round(max_hr * 0.60)
        z2_hi = round(max_hr * 0.70)
        z3_hi = round(max_hr * 0.80)
        z4_hi = round(max_hr * 0.90)
        hr = {
            1: (None, z2_lo - 1),
            2: (z2_lo, z2_hi),
            3: (z2_hi + 1, z3_hi),
            4: (z3_hi + 1, z4_hi),
            5: (z4_hi + 1, max_hr),
        }

    ftp = ATHLETE_FTP_W
    ftp_source = f"working FTP {ATHLETE_FTP_W} W"
    try:
        from .power_profile import _coggan_zones, build_power_profile
        measured = build_power_profile()
    except Exception:
        measured = None
        from .power_profile import _coggan_zones
    if measured and measured.get("ftp_w"):
        ftp = int(measured["ftp_w"])
        ftp_source = f"tested FTP {ftp} W"
    power: dict[int, tuple[Optional[int], Optional[int], str]] = {}
    for zone in _coggan_zones(ftp):
        power[int(zone["zone"])] = (zone.get("lo"), zone.get("hi"), zone["label"])
    return {"hr": hr, "hr_source": hr_source, "ftp": ftp, "ftp_source": ftp_source, "power": power}


def _hr(book: dict[str, Any], zone: int) -> str:
    lo, hi = book["hr"].get(zone, (None, None))
    if lo is None and hi is not None:
        text = f"Z{zone} · under {int(hi) + 1} bpm"
    elif lo is not None and hi is not None:
        text = f"Z{zone} · {int(lo)}–{int(hi)} bpm"
    elif lo is not None:
        text = f"Z{zone} · {int(lo)} bpm and up"
    else:
        text = f"Z{zone}"
    return f"{text} ({book['hr_source']})"


def _pwr(book: dict[str, Any], zone: int) -> str:
    lo, hi, label = book["power"][zone]
    if lo is None and hi is not None:
        span = f"under {int(hi) + 1} W"
    elif lo is not None and hi is not None:
        span = f"{int(lo)}–{int(hi)} W"
    elif lo is not None:
        span = f"{int(lo)} W and up"
    else:
        span = label
    return f"Z{zone} {label} · {span} ({book['ftp_source']})"


def _empty(d: date, stype: str, label: str, dur: int) -> dict[str, Any]:
    return {
        "date": d.isoformat(),
        "type": stype,
        "type_label": _TYPE_LABELS.get(stype, stype.replace("_", " ").title() or "Session"),
        "title": label or "Rest",
        "duration_min": dur,
        "duration_fmt": _fmt_dur(dur),
        "intensity": "",
        "hr_target": "",
        "power_target": "",
        "rpe_target": "",
        "purpose": "",
        "blocks": [],
        "exercises": [],
        "addon": pullup_for_date(d) or "",
        "ruck_pack": "",
        "ruck_route": "",
        "ruck_elevation": "",
        "cap_note": "",
        "instead": "",
        "modulation_note": "",
        "garmin": False,
        "garmin_text": "Not pushed to Garmin",
        "deload": d in _DELOAD_DATES,
        "role": "rest" if stype == "rest" or dur <= 0 and "rest" in (label or "").lower() else stype,
    }


def day_detail(
    d: date,
    session: Optional[tuple[str, str, int]] = None,
    *,
    book: Optional[dict[str, Any]] = None,
    cap_note: str = "",
    instead: str = "",
) -> dict[str, Any]:
    """Detail for the planned session on ``d``. ``session`` overrides the lookup."""
    if session is None:
        found = session_for_date(d)
        session = found if found else ("rest", "Rest", 0)
    stype, label, dur = session
    book = book or _zone_book()
    detail = _empty(d, stype, label, dur)
    detail["cap_note"] = cap_note
    detail["instead"] = instead
    detail["garmin"] = garmin_allowed(d, stype, label)
    detail["garmin_text"] = "Pushed to Garmin" if detail["garmin"] else "Not pushed to Garmin"
    _fill(detail, d, stype, label, dur, book)
    if detail["addon"] and d == date(2027, 2, 9):
        detail["addon"] += " — included in today's main set. Skip a second pull-up set if the elbows are done."
    return detail


def _fill(detail: dict[str, Any], d: date, stype: str, label: str, dur: int, book: dict[str, Any]) -> None:
    low = label.lower()
    if stype == "rest" or (dur <= 0 and "busar" not in low):
        _fill_rest(detail, label)
        return
    if "busar test" in low:
        _fill_busar(detail)
        return
    if "then sandbag" in low:
        _fill_bike_then_sandbag(detail, d, dur, book)
        return
    if stype in ("kettlebell", "strength") or low.startswith("strength"):
        _fill_strength(detail, d, label, dur, book)
        return
    if stype == "ruck" or "ruck" in low or "pack test rehearsal" in low:
        _fill_ruck(detail, label, dur, book)
        return
    if stype == "hike" or "walk" in low or "step" in low or low.startswith("keswick") or "scotland" in low:
        _fill_hike(detail, label, dur, book)
        return
    if stype == "rower" or "rower" in low:
        _fill_rower(detail, label, dur, book)
        return
    if stype == "maxiclimber" or "maxiclimber" in low:
        _fill_maxi(detail, label, dur, book)
        return
    if "teide" in low:
        _fill_teide(detail, dur, book)
        return
    if stype in ("threshold", "vo2") or "threshold" in low or "vo2" in low:
        _fill_quality_bike(detail, label, dur, book)
        return
    if stype in ("bike", "long", "endurance") or "z2" in low or "long ride" in low:
        _fill_easy_bike(detail, label, dur, book)
        return
    detail["purpose"] = (
        "Do the session as written. Until the confirmation CT: stop for flank pain, "
        "fever or blood."
    )
    detail["rpe_target"] = "Easy"
    detail["blocks"] = [
        _block("Warm-up", "5–10 min easy."),
        _block("Main set", label),
        _block("Cool-down", "5 min easy."),
    ]


def _fill_rest(detail: dict[str, Any], label: str) -> None:
    detail["role"] = "rest"
    detail["rpe_target"] = "—"
    detail["intensity"] = "Rest"
    low = label.lower()
    if "attended" in low or "no treatment" in low:
        detail["purpose"] = (
            "Clinic day. ESWL was not performed — the fragments had already passed. "
            "No training today. Until the confirmation CT: stop for flank pain, "
            "fever or blood."
        )
    elif "procedure" in low:
        detail["purpose"] = (
            "Procedure day. No training. Until the confirmation CT: stop for "
            "flank pain, fever or blood."
        )
    elif "travel" in low:
        detail["purpose"] = "Travel day. Walk through the airport. No session to make up later."
    elif "camp" in low or "new year" in low or "post-camp" in low:
        detail["purpose"] = "Rest inside the camp block. Eat and sleep. The next ride can be shorter."
    else:
        detail["purpose"] = (
            "Full rest. Monday and Friday stay empty so the hard days are not stacked. "
            "A short stroll is fine. A session is not."
        )
    detail["blocks"] = [_block("Today", "No workout.")]


def _fill_busar(detail: dict[str, Any]) -> None:
    detail["role"] = "test"
    detail["type_label"] = "Test"
    detail["rpe_target"] = "As the piece requires"
    detail["intensity"] = "Test weekend. Split the four pieces across the two days."
    detail["hr_target"] = "The pack test is a brisk walk, not a VO2 session."
    detail["purpose"] = (
        "BUSAR entry test, 20–21 Feb 2027. Do not train through it. "
        "Split the pieces across Saturday and Sunday, and eat between them."
    )
    detail["blocks"] = [
        _block(
            "Pack test",
            "3 miles flat with 20.4 kg (45 lb) in under 45 minutes, about 4 mph. "
            "Warm up 10 min with a lighter pack first.",
        ),
        _block(
            "Step-overs",
            "20 lb (about 9 kg) pack, plus a sandbag or the 24 kg kettlebell, "
            "up and over a picnic table for 30 minutes.",
        ),
        _block(
            "Deadlift",
            "Standard is 102 kg (225 lb) for at least 15 reps in one minute. "
            "Sandbag or a barbell. There is no trap bar, and a kettlebell is not this load.",
        ),
        _block(
            "Burpee pull-ups",
            "20 lb pack, at least 50 in 10 minutes. Strict pull-ups started at 0. "
            "Use the bar. Step down. Do not add the pack if the pull-ups are still negatives.",
        ),
    ]
    detail["ruck_pack"] = "20.4 kg for the pack test. About 9 kg for the step-overs and the burpee pull-ups."
    detail["ruck_route"] = "Flat measured 3 miles for the pack test. A picnic table, or the same sturdy step you have practised on, for the step-overs."
    detail["ruck_elevation"] = "The pack test is flat. Do not turn it into a hill."


def _fill_bike_then_sandbag(detail: dict[str, Any], d: date, dur: int, book: dict[str, Any]) -> None:
    detail["role"] = "sandbag"
    detail["type_label"] = "Threshold, then strength"
    detail["deload"] = d in _DELOAD_DATES
    detail["hr_target"] = _hr(book, 4)
    detail["power_target"] = _pwr(book, 4)
    detail["rpe_target"] = "8 on the bike, 6–7 on the sandbag" if not detail["deload"] else "7 on the bike, 5 on the sandbag"
    detail["intensity"] = f"{detail['power_target']}. Heart rate {detail['hr_target']}."
    detail["purpose"] = (
        "Hard ride first, sandbag second, so the heavier lift is not the day before Thursday. "
        "The sandbag is the deadlift you can actually load. A barbell is fine if you have one. "
        "There is no trap bar. A kettlebell is not this lift: the heaviest bell is 24 kg and the "
        "test is 102 kg for 15 reps in one minute. That standard is the target, not today's load. "
        + _KIT
    )
    detail["blocks"] = [
        _block("Warm-up", "8 min easy spinning, zone 1 rising into zone 2."),
        _block("Main set", "2 × 6 min at threshold. 3 min easy spinning between the efforts."),
        _block("Cool-down", "7 min easy spin, then a few minutes on your feet before the sandbag."),
        _block(
            "Sandbag",
            "After the ride. Stop each set with 2 reps left. If the back rounds, the bag is too heavy.",
        ),
    ]
    if detail["deload"]:
        detail["exercises"] = [
            _ex("Sandbag deadlift", "2×5", "Same load as the last build week, not more", "2 sec down, stand up", "2–3 min"),
        ]
        detail["purpose"] = (
            "Deload week. The ride stays, the sandbag sets are cut in half, and the load does not go up. "
            + detail["purpose"]
        )
    elif d == date(2027, 2, 2):
        detail["exercises"] = [
            _ex("Sandbag deadlift", "4×5", "A little heavier only if 19 Jan was clean", "2 sec down, stand up", "2–3 min"),
            _ex("Sandbag deadlift, lighter and smoother", "1×8", "Lighter than the work sets", "Steady, no bounce", "—"),
        ]
    elif d == date(2027, 1, 12):
        detail["exercises"] = [
            _ex("Sandbag deadlift", "5×5", "Add load only if every rep on 5 Jan was clean", "2 sec down, stand up", "2–3 min"),
        ]
    elif d == date(2027, 1, 19):
        detail["exercises"] = [
            _ex("Sandbag deadlift", "4×6", "A load that still leaves 2 reps", "2 sec down, stand up", "2–3 min"),
        ]
    else:
        detail["exercises"] = [
            _ex("Sandbag deadlift", "4×5", "About 40 kg to start, less if the back rounds", "2 sec down, stand up", "2–3 min"),
        ]
    if dur and dur != 50:
        detail["blocks"][0]["detail"] += f" The day is {_fmt_dur(dur)}."


def _fill_strength(detail: dict[str, Any], d: date, label: str, dur: int, book: dict[str, Any]) -> None:
    low = label.lower()
    detail["hr_target"] = "Not an HR-zone session. " + _hr(book, 2) + " is plenty if a circuit runs long."
    detail["power_target"] = ""
    if "easy circuit" in low or label.startswith("Kettlebell — easy"):
        _easy_circuit(detail)
    elif "step-overs" in low or "burpee" in low:
        _skills(detail)
    elif "light" in low and d <= date(2027, 2, 21):
        _taper_strength(detail)
    elif "endurance" in low:
        _endurance(detail, d, dur)
    elif "load" in low:
        _load(detail, d, dur)
    elif "maintenance" in low or stype_is_generic(low):
        _maintenance_strength(detail)
    else:
        _maintenance_strength(detail)
    if dur >= 80 and detail["role"] == "load":
        walk = dur - 40
        detail["blocks"].append(_block(
            "On foot",
            f"About {walk} min easy walk after the lifting, no pack. Heart rate in zone 1–2. "
            "This is the time on your feet, not more sets.",
        ))
    detail["intensity"] = f"RPE {detail['rpe_target']} (1–10)."


def stype_is_generic(low: str) -> bool:
    return "maintenance" in low or low.strip() in {"strength — heavy", "strength — light"}


def _easy_circuit(detail: dict[str, Any]) -> None:
    detail["role"] = "easy"
    detail["rpe_target"] = "4"
    detail["deload"] = False
    detail["purpose"] = (
        "Easy kettlebell circuit. Reintroduce the squat, the hinge, the row, and "
        "the press. Stop while it feels easy. Until the confirmation CT: stop for "
        "flank pain, fever or blood. " + _KIT
    )
    detail["blocks"] = [
        _block("Warm-up", "5 min easy march, or an easy row."),
        _block("Main set", "2 rounds of the list. Rest as written. Do not add a round."),
        _block("Cool-down", "5 min walk."),
    ]
    detail["exercises"] = [
        _ex("Goblet squat", "2×8", "12 kg", "3-1-1", "60 s"),
        _ex("Two-hand swing", "2×10", "16 kg", "Hike and float", "60 s"),
        _ex("One-arm row", "2×8 / side", "12 kg", "2-1-2", "60 s"),
        _ex("Half-kneeling press", "2×6 / side", "8 kg", "2-1-2", "60 s"),
    ]


def _load(detail: dict[str, Any], d: date, dur: int) -> None:
    detail["role"] = "load"
    detail["rpe_target"] = "5" if detail["deload"] else "6–7"
    by_date = {
        date(2026, 10, 24): [
            _ex("Goblet squat", "3×6", "16 kg", "3-1-1", "2 min"),
            _ex("Kettlebell deadlift (hinge, not the test lift)", "3×6", "20 kg", "3-1-1", "2 min"),
            _ex("One-arm row", "3×6 / side", "16 kg", "2-1-2", "90 s"),
            _ex("Strict press", "3×5 / side", "12 kg", "2-1-2", "90 s"),
            _ex("Step-up", "2×6 / leg", "Bodyweight, or the 8 kg bell", "2 s up, 3 s down", "60 s"),
            _ex("Suitcase carry", "3×30 m", "16 kg", "Walk tall", "90 s"),
        ],
        date(2026, 10, 31): [
            _ex("Goblet squat", "4×5", "20 kg", "3-1-1", "2 min"),
            _ex("Kettlebell deadlift (hinge, not the test lift)", "4×5", "24 kg", "3-1-1", "2 min"),
            _ex("One-arm row", "4×6 / side", "20 kg", "2-1-2", "90 s"),
            _ex("Strict press", "3×5 / side", "12 kg", "2-1-2", "90 s"),
            _ex("Turkish get-up", "2×3 / side", "8 kg", "Slow, about 30 s a rep", "90 s"),
            _ex("Suitcase carry", "3×40 m", "20 kg", "Walk tall", "90 s"),
        ],
        date(2026, 11, 7): [
            _ex("Goblet squat", "4×5", "20 kg", "3-1-1", "2 min"),
            _ex("Kettlebell deadlift (hinge, not the test lift)", "4×5", "24 kg", "3-1-1", "2 min"),
            _ex("One-arm row", "4×5 / side", "20 kg", "2-1-2", "2 min"),
            _ex("Strict press", "4×5 / side", "14 kg", "2-1-2", "90 s"),
            _ex("Turkish get-up", "3×2 / side", "12 kg", "Slow, about 30 s a rep", "90 s"),
            _ex("Suitcase carry", "3×40 m", "24 kg", "Walk tall", "90 s"),
        ],
        date(2026, 11, 14): [
            _ex("Goblet squat", "2×5", "16 kg", "3-1-1", "2 min"),
            _ex("Kettlebell deadlift (hinge, not the test lift)", "2×5", "20 kg", "3-1-1", "2 min"),
            _ex("One-arm row", "2×5 / side", "16 kg", "2-1-2", "90 s"),
            _ex("Strict press", "2×5 / side", "12 kg", "2-1-2", "90 s"),
            _ex("Turkish get-up", "2×2 / side", "8 kg", "Slow, about 30 s a rep", "90 s"),
            _ex("Suitcase carry", "2×30 m", "16 kg", "Walk tall", "90 s"),
        ],
        date(2026, 11, 21): [
            _ex("Goblet squat", "3×5", "24 kg", "3-1-1", "2 min"),
            _ex("Kettlebell deadlift (hinge, not the test lift)", "3×5", "24 kg", "3-1-1", "2 min"),
            _ex("One-arm row", "3×5 / side", "20 kg", "2-1-2", "90 s"),
            _ex("Strict press", "3×5 / side", "14 kg", "2-1-2", "90 s"),
            _ex("Suitcase carry", "2×40 m", "20 kg", "Walk tall", "90 s"),
        ],
        date(2026, 11, 28): [
            _ex("Goblet squat", "4×5", "24 kg", "3-1-1", "2 min"),
            _ex("One-arm row", "4×5 / side", "24 kg", "2-1-2", "2 min"),
            _ex("Strict press", "3×5 / side", "14 kg", "2-1-2", "90 s"),
            _ex("Turkish get-up", "3×3 / side", "12 kg", "Slow, about 30 s a rep", "90 s"),
            _ex("Step-up", "3×8 / leg", "16 kg in the rack", "2 s up, 3 s down", "60 s"),
            _ex("Suitcase carry", "3×40 m", "24 kg", "Walk tall", "90 s"),
        ],
        date(2026, 12, 5): [
            _ex("Goblet squat", "4×5", "24 kg", "3-1-1", "2 min"),
            _ex("One-arm row", "4×5 / side", "24 kg", "2-1-2", "2 min"),
            _ex("Strict press", "3×5 / side", "14 kg", "2-1-2", "90 s"),
            _ex("Turkish get-up", "3×3 / side", "12 kg", "Slow, about 30 s a rep", "90 s"),
            _ex("Step-up", "3×8 / leg", "16 kg in the rack", "2 s up, 3 s down", "60 s"),
            _ex("Suitcase carry", "3×40 m", "24 kg", "Walk tall", "90 s"),
        ],
        date(2026, 12, 12): [
            _ex("Goblet squat", "2×5", "20 kg", "3-1-1", "2 min"),
            _ex("One-arm row", "2×5 / side", "20 kg", "2-1-2", "90 s"),
            _ex("Strict press", "2×5 / side", "12 kg", "2-1-2", "90 s"),
            _ex("Turkish get-up", "2×2 / side", "8 kg", "Slow, about 30 s a rep", "90 s"),
            _ex("Suitcase carry", "2×30 m", "16 kg", "Walk tall", "90 s"),
        ],
        date(2026, 12, 19): [
            _ex("Goblet squat", "3×5", "20 kg", "3-1-1", "2 min"),
            _ex("One-arm row", "3×5 / side", "20 kg", "2-1-2", "90 s"),
            _ex("Strict press", "3×4 / side", "14 kg", "2-1-2", "90 s"),
            _ex("Turkish get-up", "2×2 / side", "12 kg", "Slow, about 30 s a rep", "90 s"),
            _ex("Suitcase carry", "2×40 m", "20 kg", "Walk tall", "90 s"),
        ],
    }
    detail["exercises"] = by_date.get(d, [
        _ex("Goblet squat", "3×6", "20 kg", "3-1-1", "2 min"),
        _ex("One-arm row", "3×6 / side", "20 kg", "2-1-2", "90 s"),
        _ex("Strict press", "3×5 / side", "12 kg", "2-1-2", "90 s"),
        _ex("Suitcase carry", "3×30 m", "20 kg", "Walk tall", "90 s"),
    ])
    detail["blocks"] = [
        _block("Warm-up", "5 min easy march, plus two lighter sets of the first lift."),
        _block("Main set", "The list below. Stop each set with 2 reps left. Rest as written."),
        _block("Cool-down", "5 min walk. Shake the grip out."),
    ]
    if detail["deload"]:
        detail["purpose"] = (
            "Deload. Same movements, fewer sets, one bell lighter. The Sunday ride does not shrink "
            "this week — the lifting does. " + _KIT
        )
    elif d == date(2026, 11, 21):
        detail["purpose"] = (
            "Load day before the first 3-hour Sunday. Leave 2 or 3 reps in reserve. "
            "Sunday stays in zone 2 even if the legs feel dull. " + _KIT
        )
    elif d >= date(2026, 12, 19):
        detail["purpose"] = (
            "Last load day before Tenerife. Most of a long Saturday is an easy walk, not more lifting. "
            "No gym strength on the camp. " + _KIT
        )
    else:
        detail["purpose"] = (
            "Heavier strength day. Friday was rest, and Sunday's ride is easy, so this is the day "
            "for lower reps. It is not the day before a hard ride. The kettlebell deadlift trains "
            "the hinge. It is not the 102 kg test lift. " + _KIT
        )
    if dur:
        detail["blocks"][1]["detail"] += f" The session is {_fmt_dur(dur)}."


def _endurance(detail: dict[str, Any], d: date, dur: int) -> None:
    detail["role"] = "endurance"
    detail["rpe_target"] = "5" if detail["deload"] else "6"
    rounds = "2 rounds" if detail["deload"] or dur <= 30 else "3 rounds"
    if d in (date(2026, 11, 4),):
        rounds = "4 rounds"
    catalog = {
        date(2026, 10, 21): [
            _ex("Two-hand swing", "3×10", "16 kg", "Hike and float", "45 s"),
            _ex("Goblet squat", "3×8", "16 kg", "3-1-1", "45 s"),
            _ex("Step-up", "3×8 / leg", "8 kg, or bodyweight", "2 s up, 3 s down", "45 s"),
            _ex("One-arm row", "3×8 / side", "12 kg", "2-1-2", "45 s"),
            _ex("Suitcase carry", "3×20 m", "16 kg", "Walk tall", "90 s between rounds"),
        ],
        date(2026, 10, 28): [
            _ex("Two-hand swing", "3×12", "20 kg", "Hike and float", "45 s"),
            _ex("Goblet squat", "3×8", "20 kg", "3-1-1", "45 s"),
            _ex("Step-up", "3×8 / leg", "12 kg", "2 s up, 3 s down", "45 s"),
            _ex("One-arm row", "3×8 / side", "16 kg", "2-1-2", "45 s"),
            _ex("Suitcase carry", "3×20 m", "20 kg", "Walk tall", "90 s between rounds"),
        ],
        date(2026, 11, 4): [
            _ex("Two-hand swing", "4×12", "20 kg", "Hike and float", "45 s"),
            _ex("Goblet squat", "4×8", "20 kg", "3-1-1", "45 s"),
            _ex("Step-up", "4×8 / leg", "12 kg", "2 s up, 3 s down", "45 s"),
            _ex("One-arm row", "4×8 / side", "16 kg", "2-1-2", "45 s"),
            _ex("Suitcase carry", "4×30 m", "20 kg", "Walk tall", "90 s between rounds"),
        ],
        date(2026, 11, 11): [
            _ex("Two-hand swing", "2×8", "16 kg", "Hike and float", "60 s"),
            _ex("Goblet squat", "2×6", "16 kg", "3-1-1", "60 s"),
            _ex("Step-up", "2×6 / leg", "Bodyweight", "2 s up, 3 s down", "60 s"),
            _ex("One-arm row", "2×6 / side", "12 kg", "2-1-2", "60 s"),
            _ex("Suitcase carry", "2×20 m", "12 kg", "Walk tall", "90 s between rounds"),
        ],
        date(2026, 11, 18): [
            _ex("Two-hand swing", "2×10", "20 kg", "Hike and float", "45 s"),
            _ex("Goblet squat", "2×6", "16 kg", "3-1-1", "45 s"),
            _ex("Step-up", "2×6 / leg", "12 kg", "2 s up, 3 s down", "45 s"),
            _ex("One-arm row", "2×6 / side", "16 kg", "2-1-2", "45 s"),
            _ex("Suitcase carry", "2×20 m", "16 kg", "Walk tall", "90 s between rounds"),
        ],
        date(2026, 11, 25): [
            _ex("Two-hand swing", "2×10", "20 kg", "Hike and float", "45 s"),
            _ex("Goblet squat", "2×6", "16 kg", "3-1-1", "45 s"),
            _ex("Step-up", "2×6 / leg", "12 kg", "2 s up, 3 s down", "45 s"),
            _ex("One-arm row", "2×6 / side", "16 kg", "2-1-2", "45 s"),
            _ex("Suitcase carry", "2×20 m", "16 kg", "Walk tall", "90 s between rounds"),
        ],
        date(2026, 12, 2): [
            _ex("Two-hand swing", "2×12", "20 kg", "Hike and float", "45 s"),
            _ex("Step-up", "2×8 / leg", "16 kg", "2 s up, 3 s down", "45 s"),
            _ex("Goblet squat", "2×6", "20 kg", "3-1-1", "45 s"),
            _ex("One-arm row", "2×8 / side", "16 kg", "2-1-2", "45 s"),
            _ex("Suitcase carry", "2×20 m", "20 kg", "Walk tall", "90 s between rounds"),
        ],
        date(2026, 12, 9): [
            _ex("Two-hand swing", "2×8", "16 kg", "Hike and float", "60 s"),
            _ex("Goblet squat", "2×6", "16 kg", "3-1-1", "60 s"),
            _ex("Step-up", "2×6 / leg", "8 kg", "2 s up, 3 s down", "60 s"),
            _ex("One-arm row", "2×6 / side", "12 kg", "2-1-2", "60 s"),
            _ex("Suitcase carry", "2×20 m", "12 kg", "Walk tall", "90 s between rounds"),
        ],
        date(2026, 12, 16): [
            _ex("Two-hand swing", "2×10", "16 kg", "Hike and float", "60 s"),
            _ex("Goblet squat", "2×6", "16 kg", "3-1-1", "60 s"),
            _ex("Step-up", "2×6 / leg", "12 kg", "2 s up, 3 s down", "60 s"),
            _ex("One-arm row", "2×6 / side", "12 kg", "2-1-2", "60 s"),
            _ex("Suitcase carry", "2×20 m", "16 kg", "Walk tall", "90 s between rounds"),
        ],
        date(2027, 1, 6): [
            _ex("Two-hand swing", "3×12", "20 kg", "Hike and float", "45 s"),
            _ex("Goblet squat", "3×8", "20 kg", "3-1-1", "45 s"),
            _ex("Step-up", "3×8 / leg", "16 kg", "2 s up, 3 s down", "45 s"),
            _ex("One-arm row", "3×8 / side", "16 kg", "2-1-2", "45 s"),
            _ex("Suitcase carry", "3×30 m", "20 kg", "Walk tall", "90 s between rounds"),
        ],
        date(2027, 1, 13): [
            _ex("Two-hand swing", "3×12", "20 kg", "Hike and float", "45 s"),
            _ex("Goblet squat", "3×8", "20 kg", "3-1-1", "45 s"),
            _ex("Step-up", "3×8 / leg", "16 kg", "2 s up, 3 s down", "45 s"),
            _ex("One-arm row", "3×8 / side", "16 kg", "2-1-2", "45 s"),
            _ex("Suitcase carry", "3×30 m", "20 kg", "Walk tall", "90 s between rounds"),
        ],
        date(2027, 1, 20): [
            _ex("Two-hand swing", "3×12", "20 kg", "Hike and float", "45 s"),
            _ex("Goblet squat", "3×8", "20 kg", "3-1-1", "45 s"),
            _ex("One-arm row", "3×8 / side", "20 kg", "2-1-2", "45 s"),
            _ex("Suitcase carry", "3×30 m", "24 kg", "Walk tall", "90 s between rounds"),
            _ex("Step-over", "3×2 min", "8 kg vest or pack, plus the 16 kg bell", "Change the lead, quiet feet", "2 min"),
        ],
        date(2027, 1, 27): [
            _ex("Two-hand swing", "2×8", "16 kg", "Hike and float", "60 s"),
            _ex("Goblet squat", "2×6", "16 kg", "3-1-1", "60 s"),
            _ex("Step-up", "2×6 / leg", "12 kg", "2 s up, 3 s down", "60 s"),
            _ex("One-arm row", "2×6 / side", "16 kg", "2-1-2", "60 s"),
            _ex("Step-over", "2×1 min", "8 kg vest, plus the 12 kg bell", "Quiet feet", "2 min"),
        ],
        date(2027, 2, 3): [
            _ex("Two-hand swing", "3×12", "20 kg", "Hike and float", "45 s"),
            _ex("Goblet squat", "3×8", "20 kg", "3-1-1", "45 s"),
            _ex("One-arm row", "3×8 / side", "20 kg", "2-1-2", "45 s"),
            _ex("Suitcase carry", "3×30 m", "24 kg", "Walk tall", "90 s between rounds"),
            _ex("Step-over", "4×3 min", "10 kg vest or pack, plus the 20 kg bell", "Change the lead, quiet feet", "2 min"),
        ],
        date(2027, 2, 10): [
            _ex("Two-hand swing", "2×10", "16 kg", "Hike and float", "60 s"),
            _ex("Step-up", "2×6 / leg", "12 kg", "2 s up, 3 s down", "60 s"),
            _ex("One-arm row", "2×6 / side", "16 kg", "2-1-2", "60 s"),
            _ex("Suitcase carry", "2×20 m", "16 kg", "Walk tall", "90 s between rounds"),
        ],
    }
    detail["exercises"] = catalog.get(d, [
        _ex("Two-hand swing", f"{rounds.split()[0]}×10", "16 kg", "Hike and float", "45 s"),
        _ex("Goblet squat", f"{rounds.split()[0]}×8", "16 kg", "3-1-1", "45 s"),
        _ex("Step-up", f"{rounds.split()[0]}×8 / leg", "12 kg", "2 s up, 3 s down", "45 s"),
        _ex("One-arm row", f"{rounds.split()[0]}×8 / side", "12 kg", "2-1-2", "45 s"),
    ])
    detail["blocks"] = [
        _block("Warm-up", "5 min easy march or an easy row."),
        _block("Main set", f"{rounds}. Move on the rest times. Do not turn this into a max set."),
        _block("Cool-down", "5 min walk."),
    ]
    if d == date(2027, 1, 20):
        detail["purpose"] = (
            "First step-overs. The test is 30 minutes with a 20 lb pack and a sandbag or the 24 kg bell. "
            "Today is a few short sets, the day before a hard ride, so it stays short. " + _KIT
        )
    elif d == date(2027, 2, 3):
        detail["purpose"] = (
            "Step-overs get a little longer. Still not the 30-minute test. Saturday is the 20.4 kg ruck, "
            "so finish this feeling you could do another round. " + _KIT
        )
    elif d == date(2027, 2, 10):
        detail["purpose"] = (
            "Light endurance only. Thursday is a hard row and Saturday is the timed pack rehearsal. "
            "No step-overs today. " + _KIT
        )
    elif detail["deload"]:
        detail["purpose"] = (
            "Deload of the lighter strength day. Fewer rounds and a lighter bell. "
            "This day sits before a hard session, so it was never the place to grind. " + _KIT
        )
    else:
        detail["purpose"] = (
            "Lighter strength day: swings, squats, step-ups, rows, and carries. "
            "From November it is the day before Thursday's hard session, so it stays at RPE 6 "
            "with reps in reserve. Step-ups are the path into the picnic-table step-overs. " + _KIT
        )
    if dur >= 55:
        detail["blocks"].append(_block(
            "Easy finish",
            "If the lifting finishes early, walk the rest of the time. Do not add sets.",
        ))


def _skills(detail: dict[str, Any]) -> None:
    detail["role"] = "skills"
    detail["rpe_target"] = "6–7"
    detail["purpose"] = (
        "Test-element practice, ten days out. This is the harder strength day of the week, "
        "and it is not the day before Thursday's row. Saturday is the flat pack rehearsal, "
        "so the step-overs stay short. The burpee pull-up standard is 50 with a 20 lb pack. "
        "You are not doing 50 today, and you are not wearing the pack for them yet. " + _KIT
    )
    detail["blocks"] = [
        _block("Warm-up", "5 min easy march, then a few unloaded step-ups."),
        _block("Main set", "Step-overs, then the burpee pull-ups. Rest as written."),
        _block("Cool-down", "5 min walk. Elbows and shoulders, not a second workout."),
    ]
    detail["exercises"] = [
        _ex(
            "Step-over",
            "4×3 min",
            "About 9 kg vest or pack, plus the 20 or 24 kg bell",
            "Change the lead. Quiet feet. Step down, don't drop.",
            "2 min",
        ),
        _ex(
            "Burpee to the bar",
            "5×3",
            "Bodyweight. No pack.",
            "After each burpee, one negative or one band-assisted pull-up. Step down off the bar.",
            "90 s",
        ),
    ]


def _taper_strength(detail: dict[str, Any]) -> None:
    detail["role"] = "taper"
    detail["rpe_target"] = "3–4"
    detail["deload"] = False
    detail["purpose"] = (
        "Taper. The test is at the weekend. Keep the joints moving and stop well short of fatigue. "
        "No sandbag, no step-overs, no reps to failure. " + _KIT
    )
    detail["blocks"] = [
        _block("Warm-up", "5 min easy walk."),
        _block("Main set", "2 easy rounds. If anything feels heavy, stop the session."),
        _block("Cool-down", "5 min walk."),
    ]
    detail["exercises"] = [
        _ex("Goblet squat", "2×5", "12 kg", "3-1-1", "60 s"),
        _ex("One-arm row", "2×5 / side", "12 kg", "2-1-2", "60 s"),
        _ex("Strict press", "2×5 / side", "8 kg", "2-1-2", "60 s"),
    ]


def _maintenance_strength(detail: dict[str, Any]) -> None:
    detail["role"] = "maintenance"
    detail["rpe_target"] = "6"
    detail["purpose"] = (
        "One strength day to keep the patterns after the test block. Two reps in reserve. " + _KIT
    )
    detail["blocks"] = [
        _block("Warm-up", "5 min easy march."),
        _block("Main set", "Three sets of each. Rest as written."),
        _block("Cool-down", "5 min walk."),
    ]
    detail["exercises"] = [
        _ex("Goblet squat", "3×6", "20 kg", "3-1-1", "90 s"),
        _ex("Two-hand swing", "3×10", "20 kg", "Hike and float", "60 s"),
        _ex("One-arm row", "3×6 / side", "20 kg", "2-1-2", "90 s"),
        _ex("Strict press", "3×5 / side", "12 kg", "2-1-2", "90 s"),
        _ex("Suitcase carry", "3×30 m", "20 kg", "Walk tall", "90 s"),
    ]


def _fill_quality_bike(detail: dict[str, Any], label: str, dur: int, book: dict[str, Any]) -> None:
    low = label.lower()
    vo2 = "vo2" in low or detail["type"] == "vo2"
    zone = 5 if vo2 else 4
    detail["role"] = "vo2" if vo2 else "threshold"
    detail["hr_target"] = _hr(book, zone)
    detail["power_target"] = _pwr(book, zone)
    detail["rpe_target"] = "8–9" if vo2 else "7–8"
    detail["intensity"] = f"{detail['power_target']}. Heart rate {detail['hr_target']}."
    if "camp quality" in low:
        _camp_quality(detail, vo2, dur)
        return
    if vo2:
        detail["blocks"] = [
            _block("Warm-up", "10 min easy, zone 1 into zone 2."),
            _block("Main set", "5 × 3 min at VO2 power, or the top of zone 5 if you are on heart rate. 2 min easy between."),
            _block("Cool-down", "7 min easy spin."),
        ]
        detail["purpose"] = (
            "One of the two hard days. Short repeats, full rest between them. "
            "Not pushed to Garmin — follow this, not a watch workout."
        )
    else:
        work = "2 × 10 min" if dur >= 45 else "2 × 8 min"
        between = "5 min easy between" if dur >= 45 else "4 min easy between"
        detail["blocks"] = [
            _block("Warm-up", "10 min easy, zone 1 into zone 2."),
            _block("Main set", f"{work} at threshold. {between}."),
            _block("Cool-down", "10 min easy spin, zone 1."),
        ]
        detail["purpose"] = (
            "One of the two hard days. Hold the power steady rather than surging the first minute. "
            "Not pushed to Garmin."
        )


def _camp_quality(detail: dict[str, Any], vo2: bool, dur: int) -> None:
    if vo2:
        detail["blocks"] = [
            _block("Warm-up", "20 min in zone 2."),
            _block("Main set", "5 × 4 min at VO2 power, 4 min easy zone 2 between."),
            _block("Cool-down", "The rest of the ride is zone 2, with the last 20 min very easy."),
        ]
    else:
        detail["blocks"] = [
            _block("Warm-up", "20 min in zone 2."),
            _block("Main set", "3 × 20 min at threshold, 10 min zone 2 between. On the 4-hour day, make the efforts 25 min."),
            _block("Cool-down", "Zone 2 until the last 20 min, then very easy."),
        ]
    detail["purpose"] = (
        f"Camp quality day, about {_fmt_dur(dur) or 'the planned time'}. "
        "An easy day sits on either side. Shorten it when the legs are not there. Not pushed to Garmin."
    )


def _fill_easy_bike(detail: dict[str, Any], label: str, dur: int, book: dict[str, Any]) -> None:
    long_ride = detail["type"] == "long" or "long" in label.lower()
    detail["role"] = "long" if long_ride else "endurance_bike"
    detail["hr_target"] = _hr(book, 2)
    detail["power_target"] = _pwr(book, 2)
    detail["rpe_target"] = "3–4"
    detail["intensity"] = f"{detail['power_target']}. Heart rate {detail['hr_target']}."
    if dur >= 150:
        main = max(dur - 30, 0)
        detail["blocks"] = [
            _block("Warm-up", "15 min easy, zone 1."),
            _block("Main set", f"{main} min in zone 2. On a climb, go slower before you leave zone 2."),
            _block("Cool-down", "15 min easy, zone 1."),
        ]
    elif dur >= 40:
        main = max(dur - 15, 0)
        detail["blocks"] = [
            _block("Warm-up", "10 min easy, zone 1."),
            _block("Main set", f"{main} min in zone 2."),
            _block("Cool-down", "5 min easy."),
        ]
    else:
        detail["blocks"] = [
            _block("Warm-up", "5 min very easy."),
            _block("Main set", f"The rest in zone 1–2, {_fmt_dur(dur)} all in."),
            _block("Cool-down", "A few minutes easier than the main set."),
        ]
    fuel = " Eat from the first hour." if dur >= 75 else ""
    pushed = " This one is pushed to Garmin." if detail["garmin"] else " Not pushed to Garmin."
    if long_ride:
        detail["purpose"] = (
            "Easy long ride. The point is time in zone 2, not a harder average." + fuel + pushed
        )
    else:
        detail["purpose"] = "Easy aerobic ride. Conversation pace." + fuel + pushed


def _fill_teide(detail: dict[str, Any], dur: int, book: dict[str, Any]) -> None:
    detail["role"] = "long"
    detail["hr_target"] = _hr(book, 2)
    detail["power_target"] = _pwr(book, 2)
    detail["rpe_target"] = "3–4, higher only while a steep pitch lasts"
    detail["intensity"] = f"{detail['power_target']}. Heart rate {detail['hr_target']}."
    detail["blocks"] = [
        _block("Warm-up", "20 min easy before the climb starts to matter."),
        _block("Main set", "Ride by time, in zone 2. When the road steepens, drop the gear and the speed, not the heart-rate cap."),
        _block("Cool-down", "Turn around whenever you want. The last 15 min are easy."),
    ]
    detail["purpose"] = (
        f"Optional Teide day, about {_fmt_dur(dur)}. There is no distance target. "
        "Shorten it when fitness is not there. Not pushed to Garmin."
    )


def _fill_rower(detail: dict[str, Any], label: str, dur: int, book: dict[str, Any]) -> None:
    vo2 = "vo2" in label.lower()
    zone = 5 if vo2 else 4
    detail["role"] = "vo2" if vo2 else "threshold"
    detail["hr_target"] = _hr(book, zone)
    detail["power_target"] = ""
    detail["rpe_target"] = "8–9" if vo2 else "7–8"
    detail["intensity"] = f"Heart rate {detail['hr_target']}. RPE {detail['rpe_target']}."
    if vo2 and dur <= 35:
        detail["blocks"] = [
            _block("Warm-up", "8 min easy row. Damper in the middle, not a sprint setting."),
            _block("Main set", "5 × 2 min hard, 2 min easy between. Breathe before the first hard stroke."),
            _block("Cool-down", "9 min easy row."),
        ]
    elif vo2:
        detail["blocks"] = [
            _block("Warm-up", "8 min easy row."),
            _block("Main set", "6 × 2 min hard, 2 min easy between."),
            _block("Cool-down", "Easy row for whatever is left."),
        ]
    elif dur <= 35:
        detail["blocks"] = [
            _block("Warm-up", "8 min easy row."),
            _block("Main set", "3 × 5 min at threshold, 2 min easy between."),
            _block("Cool-down", "8 min easy row."),
        ]
    else:
        detail["blocks"] = [
            _block("Warm-up", "8 min easy row."),
            _block("Main set", "4 × 5 min at threshold, 2 min easy between."),
            _block("Cool-down", "Easy row for whatever is left."),
        ]
    detail["purpose"] = (
        "Hard day on the rower, so the bike is not the only place you can do it. "
        "Not pushed to Garmin."
    )


def _fill_maxi(detail: dict[str, Any], label: str, dur: int, book: dict[str, Any]) -> None:
    detail["role"] = "vo2"
    detail["hr_target"] = _hr(book, 5)
    detail["power_target"] = ""
    detail["rpe_target"] = "8"
    detail["intensity"] = f"Heart rate {detail['hr_target']}. RPE {detail['rpe_target']}."
    detail["blocks"] = [
        _block("Warm-up", "5–8 min easy climbing. Hands light on the bars."),
        _block("Main set", "6 × 2 min hard, 90 s easy between. Short steps. Do not yank the handles."),
        _block("Cool-down", "Easy climbing for the time that is left."),
    ]
    detail["purpose"] = (
        f"Hard day on the MaxiClimber, about {_fmt_dur(dur) or 'the planned time'}. "
        "Not pushed to Garmin."
    )


def _fill_ruck(detail: dict[str, Any], label: str, dur: int, book: dict[str, Any]) -> None:
    detail["role"] = "ruck"
    kg = pack_kg_from_label(label)
    pack = f"{kg:g} kg" if kg else "the pack on the label"
    detail["ruck_pack"] = pack
    rehearsal = "rehearsal" in label.lower()
    detail["hr_target"] = _hr(book, 2)
    detail["power_target"] = ""
    detail["rpe_target"] = "6–7 for the timed piece" if rehearsal else "4–5"
    detail["intensity"] = f"Heart rate {detail['hr_target']}. The pack is the stress, not a higher zone."
    if rehearsal:
        detail["blocks"] = [
            _block("Warm-up", "10 min walk, lighter than 20.4 kg."),
            _block("Main set", "3 miles flat with 20.4 kg. The standard is under 45 minutes, about 4 mph. Record the time. Do not start at a run."),
            _block("Cool-down", "10 min walk with the pack off."),
        ]
        detail["ruck_route"] = "A flat loop you can measure: park paths or a quiet lane. Not a hill."
        detail["ruck_elevation"] = "As little climbing as you can find. The test is flat."
        detail["purpose"] = (
            "Dress rehearsal for the pack test, one week out. Time it, then stop. "
            "No strength session on top. Not pushed to Garmin."
        )
    else:
        main = max(dur - 20, 0)
        detail["blocks"] = [
            _block("Warm-up", "10 min walk, pack light or off."),
            _block("Main set", f"About {main} min with {pack}. Same route as last week."),
            _block("Cool-down", "10 min with the pack off."),
        ]
        detail["ruck_route"] = (
            "The same local hill each week. Hadleigh from Leigh-on-Sea is the default "
            "if that is the hill you can repeat. Do not pick a bigger hill on a week the pack goes up."
        )
        detail["ruck_elevation"] = (
            "Whatever that hill already gives you. Kilograms go up, the route stays put."
        )
        detail["purpose"] = (
            f"Hill ruck at {pack}. Duration stays about {_fmt_dur(dur) or 'the same'}. "
            "This is the pack-test load climbing toward 20.4 kg. Not pushed to Garmin."
        )


def _fill_hike(detail: dict[str, Any], label: str, dur: int, book: dict[str, Any]) -> None:
    detail["role"] = "hike"
    detail["hr_target"] = _hr(book, 2)
    detail["power_target"] = ""
    detail["rpe_target"] = "3–4"
    detail["intensity"] = f"Heart rate {detail['hr_target']} on the climbs. RPE {detail['rpe_target']}."
    low = label.lower()
    if "skiddaw" in low or "high spy" in low:
        detail["blocks"] = [
            _block("Warm-up", "Walk the first 15 min. Do not start uphill at a march."),
            _block("Main set", "One route only. High option: Skiddaw by Jenkin Hill, about 9 km and 900 m, around 6 h with a 15 kg pack. Lower option: High Spy and Cat Bells."),
            _block("Cool-down", "The descent is part of the session. Short steps. Poles if you have them."),
        ]
        detail["ruck_pack"] = "About 15 kg if the winter hill feels familiar. Less if it does not."
        detail["ruck_route"] = "From Keswick. Skiddaw by Jenkin Hill, or High Spy to Cat Bells if the tops are unfriendly."
        detail["ruck_elevation"] = "About 900 m for Skiddaw by the western path. Less for High Spy. These are planning figures — check the map."
        detail["purpose"] = "Lake District weekend, on foot. Pick the route that matches the weather and your head, not the bigger name."
        detail["rpe_target"] = "4–6"
        return
    if "blencathra" in low or "walla crag" in low:
        detail["blocks"] = [
            _block("Warm-up", "Easy walking until you are warm. Leave Sharp Edge and Hall's Fell alone."),
            _block("Main set", "High option: Blencathra by Blease Fell, about 8 km and 700 m, around 4 h. Lower option: Walla Crag, Bleaberry Fell, and Ashness Bridge, about 9 km and 540 m."),
            _block("Cool-down", "Finish in daylight. The descent is when tired legs get sloppy."),
        ]
        detail["ruck_pack"] = "About 15 kg, or less on the second day."
        detail["ruck_route"] = "Blencathra from Threlkeld by Blease Fell, or Walla Crag from Great Wood."
        detail["ruck_elevation"] = "About 700 m for Blease Fell. About 540 m for the Walla Crag round."
        detail["purpose"] = "Second day on foot. Choose the lower round if Saturday was bigger than planned."
        detail["rpe_target"] = "4–5"
        return
    if "scotland" in low:
        # Exact munros stay open (athlete picks from conditions that week).
        # Structure and pack come from Mountain & Road Build + fitness plan.
        detail["blocks"] = [
            _block(
                "Warm-up",
                "Easy walking until warm. Check Weatherline / avalanche forecast "
                "and pick a day inside your current winter skills — fitness is not "
                "winter skill after a long break.",
            ),
            _block(
                "Main set",
                f"{label}. Hours are a ceiling, not a target. Choose a broad, "
                "simple ridge or valley round that matches the forecast; turn back "
                "early if wind, ice, or navigation gets beyond what you want that day. "
                "Day-trip pack lighter; overnight kit is about 22 kg when you camp.",
            ),
            _block(
                "Cool-down",
                "Finish with daylight in hand. Controlled short steps on the descent; "
                "poles if you have them.",
            ),
        ]
        detail["ruck_pack"] = (
            "Day pack as needed for the route. Overnight winter pack about 22 kg "
            "when the trip includes a night out."
        )
        detail["ruck_route"] = (
            "Pick from the week's conditions report — same rule as Keswick: "
            "high option only if the tops are in play; otherwise a lower round. "
            "Exact hills are chosen that week, not locked in the calendar."
        )
        detail["ruck_elevation"] = (
            "Treat the session hours as the ceiling. Vertical follows the route "
            "you pick, not a fixed metre target."
        )
        detail["purpose"] = (
            "Scotland winter hill week (ready from Mon 22 Mar 2027). "
            "Day trips and optional multi-day; hills chosen from conditions. "
            "Not pushed to Garmin."
        )
        detail["rpe_target"] = "4–5"
        return
    if "step" in low:
        detail["blocks"] = [
            _block("Warm-up", "5 min easy walking."),
            _block("Main set", "Stairs or a single step. Change the lead leg every minute. Three seconds down. No pack."),
            _block("Cool-down", "5 min flat walking."),
        ]
        detail["purpose"] = (
            "Easy steps. Time on your feet, and the pattern the step-overs will use later. "
            "Until the confirmation CT: stop for flank pain, fever or blood."
        )
        return
    if "light pack" in low or "hill walk" in low:
        detail["blocks"] = [
            _block("Warm-up", "10 min easy on the flat."),
            _block(
                "Main set",
                f"Hill walk for the rest of the {_fmt_dur(dur) or 'session'}. "
                "Light pack (about 5–8 kg). Conversation pace. Short steps on the way down.",
            ),
            _block("Cool-down", "The last 5–10 min flatter and easier."),
        ]
        detail["ruck_pack"] = "About 5–8 kg. Light enough that the walk stays easy."
        detail["ruck_route"] = "Local hill. Hadleigh from Leigh-on-Sea is the default repeatable climb."
        detail["ruck_elevation"] = "Whatever that hill already gives you. This is not a loaded ruck yet."
        detail["purpose"] = (
            "Normal easy weekend walk with a light pack. ESWL was not performed. "
            "Until the confirmation CT: stop for flank pain, fever or blood."
        )
        return
    detail["blocks"] = [
        _block("Warm-up", "10 min easy, on the flat if you can."),
        _block("Main set", f"Walk for the rest of the {_fmt_dur(dur) or 'session'}. Conversation pace. Short steps on the way down."),
        _block("Cool-down", "The last 5–10 min flatter and easier."),
    ]
    detail["purpose"] = (
        "Easy time on foot. The bike does not train descents. "
        "Until the confirmation CT: stop for flank pain, fever or blood."
    )


def brief_activity(activity: dict) -> dict[str, Any]:
    """A logged Garmin activity, trimmed for the day panel."""
    seconds = activity.get("duration_seconds") or 0
    metres = activity.get("distance_meters") or 0
    name = (activity.get("name") or activity.get("type_key") or "Activity").strip()
    return {
        "name": name or "Activity",
        "type_key": activity.get("type_key") or "",
        "minutes": int(round(float(seconds) / 60)) if seconds else 0,
        "distance_km": round(float(metres) / 1000, 1) if metres else None,
        "avg_hr": int(round(float(activity["avg_hr"]))) if activity.get("avg_hr") else None,
        "avg_power_w": int(round(float(activity["avg_power_w"]))) if activity.get("avg_power_w") else None,
        "elevation_m": int(round(float(activity["elevation_gain"]))) if activity.get("elevation_gain") else None,
    }


def _modulation_note(day: date) -> str:
    if day != date.today():
        return ""
    try:
        from .history import baseline_stats, composite_score, load
        from .modulation import modulation_decision_text, resolve_modulation
        metrics = load(day)
        if metrics is None:
            return ""
        stats = baseline_stats(day)
        comp = composite_score(metrics, stats)
        light, modulation = resolve_modulation(day, metrics, comp)
    except Exception:
        return ""
    status = (light or {}).get("status")
    if status not in ("amber", "red") and not (modulation and modulation.get("label")):
        return ""
    return modulation_decision_text(light, modulation)


def _cap_fields(day: date, cache: dict) -> tuple[str, str]:
    try:
        from .safety import prescribed_week
        monday = day - timedelta(days=day.weekday())
        capped_days = prescribed_week(monday, cache)
        capped = capped_days[day.weekday()]
    except Exception:
        return "", ""
    if not capped.changed or not capped.reason:
        return "", ""
    stype, label, dur = capped.session
    instead = label if dur <= 0 else f"{label} · {_fmt_dur(dur)}"
    return capped.reason, instead


def attach_calendar_details(weeks: list[dict], *, today: Optional[date] = None) -> None:
    """Add ``detail`` and logged-activity flags onto fitness calendar cells."""
    today = today or date.today()
    book = _zone_book()
    cache: dict = {}
    mod = _modulation_note(today)
    for week in weeks:
        for day in week.get("days") or []:
            d = day["date"]
            cap_note, instead = _cap_fields(d, cache)
            session = (day.get("type") or "rest", day.get("label") or "Rest", int(day.get("dur_min") or 0))
            detail = day_detail(d, session, book=book, cap_note=cap_note, instead=instead)
            if d == today and mod:
                detail["modulation_note"] = mod
            day["detail"] = detail
            day["weekday_short"] = d.strftime("%a")
            day["show_logged"] = d <= today
            day.setdefault("logged", [])


def attach_logged_activities(weeks: list[dict], acts_by_date: dict[str, list[dict]], *, today: Optional[date] = None) -> None:
    today = today or date.today()
    for week in weeks:
        for day in week.get("days") or []:
            d = day["date"]
            day["show_logged"] = d <= today
            if d > today:
                day["logged"] = []
                continue
            rows = acts_by_date.get(d.isoformat(), [])
            day["logged"] = [brief_activity(row) for row in rows]

"""HRV-guided daily session modulation (green/amber/red traffic light).

Turns morning readiness data into a concrete, accept/declinable change to
today's planned session. Green = train as planned; amber = keep duration but
drop intensity; red = swap to short recovery. Applied via the existing
plan-override machinery (/apply-plan-change), so the calendar, email, and
Garmin workout sync all respect an accepted modulation automatically.

recovery_gate() runs first and handles masters-specific illness/rest signals
before HRV traffic-light modulation.
"""
from __future__ import annotations

import statistics
from datetime import date
from typing import Optional

from .history import get_plan_override, load_btb_summary, load_durability, load_session_rpe, raw_history
from .hr_plan import hr_session_for_date
from .metrics import DailyMetrics
from .plan import PLAN_START, session_for_date_extended

QUALITY_BIKE_TYPES = frozenset({"ftp", "tempo", "sweetspot", "vo2"})

# Map a planned session type to its easier amber-day variant (duration kept).
EASIER_VARIANT: dict[str, tuple[str, str]] = {
    "ftp":      ("bike", "Zone 2 Steady"),
    "tempo":    ("bike", "Zone 2 Steady"),
    "long":     ("long", "Long Ride (Easy)"),
    "bike":     ("bike", "Recovery Spin"),
    "strength": ("strength", "Light KB"),
    "ruck":     ("ruck", "Easy Walk (no load)"),
}

# Haute Route plan equivalent — kept separate so swaps stay within the HR
# plan's type/label vocabulary (hr_calendar.html colours and modals key off
# them). recovery/gym are deliberately absent: already easy, pill only.
HR_EASIER_VARIANT: dict[str, tuple[str, str]] = {
    "ftp":          ("endurance", "Z2 Endurance"),
    "tempo":        ("endurance", "Z2 Endurance"),
    "vo2":          ("endurance", "Z2 Endurance"),
    "sweetspot":    ("endurance", "Z2 Endurance"),
    "endurance":    ("endurance", "Z2 Easy"),
    "long":         ("long", "Long Ride (Easy)"),
    "back_to_back": ("long", "Long Ride (Easy)"),
}


def hrv_traffic_light(m: DailyMetrics, comp_z: Optional[float]) -> dict:
    """Classify today's readiness as green / amber / red / unknown.

    Primary signal: last-night HRV vs its own 30-day baseline (z-score),
    with the 7-day vs 30-day mean ratio as a secondary chronic-suppression
    signal, and the composite readiness z as a backstop.
    """
    # Exclude the row for m's own date from the baseline (when present) rather
    # than blindly dropping the last row — before the watch syncs, the last DB
    # row is yesterday and must stay in the baseline.
    today_iso = m.date.isoformat() if m.date else None
    rows = raw_history(31)
    baseline = [r["hrv_last_night"] for r in rows
                if r.get("date") != today_iso and r["hrv_last_night"] is not None]
    hrv_today = m.hrv_last_night

    hrv_z = None
    ratio = None
    if hrv_today is not None and len(baseline) >= 7:
        mean = statistics.mean(baseline)
        stdev = statistics.pstdev(baseline)
        if stdev > 0:
            hrv_z = (hrv_today - mean) / stdev
        last7 = [v for v in baseline[-7:] if v is not None]
        if last7 and mean > 0:
            ratio = statistics.mean(last7) / mean

    if hrv_z is None and comp_z is None:
        return {"status": "unknown", "hrv_z": None, "ratio": None,
                "reason": "Not enough HRV history yet for a baseline."}

    def _fmt(reasons: list[str]) -> str:
        return "; ".join(reasons)

    red_reasons = []
    if hrv_z is not None and hrv_z < -1.5:
        red_reasons.append(f"HRV {hrv_today:.0f} ms is {abs(hrv_z):.1f}σ below your 30-day baseline")
    if comp_z is not None and comp_z < -1.2:
        red_reasons.append(f"composite readiness is {comp_z:+.1f}σ")
    if red_reasons:
        return {"status": "red", "hrv_z": hrv_z, "ratio": ratio, "reason": _fmt(red_reasons)}

    amber_reasons = []
    if hrv_z is not None and hrv_z < -0.75:
        amber_reasons.append(f"HRV {hrv_today:.0f} ms is {abs(hrv_z):.1f}σ below baseline")
    if comp_z is not None and comp_z < -0.5:
        amber_reasons.append(f"composite readiness is {comp_z:+.1f}σ")
    if ratio is not None and ratio < 0.92:
        amber_reasons.append(f"7-day HRV average is {(1 - ratio) * 100:.0f}% below your 30-day norm")
    if amber_reasons:
        return {"status": "amber", "hrv_z": hrv_z, "ratio": ratio, "reason": _fmt(amber_reasons)}

    return {"status": "green", "hrv_z": hrv_z, "ratio": ratio,
            "reason": "HRV and readiness in normal range."}


def session_modulation(target: date, m: DailyMetrics, comp_z: Optional[float],
                       light: Optional[dict] = None) -> Optional[dict]:
    """Suggested session modification for today, or None when nothing to do.

    None when: status green/unknown, no planned session, rest day, or an
    override already exists for today (don't re-suggest over a decision).
    Pass a precomputed `light` (from hrv_traffic_light) to avoid recomputing.
    """
    if light is None:
        light = hrv_traffic_light(m, comp_z)
    status = light["status"]
    base = {"light": light, "date": target.isoformat()}

    sess = session_for_date_extended(target)
    hr_day = False
    if sess is None:
        sess = hr_session_for_date(target)
        hr_day = sess is not None
    if sess is None or sess[0] == "rest":
        return base if status in ("amber", "red") else None  # show pill, no swap
    if get_plan_override(target.isoformat()):
        return None
    stype, label, dur = sess
    base.update({"planned_type": stype, "planned_label": label, "planned_dur": dur})

    if status == "red":
        base.update({
            "session_type": "recovery" if hr_day else "bike",
            "label": "Recovery Spin",
            "duration_min": 30,
            "headline": "Red day — swap to recovery",
        })
        return base
    if status == "amber":
        variant = (HR_EASIER_VARIANT if hr_day else EASIER_VARIANT).get(stype)
        if variant is None or (variant[0] == stype and variant[1] == label):
            return base  # already easy — show pill only, no swap
        base.update({
            "session_type": variant[0],
            "label": variant[1],
            "duration_min": dur,
            "headline": "Amber day — keep duration, drop intensity",
        })
        return base
    return None


def _signal_z(rows: list[dict], field: str) -> Optional[float]:
    """Z-score of today's value for `field` vs its own baseline (all prior rows)."""
    today_val = rows[-1].get(field) if rows else None
    if today_val is None:
        return None
    baseline = [r.get(field) for r in rows[:-1] if r.get(field) is not None]
    if len(baseline) < 7:
        return None
    stdev = statistics.pstdev(baseline)
    if stdev == 0:
        return None
    return (today_val - statistics.mean(baseline)) / stdev


def _illness_triggers(today: date) -> tuple[list[str], bool]:
    """Return trigger descriptions and whether illness-risk (2-of-3) is active."""
    rows31 = raw_history(31)
    if not rows31 or rows31[-1].get("date") != today.isoformat():
        return [], False

    hrv_z = _signal_z(rows31, "hrv_last_night")
    rhr_z = _signal_z(rows31, "resting_hr")
    if rhr_z is None:
        rhr_z = _signal_z(rows31, "rest_stress")
    sleep_z = _signal_z(rows31, "sleep_score")

    triggers = []
    today_row = rows31[-1]
    if hrv_z is not None and hrv_z < -1.5:
        triggers.append(f"HRV {today_row['hrv_last_night']:.0f} ms ({hrv_z:+.1f}σ)")
    if rhr_z is not None and rhr_z > 1.5:
        if today_row.get("resting_hr") is not None:
            triggers.append(f"resting HR {today_row['resting_hr']:.0f} bpm ({rhr_z:+.1f}σ)")
        else:
            triggers.append(f"resting stress elevated ({rhr_z:+.1f}σ)")
    if sleep_z is not None and sleep_z < -1.5:
        triggers.append(f"sleep score {today_row['sleep_score']:.0f} ({sleep_z:+.1f}σ)")

    return triggers, len(triggers) >= 2


def _hrv_declining_trend() -> tuple[bool, Optional[str]]:
    rows = raw_history(5)
    hrv_vals = [r["hrv_last_night"] for r in rows if r.get("hrv_last_night") is not None]
    if len(hrv_vals) >= 4:
        last4 = hrv_vals[-4:]
        if all(last4[i] < last4[i - 1] for i in range(1, 4)):
            return True, f"HRV has declined 4 consecutive mornings ({last4[0]:.0f} → {last4[-1]:.0f} ms)"
    return False, None


def _planned_session(target: date) -> tuple[Optional[tuple], bool]:
    sess = session_for_date_extended(target)
    hr_day = False
    if sess is None:
        sess = hr_session_for_date(target)
        hr_day = sess is not None
    return sess, hr_day


def _amber_variant(stype: str, label: str, dur: int, hr_day: bool) -> Optional[dict]:
    variant = (HR_EASIER_VARIANT if hr_day else EASIER_VARIANT).get(stype)
    if variant is None or (variant[0] == stype and variant[1] == label):
        return None
    return {
        "session_type": variant[0],
        "label": variant[1],
        "duration_min": dur,
    }


def recovery_gate(target: date, m: DailyMetrics, comp_z: Optional[float],
                  light: Optional[dict] = None) -> Optional[dict]:
    """Masters recovery gate — illness/rest signals before HRV modulation."""
    if get_plan_override(target.isoformat()):
        return None
    if light is None:
        light = hrv_traffic_light(m, comp_z)

    sess, hr_day = _planned_session(target)
    if sess is None:
        return None

    stype, label, dur = sess
    base: dict = {"light": light, "date": target.isoformat(), "gate": True}
    if stype != "rest":
        base.update({"planned_type": stype, "planned_label": label, "planned_dur": dur})

    triggers, illness = _illness_triggers(target)
    if illness:
        reason = "Possible illness onset: " + ", ".join(triggers) + ". Rest today, not an easy spin."
        if stype == "rest":
            return {**base, "headline": "Illness signals — stay off the bike", "reason": reason,
                    "gate_type": "illness"}
        return {
            **base,
            "session_type": "rest",
            "label": "Rest (illness signals)",
            "duration_min": 0,
            "headline": "Illness signals — rest today",
            "reason": reason,
            "gate_type": "illness",
        }

    if stype == "rest":
        return None

    if light["status"] == "green":
        rows31 = raw_history(31)
        if rows31 and rows31[-1].get("date") == target.isoformat():
            rhr_z = _signal_z(rows31, "resting_hr")
            if rhr_z is None:
                rhr_z = _signal_z(rows31, "rest_stress")
            if rhr_z is not None and rhr_z > 1.25:
                swap = _amber_variant(stype, label, dur, hr_day)
                if swap:
                    today_row = rows31[-1]
                    if today_row.get("resting_hr") is not None:
                        detail = f"Resting HR {today_row['resting_hr']:.0f} bpm is {rhr_z:.1f}σ above baseline"
                    else:
                        detail = f"Resting stress is {rhr_z:.1f}σ above baseline"
                    return {
                        **base,
                        **swap,
                        "headline": "Elevated resting HR — ease off intensity",
                        "reason": f"{detail} (early illness warning while HRV still normal)",
                        "gate_type": "rhr_early",
                    }

    declining, trend_reason = _hrv_declining_trend()
    if declining and stype in QUALITY_BIKE_TYPES:
        swap = _amber_variant(stype, label, dur, hr_day)
        if swap:
            return {
                **base,
                **swap,
                "headline": "HRV declining — protect the trend",
                "reason": trend_reason,
                "gate_type": "hrv_trend",
            }

    if light["status"] == "amber":
        rpe_rows = load_session_rpe(7)
        if any((r.get("rpe") or 0) >= 4 for r in rpe_rows):
            swap = _amber_variant(stype, label, dur, hr_day)
            if swap:
                return {
                    **base,
                    **swap,
                    "headline": "High perceived effort — ease off intensity",
                    "reason": "Recent session RPE ≥4 with amber HRV — drop intensity today",
                    "gate_type": "rpe_amber",
                }
            shortened = max(15, int(dur * 0.8))
            if shortened < dur:
                return {
                    **base,
                    "session_type": stype,
                    "label": label,
                    "duration_min": shortened,
                    "headline": "High perceived effort — shorten today",
                    "reason": "Recent session RPE ≥4 with amber HRV — reduce volume 20%",
                    "gate_type": "rpe_amber",
                }

    return None


def durability_gate(target: date, m: DailyMetrics, comp_z: Optional[float],
                    light: Optional[dict] = None) -> Optional[dict]:
    """Gate long rides in plan weeks 9+ when durability or BTB fatigue is poor."""
    if get_plan_override(target.isoformat()):
        return None
    days_into = (target - PLAN_START).days
    if days_into < 0:
        return None
    week_num = days_into // 7 + 1
    if week_num < 9:
        return None

    if light is None:
        light = hrv_traffic_light(m, comp_z)

    sess, hr_day = _planned_session(target)
    if sess is None or sess[0] not in ("long", "back_to_back"):
        return None

    stype, label, dur = sess
    base: dict = {
        "light": light,
        "date": target.isoformat(),
        "gate": True,
        "planned_type": stype,
        "planned_label": label,
        "planned_dur": dur,
    }

    dur_rows = load_durability(90)
    if dur_rows:
        last = dur_rows[-1]
        drift = last.get("drift_pct")
        if drift is not None and drift > 8:
            swap = _amber_variant(stype, label, dur, hr_day)
            if swap:
                return {
                    **base,
                    **swap,
                    "headline": "Durability drift — ease the long ride",
                    "reason": (
                        f"Last long ride drift was {drift:+.1f}% "
                        f"({last['first_third_hr']:.0f} → {last['final_third_hr']:.0f} bpm)"
                    ),
                    "gate_type": "durability",
                }
            shortened = max(30, int(dur * 0.75))
            if shortened < dur:
                return {
                    **base,
                    "session_type": stype,
                    "label": label,
                    "duration_min": shortened,
                    "headline": "Durability drift — shorten the long ride",
                    "reason": f"Last long ride cardiac drift was {drift:+.1f}% — cut duration 25%",
                    "gate_type": "durability",
                }

    for pair in load_btb_summary():
        rating = pair.get("fatigue_rating_2")
        if rating is not None and rating >= 4:
            swap = _amber_variant(stype, label, dur, hr_day)
            if swap:
                return {
                    **base,
                    **swap,
                    "headline": "Back-to-back fatigue — ease today's ride",
                    "reason": (
                        f"Last back-to-back day 2 fatigue was {rating}/5 "
                        f"({pair['date1']} → {pair['date2']})"
                    ),
                    "gate_type": "btb_fatigue",
                }
            break

    return None


def resolve_modulation(target: date, m: DailyMetrics, comp_z: Optional[float]) -> tuple[dict, Optional[dict]]:
    """Compute traffic light then pick the highest-priority prescription."""
    light = hrv_traffic_light(m, comp_z)
    for gate_fn in (recovery_gate, durability_gate):
        gate = gate_fn(target, m, comp_z, light=light)
        if gate and gate.get("label"):
            return light, gate
    return light, session_modulation(target, m, comp_z, light=light)

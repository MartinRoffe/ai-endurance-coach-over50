"""HRV-guided daily session modulation (green/amber/red traffic light).

HRV uses the natural log of last-night rMSSD. The signal is the 7-day
rolling mean of ln(rMSSD), compared with the 30-day mean. The smallest
worthwhile change is half a standard deviation of the daily ln values
(Plews). Inside that band the change is trivial.

The morning email explains this decision. It does not make a second
Train/Rest call.

Turns morning readiness data into a concrete, accept/declinable change to
today's planned session. Green = train as planned; amber = keep duration but
drop intensity; red = swap to short recovery. Applied via the existing
plan-override machinery (/apply-plan-change), so the calendar, email, and
Garmin workout sync all respect an accepted modulation automatically.

recovery_gate() runs first and handles masters-specific illness/rest signals
before HRV traffic-light modulation.
"""
from __future__ import annotations

import math
import statistics
from datetime import date, timedelta
from typing import Optional

from .fitness_plan import PLAN_START as FITNESS_PLAN_START
from .fitness_plan import plan_label
from .history import get_plan_override, load_btb_summary, load_durability, load_session_rpe, raw_history
from .load import RPE_HIGH
from .hr_plan import hr_session_for_date
from .medical import MEDICAL_PAUSE_END
from .metrics import DailyMetrics
from .plan import session_for_date_extended

# Late-ride drift older than this, or from before the medical break, is not
# "the last long ride".
DURABILITY_RECENT_DAYS = 21
_OUTDOOR_MARK = " · outdoor"

QUALITY_BIKE_TYPES = frozenset({"ftp", "tempo", "sweetspot", "vo2", "threshold"})

# Smallest worthwhile change = this fraction of the SD of daily ln(rMSSD).
HRV_SWC_FRACTION = 0.5
# A 7-day mean more than two SWCs under the baseline is a red day.
HRV_RED_SWC_MULTIPLE = 2.0

# Map a planned session type to its easier amber-day variant (duration kept).
EASIER_VARIANT: dict[str, tuple[str, str]] = {
    "ftp":      ("bike", "Zone 2 Steady"),
    "tempo":    ("bike", "Zone 2 Steady"),
    "long":     ("long", "Long Ride (Easy)"),
    "bike":     ("bike", "Recovery Spin"),
    "strength": ("strength", "Light KB"),
    "ruck":     ("ruck", "Easy Walk (no load)"),
    "rower":    ("rower", "Z2 — rower"),
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


def assess_hrv_ln(
    rows: list[dict],
    today_iso: Optional[str],
    today_ms: Optional[float],
) -> Optional[dict]:
    """7-day mean of ln(rMSSD) against the 30-day baseline and an SWC band.

    ``rows`` may include today. Today's value is ``today_ms`` (the morning
    metric), not a duplicate row. Returns None until there are 7 baseline
    nights and a positive reading for today.
    """
    baseline_ms = [
        r["hrv_last_night"] for r in rows
        if r.get("date") != today_iso and r.get("hrv_last_night") is not None
        and r["hrv_last_night"] > 0
    ]
    if today_ms is None or today_ms <= 0 or len(baseline_ms) < 7:
        return None
    baseline_ln = [math.log(v) for v in baseline_ms]
    mean = statistics.mean(baseline_ln)
    sd = statistics.pstdev(baseline_ln)
    swc = HRV_SWC_FRACTION * sd
    window = baseline_ln[-6:] + [math.log(today_ms)]
    roll = statistics.mean(window)
    hrv_z = (roll - mean) / sd if sd > 0 else None
    return {
        "ln_7d": roll,
        "ln_baseline": mean,
        "swc": swc,
        "sd": sd,
        "hrv_z": hrv_z,
        "ratio": (roll / mean) if mean else None,
        "below_band": roll < mean - swc,
        "well_below": roll < mean - HRV_RED_SWC_MULTIPLE * swc,
        "today_ms": today_ms,
    }


def _hrv_reason(state: dict) -> str:
    gap = state["ln_baseline"] - state["ln_7d"]
    return (
        f"7-day mean ln(rMSSD) is {gap:.3f} below the 30-day baseline "
        f"(SWC {state['swc']:.3f}; last night {state['today_ms']:.0f} ms)"
    )


def hrv_traffic_light(m: DailyMetrics, comp_z: Optional[float]) -> dict:
    """Classify today's readiness as green / amber / red / unknown.

    Primary signal: 7-day rolling mean of ln(rMSSD) versus the 30-day mean
    of daily ln(rMSSD). The smallest-worthwhile-change band is
    ± HRV_SWC_FRACTION standard deviations. Composite readiness is a backstop.
    """
    today_iso = m.date.isoformat() if m.date else None
    rows = raw_history(31)
    state = assess_hrv_ln(rows, today_iso, m.hrv_last_night)
    hrv_z = state["hrv_z"] if state else None
    ratio = state["ratio"] if state else None

    if state is None and comp_z is None:
        return {"status": "unknown", "hrv_z": None, "ratio": None,
                "reason": "Not enough HRV history yet for a ln(rMSSD) baseline."}

    def _pack(status: str, reasons: list[str]) -> dict:
        out = {"status": status, "hrv_z": hrv_z, "ratio": ratio, "reason": "; ".join(reasons)}
        if state:
            out.update({
                "ln_7d": state["ln_7d"],
                "ln_baseline": state["ln_baseline"],
                "swc": state["swc"],
            })
        return out

    red_reasons = []
    if state and state["well_below"]:
        red_reasons.append(_hrv_reason(state))
    if comp_z is not None and comp_z < -1.2:
        red_reasons.append(f"composite readiness is {comp_z:+.1f}σ")
    if red_reasons:
        return _pack("red", red_reasons)

    amber_reasons = []
    if state and state["below_band"]:
        amber_reasons.append(_hrv_reason(state))
    if comp_z is not None and comp_z < -0.5:
        amber_reasons.append(f"composite readiness is {comp_z:+.1f}σ")
    if amber_reasons:
        return _pack("amber", amber_reasons)

    if state is None:
        return {"status": "unknown", "hrv_z": None, "ratio": None,
                "reason": "Not enough HRV history yet for a ln(rMSSD) baseline."}
    return _pack("green", ["7-day ln(rMSSD) is inside the smallest-worthwhile-change band."])


def _same_session_label(left: Optional[str], right: Optional[str]) -> bool:
    """True when two labels differ only by the outdoor suffix."""
    return plan_label(left or "") == plan_label(right or "")


def _keep_outdoor(new_label: str, original: str) -> str:
    """An easier swap on an outdoor day stays outdoor."""
    if _OUTDOOR_MARK in (original or "") and _OUTDOOR_MARK not in new_label:
        return f"{new_label}{_OUTDOOR_MARK}"
    return new_label


def recent_durability(rows: list[dict], today: date) -> list[dict]:
    """Drop drift from before the break or older than three weeks."""
    cutoff = today - timedelta(days=DURABILITY_RECENT_DAYS)
    kept: list[dict] = []
    for row in rows:
        raw = row.get("date")
        if not raw:
            continue
        if isinstance(raw, date):
            ride_day = raw
        else:
            ride_day = date.fromisoformat(str(raw)[:10])
        if ride_day <= MEDICAL_PAUSE_END or ride_day < cutoff:
            continue
        kept.append(row)
    return kept


def modulation_decision_text(light: Optional[dict], modulation: Optional[dict]) -> str:
    """One sentence the email must explain, not replace."""
    light = light or {}
    if modulation and modulation.get("label"):
        dur = modulation.get("duration_min")
        dur_bit = f" ({dur} min)" if dur else ""
        planned = modulation.get("planned_label")
        swap = ""
        if planned and not _same_session_label(planned, modulation.get("label")):
            swap = f" instead of {planned}"
        reason = (modulation.get("reason") or light.get("reason") or "").strip()
        line = f"Rule-based decision: {modulation['label']}{dur_bit}{swap}."
        return f"{line} {reason}".strip()
    status = light.get("status") or "unknown"
    if status == "green":
        return (
            "Rule-based decision: train the planned session. "
            "The 7-day ln(rMSSD) mean is inside the normal band."
        )
    if status == "unknown":
        return (
            "Rule-based decision: not enough HRV history to change the plan. "
            "Train the planned session unless a red flag is logged."
        )
    reason = (light.get("reason") or "").strip()
    return f"Rule-based decision: {status}. {reason}".strip()


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
        from .fitness_plan import in_plan
        from .settings import has_turbo
        if not hr_day and in_plan(target) and not has_turbo():
            if target.weekday() >= 5:
                red_type, red_label = "bike", "Z2 Easy · outdoor"
            else:
                red_type, red_label = "rower", "Z2 — rower"
        else:
            red_type = "recovery" if hr_day else "bike"
            red_label = "Recovery Spin"
        base.update({
            "session_type": red_type,
            "label": red_label,
            "duration_min": 30,
            "headline": "Red day — swap to recovery",
        })
        return base
    if status == "amber":
        variant = (HR_EASIER_VARIANT if hr_day else EASIER_VARIANT).get(stype)
        if variant is None or (variant[0] == stype and _same_session_label(variant[1], label)):
            return base  # already easy — show pill only, no swap
        base.update({
            "session_type": variant[0],
            "label": _keep_outdoor(variant[1], label),
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

    hrv_state = assess_hrv_ln(rows31, today.isoformat(), rows31[-1].get("hrv_last_night"))
    rhr_z = _signal_z(rows31, "resting_hr")
    if rhr_z is None:
        rhr_z = _signal_z(rows31, "rest_stress")
    sleep_z = _signal_z(rows31, "sleep_score")

    triggers = []
    today_row = rows31[-1]
    if hrv_state and hrv_state["below_band"]:
        triggers.append(_hrv_reason(hrv_state))
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
    if variant is None or (variant[0] == stype and _same_session_label(variant[1], label)):
        return None
    return {
        "session_type": variant[0],
        "label": _keep_outdoor(variant[1], label),
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
        if any((r.get("rpe") or 0) >= RPE_HIGH for r in rpe_rows):
            swap = _amber_variant(stype, label, dur, hr_day)
            if swap:
                return {
                    **base,
                    **swap,
                    "headline": "High perceived effort — ease off intensity",
                    "reason": f"Recent session RPE ≥{RPE_HIGH}/10 with amber HRV — drop intensity today",
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
                    "reason": f"Recent session RPE ≥{RPE_HIGH}/10 with amber HRV — reduce volume 20%",
                    "gate_type": "rpe_amber",
                }

    return None


def durability_gate(target: date, m: DailyMetrics, comp_z: Optional[float],
                    light: Optional[dict] = None) -> Optional[dict]:
    """Gate long rides in plan weeks 9+ when durability or BTB fatigue is poor."""
    if get_plan_override(target.isoformat()):
        return None
    # Week 9 of the live fitness year, not week 9 of the retired charity plan.
    days_into = (target - FITNESS_PLAN_START).days
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

    dur_rows = recent_durability(load_durability(90), target)
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

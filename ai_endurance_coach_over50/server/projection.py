"""CTL projection, taper scenarios, and plan lookup tables."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from ..hr_plan import HR_PLAN_START, HR_TRAINING_WEEKS
from ..plan import CAMP_GRID_WORKOUTS, EVENT_PREP_DAYS, TENERIFE_DAYS, session_for_date


def _ols(ys: list[float]) -> Optional[tuple[float, float]]:
    """Ordinary least squares on (index, value). Returns (slope, intercept) or None."""
    n = len(ys)
    if n < 2:
        return None
    xs = list(range(n))
    sx, sy = sum(xs), sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sx2 = sum(x * x for x in xs)
    denom = n * sx2 - sx * sx
    if not denom:
        return None
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    return slope, intercept


_PLAN_EVENT_DATE = date(2026, 9, 13)

# CTL delta per training minute by session type.
# Calibrated from week-1 observed data: Easy Spin 60min→+15, Zone2 60min→+26,
# KB+MaxiClimber 45min→+33, Ruck+KB 105min→+33. Rest days average -3.
_CTL_PER_MIN: dict[str, float] = {
    "bike":     0.32,   # easy spin / Z2
    "long":     0.40,   # Z2 long ride
    "tempo":    0.58,   # tempo effort
    "ftp":      0.78,   # threshold
    "strength": 0.70,   # KB / strength (high EPOC)
    "ruck":     0.30,   # hiking / ruck
}
_CTL_REST_DECLINE = -3.5


_TENERIFE_BY_DATE: dict = {}   # populated lazily below
_EVENT_PREP_BY_DATE: dict = {}

def _build_lookup_dicts() -> None:
    global _TENERIFE_BY_DATE, _EVENT_PREP_BY_DATE
    # Intensity → session type mapping for Tenerife days
    _intensity_type = {"easy": "bike", "medium": "bike", "hard": "long"}
    for day in TENERIFE_DAYS:
        intensity = day.get("intensity", "rest")
        stype = _intensity_type.get(intensity)
        if stype:
            km = day.get("km", 0) or 0
            elev = day.get("elev_m", 0) or 0
            # Duration estimate: flat km at 25 km/h + climbing at 700 m/h
            dur_min = int((km / 25 + elev / 700) * 60)
            _TENERIFE_BY_DATE[day["date"]] = (stype, day["label"], max(dur_min, 30))
    for day in EVENT_PREP_DAYS:
        _EVENT_PREP_BY_DATE[day["date"]] = (day["type"], day["label"], day["dur_min"])
    for day in CAMP_GRID_WORKOUTS.values():
        pass  # handled via session_for_date for the pre/post camp days

_build_lookup_dicts()


def _session_for_projection(d) -> tuple[str, str, int] | None:
    """Return (type, label, dur_min) for any plan day — 12-week plan, camp, or event prep."""
    sess = session_for_date(d)
    if sess:
        return sess
    if d in _TENERIFE_BY_DATE:
        return _TENERIFE_BY_DATE[d]
    if d in _EVENT_PREP_BY_DATE:
        return _EVENT_PREP_BY_DATE[d]
    # CAMP_GRID_WORKOUTS (pre/post camp activation rides)
    cg = CAMP_GRID_WORKOUTS.get(d)
    if cg:
        return (cg["type"], cg["label"], cg["dur_min"])
    return None


def _ctl_projection(current_ctl: float, current_atl: float,
                    modifier=None) -> tuple[list[dict], float]:
    """Project CTL/ATL/TSB from today to event day using all plan sessions including Tenerife camp.

    Uses additive deltas calibrated against observed week-1 data rather than
    the standard Coggan EMA, because Garmin's CTL units don't follow the
    standard TSS-based scale. A soft ceiling (diminishing returns above CTL 300)
    prevents runaway growth.

    `modifier` (optional) is applied to each (date, session_tuple) before the
    rate maths: return a replacement tuple, or None to treat the day as rest.
    Used by the taper scenario simulator.
    """
    import math as _math
    today = date.today()
    days_ahead = (_PLAN_EVENT_DATE - today).days
    if days_ahead <= 0:
        return [], round(current_ctl, 1)

    ctl = current_ctl
    atl = current_atl
    result = []
    for i in range(1, days_ahead + 1):
        d = today + timedelta(days=i)
        sess = _session_for_projection(d)
        if modifier is not None and sess is not None:
            sess = modifier(d, sess)
        if sess and sess[0] != "rest":
            stype, _, dur_min = sess
            rate = _CTL_PER_MIN.get(stype, 0.35)
            ceiling = (300 / max(ctl, 300)) ** 2
            delta = rate * (dur_min or 0) * ceiling
            atl_delta = rate * (dur_min or 0)
            atl = max(0.0, atl * _math.exp(-1 / 7) + atl_delta)
        else:
            delta = _CTL_REST_DECLINE
            atl = max(0.0, atl * _math.exp(-1 / 7))
        ctl = max(0.0, ctl + delta)
        tsb = round(ctl - atl, 1)
        result.append({
            "label": d.strftime("%-d %b"),
            "ctl":   round(ctl, 1),
            "atl":   round(atl, 1),
            "tsb":   tsb,
        })
    return result, round(result[-1]["ctl"], 1) if result else round(current_ctl, 1)


def _taper_scenarios(current_ctl: float, current_atl: float) -> list[dict]:
    """Three preset what-if projections over the final 14 days before the event.

    Turns the TSB projection from a chart into a decision tool: target landing
    zone on event morning is roughly TSB −5 to +15.
    """
    taper_start = _PLAN_EVENT_DATE - timedelta(days=14)
    final_week = _PLAN_EVENT_DATE - timedelta(days=7)

    scenarios = []

    # 1. As planned
    series, ctl_event = _ctl_projection(current_ctl, current_atl)
    if not series:
        return []
    scenarios.append({"name": "As planned", "series": series,
                      "tsb_event": series[-1]["tsb"], "ctl_event": ctl_event})

    # 2. Drop the first quality session (tempo/ftp) inside the final 14 days
    dropped = {"done": False}

    def _drop_quality(d, sess):
        if (not dropped["done"] and d >= taper_start
                and sess and sess[0] in ("tempo", "ftp")):
            dropped["done"] = True
            return None
        return sess

    series2, ctl2 = _ctl_projection(current_ctl, current_atl, modifier=_drop_quality)
    scenarios.append({"name": "Drop one quality session", "series": series2,
                      "tsb_event": series2[-1]["tsb"] if series2 else None,
                      "ctl_event": ctl2})

    # 3. Halve final-week volume
    def _halve_final_week(d, sess):
        if d >= final_week and sess and sess[0] != "rest":
            stype, label, dur = sess
            return (stype, label, max(15, (dur or 0) // 2))
        return sess

    series3, ctl3 = _ctl_projection(current_ctl, current_atl, modifier=_halve_final_week)
    scenarios.append({"name": "Halve final-week volume", "series": series3,
                      "tsb_event": series3[-1]["tsb"] if series3 else None,
                      "ctl_event": ctl3})

    return scenarios


def _block_zone_totals(weeks: list[dict]) -> dict:
    """Aggregate zone distribution across all weeks to block-level percentages."""
    totals = [0.0] * 5
    for w in weeks:
        for i in range(1, 6):
            totals[i - 1] += w.get(f"z{i}_sec", 0.0)
    total = sum(totals)
    if total == 0:
        return {}
    return {
        "z1_pct": round(totals[0] / total * 100, 1),
        "z2_pct": round(totals[1] / total * 100, 1),
        "z3_pct": round(totals[2] / total * 100, 1),
        "z4_pct": round(totals[3] / total * 100, 1),
        "z5_pct": round(totals[4] / total * 100, 1),
    }


_BIKE_TYPES = {"bike", "tempo", "ftp", "long"}

# CTL rates for Haute Route plan session types.
# Reuses calibrated values from _CTL_PER_MIN where keys overlap.
_HR_CTL_PER_MIN: dict[str, float] = {
    "endurance":    0.32,   # Z2 steady (same as "bike")
    "recovery":     0.25,   # recovery spin / easy core
    "sweetspot":    0.45,   # sweetspot intervals
    "tempo":        0.58,   # tempo / under-overs (same as "tempo")
    "vo2":          0.65,   # VO2max intervals
    "long":         0.40,   # long ride (same as "long")
    "back_to_back": 0.40,   # multi-hour back-to-back days
    "ftp":          0.78,   # threshold test (same as "ftp")
    "gym":          0.55,   # gym strength session
}


def _hr_ctl_projection(starting_ctl: float) -> list[dict]:
    """Project CTL across all 46 HR plan weeks, returning one point per week (Sunday)."""
    ctl = starting_ctl
    result = []
    for wk_idx, sessions in enumerate(HR_TRAINING_WEEKS):
        week_num = wk_idx + 1
        for stype, _, dur_min in sessions:
            if stype != "rest":
                rate = _HR_CTL_PER_MIN.get(stype, 0.35)
                ceiling = (300 / max(ctl, 300)) ** 2
                ctl = max(0.0, ctl + rate * dur_min * ceiling)
            else:
                ctl = max(0.0, ctl + _CTL_REST_DECLINE)
        week_end = HR_PLAN_START + timedelta(weeks=wk_idx, days=6)
        result.append({
            "label":    week_end.strftime("%-d %b"),
            "ctl":      round(ctl, 1),
            "week":     week_num,
        })
    return result

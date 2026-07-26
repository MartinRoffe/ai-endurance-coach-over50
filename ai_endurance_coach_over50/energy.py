"""Energy expenditure helpers — BMR and TDEE.

The dashboard previously surfaced Garmin's ``calorie_goal_adjusted`` as "TDEE".
That field is a *recommended intake goal* (a target to eat, adjusted for the
day's activity), **not** total daily energy expenditure. This module computes a
real TDEE from the body stats the app already tracks:

    TDEE = BMR + active_calories

BMR uses the Katch-McArdle equation, which is driven by fat-free (lean) mass —
the true determinant of resting metabolism — derived from the smart-scale
weight + body-fat % readings:

    fat_free_mass_kg = weight_kg * (1 - fat_pct / 100)
    BMR              = 370 + 21.6 * fat_free_mass_kg

``active_calories`` is the day's measured Garmin non-resting burn (NEAT +
exercise), so TDEE varies day to day with real training load — far more
accurate for an athlete than a fixed activity multiplier. This mirrors Garmin's
own total-expenditure model (total = BMR + active), but recomputes BMR from
current body composition so it tracks the athlete's changing lean mass.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

# Katch-McArdle constants
_KM_CONST = 370.0
_KM_PER_KG_LBM = 21.6

# Energy content of 1 kg body mass change (kcal/kg)
KCAL_PER_KG = 7700.0

TDEE_METHOD = (
    "Katch-McArdle BMR (lean mass) + measured Garmin active calories, "
    "calibrated from 28-day weight trend"
)


def fat_free_mass_kg(
    weight_kg: Optional[float], fat_pct: Optional[float]
) -> Optional[float]:
    """Fat-free (lean) mass = weight × (1 − fat%/100).

    Returns None if inputs are missing or implausible (fat% must be 1–69).
    """
    if weight_kg is None or fat_pct is None:
        return None
    try:
        weight_kg = float(weight_kg)
        fat_pct = float(fat_pct)
    except (TypeError, ValueError):
        return None
    if weight_kg <= 0 or fat_pct <= 0 or fat_pct >= 70:
        return None
    return weight_kg * (1.0 - fat_pct / 100.0)


def bmr_katch_mcardle(
    weight_kg: Optional[float], fat_pct: Optional[float]
) -> Optional[float]:
    """Resting metabolic rate (kcal/day) via Katch-McArdle, or None."""
    lbm = fat_free_mass_kg(weight_kg, fat_pct)
    if lbm is None:
        return None
    return _KM_CONST + _KM_PER_KG_LBM * lbm


def tdee(
    active_calories: Optional[float],
    weight_kg: Optional[float] = None,
    fat_pct: Optional[float] = None,
    bmr: Optional[float] = None,
) -> Optional[float]:
    """Total daily energy expenditure = BMR + active calories.

    Pass a precomputed ``bmr`` to avoid recomputing it per day; otherwise it is
    derived from ``weight_kg`` + ``fat_pct``. Returns None when BMR cannot be
    established (no body-composition data).
    """
    if bmr is None:
        bmr = bmr_katch_mcardle(weight_kg, fat_pct)
    if bmr is None:
        return None
    try:
        active = float(active_calories) if active_calories is not None else 0.0
    except (TypeError, ValueError):
        active = 0.0
    if active < 0:
        active = 0.0
    return bmr + active


def weight_trend_kg_per_day(readings: list[tuple[str, float]]) -> Optional[float]:
    """Least-squares slope of weight (kg/day) over dated readings.

    Returns None when fewer than 5 readings or the span is under 14 days.
    """
    if len(readings) < 5:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for d_iso, w in readings:
        try:
            xs.append(float(date.fromisoformat(d_iso).toordinal()))
            ys.append(float(w))
        except (TypeError, ValueError):
            continue
    if len(xs) < 5:
        return None
    span_days = int(max(xs) - min(xs))
    if span_days < 14:
        return None
    n = len(xs)
    sx, sy = sum(xs), sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sx2 = sum(x * x for x in xs)
    denom = n * sx2 - sx * sx
    if not denom:
        return None
    return (n * sxy - sx * sy) / denom


def empirical_tdee(avg_intake_kcal: float, slope_kg_per_day: float) -> float:
    """TDEE implied by logged intake and weight trend (kcal/day)."""
    return avg_intake_kcal - slope_kg_per_day * KCAL_PER_KG


def tdee_correction(model_avg: float, empirical: float) -> float:
    """Level-shift offset (kcal/day), clamped to ±25% of model TDEE."""
    raw = empirical - model_avg
    limit = 0.25 * model_avg
    return max(-limit, min(limit, raw))


def apply_tdee_correction(
    model_tdee: Optional[float], correction: Optional[float]
) -> Optional[float]:
    """Apply a calibration offset to a model TDEE value."""
    if model_tdee is None:
        return None
    if correction is None:
        return model_tdee
    return model_tdee + correction


# ── Mechanical work (cycling power) ─────────────────────────────────────────
# At ~24% gross efficiency, mechanical kJ ≈ dietary kcal for replacement purposes.


def ride_kj(avg_power_w: float, secs: float) -> float:
    """Mechanical work in kilojoules (power × time)."""
    if not avg_power_w or not secs or avg_power_w <= 0 or secs <= 0:
        return 0.0
    return round(avg_power_w * secs / 1000.0, 1)


def ride_kcal_from_kj(kj: float) -> int:
    """Approximate dietary kcal to replace mechanical work (~1:1 at ~24% gross efficiency)."""
    return int(round(kj))


def planned_session_kj(ftp_w: int, pct_lo: float, pct_hi: float, dur_min: int) -> float:
    """Estimated mechanical work for a planned session at mid-range %FTP."""
    if not ftp_w or dur_min <= 0:
        return 0.0
    mid_pct = (pct_lo + pct_hi) / 2.0 / 100.0
    avg_w = ftp_w * mid_pct
    return ride_kj(avg_w, dur_min * 60)


# ── Intake targets (stable TDEE − session-type deficit) ─────────────────────
# Targets are anchored to a stable multi-day TDEE (see history.stable_tdee_kcal),
# not today's partial burn — early-day active-calorie totals understate true TDEE.

MIN_INTAKE_KCAL = 1600

# kcal below stable TDEE by nutrition day type (long ≈ maintenance for fuelling).
INTAKE_DEFICIT_BY_TIER: dict[str, int] = {
    "rest": 350,
    "training": 250,
    "ruck": 150,
    "long": 50,
    "recovery": 350,
}

# Extra intake per hour of long ride beyond a 2 h baseline (kcal/h).
LONG_RIDE_EXTRA_KCAL_PER_HOUR = 175

# Deficits are suspended (maintenance) in these date windows: the final big
# training weeks into the charity ride carry too much load for a 50+ athlete
# to absorb in a deficit. Block A cut resumes in the position bridge (15 Sep).
MAINTENANCE_WINDOWS: list[tuple[date, date]] = [
    (date(2026, 7, 27), date(2026, 9, 14)),
]


def in_maintenance_window(d: Optional[date]) -> bool:
    """True when deficits are suspended for this date (eat at maintenance)."""
    if d is None:
        return False
    return any(start <= d <= end for start, end in MAINTENANCE_WINDOWS)


def intake_target_kcal(
    tdee: Optional[float],
    tier_key: str,
    *,
    long_ride_extra_min: int = 0,
    ref_date: Optional[date] = None,
) -> Optional[int]:
    """Prescribed intake (kcal) from calibrated TDEE and day type.

    Returns None when ``tdee`` is unknown (caller should fall back to static tiers).
    ``ref_date`` enables the maintenance windows; None keeps the plain deficit.
    """
    if tdee is None:
        return None
    try:
        burn = float(tdee)
    except (TypeError, ValueError):
        return None
    if burn <= 0:
        return None
    deficit = 0 if in_maintenance_window(ref_date) else INTAKE_DEFICIT_BY_TIER.get(tier_key, 300)
    target = round(burn) - deficit
    if tier_key == "long" and long_ride_extra_min > 0:
        target += round(LONG_RIDE_EXTRA_KCAL_PER_HOUR * (long_ride_extra_min / 60.0))
    return max(MIN_INTAKE_KCAL, target)

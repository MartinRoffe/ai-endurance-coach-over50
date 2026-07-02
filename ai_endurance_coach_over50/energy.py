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

from typing import Optional

# Katch-McArdle constants
_KM_CONST = 370.0
_KM_PER_KG_LBM = 21.6

TDEE_METHOD = "Katch-McArdle BMR (lean mass) + measured Garmin active calories"


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

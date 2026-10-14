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

# Same three day types outside a named cut phase. Maintenance still zeros them.
INTAKE_DEFICIT_BY_TIER: dict[str, int] = {
    "easy": 600,
    "hard": 250,
    "long": 0,
}

# Extra intake per hour of long ride beyond a 2 h baseline (kcal/h).
LONG_RIDE_EXTRA_KCAL_PER_HOUR = 175

# No cut before 3 Jan 2027 (procedure, return, Christmas camp).
# The July–September 2026 charity window has expired and is not listed.
MAINTENANCE_WINDOWS: list[tuple[date, date]] = [
    (date(2026, 10, 9), date(2027, 1, 3)),
]

# About 0.5 kg/week from 4 Jan to 31 Mar 2027, landing near 84–85 kg
# from a start around 89–92 kg. CUT_TARGET_KG is the midpoint used for
# pace maths. Easy days carry most of the deficit (600 kcal). A week of
# five easy days, one hard day and one long day averages about 460 kcal/day.
CUT_TARGET_KG = 84.5
CUT_TARGET_LOW_KG = 84
CUT_TARGET_HIGH_KG = 85
CUT_RATE_KG_PER_WEEK = 0.5
CUT_MEAN_DEFICIT_KCAL = 500
CUT_TARGET_DEADLINE = date(2027, 3, 31)
CUT_PHASES: list[tuple[date, date, str]] = [
    (date(2027, 1, 4), date(2027, 3, 31), "ease"),
]

# Three day types once a deficit applies. Easy covers rest, recovery and
# ordinary training. Hard keeps carbohydrate up. Long is maintenance
# (the ride-fuel top-up is added separately).
DAY_DEFICIT_KCAL: dict[str, int] = {
    "easy": 600,
    "hard": 250,
    "long": 0,
}

# Ease is the only live cut phase. The unused front-loaded "hard" map is gone.
CUT_DEFICIT_BY_PHASE: dict[str, dict[str, int]] = {
    "ease": dict(DAY_DEFICIT_KCAL),
}

# Shown only as a 7-day mean, and only when food is logged often enough.
EA_WINDOW_DAYS = 7
EA_MIN_LOGGED_DAYS = 5

# Energy availability = (intake kcal − exercise kcal) / kg fat-free mass.
# Below 30 kcal/kg FFM is the usual low-EA line (Loucks).
EA_WARN_KCAL_PER_KG_FFM = 30.0

# Daily fluid: 2.5–3 L plus about 500 ml per training hour.
FLUID_BASE_LOW_L = 2.5
FLUID_BASE_HIGH_L = 3.0
FLUID_PER_TRAINING_HOUR_L = 0.5

# Muscle-mass alert: late readings at least this far under the early ones,
# across a span of two weeks and at least three scale readings.
MUSCLE_DROP_KG = 0.4
MUSCLE_DROP_MIN_DAYS = 14
MUSCLE_DROP_MIN_READINGS = 3


def in_maintenance_window(d: Optional[date]) -> bool:
    """True when deficits are suspended for this date (eat at maintenance)."""
    if d is None:
        return False
    return any(start <= d <= end for start, end in MAINTENANCE_WINDOWS)


def active_cut_phase(d: Optional[date]) -> Optional[str]:
    """Return ``hard`` / ``ease`` when ``d`` falls in a cut phase, else None."""
    if d is None:
        return None
    for start, end, name in CUT_PHASES:
        if start <= d <= end:
            return name
    return None


def cut_target_band() -> str:
    """Athlete-facing weight band for the Jan–Mar cut."""
    return f"{CUT_TARGET_LOW_KG:g}–{CUT_TARGET_HIGH_KG:g} kg"


def energy_availability(
    intake_kcal: Optional[float],
    exercise_kcal: Optional[float],
    ffm_kg: Optional[float],
) -> Optional[float]:
    """kcal per kg fat-free mass. None when any input is missing."""
    if intake_kcal is None or exercise_kcal is None or ffm_kg is None:
        return None
    try:
        intake = float(intake_kcal)
        exercise = float(exercise_kcal)
        ffm = float(ffm_kg)
    except (TypeError, ValueError):
        return None
    if ffm <= 0:
        return None
    return (intake - exercise) / ffm


def day_kind(tier_key: Optional[str]) -> str:
    """Collapse legacy tier names onto easy / hard / long."""
    key = (tier_key or "").lower()
    if key == "hard":
        return "hard"
    if key == "long":
        return "long"
    return "easy"


def weekly_energy_availability(
    days: list[dict],
    ffm_kg: Optional[float],
) -> Optional[dict]:
    """Seven-day energy availability from intake and training kilocalories.

    ``training_kcal`` is the sum of logged session calories that day. Garmin
    ``active_calories`` (NEAT plus exercise) is not an input. Returns None
    unless food is logged on at least ``EA_MIN_LOGGED_DAYS`` of the rows.
    """
    if ffm_kg is None:
        return None
    try:
        ffm = float(ffm_kg)
    except (TypeError, ValueError):
        return None
    if ffm <= 0:
        return None
    logged: list[tuple[float, float]] = []
    for row in days:
        intake = row.get("intake_kcal")
        if intake is None:
            continue
        try:
            intake_f = float(intake)
            train_f = float(row.get("training_kcal") or 0)
        except (TypeError, ValueError):
            continue
        logged.append((intake_f, max(0.0, train_f)))
    if len(logged) < EA_MIN_LOGGED_DAYS:
        return None
    n = len(logged)
    ea = (sum(i for i, _t in logged) - sum(t for _i, t in logged)) / (n * ffm)
    low = ea < EA_WARN_KCAL_PER_KG_FFM
    rounded = f"{ea:.0f}"
    if low:
        words = (
            f"Over the last 7 days, energy availability is about {rounded} kcal "
            "per kg of lean mass. That is a little low. A slightly bigger plate "
            "on the next easy day is enough."
        )
    else:
        words = (
            f"Over the last 7 days, energy availability is about {rounded} kcal "
            "per kg of lean mass, which looks comfortable."
        )
    return {
        "ea": round(ea, 1),
        "logged_days": n,
        "window_days": EA_WINDOW_DAYS,
        "low": low,
        "words": words,
    }


def fluid_target_litres(training_min: float) -> dict:
    """2.5–3 L plus FLUID_PER_TRAINING_HOUR_L per training hour."""
    hours = max(0.0, float(training_min or 0)) / 60.0
    extra = FLUID_PER_TRAINING_HOUR_L * hours
    return {
        "low_l": round(FLUID_BASE_LOW_L + extra, 2),
        "high_l": round(FLUID_BASE_HIGH_L + extra, 2),
        "extra_l": round(extra, 2),
        "training_hours": round(hours, 2),
    }


def fluid_shortfall_l(logged_l: Optional[float], training_min: float) -> Optional[float]:
    """Litres under the low end of the target, or None when intake is unknown or enough."""
    if logged_l is None:
        return None
    low = fluid_target_litres(training_min)["low_l"]
    gap = low - float(logged_l)
    if gap <= 0.05:
        return None
    return round(gap, 2)


def deficit_for_tier(tier_key: str, ref_date: Optional[date] = None) -> int:
    """Planned kcal below stable TDEE for this day type and date.

    Precedence for the deficit *value* (camp still short-circuits earlier in
    ``resolve_calorie_target``): maintenance → 0; cut phase map; else default.
    """
    if in_maintenance_window(ref_date):
        return 0
    kind = day_kind(tier_key)
    phase = active_cut_phase(ref_date)
    table = CUT_DEFICIT_BY_PHASE.get(phase) if phase else INTAKE_DEFICIT_BY_TIER
    if not table:
        table = INTAKE_DEFICIT_BY_TIER
    return table.get(kind, DAY_DEFICIT_KCAL[kind])


def intake_target_kcal(
    tdee: Optional[float],
    tier_key: str,
    *,
    long_ride_extra_min: int = 0,
    ref_date: Optional[date] = None,
) -> Optional[int]:
    """Prescribed intake (kcal) from calibrated TDEE and day type.

    Returns None when ``tdee`` is unknown (caller should fall back to static tiers).
    ``ref_date`` enables maintenance windows and cut-phase deficit maps.
    """
    if tdee is None:
        return None
    try:
        burn = float(tdee)
    except (TypeError, ValueError):
        return None
    if burn <= 0:
        return None
    deficit = deficit_for_tier(tier_key, ref_date)
    target = round(burn) - deficit
    if tier_key == "long" and long_ride_extra_min > 0:
        target += round(LONG_RIDE_EXTRA_KCAL_PER_HOUR * (long_ride_extra_min / 60.0))
    return max(MIN_INTAKE_KCAL, target)

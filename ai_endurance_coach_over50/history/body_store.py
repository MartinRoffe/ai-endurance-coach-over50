"""Body composition, blood pressure, PMC/VO2 history, W/kg, BMR/TDEE."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .db import (
    _conn,
    _ensure_activities_schema,
    _ensure_blood_pressure_schema,
    _ensure_body_metrics_schema,
    _ensure_ftp_schema,
    _ensure_schema,
)
from .metrics_store import raw_history


def save_body_metrics(readings: list[dict]) -> None:
    with _conn() as con:
        _ensure_body_metrics_schema(con)
        for r in readings:
            con.execute("""
                INSERT OR REPLACE INTO body_metrics
                    (date, weight_kg, fat_pct, muscle_mass_kg, bone_mass_kg,
                     hydration_pct, visceral_fat, bmi, metabolic_age)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                r["date"], r.get("weight_kg"), r.get("fat_pct"),
                r.get("muscle_mass_kg"), r.get("bone_mass_kg"),
                r.get("hydration_pct"), r.get("visceral_fat"),
                r.get("bmi"), r.get("metabolic_age"),
            ))


def load_body_metrics(days: int = 90) -> list[dict]:
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    with _conn() as con:
        _ensure_body_metrics_schema(con)
        rows = con.execute(
            "SELECT * FROM body_metrics WHERE date >= ? ORDER BY date",
            (start,),
        ).fetchall()
    return [dict(r) for r in rows]


def save_blood_pressure(readings: list[dict]) -> None:
    with _conn() as con:
        _ensure_blood_pressure_schema(con)
        for r in readings:
            con.execute("""
                INSERT OR REPLACE INTO blood_pressure
                    (date, timestamp_local, systolic, diastolic, pulse)
                VALUES (?,?,?,?,?)
            """, (
                r["date"], r.get("timestamp_local"),
                r.get("systolic"), r.get("diastolic"), r.get("pulse"),
            ))


def load_blood_pressure(days: int = 90) -> list[dict]:
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    with _conn() as con:
        _ensure_blood_pressure_schema(con)
        rows = con.execute(
            "SELECT * FROM blood_pressure WHERE date >= ? ORDER BY timestamp_local",
            (start,),
        ).fetchall()
    return [dict(r) for r in rows]


def pmc_history(days: int = 90) -> list[dict]:
    """Return daily CTL/ATL/TSB for the last `days` days (oldest first).

    Uses Garmin's pre-computed acute (≈7d ATL) and chronic (≈28d CTL) training
    load values. TSB = CTL − ATL. All values are in Garmin training-load units
    (not Coggan TSS) so absolute thresholds from TrainingPeaks do not apply.
    """
    end = date.today()
    start = end - timedelta(days=days - 1)
    with _conn() as con:
        _ensure_schema(con)
        rows = con.execute(
            """SELECT date, training_load_acute, training_load_chronic
               FROM daily_metrics
               WHERE date >= ? AND date <= ?
               ORDER BY date""",
            (start.isoformat(), end.isoformat()),
        ).fetchall()

    by_date = {row["date"]: row for row in rows}
    result = []
    for i in range(days):
        d = start + timedelta(days=i)
        row = by_date.get(d.isoformat())
        atl = row["training_load_acute"] if row else None
        ctl = row["training_load_chronic"] if row else None
        tsb = round(ctl - atl, 1) if (ctl is not None and atl is not None) else None
        result.append({
            "date": d.isoformat(),
            "label": d.strftime("%-d %b"),
            "atl": round(atl, 1) if atl is not None else None,
            "ctl": round(ctl, 1) if ctl is not None else None,
            "tsb": tsb,
        })
    return result


def vo2_history(days: int = 90) -> list[dict]:
    """Return daily VO2 max readings for the last `days` days (oldest first)."""
    end = date.today()
    start = end - timedelta(days=days - 1)
    with _conn() as con:
        _ensure_schema(con)
        rows = con.execute(
            "SELECT date, vo2_max FROM daily_metrics WHERE date >= ? AND date <= ? ORDER BY date",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    by_date = {row["date"]: row["vo2_max"] for row in rows}
    result = []
    for i in range(days):
        d = start + timedelta(days=i)
        v = by_date.get(d.isoformat())
        result.append({
            "date": d.isoformat(),
            "label": d.strftime("%-d %b"),
            "vo2_max": round(v, 1) if v is not None else None,
        })
    return result


# ── Estimated W/kg (no power meter — ACSM estimate from VO2max + weight) ─────

def estimated_wkg_history(days: int = 180) -> list[dict]:
    """Estimated FTP watts and W/kg per day with a VO2max reading.

    p_vo2max = (vo2max − 7) × weight_kg / 10.8   (ACSM cycling formula)
    est_ftp_w = 0.80 × p_vo2max
    Weight is carried forward from the most recent body_metrics reading.
    """
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    with _conn() as con:
        _ensure_schema(con)
        _ensure_body_metrics_schema(con)
        vo2_rows = con.execute(
            "SELECT date, vo2_max FROM daily_metrics WHERE date >= ? AND vo2_max IS NOT NULL ORDER BY date",
            (start,),
        ).fetchall()
        weight_rows = con.execute(
            "SELECT date, weight_kg FROM body_metrics WHERE weight_kg IS NOT NULL ORDER BY date",
        ).fetchall()

    weights = [(r["date"], float(r["weight_kg"])) for r in weight_rows]
    result = []
    for r in vo2_rows:
        d_iso = r["date"]
        weight = None
        for wd, wv in weights:
            if wd <= d_iso:
                weight = wv
            else:
                break
        if weight is None or weight <= 0:
            continue
        vo2 = float(r["vo2_max"])
        p_vo2max = (vo2 - 7.0) * weight / 10.8
        est_ftp_w = 0.80 * p_vo2max
        d = date.fromisoformat(d_iso)
        result.append({
            "date": d_iso,
            "label": d.strftime("%-d %b"),
            "vo2_max": vo2,
            "weight_kg": round(weight, 1),
            "est_ftp_w": round(est_ftp_w),
            "wkg": round(est_ftp_w / weight, 2),
        })
    return result


def latest_estimated_wkg() -> Optional[dict]:
    hist = estimated_wkg_history(180)
    return hist[-1] if hist else None

def _weight_kg_on_date(d_iso: str, weights: list[tuple[str, float]]) -> Optional[float]:
    """Most recent bodyweight on or before d_iso."""
    weight = None
    for wd, wv in weights:
        if wd <= d_iso:
            weight = wv
        else:
            break
    return weight


def measured_wkg_history(days: int = 180) -> list[dict]:
    """Measured FTP watts and W/kg from ftp_tests crossed with bodyweight."""
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    with _conn() as con:
        _ensure_ftp_schema(con)
        _ensure_body_metrics_schema(con)
        tests = con.execute(
            "SELECT date, ftp_w FROM ftp_tests WHERE ftp_w IS NOT NULL ORDER BY date",
        ).fetchall()
        weight_rows = con.execute(
            "SELECT date, weight_kg FROM body_metrics WHERE weight_kg IS NOT NULL ORDER BY date",
        ).fetchall()
    weights = [(r["date"], float(r["weight_kg"])) for r in weight_rows]
    result = []
    for r in tests:
        d_iso = r["date"]
        if d_iso < start:
            continue
        weight = _weight_kg_on_date(d_iso, weights)
        if not weight or weight <= 0:
            continue
        ftp_w = int(r["ftp_w"])
        d = date.fromisoformat(d_iso)
        result.append({
            "date": d_iso,
            "label": d.strftime("%-d %b"),
            "ftp_w": ftp_w,
            "weight_kg": round(weight, 1),
            "wkg": round(ftp_w / weight, 2),
        })
    return result


def latest_measured_wkg() -> Optional[dict]:
    hist = measured_wkg_history(180)
    return hist[-1] if hist else None


# ── Latest bodyweight / lean mass (single source of truth for nutrition) ─────

def latest_weight_kg() -> Optional[float]:
    """Most recent measured bodyweight from body_metrics, or None if never logged."""
    with _conn() as con:
        _ensure_body_metrics_schema(con)
        row = con.execute(
            "SELECT weight_kg FROM body_metrics WHERE weight_kg IS NOT NULL ORDER BY date DESC LIMIT 1"
        ).fetchone()
    return float(row["weight_kg"]) if row and row["weight_kg"] is not None else None


def latest_lean_mass_kg() -> Optional[float]:
    """Most recent lean (fat-free) mass.

    Prefers the device's `muscle_mass_kg`; otherwise derives it from the most
    recent reading that has both weight and fat %, as weight × (1 − fat%/100).
    Returns None when neither is available.
    """
    with _conn() as con:
        _ensure_body_metrics_schema(con)
        row = con.execute(
            "SELECT muscle_mass_kg FROM body_metrics WHERE muscle_mass_kg IS NOT NULL ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if row and row["muscle_mass_kg"] is not None:
            return float(row["muscle_mass_kg"])
        row = con.execute(
            "SELECT weight_kg, fat_pct FROM body_metrics "
            "WHERE weight_kg IS NOT NULL AND fat_pct IS NOT NULL ORDER BY date DESC LIMIT 1"
        ).fetchone()
    if row and row["weight_kg"] is not None and row["fat_pct"] is not None:
        return round(float(row["weight_kg"]) * (1.0 - float(row["fat_pct"]) / 100.0), 1)
    return None

# ── BMR / TDEE (Katch-McArdle from body composition) ─────────────────────────

_CALIBRATION_WINDOW_DAYS = 28


def _load_tdee_inputs(days: int) -> tuple[
    list[tuple[str, float, float]],
    dict[str, float],
]:
    """Body-comp readings and per-day activity-calorie fallback for a date range."""
    end = date.today()
    start = end - timedelta(days=days - 1)
    with _conn() as con:
        _ensure_schema(con)
        _ensure_body_metrics_schema(con)
        _ensure_activities_schema(con)
        comp_rows = con.execute(
            "SELECT date, weight_kg, fat_pct FROM body_metrics "
            "WHERE weight_kg IS NOT NULL AND fat_pct IS NOT NULL ORDER BY date",
        ).fetchall()
        act_rows = con.execute(
            "SELECT date, COALESCE(SUM(calories), 0) AS act_cal FROM activities "
            "WHERE date >= ? AND date <= ? GROUP BY date",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    activity_cal_by_date = {r["date"]: r["act_cal"] for r in act_rows}
    comps = [(r["date"], float(r["weight_kg"]), float(r["fat_pct"])) for r in comp_rows]
    return comps, activity_cal_by_date


def _bmr_on_date(d_iso: str, comps: list[tuple[str, float, float]]) -> Optional[float]:
    from ..energy import bmr_katch_mcardle
    chosen = None
    for cd, w, f in comps:
        if cd <= d_iso:
            chosen = (w, f)
        else:
            break
    if chosen is None:
        return None
    return bmr_katch_mcardle(chosen[0], chosen[1])


def _tdee_model_for_day(
    d_iso: str,
    row: dict,
    comps: list[tuple[str, float, float]],
    activity_cal_by_date: dict[str, float],
) -> tuple[Optional[float], Optional[float], bool, Optional[float]]:
    """Return (bmr, active_calories, active_estimated, model_tdee)."""
    from ..energy import tdee as _tdee
    bmr = _bmr_on_date(d_iso, comps)
    active = row.get("active_calories")
    active_estimated = False
    if active is None:
        fallback = activity_cal_by_date.get(d_iso)
        if fallback:
            active = fallback
            active_estimated = True
    model_tdee = round(_tdee(active, bmr=bmr)) if bmr is not None else None
    return bmr, active, active_estimated, model_tdee


def latest_bmr() -> Optional[float]:
    """Resting metabolic rate (kcal/day) from the most recent body-comp reading
    that has both weight and body-fat %, via Katch-McArdle. None if unavailable.
    """
    from ..energy import bmr_katch_mcardle
    with _conn() as con:
        _ensure_body_metrics_schema(con)
        row = con.execute(
            "SELECT weight_kg, fat_pct FROM body_metrics "
            "WHERE weight_kg IS NOT NULL AND fat_pct IS NOT NULL "
            "ORDER BY date DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return bmr_katch_mcardle(row["weight_kg"], row["fat_pct"])


def _latest_body_comp_date() -> Optional[date]:
    """Most recent body-composition reading with weight + fat%."""
    with _conn() as con:
        _ensure_body_metrics_schema(con)
        row = con.execute(
            "SELECT date FROM body_metrics "
            "WHERE weight_kg IS NOT NULL AND fat_pct IS NOT NULL "
            "ORDER BY date DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    d = row["date"]
    if hasattr(d, "isoformat"):
        return d if isinstance(d, date) else date.fromisoformat(str(d))
    return date.fromisoformat(str(d))


def _calibration_confidence(
    cal: dict,
    *,
    paired_days: int,
    window_days: int,
    readings: list[tuple[str, float]],
    body_comp_age_days: Optional[int],
) -> dict:
    """Score calibration trustworthiness without changing the correction."""
    if not cal:
        return {"level": "inactive", "reasons": ["guardrails not met"]}

    reasons: list[str] = []
    coverage = paired_days / window_days if window_days else 0.0
    if coverage < 0.70:
        reasons.append(f"intake logged on {round(coverage * 100)}% of days (<70%)")
    if len(readings) <= 5:
        reasons.append("only minimum weigh-ins (5)")
    if cal.get("span_days", 0) < 21:
        reasons.append("weight trend span under 21 days")
    if body_comp_age_days is not None and body_comp_age_days > 14:
        reasons.append(f"body composition {body_comp_age_days} days old")
    model_avg = float(cal.get("model_avg") or 0)
    correction = float(cal.get("correction") or 0)
    if model_avg > 0 and abs(correction) >= 0.24 * model_avg:
        reasons.append("correction near ±25% clamp")

    return {
        "level": "high" if not reasons else "limited",
        "reasons": reasons,
        "intake_coverage_pct": round(coverage * 100),
        "body_comp_age_days": body_comp_age_days,
    }


def tdee_calibration(window_days: int = _CALIBRATION_WINDOW_DAYS) -> Optional[dict]:
    """Empirical TDEE calibration from trailing weight trend + logged intake.

    Intake and model TDEE are averaged over the **same** days (both present).
    Returns a correction dict when guardrails pass (≥10 paired intake days,
    ≥5 weigh-ins spanning ≥14 days), else None.
    """
    from ..energy import (
        empirical_tdee,
        tdee_correction,
        weight_trend_kg_per_day,
    )

    start = (date.today() - timedelta(days=window_days - 1)).isoformat()
    hist = raw_history(window_days)
    intake_rows = [r for r in hist if r.get("calories_consumed") is not None]
    if len(intake_rows) < 10:
        return None

    with _conn() as con:
        _ensure_body_metrics_schema(con)
        weight_rows = con.execute(
            "SELECT date, weight_kg FROM body_metrics "
            "WHERE date >= ? AND weight_kg IS NOT NULL ORDER BY date",
            (start,),
        ).fetchall()
    readings = [(r["date"], float(r["weight_kg"])) for r in weight_rows]
    slope = weight_trend_kg_per_day(readings)
    if slope is None:
        return None

    comps, activity_cal_by_date = _load_tdee_inputs(window_days)
    paired_intake: list[float] = []
    paired_model: list[float] = []
    for row in intake_rows:
        d_iso = row["date"].isoformat() if hasattr(row["date"], "isoformat") else str(row["date"])
        _, _, _, model = _tdee_model_for_day(d_iso, row, comps, activity_cal_by_date)
        if model is not None:
            paired_intake.append(float(row["calories_consumed"]))
            paired_model.append(float(model))
    if len(paired_intake) < 10:
        return None

    avg_intake = sum(paired_intake) / len(paired_intake)
    model_avg = sum(paired_model) / len(paired_model)
    empirical = empirical_tdee(avg_intake, slope)
    correction = round(tdee_correction(model_avg, empirical))
    span_days = (
        date.fromisoformat(readings[-1][0]) - date.fromisoformat(readings[0][0])
    ).days

    latest_bc = _latest_body_comp_date()
    bc_age = (date.today() - latest_bc).days if latest_bc else None

    cal = {
        "correction": correction,
        "empirical_tdee": round(empirical),
        "model_avg": round(model_avg),
        "avg_intake": round(avg_intake),
        "slope_kg_per_day": round(slope, 5),
        "n_intake_days": len(paired_intake),
        "n_weighins": len(readings),
        "span_days": span_days,
        "window_days": window_days,
    }
    cal["confidence"] = _calibration_confidence(
        cal,
        paired_days=len(paired_intake),
        window_days=window_days,
        readings=readings,
        body_comp_age_days=bc_age,
    )
    return cal


def tdee_calibration_backtest(
    window_days: int = _CALIBRATION_WINDOW_DAYS,
    holdout_days: int = 14,
) -> Optional[dict]:
    """Read-only check: does calibrated TDEE predict held-out weight trend?

    Uses the trailing ``holdout_days`` as validation: compares observed weight
    slope (kg/day) with the slope implied by average (intake − calibrated TDEE).
  """
    from ..energy import KCAL_PER_KG

    total_days = window_days + holdout_days
    hist = raw_history(total_days)
    if len(hist) < window_days + 7:
        return None

    cal = tdee_calibration(window_days)
    if cal is None:
        return None

    stable = stable_tdee_kcal(min(7, window_days))
    if stable is None:
        return None

    holdout = hist[-holdout_days:]
    intake_vals = [r["calories_consumed"] for r in holdout if r.get("calories_consumed") is not None]
    if len(intake_vals) < max(5, holdout_days // 2):
        return None

    avg_intake = sum(intake_vals) / len(intake_vals)
    predicted_slope = (avg_intake - stable) / KCAL_PER_KG

    start = (date.today() - timedelta(days=holdout_days - 1)).isoformat()
    with _conn() as con:
        _ensure_body_metrics_schema(con)
        weight_rows = con.execute(
            "SELECT date, weight_kg FROM body_metrics "
            "WHERE date >= ? AND weight_kg IS NOT NULL ORDER BY date",
            (start,),
        ).fetchall()
    from ..energy import weight_trend_kg_per_day
    readings = [(r["date"], float(r["weight_kg"])) for r in weight_rows]
    observed_slope = weight_trend_kg_per_day(readings)
    if observed_slope is None:
        return None

    error_kg_per_day = predicted_slope - observed_slope
    return {
        "holdout_days": holdout_days,
        "stable_tdee": stable,
        "avg_intake_holdout": round(avg_intake),
        "predicted_slope_kg_per_day": round(predicted_slope, 5),
        "observed_slope_kg_per_day": round(observed_slope, 5),
        "error_kg_per_day": round(error_kg_per_day, 5),
        "n_intake_days": len(intake_vals),
        "n_weighins": len(readings),
    }


def _applied_tdee_correction(cal: Optional[dict]) -> Optional[int]:
    """Calibration offset for prescriptions — only when confidence is high.

    Sparse food logging biases empirical TDEE low and over-corrects burn
    downward, which then hits MIN_INTAKE and nullifies planned deficits. When
    confidence is limited/inactive (or missing), prescriptions use model TDEE.
    """
    if not cal:
        return None
    conf = cal.get("confidence") or {}
    if conf.get("level") != "high":
        return None
    corr = cal.get("correction")
    if corr is None:
        return None
    return int(corr)


def tdee_history(days: int = 14) -> list[dict]:
    """Per-day TDEE for the last `days` days (oldest first).

    TDEE = Katch-McArdle BMR (weight + fat% carried forward from the most
    recent body-comp reading on or before each day) + that day's measured
    Garmin active calories, plus an optional weight-trend calibration offset
    when calibration confidence is ``high``. Days without enough data carry
    ``tdee = None``.
    """
    cal = tdee_calibration(_CALIBRATION_WINDOW_DAYS)
    correction = _applied_tdee_correction(cal)
    comps, activity_cal_by_date = _load_tdee_inputs(days)

    result = []
    for row in raw_history(days):
        d = row["date"]
        d_iso = d.isoformat() if hasattr(d, "isoformat") else str(d)
        bmr, active, active_estimated, model_tdee = _tdee_model_for_day(
            d_iso, row, comps, activity_cal_by_date
        )
        if model_tdee is not None and correction is not None:
            corrected = round(model_tdee + correction)
        else:
            corrected = model_tdee
        result.append({
            "date": d,
            "bmr": round(bmr) if bmr is not None else None,
            "active_calories": active,
            "active_estimated": active_estimated,
            "tdee_model": model_tdee,
            "calibration_kcal": correction,
            "tdee": corrected,
        })
    return result


def stable_tdee_kcal(days: int = 7) -> Optional[float]:
    """Mean calibrated TDEE over recent days — the intake-prescription burn.

    Prefers days with a real (non-estimated) Garmin active-calorie total when
    at least 3 exist; otherwise averages whatever days have a TDEE. Returns
    None when no day in the window has one.
    """
    rows = [r for r in tdee_history(days) if r.get("tdee") is not None]
    if not rows:
        return None
    solid = [r for r in rows if not r.get("active_estimated")]
    use = solid if len(solid) >= 3 else rows
    return round(sum(float(r["tdee"]) for r in use) / len(use))

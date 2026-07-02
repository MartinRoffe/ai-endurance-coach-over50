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


def tdee_history(days: int = 14) -> list[dict]:
    """Per-day TDEE for the last `days` days (oldest first).

    TDEE = Katch-McArdle BMR (weight + fat% carried forward from the most
    recent body-comp reading on or before each day) + that day's measured
    Garmin active calories. Days without enough data carry ``tdee = None``.
    """
    from ..energy import bmr_katch_mcardle, tdee as _tdee
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
        # Sum of recorded-activity calories per day — used as a fallback for the
        # day's active burn when Garmin's daily-summary activeKilocalories is
        # missing (e.g. not yet synced). When the daily summary IS present it
        # already includes activities + NEAT, so we don't add on top of it.
        act_rows = con.execute(
            "SELECT date, COALESCE(SUM(calories), 0) AS act_cal FROM activities "
            "WHERE date >= ? AND date <= ? GROUP BY date",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    activity_cal_by_date = {r["date"]: r["act_cal"] for r in act_rows}
    comps = [(r["date"], float(r["weight_kg"]), float(r["fat_pct"])) for r in comp_rows]

    def _bmr_on(d_iso: str) -> Optional[float]:
        chosen = None
        for cd, w, f in comps:
            if cd <= d_iso:
                chosen = (w, f)
            else:
                break
        if chosen is None:
            return None
        return bmr_katch_mcardle(chosen[0], chosen[1])

    result = []
    for row in raw_history(days):
        d = row["date"]
        d_iso = d.isoformat() if hasattr(d, "isoformat") else str(d)
        bmr = _bmr_on(d_iso)
        active = row.get("active_calories")
        active_estimated = False
        if active is None:
            fallback = activity_cal_by_date.get(d_iso)
            if fallback:
                active = fallback
                active_estimated = True
        result.append({
            "date": d,
            "bmr": round(bmr) if bmr is not None else None,
            "active_calories": active,
            "active_estimated": active_estimated,
            "tdee": (
                round(_tdee(active, bmr=bmr))
                if bmr is not None else None
            ),
        })
    return result

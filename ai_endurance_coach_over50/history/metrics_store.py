"""Daily metrics persistence, baseline statistics, and z-score calculations."""
from __future__ import annotations

import math
from dataclasses import asdict, fields
from datetime import date, timedelta
from typing import Optional

from ..metrics import DailyMetrics
from .db import NUMERIC_FIELDS, _conn, _ensure_schema


# Don't score these — context/baselines or timestamp fields, not daily readiness signals
_UNSCORED = {
    "training_load_chronic", "vo2_max", "total_steps", "active_calories",
    "calories_consumed", "calorie_goal", "calorie_goal_adjusted",
    "carbs_consumed", "protein_consumed",
    # acclimation + resting HR — consumed by illness/heat features, not the composite
    "heat_acclimation_pct", "altitude_acclimation", "resting_hr",
    # timestamps — large absolute values destroy z-score baseline
    "sleep_start_ts", "sleep_end_ts",
    # sleep detail — sleep_score already summarises these for the composite
    "deep_sleep_seconds", "light_sleep_seconds", "rem_sleep_seconds",
    "awake_sleep_seconds", "nap_time_seconds",
    "avg_spo2", "avg_respiration", "lowest_respiration", "highest_respiration",
}

SCORED_FIELDS = [f for f in NUMERIC_FIELDS if f not in _UNSCORED]

HIGHER_IS_BETTER = {
    "sleep_score", "sleep_seconds", "hrv_last_night", "hrv_weekly_avg",
    "body_battery_morning", "total_steps", "active_calories",
}
LOWER_IS_BETTER = {
    "avg_stress", "rest_stress", "acwr", "training_load_acute", "resting_hr",
}


def save(m: DailyMetrics) -> None:
    with _conn() as con:
        _ensure_schema(con)
        data = asdict(m)
        data["date"] = m.date.isoformat()
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        con.execute(
            f"INSERT OR REPLACE INTO daily_metrics ({cols}) VALUES ({placeholders})",
            list(data.values()),
        )


def load(target_date: date) -> Optional[DailyMetrics]:
    with _conn() as con:
        _ensure_schema(con)
        row = con.execute(
            "SELECT * FROM daily_metrics WHERE date = ?",
            (target_date.isoformat(),),
        ).fetchone()
    if row is None:
        return None
    known = {f.name for f in fields(DailyMetrics)}
    kwargs = {k: row[k] for k in row.keys() if k in known}
    kwargs["date"] = date.fromisoformat(kwargs["date"])
    return DailyMetrics(**kwargs)


def _stats_from_rows(rows) -> dict[str, tuple[float, float]]:
    """{field: (mean, std)} for scored fields across the given daily_metrics rows.

    Uses population std (÷n, matching pstdev elsewhere in the app) — slightly
    tight at small n, but every z-threshold is calibrated against this, so
    don't switch to sample std without recalibrating.
    """
    stats: dict[str, tuple[float, float]] = {}
    for field in SCORED_FIELDS:
        values = [row[field] for row in rows if row[field] is not None]
        if len(values) < 3:
            continue
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(variance)
        if std > 0:
            stats[field] = (mean, std)
    return stats


def baseline_stats(
    reference_date: date,
    window_days: int = 30,
) -> dict[str, tuple[float, float]]:
    """Returns {field_name: (mean, std)} for scored fields in the window before reference_date."""
    start = (reference_date - timedelta(days=window_days)).isoformat()
    end = (reference_date - timedelta(days=1)).isoformat()

    with _conn() as con:
        _ensure_schema(con)
        rows = con.execute(
            "SELECT * FROM daily_metrics WHERE date >= ? AND date <= ? ORDER BY date",
            (start, end),
        ).fetchall()
    return _stats_from_rows(rows)


def field_baseline(
    field: str,
    reference_date: date,
    window_days: int = 30,
) -> Optional[tuple[float, float]]:
    """(mean, std) for any single numeric field over the baseline window.

    Unlike ``baseline_stats`` this also works for ``_UNSCORED`` fields (e.g.
    ``resting_hr``) so they can be displayed with a baseline without being
    pulled into the composite readiness score.
    """
    if field not in NUMERIC_FIELDS:
        return None
    start = (reference_date - timedelta(days=window_days)).isoformat()
    end = (reference_date - timedelta(days=1)).isoformat()
    with _conn() as con:
        _ensure_schema(con)
        rows = con.execute(
            f"SELECT {field} AS v FROM daily_metrics WHERE date >= ? AND date <= ? ORDER BY date",
            (start, end),
        ).fetchall()
    values = [row["v"] for row in rows if row["v"] is not None]
    if len(values) < 3:
        return None
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance)
    if std <= 0:
        return None
    return (mean, std)


def z_score(value: float, mean: float, std: float, field: str) -> float:
    """Signed z-score oriented so positive = better readiness."""
    z = (value - mean) / std
    if field in LOWER_IS_BETTER:
        z = -z
    return z


def composite_score(m: DailyMetrics, stats: dict[str, tuple[float, float]]) -> Optional[float]:
    """Mean z-score across available scored metrics that have a baseline."""
    z_scores = []
    for field in SCORED_FIELDS:
        value = getattr(m, field)
        if value is None or field not in stats:
            continue
        mean, std = stats[field]
        z_scores.append(z_score(value, mean, std, field))
    if not z_scores:
        return None
    return sum(z_scores) / len(z_scores)


def history_for_chart(days: int = 14) -> list[tuple[date, Optional[float]]]:
    """Composite score per day, computed from ONE windowed query (the old
    per-day load() + baseline_stats() pair was ~2(days+1) queries on the
    dashboard hot path)."""
    end = date.today()
    start = end - timedelta(days=days)
    window_start = start - timedelta(days=30)  # covers the oldest day's baseline

    with _conn() as con:
        _ensure_schema(con)
        rows = con.execute(
            "SELECT * FROM daily_metrics WHERE date >= ? AND date <= ? ORDER BY date",
            (window_start.isoformat(), end.isoformat()),
        ).fetchall()
    by_date = {r["date"]: r for r in rows}
    known = {f.name for f in fields(DailyMetrics)}

    results = []
    for i in range(days + 1):
        d = start + timedelta(days=i)
        row = by_date.get(d.isoformat())
        if row is None:
            results.append((d, None))
            continue
        b_start = (d - timedelta(days=30)).isoformat()
        b_end = (d - timedelta(days=1)).isoformat()
        stats = _stats_from_rows([r for r in rows if b_start <= r["date"] <= b_end])
        kwargs = {k: row[k] for k in row.keys() if k in known}
        kwargs["date"] = d
        results.append((d, composite_score(DailyMetrics(**kwargs), stats)))
    return results


def seven_day_composite_trend_csv() -> str:
    """Comma-separated composite σ for the last 7 days (oldest→today), same as email prompt."""
    history = history_for_chart(days=7)
    return ", ".join(f"{v:+.2f}" if v is not None else "—" for _, v in history)


def raw_history(days: int = 14) -> list[dict]:
    """Return a list of dicts (one per day, oldest first) for the last `days` days.

    Each dict has: date (date), hrv_last_night, sleep_score, avg_stress (all may be None).
    Days with no DB row still appear with None values so the sparkline x-axis is continuous.
    """
    end = date.today()
    start = end - timedelta(days=days - 1)
    with _conn() as con:
        _ensure_schema(con)
        rows = con.execute(
            """SELECT date, hrv_last_night, sleep_score, avg_stress, rest_stress,
                      resting_hr, total_steps, active_calories,
                      calories_consumed, calorie_goal, calorie_goal_adjusted,
                      carbs_consumed, protein_consumed
               FROM daily_metrics
               WHERE date >= ? AND date <= ?
               ORDER BY date""",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    by_date = {row["date"]: dict(row) for row in rows}
    result = []
    for i in range(days):
        d = start + timedelta(days=i)
        row = by_date.get(d.isoformat(), {})
        result.append({
            "date": d,
            "hrv_last_night":          row.get("hrv_last_night"),
            "sleep_score":             row.get("sleep_score"),
            "avg_stress":              row.get("avg_stress"),
            "rest_stress":             row.get("rest_stress"),
            "resting_hr":              row.get("resting_hr"),
            "total_steps":             row.get("total_steps"),
            "active_calories":         row.get("active_calories"),
            "calories_consumed":       row.get("calories_consumed"),
            "calorie_goal":            row.get("calorie_goal"),
            "calorie_goal_adjusted":   row.get("calorie_goal_adjusted"),
            "carbs_consumed":          row.get("carbs_consumed"),
            "protein_consumed":        row.get("protein_consumed"),
        })
    return result


def sleep_history(days: int = 30) -> list[dict]:
    """Return one dict per day (oldest first) for the last `days` days.

    Hours are pre-computed floats; missing nights appear with None values so
    chart x-axes stay continuous.
    """
    end = date.today()
    start = end - timedelta(days=days - 1)
    with _conn() as con:
        _ensure_schema(con)
        rows = con.execute(
            """SELECT date, sleep_score, sleep_seconds,
                      deep_sleep_seconds, light_sleep_seconds,
                      rem_sleep_seconds, awake_sleep_seconds,
                      nap_time_seconds, sleep_start_ts, sleep_end_ts,
                      avg_spo2, avg_respiration,
                      lowest_respiration, highest_respiration,
                      hrv_last_night
               FROM daily_metrics
               WHERE date >= ? AND date <= ?
               ORDER BY date""",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    by_date = {row["date"]: dict(row) for row in rows}

    def _hrs(secs):
        return round(secs / 3600, 2) if secs is not None else None

    result = []
    for i in range(days):
        d = start + timedelta(days=i)
        r = by_date.get(d.isoformat(), {})
        total_secs = r.get("sleep_seconds")
        deep_s  = r.get("deep_sleep_seconds")
        light_s = r.get("light_sleep_seconds")
        rem_s   = r.get("rem_sleep_seconds")
        awake_s = r.get("awake_sleep_seconds")
        result.append({
            "date":              d.isoformat(),
            "label":             d.strftime("%-d %b"),
            "sleep_score":       r.get("sleep_score"),
            "sleep_hours":       _hrs(total_secs),
            "deep_hours":        _hrs(deep_s),
            "light_hours":       _hrs(light_s),
            "rem_hours":         _hrs(rem_s),
            "awake_hours":       _hrs(awake_s),
            "nap_min":           round(r["nap_time_seconds"] / 60) if r.get("nap_time_seconds") else None,
            "spo2":              r.get("avg_spo2"),
            "respiration":       r.get("avg_respiration"),
            "lowest_respiration":  r.get("lowest_respiration"),
            "highest_respiration": r.get("highest_respiration"),
            "hrv":               r.get("hrv_last_night"),
            "deep_pct":          round(deep_s / total_secs * 100) if deep_s and total_secs else None,
            "rem_pct":           round(rem_s  / total_secs * 100) if rem_s  and total_secs else None,
        })
    return result

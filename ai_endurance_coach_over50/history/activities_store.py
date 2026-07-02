"""Activity rows: save/load, zone distribution, power patching."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .db import _ACTIVITY_COLS, _conn, _ensure_activities_schema


# Garmin type_key values that satisfy each plan session type
ACTIVITY_MATCH: dict[str, set[str]] = {
    "bike":     {"road_biking", "cycling", "virtual_ride", "indoor_cycling", "mountain_biking"},
    "tempo":    {"road_biking", "cycling", "virtual_ride", "indoor_cycling", "mountain_biking"},
    "ftp":      {"road_biking", "cycling", "virtual_ride", "indoor_cycling", "mountain_biking"},
    "long":     {"road_biking", "cycling", "virtual_ride", "indoor_cycling", "mountain_biking"},
    "strength": {"strength_training", "stair_climbing", "fitness_equipment"},
    "ruck":     {"hiking", "walking", "trail_running", "running", "rucking", "load_carry"},
}


def patch_activity_power(activity_id: int, fields: dict) -> bool:
    """Update power columns on an existing activity row. Returns True if patched."""
    allowed = ("avg_power_w", "max_power_w", "norm_power_w", "has_power_meter")
    updates = {k: fields[k] for k in allowed if k in fields and fields[k] is not None}
    if not updates:
        return False
    sets = ", ".join(f"{k} = ?" for k in updates)
    with _conn() as con:
        _ensure_activities_schema(con)
        row = con.execute(
            "SELECT 1 FROM activities WHERE activity_id = ?", (activity_id,)
        ).fetchone()
        if not row:
            return False
        con.execute(
            f"UPDATE activities SET {sets} WHERE activity_id = ?",
            (*updates.values(), activity_id),
        )
    return True


def save_activities(activities: list[dict]) -> None:
    cols = [name for name, _ in _ACTIVITY_COLS]
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    with _conn() as con:
        _ensure_activities_schema(con)
        for a in activities:
            values = [a.get(name) for name in cols]
            con.execute(
                f"INSERT OR REPLACE INTO activities ({col_list}) VALUES ({placeholders})",
                values,
            )


def load_recent_activities(days: int = 7) -> list[dict]:
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    with _conn() as con:
        _ensure_activities_schema(con)
        rows = con.execute(
            "SELECT * FROM activities WHERE date >= ? ORDER BY start_time DESC",
            (start,),
        ).fetchall()
    return [dict(r) for r in rows]


_ZONE_BIKE_KEYS = {"road_biking", "cycling", "virtual_ride", "indoor_cycling", "mountain_biking"}


def zone_distribution(days: int = 7) -> Optional[dict]:
    """Aggregate HR zone distribution across cycling activities for the last `days` days.

    Returns zone percentages and totals, or None if no zone data is available.
    """
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    placeholders = ",".join("?" * len(_ZONE_BIKE_KEYS))
    with _conn() as con:
        _ensure_activities_schema(con)
        rows = con.execute(
            f"""SELECT hr_zone_1_sec, hr_zone_2_sec, hr_zone_3_sec, hr_zone_4_sec, hr_zone_5_sec
               FROM activities
               WHERE date >= ? AND type_key IN ({placeholders})""",
            (start, *_ZONE_BIKE_KEYS),
        ).fetchall()

    z = [0.0] * 5
    count = 0
    for row in rows:
        vals = [row[f"hr_zone_{i}_sec"] or 0 for i in range(1, 6)]
        if any(v > 0 for v in vals):
            for i, v in enumerate(vals):
                z[i] += v
            count += 1

    total = sum(z)
    if total == 0 or count == 0:
        return None

    return {
        "z1_pct": round(z[0] / total * 100, 1),
        "z2_pct": round(z[1] / total * 100, 1),
        "z3_pct": round(z[2] / total * 100, 1),
        "z4_pct": round(z[3] / total * 100, 1),
        "z5_pct": round(z[4] / total * 100, 1),
        "total_min": round(total / 60),
        "activity_count": count,
    }


def load_activities_by_date(start: date, end: date) -> dict[str, list[dict]]:
    """Return {date_str: [activity, ...]} for all activities in [start, end]."""
    with _conn() as con:
        _ensure_activities_schema(con)
        rows = con.execute(
            "SELECT * FROM activities WHERE date >= ? AND date <= ? ORDER BY start_time",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    result: dict[str, list[dict]] = {}
    for r in rows:
        d = dict(r)
        result.setdefault(d["date"], []).append(d)
    return result

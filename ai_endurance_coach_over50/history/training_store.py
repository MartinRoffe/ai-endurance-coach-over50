"""FTP tests, durability, BTB, monotony/strain, intensity distribution, fuelling logs."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .activities_store import _ZONE_BIKE_KEYS
from .body_store import latest_measured_wkg
from .db import (
    _conn,
    _ensure_activities_schema,
    _ensure_btb_schema,
    _ensure_durability_schema,
    _ensure_fit_meta_schema,
    _ensure_ftp_schema,
    _ensure_fuelling_log_schema,
    _ensure_interval_analyses_schema,
    _ensure_power_durability_schema,
    _ensure_schema,
)


def save_ftp_test(test_date: str, activity_id: Optional[int], ftp_hr: Optional[int],
                  ftp_hr_max: Optional[int], note: Optional[str] = None,
                  ftp_w: Optional[int] = None) -> None:
    with _conn() as con:
        _ensure_ftp_schema(con)
        con.execute(
            "INSERT OR IGNORE INTO ftp_tests (date, activity_id, ftp_hr, ftp_hr_max, ftp_w, note) VALUES (?,?,?,?,?,?)",
            (test_date, activity_id, ftp_hr, ftp_hr_max, ftp_w, note),
        )


def upsert_ftp_test(test_date: str, activity_id: Optional[int], ftp_hr: Optional[int],
                    ftp_hr_max: Optional[int], note: Optional[str] = None,
                    ftp_w: Optional[int] = None) -> None:
    """Insert or replace FTP row for a date (Accept-estimate / --set-ftp)."""
    with _conn() as con:
        _ensure_ftp_schema(con)
        con.execute(
            "INSERT INTO ftp_tests (date, activity_id, ftp_hr, ftp_hr_max, ftp_w, note) "
            "VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(date) DO UPDATE SET "
            "activity_id=COALESCE(excluded.activity_id, ftp_tests.activity_id), "
            "ftp_hr=COALESCE(excluded.ftp_hr, ftp_tests.ftp_hr), "
            "ftp_hr_max=COALESCE(excluded.ftp_hr_max, ftp_tests.ftp_hr_max), "
            "ftp_w=COALESCE(excluded.ftp_w, ftp_tests.ftp_w), "
            "note=COALESCE(excluded.note, ftp_tests.note)",
            (test_date, activity_id, ftp_hr, ftp_hr_max, ftp_w, note),
        )


def load_ftp_tests() -> list[dict]:
    with _conn() as con:
        _ensure_ftp_schema(con)
        rows = con.execute("SELECT * FROM ftp_tests ORDER BY date ASC").fetchall()
    return [dict(r) for r in rows]


# ── W/kg goal (target power-to-weight + date) ────────────────────────────────

_WKG_GOAL_KEY = "wkg_goal_v1"
_WKG_GOAL_DEFAULTS = {"target_wkg": 4.0, "target_date": "2027-08-23"}


def load_wkg_goal() -> dict:
    """Target W/kg + date, defaults merged over stored JSON (malformed -> defaults).

    Stored in ``text_cache`` (precedent: ``workouts_stale_ftp`` keeps a non-AI
    scalar there), so no dedicated table is needed.
    """
    import json

    from .text_cache import get_cached_text

    goal = dict(_WKG_GOAL_DEFAULTS)
    raw = get_cached_text(_WKG_GOAL_KEY)
    if raw:
        try:
            stored = json.loads(raw)
            if isinstance(stored, dict):
                if stored.get("target_wkg") is not None:
                    goal["target_wkg"] = float(stored["target_wkg"])
                if stored.get("target_date"):
                    goal["target_date"] = str(stored["target_date"])
        except (ValueError, TypeError):
            pass
    return goal


def save_wkg_goal(target_wkg: float, target_date: str) -> None:
    import json

    from .text_cache import set_cached_text

    set_cached_text(
        _WKG_GOAL_KEY,
        json.dumps({"target_wkg": float(target_wkg), "target_date": str(target_date)}),
    )


def power_meter_active() -> bool:
    """True when ≥3 cycling activities in the last 60 days recorded power."""
    return count_power_rides(60) >= 3


def count_power_rides(days: int = 60) -> int:
    """Count cycling activities with power in the last `days` days."""
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    placeholders = ",".join("?" * len(_ZONE_BIKE_KEYS))
    with _conn() as con:
        _ensure_activities_schema(con)
        row = con.execute(
            f"""SELECT COUNT(*) AS n FROM activities
                WHERE date >= ? AND type_key IN ({placeholders})
                  AND has_power_meter = 1""",
            (start, *_ZONE_BIKE_KEYS),
        ).fetchone()
    return row["n"] or 0


def power_activation_status(days: int = 60) -> dict:
    """Checklist for power-meter onboarding (Phase 6 activation workflow)."""
    power_rides = count_power_rides(days)
    active = power_meter_active()
    tests = load_ftp_tests()
    has_ftp_w = any(t.get("ftp_w") for t in tests)
    measured = latest_measured_wkg()
    decoupling_n = len(load_power_durability(days))

    power_zones_n = 0
    try:
        start = (date.today() - timedelta(days=days - 1)).isoformat()
        placeholders = ",".join("?" * len(_ZONE_BIKE_KEYS))
        with _conn() as con:
            _ensure_activities_schema(con)
            row = con.execute(
                f"""SELECT COUNT(*) AS n FROM activities a
                    JOIN activity_analyses an ON a.activity_id = an.activity_id
                    WHERE a.date >= ? AND a.type_key IN ({placeholders})
                      AND a.has_power_meter = 1 AND an.power_zones_json IS NOT NULL""",
                (start, *_ZONE_BIKE_KEYS),
            ).fetchone()
            power_zones_n = row["n"] or 0
    except Exception:
        pass

    steps = [
        {
            "id": "garmin",
            "label": "Record ≥1 ride with power in Garmin Connect",
            "done": power_rides >= 1,
            "hint": "Pair pedals and verify average watts on the activity in Connect web UI.",
        },
        {
            "id": "backfill",
            "label": "Backfill activities (endurance-coach --activate-power 30)",
            "done": power_rides >= 1,
            "hint": "Pulls power summary fields into the local database.",
        },
        {
            "id": "active",
            "label": "≥3 power rides in 60 days (dashboard power surfaces unlock)",
            "done": active,
            "hint": f"{power_rides}/3 power rides logged in the last {days} days.",
        },
        {
            "id": "metrics",
            "label": "Mine power zones & decoupling on historical rides",
            "done": power_zones_n >= 1 or decoupling_n >= 1,
            "hint": "Runs automatically during --activate-power; also via /analysis-refresh.",
        },
        {
            "id": "ftp_w",
            "label": "Complete one FTP test ride (seeds measured FTP watts)",
            "done": has_ftp_w,
            "hint": "Schedule an FTP test; watts auto-populate from the 20-min effort.",
        },
        {
            "id": "performance",
            "label": "Visit /performance — confirm measured W/kg chart",
            "done": has_ftp_w and active,
            "hint": "Measured W/kg supersedes the VO2max estimate when FTP watts exist.",
        },
    ]

    next_action = next((s for s in steps if not s["done"]), None)
    return {
        "power_rides_60d": power_rides,
        "power_meter_active": active,
        "has_measured_ftp_w": has_ftp_w,
        "measured_wkg": measured,
        "decoupling_count": decoupling_n,
        "power_zones_count": power_zones_n,
        "steps": steps,
        "next_action": next_action["label"] if next_action else None,
        "complete": active and has_ftp_w,
    }


def intensity_distribution_by_week(start: date, end: date) -> list[dict]:
    """Aggregate HR zone distribution per ISO week across all cycling activities in [start, end]."""
    placeholders = ",".join("?" * len(_ZONE_BIKE_KEYS))
    with _conn() as con:
        _ensure_activities_schema(con)
        rows = con.execute(
            f"""SELECT strftime('%Y-W%W', date) AS week_label,
                       SUM(hr_zone_1_sec) AS z1, SUM(hr_zone_2_sec) AS z2,
                       SUM(hr_zone_3_sec) AS z3, SUM(hr_zone_4_sec) AS z4,
                       SUM(hr_zone_5_sec) AS z5, COUNT(*) AS activity_count
                FROM activities
                WHERE date >= ? AND date <= ? AND type_key IN ({placeholders})
                GROUP BY week_label
                ORDER BY week_label ASC""",
            (start.isoformat(), end.isoformat(), *_ZONE_BIKE_KEYS),
        ).fetchall()

    result = []
    for row in rows:
        z = [row[f"z{i}"] or 0.0 for i in range(1, 6)]
        total = sum(z)
        if total == 0:
            continue
        result.append({
            "week_label": row["week_label"],
            "z1_pct": round(z[0] / total * 100, 1),
            "z2_pct": round(z[1] / total * 100, 1),
            "z3_pct": round(z[2] / total * 100, 1),
            "z4_pct": round(z[3] / total * 100, 1),
            "z5_pct": round(z[4] / total * 100, 1),
            "total_min": round(total / 60),
            "activity_count": row["activity_count"],
            "z1_sec": z[0], "z2_sec": z[1], "z3_sec": z[2], "z4_sec": z[3], "z5_sec": z[4],
        })
    return result


def intensity_distribution_by_week_power(start: date, end: date) -> list[dict]:
    """Aggregate power zone distribution per ISO week from analysed rides with power."""
    import json
    placeholders = ",".join("?" * len(_ZONE_BIKE_KEYS))
    with _conn() as con:
        _ensure_activities_schema(con)
        rows = con.execute(
            f"""SELECT strftime('%Y-W%W', a.date) AS week_label,
                       an.power_zones_json
                FROM activities a
                JOIN activity_analyses an ON a.activity_id = an.activity_id
                WHERE a.date >= ? AND a.date <= ? AND a.type_key IN ({placeholders})
                  AND a.has_power_meter = 1 AND an.power_zones_json IS NOT NULL""",
            (start.isoformat(), end.isoformat(), *_ZONE_BIKE_KEYS),
        ).fetchall()

    weekly: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    for row in rows:
        label = row["week_label"]
        zones = json.loads(row["power_zones_json"])
        if label not in weekly:
            weekly[label] = [0.0] * 5
            counts[label] = 0
        for z in zones:
            zn = int(z.get("zone") or 0)
            if 1 <= zn <= 5:
                weekly[label][zn - 1] += z.get("secs") or 0
        counts[label] += 1

    result = []
    for week_label in sorted(weekly):
        z = weekly[week_label]
        total = sum(z)
        if total == 0:
            continue
        result.append({
            "week_label": week_label,
            "z1_pct": round(z[0] / total * 100, 1),
            "z2_pct": round(z[1] / total * 100, 1),
            "z3_pct": round(z[2] / total * 100, 1),
            "z4_pct": round(z[3] / total * 100, 1),
            "z5_pct": round(z[4] / total * 100, 1),
            "total_min": round(total / 60),
            "activity_count": counts[week_label],
            "z1_sec": z[0], "z2_sec": z[1], "z3_sec": z[2], "z4_sec": z[3], "z5_sec": z[4],
        })
    return result


def weekly_tss(weeks: int = 12) -> list[dict]:
    """Weekly summed TSS from power-meter rides."""
    if not power_meter_active():
        return []
    end = date.today()
    start = end - timedelta(weeks=weeks * 7)
    with _conn() as con:
        _ensure_activities_schema(con)
        rows = con.execute(
            """SELECT strftime('%Y-W%W', date) AS week_label,
                      SUM(COALESCE(tss, 0)) AS total_tss,
                      COUNT(*) AS ride_count
               FROM activities
               WHERE date >= ? AND date <= ? AND has_power_meter = 1 AND tss IS NOT NULL
               GROUP BY week_label ORDER BY week_label""",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    return [dict(r) for r in rows]


def power_pmc_history(days: int = 90) -> list[dict]:
    """42/7-day EMA CTL/ATL/TSB over daily TSS (Coggan units)."""
    if not power_meter_active():
        return []
    from math import exp

    end = date.today()
    start = end - timedelta(days=days - 1)
    daily: dict[str, float] = {}
    with _conn() as con:
        _ensure_activities_schema(con)
        rows = con.execute(
            """SELECT date, SUM(COALESCE(tss, 0)) AS day_tss
               FROM activities
               WHERE date >= ? AND date <= ? AND has_power_meter = 1
               GROUP BY date ORDER BY date""",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    for r in rows:
        daily[r["date"]] = float(r["day_tss"] or 0)

    ctl = atl = 0.0
    result: list[dict] = []
    d = start
    while d <= end:
        tss = daily.get(d.isoformat(), 0.0)
        ctl = ctl * exp(-1 / 42) + tss * (1 - exp(-1 / 42))
        atl = atl * exp(-1 / 7) + tss * (1 - exp(-1 / 7))
        result.append({
            "date": d.isoformat(),
            "label": d.strftime("%-d %b"),
            "tss": round(tss, 1),
            "ctl": round(ctl, 1),
            "atl": round(atl, 1),
            "tsb": round(ctl - atl, 1),
        })
        d += timedelta(days=1)
    return result


def save_btb_note(btb_date: str, day_number: int, fatigue_rating: Optional[int], note: Optional[str] = None) -> None:
    with _conn() as con:
        _ensure_btb_schema(con)
        con.execute("DELETE FROM btb_notes WHERE date = ?", (btb_date,))
        con.execute(
            "INSERT INTO btb_notes (date, day_number, fatigue_rating, note) VALUES (?,?,?,?)",
            (btb_date, day_number, fatigue_rating, note),
        )


_BTB_BIKE_KEYS = {"road_biking", "cycling", "virtual_ride", "indoor_cycling", "mountain_biking"}


def load_btb_summary() -> list[dict]:
    """Find consecutive cycling day pairs and return them with fatigue notes."""
    with _conn() as con:
        _ensure_activities_schema(con)
        _ensure_btb_schema(con)
        placeholders = ",".join("?" * len(_BTB_BIKE_KEYS))
        rows = con.execute(
            f"""SELECT date, AVG(avg_hr) AS avg_hr, SUM(duration_seconds) AS total_secs
                FROM activities
                WHERE type_key IN ({placeholders})
                GROUP BY date
                ORDER BY date DESC""",
            (*_BTB_BIKE_KEYS,),
        ).fetchall()
        btb_notes_rows = con.execute("SELECT * FROM btb_notes ORDER BY date").fetchall()

    btb_notes = {r["date"]: dict(r) for r in btb_notes_rows}
    cycling_dates = [dict(r) for r in rows]  # newest first

    pairs = []
    for i in range(len(cycling_dates) - 1):
        day2 = cycling_dates[i]
        day1 = cycling_dates[i + 1]
        # Check they are consecutive calendar days
        try:
            d2 = date.fromisoformat(day2["date"])
            d1 = date.fromisoformat(day1["date"])
            if (d2 - d1).days != 1:
                continue
        except Exception:
            continue
        n1 = btb_notes.get(day1["date"], {})
        n2 = btb_notes.get(day2["date"], {})
        pairs.append({
            "date1": day1["date"],
            "date2": day2["date"],
            "avg_hr_1": round(day1["avg_hr"]) if day1["avg_hr"] else None,
            "avg_hr_2": round(day2["avg_hr"]) if day2["avg_hr"] else None,
            "dur_min_1": round((day1["total_secs"] or 0) / 60),
            "dur_min_2": round((day2["total_secs"] or 0) / 60),
            "fatigue_rating_1": n1.get("fatigue_rating"),
            "fatigue_rating_2": n2.get("fatigue_rating"),
            "note_1": n1.get("note"),
            "note_2": n2.get("note"),
        })
    return pairs[:10]


# ── Foster monotony & strain ─────────────────────────────────────────────────

def weekly_monotony_strain(weeks: int = 8) -> list[dict]:
    """Foster training monotony & strain, one dict per Mon–Sun week (oldest first).

    daily_load = SUM(activities.training_load) per day; days with no training
    count as 0.0 (monotony is about load *variability* across all 7 days).
    monotony = mean(daily) / pstdev(daily)  (None when stdev == 0)
    strain   = weekly_load * monotony
    Falls back to duration_seconds/60 for trained days with no training_load.
    """
    import statistics

    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    start = this_monday - timedelta(weeks=weeks - 1)
    with _conn() as con:
        _ensure_activities_schema(con)
        rows = con.execute(
            """SELECT date,
                      SUM(training_load) AS load,
                      SUM(duration_seconds) AS secs
               FROM activities
               WHERE date >= ?
               GROUP BY date""",
            (start.isoformat(),),
        ).fetchall()

    daily_load: dict[str, float] = {}
    for r in rows:
        load = r["load"]
        if load is None and r["secs"]:
            load = r["secs"] / 60.0  # fallback: minutes as load proxy
        daily_load[r["date"]] = float(load or 0.0)

    result = []
    for w in range(weeks):
        week_start = start + timedelta(weeks=w)
        days = [week_start + timedelta(days=i) for i in range(7)]
        loads = [daily_load.get(d.isoformat(), 0.0) for d in days]
        # For the current (incomplete) week, only use elapsed days
        if week_start == this_monday:
            elapsed = (today - week_start).days + 1
            loads = loads[:elapsed]
        if not loads:
            continue
        weekly_load = sum(loads)
        mean = statistics.mean(loads)
        stdev = statistics.pstdev(loads)
        monotony = round(mean / stdev, 2) if stdev > 0 else None
        strain = round(weekly_load * monotony) if monotony is not None else None
        result.append({
            "week_start": week_start,
            "label": week_start.strftime("%-d %b"),
            "weekly_load": round(weekly_load),
            "monotony": monotony,
            "strain": strain,
            "days_trained": sum(1 for v in loads if v > 0),
        })
    return result

# ── Durability (late-ride HR drift) ──────────────────────────────────────────

def save_durability(activity_id: int, row: dict) -> None:
    with _conn() as con:
        _ensure_durability_schema(con)
        con.execute(
            """INSERT OR REPLACE INTO activity_durability
               (activity_id, date, duration_min, first_third_hr, final_third_hr, drift_pct, n_laps)
               VALUES (?,?,?,?,?,?,?)""",
            (activity_id, row["date"], row.get("duration_min"),
             row.get("first_third_hr"), row.get("final_third_hr"),
             row.get("drift_pct"), row.get("n_laps")),
        )


def load_durability(days: int = 180) -> list[dict]:
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    with _conn() as con:
        _ensure_durability_schema(con)
        rows = con.execute(
            "SELECT * FROM activity_durability WHERE date >= ? ORDER BY date ASC",
            (start,),
        ).fetchall()
    return [dict(r) for r in rows]


def durability_exists(activity_id: int) -> bool:
    with _conn() as con:
        _ensure_durability_schema(con)
        row = con.execute(
            "SELECT 1 FROM activity_durability WHERE activity_id = ?", (activity_id,)
        ).fetchone()
    return row is not None


def get_durability(activity_id: int) -> Optional[dict]:
    """Return the HR-drift durability row for one activity, or None."""
    with _conn() as con:
        _ensure_durability_schema(con)
        row = con.execute(
            "SELECT * FROM activity_durability WHERE activity_id = ?", (activity_id,)
        ).fetchone()
    return dict(row) if row else None


# ── Power durability (Pw:HR decoupling on long rides) ────────────────────────

def save_power_durability(activity_id: int, row: dict) -> None:
    with _conn() as con:
        _ensure_power_durability_schema(con)
        con.execute(
            """INSERT OR REPLACE INTO activity_power_durability
               (activity_id, date, duration_min, first_third_hr, final_third_hr,
                first_third_power, final_third_power, hr_drift_pct, power_drift_pct,
                decoupling_pct, n_laps)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (activity_id, row["date"], row.get("duration_min"),
             row.get("first_third_hr"), row.get("final_third_hr"),
             row.get("first_third_power"), row.get("final_third_power"),
             row.get("hr_drift_pct"), row.get("power_drift_pct"),
             row.get("decoupling_pct"), row.get("n_laps")),
        )


def load_power_durability(days: int = 180) -> list[dict]:
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    with _conn() as con:
        _ensure_power_durability_schema(con)
        rows = con.execute(
            "SELECT * FROM activity_power_durability WHERE date >= ? ORDER BY date ASC",
            (start,),
        ).fetchall()
    return [dict(r) for r in rows]


def power_durability_exists(activity_id: int) -> bool:
    with _conn() as con:
        _ensure_power_durability_schema(con)
        row = con.execute(
            "SELECT 1 FROM activity_power_durability WHERE activity_id = ?", (activity_id,)
        ).fetchone()
    return row is not None


def get_power_durability(activity_id: int) -> Optional[dict]:
    """Return the Pw:HR decoupling row for one activity, or None."""
    with _conn() as con:
        _ensure_power_durability_schema(con)
        row = con.execute(
            "SELECT * FROM activity_power_durability WHERE activity_id = ?", (activity_id,)
        ).fetchone()
    return dict(row) if row else None


# ── Heat / altitude acclimation ──────────────────────────────────────────────

def acclimation_latest() -> Optional[dict]:
    """Most recent daily_metrics row (last 14 days) with any acclimation value."""
    start = (date.today() - timedelta(days=13)).isoformat()
    with _conn() as con:
        _ensure_schema(con)
        row = con.execute(
            """SELECT date, heat_acclimation_pct, altitude_acclimation
               FROM daily_metrics
               WHERE date >= ?
                 AND (heat_acclimation_pct IS NOT NULL OR altitude_acclimation IS NOT NULL)
               ORDER BY date DESC LIMIT 1""",
            (start,),
        ).fetchone()
    return dict(row) if row else None


# ── FTP retest due check ─────────────────────────────────────────────────────

def ftp_retest_due(today: date, max_age_days: int = 42,
                   plan_start: Optional[date] = None) -> Optional[dict]:
    """Return {last_date, age_days} when the newest FTP test is older than
    max_age_days. With an empty table, fires once today > plan_start + 21d
    (only when plan_start is provided)."""
    tests = load_ftp_tests()
    if tests:
        last = tests[-1]
        try:
            last_d = date.fromisoformat(last["date"])
        except Exception:
            return None
        age = (today - last_d).days
        if age > max_age_days:
            return {"last_date": last["date"], "age_days": age}
        return None
    if plan_start is not None and today > plan_start + timedelta(days=21):
        return {"last_date": None, "age_days": None}
    return None

# ── Fuelling compliance logs ─────────────────────────────────────────────────

def save_fuelling_log(log_date: str, activity_id: Optional[int],
                      planned_carbs_g_per_hr: Optional[float],
                      actual_carbs_g_per_hr: Optional[float],
                      fluid_ok: bool, note: Optional[str] = None) -> None:
    with _conn() as con:
        _ensure_fuelling_log_schema(con)
        if activity_id is None:
            # UNIQUE(activity_id) doesn't dedupe NULLs — upsert by date instead
            con.execute(
                "DELETE FROM fuelling_logs WHERE date = ? AND activity_id IS NULL",
                (log_date,),
            )
        con.execute(
            """INSERT OR REPLACE INTO fuelling_logs
               (date, activity_id, planned_carbs_g_per_hr, actual_carbs_g_per_hr, fluid_ok, note)
               VALUES (?,?,?,?,?,?)""",
            (log_date, activity_id, planned_carbs_g_per_hr,
             actual_carbs_g_per_hr, 1 if fluid_ok else 0, note),
        )


def load_fuelling_logs(days: int = 90) -> list[dict]:
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    with _conn() as con:
        _ensure_fuelling_log_schema(con)
        rows = con.execute(
            "SELECT * FROM fuelling_logs WHERE date >= ? ORDER BY date DESC",
            (start,),
        ).fetchall()
    return [dict(r) for r in rows]


def gut_training_summary(target: Optional[date] = None, days: int = 90) -> Optional[dict]:
    """Aggregate in-ride fuelling compliance for charity-prep gut training."""
    from ..plan import CHARITY_DAYS, PLAN_START

    today = target or date.today()
    charity_date = CHARITY_DAYS[0]["date"]
    days_to_charity = (charity_date - today).days
    days_into = (today - PLAN_START).days
    week_num = days_into // 7 + 1 if days_into >= 0 else 0

    if week_num < 7 and days_to_charity > 90:
        return None

    logs = load_fuelling_logs(days)
    sessions: list[dict] = []
    for log in logs:
        planned = log.get("planned_carbs_g_per_hr")
        actual = log.get("actual_carbs_g_per_hr")
        if planned and actual and planned > 0:
            adherence = round(actual / planned * 100, 1)
            sessions.append({
                "date": log["date"],
                "adherence_pct": adherence,
                "hit_80": adherence >= 80,
            })

    week_start = (today - timedelta(days=today.weekday())).isoformat()
    week_sessions = [s for s in sessions if s["date"] >= week_start]
    weekly_pct = None
    if week_sessions:
        weekly_pct = round(sum(s["adherence_pct"] for s in week_sessions) / len(week_sessions))

    sparkline = [
        round(s["adherence_pct"])
        for s in sorted(sessions, key=lambda x: x["date"])[-6:]
    ]

    return {
        "weekly_adherence_pct": weekly_pct,
        "sessions_rehearsed": sum(1 for s in sessions if s["hit_80"]),
        "total_logged": len(sessions),
        "sparkline": sparkline,
        "days_to_charity": days_to_charity,
        "week_num": week_num,
    }


# ── FIT interval analyses ────────────────────────────────────────────────────

def save_interval_analyses(activity_id: int, intervals: list[dict]) -> None:
    import json
    with _conn() as con:
        _ensure_interval_analyses_schema(con)
        con.execute("DELETE FROM interval_analyses WHERE activity_id = ?", (activity_id,))
        for row in intervals:
            step = int(row.get("step_index", row.get("work_num", 0)))
            con.execute(
                "INSERT OR REPLACE INTO interval_analyses (activity_id, step_index, metrics_json) "
                "VALUES (?,?,?)",
                (activity_id, step, json.dumps(row)),
            )


def load_interval_analyses(activity_id: int) -> list[dict]:
    import json
    with _conn() as con:
        _ensure_interval_analyses_schema(con)
        rows = con.execute(
            "SELECT step_index, metrics_json FROM interval_analyses "
            "WHERE activity_id = ? ORDER BY step_index",
            (activity_id,),
        ).fetchall()
    out = []
    for r in rows:
        try:
            m = json.loads(r["metrics_json"])
            m["step_index"] = r["step_index"]
            out.append(m)
        except (ValueError, TypeError):
            pass
    return out


def load_recent_interval_summaries(limit: int = 5) -> list[dict]:
    """Recent activities that have FIT interval rows, newest first."""
    import json
    with _conn() as con:
        _ensure_interval_analyses_schema(con)
        _ensure_activities_schema(con)
        rows = con.execute(
            """
            SELECT DISTINCT a.activity_id, a.date, a.name, a.type_key
            FROM interval_analyses i
            JOIN activities a ON a.activity_id = i.activity_id
            ORDER BY a.date DESC, a.activity_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    result = []
    for r in rows:
        intervals = load_interval_analyses(int(r["activity_id"]))
        result.append({
            "activity_id": r["activity_id"],
            "date": r["date"],
            "name": r["name"],
            "type_key": r["type_key"],
            "intervals": intervals,
        })
    return result


def save_fit_activity_meta(activity_id: int, meta: dict) -> None:
    import json
    with _conn() as con:
        _ensure_fit_meta_schema(con)
        con.execute(
            "INSERT OR REPLACE INTO fit_activity_meta (activity_id, meta_json) VALUES (?,?)",
            (activity_id, json.dumps(meta)),
        )


def load_fit_activity_meta(activity_id: int) -> Optional[dict]:
    import json
    with _conn() as con:
        _ensure_fit_meta_schema(con)
        row = con.execute(
            "SELECT meta_json FROM fit_activity_meta WHERE activity_id = ?",
            (activity_id,),
        ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["meta_json"])
    except (ValueError, TypeError):
        return None


def latest_stale_ftp_flag() -> Optional[dict]:
    """Most recent FIT meta with a stale_ftp proposal (not yet dismissed)."""
    import json
    with _conn() as con:
        _ensure_fit_meta_schema(con)
        rows = con.execute(
            "SELECT activity_id, meta_json FROM fit_activity_meta ORDER BY created_at DESC"
        ).fetchall()
    for r in rows:
        try:
            meta = json.loads(r["meta_json"])
        except (ValueError, TypeError):
            continue
        stale = meta.get("stale_ftp")
        if stale and not meta.get("stale_ftp_accepted") and not meta.get("stale_ftp_dismissed"):
            stale = dict(stale)
            stale["activity_id"] = r["activity_id"]
            stale["activity_date"] = meta.get("activity_date")
            return stale
    return None


def mark_stale_ftp_accepted(activity_id: int) -> None:
    import json
    meta = load_fit_activity_meta(activity_id) or {}
    meta["stale_ftp_accepted"] = True
    save_fit_activity_meta(activity_id, meta)


def observed_max_hr_12m(as_of: Optional[date] = None) -> Optional[int]:
    """Highest activity max_hr in the last 12 months."""
    end = as_of or date.today()
    start = (end - timedelta(days=365)).isoformat()
    with _conn() as con:
        _ensure_activities_schema(con)
        row = con.execute(
            "SELECT MAX(max_hr) AS mx FROM activities WHERE date >= ? AND max_hr IS NOT NULL",
            (start,),
        ).fetchone()
    if row and row["mx"]:
        return int(row["mx"])
    return None


_HR_MAX_REF_KEY = "hr_max_reference"
_HR_MAX_REF_DATE_KEY = "hr_max_reference_date"


def load_hr_max_reference() -> tuple[Optional[int], Optional[date]]:
    import os
    from .text_cache import get_cached_text
    raw = get_cached_text(_HR_MAX_REF_KEY) or os.getenv("HR_MAX_REFERENCE")
    raw_d = get_cached_text(_HR_MAX_REF_DATE_KEY) or os.getenv("HR_MAX_REFERENCE_DATE")
    ref = int(raw) if raw and str(raw).isdigit() else None
    ref_d = None
    if raw_d:
        try:
            ref_d = date.fromisoformat(str(raw_d)[:10])
        except ValueError:
            ref_d = None
    return ref, ref_d


def save_hr_max_reference(hr_max: int, ref_date: str) -> None:
    from .text_cache import set_cached_text
    set_cached_text(_HR_MAX_REF_KEY, str(int(hr_max)))
    set_cached_text(_HR_MAX_REF_DATE_KEY, str(ref_date)[:10])


def latest_hr_calibration() -> Optional[dict]:
    """Most recent FIT meta carrying an hr_calibration block with issues."""
    import json
    with _conn() as con:
        _ensure_fit_meta_schema(con)
        rows = con.execute(
            "SELECT activity_id, meta_json FROM fit_activity_meta ORDER BY created_at DESC"
        ).fetchall()
    for r in rows:
        try:
            meta = json.loads(r["meta_json"])
        except (ValueError, TypeError):
            continue
        cal = meta.get("hr_calibration")
        if cal and cal.get("issues") and not meta.get("hr_calibration_dismissed"):
            cal = dict(cal)
            cal["activity_id"] = r["activity_id"]
            return cal
    return None


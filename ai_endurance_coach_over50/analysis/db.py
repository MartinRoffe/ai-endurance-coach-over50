"""activity_analyses table: schema, save/load, power patching."""
from __future__ import annotations

import json
import sqlite3
from typing import Optional

from ..history import _conn


# ── DB schema ────────────────────────────────────────────────────────────────

def _ensure_analysis_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS activity_analyses (
            activity_id INTEGER PRIMARY KEY,
            hr_zones_json  TEXT,
            training_effect REAL,
            training_effect_label TEXT,
            aerobic_te_message TEXT,
            anaerobic_te REAL,
            training_load REAL,
            avg_respiration REAL,
            analysis_text TEXT,
            analysed_at TEXT DEFAULT (datetime('now'))
        )
    """)
    for col, typ in [
        ("ftp_effort_avg_hr",  "REAL"),
        ("ftp_effort_max_hr",  "REAL"),
        ("ftp_effort_avg_w",   "REAL"),
        ("interval_data_json", "TEXT"),
        ("power_zones_json",   "TEXT"),
    ]:
        try:
            con.execute(f"ALTER TABLE activity_analyses ADD COLUMN {col} {typ}")
        except Exception:
            pass

def save_detail(activity_id: int, detail: dict, analysis_text: str) -> None:
    with _conn() as con:
        _ensure_analysis_schema(con)
        interval_reps = detail.get("interval_reps")
        con.execute(
            """INSERT OR REPLACE INTO activity_analyses
               (activity_id, hr_zones_json, training_effect, training_effect_label,
                aerobic_te_message, anaerobic_te, training_load, avg_respiration,
                analysis_text, ftp_effort_avg_hr, ftp_effort_max_hr, ftp_effort_avg_w,
                interval_data_json, power_zones_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                activity_id,
                json.dumps(detail["hr_zones"]),
                detail.get("training_effect"),
                detail.get("training_effect_label"),
                detail.get("aerobic_te_message"),
                detail.get("anaerobic_te"),
                detail.get("training_load"),
                detail.get("avg_respiration"),
                analysis_text,
                detail.get("ftp_effort_avg_hr"),
                detail.get("ftp_effort_max_hr"),
                detail.get("ftp_effort_avg_w"),
                json.dumps(interval_reps) if interval_reps else None,
                json.dumps(detail["power_zones"]) if detail.get("power_zones") else None,
            ),
        )


def load_analysis(activity_id: int) -> Optional[dict]:
    with _conn() as con:
        _ensure_analysis_schema(con)
        row = con.execute(
            "SELECT * FROM activity_analyses WHERE activity_id = ?",
            (activity_id,),
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["hr_zones"] = json.loads(d["hr_zones_json"]) if d.get("hr_zones_json") else []
    d["interval_reps"] = json.loads(d["interval_data_json"]) if d.get("interval_data_json") else []
    d["power_zones"] = json.loads(d["power_zones_json"]) if d.get("power_zones_json") else []
    return d


def patch_analysis_power(activity_id: int, detail: dict) -> bool:
    """Update power-related columns on an existing analysis row. Returns True if patched."""
    zones_json = json.dumps(detail["power_zones"]) if detail.get("power_zones") else None
    reps_json = json.dumps(detail["interval_reps"]) if detail.get("interval_reps") else None
    if not any((detail.get("ftp_effort_avg_w"), zones_json, reps_json)):
        return False
    with _conn() as con:
        _ensure_analysis_schema(con)
        row = con.execute(
            "SELECT 1 FROM activity_analyses WHERE activity_id = ?", (activity_id,)
        ).fetchone()
        if not row:
            return False
        con.execute(
            """UPDATE activity_analyses SET
                   ftp_effort_avg_w = COALESCE(?, ftp_effort_avg_w),
                   interval_data_json = COALESCE(?, interval_data_json),
                   power_zones_json = COALESCE(?, power_zones_json)
               WHERE activity_id = ?""",
            (detail.get("ftp_effort_avg_w"), reps_json, zones_json, activity_id),
        )
    return True

"""SQLite connection, DB_PATH, and table schema helpers.

Tests patch ``history.db.DB_PATH``; ``_conn()`` reads it at call time,
so nothing else may read DB_PATH directly.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import fields
from pathlib import Path

from ..metrics import DailyMetrics, TEXT_FIELDS


DB_PATH = Path.home() / ".ai_endurance_coach_over50" / "history.db"


NUMERIC_FIELDS = [
    f.name
    for f in fields(DailyMetrics)
    if f.name not in TEXT_FIELDS
]


@contextmanager
def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # timeout: the FastAPI server (threadpool workers) and the launchd CLI can
    # write concurrently — wait out short lock contention instead of raising
    # "database is locked".
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _ensure_schema(con: sqlite3.Connection) -> None:
    # Base create
    numeric_cols = ", ".join(f"{name} REAL" for name in NUMERIC_FIELDS)
    text_extras = ", ".join(
        f"{name} TEXT" for name in TEXT_FIELDS if name != "date"
    )
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS daily_metrics (
            date TEXT PRIMARY KEY,
            {numeric_cols},
            {text_extras},
            recorded_at TEXT DEFAULT (datetime('now'))
        )
    """)
    # Migrate: add any columns missing from older schema versions
    existing = {row[1] for row in con.execute("PRAGMA table_info(daily_metrics)")}
    for name in NUMERIC_FIELDS:
        if name not in existing:
            con.execute(f"ALTER TABLE daily_metrics ADD COLUMN {name} REAL")
    for name in TEXT_FIELDS:
        if name != "date" and name not in existing:
            con.execute(f"ALTER TABLE daily_metrics ADD COLUMN {name} TEXT")


_ACTIVITY_COLS: list[tuple[str, str]] = [
    ("activity_id",            "INTEGER PRIMARY KEY"),
    ("date",                   "TEXT NOT NULL"),
    ("start_time",             "TEXT"),
    ("name",                   "TEXT"),
    ("type_key",               "TEXT"),
    ("duration_seconds",       "REAL"),
    ("distance_meters",        "REAL"),
    ("elevation_gain",         "REAL"),
    ("elevation_loss",         "REAL"),
    ("avg_hr",                 "REAL"),
    ("max_hr",                 "REAL"),
    ("calories",               "REAL"),
    ("avg_speed_ms",           "REAL"),
    ("max_speed_ms",           "REAL"),
    ("moving_duration",        "REAL"),
    ("aerobic_te",             "REAL"),
    ("anaerobic_te",           "REAL"),
    ("training_load",          "REAL"),
    ("training_effect_label",  "TEXT"),
    ("avg_respiration",        "REAL"),
    ("min_temperature",        "REAL"),
    ("max_temperature",        "REAL"),
    ("location_name",          "TEXT"),
    ("vigorous_intensity_min", "INTEGER"),
    ("moderate_intensity_min", "INTEGER"),
    ("hr_zone_1_sec",          "REAL"),
    ("hr_zone_2_sec",          "REAL"),
    ("hr_zone_3_sec",          "REAL"),
    ("hr_zone_4_sec",          "REAL"),
    ("hr_zone_5_sec",          "REAL"),
    ("avg_power_w",            "REAL"),
    ("max_power_w",            "REAL"),
    ("norm_power_w",           "REAL"),
    ("has_power_meter",        "INTEGER"),
    ("tss",                    "REAL"),
    ("intensity_factor",       "REAL"),
]


def _ensure_activities_schema(con: sqlite3.Connection) -> None:
    col_defs = ", ".join(f"{name} {typ}" for name, typ in _ACTIVITY_COLS)
    con.execute(f"CREATE TABLE IF NOT EXISTS activities ({col_defs})")
    existing = {row[1] for row in con.execute("PRAGMA table_info(activities)")}
    for name, typ in _ACTIVITY_COLS:
        if name not in existing and name != "activity_id":
            base_type = typ.split()[0]
            con.execute(f"ALTER TABLE activities ADD COLUMN {name} {base_type}")


def _ensure_body_metrics_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS body_metrics (
            date TEXT PRIMARY KEY,
            weight_kg REAL,
            fat_pct REAL,
            muscle_mass_kg REAL,
            bone_mass_kg REAL,
            hydration_pct REAL,
            visceral_fat REAL,
            bmi REAL,
            metabolic_age REAL,
            recorded_at TEXT DEFAULT (datetime('now'))
        )
    """)


def _ensure_blood_pressure_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS blood_pressure (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            timestamp_local TEXT,
            systolic INTEGER,
            diastolic INTEGER,
            pulse INTEGER,
            recorded_at TEXT DEFAULT (datetime('now')),
            UNIQUE(date, timestamp_local)
        )
    """)


def _ensure_coach_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS coach_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            proposal TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS plan_overrides (
            date TEXT PRIMARY KEY,
            session_type TEXT,
            label TEXT,
            duration_min INTEGER NOT NULL,
            note TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)


def _ensure_coach_memory_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS coach_memory (
            id INTEGER PRIMARY KEY,
            memo TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)


def _ensure_rpe_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS session_rpe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            activity_id INTEGER,
            rpe INTEGER NOT NULL,
            note TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)


def _ensure_ftp_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS ftp_tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            activity_id INTEGER,
            ftp_hr INTEGER,
            ftp_hr_max INTEGER,
            ftp_w INTEGER,
            note TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    existing = {row[1] for row in con.execute("PRAGMA table_info(ftp_tests)")}
    if "ftp_w" not in existing:
        con.execute("ALTER TABLE ftp_tests ADD COLUMN ftp_w INTEGER")


def _ensure_btb_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS btb_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            day_number INTEGER NOT NULL,
            fatigue_rating INTEGER,
            note TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)


def _ensure_durability_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS activity_durability (
            activity_id INTEGER PRIMARY KEY,
            date TEXT NOT NULL,
            duration_min INTEGER,
            first_third_hr REAL,
            final_third_hr REAL,
            drift_pct REAL,
            n_laps INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)


def _ensure_power_durability_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS activity_power_durability (
            activity_id INTEGER PRIMARY KEY,
            date TEXT NOT NULL,
            duration_min INTEGER,
            first_third_hr REAL,
            final_third_hr REAL,
            first_third_power REAL,
            final_third_power REAL,
            hr_drift_pct REAL,
            power_drift_pct REAL,
            decoupling_pct REAL,
            n_laps INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)


def _ensure_interval_analyses_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS interval_analyses (
            activity_id INTEGER NOT NULL,
            step_index INTEGER NOT NULL,
            metrics_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (activity_id, step_index)
        )
    """)


def _ensure_fit_meta_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS fit_activity_meta (
            activity_id INTEGER PRIMARY KEY,
            meta_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)


def _ensure_climb_analyses_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS climb_analyses (
            activity_id INTEGER NOT NULL,
            climb_index INTEGER NOT NULL,
            metrics_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (activity_id, climb_index)
        )
    """)


def _ensure_named_climbs_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS named_climbs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            notes TEXT,
            ref_start_lat REAL,
            ref_start_lon REAL,
            ref_end_lat REAL,
            ref_end_lon REAL,
            ref_length_m REAL,
            ref_gain_m REAL,
            ref_avg_grade REAL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS climb_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            named_climb_id INTEGER NOT NULL,
            activity_id INTEGER NOT NULL,
            climb_index INTEGER NOT NULL,
            date TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            is_pb_vam INTEGER NOT NULL DEFAULT 0,
            is_pb_time INTEGER NOT NULL DEFAULT 0,
            is_pb_wkg INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE (named_climb_id, activity_id, climb_index),
            FOREIGN KEY (named_climb_id) REFERENCES named_climbs(id)
        )
    """)


def _ensure_commitments_schema(con: sqlite3.Connection) -> None:
    """Durable coach commitments: checkpoints, guardrails and decision rules
    agreed in coach chat. Unlike coach_memory (a lossy summary), these survive
    verbatim and are re-injected into the coach context until resolved."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS coach_commitments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_date TEXT NOT NULL,
            review_date TEXT,
            title TEXT NOT NULL,
            decision_rule TEXT,
            baseline TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            resolution TEXT,
            resolved_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)


def _ensure_session_notes_schema(con: sqlite3.Connection) -> None:
    """Per-date coaching notes (e.g. 'keep genuinely easy — FTP test Wednesday').
    Rendered on calendar tiles via the existing COACH_NOTES hook in plan.py."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS session_notes (
            date TEXT PRIMARY KEY,
            note TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)


def _ensure_fuelling_log_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS fuelling_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            activity_id INTEGER UNIQUE,
            planned_carbs_g_per_hr REAL,
            actual_carbs_g_per_hr REAL,
            fluid_ok INTEGER,
            note TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

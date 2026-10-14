#!/usr/bin/env python3
"""Stage 1 — resumable Garmin activity metadata extraction (2009–2016).

Caches raw monthly JSON under archive/raw/ before parsing, rate-limits between
pages, and flattens to activities_YYYY_YYYY.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator, Optional

ARCHIVE_DIR = Path(__file__).resolve().parent
RAW_DIR = ARCHIVE_DIR / "raw"
CHECKPOINT_PATH = ARCHIVE_DIR / "checkpoint.json"

DEFAULT_START = date(2009, 1, 1)
DEFAULT_END = date(2016, 12, 31)
SLEEP_BETWEEN_MONTHS = 1.75
MAX_BACKOFF = 600

CSV_COLUMNS = [
    "activity_id",
    "date",
    "name",
    "sport",
    "sub_sport",
    "duration_s",
    "distance_m",
    "elevation_gain_m",
    "avg_power",
    "max_power",
    "normalized_power",
    "max_power_20min",
    "avg_hr",
    "max_hr",
    "avg_cadence",
    "avg_speed_ms",
    "tss",
    "intensity_factor",
    "calories",
    "aerobic_te",
    "has_power_meter",
    "device_name",
]


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = os.getenv("DOTENV_PATH")
    if env_path:
        load_dotenv(env_path)
    else:
        load_dotenv()
        fallback = Path.home() / ".ai_endurance_coach_over50" / ".env"
        if fallback.is_file():
            load_dotenv(fallback, override=False)


def _month_windows(start: date, end: date) -> Iterator[tuple[date, date]]:
    y, m = start.year, start.month
    while True:
        first = date(y, m, 1)
        last_day = monthrange(y, m)[1]
        last = date(y, m, last_day)
        win_start = max(first, start)
        win_end = min(last, end)
        if win_start <= win_end:
            yield win_start, win_end
        if last >= end:
            break
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1


def _raw_path(win_start: date) -> Path:
    return RAW_DIR / f"{win_start.year:04d}-{win_start.month:02d}.json"


def _load_checkpoint() -> dict[str, Any]:
    if CHECKPOINT_PATH.is_file():
        try:
            return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_checkpoint(data: dict[str, Any]) -> None:
    CHECKPOINT_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _is_throttle(exc: BaseException) -> bool:
    msg = str(exc).lower()
    name = type(exc).__name__.lower()
    return (
        "429" in msg
        or "rate" in msg
        or "throttl" in msg
        or "too many" in msg
        or "429" in name
    )


def _fetch_month(api: Any, win_start: date, win_end: date) -> list[dict]:
    start_s = win_start.isoformat()
    end_s = win_end.isoformat()
    backoff = 30.0
    while True:
        try:
            raw = api.get_activities_by_date(start_s, end_s) or []
            if not isinstance(raw, list):
                raw = list(raw) if raw else []
            return raw
        except Exception as e:
            if _is_throttle(e):
                print(
                    f"  throttle/429 on {start_s}…{end_s}: {e}; "
                    f"backing off {backoff:.0f}s",
                    flush=True,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
                continue
            print(f"  ERROR fetching {start_s}…{end_s}: {e}", flush=True)
            raise


def _first(*vals: Any) -> Any:
    for v in vals:
        if v is not None and v != "":
            return v
    return None


def _num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _flatten_activity(a: dict) -> Optional[dict[str, Any]]:
    try:
        act_type = a.get("activityType") or {}
        if not isinstance(act_type, dict):
            act_type = {}
        parent = act_type.get("parentTypeId") or act_type.get("typeKey")
        sport = act_type.get("typeKey") or a.get("activityTypeDTO", {}).get("typeKey") or ""
        if isinstance(parent, dict):
            parent = parent.get("typeKey")

        start_local = a.get("startTimeLocal") or a.get("startTimeGMT") or ""
        act_date = str(start_local)[:10] if start_local else ""

        avg_p = _num(_first(a.get("averagePower"), a.get("avgPower")))
        max_p = _num(_first(a.get("maxPower"), a.get("maximumPower")))
        np_v = _num(_first(a.get("normativePower"), a.get("normalizedPower"), a.get("normPower")))
        has_pm = a.get("hasPowerMeter")
        if has_pm is None:
            has_pm = (avg_p is not None and avg_p > 0) or (max_p is not None and max_p > 0)

        device = _first(
            a.get("deviceName"),
            (a.get("deviceDto") or {}).get("deviceName") if isinstance(a.get("deviceDto"), dict) else None,
            a.get("deviceId"),
        )

        return {
            "activity_id": a.get("activityId") or a.get("activityIdPk"),
            "date": act_date,
            "name": a.get("activityName") or a.get("name") or "",
            "sport": sport or "",
            "sub_sport": parent or "",
            "duration_s": _num(_first(a.get("duration"), a.get("elapsedDuration"), a.get("movingDuration"))),
            "distance_m": _num(a.get("distance")),
            "elevation_gain_m": _num(a.get("elevationGain")),
            "avg_power": avg_p,
            "max_power": max_p,
            "normalized_power": np_v,
            "max_power_20min": _num(a.get("maxPowerTwentyMinutes")),
            "avg_hr": _num(_first(a.get("averageHR"), a.get("avgHR"))),
            "max_hr": _num(_first(a.get("maxHR"), a.get("maximumHR"))),
            "avg_cadence": _num(
                _first(
                    a.get("averageBikingCadenceInRevPerMinute"),
                    a.get("averageCadence"),
                    a.get("avgBikeCadence"),
                )
            ),
            "avg_speed_ms": _num(a.get("averageSpeed")),
            "tss": _num(a.get("activityTrainingLoad")),
            "intensity_factor": _num(_first(a.get("intensityFactor"), a.get("if"))),
            "calories": _num(a.get("calories")),
            "aerobic_te": _num(a.get("aerobicTrainingEffect")),
            "has_power_meter": 1 if has_pm else 0,
            "device_name": device or "",
        }
    except Exception as e:
        print(f"  skip malformed activity: {e}", flush=True)
        return None


def flatten_raw_files(start: date, end: date, out_csv: Path) -> int:
    rows: list[dict] = []
    seen: set[Any] = set()
    for win_start, win_end in _month_windows(start, end):
        path = _raw_path(win_start)
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  warn: cannot read {path.name}: {e}", flush=True)
            continue
        activities = payload.get("activities") if isinstance(payload, dict) else payload
        if not isinstance(activities, list):
            continue
        for a in activities:
            if not isinstance(a, dict):
                continue
            flat = _flatten_activity(a)
            if flat is None or flat.get("activity_id") is None:
                continue
            aid = flat["activity_id"]
            if aid in seen:
                continue
            seen.add(aid)
            # Keep only rows that fall inside the requested window (month files may overlap)
            d = flat.get("date") or ""
            if len(d) >= 10:
                try:
                    ad = date.fromisoformat(d[:10])
                    if ad < start or ad > end:
                        continue
                except ValueError:
                    pass
            rows.append(flat)

    rows.sort(key=lambda r: (r.get("date") or "", r.get("activity_id") or 0))
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return len(rows)


def run(start: date, end: date, force: bool = False) -> Path:
    _load_dotenv()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    email = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")
    if not email or not password:
        sys.exit("GARMIN_EMAIL and GARMIN_PASSWORD must be set")

    # Import after dotenv so package path resolves under project venv
    sys.path.insert(0, str(ARCHIVE_DIR.parent))
    from ai_endurance_coach_over50.client import get_api

    print(f"Logging in to Garmin as {email}…", flush=True)
    api = get_api(email, password)
    print("Logged in.", flush=True)

    ckpt = _load_checkpoint()
    completed = set(ckpt.get("completed_months") or [])

    windows = list(_month_windows(start, end))
    print(f"Fetching {len(windows)} month window(s) {start} → {end}", flush=True)

    for i, (win_start, win_end) in enumerate(windows, 1):
        key = f"{win_start.year:04d}-{win_start.month:02d}"
        path = _raw_path(win_start)
        if path.is_file() and not force:
            try:
                n = len(json.loads(path.read_text(encoding="utf-8")).get("activities") or [])
            except Exception:
                n = "?"
            print(f"[{i}/{len(windows)}] {key}: {n} activities (cached)", flush=True)
            completed.add(key)
            continue

        print(f"[{i}/{len(windows)}] {key}: fetching {win_start}…{win_end}…", flush=True)
        activities = _fetch_month(api, win_start, win_end)
        payload = {
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "window_start": win_start.isoformat(),
            "window_end": win_end.isoformat(),
            "count": len(activities),
            "activities": activities,
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)
        completed.add(key)
        ckpt["completed_months"] = sorted(completed)
        ckpt["last_month"] = key
        ckpt["updated_at"] = datetime.now().isoformat(timespec="seconds")
        _save_checkpoint(ckpt)
        print(f"[{i}/{len(windows)}] {key}: {len(activities)} activities (fetched)", flush=True)
        if i < len(windows):
            time.sleep(SLEEP_BETWEEN_MONTHS)

    out_name = f"activities_{start.year}_{end.year}.csv"
    if start == DEFAULT_START and end == DEFAULT_END:
        out_name = "activities_2009_2016.csv"
    out_csv = ARCHIVE_DIR / out_name
    n = flatten_raw_files(start, end, out_csv)
    print(f"Wrote {n} activities → {out_csv}", flush=True)
    return out_csv


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", default=DEFAULT_START.isoformat(), help="YYYY-MM-DD")
    p.add_argument("--end", default=DEFAULT_END.isoformat(), help="YYYY-MM-DD")
    p.add_argument("--force", action="store_true", help="Re-fetch months even if cached")
    args = p.parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if end < start:
        sys.exit("--end must be on or after --start")
    run(start, end, force=args.force)


if __name__ == "__main__":
    main()

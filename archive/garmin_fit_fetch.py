#!/usr/bin/env python3
"""Stage 3a — resumable FIT download for archive/shortlist_v2.csv activity IDs.

Falls back to Garmin TCX export → archive/streams/{id}.json when ORIGINAL/FIT
is unavailable (common for pre-ORIGINAL Edge-era rides).
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ARCHIVE_DIR = Path(__file__).resolve().parent
SHORTLIST_PATH = ARCHIVE_DIR / "shortlist_v2.csv"
SHORTLIST_FALLBACK = ARCHIVE_DIR / "shortlist.csv"
FITS_DIR = ARCHIVE_DIR / "fits"
STREAMS_DIR = ARCHIVE_DIR / "streams"
CHECKPOINT_PATH = ARCHIVE_DIR / "fits_checkpoint.json"

SLEEP_BETWEEN = 2.0
MAX_BACKOFF = 600


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


def _load_checkpoint() -> dict[str, Any]:
    if CHECKPOINT_PATH.is_file():
        try:
            return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_checkpoint(data: dict[str, Any]) -> None:
    CHECKPOINT_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_shortlist(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        if path == SHORTLIST_PATH and SHORTLIST_FALLBACK.is_file():
            path = SHORTLIST_FALLBACK
            print(f"Warn: shortlist_v2 missing — using {path}", flush=True)
        else:
            sys.exit(f"Shortlist not found: {path} — run shortlist_select.py first")
    rows = []
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            aid = (row.get("activity_id") or "").strip()
            if aid:
                rows.append(row)
    return rows


def fit_path(activity_id: Any) -> Path:
    return FITS_DIR / f"{activity_id}.fit"


def stream_path(activity_id: Any) -> Path:
    return STREAMS_DIR / f"{activity_id}.json"


def _tcx_ingest():
    spec = importlib.util.spec_from_file_location(
        "tcx_ingest", ARCHIVE_DIR / "tcx_ingest.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _download_fit(api: Any, activity_id: int) -> Optional[bytes]:
    """Download FIT with throttle retries. Returns bytes or None on soft failure."""
    sys.path.insert(0, str(ARCHIVE_DIR.parent))
    from ai_endurance_coach_over50.analysis.fit_ingest import fetch_fit_for_activity

    backoff = 30.0
    while True:
        try:
            return fetch_fit_for_activity(api, activity_id)
        except Exception as e:
            if _is_throttle(e):
                print(
                    f"  throttle on FIT {activity_id}: {e}; backing off {backoff:.0f}s",
                    flush=True,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
                continue
            print(f"  ERROR FIT download {activity_id}: {e}", flush=True)
            return None


def _download_tcx(api: Any, activity_id: int) -> Optional[bytes]:
    sys.path.insert(0, str(ARCHIVE_DIR.parent))
    from ai_endurance_coach_over50.analysis.fit_ingest import fetch_tcx_for_activity

    backoff = 30.0
    while True:
        try:
            return fetch_tcx_for_activity(api, activity_id)
        except Exception as e:
            if _is_throttle(e):
                print(
                    f"  throttle on TCX {activity_id}: {e}; backing off {backoff:.0f}s",
                    flush=True,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
                continue
            print(f"  ERROR TCX download {activity_id}: {e}", flush=True)
            return None


def _has_usable_stream(activity_id: int) -> bool:
    p = stream_path(activity_id)
    if not p.is_file() or p.stat().st_size < 50:
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return int(data.get("n_powered") or 0) >= 5
    except Exception:
        return False


def run(
    shortlist: Path = SHORTLIST_PATH,
    force: bool = False,
    limit: Optional[int] = None,
    ids: Optional[list[int]] = None,
    retry_failed: bool = False,
    tcx_fallback: bool = True,
) -> None:
    _load_dotenv()
    FITS_DIR.mkdir(parents=True, exist_ok=True)
    STREAMS_DIR.mkdir(parents=True, exist_ok=True)

    email = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")
    if not email or not password:
        sys.exit("GARMIN_EMAIL and GARMIN_PASSWORD must be set")

    rows = read_shortlist(shortlist)
    ckpt = _load_checkpoint()
    completed = set(str(x) for x in (ckpt.get("completed") or []))
    failed = {str(k): v for k, v in (ckpt.get("failed") or {}).items()}
    tcx_ok = set(str(x) for x in (ckpt.get("tcx_completed") or []))

    if ids:
        id_set = {str(i) for i in ids}
        rows = [r for r in rows if str(int(float(r["activity_id"]))) in id_set
                or str(r.get("activity_id")) in id_set]
    elif retry_failed:
        rows = [r for r in rows if str(int(float(r["activity_id"]))) in failed]

    if limit is not None:
        rows = rows[:limit]

    if not rows:
        sys.exit("No activity IDs to fetch")

    sys.path.insert(0, str(ARCHIVE_DIR.parent))
    from ai_endurance_coach_over50.client import get_api

    print(f"Logging in to Garmin as {email}…", flush=True)
    api = get_api(email, password)
    print(
        f"Logged in. Fetching {len(rows)} activit(y/ies) "
        f"(FIT → {FITS_DIR}; TCX fallback → {STREAMS_DIR})",
        flush=True,
    )

    tcx_mod = _tcx_ingest() if tcx_fallback else None
    n_fit = n_tcx = n_fail = 0

    for i, row in enumerate(rows, 1):
        aid_s = str(row["activity_id"])
        try:
            aid = int(float(aid_s))
        except ValueError:
            print(f"[{i}/{len(rows)}] bad id {aid_s} — skip", flush=True)
            continue
        aid_key = str(aid)

        dest = fit_path(aid)
        if dest.is_file() and dest.stat().st_size > 5000 and not force:
            print(f"[{i}/{len(rows)}] {aid}: FIT cached ({dest.stat().st_size} B)", flush=True)
            completed.add(aid_key)
            failed.pop(aid_key, None)
            n_fit += 1
            continue

        if not force and _has_usable_stream(aid):
            print(f"[{i}/{len(rows)}] {aid}: stream cached", flush=True)
            completed.add(aid_key)
            tcx_ok.add(aid_key)
            failed.pop(aid_key, None)
            n_tcx += 1
            continue

        print(
            f"[{i}/{len(rows)}] {aid} ({row.get('date', '')}): downloading FIT…",
            flush=True,
        )
        data = _download_fit(api, aid)
        if data and len(data) > 5000:
            tmp = dest.with_suffix(".fit.tmp")
            tmp.write_bytes(data)
            tmp.replace(dest)
            completed.add(aid_key)
            failed.pop(aid_key, None)
            ckpt["completed"] = sorted(completed)
            ckpt["tcx_completed"] = sorted(tcx_ok)
            ckpt["failed"] = failed
            ckpt["updated_at"] = datetime.now().isoformat(timespec="seconds")
            _save_checkpoint(ckpt)
            print(f"[{i}/{len(rows)}] {aid}: wrote {dest.name} ({len(data)} B)", flush=True)
            n_fit += 1
            if i < len(rows):
                time.sleep(SLEEP_BETWEEN)
            continue

        # Tiny/empty FIT — don't keep as success
        if dest.is_file() and dest.stat().st_size <= 5000:
            dest.unlink(missing_ok=True)

        if not tcx_fallback or tcx_mod is None:
            print(f"[{i}/{len(rows)}] {aid}: FAILED (no ORIGINAL / empty)", flush=True)
            failed[aid_key] = "download_failed"
            n_fail += 1
        else:
            print(f"[{i}/{len(rows)}] {aid}: no FIT — trying TCX…", flush=True)
            time.sleep(SLEEP_BETWEEN)
            tcx_raw = _download_tcx(api, aid)
            if not tcx_raw:
                print(f"[{i}/{len(rows)}] {aid}: FAILED (no FIT, no TCX)", flush=True)
                failed[aid_key] = "fit_and_tcx_failed"
                n_fail += 1
            else:
                out = tcx_mod.ingest_tcx_bytes(aid, tcx_raw, source="garmin_tcx")
                if out is None:
                    print(
                        f"[{i}/{len(rows)}] {aid}: TCX saved but no power samples",
                        flush=True,
                    )
                    failed[aid_key] = "tcx_no_power"
                    n_fail += 1
                else:
                    print(
                        f"[{i}/{len(rows)}] {aid}: wrote stream {out.name} "
                        f"(from Garmin TCX, {len(tcx_raw)} B)",
                        flush=True,
                    )
                    completed.add(aid_key)
                    tcx_ok.add(aid_key)
                    failed.pop(aid_key, None)
                    n_tcx += 1

        ckpt["completed"] = sorted(completed)
        ckpt["tcx_completed"] = sorted(tcx_ok)
        ckpt["failed"] = failed
        ckpt["updated_at"] = datetime.now().isoformat(timespec="seconds")
        _save_checkpoint(ckpt)
        if i < len(rows):
            time.sleep(SLEEP_BETWEEN)

    print(
        f"Done. fit_ok≈{n_fit} tcx_stream_ok≈{n_tcx} failed={len(failed)} "
        f"(this run fail events={n_fail}) fits={FITS_DIR}",
        flush=True,
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--shortlist", type=Path, default=SHORTLIST_PATH)
    p.add_argument("--force", action="store_true", help="Re-download even if cached")
    p.add_argument("--limit", type=int, default=None, help="Only first N shortlist rows")
    p.add_argument(
        "--ids",
        type=str,
        default=None,
        help="Comma-separated activity IDs (subset of shortlist)",
    )
    p.add_argument(
        "--retry-failed",
        action="store_true",
        help="Only re-attempt IDs currently in fits_checkpoint.json failed map",
    )
    p.add_argument(
        "--no-tcx-fallback",
        action="store_true",
        help="Do not fall back to Garmin TCX → streams",
    )
    args = p.parse_args()
    id_list = None
    if args.ids:
        id_list = [int(x.strip()) for x in args.ids.split(",") if x.strip()]
    run(
        shortlist=args.shortlist,
        force=args.force,
        limit=args.limit,
        ids=id_list,
        retry_failed=args.retry_failed,
        tcx_fallback=not args.no_tcx_fallback,
    )


if __name__ == "__main__":
    main()

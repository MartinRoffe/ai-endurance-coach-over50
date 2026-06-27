"""One-off cleanup for doubled-up Garmin Connect plan workouts.

The bulk "Sync to Watch" used to only delete library templates, never the
scheduled calendar entries, so each re-sync stacked a second copy on every plan
day. This script unschedules all plan-generated calendar entries in a date range
(athlete's own workouts are left alone — only titles matching the plan name
prefixes are touched), then optionally runs one clean re-sync.

Usage:
    python cleanup_duplicate_workouts.py                 # dry-run, 2026-06-30..2026-08-09
    python cleanup_duplicate_workouts.py --apply         # actually unschedule
    python cleanup_duplicate_workouts.py --apply --resync # unschedule + one clean re-sync
    python cleanup_duplicate_workouts.py --start 2026-06-30 --end 2026-08-09 --apply
"""
from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from ai_endurance_coach_over50.client import get_api
from ai_endurance_coach_over50.workouts import (
    unschedule_plan_workouts_in_range,
    upload_and_schedule,
)

# Default window: Tue 30 Jun 2026 → end of the 12-week plan (PLAN_START 2026-05-18 + 83d).
DEFAULT_START = date(2026, 6, 30)
DEFAULT_END = date(2026, 8, 9)


def _load_env() -> None:
    env_path = os.getenv("DOTENV_PATH")
    if env_path:
        load_dotenv(env_path)
        return
    load_dotenv()
    fallback = Path.home() / ".ai_endurance_coach_over50" / ".env"
    if fallback.exists():
        load_dotenv(fallback, override=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START,
                        help="Start date YYYY-MM-DD (inclusive)")
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_END,
                        help="End date YYYY-MM-DD (inclusive)")
    parser.add_argument("--apply", action="store_true",
                        help="Actually unschedule (default is dry-run)")
    parser.add_argument("--resync", action="store_true",
                        help="After clearing, run one clean re-sync of all plan workouts")
    args = parser.parse_args()

    _load_env()
    email = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")
    if not (email and password):
        raise SystemExit("GARMIN_EMAIL / GARMIN_PASSWORD not set — check your .env")

    api = get_api(email, password)

    dry_run = not args.apply
    mode = "DRY-RUN (no changes)" if dry_run else "APPLY"
    print(f"=== Cleanup {args.start.isoformat()}..{args.end.isoformat()} — {mode} ===")
    result = unschedule_plan_workouts_in_range(api, args.start, args.end, dry_run=dry_run)
    print(f"\nSummary: found={result['found']} unscheduled={result['unscheduled']} "
          f"errors={result['errors']}")

    if args.resync:
        if dry_run:
            print("\n[skip] --resync ignored in dry-run; re-run with --apply --resync")
        else:
            print("\n=== Clean re-sync ===")
            summary = upload_and_schedule(api)
            print(f"\nRe-sync summary: {summary}")


if __name__ == "__main__":
    main()

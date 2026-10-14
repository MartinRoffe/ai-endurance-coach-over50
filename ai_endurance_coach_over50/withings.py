"""Sync Withings measurements to Garmin Connect and local SQLite."""
from __future__ import annotations

import calendar
import logging
from datetime import date, timedelta
from typing import Any

from .paths import data_dir

logger = logging.getLogger(__name__)


def withings_config_dir():
    """Withings OAuth files. Resolved at call time so tests can redirect them."""
    return data_dir() / "withings"


def _record(ok: bool, error: str | None = None, detail: str | None = None) -> None:
    try:
        from .history.sync_status import record_sync
        record_sync("withings", ok=ok, error=error, detail=detail)
    except Exception:
        logger.exception("could not record Withings sync status")


def _to_unix(d: date) -> int:
    return calendar.timegm(d.timetuple())


def sync_withings_to_garmin(api: Any, days: int = 30) -> bool:
    """Fetch recent Withings measurements, push to Garmin Connect, and save locally.

    Uses add_body_composition() and set_blood_pressure() directly —
    the correct Garmin endpoints, not the activity upload endpoint.
    Also writes the data directly to SQLite so body metrics are immediately
    available without waiting for Garmin's API to propagate.

    Requires withings-sync to be installed: pip install withings-sync
    On first run, Withings OAuth requires an interactive browser step —
    run this manually once from the terminal before scheduling.

    Returns True if any data was uploaded.
    """
    try:
        from withings_sync.withings2 import WithingsAccount
    except ImportError:
        # Optional. Do not record a failure — a Garmin-only setup would
        # otherwise show a permanent Withings banner.
        logger.warning("withings-sync not installed — run: pip install withings-sync")
        return False

    config_dir = withings_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_folder = str(config_dir)

    # Silence the "app config not found" warning by copying the bundled config once
    app_cfg = config_dir / "withings_app.json"
    if not app_cfg.exists():
        try:
            from withings_sync.withings2 import APP_CONFIG
            import shutil
            shutil.copy2(APP_CONFIG, app_cfg)
        except Exception:
            logger.exception("could not copy Withings app config")

    try:
        withings = WithingsAccount(config_folder=config_folder)
    except Exception as e:
        logger.exception("Withings auth failed")
        _record(False, error=f"{type(e).__name__}: {e}")
        return False

    end = date.today() + timedelta(days=1)  # end-of-today inclusive
    start = end - timedelta(days=days)

    try:
        groups = withings.get_measurements(
            startdate=_to_unix(start),
            enddate=_to_unix(end),
        )
        height = withings.get_height()
    except Exception as e:
        logger.exception("Withings fetch failed")
        _record(False, error=f"{type(e).__name__}: {e}")
        return False

    if not groups:
        logger.info("No Withings measurements in the last %d days", days)
        _record(True, detail="no measurements")
        return False

    body_records = []
    bp_records = []

    for group in groups:
        dt = group.get_datetime()
        ts = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
        cal_date = ts[:10]

        if group.get_weight():
            w = group.get_weight()
            hydration = group.get_hydration()
            fat_ratio = group.get_fat_ratio()
            muscle = group.get_muscle_mass()
            bone = group.get_bone_mass()
            bmi = round(w / (height ** 2), 1) if height else None
            percent_hydration = (hydration / w * 100) if hydration and w else None

            try:
                api.add_body_composition(
                    timestamp=ts,
                    weight=w,
                    percent_fat=fat_ratio,
                    percent_hydration=percent_hydration,
                    bone_mass=bone,
                    muscle_mass=muscle,
                    bmi=bmi,
                )
            except Exception:
                logger.exception("Body composition upload to Garmin failed for %s", ts)

            body_records.append({
                "date": cal_date,
                "weight_kg": w,
                "fat_pct": float(fat_ratio) if fat_ratio is not None else None,
                "muscle_mass_kg": muscle,
                "bone_mass_kg": bone,
                "hydration_pct": percent_hydration,
                "visceral_fat": None,
                "bmi": bmi,
                "metabolic_age": None,
            })

        if group.get_diastolic_blood_pressure():
            systolic = group.get_systolic_blood_pressure()
            diastolic = group.get_diastolic_blood_pressure()
            pulse = group.get_heart_pulse()

            try:
                api.set_blood_pressure(
                    systolic=int(systolic),
                    diastolic=int(diastolic),
                    pulse=int(pulse) if pulse else 0,
                    timestamp=ts,
                )
            except Exception:
                logger.exception("Blood pressure upload to Garmin failed for %s", ts)

            bp_records.append({
                "date": cal_date,
                "timestamp_local": ts,
                "systolic": int(systolic),
                "diastolic": int(diastolic),
                "pulse": int(pulse) if pulse else None,
            })

    # Save directly to SQLite — don't rely on Garmin's API propagation timing.
    # Deduplicate by date: keep the latest record that has body composition data,
    # falling back to the latest weight-only record. Groups come newest-first from
    # the Withings API, so iterating in reverse gives us oldest-first; the last
    # write per date (newest with fat_pct) wins via INSERT OR REPLACE.
    if body_records:
        from .history import save_body_metrics
        # Sort: fat_pct=None rows first, non-None rows last, so INSERT OR REPLACE
        # ends on the most complete record.
        body_records.sort(key=lambda r: r["fat_pct"] is not None)
        save_body_metrics(body_records)
        logger.info("Withings: saved %d body composition records to SQLite", len(body_records))

    if bp_records:
        from .history import save_blood_pressure
        save_blood_pressure(bp_records)
        logger.info("Withings: saved %d blood pressure records to SQLite", len(bp_records))

    synced = bool(body_records or bp_records)
    if synced:
        try:
            withings.set_lastsync()
        except Exception:
            logger.exception("Withings set_lastsync failed")
        _record(True, detail=f"body={len(body_records)} bp={len(bp_records)}")
    else:
        _record(True, detail="nothing to upload")

    return synced

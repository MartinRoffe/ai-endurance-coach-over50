"""Last Garmin / Withings sync result, and whether stored data is stale.

A sync failure is recorded even when cached rows are still inside the freshness
window, so the dashboard and the daily email can say the latest attempt failed.
Data older than 24 hours is reported from ``daily_metrics.recorded_at`` (UTC),
which ``save()`` refreshes on every successful write.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from .db import _conn, _ensure_schema

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(hours=24)
_TS_FMT = "%Y-%m-%d %H:%M:%S"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fmt(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime(_TS_FMT)


def _parse(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    text = str(raw).strip()
    if len(text) >= 19 and text[10] == " ":
        try:
            return datetime.strptime(text[:19], _TS_FMT).replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if len(text) >= 10:
        try:
            day = datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
        # Date-only rows have no clock time. Treat them as the end of that UTC
        # day so a row dated yesterday is not flagged at 00:30.
        return day + timedelta(hours=23, minutes=59, seconds=59)
    return None


def _short_error(exc: BaseException, limit: int = 180) -> str:
    text = f"{type(exc).__name__}: {exc}".replace("\n", " ").strip()
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def _ensure_sync_schema(con) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_status (
            source TEXT PRIMARY KEY,
            attempted_at TEXT NOT NULL,
            ok INTEGER NOT NULL,
            error TEXT,
            detail TEXT
        )
        """
    )


def record_sync(
    source: str,
    *,
    ok: bool,
    error: Optional[str] = None,
    detail: Optional[str] = None,
    attempted_at: Optional[datetime] = None,
) -> None:
    """Upsert the latest attempt for ``garmin`` or ``withings``."""
    when = attempted_at or _utcnow()
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    err = (error or "").replace("\n", " ").strip() or None
    if err and len(err) > 300:
        err = err[:299] + "…"
    with _conn() as con:
        _ensure_sync_schema(con)
        con.execute(
            """
            INSERT INTO sync_status (source, attempted_at, ok, error, detail)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                attempted_at = excluded.attempted_at,
                ok = excluded.ok,
                error = excluded.error,
                detail = excluded.detail
            """,
            (source, _fmt(when), 1 if ok else 0, err, detail),
        )


def sync_garmin_metrics(api, target):
    """Fetch one day from Garmin and store it. Re-raises after recording."""
    from ..metrics import fetch_metrics
    from .metrics_store import save

    try:
        metrics = fetch_metrics(api, target)
        save(metrics)
        record_sync("garmin", ok=True, detail=target.isoformat())
        return metrics
    except Exception as exc:
        logger.exception("Garmin sync failed for %s", getattr(target, "isoformat", lambda: target)())
        try:
            record_sync(
                "garmin",
                ok=False,
                error=_short_error(exc),
                detail=getattr(target, "isoformat", lambda: str(target))(),
            )
        except Exception:
            logger.exception("could not record Garmin sync failure")
        raise


def _latest_row(con, source: str) -> Optional[dict]:
    _ensure_sync_schema(con)
    row = con.execute(
        "SELECT * FROM sync_status WHERE source = ?",
        (source,),
    ).fetchone()
    return dict(row) if row else None


def _latest_garmin_saved(con) -> Optional[datetime]:
    _ensure_schema(con)
    cols = {r[1] for r in con.execute("PRAGMA table_info(daily_metrics)")}
    if not cols:
        return None
    if "recorded_at" in cols:
        row = con.execute(
            "SELECT MAX(recorded_at) AS ts FROM daily_metrics WHERE recorded_at IS NOT NULL"
        ).fetchone()
        parsed = _parse(row["ts"] if row else None)
        if parsed is not None:
            return parsed
    row = con.execute("SELECT MAX(date) AS d FROM daily_metrics").fetchone()
    return _parse(row["d"] if row else None)


def _age_phrase(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "0h"
    hours = seconds // 3600
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24}d"


def freshness_warnings(now: Optional[datetime] = None) -> list[dict]:
    """Notices for the dashboard banner and the daily email.

    Each item is ``{source, kind, message}``. ``kind`` is ``failed``, ``stale``,
    or ``missing``. Withings is mentioned only after a sync has been attempted
    (no row means Withings is not in use).
    """
    moment = now or _utcnow()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    else:
        moment = moment.astimezone(timezone.utc)

    notes: list[dict] = []
    try:
        with _conn() as con:
            garmin = _latest_row(con, "garmin")
            saved = _latest_garmin_saved(con)
            withings = _latest_row(con, "withings")
    except Exception:
        logger.exception("freshness check failed")
        return notes

    if garmin and not garmin.get("ok"):
        when = garmin.get("attempted_at") or "unknown time"
        err = garmin.get("error") or "unknown error"
        notes.append({
            "source": "garmin",
            "kind": "failed",
            "message": (
                f"Last Garmin sync failed at {when} UTC ({err}). "
                "Coaching may be using older data."
            ),
        })

    if saved is None:
        notes.append({
            "source": "garmin",
            "kind": "missing",
            "message": "No Garmin data is stored yet — a sync has not succeeded.",
        })
    else:
        age = moment - saved
        if age > STALE_AFTER:
            notes.append({
                "source": "garmin",
                "kind": "stale",
                "message": (
                    f"Garmin data is {_age_phrase(age)} old "
                    f"(last saved {_fmt(saved)} UTC). "
                    "Coaching may be based on stale metrics."
                ),
            })

    if withings:
        when = withings.get("attempted_at") or "unknown time"
        if not withings.get("ok"):
            err = withings.get("error") or "unknown error"
            notes.append({
                "source": "withings",
                "kind": "failed",
                "message": f"Last Withings sync failed at {when} UTC ({err}).",
            })
        else:
            attempted = _parse(withings.get("attempted_at"))
            if attempted is not None and (moment - attempted) > STALE_AFTER:
                age = moment - attempted
                notes.append({
                    "source": "withings",
                    "kind": "stale",
                    "message": (
                        f"Withings last synced {_age_phrase(age)} ago ({when} UTC)."
                    ),
                })
    return notes

"""FIT file ingest: parse, Garmin download, activity matching."""
from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union

log = logging.getLogger(__name__)

# FIT epoch is 1989-12-31 00:00:00 UTC
_FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)


@dataclass
class FitRecord:
    timestamp: datetime
    power: Optional[float] = None
    hr: Optional[float] = None
    cadence: Optional[float] = None
    temperature: Optional[float] = None


@dataclass
class FitLap:
    start_time: Optional[datetime] = None
    total_elapsed: Optional[float] = None
    wkt_step_index: Optional[int] = None
    intensity: Optional[str] = None
    avg_power: Optional[float] = None
    avg_hr: Optional[float] = None
    avg_cadence: Optional[float] = None


@dataclass
class FitWorkoutStep:
    message_index: Optional[int] = None
    intensity: Optional[str] = None
    duration_type: Optional[str] = None
    target_type: Optional[str] = None
    custom_target_low: Optional[float] = None
    custom_target_high: Optional[float] = None


@dataclass
class FitSession:
    start_time: Optional[datetime] = None
    total_elapsed: Optional[float] = None
    records: list[FitRecord] = field(default_factory=list)
    laps: list[FitLap] = field(default_factory=list)
    workout_steps: list[FitWorkoutStep] = field(default_factory=list)
    device_ftp: Optional[int] = None
    device_lthr: Optional[int] = None
    device_max_hr: Optional[int] = None
    weight_kg: Optional[float] = None
    resting_hr: Optional[int] = None
    left_right_balance: Optional[float] = None
    left_torque_effectiveness: Optional[float] = None
    left_pedal_smoothness: Optional[float] = None


def _field(msg: Any, name: str, default: Any = None) -> Any:
    try:
        if msg.has_field(name):
            return msg.get_value(name, fallback=default)
    except Exception:
        pass
    return default


def _as_dt(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    if isinstance(val, (int, float)):
        try:
            return _FIT_EPOCH + timedelta(seconds=float(val))
        except Exception:
            return None
    return None


def _intensity_str(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).upper()
    # fitdecode may return enum names like "active" / "INTERVAL"
    return s


def extract_fit_bytes(raw: bytes) -> bytes:
    """Garmin ORIGINAL download is often a zip containing one .fit file."""
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".fit")]
            if not names:
                raise ValueError("ZIP has no .fit member")
            return zf.read(names[0])
    return raw


def parse_fit(source: Union[str, bytes, io.BufferedIOBase]) -> FitSession:
    """Parse a FIT file path or bytes into a FitSession."""
    import fitdecode

    if isinstance(source, bytes):
        stream: Any = io.BytesIO(extract_fit_bytes(source))
    elif isinstance(source, str):
        stream = source
    else:
        stream = source

    session = FitSession()
    with fitdecode.FitReader(stream) as fit:
        for frame in fit:
            if not isinstance(frame, fitdecode.records.FitDataMessage):
                continue
            name = frame.name
            if name == "record":
                ts = _as_dt(_field(frame, "timestamp"))
                if ts is None:
                    continue
                session.records.append(FitRecord(
                    timestamp=ts,
                    power=_field(frame, "power"),
                    hr=_field(frame, "heart_rate"),
                    cadence=_field(frame, "cadence"),
                    temperature=_field(frame, "temperature"),
                ))
                # Spot-check L/R from records if present
                bal = _field(frame, "left_right_balance")
                if bal is not None and session.left_right_balance is None:
                    session.left_right_balance = float(bal)
                te = _field(frame, "left_torque_effectiveness")
                if te is not None and session.left_torque_effectiveness is None:
                    session.left_torque_effectiveness = float(te)
                ps = _field(frame, "left_pedal_smoothness")
                if ps is not None and session.left_pedal_smoothness is None:
                    session.left_pedal_smoothness = float(ps)
            elif name == "lap":
                session.laps.append(FitLap(
                    start_time=_as_dt(_field(frame, "start_time")),
                    total_elapsed=_field(frame, "total_elapsed_time"),
                    wkt_step_index=_field(frame, "wkt_step_index"),
                    intensity=_intensity_str(_field(frame, "intensity")),
                    avg_power=_field(frame, "avg_power"),
                    avg_hr=_field(frame, "avg_heart_rate"),
                    avg_cadence=_field(frame, "avg_cadence"),
                ))
            elif name == "workout_step":
                session.workout_steps.append(FitWorkoutStep(
                    message_index=_field(frame, "message_index"),
                    intensity=_intensity_str(_field(frame, "intensity")),
                    duration_type=str(_field(frame, "duration_type") or "") or None,
                    target_type=str(_field(frame, "target_type") or "") or None,
                    custom_target_low=_field(frame, "custom_target_value_low"),
                    custom_target_high=_field(frame, "custom_target_value_high"),
                ))
            elif name == "session":
                if session.start_time is None:
                    session.start_time = _as_dt(_field(frame, "start_time"))
                if session.total_elapsed is None:
                    session.total_elapsed = _field(frame, "total_elapsed_time")
            elif name == "zones_target":
                ftp = _field(frame, "functional_threshold_power")
                if ftp is not None:
                    session.device_ftp = int(ftp)
                thr = _field(frame, "threshold_heart_rate")
                if thr is not None:
                    session.device_lthr = int(thr)
                mx = _field(frame, "max_heart_rate")
                if mx is not None:
                    session.device_max_hr = int(mx)
            elif name == "user_profile":
                w = _field(frame, "weight")
                # FIT weight is often in grams or kg depending on scale
                if w is not None:
                    wf = float(w)
                    session.weight_kg = wf / 1000.0 if wf > 200 else wf
                rhr = _field(frame, "resting_heart_rate")
                if rhr is not None:
                    session.resting_hr = int(rhr)
                mx = _field(frame, "default_max_heart_rate")
                if mx is not None and session.device_max_hr is None:
                    session.device_max_hr = int(mx)

    if session.start_time is None and session.records:
        session.start_time = session.records[0].timestamp
    return session


def fetch_fit_for_activity(api: Any, activity_id: int) -> Optional[bytes]:
    """Download ORIGINAL (FIT zip) bytes from Garmin Connect. Soft-fail → None."""
    try:
        fmt = api.ActivityDownloadFormat.ORIGINAL
        raw = api.download_activity(str(activity_id), dl_fmt=fmt)
        if not raw:
            return None
        return extract_fit_bytes(raw)
    except Exception as exc:
        log.debug("FIT download failed for %s: %s", activity_id, exc)
        return None


def match_activity_by_start(
    start: datetime,
    activities: list[dict],
    window_sec: int = 120,
) -> Optional[dict]:
    """Match FIT session start to an activity whose start is within ±window_sec.

    Activity dicts may carry ``start_time`` (ISO) or we approximate from ``date``
    at midnight local (weak) — prefer explicit start_time when present.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    best = None
    best_delta = None
    for act in activities:
        cand = None
        st = act.get("start_time") or act.get("startTimeLocal") or act.get("start_time_local")
        if st:
            try:
                if isinstance(st, datetime):
                    cand = st if st.tzinfo else st.replace(tzinfo=timezone.utc)
                else:
                    s = str(st).replace("Z", "+00:00")
                    cand = datetime.fromisoformat(s)
                    if cand.tzinfo is None:
                        cand = cand.replace(tzinfo=timezone.utc)
            except Exception:
                cand = None
        if cand is None:
            continue
        delta = abs((cand - start).total_seconds())
        if delta <= window_sec and (best_delta is None or delta < best_delta):
            best, best_delta = act, delta
    return best

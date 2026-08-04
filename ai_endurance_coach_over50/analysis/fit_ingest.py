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


# FIT semicircle → degrees: 180 / 2^31
_SEMICIRCLE_TO_DEG = 180.0 / (2**31)


def _semicircle_to_deg(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val) * _SEMICIRCLE_TO_DEG
    except (TypeError, ValueError):
        return None


@dataclass
class FitRecord:
    timestamp: datetime
    power: Optional[float] = None
    hr: Optional[float] = None
    cadence: Optional[float] = None
    temperature: Optional[float] = None
    altitude: Optional[float] = None
    distance: Optional[float] = None
    speed: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


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
                alt = _field(frame, "enhanced_altitude")
                if alt is None:
                    alt = _field(frame, "altitude")
                spd = _field(frame, "enhanced_speed")
                if spd is None:
                    spd = _field(frame, "speed")
                dist = _field(frame, "distance")
                session.records.append(FitRecord(
                    timestamp=ts,
                    power=_field(frame, "power"),
                    hr=_field(frame, "heart_rate"),
                    cadence=_field(frame, "cadence"),
                    temperature=_field(frame, "temperature"),
                    altitude=float(alt) if alt is not None else None,
                    distance=float(dist) if dist is not None else None,
                    speed=float(spd) if spd is not None else None,
                    lat=_semicircle_to_deg(_field(frame, "position_lat")),
                    lon=_semicircle_to_deg(_field(frame, "position_long")),
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


def _local_tz():
    """System local timezone (Garmin startTimeLocal is wall-clock local)."""
    try:
        return datetime.now().astimezone().tzinfo or timezone.utc
    except Exception:
        return timezone.utc


def _parse_activity_start(st: Any) -> Optional[datetime]:
    """Parse activity start_time to UTC-aware datetime.

    Garmin ``startTimeLocal`` is stored naive (local wall clock). FIT record
    timestamps are UTC. Treating naive as UTC causes a ~1 h miss under BST.
    """
    if st is None:
        return None
    try:
        if isinstance(st, datetime):
            cand = st
        else:
            s = str(st).replace("Z", "+00:00")
            # Garmin often uses "YYYY-MM-DD HH:MM:SS" (space, no T)
            if " " in s and "T" not in s[:19]:
                s = s.replace(" ", "T", 1)
            cand = datetime.fromisoformat(s)
        if cand.tzinfo is None:
            cand = cand.replace(tzinfo=_local_tz())
        return cand.astimezone(timezone.utc)
    except Exception:
        return None


def match_activity_by_start(
    start: datetime,
    activities: list[dict],
    window_sec: int = 120,
) -> Optional[dict]:
    """Match FIT session start to an activity whose start is within ±window_sec.

    Activity ``start_time`` values from Garmin are local wall-clock (often naive).
    FIT starts are UTC. Naive activity times are interpreted in the system local
    timezone before comparison.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    else:
        start = start.astimezone(timezone.utc)
    best = None
    best_delta = None
    for act in activities:
        st = act.get("start_time") or act.get("startTimeLocal") or act.get("start_time_local")
        cand = _parse_activity_start(st)
        if cand is None:
            continue
        delta = abs((cand - start).total_seconds())
        if delta <= window_sec and (best_delta is None or delta < best_delta):
            best, best_delta = act, delta
    return best


def activity_id_from_filename(name: Optional[str]) -> Optional[int]:
    """Extract Garmin activity id from names like ``23823077329_ACTIVITY.fit``."""
    if not name:
        return None
    import re
    base = str(name).replace("\\", "/").rsplit("/", 1)[-1]
    m = re.match(r"^(\d{6,})_ACTIVITY\.(?:fit|FIT)$", base)
    if not m:
        m = re.match(r"^(\d{6,})\.(?:fit|FIT)$", base)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None

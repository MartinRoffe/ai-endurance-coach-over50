"""Garmin HR profile (max HR, zone boundaries) for coach context."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from .history import get_cached_text, load_ftp_tests, set_cached_text

logger = logging.getLogger(__name__)
_CACHE_KEY = "hr_profile_v1"

_METHOD_LABELS = {
    "HR_MAX": "Percent of max HR",
    "HR_RESERVE": "Heart rate reserve (Karvonen)",
    "HR_LACTATE_THRESHOLD": "Percent of lactate threshold",
}


def _lthr_zones(lthr: int) -> list[dict[str, Any]]:
    z2_lo = round(lthr * 0.85)
    return [
        {"zone": 1, "label": "Recovery", "lo": None, "hi": z2_lo - 1},
        {"zone": 2, "label": "Endurance", "lo": z2_lo, "hi": round(lthr * 0.89)},
        {"zone": 3, "label": "Tempo", "lo": round(lthr * 0.90), "hi": round(lthr * 0.94)},
        {"zone": 4, "label": "Threshold", "lo": round(lthr * 0.95), "hi": round(lthr * 0.99)},
        {"zone": 5, "label": "VO2max", "lo": lthr, "hi": None},
    ]


def _parse_garmin_zones(raw: list[dict], sport: str) -> Optional[dict[str, Any]]:
    entry = next((x for x in raw if x.get("sport") == sport), None)
    if not entry:
        return None
    floors = [entry.get(f"zone{i}Floor") for i in range(1, 6)]
    max_hr = entry.get("maxHeartRateUsed")
    if max_hr is None or any(f is None for f in floors):
        return None
    zones = []
    for i in range(5):
        lo = int(floors[i])
        hi = int(floors[i + 1] - 1) if i < 4 else int(max_hr)
        zones.append({"zone": i + 1, "lo": lo, "hi": hi})
    method = entry.get("trainingMethod") or ""
    return {
        "sport": entry.get("sport"),
        "method": method,
        "method_label": _METHOD_LABELS.get(method, method.replace("_", " ").title()),
        "max_hr": int(max_hr),
        "resting_hr": int(entry["restingHeartRateUsed"]) if entry.get("restingHeartRateUsed") is not None else None,
        "lthr_used": int(entry["lactateThresholdHeartRateUsed"])
        if entry.get("lactateThresholdHeartRateUsed") is not None else None,
        "zones": zones,
    }


def fetch_hr_profile(api) -> dict[str, Any]:
    profile: dict[str, Any] = {"fetched_at": datetime.now(timezone.utc).isoformat()}
    try:
        raw = api.connectapi("/biometric-service/heartRateZones/")
        if isinstance(raw, list):
            garmin = _parse_garmin_zones(raw, "CYCLING") or _parse_garmin_zones(raw, "DEFAULT")
            if garmin:
                profile["garmin"] = garmin
    except Exception as e:
        logger.debug("HR zones fetch failed: %s", e)

    tests = load_ftp_tests()
    if tests and tests[-1].get("ftp_hr"):
        lthr = int(tests[-1]["ftp_hr"])
        profile["lthr_test"] = {
            "lthr": lthr,
            "date": tests[-1]["date"],
            "max_hr": int(tests[-1]["ftp_hr_max"]) if tests[-1].get("ftp_hr_max") else None,
            "zones": _lthr_zones(lthr),
        }
    return profile


def save_hr_profile(profile: dict[str, Any]) -> None:
    set_cached_text(_CACHE_KEY, json.dumps(profile))


def load_hr_profile() -> Optional[dict[str, Any]]:
    raw = get_cached_text(_CACHE_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def refresh_hr_profile(api) -> dict[str, Any]:
    profile = fetch_hr_profile(api)
    save_hr_profile(profile)
    return profile


def refresh_hr_profile_if_needed(api, *, force: bool = False) -> Optional[dict[str, Any]]:
    if not force and load_hr_profile():
        return load_hr_profile()
    try:
        return refresh_hr_profile(api)
    except Exception as e:
        logger.debug("HR profile refresh failed: %s", e)
        return load_hr_profile()


def format_hr_profile_lines(
    profile: Optional[dict[str, Any]] = None,
    *,
    resting_hr_today: Optional[float] = None,
) -> list[str]:
    profile = profile or load_hr_profile()
    if not profile:
        return []

    lines = ["## Heart Rate Reference"]
    garmin = profile.get("garmin")
    if garmin:
        rest = garmin.get("resting_hr")
        rest_str = f"{rest}bpm" if rest is not None else "n/a"
        lines.append(
            f"Garmin Connect ({garmin.get('sport', 'profile')}): max HR {garmin['max_hr']}bpm, "
            f"resting HR {rest_str} (used in zone calc), method: {garmin.get('method_label', garmin.get('method'))}"
        )
        if garmin.get("lthr_used"):
            lines.append(f"  Garmin LTHR setting: {garmin['lthr_used']}bpm")
        lines.append("  Zone boundaries (Garmin — what your watch uses for time-in-zone):")
        for z in garmin["zones"]:
            lines.append(f"    Z{z['zone']}: {z['lo']}\u2013{z['hi']} bpm")

    if resting_hr_today is not None:
        lines.append(f"Today's resting HR (Garmin daily reading): {int(resting_hr_today)}bpm")

    lthr = profile.get("lthr_test")
    if lthr:
        peak = f", peak {lthr['max_hr']}bpm during effort" if lthr.get("max_hr") else ""
        lines.append(f"FTP test LTHR: {lthr['lthr']}bpm (from {lthr['date']}{peak})")
        lines.append("  Zone boundaries (% LTHR — use for coaching intensity cues):")
        for z in lthr["zones"]:
            if z["zone"] == 1:
                lines.append(f"    Z{z['zone']} ({z['label']}): <{z['lo'] or (z['hi'] + 1)} bpm")
            elif z["zone"] == 5:
                lines.append(f"    Z{z['zone']} ({z['label']}): \u2265{z['lo']} bpm")
            else:
                lines.append(f"    Z{z['zone']} ({z['label']}): {z['lo']}\u2013{z['hi']} bpm")

    return lines if len(lines) > 1 else []

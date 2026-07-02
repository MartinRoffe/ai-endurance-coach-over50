"""Measured FTP power zones (Coggan) for coach context and dashboard."""
from __future__ import annotations

from typing import Any, Optional

from .history import latest_estimated_wkg, latest_measured_wkg, load_ftp_tests

_ZONE_SPECS: list[tuple[int, str, float | None, float | None]] = [
    (1, "Recovery", None, 0.55),
    (2, "Endurance", 0.56, 0.75),
    (3, "Tempo", 0.76, 0.90),
    (4, "Threshold", 0.91, 1.05),
    (5, "VO2max", 1.06, 1.20),
    (6, "Anaerobic", 1.21, 1.50),
    (7, "Neuromuscular", 1.51, None),
]


def _coggan_zones(ftp_w: int) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    for zone, label, pct_lo, pct_hi in _ZONE_SPECS:
        lo = round(ftp_w * pct_lo) if pct_lo is not None else None
        hi = round(ftp_w * pct_hi) if pct_hi is not None else None
        zones.append({"zone": zone, "label": label, "lo": lo, "hi": hi})
    return zones


def build_power_profile() -> Optional[dict[str, Any]]:
    """Latest measured FTP watts + Coggan zones. None without ftp_w in ftp_tests."""
    tests = load_ftp_tests()
    ftp_w = None
    test_date = None
    ftp_hr = None
    for t in reversed(tests):
        if t.get("ftp_w"):
            ftp_w = int(t["ftp_w"])
            test_date = t["date"]
            ftp_hr = t.get("ftp_hr")
            break
    if not ftp_w:
        return None

    measured = latest_measured_wkg()
    wkg = measured["wkg"] if measured and measured.get("ftp_w") == ftp_w else None
    weight_kg = measured["weight_kg"] if measured else None
    est = latest_estimated_wkg()
    est_ftp_w = est["est_ftp_w"] if est else None

    return {
        "ftp_w": ftp_w,
        "test_date": test_date,
        "ftp_hr": ftp_hr,
        "wkg": wkg,
        "weight_kg": weight_kg,
        "est_ftp_w": est_ftp_w,
        "zones": _coggan_zones(ftp_w),
    }


def format_power_profile_lines(profile: Optional[dict[str, Any]] = None) -> list[str]:
    profile = profile or build_power_profile()
    if not profile:
        return []

    lines = [
        "## Power Reference (measured FTP)",
        f"FTP: {profile['ftp_w']}W (tested {profile['test_date']})",
    ]
    if profile.get("wkg") is not None:
        wt = f", weight {profile['weight_kg']:.1f} kg" if profile.get("weight_kg") else ""
        lines.append(f"W/kg: {profile['wkg']:.2f}{wt}")
    if profile.get("est_ftp_w"):
        lines.append(
            f"VO2max estimate cross-check: ~{profile['est_ftp_w']}W "
            f"(secondary — measured FTP is primary)"
        )
    if profile.get("ftp_hr"):
        lines.append(f"LTHR at test: {profile['ftp_hr']}bpm (HR is the strain/readiness channel)")
    lines.append(
        "Power is primary for prescription and pacing; HR monitors strain, fatigue, and readiness."
    )
    lines.append("Coggan zones (% FTP):")
    for z in profile["zones"]:
        if z["zone"] == 1:
            lines.append(f"  Z{z['zone']} ({z['label']}): <{z['hi']} W")
        elif z["zone"] == 7:
            lines.append(f"  Z{z['zone']} ({z['label']}): >{z['lo']} W")
        else:
            lines.append(f"  Z{z['zone']} ({z['label']}): {z['lo']}\u2013{z['hi']} W")
    return lines

"""Path-to-target W/kg projection — pure computation, no DB access.

Projects a forward path to a configurable goal W/kg by crossing two models:

* a **decelerating, floor-free** bodyweight extrapolation of the OLS weight
  trend (weight is allowed to keep dropping; the deceleration is the only brake,
  so a good "race weight" is discovered empirically rather than assumed), and
* three **scenario FTP retraining curves** (conservative / expected / stretch)
  that approach weight-independent watt ceilings and re-anchor on every new test.

The ``performance_guard`` is the race-weight discovery tool: it flags the point
where continued weight loss stops adding (or starts costing) watts.
"""
from __future__ import annotations

from datetime import date, timedelta
from math import exp, log
from typing import Optional

# Engine ladder — weight-independent FTP watt ceilings, grounded in the 2012
# Haute Route post-mortem (hr_plan.LESSONS_2012 "build_targets"): realistic
# 270-280 W, old strap estimate 301 W.
CONSERVATIVE_CEILING_W = 270
EXPECTED_CEILING_W = 285
STRETCH_CEILING_W = 300

# The post-mortem's own stated realistic W/kg range (270-280 W @ his 2012 78 kg).
# Context only — NOT a target and NOT tied to any projected race weight.
REALISTIC_BAND_WKG = (3.46, 3.59)

FTP_TAU_DAYS = 150.0
WEIGHT_HALF_LIFE_DAYS = 120.0

# performance_guard thresholds
_GUARD_SLOPE_THRESHOLD = -0.02   # kg/day; still cutting weight
_GUARD_FTP_DROP_W = 5            # watts between the two newest tests
_GUARD_READINESS_Z = -0.75       # mean 14-day composite z


def project_weight_kg(
    w0: Optional[float],
    slope_kg_per_day: Optional[float],
    days_ahead: float,
    half_life_days: float = WEIGHT_HALF_LIFE_DAYS,
) -> Optional[float]:
    """Weight at ``days_ahead`` from today, decelerating with no floor.

    The OLS slope decays exponentially (``tau = half_life / ln2``), so the total
    change asymptotes to ``slope * tau``:

        w(t) = w0 + slope * tau * (1 - exp(-t / tau))

    There is no hard floor — a steeper slope simply yields a lower asymptote.
    ``slope_kg_per_day is None`` -> flat ``w0`` (caller sets a caveat).
    """
    if w0 is None:
        return None
    if slope_kg_per_day is None:
        return round(w0, 2)
    tau = half_life_days / log(2)
    change = slope_kg_per_day * tau * (1.0 - exp(-days_ahead / tau))
    return round(w0 + change, 2)


def project_ftp_w(
    ftp0: Optional[float],
    ceiling_w: float,
    days_since_anchor: float,
    tau_days: float = FTP_TAU_DAYS,
) -> Optional[int]:
    """FTP watts approaching ``ceiling_w`` from ``ftp0`` (fast early, flattening).

        ftp(t) = C - (C - ftp0) * exp(-t / tau)

    Effective ceiling ``C = max(ceiling_w, ftp0 + 10)`` so a rider already at or
    above the scenario ceiling never projects a decline.
    """
    if ftp0 is None:
        return None
    ceiling = max(ceiling_w, ftp0 + 10)
    val = ceiling - (ceiling - ftp0) * exp(-max(0.0, days_since_anchor) / tau_days)
    return round(val)


def _ftp_anchor(ftp_tests: list[dict]) -> Optional[tuple[str, int]]:
    """(date_iso, ftp_w) of the newest watt-bearing test, else None.

    ``load_ftp_tests()`` returns rows ordered by date ascending, so the newest
    watt-bearing test is the last one with a truthy ``ftp_w``. Re-anchoring is
    automatic: a new FTP test simply moves the anchor and recomputes the band.
    """
    for t in reversed(ftp_tests or []):
        if t.get("ftp_w"):
            return (t["date"], int(t["ftp_w"]))
    return None


def build_wkg_path(
    anchor_date_iso: str,
    anchor_ftp_w: Optional[int],
    latest_weight_kg: Optional[float],
    weight_slope_kg_per_day: Optional[float],
    target_wkg: float,
    target_date_iso: str,
    today: Optional[date] = None,
) -> Optional[dict]:
    """Monthly W/kg path from today to the target date.

    Returns None when the target date is not in the future or the inputs needed
    to anchor a projection are missing. ``race_weight_kg`` is the *projected*
    weight at the target date — fully dynamic, never a fixed assumption.
    """
    today = today or date.today()
    try:
        target_d = date.fromisoformat(target_date_iso)
        anchor_d = date.fromisoformat(anchor_date_iso)
    except (TypeError, ValueError):
        return None
    if target_d <= today:
        return None
    if latest_weight_kg is None or anchor_ftp_w is None:
        return None

    weight_flat = weight_slope_kg_per_day is None

    # Monthly sample dates, guaranteeing today first and target_d last.
    sample_dates: list[date] = []
    cursor = today
    while cursor < target_d:
        sample_dates.append(cursor)
        cursor = cursor + timedelta(days=30)
    sample_dates.append(target_d)

    points: list[dict] = []
    for d in sample_dates:
        days_ahead = (d - today).days
        days_since_anchor = (d - anchor_d).days
        weight = project_weight_kg(latest_weight_kg, weight_slope_kg_per_day, days_ahead)
        ftp_c = project_ftp_w(anchor_ftp_w, CONSERVATIVE_CEILING_W, days_since_anchor)
        ftp_e = project_ftp_w(anchor_ftp_w, EXPECTED_CEILING_W, days_since_anchor)
        ftp_s = project_ftp_w(anchor_ftp_w, STRETCH_CEILING_W, days_since_anchor)
        points.append({
            "date": d.isoformat(),
            "label": d.strftime("%b %y"),
            "weight_kg": weight,
            "ftp_conservative": ftp_c,
            "ftp_expected": ftp_e,
            "ftp_stretch": ftp_s,
            "wkg_conservative": round(ftp_c / weight, 2) if weight else None,
            "wkg_expected": round(ftp_e / weight, 2) if weight else None,
            "wkg_stretch": round(ftp_s / weight, 2) if weight else None,
        })

    current_wkg = points[0]["wkg_expected"]

    # Straight required line from current W/kg to the target across the series.
    n = len(points)
    for i, p in enumerate(points):
        frac = i / (n - 1) if n > 1 else 1.0
        p["wkg_required"] = round(current_wkg + frac * (target_wkg - current_wkg), 2)

    race_weight_kg = points[-1]["weight_kg"]
    return {
        "points": points,
        "current_wkg": current_wkg,
        "gap_wkg": round(target_wkg - current_wkg, 2),
        "race_weight_kg": race_weight_kg,
        "required_ftp_w": round(target_wkg * race_weight_kg) if race_weight_kg else None,
        "wkg_expected_at_event": points[-1]["wkg_expected"],
        "weight_flat": weight_flat,
    }


def performance_guard(
    ftp_tests: list[dict],
    weight_slope_kg_per_day: Optional[float],
    recent_comp_z: list[Optional[float]],
) -> dict:
    """Flag when weight loss appears to be costing performance.

    Race-weight discovery tool. Silent unless still cutting weight
    (slope < -0.02 kg/day). Each signal abstains without data (the ILLNESS_RISK
    pattern in ``alerts.py``):

    * FTP_DROP — the two newest watt-bearing tests fell by more than 5 W.
    * READINESS_SAG — mean of >=7 non-None last-14-day composite z < -0.75.
    """
    if weight_slope_kg_per_day is None or weight_slope_kg_per_day >= _GUARD_SLOPE_THRESHOLD:
        return {"firing": False, "reasons": []}

    reasons: list[str] = []

    watt_tests = [t for t in (ftp_tests or []) if t.get("ftp_w")]
    if len(watt_tests) >= 2:
        newer = int(watt_tests[-1]["ftp_w"])
        older = int(watt_tests[-2]["ftp_w"])
        if newer < older - _GUARD_FTP_DROP_W:
            reasons.append(f"FTP fell {older}\u2192{newer} W between tests")

    zs = [z for z in (recent_comp_z or []) if z is not None]
    if len(zs) >= 7:
        mean_z = sum(zs) / len(zs)
        if mean_z < _GUARD_READINESS_Z:
            reasons.append(f"readiness composite averaging {mean_z:+.2f}\u03c3 over 14 days")

    return {"firing": bool(reasons), "reasons": reasons}

"""FIT interval metrics, stale-FTP evidence, and HR calibration checks."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Optional

from .fit_ingest import FitLap, FitRecord, FitSession, FitWorkoutStep

_WORK_INTENSITIES = {"ACTIVE", "INTERVAL", "ACTIVE_INTENSITY", "INTERVAL_INTENSITY"}
_STALE_FTP_PCT = 1.03
_STALE_MIN_SECS = 19 * 60
_HEAT_TEMP_C = 25.0
_HR_MAX_DECLINE_PER_YR = 0.6


def rolling_np(powers: list[float], window: int = 30) -> Optional[float]:
    """Coggan NP from 1 Hz (or near-1 Hz) power samples via 30 s rolling mean^4."""
    if not powers or len(powers) < window:
        # Fall back to simple 4th-power mean of available samples
        vals = [p for p in powers if p is not None and p >= 0]
        if not vals:
            return None
        mean4 = sum(v ** 4 for v in vals) / len(vals)
        return mean4 ** 0.25
    rolls: list[float] = []
    for i in range(len(powers) - window + 1):
        chunk = powers[i : i + window]
        rolls.append(sum(chunk) / window)
    if not rolls:
        return None
    mean4 = sum(r ** 4 for r in rolls) / len(rolls)
    return mean4 ** 0.25


def best_contiguous_avg_power(powers: list[float], window_secs: int = 1200) -> Optional[float]:
    """Best average power over a contiguous window (assumes ~1 Hz samples)."""
    if not powers or len(powers) < window_secs:
        if powers and len(powers) >= int(window_secs * 0.9):
            return sum(powers) / len(powers)
        return None
    best = None
    running = sum(powers[:window_secs])
    best = running / window_secs
    for i in range(window_secs, len(powers)):
        running += powers[i] - powers[i - window_secs]
        avg = running / window_secs
        if avg > best:
            best = avg
    return best


def half_decoupling(
    powers: list[float], hrs: list[float]
) -> Optional[float]:
    """First-half vs second-half Pw:HR decoupling % = HR_drift − power_drift."""
    n = min(len(powers), len(hrs))
    if n < 20:
        return None
    mid = n // 2
    p1, p2 = powers[:mid], powers[mid:]
    h1, h2 = hrs[:mid], hrs[mid:]
    if not p1 or not p2 or not h1 or not h2:
        return None
    avg_p1, avg_p2 = sum(p1) / len(p1), sum(p2) / len(p2)
    avg_h1, avg_h2 = sum(h1) / len(h1), sum(h2) / len(h2)
    if avg_p1 <= 0 or avg_h1 <= 0:
        return None
    power_drift = (avg_p2 - avg_p1) / avg_p1 * 100
    hr_drift = (avg_h2 - avg_h1) / avg_h1 * 100
    return hr_drift - power_drift


def five_min_splits(
    records: list[FitRecord],
) -> list[dict[str, Any]]:
    """Split records into 5-minute bins with avg P/HR/cad."""
    if not records:
        return []
    t0 = records[0].timestamp
    bins: dict[int, list[FitRecord]] = {}
    for r in records:
        idx = int((r.timestamp - t0).total_seconds() // 300)
        bins.setdefault(idx, []).append(r)
    out = []
    for idx in sorted(bins):
        chunk = bins[idx]
        pw = [r.power for r in chunk if r.power is not None]
        hr = [r.hr for r in chunk if r.hr is not None]
        cad = [r.cadence for r in chunk if r.cadence is not None]
        out.append({
            "split": idx + 1,
            "offset_min": idx * 5,
            "avg_power_w": round(sum(pw) / len(pw)) if pw else None,
            "avg_hr": round(sum(hr) / len(hr)) if hr else None,
            "avg_cadence": round(sum(cad) / len(cad)) if cad else None,
        })
    return out


def band_compliance(
    powers: list[float], lo: Optional[float], hi: Optional[float]
) -> dict[str, Optional[float]]:
    if not powers or lo is None or hi is None or hi <= 0:
        return {"pct_in": None, "pct_above": None, "pct_below": None}
    n = len(powers)
    below = sum(1 for p in powers if p < lo)
    above = sum(1 for p in powers if p > hi)
    inside = n - below - above
    return {
        "pct_in": round(inside / n * 100, 1),
        "pct_above": round(above / n * 100, 1),
        "pct_below": round(below / n * 100, 1),
    }


def _step_for_index(steps: list[FitWorkoutStep], idx: Optional[int]) -> Optional[FitWorkoutStep]:
    if idx is None:
        return None
    for s in steps:
        if s.message_index == idx:
            return s
    if 0 <= idx < len(steps):
        return steps[idx]
    return None


def _is_work_intensity(intens: Optional[str], step: Optional[FitWorkoutStep]) -> bool:
    candidates = []
    if intens:
        candidates.append(intens.upper())
    if step and step.intensity:
        candidates.append(step.intensity.upper())
    if not candidates:
        return True  # treat unknown as work when grouped by step
    return any(
        c in _WORK_INTENSITIES or c.endswith("ACTIVE") or "INTERVAL" in c
        for c in candidates
    )


def _records_in_window(
    records: list[FitRecord], start: datetime, secs: float
) -> list[FitRecord]:
    end = start + timedelta(seconds=secs)
    return [r for r in records if start <= r.timestamp < end]


def group_laps_by_step(laps: list[FitLap]) -> list[tuple[Optional[int], list[FitLap]]]:
    """Merge consecutive laps that share the same wkt_step_index."""
    groups: list[tuple[Optional[int], list[FitLap]]] = []
    for lap in laps:
        idx = lap.wkt_step_index
        if groups and groups[-1][0] is not None and groups[-1][0] == idx:
            groups[-1][1].append(lap)
        elif groups and idx is None and groups[-1][0] is None:
            # Unindexed laps stay separate (do not merge)
            groups.append((idx, [lap]))
        else:
            groups.append((idx, [lap]))
    return groups


def compute_interval_metrics(
    fit: FitSession,
    ftp_w: Optional[int],
    weight_kg: Optional[float] = None,
    max_hr_ref: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Per work-step metrics from FIT records + workout steps."""
    weight = weight_kg or fit.weight_kg
    max_hr = max_hr_ref or fit.device_max_hr
    results: list[dict[str, Any]] = []
    groups = group_laps_by_step(fit.laps) if fit.laps else []

    # Fallback: no laps — treat whole session as one block
    if not groups and fit.records:
        groups = [(0, [FitLap(
            start_time=fit.start_time or fit.records[0].timestamp,
            total_elapsed=fit.total_elapsed or (
                (fit.records[-1].timestamp - fit.records[0].timestamp).total_seconds()
            ),
            wkt_step_index=0,
            intensity="ACTIVE",
        )])]

    work_num = 0
    for step_idx, laps in groups:
        step = _step_for_index(fit.workout_steps, step_idx)
        intens = laps[0].intensity if laps else None
        if not _is_work_intensity(intens, step):
            continue
        # Skip recovery-named steps
        if step and step.intensity and "RECOVERY" in step.intensity.upper():
            continue
        if intens and intens.upper() in {"RECOVERY", "REST", "WARMUP", "COOLDOWN"}:
            continue

        start = laps[0].start_time
        if start is None:
            continue
        dur = sum(float(l.total_elapsed or 0) for l in laps)
        if dur <= 0:
            continue
        recs = _records_in_window(fit.records, start, dur)
        powers = [float(r.power) for r in recs if r.power is not None]
        hrs = [float(r.hr) for r in recs if r.hr is not None]
        cads = [float(r.cadence) for r in recs if r.cadence is not None]
        temps = [float(r.temperature) for r in recs if r.temperature is not None]

        avg_p = sum(powers) / len(powers) if powers else None
        np_p = rolling_np(powers) if powers else None
        vi = (np_p / avg_p) if (np_p and avg_p and avg_p > 0) else None
        if_val = (np_p / ftp_w) if (np_p and ftp_w) else None
        pct_ftp = (avg_p / ftp_w * 100) if (avg_p and ftp_w) else None
        avg_hr = sum(hrs) / len(hrs) if hrs else None
        max_hr_i = max(hrs) if hrs else None
        avg_cad = sum(cads) / len(cads) if cads else None
        decoupling = half_decoupling(powers, hrs) if powers and hrs else None
        splits = five_min_splits(recs)

        lo = step.custom_target_low if step else None
        hi = step.custom_target_high if step else None
        # Garmin sometimes stores power targets as watts directly
        band = band_compliance(powers, lo, hi) if powers else {
            "pct_in": None, "pct_above": None, "pct_below": None
        }

        front_load = None
        if splits and avg_p and splits[0].get("avg_power_w"):
            first = splits[0]["avg_power_w"]
            if first and avg_p:
                front_load = round((first - avg_p) / avg_p * 100, 1)

        heat_note = False
        if (
            decoupling is not None
            and decoupling > 5
            and pct_ftp is not None
            and pct_ftp >= 95
            and temps
            and max(temps) >= _HEAT_TEMP_C
        ):
            heat_note = True

        work_num += 1
        results.append({
            "step_index": step_idx if step_idx is not None else work_num - 1,
            "work_num": work_num,
            "duration_secs": round(dur),
            "avg_power_w": round(avg_p) if avg_p is not None else None,
            "np_w": round(np_p) if np_p is not None else None,
            "vi": round(vi, 3) if vi is not None else None,
            "if": round(if_val, 3) if if_val is not None else None,
            "pct_ftp": round(pct_ftp, 1) if pct_ftp is not None else None,
            "wkg": round(avg_p / weight, 2) if (avg_p and weight) else None,
            "avg_hr": round(avg_hr) if avg_hr is not None else None,
            "max_hr": round(max_hr_i) if max_hr_i is not None else None,
            "pct_max_hr": round(avg_hr / max_hr * 100, 1) if (avg_hr and max_hr) else None,
            "avg_cadence": round(avg_cad) if avg_cad is not None else None,
            "decoupling_pct": round(decoupling, 1) if decoupling is not None else None,
            "five_min_splits": splits,
            "band_pct_in": band["pct_in"],
            "band_pct_above": band["pct_above"],
            "band_pct_below": band["pct_below"],
            "target_lo_w": lo,
            "target_hi_w": hi,
            "front_load_pct": front_load,
            "temp_min": min(temps) if temps else None,
            "temp_max": max(temps) if temps else None,
            "heat_decoupling_expected": heat_note,
        })
    return results


def detect_stale_ftp(
    intervals: list[dict[str, Any]],
    records: list[FitRecord],
    ftp_w: Optional[int],
) -> Optional[dict[str, Any]]:
    """Return stale-FTP evidence + proposed FTP, or None."""
    if not ftp_w or ftp_w <= 0:
        return None
    threshold = ftp_w * _STALE_FTP_PCT

    long_efforts = [
        i for i in intervals
        if (i.get("duration_secs") or 0) >= _STALE_MIN_SECS
        and (i.get("avg_power_w") or 0) > threshold
    ]

    # 2×20-shaped: two work intervals ~19–23 min both supra-threshold
    twenties = [
        i for i in intervals
        if 19 * 60 <= (i.get("duration_secs") or 0) <= 23 * 60
        and (i.get("avg_power_w") or 0) > threshold
    ]
    two_x_twenty = False
    if len(twenties) >= 2:
        a, b = twenties[0], twenties[1]
        if (b.get("avg_power_w") or 0) >= (a.get("avg_power_w") or 0):
            two_x_twenty = True
            long_efforts = twenties[:2]

    if not long_efforts and not two_x_twenty:
        return None

    powers = [float(r.power) for r in records if r.power is not None]
    best20 = best_contiguous_avg_power(powers, 1200)
    propose_candidates = []
    if best20:
        propose_candidates.append(best20 * 0.95)
    if two_x_twenty and len(twenties) >= 2:
        mean_2x20 = (
            (twenties[0]["avg_power_w"] or 0) + (twenties[1]["avg_power_w"] or 0)
        ) / 2
        propose_candidates.append(mean_2x20 * 0.97)
    elif long_efforts:
        best_long = max(i.get("avg_power_w") or 0 for i in long_efforts)
        propose_candidates.append(best_long * 0.95)

    if not propose_candidates:
        return None
    proposed = round(max(propose_candidates))
    if proposed <= ftp_w:
        return None

    evidence_bits = []
    for i in long_efforts[:3]:
        evidence_bits.append(
            f"{(i.get('duration_secs') or 0) // 60}min @ {i.get('avg_power_w')} W "
            f"({i.get('pct_ftp')}% FTP)"
        )
    thr_hrs = [
        i.get("avg_hr") for i in long_efforts
        if i.get("avg_hr") and (i.get("pct_ftp") or 0) >= 95
    ]
    measured_lthr_hr = round(sum(thr_hrs) / len(thr_hrs)) if thr_hrs else None

    return {
        "current_ftp_w": ftp_w,
        "proposed_ftp_w": proposed,
        "evidence": "; ".join(evidence_bits),
        "two_x_twenty": two_x_twenty,
        "best_20min_w": round(best20) if best20 else None,
        "activity_ids": [],
        "measured_threshold_hr": measured_lthr_hr,
        "proposed_lthr": round(measured_lthr_hr * 0.95) if measured_lthr_hr else None,
    }


def age_adjusted_hr_max(
    reference: int, reference_date: date, as_of: date,
    decline_per_yr: float = _HR_MAX_DECLINE_PER_YR,
) -> int:
    years = max(0.0, (as_of - reference_date).days / 365.25)
    return round(reference - decline_per_yr * years)


def hr_calibration_check(
    *,
    device_max_hr: Optional[int],
    observed_max_12m: Optional[int],
    hr_max_reference: Optional[int],
    hr_max_reference_date: Optional[date],
    as_of: date,
    stored_lthr: Optional[int],
    measured_threshold_hr: Optional[int],
    current_ftp_w: Optional[int] = None,
    proposed_ftp_w: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """Build HR calibration discrepancies when evidence diverges."""
    issues: list[str] = []
    age_adj = None
    if hr_max_reference and hr_max_reference_date:
        age_adj = age_adjusted_hr_max(hr_max_reference, hr_max_reference_date, as_of)

    evidence_max = None
    if observed_max_12m or age_adj:
        evidence_max = max(x for x in (observed_max_12m, age_adj) if x)

    if device_max_hr and evidence_max and evidence_max - device_max_hr >= 5:
        issues.append(
            f"Device max HR {device_max_hr} vs evidence ~{evidence_max}"
            + (f" (age-adj from {hr_max_reference})" if age_adj else "")
        )

    if stored_lthr and measured_threshold_hr and stored_lthr > measured_threshold_hr + 5:
        issues.append(
            f"LTHR on record {stored_lthr} bpm exceeds threshold-effort avg HR "
            f"{measured_threshold_hr} by >5 bpm"
        )

    true_max = evidence_max or device_max_hr
    if stored_lthr and true_max:
        pct = stored_lthr / true_max * 100
        if pct < 88 or pct > 92:
            issues.append(
                f"LTHR {stored_lthr} is {pct:.0f}% of max HR {true_max} "
                "(expected ~88–92%)"
            )

    if not issues and not (proposed_ftp_w and current_ftp_w and proposed_ftp_w > current_ftp_w):
        return None

    return {
        "issues": issues,
        "device_max_hr": device_max_hr,
        "observed_max_12m": observed_max_12m,
        "age_adjusted_max_hr": age_adj,
        "evidence_max_hr": evidence_max,
        "stored_lthr": stored_lthr,
        "measured_threshold_hr": measured_threshold_hr,
        "suggested_lthr": (
            round(measured_threshold_hr * 0.95) if measured_threshold_hr else None
        ),
        "current_ftp_w": current_ftp_w,
        "proposed_ftp_w": proposed_ftp_w,
    }


def fit_prompt_lines(intervals: list[dict[str, Any]], meta: dict[str, Any]) -> list[str]:
    """Lines injected into the analysis prompt from FIT interval metrics."""
    lines: list[str] = []
    if meta.get("device_ftp") and meta.get("app_ftp_w"):
        lines.append(
            f"FIT device FTP: {meta['device_ftp']} W; app measured FTP: {meta['app_ftp_w']} W "
            "— use app measured FTP for all %FTP/IF claims."
        )
    if meta.get("single_sided_note"):
        lines.append(meta["single_sided_note"])
    if not intervals:
        return lines
    lines.append("FIT interval execution (workout steps):")
    lines.append(
        "Call out front-loading when the first 5-min split is >8% above interval average; "
        "praise negative splits; supra-threshold decoupling in >25 °C heat is not an aerobic deficiency."
    )
    for i in intervals:
        bits = [f"  Step {i.get('work_num')} ({i.get('duration_secs', 0) // 60}m)"]
        if i.get("avg_power_w") is not None:
            bits.append(f"avg {i['avg_power_w']} W")
        if i.get("np_w") is not None:
            bits.append(f"NP {i['np_w']} W")
        if i.get("pct_ftp") is not None:
            bits.append(f"{i['pct_ftp']}% FTP")
        if i.get("avg_hr") is not None:
            bits.append(f"HR {i['avg_hr']}")
        if i.get("avg_cadence") is not None:
            bits.append(f"{i['avg_cadence']} rpm")
        if i.get("decoupling_pct") is not None:
            bits.append(f"decoupling {i['decoupling_pct']:+.1f}%")
        if i.get("band_pct_in") is not None:
            bits.append(
                f"band in/above/below {i['band_pct_in']}/{i['band_pct_above']}/{i['band_pct_below']}%"
            )
        if i.get("front_load_pct") is not None and abs(i["front_load_pct"]) >= 8:
            bits.append(f"FRONT-LOADED {i['front_load_pct']:+.1f}%")
        if i.get("heat_decoupling_expected"):
            bits.append("heat-expected decoupling")
        lines.append(" · ".join(bits))
        splits = i.get("five_min_splits") or []
        if splits:
            sp = ", ".join(
                f"{s['offset_min']}m:{s.get('avg_power_w') or '—'}W/{s.get('avg_hr') or '—'}bpm"
                for s in splits
            )
            lines.append(f"    5-min splits: {sp}")
    return lines

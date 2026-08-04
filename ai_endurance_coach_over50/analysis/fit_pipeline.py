"""Orchestrate FIT download/parse → interval + climb metrics → SQLite persistence."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from .fit_climbs import compute_climb_analysis
from .fit_ingest import FitSession, fetch_fit_for_activity, parse_fit
from .fit_intervals import (
    compute_interval_metrics,
    detect_stale_ftp,
    fit_prompt_lines,
    hr_calibration_check,
)
from .power import ftp_w_on_date

log = logging.getLogger(__name__)


def process_fit_session(
    fit: FitSession,
    activity: dict,
    *,
    weight_kg: Optional[float] = None,
) -> dict[str, Any]:
    """Compute intervals + climbs + flags for a parsed FIT and persist."""
    from ..history import (
        latest_weight_kg,
        load_fit_activity_meta,
        load_ftp_tests,
        load_hr_max_reference,
        match_and_record_climb_attempts,
        observed_max_hr_12m,
        save_climb_analyses,
        save_fit_activity_meta,
        save_interval_analyses,
    )

    act_id = int(activity["activity_id"])
    act_date = activity.get("date")
    d_obj = date.fromisoformat(act_date) if act_date else date.today()
    ftp_w = ftp_w_on_date(d_obj)
    weight = weight_kg or fit.weight_kg
    if weight is None:
        try:
            weight = latest_weight_kg()
        except Exception:
            weight = None

    intervals = compute_interval_metrics(fit, ftp_w, weight_kg=weight)
    stale = detect_stale_ftp(intervals, fit.records, ftp_w)

    stored_lthr = None
    for t in reversed(load_ftp_tests()):
        if t.get("ftp_hr"):
            stored_lthr = int(t["ftp_hr"])
            break

    ref, ref_d = load_hr_max_reference()
    measured_thr_hr = stale.get("measured_threshold_hr") if stale else None
    if measured_thr_hr is None:
        thr_hrs = [
            i["avg_hr"] for i in intervals
            if i.get("avg_hr") and (i.get("pct_ftp") or 0) >= 95
        ]
        if thr_hrs:
            measured_thr_hr = round(sum(thr_hrs) / len(thr_hrs))

    hr_cal = hr_calibration_check(
        device_max_hr=fit.device_max_hr,
        observed_max_12m=observed_max_hr_12m(d_obj),
        hr_max_reference=ref,
        hr_max_reference_date=ref_d,
        as_of=d_obj,
        stored_lthr=stored_lthr,
        measured_threshold_hr=measured_thr_hr,
        current_ftp_w=ftp_w,
        proposed_ftp_w=stale.get("proposed_ftp_w") if stale else None,
    )

    single_sided = None
    if fit.left_torque_effectiveness is not None or fit.left_pedal_smoothness is not None:
        bits = []
        if fit.left_torque_effectiveness is not None:
            bits.append(f"left TE {fit.left_torque_effectiveness:.0f}%")
        if fit.left_pedal_smoothness is not None:
            bits.append(f"smoothness {fit.left_pedal_smoothness:.1f}%")
        single_sided = (
            "Single-sided / left-leg power metrics present ("
            + ", ".join(bits)
            + ") — true bilateral power may differ a few % with L/R imbalance."
        )

    climb_result = compute_climb_analysis(fit, ftp_w=ftp_w, weight_kg=weight)
    climbs = climb_result.get("climbs") or []
    grade_bins = climb_result.get("grade_bins") or []

    temps = [r.temperature for r in fit.records if r.temperature is not None]
    # Preserve existing meta keys when re-processing
    prev = load_fit_activity_meta(act_id) or {}
    meta = {
        **prev,
        "activity_date": act_date,
        "device_ftp": fit.device_ftp,
        "device_lthr": fit.device_lthr,
        "device_max_hr": fit.device_max_hr,
        "app_ftp_w": ftp_w,
        "temp_min": min(temps) if temps else None,
        "temp_max": max(temps) if temps else None,
        "stale_ftp": stale,
        "hr_calibration": hr_cal,
        "single_sided_note": single_sided,
        "n_intervals": len(intervals),
        "n_climbs": len(climbs),
        "grade_bins": grade_bins,
    }
    save_interval_analyses(act_id, intervals)
    save_climb_analyses(act_id, climbs)
    save_fit_activity_meta(act_id, meta)

    matched = []
    if climbs and act_date:
        try:
            matched = match_and_record_climb_attempts(act_id, act_date, climbs)
            # Persist names stamped onto climb rows for Recent UI
            if matched:
                save_climb_analyses(act_id, climbs)
                meta["matched_climbs"] = matched
                save_fit_activity_meta(act_id, meta)
            # Phase 2b: essays for named matches (best-effort)
            try:
                from .climb_essays import maybe_generate_named_climb_essays
                essays = maybe_generate_named_climb_essays(activity, climbs, matched)
                if essays:
                    meta["climb_essays"] = {**(meta.get("climb_essays") or {}), **essays}
                    save_fit_activity_meta(act_id, meta)
            except Exception as exc:
                log.debug("Climb essays failed for %s: %s", act_id, exc)
        except Exception as exc:
            log.debug("Named climb match failed for %s: %s", act_id, exc)

    return {
        "intervals": intervals,
        "climbs": climbs,
        "grade_bins": grade_bins,
        "matched_climbs": matched,
        "meta": meta,
        "prompt_lines": fit_prompt_lines(intervals, meta),
    }


def ingest_fit_for_activity(
    api: Any,
    activity: dict,
    *,
    fit_bytes: Optional[bytes] = None,
) -> Optional[dict[str, Any]]:
    """Download (or use provided) FIT, parse, persist. Soft-fail → None."""
    try:
        raw = fit_bytes
        if raw is None:
            raw = fetch_fit_for_activity(api, int(activity["activity_id"]))
        if not raw:
            return None
        fit = parse_fit(raw)
        if not fit.records and not fit.laps:
            return None
        return process_fit_session(fit, activity)
    except Exception as exc:
        log.debug("FIT ingest failed for %s: %s", activity.get("activity_id"), exc)
        return None

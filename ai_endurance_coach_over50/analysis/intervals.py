"""Lap-split mining: interval reps, FTP efforts, HR/power durability."""
from __future__ import annotations

from typing import Any, Optional


_FTP_SESSION_LABELS = {
    "FTP Test", "FTP Re-test", "Final FTP Test",
    "FTP Baseline Test", "FTP Final Test",
}
_RAMP_SESSION_LABELS = {"Ramp Test", "FTP Ramp Test"}
_ALL_FTP_LABELS = _FTP_SESSION_LABELS | _RAMP_SESSION_LABELS

# effort_min/max in seconds — range that identifies a single effort lap
_INTERVAL_CONFIG: dict[str, dict] = {
    "Tempo Intervals":     {"effort_min": 480,  "effort_max": 780,  "name": "Tempo rep"},
    "Sweetspot Intervals": {"effort_min": 720,  "effort_max": 1200, "name": "Sweetspot block"},
    "Sweetspot Ride":      {"effort_min": 720,  "effort_max": 1200, "name": "Sweetspot block"},
    "Hill Repeats":        {"effort_min": 120,  "effort_max": 330,  "name": "Hill rep"},
    "Threshold Ride":      {"effort_min": 900,  "effort_max": 1500, "name": "Threshold block"},
    "Over-Unders":         {"effort_min": 840,  "effort_max": 1200, "name": "OU set"},
    # MaxiClimber work intervals: 90–240 s across all plan weeks (easy → Norwegian 4×4)
    "MaxiClimber":         {"effort_min": 80,   "effort_max": 260,  "name": "Climbing interval"},
    "Easy MaxiClimber":    {"effort_min": 80,   "effort_max": 260,  "name": "Climbing interval"},
    "KB + MaxiClimber":    {"effort_min": 80,   "effort_max": 260,  "name": "Climbing interval"},
}

# Interval sessions are discipline-specific. On a compound day (e.g.
# "KB + MaxiClimber") two activities share the same plan label — only the
# climbing one carries climbing intervals, so the kettlebell strength activity
# must be skipped rather than mined for reps. Labels not listed here are cycling.
_CLIMBING_INTERVAL_LABELS = {"MaxiClimber", "Easy MaxiClimber", "KB + MaxiClimber"}
_CLIMBING_TYPES = {"stair_climbing", "indoor_cardio"}


# Garmin lap intensityType tags. Work reps are ACTIVE/INTERVAL; the rest mark
# warm-up, recovery, and cool-down.
_WORK_INTENSITIES = {"ACTIVE", "INTERVAL"}
_NONWORK_INTENSITIES = {"WARMUP", "COOLDOWN", "RECOVERY", "REST"}


def _drop_stubs(work_laps: list[dict]) -> list[dict]:
    """Remove truncated stub laps (e.g. a 7 s tail from an accidental lap press)
    that are far shorter than the typical work rep."""
    import statistics

    if not work_laps:
        return work_laps
    med = statistics.median([_lap_dur(l) for l in work_laps])
    return [l for l in work_laps if _lap_dur(l) >= 0.5 * med]


def _work_laps_from_steps(hr_laps: list[dict]) -> Optional[list[dict]]:
    """Pick out only the work-interval laps from a structured workout.

    Prefers Garmin's per-lap ``intensityType`` tag (WARMUP / ACTIVE / RECOVERY /
    COOLDOWN), which correctly identifies the work reps even when each interval
    carries its own sequential ``wktStepIndex`` (i.e. the workout was built as
    sequential steps rather than a single repeat block — in which case the
    "repeated step with highest HR" heuristic would only catch one rep).

    Falls back to the repeated-step heuristic when intensity tags are absent.
    Returns None when laps carry no usable structure so the caller can fall back
    to a duration band.
    """
    from collections import defaultdict

    # ── Primary: Garmin intensityType tags ──────────────────────────────────
    intensities = {(l.get("intensityType") or "").upper() for l in hr_laps}
    # Only trust the tags when at least one non-work marker is present — that
    # confirms the laps are meaningfully intensity-tagged (a manually ridden
    # session with every lap defaulting to ACTIVE carries no real signal).
    if intensities & _NONWORK_INTENSITIES:
        # When step indices exist, restrict to the structured part so extra
        # laps ridden after the workout (step index None) aren't counted.
        stepped = [l for l in hr_laps if l.get("wktStepIndex") is not None]
        pool = stepped or hr_laps
        work_laps = [
            l for l in pool
            if (l.get("intensityType") or "").upper() in _WORK_INTENSITIES
        ]
        work_laps = _drop_stubs(work_laps)
        if work_laps:
            return work_laps

    # ── Fallback: repeated-step-with-highest-HR heuristic ───────────────────
    step_vals = {l.get("wktStepIndex") for l in hr_laps if l.get("wktStepIndex") is not None}
    if len(step_vals) < 2:
        return None

    groups: dict = defaultdict(list)
    for l in hr_laps:
        si = l.get("wktStepIndex")
        if si is not None:
            groups[si].append(l)

    repeated = {si: ls for si, ls in groups.items() if len(ls) >= 2}
    pool = repeated or groups
    work_step = max(pool, key=lambda si: sum(l["averageHR"] for l in pool[si]) / len(pool[si]))
    work_laps = [l for l in hr_laps if l.get("wktStepIndex") == work_step]
    return _drop_stubs(work_laps) or None


def _lap_dur(l: dict) -> float:
    return l.get("duration") or l.get("elapsedDuration") or 0


def _lap_power(l: dict) -> Optional[float]:
    np = l.get("normativePower") or l.get("normalizedPower")
    if np is not None:
        return float(np)
    ap = l.get("averagePower")
    return float(ap) if ap is not None else None


def _extract_interval_data(api: Any, activity_id: int, session_label: str,
                           activity_type: Optional[str] = None) -> dict:
    """Return per-rep HR data for structured interval sessions using lap splits.

    Prefers structured-workout step tags so warm-up and recovery laps are not
    mislabelled as work reps; falls back to a duration band when no step tags
    are present (e.g. a manually lapped session). On compound days the activity
    whose discipline doesn't match the session (e.g. a kettlebell strength
    activity under a "KB + MaxiClimber" label) is skipped.
    """
    config = _INTERVAL_CONFIG.get(session_label)
    if not config:
        return {}
    if activity_type:
        allowed = _CLIMBING_TYPES if session_label in _CLIMBING_INTERVAL_LABELS else _CYCLING_TYPES
        if activity_type not in allowed:
            return {}
    try:
        splits = api.get_activity_splits(activity_id)
        laps = splits.get("lapDTOs") or splits.get("laps") or []
        hr_laps = [l for l in laps if (l.get("averageHR") or 0) > 0 and _lap_dur(l) > 0]
        if not hr_laps:
            return {}

        effort_laps = _work_laps_from_steps(hr_laps)
        if not effort_laps:
            # Fallback: no step tags — identify efforts by their duration band.
            lo, hi = config["effort_min"], config["effort_max"]
            effort_laps = [l for l in hr_laps if lo <= _lap_dur(l) <= hi]
        if not effort_laps:
            return {}

        reps = []
        for i, l in enumerate(effort_laps, 1):
            rep = {
                "rep":          i,
                "name":         config["name"],
                "avg_hr":       round(l["averageHR"]) if l.get("averageHR") else None,
                "max_hr":       round(l["maxHR"])     if l.get("maxHR")     else None,
                "duration_secs": round(_lap_dur(l)),
            }
            if l.get("averagePower"):
                rep["avg_power_w"] = round(l["averagePower"])
            reps.append(rep)
        return {"interval_reps": reps} if reps else {}
    except Exception:
        return {}


def _ftp_effort_from_summary(api: Any, activity_id: int) -> dict:
    """Fallback: Garmin's best 20-min average power from the activity summary."""
    try:
        s = api.get_activity(activity_id).get("summaryDTO") or {}
        max20 = s.get("maxPowerTwentyMinutes")
        if not max20:
            return {}
        result: dict = {
            "ftp_effort_avg_w": round(float(max20)),
            "ftp_w": round(float(max20) * 0.95),
        }
        avg_hr = s.get("averageHR")
        if avg_hr:
            result["ftp_effort_avg_hr"] = round(float(avg_hr))
        max_hr = s.get("maxHR")
        if max_hr:
            result["ftp_effort_max_hr"] = round(float(max_hr))
        return result
    except Exception:
        return {}


def _extract_ftp_effort(api: Any, activity_id: int) -> dict:
    """Return avg/max HR and power for the best ~20-min contiguous lap window.

    Structured FTP workouts often split the all-out effort across several laps
    (each under 10 min), with a longer warm-up lap that can carry a misleadingly
    high average HR. Scan contiguous lap windows totalling 17–23 minutes and pick
    the highest duration-weighted normalized power (average power if NP absent).
  HR-only rides maximise duration-weighted average HR over the same window.
    Falls back to Garmin summary maxPowerTwentyMinutes when lap windows fail.
    """
    _TARGET_SECS = 1200.0
    _TOLERANCE_SECS = 180.0  # 17–23 min

    def _window_stats(window: list[dict]) -> Optional[tuple[float, float, float, float]]:
        secs = sum(_lap_dur(l) for l in window)
        if secs <= 0:
            return None
        hr_vals = [(float(l["averageHR"]), _lap_dur(l)) for l in window if l.get("averageHR")]
        if not hr_vals:
            return None
        w_hr = sum(hr * d for hr, d in hr_vals) / sum(d for _, d in hr_vals)
        max_hr = max(l.get("maxHR") or 0 for l in window) or None
        pwr_vals = [(_lap_power(l), _lap_dur(l)) for l in window if _lap_power(l)]
        w_pwr = None
        if pwr_vals:
            psec = sum(d for _, d in pwr_vals)
            w_pwr = sum(p * d for p, d in pwr_vals) / psec if psec > 0 else None
        return w_hr, max_hr, w_pwr, secs

    try:
        splits = api.get_activity_splits(activity_id)
        laps = splits.get("lapDTOs") or splits.get("laps") or []
        if not laps:
            return _ftp_effort_from_summary(api, activity_id)

        has_power = any(_lap_power(l) for l in laps)
        best: Optional[tuple[float, float, Optional[float], float]] = None
        best_score = -1.0

        for i in range(len(laps)):
            total_dur = 0.0
            for j in range(i, len(laps)):
                total_dur += _lap_dur(laps[j])
                if total_dur < _TARGET_SECS - _TOLERANCE_SECS:
                    continue
                if total_dur > _TARGET_SECS + _TOLERANCE_SECS:
                    break
                stats = _window_stats(laps[i : j + 1])
                if not stats:
                    continue
                w_hr, max_hr, w_pwr, secs = stats
                score = w_pwr if has_power and w_pwr is not None else w_hr
                if score > best_score:
                    best_score = score
                    best = (w_hr, max_hr, w_pwr, secs)

        if best:
            w_hr, max_hr, w_pwr, _secs = best
            result: dict = {
                "ftp_effort_avg_hr": round(w_hr),
                "ftp_effort_max_hr": round(max_hr) if max_hr else None,
            }
            if w_pwr is not None:
                result["ftp_effort_avg_w"] = round(w_pwr)
                result["ftp_w"] = round(w_pwr * 0.95)
            return result

        # Single lap ~20 min (classic manual lap)
        single = [
            l for l in laps
            if _TARGET_SECS - _TOLERANCE_SECS <= _lap_dur(l) <= _TARGET_SECS + _TOLERANCE_SECS
            and l.get("averageHR")
        ]
        if single:
            pick = max(
                single,
                key=lambda l: _lap_power(l) or 0 if has_power else l.get("averageHR") or 0,
            )
            result = {
                "ftp_effort_avg_hr": round(pick["averageHR"]),
                "ftp_effort_max_hr": round(pick["maxHR"]) if pick.get("maxHR") else None,
            }
            pwr = _lap_power(pick)
            if pwr is not None:
                result["ftp_effort_avg_w"] = round(pwr)
                result["ftp_w"] = round(pwr * 0.95)
            return result

        return _ftp_effort_from_summary(api, activity_id)
    except Exception:
        return {}


def _extract_ramp_ftp(api: Any, activity_id: int) -> dict:
    """Ramp test: best 45–90 s lap avg power; FTP = 75% of best 1-min power."""
    try:
        splits = api.get_activity_splits(activity_id)
        laps = splits.get("lapDTOs") or splits.get("laps") or []
        best_pwr = 0.0
        best_lap: Optional[dict] = None
        for l in laps:
            dur = _lap_dur(l)
            if dur < 45 or dur > 90:
                continue
            pwr = _lap_power(l)
            if pwr and pwr > best_pwr:
                best_pwr = pwr
                best_lap = l
        if not best_lap or best_pwr <= 0:
            return {}
        result: dict = {
            "ftp_effort_avg_w": round(best_pwr),
            "ftp_w": round(best_pwr * 0.75),
            "ramp_best_1min_w": round(best_pwr),
        }
        if best_lap.get("averageHR"):
            result["ftp_effort_avg_hr"] = round(best_lap["averageHR"])
        if best_lap.get("maxHR"):
            result["ftp_effort_max_hr"] = round(best_lap["maxHR"])
        return result
    except Exception:
        return {}


_CYCLING_TYPES = {"road_biking", "cycling", "virtual_ride", "indoor_cycling", "mountain_biking"}


def _extract_durability(api: Any, activity: dict) -> Optional[dict]:
    """Late-ride HR drift from lap splits: duration-weighted avg HR of the
    final third of the ride vs the first third.

    drift_pct = (final − first) / first × 100. Positive = HR rising late in
    the ride at (assumed) constant effort — a durability/fatigue-resistance
    signal. Returns None when fewer than 3 HR-bearing laps (e.g. single-lap
    indoor rides) so callers can skip silently.
    """
    try:
        splits = api.get_activity_splits(activity["activity_id"])
        laps = splits.get("lapDTOs") or splits.get("laps") or []
        hr_laps = [
            l for l in laps
            if (l.get("averageHR") or 0) > 0
            and (l.get("duration") or l.get("elapsedDuration") or 0) > 0
        ]
        if len(hr_laps) < 3:
            return None

        def _dur(l: dict) -> float:
            return float(l.get("duration") or l.get("elapsedDuration") or 0)

        total = sum(_dur(l) for l in hr_laps)
        third = total / 3.0

        def _weighted_hr(lap_subset: list[dict]) -> Optional[float]:
            secs = sum(_dur(l) for l in lap_subset)
            if secs <= 0:
                return None
            return sum(float(l["averageHR"]) * _dur(l) for l in lap_subset) / secs

        # Bucket laps into thirds by cumulative duration
        first_laps, final_laps = [], []
        elapsed = 0.0
        for l in hr_laps:
            mid = elapsed + _dur(l) / 2.0
            if mid < third:
                first_laps.append(l)
            elif mid >= 2 * third:
                final_laps.append(l)
            elapsed += _dur(l)
        first_hr = _weighted_hr(first_laps)
        final_hr = _weighted_hr(final_laps)
        if not first_hr or not final_hr:
            return None
        return {
            "date": activity["date"],
            "duration_min": round((activity.get("duration_seconds") or total) / 60),
            "first_third_hr": round(first_hr, 1),
            "final_third_hr": round(final_hr, 1),
            "drift_pct": round((final_hr - first_hr) / first_hr * 100, 2),
            "n_laps": len(hr_laps),
        }
    except Exception:
        return None


def _extract_power_durability(api: Any, activity: dict) -> Optional[dict]:
    """Pw:HR decoupling on long rides: first-third vs final-third power and HR.

    decoupling_pct = HR drift % − power drift %. Positive = HR rising faster
    than power (cardiac drift at constant-ish effort).
    """
    try:
        splits = api.get_activity_splits(activity["activity_id"])
        laps = splits.get("lapDTOs") or splits.get("laps") or []
        power_laps = [
            l for l in laps
            if (l.get("averageHR") or 0) > 0
            and (l.get("averagePower") or 0) > 0
            and (l.get("duration") or l.get("elapsedDuration") or 0) > 0
        ]
        if len(power_laps) < 3:
            return None

        def _dur(l: dict) -> float:
            return float(l.get("duration") or l.get("elapsedDuration") or 0)

        def _lap_power(l: dict) -> float:
            return float(l.get("normativePower") or l.get("normalizedPower") or l["averagePower"])

        total = sum(_dur(l) for l in power_laps)
        third = total / 3.0

        def _weighted(lap_subset: list[dict], field: str) -> Optional[float]:
            secs = sum(_dur(l) for l in lap_subset)
            if secs <= 0:
                return None
            if field == "hr":
                return sum(float(l["averageHR"]) * _dur(l) for l in lap_subset) / secs
            return sum(_lap_power(l) * _dur(l) for l in lap_subset) / secs

        first_laps, final_laps = [], []
        elapsed = 0.0
        for l in power_laps:
            mid = elapsed + _dur(l) / 2.0
            if mid < third:
                first_laps.append(l)
            elif mid >= 2 * third:
                final_laps.append(l)
            elapsed += _dur(l)
        first_hr = _weighted(first_laps, "hr")
        final_hr = _weighted(final_laps, "hr")
        first_pwr = _weighted(first_laps, "power")
        final_pwr = _weighted(final_laps, "power")
        if not all((first_hr, final_hr, first_pwr, final_pwr)):
            return None
        hr_drift = (final_hr - first_hr) / first_hr * 100
        pwr_drift = (final_pwr - first_pwr) / first_pwr * 100
        return {
            "date": activity["date"],
            "duration_min": round((activity.get("duration_seconds") or total) / 60),
            "first_third_hr": round(first_hr, 1),
            "final_third_hr": round(final_hr, 1),
            "first_third_power": round(first_pwr, 1),
            "final_third_power": round(final_pwr, 1),
            "hr_drift_pct": round(hr_drift, 2),
            "power_drift_pct": round(pwr_drift, 2),
            "decoupling_pct": round(hr_drift - pwr_drift, 2),
            "n_laps": len(power_laps),
        }
    except Exception:
        return None

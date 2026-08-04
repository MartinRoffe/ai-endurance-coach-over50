"""FIT climb detection: grade, VAM, W/kg, pacing, cadence-vs-gradient bins."""
from __future__ import annotations

import math
from typing import Any, Optional

from .fit_ingest import FitRecord, FitSession
from .fit_intervals import rolling_np

# Detection thresholds
_MIN_GRADE_START = 2.0
_MIN_GRADE_END = 0.5
_MIN_GAIN_M = 20.0
_MIN_LENGTH_M = 200.0
_GRADE_LOOKBACK_M = 75.0
_SMOOTH_HALF_WIN = 10  # ~21-point mean
_VAM_CONFIDENCE_GRADE = 5.0

_GRADE_BINS: list[tuple[float, float, str]] = [
    (0.0, 2.0, "0-2%"),
    (2.0, 4.0, "2-4%"),
    (4.0, 6.0, "4-6%"),
    (6.0, 8.0, "6-8%"),
    (8.0, 10.0, "8-10%"),
    (10.0, 99.0, "10%+"),
]


def vam_m_h(gain_m: float, duration_min: float) -> Optional[float]:
    """VAM = (metres ascended × 60) / minutes."""
    if duration_min <= 0 or gain_m <= 0:
        return None
    return round((gain_m * 60.0) / duration_min, 1)


def est_wkg_from_vam(vam: float, avg_grade_pct: float) -> Optional[float]:
    """Ferrari empirical: W/kg ≈ VAM / (200 + 10 × %grade)."""
    if vam <= 0:
        return None
    denom = 200.0 + 10.0 * max(0.0, avg_grade_pct)
    if denom <= 0:
        return None
    return round(vam / denom, 2)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _smooth_altitude(alts: list[float], half_win: int = _SMOOTH_HALF_WIN) -> list[float]:
    n = len(alts)
    out: list[float] = []
    for i in range(n):
        lo = max(0, i - half_win)
        hi = min(n, i + half_win + 1)
        chunk = alts[lo:hi]
        out.append(sum(chunk) / len(chunk))
    return out


def _grades_from_series(
    dists: list[float],
    smooth_alts: list[float],
    lookback_m: float = _GRADE_LOOKBACK_M,
) -> list[float]:
    grades: list[float] = []
    for i in range(len(smooth_alts)):
        j = i
        while j > 0 and dists[i] - dists[j] < lookback_m:
            j -= 1
        dd = dists[i] - dists[j]
        if dd > 20:
            grades.append(100.0 * (smooth_alts[i] - smooth_alts[j]) / dd)
        else:
            grades.append(0.0)
    return grades


def _usable_series(records: list[FitRecord]) -> Optional[dict[str, list]]:
    """Extract parallel series; None if altitude+distance coverage too sparse."""
    idxs: list[int] = []
    for i, r in enumerate(records):
        if r.altitude is not None and r.distance is not None:
            idxs.append(i)
    if len(idxs) < 30:
        return None
    return {
        "idxs": idxs,
        "alts": [float(records[i].altitude) for i in idxs],  # type: ignore[arg-type]
        "dists": [float(records[i].distance) for i in idxs],  # type: ignore[arg-type]
        "powers": [records[i].power for i in idxs],
        "cads": [records[i].cadence for i in idxs],
        "hrs": [records[i].hr for i in idxs],
        "lats": [records[i].lat for i in idxs],
        "lons": [records[i].lon for i in idxs],
        "times": [records[i].timestamp for i in idxs],
    }


def _avg(vals: list[Optional[float]], *, min_val: float = 0.0) -> Optional[float]:
    clean = [float(v) for v in vals if v is not None and float(v) > min_val]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _cadence_bands(cads: list[Optional[float]]) -> tuple[Optional[float], Optional[float], Optional[float]]:
    clean = [float(c) for c in cads if c is not None and float(c) > 0]
    if not clean:
        return None, None, None
    n = len(clean)
    below_60 = sum(1 for c in clean if c < 60) / n * 100
    in_70_85 = sum(1 for c in clean if 70 <= c <= 85) / n * 100
    return round(sum(clean) / n, 1), round(below_60, 1), round(in_70_85, 1)


def _grade_bin_rows(
    grades: list[float],
    powers: list[Optional[float]],
    cads: list[Optional[float]],
    hrs: list[Optional[float]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lo, hi, label in _GRADE_BINS:
        pts_p: list[float] = []
        pts_c: list[float] = []
        pts_h: list[float] = []
        for i, g in enumerate(grades):
            if not (lo <= g < hi):
                continue
            p, c = powers[i], cads[i]
            if p is None or c is None or p <= 50 or c <= 30:
                continue
            pts_p.append(float(p))
            pts_c.append(float(c))
            if hrs[i] is not None and float(hrs[i]) > 0:  # type: ignore[arg-type]
                pts_h.append(float(hrs[i]))  # type: ignore[arg-type]
        if not pts_p:
            continue
        ap = sum(pts_p) / len(pts_p)
        ac = sum(pts_c) / len(pts_c)
        rows.append({
            "label": label,
            "lo": lo,
            "hi": hi,
            "n": len(pts_p),
            "avg_power": round(ap),
            "avg_cadence": round(ac, 1),
            "w_per_rpm": round(ap / ac, 2) if ac else None,
            "avg_hr": round(sum(pts_h) / len(pts_h)) if pts_h else None,
        })
    return rows


def _climb_metrics(
    start: int,
    end: int,
    series: dict[str, list],
    smooth: list[float],
    grades: list[float],
    *,
    ftp_w: Optional[int] = None,
    weight_kg: Optional[float] = None,
    climb_index: int = 1,
) -> dict[str, Any]:
    dists = series["dists"]
    times = series["times"]
    powers = series["powers"]
    cads = series["cads"]
    hrs = series["hrs"]
    lats = series["lats"]
    lons = series["lons"]

    gain = smooth[end] - smooth[start]
    length = dists[end] - dists[start]
    dur_s = (times[end] - times[start]).total_seconds()
    dur_min = dur_s / 60.0 if dur_s > 0 else 0.0
    avg_grade = (100.0 * gain / length) if length > 0 else 0.0
    max_grade = max(grades[start : end + 1]) if end >= start else 0.0

    seg_p = powers[start : end + 1]
    seg_c = cads[start : end + 1]
    seg_h = hrs[start : end + 1]
    avg_p = _avg(seg_p, min_val=0)
    max_p = None
    clean_p = [float(p) for p in seg_p if p is not None and float(p) > 0]
    if clean_p:
        max_p = max(clean_p)
    np_val = rolling_np(clean_p) if clean_p else None
    avg_cad, pct_below_60, pct_70_85 = _cadence_bands(seg_c)
    avg_hr = _avg(seg_h, min_val=0)

    # Pacing: first half vs second half power
    mid = (end - start) // 2
    first = seg_p[: mid + 1]
    second = seg_p[mid + 1 :]
    p1 = _avg(first, min_val=30)
    p2 = _avg(second, min_val=30)
    fade_pct = None
    if p1 and p2 and p1 > 0:
        fade_pct = round((p1 - p2) / p1 * 100, 1)

    vam = vam_m_h(gain, dur_min) if dur_min > 0 else None
    confidence = "high" if avg_grade >= _VAM_CONFIDENCE_GRADE else "low"
    est_wkg = est_wkg_from_vam(vam, avg_grade) if vam is not None else None
    wkg = round(avg_p / weight_kg, 2) if avg_p and weight_kg and weight_kg > 0 else None
    pct_ftp = round(100.0 * avg_p / ftp_w, 1) if avg_p and ftp_w and ftp_w > 0 else None

    within_bins = _grade_bin_rows(
        grades[start : end + 1],
        powers[start : end + 1],
        cads[start : end + 1],
        hrs[start : end + 1],
    )

    return {
        "climb_index": climb_index,
        "start_km": round(dists[start] / 1000.0, 2),
        "length_m": round(length, 1),
        "gain_m": round(gain, 1),
        "avg_grade": round(avg_grade, 2),
        "max_grade": round(max_grade, 1),
        "duration_s": round(dur_s, 1),
        "duration_min": round(dur_min, 2),
        "vam_m_h": vam,
        "vam_confidence": confidence,
        "avg_power": round(avg_p) if avg_p is not None else None,
        "max_power": round(max_p) if max_p is not None else None,
        "np": round(np_val) if np_val is not None else None,
        "wkg": wkg,
        "pct_ftp": pct_ftp,
        "est_wkg_from_vam": est_wkg,
        "first_half_w": round(p1) if p1 is not None else None,
        "second_half_w": round(p2) if p2 is not None else None,
        "fade_pct": fade_pct,
        "avg_cadence": avg_cad,
        "pct_below_60": pct_below_60,
        "pct_70_85": pct_70_85,
        "avg_hr": round(avg_hr) if avg_hr is not None else None,
        "start_lat": lats[start],
        "start_lon": lons[start],
        "end_lat": lats[end],
        "end_lon": lons[end],
        "grade_bins": within_bins,
    }


def detect_climbs(
    records: list[FitRecord],
    *,
    ftp_w: Optional[int] = None,
    weight_kg: Optional[float] = None,
    min_grade: float = _MIN_GRADE_START,
    end_grade: float = _MIN_GRADE_END,
    min_gain_m: float = _MIN_GAIN_M,
    min_length_m: float = _MIN_LENGTH_M,
) -> list[dict[str, Any]]:
    """Detect climb segments from altitude/distance series."""
    series = _usable_series(records)
    if series is None:
        return []
    smooth = _smooth_altitude(series["alts"])
    grades = _grades_from_series(series["dists"], smooth)

    climbs: list[dict[str, Any]] = []
    in_climb = False
    start = 0
    for i, g in enumerate(grades):
        if g >= min_grade and not in_climb:
            in_climb = True
            start = i
        elif in_climb and (g < end_grade or i == len(grades) - 1):
            end = i
            gain = smooth[end] - smooth[start]
            length = series["dists"][end] - series["dists"][start]
            if gain >= min_gain_m and length >= min_length_m:
                climbs.append(_climb_metrics(
                    start, end, series, smooth, grades,
                    ftp_w=ftp_w, weight_kg=weight_kg,
                    climb_index=len(climbs) + 1,
                ))
            in_climb = False
    return climbs


def compute_grade_bins(
    records: list[FitRecord],
) -> list[dict[str, Any]]:
    series = _usable_series(records)
    if series is None:
        return []
    smooth = _smooth_altitude(series["alts"])
    grades = _grades_from_series(series["dists"], smooth)
    return _grade_bin_rows(grades, series["powers"], series["cads"], series["hrs"])


def compute_climb_analysis(
    fit: FitSession,
    *,
    ftp_w: Optional[int] = None,
    weight_kg: Optional[float] = None,
) -> dict[str, Any]:
    """Full climb analysis for a FIT session."""
    climbs = detect_climbs(fit.records, ftp_w=ftp_w, weight_kg=weight_kg)
    bins = compute_grade_bins(fit.records)
    return {
        "climbs": climbs,
        "grade_bins": bins,
        "n_climbs": len(climbs),
    }


def match_named_climb(
    climb: dict[str, Any],
    named: dict[str, Any],
    *,
    start_radius_m: float = 100.0,
    length_tol: float = 0.15,
    gain_tol: float = 0.20,
    grade_tol_pp: float = 1.5,
) -> Optional[float]:
    """Return start-distance metres if climb matches named fingerprint, else None."""
    slat, slon = climb.get("start_lat"), climb.get("start_lon")
    rlat, rlon = named.get("ref_start_lat"), named.get("ref_start_lon")
    if None in (slat, slon, rlat, rlon):
        return None
    dist = haversine_m(float(slat), float(slon), float(rlat), float(rlon))
    if dist > start_radius_m:
        return None
    ref_len = float(named.get("ref_length_m") or 0)
    length = float(climb.get("length_m") or 0)
    if ref_len <= 0 or length <= 0:
        return None
    if abs(length - ref_len) / ref_len > length_tol:
        return None
    ref_gain = float(named.get("ref_gain_m") or 0)
    gain = float(climb.get("gain_m") or 0)
    gain_ok = ref_gain > 0 and abs(gain - ref_gain) / ref_gain <= gain_tol
    ref_grade = named.get("ref_avg_grade")
    grade = climb.get("avg_grade")
    grade_ok = (
        ref_grade is not None and grade is not None
        and abs(float(grade) - float(ref_grade)) <= grade_tol_pp
    )
    if not (gain_ok or grade_ok):
        return None
    return dist

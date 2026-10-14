#!/usr/bin/env python3
"""Physiologically-valid mean-maximal power on wall-clock 1 Hz series.

Rules (third-pass / Issue 1):
- Recorded 0 W counts as 0 (never dropped).
- Missing samples on the wall-clock axis are filled with 0 W (not skipped).
- Irregular Smart Recording is resampled onto a 1 s timestamp grid.
- Spike samples above MAX_SPIKE_W are rejected (treated as missing → 0 after fill).
- Rolling MMP windows are contiguous wall-clock seconds; no None-skipping.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

MAX_SPIKE_W = 1800.0
# Hold last value across short Smart Recording gaps; longer gaps → 0 W
SMART_HOLD_MAX_S = 8.0
# Plausibility bands for annual curves
RATIO_5_60 = (1.10, 1.35)
RATIO_20_60 = (1.03, 1.15)


@dataclass
class SeriesDiagnostics:
    n_raw_samples: int = 0
    n_zero_power: int = 0
    n_spike_rejected: int = 0
    n_negative_rejected: int = 0
    n_null_power_skipped: int = 0
    median_dt_s: Optional[float] = None
    mean_dt_s: Optional[float] = None
    smart_recording: bool = False
    wall_clock_s: int = 0
    n_ones_filled_zero: int = 0  # seconds filled with 0 (no sample / after spike)
    n_ones_held: int = 0         # seconds held from prior Smart sample
    zero_pct_of_wall: Optional[float] = None
    notes: list[str] = field(default_factory=list)


def _median(xs: list[float]) -> Optional[float]:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else 0.5 * (s[mid - 1] + s[mid])


def extract_power_pairs(
    records: Sequence[Any],
) -> tuple[list[tuple[float, float]], SeriesDiagnostics]:
    """(unix_ts, power_w) including zeros; rejects spikes/negatives."""
    diag = SeriesDiagnostics()
    pairs: list[tuple[float, float]] = []
    for r in records:
        ts = getattr(r, "timestamp", None)
        if ts is None:
            continue
        try:
            t = ts.timestamp() if hasattr(ts, "timestamp") else float(ts)
        except Exception:
            continue
        p = getattr(r, "power", None)
        diag.n_raw_samples += 1
        if p is None:
            diag.n_null_power_skipped += 1
            continue
        try:
            pf = float(p)
        except Exception:
            diag.n_null_power_skipped += 1
            continue
        if pf < 0:
            diag.n_negative_rejected += 1
            continue
        if pf > MAX_SPIKE_W:
            diag.n_spike_rejected += 1
            continue
        if pf == 0:
            diag.n_zero_power += 1
        pairs.append((t, pf))
    pairs.sort(key=lambda x: x[0])
    if len(pairs) >= 2:
        dts = [pairs[i + 1][0] - pairs[i][0] for i in range(len(pairs) - 1)]
        dts = [d for d in dts if 0 < d < 120]
        diag.median_dt_s = _median(dts)
        diag.mean_dt_s = (sum(dts) / len(dts)) if dts else None
        if diag.median_dt_s and diag.median_dt_s > 1.5:
            diag.smart_recording = True
            diag.notes.append(
                f"Smart/irregular recording suspected (median Δt={diag.median_dt_s:.2f}s)"
            )
    return pairs, diag


def pairs_from_stream_series(
    series: list,
    t0: Optional[float] = None,
) -> tuple[list[tuple[float, float]], SeriesDiagnostics]:
    """Rebuild (t,p) from a stored 1 Hz series (may contain nulls)."""
    diag = SeriesDiagnostics()
    pairs: list[tuple[float, float]] = []
    base = t0 if t0 is not None else 0.0
    for i, p in enumerate(series):
        diag.n_raw_samples += 1
        if p is None:
            diag.n_null_power_skipped += 1
            continue
        try:
            pf = float(p)
        except Exception:
            diag.n_null_power_skipped += 1
            continue
        if pf < 0:
            diag.n_negative_rejected += 1
            continue
        if pf > MAX_SPIKE_W:
            diag.n_spike_rejected += 1
            continue
        if pf == 0:
            diag.n_zero_power += 1
        pairs.append((base + i, pf))
    # Streams already claim 1 Hz — but may have dropped zeros as nulls
    diag.median_dt_s = 1.0
    return pairs, diag


def pairs_from_tcx_path(path) -> tuple[list[tuple[float, float]], SeriesDiagnostics]:
    """Parse TCX keeping explicit Watts including zeros."""
    import xml.etree.ElementTree as ET
    from datetime import datetime

    diag = SeriesDiagnostics()
    pairs: list[tuple[float, float]] = []

    def parse_time(s: str) -> Optional[float]:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None

    tree = ET.parse(path)
    for tp in tree.getroot().iter():
        tag = tp.tag.split("}")[-1] if "}" in tp.tag else tp.tag
        if tag != "Trackpoint":
            continue
        t_el = None
        watts = None
        saw_watts = False
        for child in tp:
            ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if ctag == "Time" and child.text:
                t_el = parse_time(child.text)
            if ctag == "Extensions":
                for ext in child.iter():
                    et = ext.tag.split("}")[-1] if "}" in ext.tag else ext.tag
                    if et == "Watts" and ext.text is not None:
                        saw_watts = True
                        try:
                            watts = float(ext.text)
                        except ValueError:
                            watts = None
        if t_el is None:
            continue
        diag.n_raw_samples += 1
        if not saw_watts or watts is None:
            diag.n_null_power_skipped += 1
            continue
        if watts < 0:
            diag.n_negative_rejected += 1
            continue
        if watts > MAX_SPIKE_W:
            diag.n_spike_rejected += 1
            continue
        if watts == 0:
            diag.n_zero_power += 1
        pairs.append((t_el, watts))
    pairs.sort(key=lambda x: x[0])
    if len(pairs) >= 2:
        dts = [pairs[i + 1][0] - pairs[i][0] for i in range(len(pairs) - 1)]
        dts = [d for d in dts if 0 < d < 120]
        diag.median_dt_s = _median(dts)
        diag.mean_dt_s = (sum(dts) / len(dts)) if dts else None
        if diag.median_dt_s and diag.median_dt_s > 1.5:
            diag.smart_recording = True
    return pairs, diag


def resample_wall_clock_1hz(
    pairs: list[tuple[float, float]],
    diag: Optional[SeriesDiagnostics] = None,
) -> tuple[list[float], SeriesDiagnostics]:
    """1 Hz wall-clock series; gaps filled with 0 W (zeros are conserved).

    Between samples closer than SMART_HOLD_MAX_S, hold last power (Smart Recording).
    Longer gaps fill with 0 so coast/stop/pause inflate neither mean nor window length.
    """
    diag = diag or SeriesDiagnostics()
    if not pairs:
        return [], diag
    t0 = pairs[0][0]
    t_end = pairs[-1][0]
    n = int(round(t_end - t0)) + 1
    if n <= 0:
        return [], diag
    if n > 3600 * 20:
        diag.notes.append(f"absurd wall span {n}s — truncated")
        n = 3600 * 20

    out = [0.0] * n
    # Mark which seconds received a sample or a smart-hold
    placed = [False] * n
    for t, p in pairs:
        idx = int(round(t - t0))
        if 0 <= idx < n:
            out[idx] = p
            placed[idx] = True

    # Smart-hold: between consecutive samples spanning ≤ SMART_HOLD_MAX_S, fill
    for i in range(len(pairs) - 1):
        t_a, p_a = pairs[i]
        t_b, _ = pairs[i + 1]
        dt = t_b - t_a
        if dt <= 0:
            continue
        if dt <= SMART_HOLD_MAX_S:
            i0 = int(round(t_a - t0))
            i1 = int(round(t_b - t0))
            for j in range(i0 + 1, i1):
                if 0 <= j < n and not placed[j]:
                    out[j] = p_a
                    placed[j] = True
                    diag.n_ones_held += 1
        # else leave as 0 (already initialized)

    diag.wall_clock_s = n
    diag.n_ones_filled_zero = sum(1 for v, pl in zip(out, placed) if not pl and v == 0.0)
    # recount zeros on wall clock
    n_zero = sum(1 for v in out if v == 0.0)
    diag.zero_pct_of_wall = round(100.0 * n_zero / n, 2) if n else None
    return out, diag


def best_mean_max_1hz(
    series: list[float],
    window_secs: int,
) -> tuple[Optional[float], int, Optional[float]]:
    """Best mean over contiguous wall-clock window.

    Returns (watts, windows_checked, peak_in_best_window).
    """
    if not series or window_secs <= 0 or len(series) < window_secs:
        if series and len(series) >= int(window_secs * 0.95):
            return round(sum(series) / len(series), 1), 1, max(series)
        return None, 0, None
    n = len(series)
    running = sum(series[:window_secs])
    best = running / window_secs
    best_i0 = 0
    checked = 1
    for i in range(window_secs, n):
        running += series[i] - series[i - window_secs]
        avg = running / window_secs
        checked += 1
        if avg > best:
            best = avg
            best_i0 = i - window_secs + 1
    peak = max(series[best_i0 : best_i0 + window_secs])
    return round(best, 1), checked, peak


def peak_to_mean_ok(window_secs: int, best: float, peak: float) -> bool:
    if best <= 0 or peak <= 0:
        return False
    ratio = peak / best
    if window_secs >= 1200 and ratio > 3.5:
        return False
    if window_secs >= 300 and ratio > 5.0:
        return False
    return True


MMP_SPECS = [
    ("mmp_5s", 5),
    ("mmp_1min", 60),
    ("mmp_2min", 120),
    ("mmp_5min", 300),
    ("mmp_20min", 1200),
    ("mmp_60min", 3600),
]


def compute_mmp_from_pairs(
    pairs: list[tuple[float, float]],
    diag: Optional[SeriesDiagnostics] = None,
) -> tuple[dict[str, Optional[float]], SeriesDiagnostics, list[float]]:
    series, diag = resample_wall_clock_1hz(pairs, diag)
    out: dict[str, Optional[float]] = {k: None for k, _ in MMP_SPECS}
    if len(series) < 5:
        diag.notes.append("series too short")
        return out, diag, series
    # median glitch guard on non-zero pedaling samples
    ped = [v for v in series if v > 0]
    if ped:
        med = _median(ped)
        if med and med > 500:
            diag.notes.append(f"rejected: pedaling median {med:.0f}W glitch")
            return out, diag, series

    windows_total = 0
    for key, win in MMP_SPECS:
        v, checked, peak = best_mean_max_1hz(series, win)
        windows_total += checked
        if v is None:
            continue
        if peak is not None and not peak_to_mean_ok(win, v, peak):
            diag.notes.append(f"{key} rejected peak/mean ({peak}/{v})")
            continue
        # Hard caps
        caps = {
            "mmp_5s": 2000, "mmp_1min": 1000, "mmp_2min": 800,
            "mmp_5min": 550, "mmp_20min": 450, "mmp_60min": 400,
        }
        if v > caps.get(key, 9999):
            diag.notes.append(f"{key}={v} above cap")
            continue
        out[key] = v
    diag.notes.append(f"windows_scanned={windows_total}")
    return out, diag, series


def compute_mmp_from_1hz_list(
    series_in: list,
) -> tuple[dict[str, Optional[float]], SeriesDiagnostics, list[float]]:
    """Consume a claimed 1 Hz series: None → 0 W; spikes rejected → 0."""
    diag = SeriesDiagnostics()
    series: list[float] = []
    for p in series_in:
        diag.n_raw_samples += 1
        if p is None:
            diag.n_null_power_skipped += 1
            series.append(0.0)
            continue
        try:
            pf = float(p)
        except Exception:
            diag.n_null_power_skipped += 1
            series.append(0.0)
            continue
        if pf < 0:
            diag.n_negative_rejected += 1
            series.append(0.0)
            continue
        if pf > MAX_SPIKE_W:
            diag.n_spike_rejected += 1
            series.append(0.0)
            continue
        if pf == 0:
            diag.n_zero_power += 1
        series.append(pf)
    diag.wall_clock_s = len(series)
    diag.median_dt_s = 1.0
    n_zero = sum(1 for v in series if v == 0.0)
    diag.zero_pct_of_wall = round(100.0 * n_zero / len(series), 2) if series else None
    # Build empty pairs path results via same caps/plausibility loop
    out: dict[str, Optional[float]] = {k: None for k, _ in MMP_SPECS}
    if len(series) < 5:
        return out, diag, series
    ped = [v for v in series if v > 0]
    if ped:
        med = _median(ped)
        if med and med > 500:
            diag.notes.append(f"rejected: pedaling median {med:.0f}W glitch")
            return out, diag, series
    windows_total = 0
    for key, win in MMP_SPECS:
        v, checked, peak = best_mean_max_1hz(series, win)
        windows_total += checked
        if v is None:
            continue
        if peak is not None and not peak_to_mean_ok(win, v, peak):
            diag.notes.append(f"{key} rejected peak/mean ({peak}/{v})")
            continue
        caps = {
            "mmp_5s": 2000, "mmp_1min": 1000, "mmp_2min": 800,
            "mmp_5min": 550, "mmp_20min": 450, "mmp_60min": 400,
        }
        if v > caps.get(key, 9999):
            diag.notes.append(f"{key}={v} above cap")
            continue
        out[key] = v
    diag.notes.append(f"windows_scanned={windows_total}")
    return out, diag, series


def annual_plausibility(by_year: list[dict]) -> list[str]:
    flags = []
    for b in by_year:
        y = b.get("year")
        m5, m20, m60 = b.get("mmp_5min"), b.get("mmp_20min"), b.get("mmp_60min")
        if m60 and m60 > 0 and m5:
            r = m5 / m60
            b["ratio_5_60"] = round(r, 3)
            if not (RATIO_5_60[0] <= r <= RATIO_5_60[1]):
                b["plausibility_fail"] = True
                flags.append(f"{y}: 5:60={r:.3f} outside {RATIO_5_60}")
        if m60 and m60 > 0 and m20:
            r = m20 / m60
            b["ratio_20_60"] = round(r, 3)
            if not (RATIO_20_60[0] <= r <= RATIO_20_60[1]):
                b["plausibility_fail"] = True
                flags.append(f"{y}: 20:60={r:.3f} outside {RATIO_20_60}")
    return flags


def half_decoupling_1hz(power: list[float], hr: list[float]) -> Optional[float]:
    """Full-ride first-half vs second-half Pw:HR % (HR drift − power drift)."""
    n = min(len(power), len(hr))
    if n < 600:
        return None
    mid = n // 2
    def avg(xs):
        return sum(xs) / len(xs) if xs else 0.0
    p1, p2 = avg(power[:mid]), avg(power[mid:n])
    h1, h2 = avg(hr[:mid]), avg(hr[mid:n])
    if p1 < 30 or p2 < 30 or h1 <= 0:
        return None
    return round((h2 - h1) / h1 * 100 - (p2 - p1) / p1 * 100, 1)


def estimate_cp_w_prime(mmp: dict[str, Optional[float]]) -> Optional[dict]:
    """Two-parameter CP from MMP-3min≈mmp_2min+ / 5 / 20 if available.

    Uses classic: W = CP·t + W'  →  P = CP + W'/t
    Fit CP, W' from (t=120,300,1200) where present via least squares.
    """
    pts = []
    for key, t in (("mmp_2min", 120), ("mmp_5min", 300), ("mmp_20min", 1200)):
        v = mmp.get(key)
        if v and v > 0:
            pts.append((t, float(v)))
    if len(pts) < 2:
        return None
    # P = CP + W'/t  →  linear regression of P vs 1/t
    xs = [1.0 / t for t, _ in pts]
    ys = [p for _, p in pts]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den <= 0:
        return None
    w_prime = num / den  # slope = W'
    cp = mean_y - w_prime * mean_x
    if cp <= 0 or w_prime <= 0:
        return None
    return {
        "cp_w": round(cp, 1),
        "w_prime_j": round(w_prime, 0),
        "w_prime_kj": round(w_prime / 1000.0, 2),
        "points": pts,
    }

#!/usr/bin/env python3
"""Stage 2 — consistency, rebuild-curve, peaks, power proxies, shortlist, Opus narrative."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

ARCHIVE_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = ARCHIVE_DIR / "activities_2009_2016.csv"
FINDINGS_PATH = ARCHIVE_DIR / "findings.json"
REPORT_PATH = ARCHIVE_DIR / "analysis_report.md"
SHORTLIST_PATH = ARCHIVE_DIR / "shortlist.csv"
CHARTS_DIR = ARCHIVE_DIR / "charts"

CYCLING_KEYS = {
    "cycling",
    "road_biking",
    "indoor_cycling",
    "mountain_biking",
    "gravel_cycling",
    "virtual_ride",
    "cyclocross",
    "bmx",
    "e_bike_fitness",
    "e_biking",
}

STATED_PEAKS = [
    {"year": 2012, "label": "device FTP ~242W / best 60-min climb 253W @ ~78kg → 3.24 W/kg"},
    {"year": 2015, "label": "critical power 282W, W' 7.0 kJ @ ~84.4kg → 3.34 W/kg"},
    {"year": 2016, "label": "device FTP 260W (Jan) @ ~82kg → 3.17 W/kg"},
]

CURRENT_CONTEXT = {
    "age": 49,
    "weight_kg": 92,
    "ftp_w": 220,
    "wkg": 2.39,
    "target_wkg": 3.5,
    "stretch_wkg": 4.0,
}


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = os.getenv("DOTENV_PATH")
    if env_path:
        load_dotenv(env_path)
    else:
        load_dotenv()
        fallback = Path.home() / ".ai_endurance_coach_over50" / ".env"
        if fallback.is_file():
            load_dotenv(fallback, override=False)


def _is_cycling(sport: str) -> bool:
    s = (sport or "").lower().strip()
    if not s:
        return False
    if s in CYCLING_KEYS:
        return True
    return "cycl" in s or "bik" in s


def load_activities(csv_path: Path):
    import pandas as pd

    df = pd.read_csv(csv_path)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    for col in (
        "duration_s", "distance_m", "elevation_gain_m", "avg_power", "max_power",
        "normalized_power", "max_power_20min", "avg_hr", "max_hr", "avg_cadence",
        "avg_speed_ms", "tss", "intensity_factor", "calories", "aerobic_te",
        "has_power_meter",
    ):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = float("nan")
    df["sport"] = df["sport"].fillna("").astype(str)
    df["is_cycling"] = df["sport"].map(_is_cycling)
    df["hours"] = df["duration_s"].fillna(0) / 3600.0
    df["week"] = df["date"].dt.to_period("W-MON").dt.start_time
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["year"] = df["date"].dt.year
    return df


# ── Consistency / gaps ───────────────────────────────────────────────────────

def find_cycling_gaps(bike, min_days: int = 21) -> list[dict]:
    if bike.empty:
        return []
    dates = sorted(bike["date"].dt.date.unique())
    gaps = []
    for i in range(len(dates) - 1):
        delta = (dates[i + 1] - dates[i]).days
        if delta >= min_days:
            gaps.append({
                "start": dates[i].isoformat(),
                "end": dates[i + 1].isoformat(),
                "length_days": delta,
                "length_weeks": round(delta / 7.0, 1),
            })
    return gaps


def longest_streak_ge3(bike) -> dict:
    if bike.empty:
        return {"weeks": 0, "start": None, "end": None}
    weekly = bike.groupby("week").size()
    weeks = sorted(weekly.index)
    best = cur = 0
    best_start = best_end = cur_start = None
    prev = None
    for w in weeks:
        count = int(weekly.loc[w])
        if count >= 3 and (prev is None or (w - prev).days == 7):
            if cur == 0:
                cur_start = w
            cur += 1
            if cur > best:
                best = cur
                best_start = cur_start
                best_end = w
        elif count >= 3:
            cur = 1
            cur_start = w
            if cur > best:
                best = cur
                best_start = cur_start
                best_end = w
        else:
            cur = 0
            cur_start = None
        prev = w
    return {
        "weeks": best,
        "start": best_start.date().isoformat() if best_start is not None else None,
        "end": best_end.date().isoformat() if best_end is not None else None,
    }


def annual_totals(df) -> list[dict]:
    rows = []
    for year, g in df.groupby("year"):
        bike = g[g["is_cycling"]]
        rows.append({
            "year": int(year),
            "hours_all": round(float(g["hours"].sum()), 1),
            "hours_cycling": round(float(bike["hours"].sum()), 1),
            "distance_km": round(float(bike["distance_m"].fillna(0).sum()) / 1000.0, 1),
            "elevation_m": round(float(bike["elevation_gain_m"].fillna(0).sum()), 0),
            "ride_count": int(len(bike)),
            "activity_count": int(len(g)),
            "elevation_note": "Elevation from older Edge devices is often unreliable.",
        })
    return rows


def weekly_hours_series(df, gaps: list[dict]) -> dict:
    if df.empty:
        return {"labels": [], "all_sports": [], "cycling": [], "gap_spans": []}
    all_w = df.groupby("week")["hours"].sum()
    bike = df[df["is_cycling"]]
    bike_w = bike.groupby("week")["hours"].sum() if not bike.empty else all_w * 0
    # Continuous weekly index
    start = all_w.index.min()
    end = all_w.index.max()
    labels, all_h, bike_h = [], [], []
    cur = start
    while cur <= end:
        labels.append(cur.date().isoformat())
        all_h.append(round(float(all_w.get(cur, 0.0)), 2))
        bike_h.append(round(float(bike_w.get(cur, 0.0)), 2))
        cur = cur + timedelta(days=7)
    gap_spans = [{"start": g["start"], "end": g["end"], "length_days": g["length_days"]} for g in gaps]
    return {"labels": labels, "all_sports": all_h, "cycling": bike_h, "gap_spans": gap_spans}


# ── Fitness proxies / rebuild ────────────────────────────────────────────────

def _aid_key(row) -> Optional[int]:
    aid = row.get("activity_id") if hasattr(row, "get") else None
    if aid is None:
        return None
    try:
        return int(float(aid))
    except (TypeError, ValueError):
        return None


def _ride_proxy(row, fit_mmp: Optional[dict[int, dict]] = None) -> tuple[Optional[float], str]:
    """Fitness proxy for one ride. Prefer FIT MMP when available."""
    aid = _aid_key(row)
    if fit_mmp and aid is not None and aid in fit_mmp:
        m = fit_mmp[aid]
        for key, kind in (
            ("mmp_20min", "fit_mmp_20min"),
            ("mmp_5min", "fit_mmp_5min"),
            ("mmp_1min", "fit_mmp_1min"),
        ):
            v = m.get(key)
            if v is not None:
                try:
                    return float(v), kind
                except (TypeError, ValueError):
                    pass

    dur = row.get("duration_s") or 0
    if row.get("max_power_20min") and not (isinstance(row["max_power_20min"], float) and math.isnan(row["max_power_20min"])):
        return float(row["max_power_20min"]), "max_power_20min"
    np_v = row.get("normalized_power")
    if np_v is not None and not (isinstance(np_v, float) and math.isnan(np_v)) and dur >= 45 * 60:
        return float(np_v), "normalized_power"
    avg_p = row.get("avg_power")
    if avg_p is not None and not (isinstance(avg_p, float) and math.isnan(avg_p)) and dur >= 60 * 60:
        return float(avg_p), "avg_power_60plus"
    if (
        np_v is not None and not (isinstance(np_v, float) and math.isnan(np_v))
        and row.get("avg_hr") and not (isinstance(row["avg_hr"], float) and math.isnan(row["avg_hr"]))
        and row["avg_hr"] > 0 and dur > 60 * 60
    ):
        return float(np_v) / float(row["avg_hr"]), "ef_np_hr"
    speed = row.get("avg_speed_ms")
    hr = row.get("avg_hr")
    if (
        speed is not None and not (isinstance(speed, float) and math.isnan(speed))
        and hr is not None and not (isinstance(hr, float) and math.isnan(hr))
        and hr > 0 and dur >= 60 * 60
    ):
        return float(speed) / float(hr), "speed_hr"
    return None, "none"


def rolling_4w_peak(weekly_series: list[tuple[date, Optional[float]]], at_idx: int) -> Optional[float]:
    window = [weekly_series[i][1] for i in range(max(0, at_idx - 3), at_idx + 1)]
    vals = [v for v in window if v is not None]
    return max(vals) if vals else None


def analyse_rebuild(bike, gaps: list[dict], fit_mmp: Optional[dict[int, dict]] = None) -> dict:
    """For each layoff ≥6 weeks, measure weeks to recover pre-layoff fitness proxy."""
    major = [g for g in gaps if g["length_days"] >= 42]
    layoffs = []
    trajectories = []
    fit_mmp = fit_mmp or {}

    if bike.empty:
        return {
            "central_estimate_weeks": None,
            "iqr": None,
            "n_full_recoveries": 0,
            "n_plateaued": 0,
            "proxy_notes": "No cycling activities in range.",
            "layoffs": [],
            "trajectories": [],
        }

    n_fit_baseline = 0
    n_fit_restart = 0

    for g in major:
        gap_start = date.fromisoformat(g["start"])
        restart = date.fromisoformat(g["end"])
        # Baseline: peak weekly proxy in 8 weeks before gap start
        pre_start = gap_start - timedelta(weeks=8)
        pre = bike[(bike["date"].dt.date > pre_start) & (bike["date"].dt.date <= gap_start)]
        baseline = None
        baseline_proxy = "none"
        baseline_used_fit = False
        for _, row in pre.iterrows():
            val, kind = _ride_proxy(row, fit_mmp)
            if val is None:
                continue
            if baseline is None or val > baseline:
                baseline, baseline_proxy = val, kind
                baseline_used_fit = kind.startswith("fit_mmp")
        if baseline_used_fit:
            n_fit_baseline += 1
        if baseline is None or baseline <= 0:
            layoffs.append({
                "layoff_start": g["start"],
                "layoff_end": g["end"],
                "layoff_weeks": g["length_weeks"],
                "restart_date": g["end"],
                "weeks_to_recover": None,
                "status": "no_baseline",
                "proxy_used": "none",
                "baseline": None,
                "recovered_to": None,
            })
            continue

        # Weekly series for 26 weeks after restart (or until next major gap)
        look_end = restart + timedelta(weeks=26)
        post = bike[(bike["date"].dt.date >= restart) & (bike["date"].dt.date <= look_end)]
        # First week after restart — count if any FIT-grounded ride
        restart_week_end = restart + timedelta(days=14)
        first_post = post[post["date"].dt.date <= restart_week_end]
        if any(
            (aid := _aid_key(row)) is not None and aid in fit_mmp
            for _, row in first_post.iterrows()
        ):
            n_fit_restart += 1

        # Build week grid from Monday of restart week
        week0 = restart - timedelta(days=restart.weekday())
        weekly: list[tuple[date, Optional[float]]] = []
        traj_weeks, traj_idx = [], []
        for wi in range(0, 27):
            ws = week0 + timedelta(weeks=wi)
            we = ws + timedelta(days=7)
            week_mask = (post["date"].dt.date >= ws) & (post["date"].dt.date < we)
            peak = None
            for _, row in post.loc[week_mask].iterrows():
                val, kind = _ride_proxy(row, fit_mmp)
                if val is None:
                    continue
                if baseline_proxy.startswith("fit_mmp") or baseline_proxy in (
                    "max_power_20min", "normalized_power", "avg_power_60plus",
                ):
                    if kind.startswith("fit_mmp") or kind in (
                        "max_power_20min", "normalized_power", "avg_power_60plus",
                    ):
                        pass
                    else:
                        continue
                elif baseline_proxy == "ef_np_hr" and kind != "ef_np_hr":
                    continue
                elif baseline_proxy == "speed_hr" and kind != "speed_hr":
                    continue
                if peak is None or val > peak:
                    peak = val
            weekly.append((ws, peak))
            r4 = rolling_4w_peak(weekly, wi)
            if r4 is not None:
                traj_weeks.append(wi)
                traj_idx.append(round(r4 / baseline, 3))

        weeks_to_recover = None
        status = "plateaued_lower"
        recovered_to = None
        for wi in range(len(weekly)):
            # Need a full 4-week window (wi >= 3) so early single hard rides
            # cannot falsely "recover" against a soft pre-layoff baseline.
            if wi < 3:
                continue
            window_vals = [weekly[i][1] for i in range(wi - 3, wi + 1)]
            if sum(1 for v in window_vals if v is not None) < 3:
                continue
            r4 = rolling_4w_peak(weekly, wi)
            if r4 is not None and r4 >= 0.95 * baseline:
                weeks_to_recover = wi
                status = "recovered"
                recovered_to = round(r4 / baseline, 3)
                break
        if status == "plateaued_lower":
            peaks = [rolling_4w_peak(weekly, i) for i in range(3, len(weekly))]
            peaks = [p for p in peaks if p is not None]
            recovered_to = round(max(peaks) / baseline, 3) if peaks else None

        layoffs.append({
            "layoff_start": g["start"],
            "layoff_end": g["end"],
            "layoff_weeks": g["length_weeks"],
            "restart_date": g["end"],
            "weeks_to_recover": weeks_to_recover,
            "status": status,
            "proxy_used": baseline_proxy,
            "baseline": round(baseline, 3),
            "recovered_to": recovered_to,
        })
        trajectories.append({
            "label": f"{g['start']} ({g['length_weeks']}w layoff)",
            "weeks": traj_weeks,
            "index": traj_idx,
            "proxy": baseline_proxy,
        })

    recovered_weeks = [
        L["weeks_to_recover"] for L in layoffs
        if L["status"] == "recovered" and L["weeks_to_recover"] is not None
    ]
    central = None
    iqr = None
    if recovered_weeks:
        recovered_weeks = sorted(recovered_weeks)
        mid = len(recovered_weeks) // 2
        if len(recovered_weeks) % 2:
            central = recovered_weeks[mid]
        else:
            central = (recovered_weeks[mid - 1] + recovered_weeks[mid]) / 2
        q1 = recovered_weeks[max(0, len(recovered_weeks) // 4)]
        q3 = recovered_weeks[min(len(recovered_weeks) - 1, (3 * len(recovered_weeks)) // 4)]
        iqr = [q1, q3]

    power_era = [
        L for L in layoffs
        if L["proxy_used"] in (
            "max_power_20min", "normalized_power", "avg_power_60plus",
            "fit_mmp_20min", "fit_mmp_5min", "fit_mmp_1min",
        )
    ]
    hr_era = [L for L in layoffs if L["proxy_used"] in ("ef_np_hr", "speed_hr")]

    notes = (
        "Proxy ladder: FIT MMP-20 → max_power_20min → NP (≥45 min) → avg power (≥60 min) → "
        "EF (NP/HR) → speed/HR."
        if fit_mmp else
        "Proxy ladder: max_power_20min → NP (≥45 min) → avg power (≥60 min) → "
        "EF (NP/HR) → speed/HR. Not true mean-maximal power."
    )
    if fit_mmp:
        notes += (
            f" FIT-grounded baselines: {n_fit_baseline}/{len(major)}; "
            f"FIT restarts (first 14d): {n_fit_restart}/{len(major)}."
        )

    return {
        "central_estimate_weeks": central,
        "iqr": iqr,
        "n_full_recoveries": len(recovered_weeks),
        "n_plateaued": sum(1 for L in layoffs if L["status"] == "plateaued_lower"),
        "n_no_baseline": sum(1 for L in layoffs if L["status"] == "no_baseline"),
        "n_layoffs_with_fit_baseline": n_fit_baseline,
        "n_layoffs_with_fit_restart": n_fit_restart,
        "proxy_notes": notes,
        "power_era_recoveries": [
            L["weeks_to_recover"] for L in power_era if L["status"] == "recovered"
        ],
        "hr_era_recoveries": [
            L["weeks_to_recover"] for L in hr_era if L["status"] == "recovered"
        ],
        "layoffs": layoffs,
        "trajectories": trajectories,
    }


# ── Peaks ────────────────────────────────────────────────────────────────────

def peak_blocks(bike, top_n: int = 5) -> dict:
    if bike.empty:
        return {"top_blocks": [], "note": "No cycling data"}
    weekly = bike.groupby("week").agg(
        hours=("hours", "sum"),
        load=("tss", "sum"),
        rides=("activity_id", "count"),
        te=("aerobic_te", "mean"),
        np=("normalized_power", "mean"),
        dur_median=("duration_s", "median"),
    )
    # Prefer load when present; else hours * te; else hours
    scores = []
    weeks = list(weekly.index)
    for i, w in enumerate(weeks):
        block_weeks = weeks[i : i + 6]
        if len(block_weeks) < 6:
            break
        sub = weekly.loc[block_weeks]
        load_sum = float(sub["load"].fillna(0).sum())
        hours_sum = float(sub["hours"].sum())
        te_mean = float(sub["te"].mean()) if sub["te"].notna().any() else None
        if load_sum > 0:
            score = load_sum
            score_kind = "garmin_training_load"
        elif te_mean:
            score = hours_sum * te_mean
            score_kind = "hours_x_te"
        else:
            score = hours_sum
            score_kind = "hours"
        # Intensity spread proxy: CV of NP when available
        np_vals = sub["np"].dropna()
        intensity_spread = round(float(np_vals.std() / np_vals.mean()), 3) if len(np_vals) >= 2 and np_vals.mean() else None
        scores.append({
            "start": w.date().isoformat(),
            "end": (block_weeks[-1] + timedelta(days=6)).date().isoformat(),
            "score": round(score, 1),
            "score_kind": score_kind,
            "hours": round(hours_sum, 1),
            "rides": int(sub["rides"].sum()),
            "rides_per_week": round(float(sub["rides"].mean()), 1),
            "median_duration_min": round(float(sub["dur_median"].median()) / 60.0, 0) if sub["dur_median"].notna().any() else None,
            "intensity_spread_np_cv": intensity_spread,
        })
    scores.sort(key=lambda x: x["score"], reverse=True)
    top = scores[:top_n]
    # Accidental consistency: top block score > 1.5× median of all block scores
    if scores:
        med = sorted(s["score"] for s in scores)[len(scores) // 2]
        for t in top:
            t["accidental_consistency"] = bool(med > 0 and t["score"] >= 1.5 * med)
    return {"top_blocks": top, "n_blocks_scored": len(scores)}


# ── Power proxies by year ────────────────────────────────────────────────────

def power_proxies_by_year(bike) -> list[dict]:
    rows = []
    for year, g in bike.groupby("year"):
        powered = g[g["normalized_power"].notna() | g["avg_power"].notna() | g["max_power_20min"].notna()]
        if powered.empty:
            rows.append({"year": int(year), "has_power": False})
            continue

        def best_in_bucket(min_s: int, col: str) -> Optional[float]:
            sub = powered[(powered["duration_s"] >= min_s) & powered[col].notna()]
            if sub.empty:
                return None
            return round(float(sub[col].max()), 1)

        best_np_20 = best_in_bucket(20 * 60, "normalized_power")
        best_np_45 = best_in_bucket(45 * 60, "normalized_power")
        best_np_60 = best_in_bucket(60 * 60, "normalized_power")
        best_avg_60 = best_in_bucket(60 * 60, "avg_power")
        best_20min_field = best_in_bucket(0, "max_power_20min")
        best_avg_5 = best_in_bucket(5 * 60, "avg_power")  # weak short proxy
        ratio = None
        if best_np_20 and best_np_60 and best_np_60 > 0:
            ratio = round(best_np_20 / best_np_60, 3)
        note = None
        if ratio is not None and ratio < 1.05:
            note = (
                "Flat 20-to-60 NP ratio — likely few short hard efforts that year "
                "(proxy caveat, not true MMP)."
            )
        rows.append({
            "year": int(year),
            "has_power": True,
            "best_avg_power_ge5min": best_avg_5,
            "best_max_power_20min": best_20min_field,
            "best_np_ge20min": best_np_20,
            "best_np_ge45min": best_np_45,
            "best_np_ge60min": best_np_60,
            "best_avg_power_ge60min": best_avg_60,
            "np20_to_np60_ratio": ratio,
            "caveat": note,
            "disclaimer": "Whole-ride means only — not mean-maximal power from streams.",
        })
    return rows


def contradiction_checks(proxies: list[dict]) -> list[dict]:
    out = []
    by_year = {p["year"]: p for p in proxies}
    for stated in STATED_PEAKS:
        p = by_year.get(stated["year"])
        if not p or not p.get("has_power"):
            out.append({
                "year": stated["year"],
                "stated": stated["label"],
                "archive": "No power data in archive for this year",
                "conflicts": False,
            })
            continue
        best = max(
            v for v in [
                p.get("best_max_power_20min"),
                p.get("best_np_ge20min"),
                p.get("best_np_ge45min"),
                p.get("best_np_ge60min"),
                p.get("best_avg_power_ge60min"),
            ] if v is not None
        ) if any(
            p.get(k) for k in (
                "best_max_power_20min", "best_np_ge20min", "best_np_ge45min",
                "best_np_ge60min", "best_avg_power_ge60min",
            )
        ) else None
        # Loose comparison: flag if archive best is >15% below the stated peak watts
        stated_w = {2012: 253, 2015: 282, 2016: 260}[stated["year"]]
        conflicts = bool(best is not None and best < stated_w * 0.85)
        out.append({
            "year": stated["year"],
            "stated": stated["label"],
            "archive_best_proxy_w": best,
            "stated_peak_w": stated_w,
            "conflicts": conflicts,
            "note": (
                f"Archive best whole-ride proxy {best} W vs stated ~{stated_w} W — "
                "summaries understate true MMP; contradiction only if gap is large."
                if best is not None else "No comparable proxy"
            ),
        })
    return out


# ── Shortlist ────────────────────────────────────────────────────────────────

def build_shortlist(bike, gaps: list[dict], limit: int = 35) -> list[dict]:
    if bike.empty:
        return []
    scores: dict[Any, dict] = {}

    def bump(aid, date_s, reason, pts, row):
        if aid is None or (isinstance(aid, float) and math.isnan(aid)):
            return
        key = int(aid) if not isinstance(aid, str) else aid
        ent = scores.setdefault(key, {
            "activity_id": key,
            "date": date_s,
            "score": 0.0,
            "reasons": [],
            "np": None,
            "duration_s": None,
            "avg_hr": None,
        })
        ent["score"] += pts
        if reason not in ent["reasons"]:
            ent["reasons"].append(reason)
        if row is not None:
            ent["date"] = row["date"].date().isoformat() if hasattr(row["date"], "date") else str(row["date"])[:10]
            if row.get("normalized_power") == row.get("normalized_power"):
                ent["np"] = round(float(row["normalized_power"]), 1) if row.get("normalized_power") == row.get("normalized_power") else ent["np"]
            if row.get("duration_s") == row.get("duration_s"):
                ent["duration_s"] = round(float(row["duration_s"]))
            if row.get("avg_hr") == row.get("avg_hr"):
                ent["avg_hr"] = round(float(row["avg_hr"]))

    # First rides after major layoffs
    major = [g for g in gaps if g["length_days"] >= 42]
    for g in major:
        restart = date.fromisoformat(g["end"])
        after = bike[bike["date"].dt.date >= restart].head(5)
        for i, (_, row) in enumerate(after.iterrows()):
            bump(row.get("activity_id"), None, f"post_layoff_{g['start']}", 50 - i * 5, row)

    # Highest NP
    np_rides = bike[bike["normalized_power"].notna()].nlargest(15, "normalized_power")
    for _, row in np_rides.iterrows():
        bump(row.get("activity_id"), None, "high_np", 30, row)

    # Longest rides
    long_rides = bike.nlargest(15, "duration_s")
    for _, row in long_rides.iterrows():
        bump(row.get("activity_id"), None, "longest", 20, row)

    # Anomalous EF
    ef = bike[
        bike["normalized_power"].notna()
        & bike["avg_hr"].notna()
        & (bike["avg_hr"] > 0)
        & (bike["duration_s"] > 3600)
    ].copy()
    if not ef.empty:
        ef["ef"] = ef["normalized_power"] / ef["avg_hr"]
        for _, row in ef.nlargest(8, "ef").iterrows():
            bump(row.get("activity_id"), None, "high_ef", 25, row)
        for _, row in ef.nsmallest(5, "ef").iterrows():
            bump(row.get("activity_id"), None, "low_ef", 15, row)

    ranked = sorted(scores.values(), key=lambda x: x["score"], reverse=True)[:limit]
    for r in ranked:
        r["reason"] = ", ".join(r.pop("reasons"))
    return ranked


# ── Charts (PNG) ─────────────────────────────────────────────────────────────

def write_charts(findings: dict) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print("matplotlib not installed — skipping PNGs", flush=True)
        return

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    wh = findings.get("charts", {}).get("weekly_hours", {})
    labels = wh.get("labels") or []
    if labels:
        fig, ax = plt.subplots(figsize=(12, 4))
        xs = [datetime.fromisoformat(l) for l in labels]
        ax.plot(xs, wh.get("all_sports") or [], label="All sports", color="#94a3b8", linewidth=1)
        ax.plot(xs, wh.get("cycling") or [], label="Cycling", color="#60a5fa", linewidth=1.5)
        for g in wh.get("gap_spans") or []:
            try:
                ax.axvspan(
                    datetime.fromisoformat(g["start"]),
                    datetime.fromisoformat(g["end"]),
                    color="#f59e0b",
                    alpha=0.15,
                )
            except Exception:
                pass
        ax.set_ylabel("Hours / week")
        ax.set_title("Weekly training hours (cycling gaps ≥21d shaded)")
        ax.legend(loc="upper right")
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        fig.tight_layout()
        fig.savefig(CHARTS_DIR / "training_hours_timeline.png", dpi=120)
        plt.close(fig)

    traj = findings.get("charts", {}).get("rebuild_trajectories", {}).get("series") or []
    if traj:
        fig, ax = plt.subplots(figsize=(10, 5))
        for s in traj[:8]:
            ax.plot(s.get("weeks") or [], s.get("index") or [], label=s.get("label", "")[:24], linewidth=1.4)
        ax.axhline(0.95, color="#22c55e", linestyle="--", linewidth=1, label="95% recovery")
        ax.set_xlabel("Weeks since restart")
        ax.set_ylabel("Fitness index (÷ pre-layoff baseline)")
        ax.set_title("Rebuild trajectories after major layoffs")
        ax.legend(fontsize=7, loc="best")
        fig.tight_layout()
        fig.savefig(CHARTS_DIR / "rebuild_trajectories.png", dpi=120)
        plt.close(fig)

    pyl = findings.get("charts", {}).get("power_by_year", {})
    years = pyl.get("years") or []
    if years:
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.plot(years, pyl.get("best_np_60") or [], marker="o", label="Best NP ≥60 min")
        ax.plot(years, pyl.get("best_np_20") or [], marker="s", label="Best NP ≥20 min")
        ax.plot(years, pyl.get("best_20min_field") or [], marker="^", label="maxPowerTwentyMinutes")
        ax.set_xlabel("Year")
        ax.set_ylabel("Watts (whole-ride proxy)")
        ax.set_title("Power-duration proxies by year (not true MMP)")
        ax.legend()
        fig.tight_layout()
        fig.savefig(CHARTS_DIR / "power_duration_by_year.png", dpi=120)
        plt.close(fig)


# ── AI narrative ─────────────────────────────────────────────────────────────

def generate_ai_narrative(findings: dict, force: bool = False) -> Optional[dict]:
    existing = findings.get("ai_narrative")
    if existing and existing.get("markdown") and not force:
        print("AI narrative cached — skip (use --force-ai to regenerate)", flush=True)
        return existing

    _load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ANTHROPIC_API_KEY not set — skipping Opus narrative", flush=True)
        return None

    sys.path.insert(0, str(ARCHIVE_DIR.parent))
    import anthropic
    from ai_endurance_coach_over50.llm import MODEL_COACH

    compact = {
        "rebuild": {
            k: findings["rebuild"].get(k)
            for k in (
                "central_estimate_weeks", "iqr", "n_full_recoveries", "n_plateaued",
                "proxy_notes", "layoffs", "power_era_recoveries", "hr_era_recoveries",
            )
        },
        "rebuild_fit": {
            k: (findings.get("rebuild_fit") or {}).get(k)
            for k in (
                "central_estimate_weeks", "iqr", "n_full_recoveries", "n_plateaued",
                "n_layoffs_with_fit_baseline", "proxy_notes",
            )
        },
        "mmp_by_year": (findings.get("mmp") or {}).get("by_year"),
        "mmp_notes": (findings.get("mmp") or {}).get("curve_notes"),
        "contradictions_fit": findings.get("contradictions_fit"),
        "gaps_ge21d_count": len(findings.get("gaps") or []),
        "major_layoffs_ge6w": [
            g for g in (findings.get("gaps") or []) if g.get("length_days", 0) >= 42
        ][:12],
        "annual_totals": findings.get("consistency", {}).get("annual_totals"),
        "longest_streak": findings.get("consistency", {}).get("longest_streak_weeks"),
        "peaks": findings.get("peaks"),
        "power_proxies_by_year": findings.get("power_proxies_by_year"),
        "contradictions_summary_proxies": findings.get("contradictions"),
        "current": CURRENT_CONTEXT,
        "reversal_note": (
            "FIT-grounded rebuild is 5.0 weeks on shortlist_v2 (agrees with summary). "
            "An earlier 7.5-week FIT estimate came from sparse v1 shortlist coverage only — "
            "not evidence that summary was optimistic."
        ),
    }

    prompt = f"""You are an endurance coach analysing one athlete's Garmin history (2009–2016).

Athlete context: {CURRENT_CONTEXT['age']}-year-old male cyclist, currently {CURRENT_CONTEXT['ftp_w']} W at ~{CURRENT_CONTEXT['weight_kg']} kg ({CURRENT_CONTEXT['wkg']} W/kg). Target {CURRENT_CONTEXT['target_wkg']} W/kg (stretch {CURRENT_CONTEXT['stretch_wkg']}). Historical peaks were on unstructured on/off training.

QUANTITATIVE FINDINGS (do not invent numbers beyond these):
```json
{json.dumps(compact, indent=2, default=str)}
```

IMPORTANT FACTS (do not contradict):
- True MMP (MEASURED_MMP) EXISTS for shortlist FIT/TCX streams under mmp_by_year. Never say "no true MMP".
- Prefer rebuild_fit central estimate when present; it currently agrees with summary at ~5 weeks.
- Tag watts as MEASURED_MMP, DEVICE_SETTING, PROXY, or MODELLED. DEVICE_SETTING FTP is not a measurement contradiction.
- Weight/power: coupled 0/3/6 W lost per kg — do not treat weight as an independent lever holding watts constant.
- Flat year-level 20:60 ratios can be steady plateau rides (same-ride near-constant power), not necessarily a bug.

Write markdown with:
1. A prominent **rebuild-rate verdict** (central estimate in weeks; fast vs slow responder).
2. Implications for time/path back toward {CURRENT_CONTEXT['target_wkg']} W/kg from {CURRENT_CONTEXT['wkg']}.
   WEIGHT RULES: do NOT treat weight loss as an independent lever that holds watts constant.
   If discussing kg drop, show a W/kg band under assumptions of 0, 3, and 6 W lost per kg.
   Sequence: training consistency first, modest deficit under it, MMP-20 as guardrail.
3. What the consistency/gaps pattern says about this athlete.
4. Peak blocks / accidental consistency observations.
5. Power: prefer MEASURED_MMP year peaks when present; summary proxies are secondary.
   Tag lore carefully: device FTP = DEVICE_SETTING.
6. Data-quality caveats (TSS here is Garmin training load; elevation unreliable; MMP is shortlist_v2 not exhaustive).

Be direct. Prefer their personal rebuild numbers over generic 3–5% FTP/year rules."""

    print(f"Calling {MODEL_COACH} for narrative…", flush=True)
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=MODEL_COACH,
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    return {
        "model": MODEL_COACH,
        "markdown": text.strip(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


# ── Report markdown ──────────────────────────────────────────────────────────

def write_report(findings: dict) -> None:
    rb = findings.get("rebuild") or {}
    lines = [
        "# Garmin history analysis (2009–2016)",
        "",
        f"_Generated {findings.get('generated_at', '')}_",
        "",
        "## Rebuild-rate estimate (headline)",
        "",
    ]
    if rb.get("central_estimate_weeks") is not None:
        iqr = rb.get("iqr") or []
        lines.append(
            f"**Central estimate: {rb['central_estimate_weeks']} weeks** "
            f"to recover prior fitness after a major layoff "
            f"(median across {rb.get('n_full_recoveries', 0)} full recoveries"
            + (f"; IQR {iqr[0]}–{iqr[1]}" if len(iqr) == 2 else "")
            + f"; {rb.get('n_plateaued', 0)} plateaued lower)."
        )
    else:
        lines.append("**No full recoveries measured** — insufficient proxy data or layoffs.")
    lines += ["", rb.get("proxy_notes") or "", ""]

    ai = findings.get("ai_narrative") or {}
    if ai.get("markdown"):
        lines += ["## Coach narrative (Claude Opus)", "", ai["markdown"], ""]

    lines += ["## Layoff rebuild table", "",
              "| Layoff start | Weeks off | Restart | Weeks to recover | Status | Proxy |",
              "|---|---:|---|---:|---|---|"]
    for L in rb.get("layoffs") or []:
        lines.append(
            f"| {L.get('layoff_start')} | {L.get('layoff_weeks')} | {L.get('restart_date')} | "
            f"{L.get('weeks_to_recover') if L.get('weeks_to_recover') is not None else '—'} | "
            f"{L.get('status')} | {L.get('proxy_used')} |"
        )

    cons = findings.get("consistency") or {}
    lines += ["", "## Consistency", "",
              f"Longest streak of weeks with ≥3 rides: **{cons.get('longest_streak_weeks', {}).get('weeks')}** "
              f"({cons.get('longest_streak_weeks', {}).get('start')} → {cons.get('longest_streak_weeks', {}).get('end')})",
              "",
              "### Annual totals",
              "",
              "| Year | Hours (all) | Hours (bike) | Distance km | Elev m | Rides |",
              "|---|---:|---:|---:|---:|---:|"]
    for a in cons.get("annual_totals") or []:
        lines.append(
            f"| {a['year']} | {a['hours_all']} | {a['hours_cycling']} | {a['distance_km']} | "
            f"{a['elevation_m']} | {a['ride_count']} |"
        )
    lines.append("")
    lines.append("_Elevation from older Edge devices is unreliable._")
    lines.append("")
    lines.append(f"Cycling gaps ≥21 days: **{len(findings.get('gaps') or [])}**")
    lines.append("")

    lines += ["## Peak 6-week blocks", ""]
    for i, b in enumerate((findings.get("peaks") or {}).get("top_blocks") or [], 1):
        flag = " ⚠️ accidental-consistency outlier" if b.get("accidental_consistency") else ""
        lines.append(
            f"{i}. {b['start']} → {b['end']}: score {b['score']} ({b['score_kind']}), "
            f"{b['hours']} h, {b['rides']} rides (~{b['rides_per_week']}/wk){flag}"
        )

    lines += ["", "## Power proxies by year", "",
              "_Not true mean-maximal power — whole-ride summary fields only._", ""]
    for p in findings.get("power_proxies_by_year") or []:
        if not p.get("has_power"):
            lines.append(f"- **{p['year']}**: no power data")
            continue
        lines.append(
            f"- **{p['year']}**: NP≥20 {p.get('best_np_ge20min')} · NP≥60 {p.get('best_np_ge60min')} · "
            f"max20min {p.get('best_max_power_20min')} · ratio20/60 {p.get('np20_to_np60_ratio')}"
            + (f" — {p['caveat']}" if p.get("caveat") else "")
        )

    lines += ["", "## Stated peaks vs archive", ""]
    for c in findings.get("contradictions") or []:
        flag = " **CONFLICT**" if c.get("conflicts") else ""
        lines.append(f"- {c['year']}: stated {c['stated']}; archive best {c.get('archive_best_proxy_w')}{flag}")
        if c.get("note"):
            lines.append(f"  - {c['note']}")

    lines += ["", "## Shortlist preview", ""]
    for s in (findings.get("shortlist_preview") or [])[:15]:
        lines.append(
            f"- `{s['activity_id']}` {s.get('date')} score={s.get('score')} — {s.get('reason')}"
        )
    lines += ["", f"Full list: `{SHORTLIST_PATH.name}`", "",
              "## Charts", "",
              "- `charts/training_hours_timeline.png`",
              "- `charts/rebuild_trajectories.png`",
              "- `charts/power_duration_by_year.png`",
              ""]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_shortlist_csv(rows: list[dict]) -> None:
    import csv
    cols = ["activity_id", "date", "reason", "score", "np", "duration_s", "avg_hr"]
    with SHORTLIST_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


# ── Main orchestration ───────────────────────────────────────────────────────

def run(csv_path: Path, force_ai: bool = False) -> dict:
    print(f"Loading {csv_path}…", flush=True)
    df = load_activities(csv_path)
    if df.empty:
        sys.exit(f"No activities in {csv_path}")
    bike = df[df["is_cycling"]].copy()
    print(f"  {len(df)} activities, {len(bike)} cycling", flush=True)

    gaps = find_cycling_gaps(bike, min_days=21)
    print(f"  {len(gaps)} cycling gaps ≥21d", flush=True)
    streak = longest_streak_ge3(bike)
    annual = annual_totals(df)
    rebuild = analyse_rebuild(bike, gaps)
    print(
        f"  rebuild central estimate: {rebuild.get('central_estimate_weeks')} weeks "
        f"({rebuild.get('n_full_recoveries')} recovered, {rebuild.get('n_plateaued')} plateaued)",
        flush=True,
    )
    peaks = peak_blocks(bike)
    proxies = power_proxies_by_year(bike)
    contradictions = contradiction_checks(proxies)
    shortlist = build_shortlist(bike, gaps)
    write_shortlist_csv(shortlist)

    period_start = df["date"].min().date().isoformat()
    period_end = df["date"].max().date().isoformat()

    # Chart series for Chart.js + PNG
    power_chart = {
        "years": [p["year"] for p in proxies if p.get("has_power")],
        "best_np_20": [p.get("best_np_ge20min") for p in proxies if p.get("has_power")],
        "best_np_60": [p.get("best_np_ge60min") for p in proxies if p.get("has_power")],
        "best_20min_field": [p.get("best_max_power_20min") for p in proxies if p.get("has_power")],
    }

    findings: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "period": {"start": period_start, "end": period_end},
        "rebuild": {k: v for k, v in rebuild.items() if k != "trajectories"},
        "gaps": gaps,
        "consistency": {
            "longest_streak_weeks": streak,
            "annual_totals": annual,
            "n_activities": int(len(df)),
            "n_cycling": int(len(bike)),
        },
        "peaks": peaks,
        "power_proxies_by_year": proxies,
        "contradictions": contradictions,
        "shortlist_preview": shortlist[:25],
        "charts": {
            "weekly_hours": weekly_hours_series(df, gaps),
            "rebuild_trajectories": {"series": rebuild.get("trajectories") or []},
            "power_by_year": power_chart,
        },
        "current_athlete": CURRENT_CONTEXT,
        "data_quality_notes": [
            "tss column is Garmin activityTrainingLoad, not Coggan TSS.",
            "Elevation from older Edge devices is unreliable.",
            "Power fields are whole-ride summaries — not mean-maximal power.",
            "True 5s/1/5/20/60 MMP requires FIT files from shortlist.csv.",
        ],
    }

    # Preserve prior ai_narrative if present and not forcing; always keep Stage 3 keys
    prev: dict[str, Any] = {}
    if FINDINGS_PATH.is_file():
        try:
            prev = json.loads(FINDINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    if prev.get("ai_narrative") and not force_ai:
        findings["ai_narrative"] = prev["ai_narrative"]
    for key in (
        "mmp", "rebuild_fit", "contradictions_fit", "ai_narrative_mmp",
        "coupled_weight_power", "activity_provenance_note",
    ):
        if key in prev and key not in findings:
            findings[key] = prev[key]
    # Merge chart overlays from Stage 3
    if prev.get("charts"):
        findings.setdefault("charts", {}).update({
            k: v for k, v in prev["charts"].items()
            if k not in findings.get("charts", {})
        })
    # Prefer FIT contradictions on the report path when MMP exists
    if findings.get("contradictions_fit"):
        notes = findings.setdefault("data_quality_notes", [])
        note = "True MMP (MEASURED_MMP) lives under findings.mmp; DEVICE_SETTING FTP is not a measurement."
        if note not in notes:
            notes.append(note)

    write_charts(findings)

    narrative = generate_ai_narrative(findings, force=force_ai)
    if narrative:
        findings["ai_narrative"] = narrative

    FINDINGS_PATH.write_text(json.dumps(findings, indent=2, default=str), encoding="utf-8")
    try:
        sys.path.insert(0, str(ARCHIVE_DIR.parent))
        from ai_endurance_coach_over50.archive_findings import publish_findings
        published = publish_findings(FINDINGS_PATH)
        print(f"Published → {published}", flush=True)
    except Exception as e:
        print(f"Warn: could not publish findings to home archive: {e}", flush=True)
    write_report(findings)
    print(f"Wrote {FINDINGS_PATH}", flush=True)
    print(f"Wrote {REPORT_PATH}", flush=True)
    print(f"Wrote {SHORTLIST_PATH} ({len(shortlist)} rows)", flush=True)
    return findings


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    p.add_argument("--force-ai", action="store_true")
    args = p.parse_args()
    if not args.csv.is_file():
        sys.exit(f"CSV not found: {args.csv} — run garmin_fetch.py first")
    run(args.csv, force_ai=args.force_ai)


if __name__ == "__main__":
    main()

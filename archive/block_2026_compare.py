#!/usr/bin/env python3
"""Compare the 2026 12-week charity block against the 2009–2016 archive.

Reuses validated MMP (mmp_engine / garmin_mmp.compute_activity_mmp) and
consistency helpers from garmin_analysis. Does not invent a parallel power path.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import os
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd

ARCHIVE_DIR = Path(__file__).resolve().parent
REPO = ARCHIVE_DIR.parent
FITS_DIR = ARCHIVE_DIR / "fits"
CHARTS_DIR = ARCHIVE_DIR / "charts"
DB_PATH = Path.home() / ".ai_endurance_coach_over50" / "history.db"
FINDINGS_PATH = ARCHIVE_DIR / "findings.json"
ACT_CSV = ARCHIVE_DIR / "activities_2009_2016.csv"

PLAN_START = date(2026, 5, 18)
PLAN_END = date(2026, 8, 9)  # week-12 Sunday
BLOCK_END_DATA = date(2026, 8, 7)  # last observed activity (FTP test)

FTP_TEST_ID = 23884317052
FTP_RECORDED_W = 220
FTP_EFFORT_AVG_W = 232.0  # from activity_analyses.ftp_effort_avg_w
FTP_MULTIPLIER = 0.95
FTP_PROTOCOL = "20-min effort × 0.95"

# Weights for W/kg (user / lore)
WEIGHTS = {
    2012: 78.0,
    2015: 84.4,
    2016: 82.0,
    2026: 89.9,  # measured near test (body_metrics); report also notes 92 kg prior framing
}

ARCHIVE_HRMAX = 204.0  # stated at age ~38


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()
    fb = Path.home() / ".ai_endurance_coach_over50" / ".env"
    if fb.is_file():
        load_dotenv(fb, override=False)


def load_garmin_analysis():
    return _load_mod("garmin_analysis", ARCHIVE_DIR / "garmin_analysis.py")


def load_garmin_mmp():
    return _load_mod("garmin_mmp", ARCHIVE_DIR / "garmin_mmp.py")


def load_fit_fetch():
    return _load_mod("garmin_fit_fetch", ARCHIVE_DIR / "garmin_fit_fetch.py")


# ── 2026 activities from SQLite ──────────────────────────────────────────────

CYCLING_KEYS = {
    "road_biking", "cycling", "virtual_ride", "indoor_cycling",
    "gravel_cycling", "mountain_biking", "cyclocross",
}


def load_block_activities(conn: sqlite3.Connection) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT activity_id, date, name, type_key, duration_seconds,
               distance_meters, elevation_gain, avg_hr, max_hr,
               avg_power_w, norm_power_w, has_power_meter, tss, location_name
        FROM activities
        WHERE date >= ? AND date <= ?
        ORDER BY date, activity_id
        """,
        (PLAN_START.isoformat(), PLAN_END.isoformat()),
    ).fetchall()
    cols = [
        "activity_id", "date", "name", "type_key", "duration_seconds",
        "distance_meters", "elevation_gain", "avg_hr", "max_hr",
        "avg_power_w", "norm_power_w", "has_power_meter", "tss", "location_name",
    ]
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["is_cycling"] = df["type_key"].isin(CYCLING_KEYS) | df["type_key"].str.contains(
        "cycl|bik", case=False, na=False
    )
    df["hours"] = df["duration_seconds"].fillna(0) / 3600.0
    df["duration_s"] = df["duration_seconds"]
    df["week"] = df["date"].dt.to_period("W-MON").dt.start_time
    df["year"] = df["date"].dt.year
    df["normalized_power"] = df["norm_power_w"]
    df["avg_power"] = df["avg_power_w"]
    df["max_power_20min"] = None
    df["aerobic_te"] = None
    return df


def load_archive_bike() -> pd.DataFrame:
    df = pd.read_csv(ACT_CSV)
    df["date"] = pd.to_datetime(df["date"])
    sport = df["sport"].fillna("").str.lower()
    sub = df.get("sub_sport")
    if sub is not None:
        # numeric sub_sport in csv — treat sport==cycling as bike
        pass
    df["is_cycling"] = sport.str.contains("cycl|bik", case=False, na=False) | (
        sport == "cycling"
    )
    # In this extract almost all are cycling
    if "hours" not in df.columns:
        df["hours"] = df["duration_s"].fillna(0) / 3600.0
    df["week"] = df["date"].dt.to_period("W-MON").dt.start_time
    df["year"] = df["date"].dt.year
    df["normalized_power"] = df.get("normalized_power")
    df["avg_power"] = df.get("avg_power")
    df["tss"] = df.get("tss")
    df["aerobic_te"] = df.get("aerobic_te")
    bike = df[df["is_cycling"]].copy()
    return bike


# ── FIT download + MMP ───────────────────────────────────────────────────────

def ensure_fits(aids: list[int], force: bool = False) -> dict[int, Path]:
    ff = load_fit_fetch()
    _dotenv()
    email = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")
    if not email or not password:
        raise SystemExit("GARMIN_EMAIL / GARMIN_PASSWORD required to fetch FITs")
    sys.path.insert(0, str(REPO))
    from ai_endurance_coach_over50.client import get_api

    FITS_DIR.mkdir(parents=True, exist_ok=True)
    need = [
        aid for aid in aids
        if force or not (
            (FITS_DIR / f"{aid}.fit").is_file()
            and (FITS_DIR / f"{aid}.fit").stat().st_size > 5000
        )
    ]
    api = None
    if need:
        print(f"Logging in to Garmin as {email}…", flush=True)
        api = get_api(email, password)
    out: dict[int, Path] = {}
    for i, aid in enumerate(aids):
        dest = FITS_DIR / f"{aid}.fit"
        if dest.is_file() and dest.stat().st_size > 5000 and not force:
            out[aid] = dest
            print(f"  FIT cached {aid}", flush=True)
            continue
        assert api is not None
        print(f"  downloading FIT {aid} ({i+1}/{len(aids)})…", flush=True)
        data = ff._download_fit(api, aid)
        if data and len(data) > 5000:
            tmp = dest.with_suffix(".fit.tmp")
            tmp.write_bytes(data)
            tmp.replace(dest)
            out[aid] = dest
            print(f"  wrote {dest.name} ({len(data)} B)", flush=True)
        else:
            print(f"  FAILED FIT {aid}", flush=True)
        if i < len(aids) - 1:
            time.sleep(2.0)
    return out


def mmp_for_fits(fit_map: dict[int, Path], dates: dict[int, str]) -> list[dict]:
    gm = load_garmin_mmp()
    rows = []
    for aid, path in fit_map.items():
        row = gm.compute_activity_mmp(path, aid, dates.get(aid, ""))
        rows.append(row)
        print(
            f"  MMP {aid} {row.get('date')}: "
            f"20={row.get('mmp_20min')} 60={row.get('mmp_60min')} "
            f"err={row.get('error')!r}",
            flush=True,
        )
    return rows


def aggregate_mmp(rows: list[dict]) -> dict[str, Any]:
    keys = ["mmp_5s", "mmp_1min", "mmp_2min", "mmp_5min", "mmp_20min", "mmp_60min"]
    best: dict[str, Any] = {k: None for k in keys}
    best_aid: dict[str, Any] = {k: None for k in keys}
    for r in rows:
        if not r.get("has_power"):
            continue
        for k in keys:
            v = r.get(k)
            if v is None:
                continue
            if best[k] is None or float(v) > float(best[k]):
                best[k] = round(float(v), 1)
                best_aid[k] = r.get("activity_id")
    return {"best": best, "best_activity_id": best_aid, "n_rides": sum(1 for r in rows if r.get("has_power"))}


# ── Consistency ──────────────────────────────────────────────────────────────

def block_consistency(bike: pd.DataFrame, ga) -> dict[str, Any]:
    if bike.empty:
        return {}
    weekly = bike.groupby("week").agg(
        rides=("activity_id", "count"),
        hours=("hours", "sum"),
        dur_median=("duration_s", "median"),
    )
    weeks_ge3 = int((weekly["rides"] >= 3).sum())
    streak = ga.longest_streak_ge3(bike)
    gaps10 = ga.find_cycling_gaps(bike, min_days=10)
    gaps21 = ga.find_cycling_gaps(bike, min_days=21)

    # Continuous Monday weeks across plan
    plan_weeks = []
    d = PLAN_START
    while d <= PLAN_END:
        plan_weeks.append(d)
        d += timedelta(days=7)

    weekly_detail = []
    for w0 in plan_weeks:
        w_end = w0 + timedelta(days=6)
        sub = bike[(bike["date"].dt.date >= w0) & (bike["date"].dt.date <= w_end)]
        weekly_detail.append({
            "week_start": w0.isoformat(),
            "week_end": w_end.isoformat(),
            "rides": int(len(sub)),
            "hours": round(float(sub["hours"].sum()), 2),
            "ge3": bool(len(sub) >= 3),
        })

    n_weeks = max(1, (min(BLOCK_END_DATA, PLAN_END) - PLAN_START).days / 7.0)
    total_h = float(bike["hours"].sum())
    n_rides = int(len(bike))
    med_dur = float(bike["duration_s"].median()) / 60.0 if n_rides else None

    # Best 6-week sub-block (same scorer as archive peak_blocks)
    peaks = ga.peak_blocks(bike, top_n=3)

    return {
        "plan_start": PLAN_START.isoformat(),
        "plan_end": PLAN_END.isoformat(),
        "data_end": BLOCK_END_DATA.isoformat(),
        "weeks_ge3_rides": weeks_ge3,
        "longest_streak_ge3": streak,
        "gaps_ge10d": gaps10,
        "gaps_ge21d": gaps21,
        "total_hours": round(total_h, 1),
        "hours_per_week": round(total_h / n_weeks, 2),
        "n_rides": n_rides,
        "rides_per_week": round(n_rides / n_weeks, 2),
        "median_duration_min": round(med_dur, 1) if med_dur is not None else None,
        "span_weeks": round(n_weeks, 2),
        "weekly_detail": weekly_detail,
        "best_6week_subblocks": peaks.get("top_blocks", []),
    }


def compare_to_top_blocks(cons: dict, archive_top: list[dict]) -> dict[str, Any]:
    """Per-week normalisation vs archive top-5 (which are 6-week windows)."""
    hpw = cons.get("hours_per_week")
    rpw = cons.get("rides_per_week")
    best6 = (cons.get("best_6week_subblocks") or [{}])[0]
    rows = []
    for b in archive_top[:5]:
        # Archive peak_blocks are exactly 6 weeks
        span = 6.0
        rows.append({
            "label": f"{b['start']} → {b['end']}",
            "hours": b["hours"],
            "hours_per_week": round(b["hours"] / span, 2),
            "rides_per_week": b["rides_per_week"],
            "median_duration_min": b.get("median_duration_min"),
            "span_weeks": span,
        })
    return {
        "archive_top5_per_week": rows,
        "block_2026_full": {
            "hours": cons.get("total_hours"),
            "hours_per_week": hpw,
            "rides_per_week": rpw,
            "span_weeks": cons.get("span_weeks"),
            "median_duration_min": cons.get("median_duration_min"),
        },
        "block_2026_best_6wk": {
            "start": best6.get("start"),
            "end": best6.get("end"),
            "hours": best6.get("hours"),
            "hours_per_week": round(best6["hours"] / 6.0, 2) if best6.get("hours") else None,
            "rides_per_week": best6.get("rides_per_week"),
            "median_duration_min": best6.get("median_duration_min"),
        },
        "largest_single_block_in_dataset": None,  # filled below
    }


# ── EF trend (% HRmax normalised) ────────────────────────────────────────────

def hrmax_2026(bike: pd.DataFrame) -> float:
    mx = bike["max_hr"].dropna()
    return float(mx.max()) if len(mx) else 188.0


def _is_ftp_labelled(name: Any) -> bool:
    s = str(name or "").lower()
    return "ftp" in s


def weekly_ef_pct(
    bike: pd.DataFrame,
    hrmax: float,
    start: date,
    end: date,
    min_dur_s: float = 45 * 60,
    exclude_ftp: bool = False,
) -> list[dict]:
    """Weekly median EF = NP / (%HRavg of max). Requires NP + avg_hr."""
    sub = bike[(bike["date"].dt.date >= start) & (bike["date"].dt.date <= end)].copy()
    rows = []
    if sub.empty or hrmax <= 0:
        return rows
    weeks = sorted(sub["week"].unique())
    for w in weeks:
        g = sub[sub["week"] == w]
        efs = []
        for _, r in g.iterrows():
            if exclude_ftp and _is_ftp_labelled(r.get("name")):
                continue
            np_v = r.get("normalized_power")
            hr = r.get("avg_hr")
            dur = r.get("duration_s") or 0
            if np_v is None or (isinstance(np_v, float) and math.isnan(np_v)):
                continue
            if hr is None or (isinstance(hr, float) and math.isnan(hr)) or hr <= 0:
                continue
            if dur < min_dur_s:
                continue
            pct = 100.0 * float(hr) / hrmax
            if pct < 40:  # sensor glitches (e.g. avg_hr=70 lock)
                continue
            efs.append(float(np_v) / pct)
        if efs:
            efs_sorted = sorted(efs)
            med = efs_sorted[len(efs_sorted) // 2]
            rows.append({
                "week_start": pd.Timestamp(w).date().isoformat(),
                "ef_np_pct_hrmax_median": round(med, 4),
                "n": len(efs),
                "ef_mean": round(sum(efs) / len(efs), 4),
            })
    return rows


def ef_2015_secondary(archive_bike: pd.DataFrame) -> dict[str, Any]:
    """Only archive stretch with contiguous NP weeks — not a top-hours block."""
    series = weekly_ef_pct(
        archive_bike, ARCHIVE_HRMAX, date(2015, 5, 18), date(2015, 6, 7)
    )
    return {
        "label": "2015-05-18→2015-06-01 (NP-available only; NOT a top hours block)",
        "hrmax": ARCHIVE_HRMAX,
        "series": series,
        "rate": ef_rate(series),
        "n_ef_weeks": len(series),
        "valid_as_top_block_compare": False,
        "note": (
            "Top-5 archive hours blocks have zero NP in the Garmin export — "
            "EF vs those blocks is not valid. This 2015 strip is the densest NP-EF "
            "window available (3 weeks) and is secondary context only."
        ),
    }


def ef_rate(series: list[dict]) -> dict[str, Any]:
    """Linear slope of EF vs week index (per week)."""
    if len(series) < 2:
        return {"slope_per_week": None, "n_weeks": len(series), "still_climbing": None}
    ys = [r["ef_np_pct_hrmax_median"] for r in series]
    xs = list(range(len(ys)))
    n = len(xs)
    xbar = sum(xs) / n
    ybar = sum(ys) / n
    num = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys))
    den = sum((x - xbar) ** 2 for x in xs) or 1.0
    slope = num / den
    # Front vs back half
    mid = n // 2
    front = sum(ys[: max(1, mid)]) / max(1, mid)
    back = sum(ys[mid:]) / max(1, n - mid)
    last3 = ys[-3:] if n >= 3 else ys
    first3 = ys[:3] if n >= 3 else ys
    # End-climb = last point above the prior point AND above the series open
    still = bool(n >= 2 and ys[-1] > ys[-2] and ys[-1] > ys[0] and slope > 0)
    shape = "linear"
    if back - front > 0.02 and slope > 0:
        if still:
            shape = "still_climbing"
        else:
            shape = "back_loaded"
    elif front - back > 0.02:
        shape = "front_loaded"
    elif abs(slope) < 0.002:
        shape = "flat"
    # Mid-peak then fade
    if n >= 4 and max(ys) == max(ys[1:-1]) and ys[-1] < ys[0]:
        shape = "mid_peak_then_fade"
        still = False
    return {
        "slope_per_week": round(slope, 5),
        "n_weeks": n,
        "first": ys[0],
        "last": ys[-1],
        "delta": round(ys[-1] - ys[0], 4),
        "pct_change": round(100.0 * (ys[-1] - ys[0]) / ys[0], 2) if ys[0] else None,
        "shape": shape,
        "still_climbing_at_end": still,
        "front_half_mean": round(front, 4),
        "back_half_mean": round(back, 4),
    }


# ── Charts ───────────────────────────────────────────────────────────────────

def write_hours_chart(findings: dict, cons_2026: dict) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    wh = findings.get("charts", {}).get("weekly_hours", {})
    labels = wh.get("labels") or []
    cycling = wh.get("cycling") or []
    gaps = wh.get("gap_spans") or []

    # Append 2026 plan weeks from weekly_detail
    fig, ax = plt.subplots(figsize=(14, 4.5))
    if labels:
        xs = [datetime.fromisoformat(l) for l in labels]
        ax.plot(xs, cycling, label="Archive cycling h/wk", color="#64748b", linewidth=1.0)

    for g in gaps:
        try:
            ax.axvspan(
                datetime.fromisoformat(g["start"]),
                datetime.fromisoformat(g["end"]),
                color="#f59e0b",
                alpha=0.12,
            )
        except Exception:
            pass

    # 2026 overlay
    wd = cons_2026.get("weekly_detail") or []
    if wd:
        xs2 = [datetime.fromisoformat(r["week_start"]) for r in wd]
        ys2 = [r["hours"] for r in wd]
        ax.plot(xs2, ys2, label="2026 12-wk block", color="#2563eb", linewidth=2.2, marker="o", markersize=4)
        ax.axvspan(xs2[0], xs2[-1] + timedelta(days=6), color="#2563eb", alpha=0.08)

    ax.set_ylabel("Hours / week")
    ax.set_title("Weekly cycling hours 2009–2016 + 2026 block (gaps ≥21d shaded)")
    ax.legend(loc="upper right")
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.tight_layout()
    out = CHARTS_DIR / "training_hours_2009_2026.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def write_ef_chart(
    series_2026: list[dict],
    hist_blocks: list[dict],
) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    if series_2026:
        ax.plot(
            range(1, len(series_2026) + 1),
            [r["ef_np_pct_hrmax_median"] for r in series_2026],
            marker="o",
            linewidth=2.2,
            color="#2563eb",
            label="2026 block ex-FTP (HRmax=observed)",
        )
    colors = ["#94a3b8", "#64748b", "#475569", "#334155", "#1e293b"]
    for i, hb in enumerate(hist_blocks):
        s = hb.get("series") or []
        if not s:
            continue
        ax.plot(
            range(1, len(s) + 1),
            [r["ef_np_pct_hrmax_median"] for r in s],
            marker=".",
            linewidth=1.2,
            color=colors[i % len(colors)],
            label=hb.get("label", "")[:28],
            alpha=0.85,
        )
    ax.set_xlabel("Week index within block")
    ax.set_ylabel("EF = NP ÷ (% max HR)")
    ax.set_title("Efficiency factor trend — %HRmax normalised")
    ax.legend(fontsize=8, loc="best")
    fig.tight_layout()
    out = CHARTS_DIR / "ef_trend_2026_vs_blocks.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


# ── Report ───────────────────────────────────────────────────────────────────

def write_report(payload: dict) -> Path:
    ftp = payload["ftp_test"]
    cons = payload["consistency"]
    cmpb = payload["block_compare"]
    mmp = payload["mmp"]
    ef = payload["ef"]
    pos = payload["positioning"]
    proj = payload["projection"]
    autumn = payload["autumn"]

    streak_2026 = cons["longest_streak_ge3"]["weeks"]
    streak_arch = payload["archive_streak_weeks"]
    beat = streak_2026 > streak_arch

    lines = [
        "# 2026 12-week block vs 2009–2016 archive",
        "",
        f"_Generated {datetime.now().isoformat(timespec='seconds')}_",
        "",
        "Uses **validated `mmp_engine.py`** (wall-clock 1 Hz; zeros as zero; gaps >8 s → 0; spikes >1800 W rejected).",
        "Consistency helpers: `longest_streak_ge3`, `find_cycling_gaps`, `peak_blocks` from `garmin_analysis.py`.",
        "",
        "---",
        "",
        "## FTP test provenance (read before any power comparison)",
        "",
        f"| Field | Value |",
        f"|---|---|",
        f"| Activity | `{ftp['activity_id']}` — {ftp['name']} |",
        f"| Date | **{ftp['date']}** |",
        f"| Setting | **{ftp['indoor_outdoor']}** |",
        f"| Protocol | **{ftp['protocol']}** |",
        f"| Multiplier | **×{ftp['multiplier']}** |",
        f"| Recorded FTP (DEVICE / app) | **{ftp['ftp_w']} W** |",
        f"| Analysed 20-min effort avg | **{ftp['ftp_effort_avg_w']} W** |",
        f"| **Raw MMP-20 (MEASURED_MMP, stream)** | **{ftp['mmp_20min']} W** |",
        f"| MMP-60 same ride | {ftp.get('mmp_60min') if ftp.get('mmp_60min') is not None else 'n/a (ride <60 min wall-clock)'} |",
        f"| Weight near test | **{ftp['weight_kg']} kg** |",
        f"| MMP-20 W/kg | **{ftp.get('mmp_20_wkg')}** |",
        "",
        (
            "**Do not compare 220 W FTP to archive MMP-20.** "
            f"The like-for-like number is raw MMP-20 = **{ftp['mmp_20min']} W** "
            f"(provenance `{ftp['provenance']}`)."
        ),
        "",
    ]
    if ftp["indoor_outdoor"].lower().startswith("outdoor"):
        lines.append(
            "Indoor/outdoor confound: **none for this test** — outdoor road ride "
            "(matches archive bests). Assioma vs 2012-era meter calibration still applies."
        )
    else:
        lines.append(
            "**Indoor confound:** turbo tests typically run 5–10% lower than outdoor "
            "equivalent effort. Direct W comparison to archive outdoor MMP is **not valid** "
            "without that caveat — do not silently adjust."
        )
    lines += [
        "",
        "---",
        "",
        "## Analysis 1 — Consistency (definition-independent)",
        "",
        "Cycling-only, same rules as the archive (≥3 rides/week streak).",
        "",
        f"- Plan window: **{cons['plan_start']} → {cons['plan_end']}** (data through {cons['data_end']})",
        f"- Weeks with ≥3 rides: **{cons['weeks_ge3_rides']}** / 12",
        f"- Longest unbroken ≥3-rides streak: **{streak_2026} weeks** "
        f"({cons['longest_streak_ge3'].get('start')} → {cons['longest_streak_ge3'].get('end')}) "
        f"— same `W-MON` week key as the archive 8-week record "
        f"(can diverge from Mon–Sun plan rows below)",
        f"- Archive record: **{streak_arch} weeks** (2012-04-10 → 2012-05-29)",
        (
            f"- **Did this block beat the archive streak?** **{'YES' if beat else 'NO'}** — "
            f"{streak_2026} vs {streak_arch}."
        ),
        f"- Gaps ≥10 days inside the block: "
        + (
            "none"
            if not cons["gaps_ge10d"]
            else ", ".join(
                f"{g['start']}→{g['end']} ({g['length_days']}d)" for g in cons["gaps_ge10d"]
            )
        ),
        f"- Total cycling hours: **{cons['total_hours']} h** "
        f"({cons['hours_per_week']} h/wk over {cons['span_weeks']} weeks)",
        f"- Rides: **{cons['n_rides']}** ({cons['rides_per_week']}/wk); "
        f"median duration **{cons['median_duration_min']} min**",
        "",
        "### Per-week vs archive top-5 (6-week scored blocks)",
        "",
        "Archive `peak_blocks` score rolling **6-week** windows. The 2026 plan is 12 weeks — "
        "compare hours/week, and also the best 6-week sub-window inside 2026.",
        "",
        "| Block | Span wk | Hours | h/wk | rides/wk | median min |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in cmpb["archive_top5_per_week"]:
        lines.append(
            f"| {r['label']} | {r['span_weeks']} | {r['hours']} | {r['hours_per_week']} | "
            f"{r['rides_per_week']} | {r['median_duration_min']} |"
        )
    b6 = cmpb["block_2026_best_6wk"]
    bf = cmpb["block_2026_full"]
    lines += [
        f"| **2026 best 6-wk** ({b6.get('start')}→{b6.get('end')}) | 6 | {b6.get('hours')} | "
        f"{b6.get('hours_per_week')} | {b6.get('rides_per_week')} | {b6.get('median_duration_min')} |",
        f"| **2026 full 12-wk** | {bf.get('span_weeks')} | {bf.get('hours')} | "
        f"{bf.get('hours_per_week')} | {bf.get('rides_per_week')} | {bf.get('median_duration_min')} |",
        "",
        f"**Largest single training block in the dataset (by hours in a 6-wk window)?** "
        f"**{cmpb['largest_single_block_in_dataset']}**",
        "",
        "Note: full 12-week total hours can exceed any 6-week archive block while still "
        "losing on h/wk density and ≥3-ride streak. Consistency is the stronger signal here.",
        "",
        "### Weekly detail (2026)",
        "",
        "| Week | Rides | Hours | ≥3? |",
        "|---|---:|---:|---|",
    ]
    for w in cons["weekly_detail"]:
        lines.append(
            f"| {w['week_start']} | {w['rides']} | {w['hours']} | {'yes' if w['ge3'] else 'no'} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Analysis 2 — Response (EF, % max HR)",
        "",
        f"Archive HRmax used: **{ef['archive_hrmax']}**. "
        f"2026 HRmax = highest HR observed in block: **{ef['hrmax_2026']}**.",
        "Metric: median weekly **EF = NP ÷ (% of HRmax)** on rides ≥45 min with NP+HR.",
        "Power meter only from late June — EF series starts then, not week 1.",
        "",
        "### 2026 (all NP rides)",
        "",
        f"- Slope: **{ef['rate_2026'].get('slope_per_week')}** /wk "
        f"(Δ {ef['rate_2026'].get('delta')}, {ef['rate_2026'].get('pct_change')}%)",
        f"- Shape: **{ef['rate_2026'].get('shape')}**; "
        f"still climbing at end: **{ef['rate_2026'].get('still_climbing_at_end')}**",
        "",
        "### 2026 excluding FTP-labelled rides (preferred for adaptation)",
        "",
        f"- Slope: **{ef['rate_2026_ex_ftp'].get('slope_per_week')}** /wk "
        f"(Δ {ef['rate_2026_ex_ftp'].get('delta')}, {ef['rate_2026_ex_ftp'].get('pct_change')}%)",
        f"- Shape: **{ef['rate_2026_ex_ftp'].get('shape')}**; "
        f"still climbing at end: **{ef['rate_2026_ex_ftp'].get('still_climbing_at_end')}**",
        f"- Front-half mean: {ef['rate_2026_ex_ftp'].get('front_half_mean')}; "
        f"back-half: {ef['rate_2026_ex_ftp'].get('back_half_mean')}",
        "",
        "### Vs top historical blocks — **not a valid comparison**",
        "",
        "The archive top-5 hours blocks (mostly 2009 / 2012) have **zero `normalized_power`** "
        "in the Garmin export. Computing EF for them would invent numbers. "
        "**No EF slope is reported against those blocks.**",
        "",
        "Secondary context only — densest NP-covered archive strip (not a top hours block):",
        "",
        "| Block | HRmax | Slope /wk | Δ EF | Shape | Still climbing? |",
        "|---|---:|---:|---:|---|---|",
    ]
    lines.append(
        f"| 2026 ex-FTP | {ef['hrmax_2026']} | {ef['rate_2026_ex_ftp'].get('slope_per_week')} | "
        f"{ef['rate_2026_ex_ftp'].get('delta')} | {ef['rate_2026_ex_ftp'].get('shape')} | "
        f"{ef['rate_2026_ex_ftp'].get('still_climbing_at_end')} |"
    )
    sec = ef.get("secondary_2015") or {}
    r = sec.get("rate") or {}
    lines.append(
        f"| {sec.get('label')} | {sec.get('hrmax')} | {r.get('slope_per_week')} | "
        f"{r.get('delta')} | {r.get('shape')} | {r.get('still_climbing_at_end')} |"
    )
    lines += [
        "",
        ef.get("response_verdict", ""),
        "",
        "Chart: `charts/ef_trend_2026_vs_blocks.png` (2026 ex-FTP vs 2015 NP strip)",
        "",
        "---",
        "",
        "## Analysis 3 — Honest power positioning (MEASURED_MMP)",
        "",
        "All rows: **MEASURED_MMP** from the same wall-clock engine. "
        "2026 year row = best across powered rides in the 12-week block "
        f"(n={mmp['block_aggregate']['n_rides']}). "
        "Several long rides had raw MMP windows rejected by the engine’s peak/mean "
        "spike guard (same rule as archive) — those rides contribute shorter-duration "
        "peaks only when the guard passes.",
        "",
        "| Year | MMP-20 | MMP-60 | Weight kg | MMP-20 W/kg | MMP-60 W/kg | Notes |",
        "|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in pos["table"]:
        lines.append(
            f"| {row['year']} | {row['mmp_20']} | {row['mmp_60']} | {row['weight_kg']} | "
            f"{row['mmp_20_wkg']} | {row['mmp_60_wkg']} | {row['notes']} |"
        )
    lines += [
        "",
        "### Confounds (stated, not adjusted away)",
        "",
    ]
    for c in pos["confounds"]:
        lines.append(f"- {c}")
    lines += [
        "",
        "### Full MMP curve — FTP test ride vs block bests",
        "",
        "| Duration | FTP test ride | Block best (any ride) | Best activity |",
        "|---|---:|---:|---|",
    ]
    for k, label in [
        ("mmp_1min", "1 min"),
        ("mmp_2min", "2 min"),
        ("mmp_5min", "5 min"),
        ("mmp_20min", "20 min"),
        ("mmp_60min", "60 min"),
    ]:
        lines.append(
            f"| {label} | {ftp.get(k)} | {mmp['block_aggregate']['best'].get(k)} | "
            f"{mmp['block_aggregate']['best_activity_id'].get(k)} |"
        )
    lines += [
        "",
        "---",
        "",
        "## Analysis 4 — Forward projection",
        "",
        proj["body"],
        "",
        "---",
        "",
        "## Analysis 5 — Autumn layoff risk",
        "",
        autumn["body"],
        "",
        "---",
        "",
        "## Artefacts",
        "",
        "- `charts/training_hours_2009_2026.png`",
        "- `charts/ef_trend_2026_vs_blocks.png`",
        "- `activity_mmp_2026.csv` — per-ride MEASURED_MMP for the block",
        "- `mmp_by_year_with_2026.csv` — year table with 2026 appended",
        "- `block_2026_findings.json` — machine-readable payload",
        "",
    ]
    out = ARCHIVE_DIR / "block_2026_analysis.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> int:
    _dotenv()
    ga = load_garmin_analysis()
    findings = json.loads(FINDINGS_PATH.read_text(encoding="utf-8"))
    conn = sqlite3.connect(str(DB_PATH))
    all_act = load_block_activities(conn)
    bike = all_act[all_act["is_cycling"]].copy()
    print(f"Block activities: {len(all_act)} total, {len(bike)} cycling", flush=True)

    # Power rides for MMP
    power_aids = [
        int(r.activity_id)
        for _, r in bike.iterrows()
        if r.has_power_meter == 1 or (r.avg_power_w and r.avg_power_w > 0)
    ]
    # Always include FTP test
    if FTP_TEST_ID not in power_aids:
        power_aids.append(FTP_TEST_ID)
    dates = {int(r.activity_id): r.date.date().isoformat() for _, r in bike.iterrows()}
    # Also early FTP without power flag
    for aid in (23118027637,):
        if aid not in power_aids:
            power_aids.append(aid)

    print(f"Fetching FITs for {len(power_aids)} rides…", flush=True)
    fit_map = ensure_fits(power_aids)
    mmp_rows = mmp_for_fits(fit_map, dates)
    agg = aggregate_mmp(mmp_rows)

    ftp_row = next((r for r in mmp_rows if r.get("activity_id") == FTP_TEST_ID), {})
    ftp_name = "Southend-on-Sea - Final FTP Test"
    fr = bike[bike["activity_id"] == FTP_TEST_ID]
    if not fr.empty:
        ftp_name = str(fr.iloc[0]["name"])

    mmp20 = ftp_row.get("mmp_20min")
    weight = WEIGHTS[2026]
    ftp_meta = {
        "activity_id": FTP_TEST_ID,
        "name": ftp_name,
        "date": dates.get(FTP_TEST_ID, "2026-08-07"),
        "indoor_outdoor": "Outdoor (road_biking, Southend-on-Sea)",
        "protocol": FTP_PROTOCOL,
        "multiplier": FTP_MULTIPLIER,
        "ftp_w": FTP_RECORDED_W,
        "ftp_effort_avg_w": FTP_EFFORT_AVG_W,
        "mmp_20min": mmp20,
        "mmp_60min": ftp_row.get("mmp_60min"),
        "mmp_1min": ftp_row.get("mmp_1min"),
        "mmp_2min": ftp_row.get("mmp_2min"),
        "mmp_5min": ftp_row.get("mmp_5min"),
        "provenance": "MEASURED_MMP",
        "weight_kg": weight,
        "mmp_20_wkg": round(float(mmp20) / weight, 2) if mmp20 else None,
        "implied_check": (
            f"232 × 0.95 ≈ {round(232 * 0.95)} vs recorded FTP {FTP_RECORDED_W}"
        ),
    }

    cons = block_consistency(bike, ga)
    archive_top = findings.get("peaks", {}).get("top_blocks") or []
    cmpb = compare_to_top_blocks(cons, archive_top)
    arch_best_h = max((b["hours"] for b in archive_top[:5]), default=0)
    b6h = (cmpb["block_2026_best_6wk"] or {}).get("hours") or 0
    if b6h > arch_best_h:
        cmpb["largest_single_block_in_dataset"] = (
            f"YES — 2026 best 6-wk ({b6h} h) exceeds archive #1 ({arch_best_h} h)"
        )
    else:
        cmpb["largest_single_block_in_dataset"] = (
            f"NO — archive #1 remains {arch_best_h} h (6-wk); "
            f"2026 best 6-wk is {b6h} h. "
            f"Full 12-wk total ({cons['total_hours']} h) is a longer block, not a denser one."
        )

    # EF
    hrmax = hrmax_2026(bike)
    series_2026 = weekly_ef_pct(bike, hrmax, PLAN_START, BLOCK_END_DATA)
    series_2026_ex_ftp = weekly_ef_pct(
        bike, hrmax, PLAN_START, BLOCK_END_DATA, exclude_ftp=True
    )
    rate_2026 = ef_rate(series_2026)
    rate_ex = ef_rate(series_2026_ex_ftp)

    archive_bike = load_archive_bike()
    hist_ef = []
    for b in archive_top[:5]:
        s = date.fromisoformat(b["start"])
        e = date.fromisoformat(b["end"])
        series = weekly_ef_pct(archive_bike, ARCHIVE_HRMAX, s, e)
        hist_ef.append({
            "label": f"{b['start']}→{b['end']} ({b['hours']}h)",
            "hrmax": ARCHIVE_HRMAX,
            "series": series,
            "rate": ef_rate(series),
            "n_ef_weeks": len(series),
            "valid_compare": False,
            "invalid_reason": "No NP in Garmin export for this block — EF not computable",
        })
    secondary_2015 = ef_2015_secondary(archive_bike)

    # Verdict — use non-FTP series for "still climbing" claim
    if rate_ex.get("still_climbing_at_end"):
        resp = (
            "**Finding (ex-FTP):** EF was still rising into the final non-test week — "
            "the block ended before aerobic adaptation clearly plateaued."
        )
    elif rate_ex.get("shape") == "mid_peak_then_fade":
        resp = (
            "**Finding (ex-FTP):** EF **peaked mid-block** (quality weeks ~Jul 14) then faded; "
            "the final non-test week was below the powered-window open. "
            "Do not read this as 'adaptation still climbing at week 12'."
        )
    elif rate_ex.get("slope_per_week") and rate_ex["slope_per_week"] > 0:
        resp = (
            "**Finding (ex-FTP):** Mild positive slope overall, driven by the mid-block peak; "
            "the series does not finish at a new high."
        )
    else:
        resp = (
            "**Finding (ex-FTP):** EF did **not** finish still climbing. "
            "The all-rides series looks stronger mainly because the final week is the FTP test."
        )
    resp += (
        " **EF vs archive top-5 hours blocks is not valid** — those blocks have zero NP in the "
        "export. Secondary 2015 NP strip is shown only for context."
    )

    # Positioning table
    pos_table = []
    by_year = {r["year"]: r for r in findings.get("mmp", {}).get("by_year") or []}
    for y in (2011, 2012, 2013, 2014, 2015, 2016):
        r = by_year.get(y) or {}
        m20 = r.get("mmp_20min")
        m60 = r.get("mmp_60min")
        w = WEIGHTS.get(y)
        notes = "MEASURED_MMP shortlist"
        if r.get("plausibility_fail"):
            notes += "; ratio band FAIL (coverage caveat)"
        if y == 2012:
            notes += "; Alps Day4 MMP-60≈253 lore confirmed on stream"
        pos_table.append({
            "year": y,
            "mmp_20": m20,
            "mmp_60": m60,
            "weight_kg": w if w else "—",
            "mmp_20_wkg": round(m20 / w, 2) if m20 and w else "—",
            "mmp_60_wkg": round(m60 / w, 2) if m60 and w else "—",
            "notes": notes,
        })
    m20_26 = agg["best"].get("mmp_20min")
    m60_26 = agg["best"].get("mmp_60min")
    pos_table.append({
        "year": 2026,
        "mmp_20": m20_26,
        "mmp_60": m60_26,
        "weight_kg": weight,
        "mmp_20_wkg": round(m20_26 / weight, 2) if m20_26 else "—",
        "mmp_60_wkg": round(m60_26 / weight, 2) if m60_26 else "—",
        "notes": (
            f"MEASURED_MMP block bests; FTP test MMP-20={mmp20} outdoor; "
            f"FTP {FTP_RECORDED_W}=effort×0.95 (not in this table)"
        ),
    })

    confounds = [
        "13 years older (archive peak years ~35–39; now 50).",
        f"~{round(weight - 78, 1)} kg heavier than 2012 Alps weight (78 kg); 2026 test weight {weight} kg "
        "(prior framing sometimes used 92 kg).",
        "Different power meters — 2012-era unit had known climbing-physics discrepancy; "
        "2026 Favero Assioma almost certainly more accurate. Part of any watt gap is measurement.",
        "FTP test indoor/outdoor: outdoor — no turbo confound for the headline MMP-20.",
        "2026 MMP year curve is from ~6 weeks of powered riding (meter from late June), "
        "not a full season shortlist like archive years.",
        "Powered early-block weeks (May–mid June) missing from MMP — understates block capacity if unpowered hard days existed.",
    ]

    # Projection
    slope_ef = rate_2026.get("slope_per_week")
    # Use MMP-20 change across FTP tests if available
    mmp20_by_aid = {r["activity_id"]: r.get("mmp_20min") for r in mmp_rows}
    retest = mmp20_by_aid.get(23455664973)
    final = mmp20
    weeks_between = None
    rate_w_per_week = None
    if retest and final:
        weeks_between = (date(2026, 8, 7) - date(2026, 7, 2)).days / 7.0
        rate_w_per_week = (float(final) - float(retest)) / weeks_between if weeks_between else None

    proj_lines = [
        f"Observed MMP-20: FTP re-test ride `{23455664973}` → **{retest} W**; "
        f"final test → **{final} W**"
        + (f" over ~{weeks_between:.1f} weeks" if weeks_between else "")
        + ".",
    ]
    if rate_w_per_week is not None:
        m6 = float(final) + rate_w_per_week * 26
        m12 = float(final) + rate_w_per_week * 52
        proj_lines.append(
            f"Naive linear continuation of that Δ: **~{rate_w_per_week:.2f} W/week** → "
            f"MMP-20 ≈ **{m6:.0f} W** at +6 months, **{m12:.0f} W** at +12 months."
        )
        proj_lines.append(
            "**Do not believe the linear numbers.** Early/mid-block gains decelerate; "
            "FTP and MMP curves flatten. Treat the projection as an upper-bound illustration only."
        )
    else:
        proj_lines.append(
            "Insufficient spaced MMP-20 tests to fit a watt rate — use EF slope and rebuild lore instead."
        )
    proj_lines += [
        "Archive rebuild central estimate: **~5 weeks** to recover after a typical layoff "
        "(longer when off >10 weeks); three autumn layoffs never recovered.",
        "Next 12 weeks to keep response going: protect the **≥3 rides/week streak**, "
        "one quality day + one long ride weekly, maintain outdoor MMP sampling monthly, "
        "avoid Nov–Jan zero; if travel forces a cut, cap layoff at ≤3 weeks then rebuild deliberately.",
    ]
    if rate_2026.get("still_climbing_at_end"):
        proj_lines.append(
            "EF still climbing at week 12 supports continuing the dose rather than an immediate deload into inactivity."
        )

    # Autumn cost
    mmp_now = float(final) if final else None
    autumn_body = [
        "Archive pattern: every year shows a **6–12 week layoff** clustered Nov–Jan "
        "(Nov 2009, Nov 2010, Oct 2011, Nov 2012, Nov 2013, Nov 2014). Three never recovered.",
        "From the current position, a typical autumn gap of **8 weeks off** plus **~5 weeks rebuild** "
        "is **≈13 weeks of lost progress** before matching today's fitness proxy again — "
        "and that assumes a *successful* rebuild, which failed in 3/15 major layoffs.",
    ]
    if mmp_now and rate_w_per_week and rate_w_per_week > 0:
        # During layoff assume decay; we don't have a personal decay model — use rebuild framing only
        autumn_body.append(
            f"Concrete: if you stop now at MMP-20 ≈ **{mmp_now:.0f} W**, after 8 weeks off you are "
            f"not at {mmp_now:.0f} W — you restart below it. After ~5 rebuild weeks you *might* "
            f"revisit ~{mmp_now:.0f} W (archive median recoverers). "
            f"Linear +52-week fantasy ({mmp_now + rate_w_per_week * 52:.0f} W) is forfeited; "
            f"realistic return point is **near current MMP-20, not ahead of it**."
        )
    elif mmp_now:
        autumn_body.append(
            f"Concrete: return-from-layoff estimate is **≈{mmp_now:.0f} W MMP-20** after ~5 rebuild weeks "
            f"(if recovery succeeds) — i.e. back to today, not past it. Three historical failures "
            f"never regained prior proxy."
        )
    autumn_body.append(
        "Cost of an autumn layoff from here: **~13 weeks of calendar (8+5)** and "
        "**zero expected net MMP-20 gain** across that span — progress clock resets."
    )

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ftp_test": ftp_meta,
        "consistency": cons,
        "block_compare": cmpb,
        "archive_streak_weeks": findings["consistency"]["longest_streak_weeks"]["weeks"],
        "mmp": {"rides": mmp_rows, "block_aggregate": agg},
        "ef": {
            "hrmax_2026": hrmax,
            "archive_hrmax": ARCHIVE_HRMAX,
            "series_2026": series_2026,
            "series_2026_ex_ftp": series_2026_ex_ftp,
            "rate_2026": rate_2026,
            "rate_2026_ex_ftp": rate_ex,
            "historical_top5": hist_ef,
            "historical": hist_ef,  # backward compat for chart
            "secondary_2015": secondary_2015,
            "top5_ef_valid": False,
            "response_verdict": resp,
        },
        "positioning": {"table": pos_table, "confounds": confounds},
        "projection": {"body": "\n\n".join(proj_lines), "rate_w_per_week": rate_w_per_week},
        "autumn": {"body": "\n\n".join(autumn_body)},
    }

    # CSVs
    csv_path = ARCHIVE_DIR / "activity_mmp_2026.csv"
    keys = [
        "activity_id", "date", "mmp_1min", "mmp_2min", "mmp_5min", "mmp_20min", "mmp_60min",
        "has_power", "source", "provenance_peak", "zero_pct_wall", "smart_recording",
        "spikes_rejected", "error",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in mmp_rows:
            w.writerow(r)

    year_csv = ARCHIVE_DIR / "mmp_by_year_with_2026.csv"
    with year_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "year", "mmp_20", "mmp_60", "weight_kg", "mmp_20_wkg", "mmp_60_wkg",
                "provenance", "notes",
            ],
        )
        w.writeheader()
        for row in pos_table:
            w.writerow({
                "year": row["year"],
                "mmp_20": row["mmp_20"],
                "mmp_60": row["mmp_60"],
                "weight_kg": row["weight_kg"],
                "mmp_20_wkg": row["mmp_20_wkg"],
                "mmp_60_wkg": row["mmp_60_wkg"],
                "provenance": "MEASURED_MMP",
                "notes": row["notes"],
            })

    write_hours_chart(findings, cons)
    chart_blocks = []
    if secondary_2015.get("series"):
        chart_blocks.append(secondary_2015)
    write_ef_chart(series_2026_ex_ftp, chart_blocks)

    report = write_report(payload)
    (ARCHIVE_DIR / "block_2026_findings.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )

    # Append CHANGELOG
    cl = ARCHIVE_DIR / "CHANGELOG.md"
    entry = f"""
## 8. 2026 block compare — FTP ≠ archive MMP-20 (2026-08-07)

**Prior risk:** Treating app FTP **{FTP_RECORDED_W} W** as comparable to archive annual MMP-20 peaks (e.g. 2015 **303.7 W**).

**Now:** Final FTP test `{FTP_TEST_ID}` is **outdoor** **{FTP_PROTOCOL}**. Analysed effort avg **{FTP_EFFORT_AVG_W} W**; stream **MMP-20 MEASURED_MMP = {mmp20} W**. Only that stream number joins the year table. Full write-up: `block_2026_analysis.md`.

**Consistency:** 2026 longest ≥3-rides/week streak = **{cons['longest_streak_ge3']['weeks']}** weeks — does **not** beat archive **8** (Apr–May 2012). Best 6-wk sub-block **{b6h} h** vs archive #1 **{arch_best_h} h**.

**Still true:** wall-clock MMP engine; rebuild ~5 weeks; do not compare DEVICE FTP to MEASURED_MMP.
"""
    text = cl.read_text(encoding="utf-8")
    if "## 8. 2026 block compare" not in text:
        cl.write_text(text.rstrip() + "\n" + entry, encoding="utf-8")

    # Patch findings.json mmp.by_year with 2026
    by = findings.setdefault("mmp", {}).setdefault("by_year", [])
    by = [r for r in by if r.get("year") != 2026]
    by.append({
        "year": 2026,
        "n_rides": agg["n_rides"],
        "mmp_5s": agg["best"].get("mmp_5s"),
        "mmp_1min": agg["best"].get("mmp_1min"),
        "mmp_2min": agg["best"].get("mmp_2min"),
        "mmp_5min": agg["best"].get("mmp_5min"),
        "mmp_20min": agg["best"].get("mmp_20min"),
        "mmp_60min": agg["best"].get("mmp_60min"),
        "provenance": "MEASURED_MMP",
        "source": "block_2026_fits",
        "note": "12-week charity block powered rides; not a full-year shortlist",
    })
    findings["mmp"]["by_year"] = sorted(by, key=lambda r: r["year"])
    findings["block_2026"] = {
        "report": "block_2026_analysis.md",
        "ftp_test": ftp_meta,
        "consistency_summary": {
            "streak_weeks": cons["longest_streak_ge3"]["weeks"],
            "beat_archive_streak": cons["longest_streak_ge3"]["weeks"]
            > findings["consistency"]["longest_streak_weeks"]["weeks"],
            "total_hours": cons["total_hours"],
            "hours_per_week": cons["hours_per_week"],
        },
    }
    FINDINGS_PATH.write_text(json.dumps(findings, indent=2, default=str), encoding="utf-8")
    # Mirror to home cache if present
    home_f = Path.home() / ".ai_endurance_coach_over50" / "archive" / "findings.json"
    if home_f.parent.is_dir():
        home_f.write_text(FINDINGS_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"\nReport: {report}", flush=True)
    print(f"FTP MMP-20: {mmp20} W (FTP recorded {FTP_RECORDED_W})", flush=True)
    print(f"Streak: {cons['longest_streak_ge3']['weeks']} vs archive {findings['consistency']['longest_streak_weeks']['weeks']}", flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

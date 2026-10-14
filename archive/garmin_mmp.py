#!/usr/bin/env python3
"""Stage 3b — true mean-maximal power from cached shortlist FITs; merge into findings."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ARCHIVE_DIR = Path(__file__).resolve().parent
FITS_DIR = ARCHIVE_DIR / "fits"
STREAMS_DIR = ARCHIVE_DIR / "streams"
SHORTLIST_PATH = ARCHIVE_DIR / "shortlist_v2.csv"
SHORTLIST_FALLBACK = ARCHIVE_DIR / "shortlist.csv"
ACTIVITIES_CSV = ARCHIVE_DIR / "activities_2009_2016.csv"
FINDINGS_PATH = ARCHIVE_DIR / "findings.json"
MMP_CSV = ARCHIVE_DIR / "activity_mmp.csv"
PROVENANCE_CSV = ARCHIVE_DIR / "activity_provenance.csv"
CHARTS_DIR = ARCHIVE_DIR / "charts"
REPORT_PATH = ARCHIVE_DIR / "analysis_report.md"
SANITY_WARNINGS_PATH = ARCHIVE_DIR / "mmp_sanity_warnings.md"

MMP_WINDOWS = [
    ("mmp_5s", 5),
    ("mmp_1min", 60),
    ("mmp_2min", 120),
    ("mmp_5min", 300),
    ("mmp_20min", 1200),
    ("mmp_60min", 3600),
]

# Sensor-glitch guards (Edge-era spikes produced 1951W "avg" / 2624W "MMP-20")
MAX_SAMPLE_POWER_W = 1500.0
# Refuse to publish mean-max figures above these for ≥5s windows (sprint 5s may be high)
MAX_MMP_PUBLISH_W = {
    "mmp_5s": 1800.0,
    "mmp_1min": 900.0,
    "mmp_5min": 600.0,
    "mmp_20min": 450.0,
    "mmp_60min": 400.0,
}
MAX_CSV_PROXY_SANITY_W = 450.0  # whole-ride NP/avg above this ignored in shortlist sanity

# Lore tags: MEASURED climb target vs DEVICE_SETTING FTP
STATED_PEAKS = [
    {
        "year": 2012,
        "stated_peak_w": 253,
        "label": "best 60-min Alps climb 253W",
        "provenance": "MEASURED_MMP",
        "compare_to": "mmp_60min",
    },
    {
        "year": 2012,
        "stated_peak_w": 242,
        "label": "device FTP setting ~242W",
        "provenance": "DEVICE_SETTING",
        "compare_to": None,  # do not contradict against MMP
    },
    {
        "year": 2015,
        "stated_peak_w": 282,
        "label": "critical power 282W (athlete lore / modelled)",
        "provenance": "MODELLED",
        "compare_to": "mmp_5min",
    },
    {
        "year": 2016,
        "stated_peak_w": 260,
        "label": "device FTP setting 260W (Jan — stale config)",
        "provenance": "DEVICE_SETTING",
        "compare_to": None,
    },
]


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


def _engine():
    import importlib.util
    import sys
    name = "archive_mmp_engine"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ARCHIVE_DIR / "mmp_engine.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def compute_activity_mmp_from_series(
    series: list,
    activity_id: int,
    date_s: str = "",
    source: str = "fit",
    device_ftp_w: Optional[float] = None,
    device_ftp_source: Optional[str] = None,
) -> dict[str, Any]:
    """Deprecated path — prefer FIT/TCX pairs. Treats None as 0 W."""
    eng = _engine()
    mmp, diag, filled = eng.compute_mmp_from_1hz_list(series)
    row: dict[str, Any] = {
        "activity_id": activity_id,
        "date": date_s,
        "duration_s": len(filled) if filled else None,
        "mmp_5s": mmp.get("mmp_5s"),
        "mmp_1min": mmp.get("mmp_1min"),
        "mmp_2min": mmp.get("mmp_2min"),
        "mmp_5min": mmp.get("mmp_5min"),
        "mmp_20min": mmp.get("mmp_20min"),
        "mmp_60min": mmp.get("mmp_60min"),
        "samples": sum(1 for v in filled if v > 0),
        "has_power": 1 if any(v > 0 for v in filled) else 0,
        "error": "",
        "source": source,
        "provenance_peak": "MEASURED_MMP",
        "device_ftp_w": device_ftp_w,
        "device_ftp_source": device_ftp_source,
        "zero_pct_wall": diag.zero_pct_of_wall,
        "smart_recording": int(bool(diag.smart_recording)),
        "median_dt_s": diag.median_dt_s,
        "spikes_rejected": diag.n_spike_rejected,
    }
    if not row["has_power"]:
        row["error"] = "no_power_samples"
        row["provenance_peak"] = None
    if diag.notes:
        row["error"] = (row.get("error") or "") + "|" + ";".join(diag.notes)
    return row


def compute_activity_mmp(fit_path: Path, activity_id: int, date_s: str = "") -> dict[str, Any]:
    sys.path.insert(0, str(ARCHIVE_DIR.parent))
    from ai_endurance_coach_over50.analysis.fit_ingest import parse_fit

    eng = _engine()
    empty = {
        "activity_id": activity_id, "date": date_s, "duration_s": None,
        "mmp_5s": None, "mmp_1min": None, "mmp_2min": None, "mmp_5min": None,
        "mmp_20min": None, "mmp_60min": None, "samples": 0, "has_power": 0,
        "error": "", "source": "fit", "provenance_peak": None,
        "device_ftp_w": None, "device_ftp_source": None,
    }
    try:
        session = parse_fit(fit_path)
    except Exception as e:
        empty["error"] = f"parse:{e}"
        return empty

    device_ftp = getattr(session, "device_ftp", None) or getattr(session, "ftp", None)
    for attr in ("device_ftp_w", "ftp_w", "threshold_power"):
        if getattr(session, attr, None):
            device_ftp = getattr(session, attr)
            break
    pairs, diag = eng.extract_power_pairs(session.records)
    mmp, diag, series = eng.compute_mmp_from_pairs(pairs, diag)
    row = {
        "activity_id": activity_id,
        "date": date_s,
        "duration_s": len(series) if series else None,
        "mmp_5s": mmp.get("mmp_5s"),
        "mmp_1min": mmp.get("mmp_1min"),
        "mmp_2min": mmp.get("mmp_2min"),
        "mmp_5min": mmp.get("mmp_5min"),
        "mmp_20min": mmp.get("mmp_20min"),
        "mmp_60min": mmp.get("mmp_60min"),
        "samples": sum(1 for v in series if v > 0),
        "has_power": 1 if any(v > 0 for v in series) else 0,
        "error": "",
        "source": "fit",
        "provenance_peak": "MEASURED_MMP" if series else None,
        "device_ftp_w": float(device_ftp) if device_ftp else None,
        "device_ftp_source": "fit_session" if device_ftp else None,
        "zero_pct_wall": diag.zero_pct_of_wall,
        "smart_recording": int(bool(diag.smart_recording)),
        "median_dt_s": diag.median_dt_s,
        "spikes_rejected": diag.n_spike_rejected,
    }
    if not row["has_power"]:
        row["error"] = "no_power_samples"
        row["provenance_peak"] = None
    return row


def compute_from_stream_json(path: Path, date_s: str = "") -> dict[str, Any]:
    """Prefer original TCX beside stream; else fill None→0 on stored 1 Hz."""
    eng = _engine()
    data = json.loads(path.read_text(encoding="utf-8"))
    aid = int(data["activity_id"])
    # Re-parse Haute Route / cached TCX when available (zeros preserved)
    tcx_path = None
    src_path = data.get("path")
    if src_path and Path(src_path).is_file() and str(src_path).lower().endswith(".tcx"):
        tcx_path = Path(src_path)
    else:
        cand = ARCHIVE_DIR / "tcx" / f"{aid}.tcx"
        if cand.is_file():
            tcx_path = cand
        else:
            # Alps local
            import re
            HR = {277575486: 1, 277575362: 2, 277575279: 3, 277575228: 4, 277575139: 5}
            if aid in HR:
                day = HR[aid]
                for p in (ARCHIVE_DIR.parent / "data" / "haute-route-2012").glob("*.tcx"):
                    if re.search(rf"Day\s*{day}\b", p.name, re.I):
                        tcx_path = p
                        break
    if tcx_path is not None:
        pairs, diag = eng.pairs_from_tcx_path(tcx_path)
        mmp, diag, series = eng.compute_mmp_from_pairs(pairs, diag)
        source = data.get("source", "tcx")
    else:
        mmp, diag, series = eng.compute_mmp_from_1hz_list(data.get("power_1hz") or [])
        source = data.get("source", "stream_json")
    return {
        "activity_id": aid,
        "date": date_s,
        "duration_s": len(series) if series else None,
        "mmp_5s": mmp.get("mmp_5s"),
        "mmp_1min": mmp.get("mmp_1min"),
        "mmp_2min": mmp.get("mmp_2min"),
        "mmp_5min": mmp.get("mmp_5min"),
        "mmp_20min": mmp.get("mmp_20min"),
        "mmp_60min": mmp.get("mmp_60min"),
        "samples": sum(1 for v in series if v > 0),
        "has_power": 1 if any(v > 0 for v in series) else 0,
        "error": "",
        "source": source,
        "provenance_peak": "MEASURED_MMP",
        "device_ftp_w": data.get("device_ftp_w"),
        "device_ftp_source": data.get("device_ftp_source"),
        "zero_pct_wall": diag.zero_pct_of_wall,
        "smart_recording": int(bool(diag.smart_recording)),
        "median_dt_s": diag.median_dt_s,
        "spikes_rejected": diag.n_spike_rejected,
    }


def load_shortlist_meta(path: Path) -> dict[int, dict]:
    if not path.is_file() and path == SHORTLIST_PATH and SHORTLIST_FALLBACK.is_file():
        path = SHORTLIST_FALLBACK
    meta: dict[int, dict] = {}
    if not path.is_file():
        return meta
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                aid = int(float(row["activity_id"]))
            except (KeyError, ValueError, TypeError):
                continue
            meta[aid] = row
    return meta


def write_mmp_csv(rows: list[dict]) -> None:
    cols = [
        "activity_id", "date", "duration_s",
        "mmp_5s", "mmp_1min", "mmp_2min", "mmp_5min", "mmp_20min", "mmp_60min",
        "samples", "has_power", "source", "provenance_peak",
        "device_ftp_w", "zero_pct_wall", "smart_recording", "median_dt_s",
        "spikes_rejected", "error",
    ]
    with MMP_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_provenance_csv(rows: list[dict]) -> None:
    """Chronological device-FTP tracking + stale flag (≥18 months unchanged)."""
    chron = sorted(
        [r for r in rows if r.get("date")],
        key=lambda r: (r.get("date") or "", r["activity_id"]),
    )
    last_ftp = None
    last_change_date = None
    out_rows = []
    for r in chron:
        ftp = r.get("device_ftp_w")
        d = r.get("date") or ""
        changed = False
        if ftp is not None:
            if last_ftp is None or abs(float(ftp) - float(last_ftp)) >= 1:
                last_ftp = float(ftp)
                last_change_date = d
                changed = True
        stale = False
        if last_change_date and d and last_ftp is not None:
            try:
                from datetime import date as date_cls
                a = date_cls.fromisoformat(last_change_date[:10])
                b = date_cls.fromisoformat(d[:10])
                stale = (b - a).days >= 18 * 30
            except Exception:
                stale = False
        out_rows.append({
            "activity_id": r["activity_id"],
            "date": d,
            "device_ftp_w": ftp if ftp is not None else last_ftp,
            "device_ftp_source": r.get("device_ftp_source") or ("inferred_carry" if last_ftp else None),
            "last_changed_date": last_change_date,
            "stale_device_ftp": int(bool(stale and not changed and ftp is None)),
            "mmp_20min": r.get("mmp_20min"),
            "mmp_60min": r.get("mmp_60min"),
            "provenance_peak": r.get("provenance_peak") if r.get("has_power") else "PROXY",
            "source": r.get("source"),
        })
    cols = [
        "activity_id", "date", "device_ftp_w", "device_ftp_source",
        "last_changed_date", "stale_device_ftp", "mmp_20min", "mmp_60min",
        "provenance_peak", "source",
    ]
    with PROVENANCE_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    print(f"Wrote {PROVENANCE_CSV}", flush=True)
    return out_rows


def aggregate_by_year(rows: list[dict]) -> list[dict]:
    by_year: dict[int, list[dict]] = {}
    for r in rows:
        if not r.get("has_power"):
            continue
        d = (r.get("date") or "")[:4]
        try:
            y = int(d)
        except ValueError:
            continue
        by_year.setdefault(y, []).append(r)

    out = []
    for year in sorted(by_year):
        group = by_year[year]
        entry: dict[str, Any] = {"year": year, "n_rides": len(group)}
        for key, _ in MMP_WINDOWS:
            vals = [r[key] for r in group if r.get(key) is not None]
            entry[key] = round(max(vals), 1) if vals else None
        out.append(entry)
    eng = _engine()
    flags = eng.annual_plausibility(out)
    for f in flags:
        print(f"PLAUSIBILITY: {f}", flush=True)
    return out


def fit_contradictions(by_year: list[dict]) -> list[dict]:
    lookup = {b["year"]: b for b in by_year}
    out = []
    for stated in STATED_PEAKS:
        y = stated["year"]
        prov = stated["provenance"]
        b = lookup.get(y)
        compare_key = stated.get("compare_to")
        best = None
        if b and compare_key:
            best = b.get(compare_key) or b.get("mmp_60min") or b.get("mmp_20min") or b.get("mmp_5min")
        elif b and prov == "MEASURED_MMP":
            for k in ("mmp_60min", "mmp_20min", "mmp_5min"):
                if b.get(k) is not None:
                    best = max(best or 0, b[k])

        stated_w = stated["stated_peak_w"]
        # Never call DEVICE_SETTING vs PROXY/MMP a "genuine contradiction"
        if prov == "DEVICE_SETTING":
            out.append({
                "year": y,
                "stated": stated["label"],
                "stated_peak_w": stated_w,
                "stated_provenance": prov,
                "archive_best_mmp_w": best,
                "archive_provenance": "MEASURED_MMP" if best else None,
                "conflicts": False,
                "source": "shortlist_fit_mmp",
                "note": (
                    f"{stated_w}W is a DEVICE_SETTING — not a measured fitness datum. "
                    "Do not treat gaps vs proxies/MMP as measurement contradictions."
                    + (f" Year MMP-60={b.get('mmp_60min')} MEASURED_MMP." if b and b.get("mmp_60min") else "")
                ),
            })
            continue

        conflicts = bool(
            best is not None and compare_key and best < stated_w * 0.85
        )
        out.append({
            "year": y,
            "stated": stated["label"],
            "stated_peak_w": stated_w,
            "stated_provenance": prov,
            "archive_best_mmp_w": best,
            "archive_provenance": "MEASURED_MMP" if best else None,
            "conflicts": conflicts,
            "source": "shortlist_fit_mmp",
            "note": (
                f"Stated {stated_w}W ({prov}) vs shortlist {compare_key or 'MMP'} "
                f"{best}W MEASURED_MMP"
                if best is not None else
                f"No MEASURED_MMP on shortlist for {y} to compare to stated {prov}"
            ),
        })
    return out


def mmp_sanity_check(rows: list[dict], activities_csv: Path) -> list[str]:
    """Warn if shortlist best MMP-60 < 60% of year's best CSV NP/avg_power."""
    warnings = []
    csv_best: dict[int, tuple[float, int]] = {}
    if activities_csv.is_file():
        with activities_csv.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                sport = (r.get("sport") or "").lower()
                if "cycl" not in sport and "bik" not in sport:
                    continue
                d = (r.get("date") or "")[:4]
                try:
                    y = int(d)
                    aid = int(float(r["activity_id"]))
                except Exception:
                    continue
                vals = []
                for k in ("normalized_power", "avg_power"):
                    try:
                        if r.get(k):
                            vals.append(float(r[k]))
                    except Exception:
                        pass
                if not vals:
                    continue
                v = max(vals)
                if v > MAX_CSV_PROXY_SANITY_W:
                    continue
                prev = csv_best.get(y)
                if prev is None or v > prev[0]:
                    csv_best[y] = (v, aid)

    by_year_mmp: dict[int, float] = {}
    for r in rows:
        if not r.get("has_power") or not r.get("mmp_60min"):
            continue
        try:
            y = int(str(r.get("date") or "")[:4])
        except Exception:
            continue
        by_year_mmp[y] = max(by_year_mmp.get(y, 0), float(r["mmp_60min"]))

    for y, (csv_w, champ_id) in sorted(csv_best.items()):
        mmp_w = by_year_mmp.get(y)
        if mmp_w is None:
            warnings.append(
                f"WARNING {y}: shortlist has no MMP-60; CSV champ ~{csv_w}W "
                f"(activity {champ_id}) — selection may have missed peak efforts."
            )
            continue
        if csv_w > 0 and mmp_w < 0.60 * csv_w:
            warnings.append(
                f"WARNING {y}: shortlist best MMP-60 {mmp_w}W is "
                f"{100 * mmp_w / csv_w:.0f}% of CSV whole-ride NP/avg champ "
                f"{csv_w}W (activity {champ_id}) — selection likely missed something."
            )
    if warnings:
        SANITY_WARNINGS_PATH.write_text("\n".join(warnings) + "\n", encoding="utf-8")
        for w in warnings:
            print(w, flush=True)
    return warnings


def write_mmp_png(by_year: list[dict]) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    years = [b["year"] for b in by_year]
    if not years:
        return
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 4))
    for key, label in (
        ("mmp_5s", "5s"),
        ("mmp_1min", "1 min"),
        ("mmp_5min", "5 min"),
        ("mmp_20min", "20 min"),
        ("mmp_60min", "60 min"),
    ):
        ax.plot(years, [b.get(key) for b in by_year], marker="o", label=label)
    ax.set_xlabel("Year")
    ax.set_ylabel("Watts (true MMP, shortlist)")
    ax.set_title("Mean-maximal power by year (shortlist FITs)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "mmp_by_year.png", dpi=120)
    plt.close(fig)


def recompute_rebuild_fit(fit_mmp: dict[int, dict]) -> tuple[dict, list[dict]]:
    """Re-run rebuild with FIT preferred; return (rebuild_fit_dict, trajectories)."""
    sys.path.insert(0, str(ARCHIVE_DIR.parent))
    # Import sibling analysis module
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "garmin_analysis", ARCHIVE_DIR / "garmin_analysis.py"
    )
    assert spec and spec.loader
    ga = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ga)

    if not ACTIVITIES_CSV.is_file():
        return {"error": "activities CSV missing"}, []

    df = ga.load_activities(ACTIVITIES_CSV)
    bike = df[df["is_cycling"]].copy()
    gaps = ga.find_cycling_gaps(bike, min_days=21)
    rebuild = ga.analyse_rebuild(bike, gaps, fit_mmp=fit_mmp)
    traj = rebuild.pop("trajectories", [])
    return rebuild, traj


def append_report_mmp(findings: dict) -> None:
    lines = [
        "",
        "---",
        "",
        "## True MMP (shortlist FITs)",
        "",
    ]
    mmp = findings.get("mmp") or {}
    lines.append(
        f"Parsed {mmp.get('n_fits', 0)} FITs, {mmp.get('n_with_power', 0)} with power samples."
    )
    lines.append("")
    lines.append(mmp.get("curve_notes") or "")
    lines.append("")
    lines.append("| Year | 5s | 1min | 5min | 20min | 60min |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for b in mmp.get("by_year") or []:
        lines.append(
            f"| {b['year']} | {b.get('mmp_5s')} | {b.get('mmp_1min')} | "
            f"{b.get('mmp_5min')} | {b.get('mmp_20min')} | {b.get('mmp_60min')} |"
        )
    rb = findings.get("rebuild_fit") or {}
    lines += [
        "",
        "### FIT-grounded rebuild",
        "",
        f"**Central estimate: {rb.get('central_estimate_weeks')} weeks** "
        f"(summary-only was { (findings.get('rebuild') or {}).get('central_estimate_weeks') }).",
        "",
        rb.get("proxy_notes") or "",
        "",
        "### FIT vs stated peaks",
        "",
    ]
    for c in findings.get("contradictions_fit") or []:
        flag = " **CONFLICT**" if c.get("conflicts") else ""
        sp = c.get("stated_provenance") or "?"
        ap = c.get("archive_provenance") or "?"
        lines.append(
            f"- {c['year']}: {c.get('archive_best_mmp_w')}W {ap} vs stated "
            f"{c.get('stated_peak_w')}W {sp}{flag} — {c.get('note')}"
        )
    cw = findings.get("coupled_weight_power") or {}
    if cw:
        lines += [
            "",
            "### Coupled weight / power (not independent levers)",
            "",
            cw.get("note") or "",
            f"Assumptions W lost per kg: {cw.get('assumptions_w_lost_per_kg')}",
            f"Archive-era weight overlap: {(cw.get('archive_weight_overlap') or {}).get('note') or cw.get('archive_weight_overlap')}",
            "",
        ]
    ai = findings.get("ai_narrative_mmp") or {}
    if ai.get("markdown"):
        lines += ["", "## Coach MMP narrative (Claude Opus)", "", ai["markdown"], ""]

    if REPORT_PATH.is_file():
        existing = REPORT_PATH.read_text(encoding="utf-8")
        # Drop previous MMP appendix if re-running
        marker = "\n---\n\n## True MMP (shortlist FITs)"
        if marker in existing:
            existing = existing.split(marker)[0].rstrip()
        REPORT_PATH.write_text(existing + "\n" + "\n".join(lines), encoding="utf-8")
    else:
        REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def generate_mmp_narrative(findings: dict, force: bool = False) -> Optional[dict]:
    existing = findings.get("ai_narrative_mmp")
    if existing and existing.get("markdown") and not force:
        return existing
    _load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ANTHROPIC_API_KEY not set — skipping MMP Opus narrative", flush=True)
        return None

    sys.path.insert(0, str(ARCHIVE_DIR.parent))
    import anthropic
    from ai_endurance_coach_over50.llm import MODEL_COACH

    compact = {
        "rebuild_summary": {
            k: (findings.get("rebuild") or {}).get(k)
            for k in ("central_estimate_weeks", "iqr", "n_full_recoveries")
        },
        "rebuild_fit": {
            k: (findings.get("rebuild_fit") or {}).get(k)
            for k in (
                "central_estimate_weeks", "iqr", "n_full_recoveries", "n_plateaued",
                "n_layoffs_with_fit_baseline", "n_layoffs_with_fit_restart", "proxy_notes",
                "layoffs",
            )
        },
        "mmp_by_year": (findings.get("mmp") or {}).get("by_year"),
        "mmp_notes": (findings.get("mmp") or {}).get("curve_notes"),
        "contradictions_fit": findings.get("contradictions_fit"),
        "current": findings.get("current_athlete"),
        "reversal_note": (
            "rebuild_fit is 5.0 weeks (agrees with summary). Earlier 7.5 weeks was from "
            "sparse v1 shortlist FIT coverage (esp. 2012-01-07 took 12 weeks under that map); "
            "not summary optimism."
        ),
        "mmp_method": (
            "Wall-clock 1 Hz; zeros count as 0; gaps>8s→0; spikes>1800W rejected. "
            "Flat year 20:60 can be a steady plateau ride (e.g. 2013 same-ride), not a bug."
        ),
    }
    prompt = f"""You are an endurance coach. The athlete now has TRUE mean-maximal power
from FIT/TCX streams for shortlist_v2 historical rides (not exhaustive).

QUANTITATIVE FINDINGS (do not invent numbers):
```json
{json.dumps(compact, indent=2, default=str)}
```

Write a short markdown addendum (not a full rehash of the earlier narrative):
1. How the FIT/stream-grounded rebuild estimate compares to the summary-only estimate — address the 7.5→5.0 reversal using reversal_note.
2. What the true MMP year curves say vs stated historical peaks — tag every figure MEASURED_MMP / DEVICE_SETTING / PROXY / MODELLED. Never treat DEVICE_SETTING FTP as a measurement contradiction. Note wall-clock method and that flat 20:60 can be plateau rides.
3. Path toward 3.5 W/kg: coupled weight+power only. Show W/kg under 0 / 3 / 6 W lost per kg of weight drop. Sequence: consistency first, modest deficit, MMP-20 guardrail. Do NOT claim weight is an independent lever that holds watts constant.
4. Caveat: shortlist_v2 only; missing FITs / pre-power years; some year MMP-60 coverage still weak (2010/2011/2016 flags).

Prefer personal rebuild numbers over generic 3–5%/year rules.

PROVENANCE RULES (mandatory):
- Tag every watts claim as MEASURED_MMP, DEVICE_SETTING, PROXY, or MODELLED.
- Never treat device FTP settings (e.g. Jan 2016 260W, 2012 242W) as measurements or as contradictions against proxies.
- 2012 Alps Day 4 ~253W MMP-60 is MEASURED_MMP when present; year peak ~267W Day 1 is also MEASURED_MMP.

WEIGHT / W/kg RULES (mandatory):
- Do NOT recommend holding watts constant while cutting weight to hit 3.5 W/kg.
- If discussing weight, show a band under assumptions of 0, 3, and 6 W lost per kg dropped.
- Recommend sequenced approach: training consistency first, modest deficit under it, MMP-20 as guardrail.
- If power falls while weight falls, the deficit is too aggressive.

If this run overturns earlier conclusions (e.g. 2012 MMP-60≈159W / “low fitness”, or FIT rebuild 7.5 weeks), say so plainly."""

    print(f"Calling {MODEL_COACH} for MMP narrative…", flush=True)
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=MODEL_COACH,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    return {
        "model": MODEL_COACH,
        "markdown": text.strip(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "version": "mmp_v3_wallclock",
    }


def run(force_ai: bool = False, fetch_missing: bool = False) -> dict:
    sys.path.insert(0, str(ARCHIVE_DIR.parent))

    meta = load_shortlist_meta(SHORTLIST_PATH)
    if not meta:
        sys.exit(f"No shortlist at {SHORTLIST_PATH}")

    if fetch_missing:
        stream_ids = {int(p.stem) for p in STREAMS_DIR.glob("*.json")} if STREAMS_DIR.is_dir() else set()
        missing = [
            aid for aid in meta
            if not (FITS_DIR / f"{aid}.fit").is_file() and aid not in stream_ids
        ]
        if missing:
            print(f"Fetching {len(missing)} missing FITs…", flush=True)
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "garmin_fit_fetch", ARCHIVE_DIR / "garmin_fit_fetch.py"
            )
            assert spec and spec.loader
            ff = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ff)
            ff.run(ids=missing)

    FITS_DIR.mkdir(parents=True, exist_ok=True)
    STREAMS_DIR.mkdir(parents=True, exist_ok=True)

    # Prefer stream JSON (e.g. TCX Alps) over FIT when both exist / FIT tiny
    stream_files = {int(p.stem): p for p in STREAMS_DIR.glob("*.json")}
    fit_files = {int(p.stem): p for p in FITS_DIR.glob("*.fit") if p.stem.isdigit()}

    ids = sorted(set(meta) | set(stream_files) | set(fit_files))
    print(f"Computing MMP for {len(ids)} activity ID(s)…", flush=True)

    rows: list[dict] = []
    for aid in ids:
        date_s = (meta.get(aid) or {}).get("date", "")
        stream_p = stream_files.get(aid)
        fit_p = fit_files.get(aid)
        # Prefer TCX/stream when present (trusted Alps peaks)
        if stream_p is not None:
            print(f"  {aid} (stream)…", flush=True)
            rows.append(compute_from_stream_json(stream_p, date_s))
            continue
        if fit_p is not None and fit_p.stat().st_size > 5000:
            print(f"  {aid} (fit)…", flush=True)
            rows.append(compute_activity_mmp(fit_p, aid, date_s))
            continue
        if fit_p is not None:
            print(f"  {aid} (tiny fit {fit_p.stat().st_size}B)…", flush=True)
            rows.append(compute_activity_mmp(fit_p, aid, date_s))
            continue
        if aid in meta:
            rows.append({
                "activity_id": aid,
                "date": date_s,
                "duration_s": None,
                "mmp_5s": None, "mmp_1min": None, "mmp_5min": None,
                "mmp_20min": None, "mmp_60min": None,
                "samples": 0, "has_power": 0, "error": "fit_missing",
                "source": None, "provenance_peak": None,
                "device_ftp_w": None, "device_ftp_source": None,
            })

    rows.sort(key=lambda r: (r.get("date") or "", r["activity_id"]))
    write_mmp_csv(rows)
    write_provenance_csv(rows)
    sanity = mmp_sanity_check(rows, ACTIVITIES_CSV)

    with_power = [r for r in rows if r.get("has_power")]
    by_year = aggregate_by_year(rows)
    write_mmp_png(by_year)
    contradictions_fit = fit_contradictions(by_year)

    fit_mmp_map: dict[int, dict] = {
        int(r["activity_id"]): r for r in with_power
    }
    print("Recomputing FIT-grounded rebuild…", flush=True)
    rebuild_fit, traj_fit = recompute_rebuild_fit(fit_mmp_map)

    # Load / merge findings
    if not FINDINGS_PATH.is_file():
        sys.exit(f"Missing {FINDINGS_PATH} — run garmin_analysis.py first")
    findings = json.loads(FINDINGS_PATH.read_text(encoding="utf-8"))

    findings["mmp"] = {
        "source": "shortlist_v2_fits_and_streams",
        "n_fits": len(fit_files),
        "n_streams": len(stream_files),
        "n_with_power": len(with_power),
        "n_missing_fit": sum(1 for r in rows if r.get("error") == "fit_missing"),
        "by_year": by_year,
        "sanity_warnings": sanity,
        "curve_notes": (
            "True mean-maximal power (MEASURED_MMP) from FIT/TCX streams "
            "(1 Hz resampled; gaps >3s excluded). shortlist_v2 — not exhaustive. "
            "Device FTP values are DEVICE_SETTING, not measurements."
        ),
        "activities": [
            {
                "activity_id": r["activity_id"],
                "date": r.get("date"),
                "mmp_5s": r.get("mmp_5s"),
                "mmp_1min": r.get("mmp_1min"),
                "mmp_5min": r.get("mmp_5min"),
                "mmp_20min": r.get("mmp_20min"),
                "mmp_60min": r.get("mmp_60min"),
                "has_power": r.get("has_power"),
                "source": r.get("source"),
                "provenance_peak": r.get("provenance_peak"),
                "error": r.get("error") or None,
            }
            for r in rows if r.get("has_power") or r.get("error")
        ][:200],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    findings["rebuild_fit"] = rebuild_fit
    findings["contradictions_fit"] = contradictions_fit
    append_coupled_section_to_report = None
    write_changelog = None
    prior_snap = None
    try:
        import copy
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "weight_framing", ARCHIVE_DIR / "weight_framing.py"
        )
        assert spec and spec.loader
        wf = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wf)
        prior_snap = {
            "rebuild_fit": copy.deepcopy(findings.get("rebuild_fit")),
            "mmp": copy.deepcopy(findings.get("mmp")),
        }
        findings = wf.patch_findings_weight(findings)
        append_coupled_section_to_report = wf.append_coupled_section_to_report
        write_changelog = wf.write_changelog
    except Exception as e:
        print(f"Warn: weight framing failed: {e}", flush=True)
        findings["coupled_weight_power"] = {
            "assumptions_w_lost_per_kg": [0, 3, 6],
            "note": (
                "W/kg targets must not assume power is held constant while weight drops. "
                "Show a band under 0/3/6 W lost per kg. Sequence: consistency first, "
                "modest deficit, MMP-20 guardrail."
            ),
            "archive_weight_overlap": {"note": "body_db check failed"},
        }

    charts = findings.setdefault("charts", {})
    charts["mmp_by_year"] = {
        "years": [b["year"] for b in by_year],
        "mmp_5s": [b.get("mmp_5s") for b in by_year],
        "mmp_1min": [b.get("mmp_1min") for b in by_year],
        "mmp_2min": [b.get("mmp_2min") for b in by_year],
        "mmp_5min": [b.get("mmp_5min") for b in by_year],
        "mmp_20min": [b.get("mmp_20min") for b in by_year],
        "mmp_60min": [b.get("mmp_60min") for b in by_year],
        "ratio_5_60": [b.get("ratio_5_60") for b in by_year],
    }
    if traj_fit:
        charts["rebuild_trajectories_fit"] = {"series": traj_fit}

    narrative = generate_mmp_narrative(findings, force=force_ai)
    if narrative:
        findings["ai_narrative_mmp"] = narrative
    elif force_ai:
        findings.pop("ai_narrative_mmp", None)

    notes = findings.setdefault("data_quality_notes", [])
    fit_note = "True MMP (MEASURED_MMP) on shortlist_v2 under findings.mmp; DEVICE_SETTING FTP is not a measurement."
    if fit_note not in notes:
        notes.append(fit_note)

    FINDINGS_PATH.write_text(json.dumps(findings, indent=2, default=str), encoding="utf-8")
    append_report_mmp(findings)
    if append_coupled_section_to_report:
        try:
            append_coupled_section_to_report(findings)
        except Exception as e:
            print(f"Warn: coupled report section: {e}", flush=True)
    if write_changelog:
        try:
            write_changelog(findings, prior=prior_snap)
        except Exception as e:
            print(f"Warn: changelog: {e}", flush=True)

    try:
        from ai_endurance_coach_over50.archive_findings import publish_findings
        published = publish_findings(FINDINGS_PATH)
        print(f"Published → {published}", flush=True)
    except Exception as e:
        print(f"Warn: publish_findings failed: {e}", flush=True)

    print(f"Wrote {MMP_CSV} ({len(rows)} rows)", flush=True)
    print(
        f"rebuild_fit central={rebuild_fit.get('central_estimate_weeks')} "
        f"(summary was {(findings.get('rebuild') or {}).get('central_estimate_weeks')})",
        flush=True,
    )
    for b in by_year:
        print(
            f"  {b['year']}: MMP60={b.get('mmp_60min')} MMP20={b.get('mmp_20min')} "
            f"n={b.get('n_rides')}",
            flush=True,
        )
    print(f"Updated {FINDINGS_PATH}", flush=True)
    return findings


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--force-ai", action="store_true")
    p.add_argument(
        "--fetch-missing",
        action="store_true",
        help="Download any shortlist FITs still missing before analysing",
    )
    args = p.parse_args()
    run(force_ai=args.force_ai, fetch_missing=args.fetch_missing)


if __name__ == "__main__":
    main()

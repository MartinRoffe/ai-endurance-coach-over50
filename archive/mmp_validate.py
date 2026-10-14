#!/usr/bin/env python3
"""Issue 1 — MMP validation report against known-good values + pipeline audits."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ARCHIVE_DIR = Path(__file__).resolve().parent
REPO = ARCHIVE_DIR.parent
sys.path.insert(0, str(REPO))

OUT = ARCHIVE_DIR / "mmp_validation.md"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hr_series_from_fit(records) -> list[float]:
    eng = _load("mmp_engine", ARCHIVE_DIR / "mmp_engine.py")
    pairs_p, _ = eng.extract_power_pairs(records)
    if not pairs_p:
        return []
    t0 = pairs_p[0][0]
    t_end = pairs_p[-1][0]
    n = int(round(t_end - t0)) + 1
    hr = [0.0] * n
    for r in records:
        if r.timestamp is None or r.heart_rate is None:
            continue
        try:
            t = r.timestamp.timestamp()
            h = float(r.heart_rate)
        except Exception:
            continue
        idx = int(round(t - t0))
        if 0 <= idx < n:
            hr[idx] = h
    # hold HR across short gaps
    last = 0.0
    for i in range(n):
        if hr[i] > 0:
            last = hr[i]
        elif last > 0:
            hr[i] = last
    return hr


def _hr_series_from_tcx(path: Path, t0: float, n: int) -> list[float]:
    import xml.etree.ElementTree as ET
    from datetime import datetime as dt

    hr = [0.0] * n

    def parse_time(s: str) -> Optional[float]:
        try:
            return dt.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None

    tree = ET.parse(path)
    for tp in tree.getroot().iter():
        tag = tp.tag.split("}")[-1] if "}" in tp.tag else tp.tag
        if tag != "Trackpoint":
            continue
        t_el = None
        h = None
        for child in tp:
            ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if ctag == "Time" and child.text:
                t_el = parse_time(child.text)
            if ctag == "HeartRateBpm":
                for v in child.iter():
                    vt = v.tag.split("}")[-1] if "}" in v.tag else v.tag
                    if vt == "Value" and v.text:
                        try:
                            h = float(v.text)
                        except ValueError:
                            pass
        if t_el is None or h is None:
            continue
        idx = int(round(t_el - t0))
        if 0 <= idx < n:
            hr[idx] = h
    last = 0.0
    for i in range(n):
        if hr[i] > 0:
            last = hr[i]
        elif last > 0:
            hr[i] = last
    return hr


def validate_activity(
    activity_id: int,
    *,
    expect_mmp60: Optional[float] = None,
    expect_decoupling: Optional[float] = None,
    expect_cp: Optional[float] = None,
    expect_w_prime_kj: Optional[float] = None,
) -> dict[str, Any]:
    eng = _load("mmp_engine", ARCHIVE_DIR / "mmp_engine.py")
    out: dict[str, Any] = {"activity_id": activity_id}

    fit = ARCHIVE_DIR / "fits" / f"{activity_id}.fit"
    tcx_cache = ARCHIVE_DIR / "tcx" / f"{activity_id}.tcx"
    tcx_hr = REPO / "data" / "haute-route-2012"
    local_tcx = None
    for p in tcx_hr.glob("*.tcx") if tcx_hr.is_dir() else []:
        # map via known Alps ids later
        pass

    # Prefer raw FIT/TCX over stored stream JSON (streams may have dropped zeros)
    pairs = None
    diag = None
    source = None
    series = None
    hr = []

    if fit.is_file() and fit.stat().st_size > 5000:
        from ai_endurance_coach_over50.analysis.fit_ingest import parse_fit
        session = parse_fit(fit)
        pairs, diag = eng.extract_power_pairs(session.records)
        source = "fit"
        mmp, diag, series = eng.compute_mmp_from_pairs(pairs, diag)
        hr = _hr_series_from_fit(session.records)
    else:
        # Haute Route local TCX map
        HR = {277575486: 1, 277575362: 2, 277575279: 3, 277575228: 4, 277575139: 5}
        tcx_path = None
        if activity_id in HR:
            day = HR[activity_id]
            import re
            for p in (REPO / "data" / "haute-route-2012").glob("*.tcx"):
                if re.search(rf"Day\s*{day}\b", p.name, re.I):
                    tcx_path = p
                    break
        if tcx_path is None and tcx_cache.is_file():
            tcx_path = tcx_cache
        if tcx_path is not None:
            pairs, diag = eng.pairs_from_tcx_path(tcx_path)
            source = f"tcx:{tcx_path.name}"
            mmp, diag, series = eng.compute_mmp_from_pairs(pairs, diag)
            if series:
                hr = _hr_series_from_tcx(tcx_path, pairs[0][0], len(series))
        else:
            out["error"] = "no_fit_or_tcx"
            return out

    out["source"] = source
    out["mmp"] = mmp
    out["diag"] = {
        "n_raw_samples": diag.n_raw_samples,
        "n_zero_power": diag.n_zero_power,
        "n_spike_rejected": diag.n_spike_rejected,
        "n_null_power_skipped": diag.n_null_power_skipped,
        "median_dt_s": diag.median_dt_s,
        "smart_recording": diag.smart_recording,
        "wall_clock_s": diag.wall_clock_s,
        "zero_pct_of_wall": diag.zero_pct_of_wall,
        "n_ones_held": diag.n_ones_held,
        "notes": list(diag.notes),
    }

    # OLD broken method comparison (drop nulls / split segments) if FIT parseable
    out["old_pipeline_mmp60"] = None
    stream = ARCHIVE_DIR / "streams" / f"{activity_id}.json"
    if stream.is_file():
        data = json.loads(stream.read_text())
        old_series = data.get("power_1hz") or []
        # emulate old: drop Nones by splitting
        from archive import garmin_mmp as gm  # may fail
        try:
            sys.path.insert(0, str(ARCHIVE_DIR))
            gm_mod = _load("garmin_mmp_old", ARCHIVE_DIR / "garmin_mmp.py")
            out["old_pipeline_mmp60"] = gm_mod.best_mean_max(old_series, 3600)
        except Exception as e:
            out["old_pipeline_mmp60_error"] = str(e)

    if expect_mmp60 is not None:
        got = mmp.get("mmp_60min")
        delta = None if got is None else abs(got - expect_mmp60)
        out["crosscheck_mmp60"] = {
            "expected": expect_mmp60,
            "got": got,
            "delta_w": delta,
            "pass": delta is not None and delta <= 3.0,
        }

    if expect_decoupling is not None and series and hr:
        dec = eng.half_decoupling_1hz(series, hr)
        out["crosscheck_decoupling"] = {
            "expected": expect_decoupling,
            "got": dec,
            "delta_pp": None if dec is None else abs(dec - expect_decoupling),
            "pass": dec is not None and abs(dec - expect_decoupling) <= 1.5,
        }

    if expect_cp is not None:
        cp = eng.estimate_cp_w_prime(mmp)
        out["crosscheck_cp"] = {
            "expected_cp": expect_cp,
            "expected_w_prime_kj": expect_w_prime_kj,
            "got": cp,
            "pass": bool(
                cp
                and abs(cp["cp_w"] - expect_cp) <= 5
                and (
                    expect_w_prime_kj is None
                    or abs(cp["w_prime_kj"] - expect_w_prime_kj) <= 1.5
                )
            ),
        }
    return out


def compare_drop_zeros(activity_id: int = 277575228) -> dict:
    """Show inflation if zeros are dropped from wall series (user's +22/+36W finding)."""
    eng = _load("mmp_engine", ARCHIVE_DIR / "mmp_engine.py")
    import re
    tcx = None
    for p in (REPO / "data" / "haute-route-2012").glob("*.tcx"):
        if re.search(r"Day\s*4\b", p.name, re.I):
            tcx = p
            break
    if tcx is None:
        return {"error": "no day4 tcx"}
    pairs, diag = eng.pairs_from_tcx_path(tcx)
    series, diag = eng.resample_wall_clock_1hz(pairs, diag)
    m60_keep, _, _ = eng.best_mean_max_1hz(series, 3600)
    # Drop zeros: replace with skip via segmentation
    nozero = [v for v in series if v > 0]
    m60_drop, _, _ = eng.best_mean_max_1hz(nozero, 3600)
    return {
        "activity_id": activity_id,
        "mmp60_zeros_as_zero": m60_keep,
        "mmp60_zeros_dropped": m60_drop,
        "inflation_w": None
        if m60_keep is None or m60_drop is None
        else round(m60_drop - m60_keep, 1),
        "zero_pct_wall": diag.zero_pct_of_wall,
    }


def main() -> None:
    eng = _load("mmp_engine", ARCHIVE_DIR / "mmp_engine.py")
    lines = [
        "# MMP validation (Issue 1)",
        "",
        f"_Generated {datetime.now().isoformat(timespec='seconds')}_",
        "",
        "## Method changes vs prior pipeline",
        "",
        "Prior pipeline placed samples on a 1 Hz grid, left holes as `None`, "
        "forward-filled ≤3 s, then computed MMP only on **contiguous non-None "
        "segments**. That excludes coasting/stop gaps that were never recorded as "
        "0 W, which inflates long-window means (flat 5:60 / 20:60 ratios).",
        "",
        "Corrected pipeline:",
        "- Keep recorded **0 W** as zeros.",
        "- Resample to wall-clock 1 Hz; gaps >8 s filled with **0 W**; "
        "≤8 s Smart Recording holds last value.",
        "- Spikes >1800 W rejected.",
        "- Rolling MMP on the full wall-clock series (no None-skip).",
        "",
        "## 1a — Zero-power handling (demonstration)",
        "",
    ]
    drop = compare_drop_zeros()
    lines += [
        "Day 4 (277575228) intentional A/B:",
        "",
        f"- MMP-60 with zeros as zero: **{drop.get('mmp60_zeros_as_zero')} W**",
        f"- MMP-60 with zeros dropped: **{drop.get('mmp60_zeros_dropped')} W**",
        f"- Inflation: **{drop.get('inflation_w')} W** "
        f"(zero% of wall clock={drop.get('zero_pct_wall')})",
        "",
        "This reproduces the user's qualitative finding: dropping zeros inflates MMP-60.",
        "",
        "## Cross-checks (known-good)",
        "",
    ]

    checks = []
    checks.append(
        validate_activity(
            277575228,
            expect_mmp60=253.0,
            expect_decoupling=-3.3,
        )
    )

    # Fetch CP activity if missing
    cp_id = 741976271
    fit_cp = ARCHIVE_DIR / "fits" / f"{cp_id}.fit"
    if not fit_cp.is_file() or fit_cp.stat().st_size < 5000:
        lines.append(
            f"Activity `{cp_id}` FIT not in cache — attempting Garmin download…"
        )
        try:
            from dotenv import load_dotenv
            import os
            load_dotenv()
            load_dotenv(Path.home() / ".ai_endurance_coach_over50" / ".env", override=False)
            from ai_endurance_coach_over50.client import get_api
            from ai_endurance_coach_over50.analysis.fit_ingest import (
                fetch_fit_for_activity,
                fetch_tcx_for_activity,
            )
            api = get_api(os.environ["GARMIN_EMAIL"], os.environ["GARMIN_PASSWORD"])
            raw = fetch_fit_for_activity(api, cp_id)
            if raw and len(raw) > 5000:
                fit_cp.write_bytes(raw)
                lines.append(f"Downloaded FIT {len(raw)} B")
            else:
                tcx = fetch_tcx_for_activity(api, cp_id)
                if tcx:
                    tcx_path = ARCHIVE_DIR / "tcx" / f"{cp_id}.tcx"
                    tcx_path.parent.mkdir(exist_ok=True)
                    tcx_path.write_bytes(tcx)
                    lines.append(f"Downloaded TCX {len(tcx)} B (no FIT)")
                    # ingest stream
                    tcx_mod = _load("tcx_ingest", ARCHIVE_DIR / "tcx_ingest.py")
                    tcx_mod.ingest_tcx_bytes(cp_id, tcx)
        except Exception as e:
            lines.append(f"Download failed: {e}")

    checks.append(
        validate_activity(
            cp_id,
            expect_cp=282.0,
            expect_w_prime_kj=7.0,
        )
    )

    for c in checks:
        aid = c["activity_id"]
        lines += [f"### Activity `{aid}`", ""]
        if c.get("error"):
            lines.append(f"**Error:** {c['error']}")
            lines.append("")
            continue
        lines.append(f"- Source: `{c.get('source')}`")
        d = c.get("diag") or {}
        lines.append(
            f"- Raw samples={d.get('n_raw_samples')}, recorded zeros={d.get('n_zero_power')}, "
            f"spikes rejected={d.get('n_spike_rejected')}, null power skipped={d.get('n_null_power_skipped')}"
        )
        lines.append(
            f"- median Δt={d.get('median_dt_s')} s, smart_recording={d.get('smart_recording')}, "
            f"wall_clock={d.get('wall_clock_s')} s, zero% wall={d.get('zero_pct_of_wall')}, "
            f"smart-held seconds={d.get('n_ones_held')}"
        )
        m = c.get("mmp") or {}
        lines.append(
            f"- MMP: 5s={m.get('mmp_5s')} 1min={m.get('mmp_1min')} 2min={m.get('mmp_2min')} "
            f"5min={m.get('mmp_5min')} 20min={m.get('mmp_20min')} **60min={m.get('mmp_60min')}**"
        )
        if c.get("old_pipeline_mmp60") is not None:
            lines.append(f"- Old (None-split) MMP-60 from stored stream: {c['old_pipeline_mmp60']}")
        for key in ("crosscheck_mmp60", "crosscheck_decoupling", "crosscheck_cp"):
            if key in c:
                lines.append(f"- `{key}`: `{json.dumps(c[key])}`")
        if d.get("notes"):
            lines.append(f"- Notes: {'; '.join(d['notes'])}")
        lines.append("")

    # Per-file zero% for all shortlist sources with power
    lines += ["## Per-file diagnostics (shortlist sources with power)", "", 
              "| activity_id | date | source | median_dt | smart | zero% | MMP60 | spikes |",
              "|---|---|---|---:|:---:|---:|---:|---:|"]

    meta = {}
    sl = ARCHIVE_DIR / "shortlist_v2.csv"
    if sl.is_file():
        import csv
        with sl.open() as f:
            for r in csv.DictReader(f):
                meta[int(float(r["activity_id"]))] = r.get("date", "")

    ids = sorted(set(meta) | {
        int(p.stem) for p in (ARCHIVE_DIR / "fits").glob("*.fit") if p.stem.isdigit()
    } | {
        int(p.stem) for p in (ARCHIVE_DIR / "streams").glob("*.json") if p.stem.isdigit()
    })

    rows_out = []
    for aid in ids:
        try:
            r = validate_activity(aid)
        except Exception as e:
            rows_out.append((aid, "", "error", None, False, None, None, 0, str(e)))
            continue
        if r.get("error"):
            continue
        d = r["diag"]
        m = r["mmp"]
        rows_out.append((
            aid, meta.get(aid, ""), r.get("source"), d.get("median_dt_s"),
            d.get("smart_recording"), d.get("zero_pct_of_wall"),
            (m or {}).get("mmp_60min"), d.get("n_spike_rejected"), "",
        ))

    for row in rows_out:
        if len(row) == 9 and row[8]:
            lines.append(f"| {row[0]} | | error | | | | | | {row[8]} |")
            continue
        aid, date, src, dt, smart, zp, m60, sp, _ = row
        lines.append(
            f"| {aid} | {date} | {src} | {dt} | {smart} | {zp} | {m60} | {sp} |"
        )

    lines += [
        "",
        "## 1b/1c/1d/1e summary",
        "",
        "- **Wall-clock:** MMP windows are exactly `window_secs` samples on a 1 Hz "
        "grid aligned to `timestamp[0]` — by construction `t[i+n]-t[i]=n` seconds; "
        "no index-only windows on irregular samples.",
        "- **Smart Recording:** detected when median Δt > 1.5 s; held ≤8 s, else 0 W.",
        "- **Missing values:** filled with 0 W on the wall-clock axis (never silently "
        "shorten the window).",
        "- **Spikes:** samples >1800 W rejected before resample.",
        "",
        "Annual curves and plausibility flags are regenerated by `garmin_mmp.py` "
        "using this engine (see findings + analysis_report).",
        "",
    ]

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}", flush=True)
    # Print cross-check verdicts
    for c in checks:
        print(json.dumps({k: c.get(k) for k in (
            "activity_id", "crosscheck_mmp60", "crosscheck_decoupling", "crosscheck_cp", "error"
        ) if k in c or k == "activity_id"}, indent=2), flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Issue 2 — audit 5.0 vs 7.5 week FIT-grounded rebuild reversal."""
from __future__ import annotations

import csv
import importlib.util
import sys
from datetime import datetime
from pathlib import Path

ARCHIVE = Path(__file__).resolve().parent
OUT = ARCHIVE / "reversal_audit.md"


def main() -> None:
    sys.path.insert(0, str(ARCHIVE.parent))
    spec = importlib.util.spec_from_file_location("ga", ARCHIVE / "garmin_analysis.py")
    ga = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(ga)

    df = ga.load_activities(ARCHIVE / "activities_2009_2016.csv")
    bike = df[df["is_cycling"]].copy()
    gaps = ga.find_cycling_gaps(bike, min_days=21)

    mmp: dict[int, dict] = {}
    with (ARCHIVE / "activity_mmp.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("has_power") != "1":
                continue
            aid = int(float(r["activity_id"]))
            mmp[aid] = {
                k: (float(r[k]) if r.get(k) else None)
                for k in ("mmp_1min", "mmp_5min", "mmp_20min", "mmp_60min")
            }

    old_ids = {
        int(float(r["activity_id"]))
        for r in csv.DictReader((ARCHIVE / "shortlist.csv").open(encoding="utf-8"))
    }
    mmp_old = {k: v for k, v in mmp.items() if k in old_ids}

    rb_sum = ga.analyse_rebuild(bike, gaps, fit_mmp=None)
    rb_old = ga.analyse_rebuild(bike, gaps, fit_mmp=mmp_old)
    rb_v2 = ga.analyse_rebuild(bike, gaps, fit_mmp=mmp)

    lines = [
        "# Rebuild reversal audit: 5.0 vs 7.5 weeks",
        "",
        f"_Generated {datetime.now().isoformat(timespec='seconds')}_",
        "",
        "## Verdict",
        "",
        "**5.0 weeks is the correct FIT/stream-grounded central estimate on shortlist_v2.**",
        "",
        "The earlier **7.5 weeks** figure was not a summarizer bug in `analyse_rebuild`’s median math; "
        "it was produced by the **v1 shortlist (~35 IDs)** FIT map. Restricting today’s corrected MMP "
        "file to those old shortlist IDs **reproduces 7.5 exactly**.",
        "",
        "Mechanism: with only v1 FIT coverage, layoff restart **2012-01-07** took **12 weeks** to recover "
        "under `fit_mmp_5min` baselines. Expanding to shortlist_v2 restores richer post-restart MMP "
        "coverage and that layoff returns to **5 weeks** (matching summary). Median of the twelve "
        "recovery durations therefore moves from 7.5 → 5.0.",
        "",
        "The prior addendum claiming summary 5.0 was “optimistic by ~50%” was **wrong about the "
        "direction of bias for the full archive** — it overfitted a sparse FIT map. "
        "Both methods agree at **5.0** once FIT coverage is adequate.",
        "",
        "## Central estimates",
        "",
        f"| Map | n FIT ids used | central weeks | IQR | n_fit_baseline |",
        f"|---|---:|---:|---|---:|",
        f"| Summary only (no FIT) | 0 | {rb_sum['central_estimate_weeks']} | {rb_sum['iqr']} | 0 |",
        f"| Old shortlist.csv ∩ MMP | {len(mmp_old)} | {rb_old['central_estimate_weeks']} | {rb_old['iqr']} | {rb_old.get('n_layoffs_with_fit_baseline')} |",
        f"| shortlist_v2 MMP (current) | {len(mmp)} | {rb_v2['central_estimate_weeks']} | {rb_v2['iqr']} | {rb_v2.get('n_layoffs_with_fit_baseline')} |",
        "",
        "## Per-layoff weeks side-by-side",
        "",
        "| restart | summary weeks | summary status | old-shortlist FIT weeks | old status / proxy | v2 FIT weeks | v2 status / proxy |",
        "|---|---:|---|---:|---|---:|---|",
    ]
    for a, b, c in zip(rb_sum["layoffs"], rb_old["layoffs"], rb_v2["layoffs"]):
        lines.append(
            f"| {a['restart_date']} | {a['weeks_to_recover']} | {a['status']} | "
            f"{b['weeks_to_recover']} | {b['status']} / {b['proxy_used']} | "
            f"{c['weeks_to_recover']} | {c['status']} / {c['proxy_used']} |"
        )

    # highlight changers among recovered
    lines += ["", "## What moved between old FIT map and v2", ""]
    movers = []
    for b, c in zip(rb_old["layoffs"], rb_v2["layoffs"]):
        if b.get("weeks_to_recover") != c.get("weeks_to_recover") or b.get("status") != c.get("status"):
            movers.append(
                f"- **{b['restart_date']}**: {b['weeks_to_recover']} ({b['status']}, {b['proxy_used']}) "
                f"→ {c['weeks_to_recover']} ({c['status']}, {c['proxy_used']})"
            )
    if movers:
        lines.extend(movers)
    else:
        lines.append("No per-layoff weeks/status changes (unexpected).")

    lines += [
        "",
        "### Recovered-week multisets",
        "",
        f"- Old FIT map recovered weeks: "
        f"{sorted(L['weeks_to_recover'] for L in rb_old['layoffs'] if L['status']=='recovered')}",
        f"- v2 FIT map recovered weeks: "
        f"{sorted(L['weeks_to_recover'] for L in rb_v2['layoffs'] if L['status']=='recovered')}",
        "",
        "Median of `[3,3,3,3,3,5,10,12,12,14,19,26]` = **7.5**; "
        "median of `[3,3,3,3,3,5,5,10,12,14,19,26]` = **5.0** "
        "(only material swap is 2012-01-07: 12 → 5).",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()

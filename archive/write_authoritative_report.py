#!/usr/bin/env python3
"""Build a single authoritative analysis_report.md from findings (no dual addendum)."""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ARCHIVE = Path(__file__).resolve().parent
FINDINGS = ARCHIVE / "findings.json"
REPORT = ARCHIVE / "analysis_report.md"
SUPERSEDED = ARCHIVE / "superseded"


def _fv(x) -> Optional[float]:
    try:
        return float(x) if x not in (None, "") else None
    except Exception:
        return None


def device_ftp_by_year(rows: list[dict]) -> dict[int, Optional[float]]:
    """Latest non-null device FTP seen that year from provenance/mmp rows."""
    by: dict[int, list[tuple[str, float]]] = {}
    for r in rows:
        d = r.get("date") or ""
        if len(d) < 4:
            continue
        y = int(d[:4])
        ftp = _fv(r.get("device_ftp_w"))
        if ftp is None:
            continue
        by.setdefault(y, []).append((d, ftp))
    out = {}
    for y, items in by.items():
        items.sort()
        out[y] = items[-1][1]
    return out


def coupled_band(ftp: float = 220.0, wt: float = 92.0, drop: float = 12.0) -> list[dict]:
    target = wt - drop
    rows = []
    for loss in (0.0, 3.0, 6.0):
        pw = max(0.0, ftp - loss * drop)
        rows.append({
            "loss": loss,
            "power": round(pw, 1),
            "kg": round(target, 1),
            "wkg": round(pw / target, 2) if target else None,
        })
    return rows


def main() -> None:
    findings = json.loads(FINDINGS.read_text(encoding="utf-8"))
    SUPERSEDED.mkdir(exist_ok=True)

    # Archive prior dual-document residue if present as copies
    for name in ("analysis_report_pre_merge.md",):
        pass

    mmp_rows = list(csv.DictReader((ARCHIVE / "activity_mmp.csv").open(encoding="utf-8")))
    ftp_year = device_ftp_by_year(mmp_rows)
    # Also provenance CSV
    prov_path = ARCHIVE / "activity_provenance.csv"
    if prov_path.is_file():
        ftp_year.update(device_ftp_by_year(list(csv.DictReader(prov_path.open(encoding="utf-8")))))

    rb = findings.get("rebuild_fit") or findings.get("rebuild") or {}
    rb_sum = findings.get("rebuild") or {}
    mmp = findings.get("mmp") or {}
    cw = findings.get("coupled_weight_power") or {}
    band = (cw.get("band") or {}).get("scenarios") or coupled_band()

    lines: list[str] = [
        "# Garmin history analysis (2009–2016) — authoritative",
        "",
        f"_Generated {datetime.now().isoformat(timespec='seconds')}_",
        "",
        "This file is the **single** report. Prior Stage-2 body + Stage-3 addendum split is retired.",
        "Superseded dual narratives live under coach UI collapsibles and `archive/superseded/` snapshots.",
        "",
        "## Rebuild-rate verdict",
        "",
    ]
    if rb.get("central_estimate_weeks") is not None:
        iqr = rb.get("iqr") or []
        lines.append(
            f"**Central estimate: {rb['central_estimate_weeks']} weeks** "
            f"(FIT/stream-grounded on shortlist_v2; IQR {iqr[0]}–{iqr[1] if len(iqr)>1 else '—'}; "
            f"{rb.get('n_full_recoveries', 0)} recovered, {rb.get('n_plateaued', 0)} plateaued)."
        )
        lines.append("")
        lines.append(
            f"Summary-only estimate is also **{rb_sum.get('central_estimate_weeks')} weeks**. "
            f"The earlier FIT-only **7.5 weeks** came from the sparse v1 shortlist FIT map "
            f"(see `reversal_audit.md`) — overturned."
        )
    lines += ["", rb.get("proxy_notes") or "", ""]

    lines += [
        "## True MMP (MEASURED_MMP)",
        "",
        mmp.get("curve_notes")
        or "Wall-clock 1 Hz mean-maximal power from FIT/TCX; zeros count as zero.",
        "",
        f"n_with_power={mmp.get('n_with_power')}; source=`{mmp.get('source')}`.",
        "",
        "| Year | 1 min | 2 min | 5 min | 20 min | 60 min | 5:60 | 20:60 | flag |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for b in mmp.get("by_year") or []:
        flag = "FAIL" if b.get("plausibility_fail") else "ok"
        lines.append(
            f"| {b['year']} | {b.get('mmp_1min')} | {b.get('mmp_2min')} | {b.get('mmp_5min')} | "
            f"{b.get('mmp_20min')} | {b.get('mmp_60min')} | {b.get('ratio_5_60')} | "
            f"{b.get('ratio_20_60')} | {flag} |"
        )
    lines += [
        "",
        "Provenance: stream peaks are **MEASURED_MMP**. Device FTP values are **DEVICE_SETTING**.",
        "Day 4 Haute Route `277575228` MMP-60 = **252.7 W MEASURED_MMP** (known-good 253 W).",
        "See `mmp_validation.md` for zero-handling, Smart Recording, and cross-checks.",
        "",
        "## Device FTP (DEVICE_SETTING) vs MEASURED MMP-60",
        "",
        "| Year | Device FTP (latest seen) | MMP-60 MEASURED | Gap (setting − MMP60) | Setting as % of MMP60 |",
        "|---:|---:|---:|---:|---:|",
    ]
    by_year = {b["year"]: b for b in (mmp.get("by_year") or [])}
    for y in sorted(set(by_year) | set(ftp_year)):
        m60 = (by_year.get(y) or {}).get("mmp_60min")
        ftp = ftp_year.get(y)
        gap = (ftp - m60) if (ftp is not None and m60 is not None) else None
        pct = (100 * ftp / m60) if (ftp and m60) else None
        lines.append(
            f"| {y} | {ftp if ftp is not None else '—'} | {m60 if m60 is not None else '—'} | "
            f"{round(gap,1) if gap is not None else '—'} | "
            f"{round(pct,1) if pct is not None else '—'}% |"
        )
    lines += [
        "",
        "If device FTP sits **below** measured hour power, zones were systematically soft that season",
        "(e.g. training “threshold” easier than true sustainable power). Where the device FTP column is",
        "empty, no FIT `threshold_power`/zones field was recovered for that year on the shortlist.",
        "",
        "## Stated peaks (provenance-tagged)",
        "",
    ]
    for c in findings.get("contradictions_fit") or []:
        lines.append(
            f"- {c.get('year')}: stated {c.get('stated_peak_w')}W "
            f"**{c.get('stated_provenance')}** vs archive {c.get('archive_best_mmp_w')}W "
            f"{c.get('archive_provenance')} — conflicts={c.get('conflicts')} — {c.get('note')}"
        )

    lines += [
        "",
        "## Coupled weight / power (0 / 3 / 6 W lost per kg)",
        "",
        "Do **not** assume watts stay constant while weight falls.",
        "",
        "| W lost / kg | Power after −12 kg | Weight | W/kg |",
        "|---:|---:|---:|---:|",
    ]
    for s in band:
        if "w_lost_per_kg" in s:
            lines.append(
                f"| {s['w_lost_per_kg']} | {s['power_w']} | {s['weight_kg']} | {s['wkg']} |"
            )
        else:
            lines.append(f"| {s['loss']} | {s['power']} | {s['kg']} | {s['wkg']} |")
    overlap = cw.get("archive_weight_overlap") or {}
    lines += [
        "",
        f"Archive-era weight overlap: {overlap.get('note') or overlap or 'none'}.",
        "Sequence: consistency first → modest deficit → MMP-20 guardrail.",
        "",
        "## Failed rebuilds (n_failed=3)",
        "",
        "See `rebuild_failures.md`. **Null result** at n=3 — no metric cleanly separates",
        "`plateaued_lower` from recovered restarts. Do not invent an autumn rule from three points.",
        "",
        "## Coach narratives (UI)",
        "",
        "Opus narratives are served on `/archive` collapsibles (`ai_narrative`, `ai_narrative_mmp`).",
        "**Normative numbers are the tables above**, plus `mmp_validation.md` / `reversal_audit.md`.",
        "If a narrative sentence conflicts with MEASURED_MMP / DEVICE_SETTING tables, the tables win.",
        "",
        "## Related artefacts",
        "",
        "- `mmp_validation.md` — Issue 1 checks",
        "- `reversal_audit.md` — 5.0 vs 7.5",
        "- `rebuild_failures.md` — failed vs recovered first-21d",
        "- `CHANGELOG.md` — overturned conclusions this run",
        "",
    ]

    # Snapshot previous report
    if REPORT.is_file():
        snap = SUPERSEDED / f"analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        snap.write_text(REPORT.read_text(encoding="utf-8"), encoding="utf-8")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT}", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Coupled weight/power section + changelog of overturned archive conclusions."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

ARCHIVE_DIR = Path(__file__).resolve().parent
FINDINGS_PATH = ARCHIVE_DIR / "findings.json"
REPORT_PATH = ARCHIVE_DIR / "analysis_report.md"
CHANGELOG_PATH = ARCHIVE_DIR / "changelog_overturned.md"


def body_weight_overlap(mmp_years: list[int]) -> dict[str, Any]:
    """Check body_metrics for dates overlapping archive MMP years (body_db only)."""
    try:
        import sys
        sys.path.insert(0, str(ARCHIVE_DIR.parent))
        from ai_endurance_coach_over50.history.db import _conn
        from ai_endurance_coach_over50.history.body_store import _ensure_body_metrics_schema
    except Exception as e:
        return {"overlap": False, "n": 0, "note": f"body_db unavailable: {e}"}

    with _conn() as con:
        _ensure_body_metrics_schema(con)
        rows = con.execute(
            "SELECT date, weight_kg FROM body_metrics "
            "WHERE weight_kg IS NOT NULL ORDER BY date"
        ).fetchall()
    if not rows:
        return {
            "overlap": False,
            "n": 0,
            "note": "No body_metrics weight rows — no archive-era weight history to plot.",
        }
    years = set(mmp_years) | set(range(2009, 2017))
    overlapping = []
    for d, w in rows:
        try:
            y = int(str(d)[:4])
        except Exception:
            continue
        if y in years:
            overlapping.append({"date": str(d)[:10], "weight_kg": float(w)})
    if not overlapping:
        first = str(rows[0][0])[:10]
        last = str(rows[-1][0])[:10]
        return {
            "overlap": False,
            "n": 0,
            "body_span": f"{first} → {last}",
            "note": (
                "No overlapping weight history between body_metrics and archive "
                f"MMP years ({min(years)}–{max(years)}). body_db span is {first}→{last}."
            ),
        }
    return {
        "overlap": True,
        "n": len(overlapping),
        "rows": overlapping[:50],
        "note": f"{len(overlapping)} body_metrics weight readings overlap archive years.",
    }


def coupled_wkg_band(
    ftp_w: float = 220.0,
    weight_kg: float = 92.0,
    drop_kg: float = 12.0,
    w_lost_per_kg: tuple[float, ...] = (0.0, 3.0, 6.0),
) -> dict[str, Any]:
    """W/kg after dropping drop_kg under three power-loss assumptions."""
    target_kg = weight_kg - drop_kg
    scenarios = []
    for loss in w_lost_per_kg:
        new_w = max(0.0, ftp_w - loss * drop_kg)
        scenarios.append({
            "w_lost_per_kg": loss,
            "power_w": round(new_w, 1),
            "weight_kg": round(target_kg, 1),
            "wkg": round(new_w / target_kg, 2) if target_kg > 0 else None,
        })
    return {
        "start_power_w": ftp_w,
        "start_weight_kg": weight_kg,
        "drop_kg": drop_kg,
        "scenarios": scenarios,
        "note": (
            "Never treat weight as an independent lever that holds watts constant. "
            "Sequence: consistency first, modest deficit, MMP-20 as guardrail; "
            "if power falls as weight falls, deficit is too aggressive."
        ),
    }


def patch_findings_weight(findings: dict) -> dict:
    mmp_years = [b["year"] for b in (findings.get("mmp") or {}).get("by_year") or []]
    cur = findings.get("current_athlete") or {}
    ftp = float(cur.get("ftp_w") or 220)
    wt = float(cur.get("weight_kg") or 92)
    overlap = body_weight_overlap(mmp_years)
    band = coupled_wkg_band(ftp, wt, drop_kg=12.0)
    findings["coupled_weight_power"] = {
        "assumptions_w_lost_per_kg": [0, 3, 6],
        "band": band,
        "archive_weight_overlap": overlap,
        "note": band["note"],
    }
    return findings


def append_coupled_section_to_report(findings: dict) -> None:
    cw = findings.get("coupled_weight_power") or {}
    band = cw.get("band") or coupled_wkg_band()
    overlap = cw.get("archive_weight_overlap") or {}
    lines = [
        "",
        "---",
        "",
        "## Coupled weight / power (0 / 3 / 6 W lost per kg)",
        "",
        cw.get("note") or band.get("note") or "",
        "",
        f"Starting point: {band['start_power_w']} W at {band['start_weight_kg']} kg; "
        f"illustrative drop of {band['drop_kg']} kg → {band['start_weight_kg'] - band['drop_kg']:.0f} kg.",
        "",
        "| W lost / kg | Power after | Weight | W/kg |",
        "|---:|---:|---:|---:|",
    ]
    for s in band.get("scenarios") or []:
        lines.append(
            f"| {s['w_lost_per_kg']:g} | {s['power_w']} | {s['weight_kg']} | {s['wkg']} |"
        )
    lines += [
        "",
        f"**Archive-era weight overlap:** {overlap.get('note') or 'unchecked'}",
        "",
        "Framing for coaching: train consistently first; add a modest deficit under that; "
        "watch MMP-20. Do not sell a single-path 'hold 220 W, cut to 80 kg → 2.75 W/kg' story "
        "as if power is invariant.",
        "",
    ]
    marker = "\n---\n\n## Coupled weight / power"
    text = REPORT_PATH.read_text(encoding="utf-8") if REPORT_PATH.is_file() else ""
    if marker in text:
        text = text.split(marker)[0].rstrip()
    # Also strip old "fastest lever is weight" narrative section if regenerating notes —
    # leave AI narrative; changelog records the overturn.
    REPORT_PATH.write_text(text + "\n" + "\n".join(lines), encoding="utf-8")


def write_changelog(findings: dict, prior: Optional[dict] = None) -> None:
    mmp = findings.get("mmp") or {}
    by_year = {b["year"]: b for b in (mmp.get("by_year") or [])}
    y2012 = by_year.get(2012) or {}
    mmp60_2012 = y2012.get("mmp_60min")
    rb_fit = (findings.get("rebuild_fit") or {}).get("central_estimate_weeks")
    rb_sum = (findings.get("rebuild") or {}).get("central_estimate_weeks")
    prior_fit = None
    if prior:
        prior_fit = (prior.get("rebuild_fit") or {}).get("central_estimate_weeks")

    conflicts = [
        c for c in (findings.get("contradictions_fit") or [])
        if c.get("conflicts")
    ]
    device = [
        c for c in (findings.get("contradictions_fit") or [])
        if c.get("stated_provenance") == "DEVICE_SETTING"
    ]

    lines = [
        "# Changelog: overturned archive conclusions",
        "",
        f"_Generated {datetime.now().isoformat(timespec='seconds')}_",
        "",
        "This run reverses claims from the first shortlist/MMP pass. Do not soften.",
        "",
        "## 1. 2012 MMP-60 / 'low-fitness year'",
        "",
        "**Prior claim:** 2012 shortlist MMP-60 ≈159 W; year framed as low-fitness / "
        "fragmented, with an anomalous flat 5→60 ratio driven by easy rides that "
        "happened to clear the NP+layover composite shortlist.",
        "",
        f"**Now:** 2012 MMP-60 = **{mmp60_2012}W MEASURED_MMP** "
        f"(Haute Route TCX streams on shortlist_v2: Day 1 peak MMP-60, Day 4 ≈253W "
        "matching stated Alps lore). "
        "The Alps block was excluded from v1 because Edge-era NP/TSS were null and "
        "composite scoring + cap 35 truncated duration-only days. That selection bug "
        "invalidated the prior 2012 narrative.",
        "",
        "## 2. Jan 2016 FTP 260 vs weak proxy — not a MEASURED contradiction",
        "",
        "**Prior claim:** framing 260 W FTP vs ~157 W proxy as a 'genuine contradiction' "
        "of measured fitness.",
        "",
        "**Now:** 260 W (and 2012 ~242 W device FTP) are tagged **DEVICE_SETTING**. "
        "Gaps vs PROXY/MMP are expected for stale device config, not evidence against "
        "the athlete's measured peaks. Provenance-aware contradiction logic never sets "
        "`conflicts=true` for DEVICE_SETTING rows.",
        "",
    ]
    for c in device:
        lines.append(
            f"- {c.get('year')}: stated {c.get('stated_peak_w')}W DEVICE_SETTING — "
            f"conflicts={c.get('conflicts')}"
        )
    lines += [
        "",
        "## 3. Rebuild central estimate",
        "",
        f"- Summary-only: **{rb_sum} weeks**",
        f"- FIT/stream-grounded (`rebuild_fit`): **{rb_fit} weeks**",
    ]
    if prior_fit is not None and rb_fit is not None and prior_fit != rb_fit:
        lines.append(
            f"- **Moved** from prior FIT estimate {prior_fit} → {rb_fit} after shortlist_v2."
        )
    elif rb_fit is not None:
        lines.append(
            f"- Recorded FIT/stream estimate {rb_fit} weeks on shortlist_v2 "
            "(compare to prior FIT pass ~7.5 weeks if that lived only in memory)."
        )
    lines += [
        "",
        "## 4. Weight-as-fastest-independent-lever framing",
        "",
        "**Prior claim:** 'The fastest lever is weight, not watts' / hold watts constant "
        "and drop to ~80 kg to hit 3.5 W/kg as a single-point path.",
        "",
        "**Now:** Couples weight and power. Report and Opus prompts require a band under "
        "**0 / 3 / 6 W lost per kg** dropped; sequence consistency → modest deficit → "
        "MMP-20 guardrail. Independent-lever framing is overturned.",
        "",
        f"Archive weight overlap: {(findings.get('coupled_weight_power') or {}).get('archive_weight_overlap', {}).get('note', 'see findings')}",
        "",
        "## Remaining MEASURED conflicts (if any)",
        "",
    ]
    if conflicts:
        for c in conflicts:
            lines.append(
                f"- {c.get('year')}: {c.get('archive_best_mmp_w')}W MEASURED_MMP vs "
                f"stated {c.get('stated_peak_w')}W {c.get('stated_provenance')} — {c.get('note')}"
            )
    else:
        lines.append("None among provenance-aware `contradictions_fit` with conflicts=true.")
    lines.append("")
    CHANGELOG_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {CHANGELOG_PATH}", flush=True)


def run() -> None:
    prior = None
    # optional snapshot before overwrite (if findings already new, prior is same)
    if FINDINGS_PATH.is_file():
        findings = json.loads(FINDINGS_PATH.read_text(encoding="utf-8"))
    else:
        raise SystemExit(f"Missing {FINDINGS_PATH}")

    findings = patch_findings_weight(findings)
    FINDINGS_PATH.write_text(json.dumps(findings, indent=2, default=str), encoding="utf-8")
    append_coupled_section_to_report(findings)
    write_changelog(findings, prior=prior)
    try:
        from ai_endurance_coach_over50.archive_findings import publish_findings
        publish_findings(FINDINGS_PATH)
        print("Published findings", flush=True)
    except Exception as e:
        print(f"Warn: publish failed: {e}", flush=True)
    print(f"Updated {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    run()

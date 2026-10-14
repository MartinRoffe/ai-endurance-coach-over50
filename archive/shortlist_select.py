#!/usr/bin/env python3
"""Shortlist v2: diagnostic replay of v1 scoring + multi-criteria union selection."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

ARCHIVE_DIR = Path(__file__).resolve().parent
ACTIVITIES_CSV = ARCHIVE_DIR / "activities_2009_2016.csv"
DIAG_PATH = ARCHIVE_DIR / "shortlist_diagnosis.md"
SHORTLIST_V2 = ARCHIVE_DIR / "shortlist_v2.csv"

ALPS_IDS = [277575486, 277575362, 277575279, 277575228, 277575139]  # Days 1–5


def _num(v: Any) -> Optional[float]:
    if v is None or v == "" or (isinstance(v, float) and math.isnan(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_bike(csv_path: Path = ACTIVITIES_CSV):
    sys.path.insert(0, str(ARCHIVE_DIR.parent))
    # Reuse analysis loader
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "garmin_analysis", ARCHIVE_DIR / "garmin_analysis.py"
    )
    assert spec and spec.loader
    ga = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ga)
    df = ga.load_activities(csv_path)
    bike = df[df["is_cycling"]].copy()
    gaps = ga.find_cycling_gaps(bike, min_days=21)
    return ga, bike, gaps


def replay_v1_scores(bike, gaps: list[dict], limit: int = 35) -> tuple[list[dict], dict[int, dict]]:
    """Replay legacy composite scoring; return (ranked_top, all_scored_by_id)."""
    scores: dict[int, dict] = {}

    def bump(aid, reason, pts, row):
        if aid is None or (isinstance(aid, float) and math.isnan(aid)):
            return
        key = int(aid)
        ent = scores.setdefault(key, {
            "activity_id": key,
            "date": "",
            "score": 0.0,
            "reasons": [],
            "bumps": [],
        })
        ent["score"] += pts
        ent["bumps"].append({"reason": reason, "pts": pts})
        if reason not in ent["reasons"]:
            ent["reasons"].append(reason)
        if row is not None:
            d = row["date"]
            ent["date"] = d.date().isoformat() if hasattr(d, "date") else str(d)[:10]
            np_v = _num(row.get("normalized_power"))
            if np_v is not None:
                ent["np"] = np_v
            ent["duration_s"] = _num(row.get("duration_s"))
            ent["avg_power"] = _num(row.get("avg_power"))
            ent["tss"] = _num(row.get("tss"))
            ent["elevation_gain_m"] = _num(row.get("elevation_gain_m"))

    major = [g for g in gaps if g["length_days"] >= 42]
    for g in major:
        restart = date.fromisoformat(g["end"])
        after = bike[bike["date"].dt.date >= restart].head(5)
        for i, (_, row) in enumerate(after.iterrows()):
            bump(row.get("activity_id"), f"post_layoff_{g['start']}", 50 - i * 5, row)

    np_rides = bike[bike["normalized_power"].notna()].nlargest(15, "normalized_power")
    for _, row in np_rides.iterrows():
        bump(row.get("activity_id"), "high_np", 30, row)

    long_rides = bike.nlargest(15, "duration_s")
    for _, row in long_rides.iterrows():
        bump(row.get("activity_id"), "longest", 20, row)

    ef = bike[
        bike["normalized_power"].notna()
        & bike["avg_hr"].notna()
        & (bike["avg_hr"] > 0)
        & (bike["duration_s"] > 3600)
    ].copy()
    if not ef.empty:
        ef = ef.copy()
        ef["ef"] = ef["normalized_power"] / ef["avg_hr"]
        for _, row in ef.nlargest(8, "ef").iterrows():
            bump(row.get("activity_id"), "high_ef", 25, row)
        for _, row in ef.nsmallest(5, "ef").iterrows():
            bump(row.get("activity_id"), "low_ef", 15, row)

    all_ranked = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    for i, r in enumerate(all_ranked, 1):
        r["rank"] = i
    return all_ranked[:limit], {int(r["activity_id"]): r for r in all_ranked}


def np_tss_null_rates(bike) -> list[dict]:
    rows = []
    for year, g in bike.groupby(bike["date"].dt.year):
        n = len(g)
        np_null = int(g["normalized_power"].isna().sum())
        tss_null = int(g["tss"].isna().sum()) if "tss" in g.columns else n
        avg_null = int(g["avg_power"].isna().sum())
        rows.append({
            "year": int(year),
            "n_cycling": n,
            "np_null_pct": round(100 * np_null / n, 1) if n else None,
            "tss_null_pct": round(100 * tss_null / n, 1) if n else None,
            "avg_power_null_pct": round(100 * avg_null / n, 1) if n else None,
            "np_null": np_null,
            "tss_null": tss_null,
        })
    return rows


def write_diagnosis(bike, gaps) -> None:
    top35, all_scored = replay_v1_scores(bike, gaps, limit=35)
    cut_score = top35[-1]["score"] if top35 else None
    lines = [
        "# Shortlist v1 diagnosis — Alps exclusion",
        "",
        "## Root cause",
        "",
        "The Haute Route Alps activities **are present** in `activities_2009_2016.csv` "
        "with `avg_power` and elevation, but Garmin list-API fields `normalized_power` and "
        "`tss` are **null** on these 2012 Edge-era records.",
        "",
        "v1 `build_shortlist` used a **single composite score**: post-layoff (+50…+30), "
        "top-15 NP (+30), top-15 duration (+20), EF needing NP (+25/+15). Alps Day 4 "
        "(`277575228`) only earned `longest` (+20). The shortlist cut at N=35 was dominated "
        "by layoff+NP+EF stacks (70–120). **Limit 35 truncated all Alps rides.** "
        "Not a string-sort bug and not a duration filter.",
        "",
        f"Cut line at rank 35: score **{cut_score}**.",
        "",
        "## Alps ID score replay",
        "",
        "| Activity ID | Date | Score | Rank | In top 35? | Bumps | NP | avg_p | elev |",
        "|---|---|---:|---:|---|---|---:|---:|---:|",
    ]
    for aid in ALPS_IDS:
        ent = all_scored.get(aid)
        if not ent:
            # not scored at all
            row = bike[bike["activity_id"] == aid]
            if row.empty:
                lines.append(f"| {aid} | — | — | — | no | **NOT IN CSV** | — | — | — |")
            else:
                r = row.iloc[0]
                lines.append(
                    f"| {aid} | {str(r['date'])[:10]} | 0 | unscored | no | (no bumps fired) | "
                    f"{_num(r.get('normalized_power'))} | {_num(r.get('avg_power'))} | "
                    f"{_num(r.get('elevation_gain_m'))} |"
                )
            continue
        bumps = ", ".join(f"{b['reason']}(+{b['pts']})" for b in ent["bumps"])
        in35 = "yes" if ent["rank"] <= 35 else "no"
        lines.append(
            f"| {aid} | {ent.get('date')} | {ent['score']} | {ent['rank']} | {in35} | "
            f"{bumps} | {ent.get('np')} | {ent.get('avg_power')} | {ent.get('elevation_gain_m')} |"
        )

    lines += [
        "",
        "## Top 10 v1 shortlist (for contrast)",
        "",
        "| Rank | ID | Date | Score | Reasons |",
        "|---:|---|---|---:|---|",
    ]
    for r in top35[:10]:
        lines.append(
            f"| {r['rank']} | {r['activity_id']} | {r.get('date')} | {r['score']} | "
            f"{', '.join(r['reasons'])} |"
        )

    lines += [
        "",
        "## CSV NP / TSS null rates by year (cycling)",
        "",
        "| Year | n | NP null % | TSS null % | avg_power null % |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in np_tss_null_rates(bike):
        lines.append(
            f"| {r['year']} | {r['n_cycling']} | {r['np_null_pct']} | "
            f"{r['tss_null_pct']} | {r['avg_power_null_pct']} |"
        )
    lines.append("")
    DIAG_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {DIAG_PATH}", flush=True)


def _est_kj(row) -> Optional[float]:
    dur = _num(row.get("duration_s"))
    if not dur:
        return None
    p = _num(row.get("normalized_power")) or _num(row.get("avg_power"))
    if p is None:
        return None
    return p * dur / 1000.0


def build_shortlist_v2(bike, gaps: list[dict]) -> list[dict]:
    """Multi-criteria union with per-year coverage guarantees."""
    import pandas as pd

    selected: dict[int, dict] = {}

    def add(row, reason: str):
        aid = row.get("activity_id")
        if aid is None or (isinstance(aid, float) and math.isnan(aid)):
            return
        key = int(aid)
        d = row["date"]
        date_s = d.date().isoformat() if hasattr(d, "date") else str(d)[:10]
        year = int(date_s[:4])
        ent = selected.setdefault(key, {
            "activity_id": key,
            "date": date_s,
            "year": year,
            "reasons": [],
            "np": _num(row.get("normalized_power")),
            "avg_power": _num(row.get("avg_power")),
            "duration_s": _num(row.get("duration_s")),
            "elevation_gain_m": _num(row.get("elevation_gain_m")),
            "tss": _num(row.get("tss")),
            "avg_hr": _num(row.get("avg_hr")),
            "avg_speed_ms": _num(row.get("avg_speed_ms")),
            "est_kj": _est_kj(row),
        })
        if reason not in ent["reasons"]:
            ent["reasons"].append(reason)

    years = sorted(bike["date"].dt.year.unique())

    def year_slice(y):
        return bike[bike["date"].dt.year == y]

    for y in years:
        g = year_slice(int(y))
        if g.empty:
            continue
        # NP top 5/year
        for _, row in g[g["normalized_power"].notna()].nlargest(5, "normalized_power").iterrows():
            add(row, f"np_top5_{y}")
        # Avg power top 5/year
        for _, row in g[g["avg_power"].notna()].nlargest(5, "avg_power").iterrows():
            add(row, f"avg_power_top5_{y}")
        # TSS top 5/year
        if "tss" in g.columns:
            for _, row in g[g["tss"].notna()].nlargest(5, "tss").iterrows():
                add(row, f"tss_top5_{y}")
        # Duration top 3/year (hard guarantee)
        for _, row in g.nlargest(3, "duration_s").iterrows():
            add(row, f"duration_top3_{y}")
        # Elevation top 5/year
        for _, row in g[g["elevation_gain_m"].notna()].nlargest(5, "elevation_gain_m").iterrows():
            add(row, f"elev_top5_{y}")
        # Est kJ top 5/year
        tmp = g.copy()
        tmp["_kj"] = pd.to_numeric(tmp.apply(_est_kj, axis=1), errors="coerce")
        for _, row in tmp[tmp["_kj"].notna()].nlargest(5, "_kj").iterrows():
            add(row, f"kj_top5_{y}")
        # High avg HR ≥20 min top 3/year
        hr = g[(g["avg_hr"].notna()) & (g["duration_s"] >= 20 * 60)]
        for _, row in hr.nlargest(3, "avg_hr").iterrows():
            add(row, f"hr_top3_{y}")
        # Flat speed proxy when power scarce
        powerish = g["normalized_power"].notna().sum() + g["avg_power"].notna().sum()
        if powerish < max(3, len(g) // 4):
            flat = g[
                (g["duration_s"] >= 3600)
                & g["avg_speed_ms"].notna()
                & (g["elevation_gain_m"].isna() | (g["elevation_gain_m"] < 300))
            ]
            for _, row in flat.nlargest(5, "avg_speed_ms").iterrows():
                add(row, f"flat_speed_top5_{y}")
        # NP top-3 guarantee (or avg_power if all NP null)
        np_ok = g[g["normalized_power"].notna()]
        if not np_ok.empty:
            for _, row in np_ok.nlargest(3, "normalized_power").iterrows():
                add(row, f"np_guarantee_top3_{y}")
        else:
            for _, row in g[g["avg_power"].notna()].nlargest(3, "avg_power").iterrows():
                add(row, f"avg_power_guarantee_top3_{y}")

    # Global tops
    for _, row in bike[bike["normalized_power"].notna()].nlargest(20, "normalized_power").iterrows():
        add(row, "np_global_top20")
    for _, row in bike.nlargest(25, "duration_s").iterrows():
        add(row, "duration_global_top25")
    for _, row in bike[bike["avg_power"].notna()].nlargest(20, "avg_power").iterrows():
        add(row, "avg_power_global_top20")
    tmp = bike.copy()
    tmp["_kj"] = pd.to_numeric(tmp.apply(_est_kj, axis=1), errors="coerce")
    for _, row in tmp[tmp["_kj"].notna()].nlargest(20, "_kj").iterrows():
        add(row, "kj_global_top20")

    # Post-layoff first 3
    major = [g for g in gaps if g["length_days"] >= 42]
    for g in major:
        restart = date.fromisoformat(g["end"])
        after = bike[bike["date"].dt.date >= restart].head(3)
        for _, row in after.iterrows():
            add(row, f"post_layoff3_{g['start']}")

    # Force-include known Alps IDs if in CSV
    id_map = {}
    for _, row in bike.iterrows():
        try:
            id_map[int(float(row["activity_id"]))] = row
        except Exception:
            continue
    for aid in ALPS_IDS:
        if aid in id_map:
            add(id_map[aid], "force_alps_hr2012")

    # Coverage guarantees — expand if year has ≥8 rides but <8 selected
    by_year_sel: dict[int, list[int]] = defaultdict(list)
    for ent in selected.values():
        by_year_sel[ent["year"]].append(ent["activity_id"])

    for y in years:
        y = int(y)
        g = year_slice(y)
        n_exist = len(g)
        if n_exist < 8:
            continue
        have = set(by_year_sel.get(y, []))
        if len(have) >= 8:
            continue
        # Fill with next-longest not yet selected
        for _, row in g.nlargest(n_exist, "duration_s").iterrows():
            aid = int(row["activity_id"])
            if aid in have:
                continue
            add(row, f"coverage_fill8_{y}")
            have.add(aid)
            if len(have) >= 8:
                break

    # Validate guarantees
    errors = []
    for y in years:
        y = int(y)
        g = year_slice(y)
        if g.empty:
            continue
        have_ids = {e["activity_id"] for e in selected.values() if e["year"] == y}
        if len(g) >= 8 and len(have_ids) < 8:
            errors.append(f"year {y}: need ≥8 selected, have {len(have_ids)}")
        top3_dur = set(int(x) for x in g.nlargest(3, "duration_s")["activity_id"])
        if not top3_dur.issubset(have_ids):
            errors.append(f"year {y}: missing duration top-3 {top3_dur - have_ids}")
        np_ok = g[g["normalized_power"].notna()]
        if not np_ok.empty:
            top3_np = set(int(x) for x in np_ok.nlargest(3, "normalized_power")["activity_id"])
            if not top3_np.issubset(have_ids):
                errors.append(f"year {y}: missing NP top-3 {top3_np - have_ids}")
        else:
            ap = g[g["avg_power"].notna()]
            if not ap.empty:
                top3_ap = set(int(x) for x in ap.nlargest(3, "avg_power")["activity_id"])
                if not top3_ap.issubset(have_ids):
                    errors.append(f"year {y}: missing avg_power top-3 {top3_ap - have_ids}")

    if errors:
        raise RuntimeError("shortlist_v2 coverage failed:\n  " + "\n  ".join(errors))

    rows = list(selected.values())
    for r in rows:
        r["reason"] = "|".join(r.pop("reasons"))
    rows.sort(key=lambda x: (x["year"], x["date"], x["activity_id"]))

    # Soft target size hint
    if len(rows) < 80:
        print(f"Warn: shortlist_v2 only {len(rows)} IDs (wanted ~100–150)", flush=True)
    if len(rows) > 200:
        print(f"Warn: shortlist_v2 large ({len(rows)}); proceeding", flush=True)

    return rows


def write_shortlist_v2(rows: list[dict]) -> None:
    cols = [
        "activity_id", "date", "year", "reason",
        "np", "avg_power", "duration_s", "elevation_gain_m", "tss", "est_kj", "avg_hr",
    ]
    with SHORTLIST_V2.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"Wrote {SHORTLIST_V2} ({len(rows)} activities)", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", type=Path, default=ACTIVITIES_CSV)
    args = p.parse_args()
    if not args.csv.is_file():
        sys.exit(f"Missing {args.csv}")
    _, bike, gaps = load_bike(args.csv)
    write_diagnosis(bike, gaps)
    rows = build_shortlist_v2(bike, gaps)
    write_shortlist_v2(rows)
    # Confirm Alps present
    ids = {r["activity_id"] for r in rows}
    for aid in ALPS_IDS:
        print(f"  Alps {aid}: {'IN' if aid in ids else 'MISSING'}", flush=True)


if __name__ == "__main__":
    main()

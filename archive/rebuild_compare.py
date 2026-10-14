#!/usr/bin/env python3
"""Compare first-21-day restart patterns for recovered vs plateaued_lower layoffs."""
from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

ARCHIVE_DIR = Path(__file__).resolve().parent
ACTIVITIES_CSV = ARCHIVE_DIR / "activities_2009_2016.csv"
FINDINGS_PATH = ARCHIVE_DIR / "findings.json"
MMP_CSV = ARCHIVE_DIR / "activity_mmp.csv"
OUT_PATH = ARCHIVE_DIR / "rebuild_failures.md"


def _parse_date(s: str) -> Optional[date]:
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def _f(v) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def load_activities() -> list[dict]:
    rows = []
    with ACTIVITIES_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            sport = (r.get("sport") or "").lower()
            if "cycl" not in sport and "bik" not in sport:
                continue
            d = _parse_date(r.get("date") or "")
            if not d:
                continue
            rows.append({
                "activity_id": int(float(r["activity_id"])),
                "date": d,
                "duration_s": _f(r.get("duration_s") or r.get("duration")),
                "avg_hr": _f(r.get("avg_hr")),
                "avg_power": _f(r.get("avg_power")),
                "np": _f(r.get("normalized_power")),
                "tss": _f(r.get("tss")),
                "training_load": _f(r.get("training_load") or r.get("tss")),
            })
    rows.sort(key=lambda x: x["date"])
    return rows


def load_mmp() -> dict[int, dict]:
    out = {}
    if not MMP_CSV.is_file():
        return out
    with MMP_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                aid = int(float(r["activity_id"]))
            except Exception:
                continue
            out[aid] = r
    return out


def first_21_features(
    bike: list[dict],
    restart: date,
    layoff_days: int,
    mmp: dict[int, dict],
) -> dict[str, Any]:
    end21 = restart + timedelta(days=20)
    end14 = restart + timedelta(days=13)
    window8w = restart + timedelta(days=56)
    rides21 = [r for r in bike if restart <= r["date"] <= end21]
    rides14 = [r for r in bike if restart <= r["date"] <= end14]

    def week_bucket(d: date) -> int:
        return min(2, (d - restart).days // 7)

    weeks: dict[int, list[dict]] = defaultdict(list)
    for r in rides21:
        weeks[week_bucket(r["date"])].append(r)

    def week_hours(ws: list[dict]) -> float:
        return sum((x["duration_s"] or 0) for x in ws) / 3600.0

    def week_load(ws: list[dict]) -> float:
        return sum(
            (x["tss"] or x["training_load"] or 0)
            or ((x["avg_power"] or 0) * (x["duration_s"] or 0) / 1000.0)
            for x in ws
        )

    h = [week_hours(weeks[i]) for i in range(3)]
    load = [week_load(weeks[i]) for i in range(3)]

    wow12 = (h[1] / h[0] - 1.0) if h[0] > 0 else None
    wow23 = (h[2] / h[1] - 1.0) if h[1] > 0 else None

    hrs = [r["avg_hr"] for r in rides21 if r["avg_hr"]]
    nps = [r["np"] or r["avg_power"] for r in rides21 if (r["np"] or r["avg_power"])]
    med_hr = statistics.median(hrs) if hrs else None
    med_np = statistics.median(nps) if nps else None
    above = 0
    denom = 0
    for r in rides21:
        hit = False
        used = False
        if med_hr is not None and r["avg_hr"] is not None:
            used = True
            if r["avg_hr"] > med_hr:
                hit = True
        if med_np is not None and (r["np"] or r["avg_power"]):
            used = True
            if (r["np"] or r["avg_power"] or 0) > med_np:
                hit = True
        if used:
            denom += 1
            if hit:
                above += 1
    intensity_share = (above / denom) if denom else None

    longest14 = max((r["duration_s"] or 0) for r in rides14) / 3600.0 if rides14 else 0.0

    # EF = NP/HR when both present — weekly means week1 vs week3
    def week_ef(ws: list[dict]) -> Optional[float]:
        vals = []
        for r in ws:
            p = r["np"] or r["avg_power"]
            if p and r["avg_hr"] and r["avg_hr"] > 0:
                vals.append(p / r["avg_hr"])
            elif r["activity_id"] in mmp:
                m = mmp[r["activity_id"]]
                # no HR in mmp csv — skip
                _ = m
        return statistics.mean(vals) if vals else None

    ef1, ef3 = week_ef(weeks[0]), week_ef(weeks[2])
    ef_trend = (ef3 - ef1) if (ef1 is not None and ef3 is not None) else None

    # Further ≥10-day cycling gap within 8 weeks of restart
    further_gap = False
    post = [r for r in bike if restart <= r["date"] <= window8w]
    for i in range(len(post) - 1):
        gap = (post[i + 1]["date"] - post[i]["date"]).days - 1
        if gap >= 10:
            further_gap = True
            break
    if post and (window8w - post[-1]["date"]).days >= 10:
        further_gap = True

    return {
        "restart_date": restart.isoformat(),
        "layoff_days": layoff_days,
        "restart_month": restart.month,
        "week1_h": round(h[0], 2),
        "week2_h": round(h[1], 2),
        "week3_h": round(h[2], 2),
        "week1_load": round(load[0], 1),
        "week2_load": round(load[1], 1),
        "week3_load": round(load[2], 1),
        "wow_w1_w2": round(wow12, 2) if wow12 is not None else None,
        "wow_w2_w3": round(wow23, 2) if wow23 is not None else None,
        "rides_14d": len(rides14),
        "rides_21d": len(rides21),
        "intensity_share": round(intensity_share, 2) if intensity_share is not None else None,
        "longest_ride_14d_h": round(longest14, 2),
        "ef_trend_w1_w3": round(ef_trend, 4) if ef_trend is not None else None,
        "further_ge10d_gap_in_8w": further_gap,
    }


def group_medians(rows: list[dict], key: str) -> Optional[float]:
    vals = [r[key] for r in rows if r.get(key) is not None]
    if not vals:
        return None
    return statistics.median(vals)


def overlaps(a: list[float], b: list[float]) -> bool:
    if not a or not b:
        return True
    return not (max(a) < min(b) or max(b) < min(a))


def run() -> str:
    findings = json.loads(FINDINGS_PATH.read_text(encoding="utf-8"))
    layoffs = (findings.get("rebuild_fit") or findings.get("rebuild") or {}).get("layoffs") or []
    if not layoffs:
        layoffs = (findings.get("rebuild") or {}).get("layoffs") or []

    bike = load_activities()
    mmp = load_mmp()

    recovered, failed = [], []
    for lo in layoffs:
        rd = _parse_date(lo.get("restart_date") or "")
        if not rd:
            continue
        feat = first_21_features(
            bike,
            rd,
            int(
                lo.get("layoff_days")
                or lo.get("length_days")
                or (round(float(lo["layoff_weeks"]) * 7) if lo.get("layoff_weeks") is not None else 0)
            ),
            mmp,
        )
        feat["status"] = lo.get("status")
        feat["weeks_to_recover"] = lo.get("weeks_to_recover")
        if lo.get("status") == "plateaued_lower":
            failed.append(feat)
        elif lo.get("status") == "recovered":
            recovered.append(feat)

    metrics = [
        "layoff_days", "restart_month", "rides_14d", "rides_21d",
        "week1_h", "week2_h", "week3_h", "wow_w1_w2", "wow_w2_w3",
        "intensity_share", "longest_ride_14d_h", "ef_trend_w1_w3",
    ]

    lines = [
        "# Rebuild failure comparison (first 21 days)",
        "",
        f"_Generated {datetime.now().isoformat(timespec='seconds')}_",
        "",
        f"n_recovered={len(recovered)}, n_failed (plateaued_lower)={len(failed)}.",
        "Source: major layoffs in `findings.rebuild_fit.layoffs` (fallback `rebuild`).",
        "",
        "## Per-restart features",
        "",
        "| restart | status | layoff_d | month | rides_14d | w1_h | w2_h | w3_h | "
        "wow1→2 | longest_14d_h | intensity | further_gap |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for feat in failed + recovered:
        lines.append(
            f"| {feat['restart_date']} | {feat['status']} | {feat['layoff_days']} | "
            f"{feat['restart_month']} | {feat['rides_14d']} | {feat['week1_h']} | "
            f"{feat['week2_h']} | {feat['week3_h']} | {feat['wow_w1_w2']} | "
            f"{feat['longest_ride_14d_h']} | {feat['intensity_share']} | "
            f"{feat['further_ge10d_gap_in_8w']} |"
        )

    lines += ["", "## Group medians", "", "| metric | recovered median | failed median |", "|---|---:|---:|"]
    separators: list[str] = []
    for m in metrics:
        rm = group_medians(recovered, m)
        fm = group_medians(failed, m)
        lines.append(
            f"| {m} | {rm if rm is not None else '—'} | {fm if fm is not None else '—'} |"
        )
        rv = [r[m] for r in recovered if r.get(m) is not None]
        fv = [r[m] for r in failed if r.get(m) is not None]
        if rv and fv and not overlaps(rv, fv):
            separators.append(
                f"`{m}`: recovered {sorted(rv)} vs failed {sorted(fv)} (ranges do not overlap)"
            )

    # Binary: further gap rate
    if recovered and failed:
        rg = sum(1 for r in recovered if r["further_ge10d_gap_in_8w"]) / len(recovered)
        fg = sum(1 for r in failed if r["further_ge10d_gap_in_8w"]) / len(failed)
        lines.append(f"| further_ge10d_gap_rate | {rg:.2f} | {fg:.2f} |")

    lines += ["", "## Verdict", ""]
    n_fail = len(failed)
    if n_fail == 0:
        lines.append("No plateaued_lower restarts to compare.")
    elif separators:
        lines.append(
            f"At n_failed={n_fail}, the following metric(s) cleanly separate groups:"
        )
        for s in separators:
            lines.append(f"- {s}")
        # Concrete autumn rule only if rides_14d separates and all failed are low
        if any(s.startswith("`rides_14d`") for s in separators):
            max_fail = max(r["rides_14d"] for r in failed)
            lines.append(
                f"**Autumn rule (data-backed at this n):** treat a restart with "
                f"<{max_fail + 1} cycling rides in the first 14 days as higher risk of plateau."
            )
    else:
        lines.append(
            f"**Null result at n_failed={n_fail}.** No metric cleanly separates "
            f"`plateaued_lower` from `recovered` (medians/ranges overlap on all compared "
            f"features: ramp, ride count, intensity share, longest ride, EF trend, "
            f"layoff length, restart month, further ≥10-day gap). Do not invent a "
            f"causal pattern from three failures."
        )

    lines += [
        "",
        "## Notes",
        "",
        "- Intensity share = fraction of first-21-day rides above that restart's own "
        "median avg_hr or NP/avg_power.",
        "- Weekly load uses Garmin TSS/training_load when present, else est_kJ = avg_power×duration_s/1000.",
        "- EF trend requires NP+HR (or avg_power+HR); often sparse in Edge-era CSV rows.",
        "",
    ]
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_PATH}", flush=True)
    return "\n".join(lines)


if __name__ == "__main__":
    run()

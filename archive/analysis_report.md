# Garmin history analysis (2009–2016) — authoritative

_Generated 2026-08-07T23:06:12_

This file is the **single** report. Prior Stage-2 body + Stage-3 addendum split is retired.
Superseded dual narratives live under coach UI collapsibles and `archive/superseded/` snapshots.

## Rebuild-rate verdict

**Central estimate: 5.0 weeks** (FIT/stream-grounded on shortlist_v2; IQR 3–14; 12 recovered, 3 plateaued).

Summary-only estimate is also **5.0 weeks**. The earlier FIT-only **7.5 weeks** came from the sparse v1 shortlist FIT map (see `reversal_audit.md`) — overturned.

Proxy ladder: FIT MMP-20 → max_power_20min → NP (≥45 min) → avg power (≥60 min) → EF (NP/HR) → speed/HR. FIT-grounded baselines: 8/15; FIT restarts (first 14d): 9/15.

## True MMP (MEASURED_MMP)

True mean-maximal power (MEASURED_MMP) from FIT/TCX streams (1 Hz resampled; gaps >3s excluded). shortlist_v2 — not exhaustive. Device FTP values are DEVICE_SETTING, not measurements.

n_with_power=101; source=`shortlist_v2_fits_and_streams`.

| Year | 1 min | 2 min | 5 min | 20 min | 60 min | 5:60 | 20:60 | flag |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2010 | 392.7 | 321.7 | 265.4 | 222.3 | 187.7 | 1.414 | 1.184 | FAIL |
| 2011 | 435.4 | 386.0 | 287.3 | 210.3 | 179.0 | 1.605 | 1.175 | FAIL |
| 2012 | 422.0 | 352.1 | 310.4 | 281.7 | 267.1 | 1.162 | 1.055 | ok |
| 2013 | 491.9 | 349.1 | 317.7 | 302.3 | 296.3 | 1.072 | 1.02 | FAIL |
| 2014 | 389.1 | 343.4 | 312.0 | 273.8 | 258.6 | 1.206 | 1.059 | ok |
| 2015 | 433.3 | 356.7 | 329.9 | 303.7 | 271.5 | 1.215 | 1.119 | ok |
| 2016 | 268.1 | 255.6 | 246.4 | 213.9 | 172.5 | 1.428 | 1.24 | FAIL |
| 2026 | 346.7 | 282.6 | 252.6 | 222.6 | 186.1 | 1.863 | 1.196 | FAIL |

2026 row: **MEASURED_MMP** from wall-clock engine on 12-week block powered FITs (not a full-year shortlist).
Headline outdoor FTP test `23884317052` MMP-20 = **222.6 W**; app FTP **220 W** is `20-min×0.95` (DEVICE/app) — **not** comparable to this column.
See `block_2026_analysis.md` / `mmp_by_year_with_2026.csv`. Ratio band FAIL expected (short power-meter window + spike-guard rejections on several long rides).

Provenance: stream peaks are **MEASURED_MMP**. Device FTP values are **DEVICE_SETTING**.
Day 4 Haute Route `277575228` MMP-60 = **252.7 W MEASURED_MMP** (known-good 253 W).
See `mmp_validation.md` for zero-handling, Smart Recording, and cross-checks.

## Device FTP (DEVICE_SETTING) vs MEASURED MMP-60

| Year | Device FTP (latest seen) | MMP-60 MEASURED | Gap (setting − MMP60) | Setting as % of MMP60 |
|---:|---:|---:|---:|---:|
| 2010 | — | 187.7 | — | —% |
| 2011 | — | 179.0 | — | —% |
| 2012 | — | 267.1 | — | —% |
| 2013 | — | 296.3 | — | —% |
| 2014 | 200.0 | 258.6 | -58.6 | 77.3% |
| 2015 | 260.0 | 271.5 | -11.5 | 95.8% |
| 2016 | 230.0 | 172.5 | 57.5 | 133.3% |

If device FTP sits **below** measured hour power, zones were systematically soft that season
(e.g. training “threshold” easier than true sustainable power). Where the device FTP column is
empty, no FIT `threshold_power`/zones field was recovered for that year on the shortlist.

## Stated peaks (provenance-tagged)

- 2012: stated 253W **MEASURED_MMP** vs archive 267.1W MEASURED_MMP — conflicts=False — Stated 253W (MEASURED_MMP) vs shortlist mmp_60min 267.1W MEASURED_MMP
- 2012: stated 242W **DEVICE_SETTING** vs archive NoneW None — conflicts=False — 242W is a DEVICE_SETTING — not a measured fitness datum. Do not treat gaps vs proxies/MMP as measurement contradictions. Year MMP-60=267.1 MEASURED_MMP.
- 2015: stated 282W **MODELLED** vs archive 329.9W MEASURED_MMP — conflicts=False — Stated 282W (MODELLED) vs shortlist mmp_5min 329.9W MEASURED_MMP
- 2016: stated 260W **DEVICE_SETTING** vs archive NoneW None — conflicts=False — 260W is a DEVICE_SETTING — not a measured fitness datum. Do not treat gaps vs proxies/MMP as measurement contradictions. Year MMP-60=172.5 MEASURED_MMP.

## Coupled weight / power (0 / 3 / 6 W lost per kg)

Do **not** assume watts stay constant while weight falls.

| W lost / kg | Power after −12 kg | Weight | W/kg |
|---:|---:|---:|---:|
| 0.0 | 220.0 | 80.0 | 2.75 |
| 3.0 | 184.0 | 80.0 | 2.3 |
| 6.0 | 148.0 | 80.0 | 1.85 |

Archive-era weight overlap: No overlapping weight history between body_metrics and archive MMP years (2009–2016). body_db span is 2026-03-30→2026-08-06..
Sequence: consistency first → modest deficit → MMP-20 guardrail.

## Failed rebuilds (n_failed=3)

See `rebuild_failures.md`. **Null result** at n=3 — no metric cleanly separates
`plateaued_lower` from recovered restarts. Do not invent an autumn rule from three points.

## Coach narratives (UI)

Opus narratives are served on `/archive` collapsibles (`ai_narrative`, `ai_narrative_mmp`).
**Normative numbers are the tables above**, plus `mmp_validation.md` / `reversal_audit.md`.
If a narrative sentence conflicts with MEASURED_MMP / DEVICE_SETTING tables, the tables win.

## Related artefacts

- `mmp_validation.md` — Issue 1 checks
- `reversal_audit.md` — 5.0 vs 7.5
- `rebuild_failures.md` — failed vs recovered first-21d
- `CHANGELOG.md` — overturned conclusions this run

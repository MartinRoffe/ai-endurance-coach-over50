# 2026 12-week block vs 2009–2016 archive

_Generated 2026-08-07T23:27:03_

Uses **validated `mmp_engine.py`** (wall-clock 1 Hz; zeros as zero; gaps >8 s → 0; spikes >1800 W rejected).
Consistency helpers: `longest_streak_ge3`, `find_cycling_gaps`, `peak_blocks` from `garmin_analysis.py`.

---

## FTP test provenance (read before any power comparison)

| Field | Value |
|---|---|
| Activity | `23884317052` — Southend-on-Sea - Final FTP Test |
| Date | **2026-08-07** |
| Setting | **Outdoor (road_biking, Southend-on-Sea)** |
| Protocol | **20-min effort × 0.95** |
| Multiplier | **×0.95** |
| Recorded FTP (DEVICE / app) | **220 W** |
| Analysed 20-min effort avg | **232.0 W** |
| **Raw MMP-20 (MEASURED_MMP, stream)** | **222.6 W** |
| MMP-60 same ride | n/a (ride <60 min wall-clock) |
| Weight near test | **89.9 kg** |
| MMP-20 W/kg | **2.48** |

**Do not compare 220 W FTP to archive MMP-20.** The like-for-like number is raw MMP-20 = **222.6 W** (provenance `MEASURED_MMP`).

Indoor/outdoor confound: **none for this test** — outdoor road ride (matches archive bests). Assioma vs 2012-era meter calibration still applies.

---

## Analysis 1 — Consistency (definition-independent)

Cycling-only, same rules as the archive (≥3 rides/week streak).

- Plan window: **2026-05-18 → 2026-08-09** (data through 2026-08-07)
- Weeks with ≥3 rides: **5** / 12
- Longest unbroken ≥3-rides streak: **3 weeks** (2026-07-14 → 2026-07-28) — same `W-MON` week key as the archive 8-week record (can diverge from Mon–Sun plan rows below)
- Archive record: **8 weeks** (2012-04-10 → 2012-05-29)
- **Did this block beat the archive streak?** **NO** — 3 vs 8.
- Gaps ≥10 days inside the block: none
- Total cycling hours: **43.8 h** (3.78 h/wk over 11.57 weeks)
- Rides: **26** (2.25/wk); median duration **76.8 min**

### Per-week vs archive top-5 (6-week scored blocks)

Archive `peak_blocks` score rolling **6-week** windows. The 2026 plan is 12 weeks — compare hours/week, and also the best 6-week sub-window inside 2026.

| Block | Span wk | Hours | h/wk | rides/wk | median min |
|---|---:|---:|---:|---:|---:|
| 2009-06-23 → 2009-08-24 | 6.0 | 59.4 | 9.9 | 2.7 | 139.0 |
| 2009-06-16 → 2009-07-27 | 6.0 | 57.1 | 9.52 | 2.5 | 141.0 |
| 2009-02-10 → 2009-05-04 | 6.0 | 55.9 | 9.32 | 3.7 | 144.0 |
| 2012-07-17 → 2012-08-27 | 6.0 | 54.7 | 9.12 | 3.2 | 149.0 |
| 2009-06-09 → 2009-07-20 | 6.0 | 54.5 | 9.08 | 2.3 | 141.0 |
| **2026 best 6-wk** (2026-06-30→2026-08-10) | 6 | 26.4 | 4.4 | 2.2 | 85.0 |
| **2026 full 12-wk** | 11.57 | 43.8 | 3.78 | 2.25 | 76.8 |

**Largest single training block in the dataset (by hours in a 6-wk window)?** **NO — archive #1 remains 59.4 h (6-wk); 2026 best 6-wk is 26.4 h. Full 12-wk total (43.8 h) is a longer block, not a denser one.**

Note: full 12-week total hours can exceed any 6-week archive block while still losing on h/wk density and ≥3-ride streak. Consistency is the stronger signal here.

### Weekly detail (2026)

| Week | Rides | Hours | ≥3? |
|---|---:|---:|---|
| 2026-05-18 | 2 | 2.22 | no |
| 2026-05-25 | 2 | 3.3 | no |
| 2026-06-01 | 3 | 4.23 | yes |
| 2026-06-08 | 1 | 1.06 | no |
| 2026-06-15 | 3 | 4.16 | yes |
| 2026-06-22 | 2 | 2.4 | no |
| 2026-06-29 | 2 | 5.49 | no |
| 2026-07-06 | 1 | 1.22 | no |
| 2026-07-13 | 3 | 6.14 | yes |
| 2026-07-20 | 3 | 4.45 | yes |
| 2026-07-27 | 2 | 7.18 | no |
| 2026-08-03 | 2 | 1.92 | no |

---

## Analysis 2 — Response (EF, % max HR)

Archive HRmax used: **204.0**. 2026 HRmax = highest HR observed in block: **188.0**.
Metric: median weekly **EF = NP ÷ (% of HRmax)** on rides ≥45 min with NP+HR.
Power meter only from late June — EF series starts then, not week 1.

### 2026 (all NP rides)

- Slope: **0.03894** /wk (Δ 0.4361, 21.8%)
- Shape: **still_climbing**; still climbing at end: **True**

### 2026 excluding FTP-labelled rides (preferred for adaptation)

- Slope: **0.00572** /wk (Δ -0.0707, -3.53%)
- Shape: **mid_peak_then_fade**; still climbing at end: **False**
- Front-half mean: 2.0309; back-half: 2.1148

### Vs top historical blocks — **not a valid comparison**

The archive top-5 hours blocks (mostly 2009 / 2012) have **zero `normalized_power`** in the Garmin export. Computing EF for them would invent numbers. **No EF slope is reported against those blocks.**

Secondary context only — densest NP-covered archive strip (not a top hours block):

| Block | HRmax | Slope /wk | Δ EF | Shape | Still climbing? |
|---|---:|---:|---:|---|---|
| 2026 ex-FTP | 188.0 | 0.00572 | -0.0707 | mid_peak_then_fade | False |
| 2015-05-18→2015-06-01 (NP-available only; NOT a top hours block) | 204.0 | 0.00025 | 0.0005 | back_loaded | False |

**Finding (ex-FTP):** EF **peaked mid-block** (quality weeks ~Jul 14) then faded; the final non-test week was below the powered-window open. Do not read this as 'adaptation still climbing at week 12'. **EF vs archive top-5 hours blocks is not valid** — those blocks have zero NP in the export. Secondary 2015 NP strip is shown only for context.

Chart: `charts/ef_trend_2026_vs_blocks.png` (2026 ex-FTP vs 2015 NP strip)

---

## Analysis 3 — Honest power positioning (MEASURED_MMP)

All rows: **MEASURED_MMP** from the same wall-clock engine. 2026 year row = best across powered rides in the 12-week block (n=15). Several long rides had raw MMP windows rejected by the engine’s peak/mean spike guard (same rule as archive) — those rides contribute shorter-duration peaks only when the guard passes.

| Year | MMP-20 | MMP-60 | Weight kg | MMP-20 W/kg | MMP-60 W/kg | Notes |
|---:|---:|---:|---:|---:|---:|---|
| 2011 | 210.3 | 179.0 | — | — | — | MEASURED_MMP shortlist; ratio band FAIL (coverage caveat) |
| 2012 | 281.7 | 267.1 | 78.0 | 3.61 | 3.42 | MEASURED_MMP shortlist; Alps Day4 MMP-60≈253 lore confirmed on stream |
| 2013 | 302.3 | 296.3 | — | — | — | MEASURED_MMP shortlist; ratio band FAIL (coverage caveat) |
| 2014 | 273.8 | 258.6 | — | — | — | MEASURED_MMP shortlist |
| 2015 | 303.7 | 271.5 | 84.4 | 3.6 | 3.22 | MEASURED_MMP shortlist |
| 2016 | 213.9 | 172.5 | 82.0 | 2.61 | 2.1 | MEASURED_MMP shortlist; ratio band FAIL (coverage caveat) |
| 2026 | 222.6 | 186.1 | 89.9 | 2.48 | 2.07 | MEASURED_MMP block bests; FTP test MMP-20=222.6 outdoor; FTP 220=effort×0.95 (not in this table) |

### Confounds (stated, not adjusted away)

- 13 years older (archive peak years ~35–39; now 50).
- ~11.9 kg heavier than 2012 Alps weight (78 kg); 2026 test weight 89.9 kg (prior framing sometimes used 92 kg).
- Different power meters — 2012-era unit had known climbing-physics discrepancy; 2026 Favero Assioma almost certainly more accurate. Part of any watt gap is measurement.
- FTP test indoor/outdoor: outdoor — no turbo confound for the headline MMP-20.
- 2026 MMP year curve is from ~6 weeks of powered riding (meter from late June), not a full season shortlist like archive years.
- Powered early-block weeks (May–mid June) missing from MMP — understates block capacity if unpowered hard days existed.

### Full MMP curve — FTP test ride vs block bests

| Duration | FTP test ride | Block best (any ride) | Best activity |
|---|---:|---:|---|
| 1 min | 301.7 | 346.7 | 23651173277 |
| 2 min | 282.6 | 282.6 | 23884317052 |
| 5 min | 252.6 | 252.6 | 23884317052 |
| 20 min | 222.6 | 222.6 | 23884317052 |
| 60 min | None | 186.1 | 23687360572 |

---

## Analysis 4 — Forward projection

Observed MMP-20: FTP re-test ride `23455664973` → **208.1 W**; final test → **222.6 W** over ~5.1 weeks.

Naive linear continuation of that Δ: **~2.82 W/week** → MMP-20 ≈ **296 W** at +6 months, **369 W** at +12 months.

**Do not believe the linear numbers.** Early/mid-block gains decelerate; FTP and MMP curves flatten. Treat the projection as an upper-bound illustration only.

Archive rebuild central estimate: **~5 weeks** to recover after a typical layoff (longer when off >10 weeks); three autumn layoffs never recovered.

Next 12 weeks to keep response going: protect the **≥3 rides/week streak**, one quality day + one long ride weekly, maintain outdoor MMP sampling monthly, avoid Nov–Jan zero; if travel forces a cut, cap layoff at ≤3 weeks then rebuild deliberately.

EF still climbing at week 12 supports continuing the dose rather than an immediate deload into inactivity.

---

## Analysis 5 — Autumn layoff risk

Archive pattern: every year shows a **6–12 week layoff** clustered Nov–Jan (Nov 2009, Nov 2010, Oct 2011, Nov 2012, Nov 2013, Nov 2014). Three never recovered.

From the current position, a typical autumn gap of **8 weeks off** plus **~5 weeks rebuild** is **≈13 weeks of lost progress** before matching today's fitness proxy again — and that assumes a *successful* rebuild, which failed in 3/15 major layoffs.

Concrete: if you stop now at MMP-20 ≈ **223 W**, after 8 weeks off you are not at 223 W — you restart below it. After ~5 rebuild weeks you *might* revisit ~223 W (archive median recoverers). Linear +52-week fantasy (369 W) is forfeited; realistic return point is **near current MMP-20, not ahead of it**.

Cost of an autumn layoff from here: **~13 weeks of calendar (8+5)** and **zero expected net MMP-20 gain** across that span — progress clock resets.

---

## Artefacts

- `charts/training_hours_2009_2026.png`
- `charts/ef_trend_2026_vs_blocks.png`
- `activity_mmp_2026.csv` — per-ride MEASURED_MMP for the block
- `mmp_by_year_with_2026.csv` — year table with 2026 appended
- `block_2026_findings.json` — machine-readable payload


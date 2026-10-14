# CHANGELOG — archive analysis (third pass)

_Generated 2026-08-07 (third pass)_

Every overturned conclusion since the prior published run, with reason. Do not soften.

## 1. MMP engine (zeros / wall-clock) — prior annual curves partly invalid

**Prior:** MMP computed on contiguous non-`None` segments after 1 Hz placement with short forward-fill. Year table showed physiologically impossible flats (e.g. 2013 20:60≈1.02 treated as a “shortlist” anomaly without same-ride diagnosis).

**Now:** `mmp_engine.py` wall-clock 1 Hz; **0 W counts as 0**; gaps >8 s → 0; spikes >1800 W rejected; Smart Recording hold ≤8 s. Day 4 `277575228` still **252.7 W ≈ 253 W** (PASS).

**2013 flat ratio:** same-ride owner `356001204` still 20:60≈1.02 with **0.23% zeros** → **steady plateau ride**, not residual gap inflation. MMP-60 **296.3 W MEASURED_MMP** stands; do not read the ratio as anaerobic capacity. Years 2010/2011/2016 fail high-side bands — shortlist hour coverage incomplete (**OPEN** for true year MMP-60).

## 2. Rebuild 7.5 → 5.0 weeks — explained, not waved away

**Prior addendum:** FIT-grounded **7.5 weeks**; claimed summary 5.0 was “optimistic by ~50%.”

**Now:** FIT/stream-grounded **5.0 weeks**, agreeing with summary. Reproduced in `reversal_audit.md`: restricting MMP map to **v1 shortlist.csv** IDs restores **7.5**. Sole material recovered-week change is **2012-01-07: 12 → 5 weeks** when v2 FIT coverage is used. The 7.5 figure was **sparse-FIT-map bias**, not evidence that personal rebuilds are 50% slower than summary.

## 3. DEVICE_SETTING vs PROXY “genuine contradiction”

**Prior Stage 2 text:** treated Jan 2016 FTP 260 vs weak proxies as measurement conflict.

**Now:** **DEVICE_SETTING**; `conflicts=false`. Retained from second pass; Stage 2 narrative regenerated without “genuine contradiction” / “fastest lever” framing.

## 4. Weight as independent lever

**Prior:** hold watts, cut to ~80 kg → 3.5 W/kg single path.

**Now:** coupled **0 / 3 / 6 W lost per kg** band; no archive-era body_metrics overlap (2026-only). First-class in authoritative report.

## 5. Failed rebuilds

**Prior brief:** not delivered.

**Now:** `rebuild_failures.md` — **null at n_failed=3**. Explicit.

## 6. Report structure

**Prior:** Stage 2 body denied true MMP while addendum published MEASURED_MMP table (contradiction).

**Now:** single `analysis_report.md`; prior dual copy snapshotted under `archive/superseded/`.

## 7. CP 282 / W′ 7.0 (OPEN)

Could not fetch `741976271` this run. Partial fit from `744349104` alone → CP≈268 W, W′≈6.9 kJ. **Question open** pending full track-day FITs.

## Still true / not overturned

- Alps Day 4 lore 253 W MEASURED_MMP confirmed.
- Summary rebuild ~5 weeks (12 recovered / 3 plateaued) unchanged as headline personal rate once FIT map is adequate.
- Shortlist_v2 diagnosis (NP-null Edge + composite cap truncating Alps) remains correct.

## 8. 2026 block compare — FTP ≠ archive MMP-20 (2026-08-07)

**Prior risk:** Treating app FTP **220 W** as comparable to archive annual MMP-20 peaks (e.g. 2015 **303.7 W**).

**Now:** Final FTP test `23884317052` is **outdoor** **20-min effort × 0.95**. Analysed effort avg **232.0 W**; stream **MMP-20 MEASURED_MMP = 222.6 W**. Only that stream number joins the year table. Full write-up: `block_2026_analysis.md`.

**Consistency:** 2026 longest ≥3-rides/week streak = **3** weeks — does **not** beat archive **8** (Apr–May 2012). Best 6-wk sub-block **26.4 h** vs archive #1 **59.4 h**.

**Still true:** wall-clock MMP engine; rebuild ~5 weeks; do not compare DEVICE FTP to MEASURED_MMP.

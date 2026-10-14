# Changelog: overturned archive conclusions

_Generated 2026-08-07T23:06:00_

This run reverses claims from the first shortlist/MMP pass. Do not soften.

## 1. 2012 MMP-60 / 'low-fitness year'

**Prior claim:** 2012 shortlist MMP-60 ≈159 W; year framed as low-fitness / fragmented, with an anomalous flat 5→60 ratio driven by easy rides that happened to clear the NP+layover composite shortlist.

**Now:** 2012 MMP-60 = **267.1W MEASURED_MMP** (Haute Route TCX streams on shortlist_v2: Day 1 peak MMP-60, Day 4 ≈253W matching stated Alps lore). The Alps block was excluded from v1 because Edge-era NP/TSS were null and composite scoring + cap 35 truncated duration-only days. That selection bug invalidated the prior 2012 narrative.

## 2. Jan 2016 FTP 260 vs weak proxy — not a MEASURED contradiction

**Prior claim:** framing 260 W FTP vs ~157 W proxy as a 'genuine contradiction' of measured fitness.

**Now:** 260 W (and 2012 ~242 W device FTP) are tagged **DEVICE_SETTING**. Gaps vs PROXY/MMP are expected for stale device config, not evidence against the athlete's measured peaks. Provenance-aware contradiction logic never sets `conflicts=true` for DEVICE_SETTING rows.

- 2012: stated 242W DEVICE_SETTING — conflicts=False
- 2016: stated 260W DEVICE_SETTING — conflicts=False

## 3. Rebuild central estimate

- Summary-only: **5.0 weeks**
- FIT/stream-grounded (`rebuild_fit`): **5.0 weeks**
- Recorded FIT/stream estimate 5.0 weeks on shortlist_v2 (compare to prior FIT pass ~7.5 weeks if that lived only in memory).

## 4. Weight-as-fastest-independent-lever framing

**Prior claim:** 'The fastest lever is weight, not watts' / hold watts constant and drop to ~80 kg to hit 3.5 W/kg as a single-point path.

**Now:** Couples weight and power. Report and Opus prompts require a band under **0 / 3 / 6 W lost per kg** dropped; sequence consistency → modest deficit → MMP-20 guardrail. Independent-lever framing is overturned.

Archive weight overlap: No overlapping weight history between body_metrics and archive MMP years (2009–2016). body_db span is 2026-03-30→2026-08-06.

## Remaining MEASURED conflicts (if any)

None among provenance-aware `contradictions_fit` with conflicts=true.

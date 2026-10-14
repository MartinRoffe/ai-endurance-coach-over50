# Rebuild reversal audit: 5.0 vs 7.5 weeks

_Generated 2026-08-07T22:54:47_

## Verdict

**5.0 weeks is the correct FIT/stream-grounded central estimate on shortlist_v2.**

The earlier **7.5 weeks** figure was not a summarizer bug in `analyse_rebuild`’s median math; it was produced by the **v1 shortlist (~35 IDs)** FIT map. Restricting today’s corrected MMP file to those old shortlist IDs **reproduces 7.5 exactly**.

Mechanism: with only v1 FIT coverage, layoff restart **2012-01-07** took **12 weeks** to recover under `fit_mmp_5min` baselines. Expanding to shortlist_v2 restores richer post-restart MMP coverage and that layoff returns to **5 weeks** (matching summary). Median of the twelve recovery durations therefore moves from 7.5 → 5.0.

The prior addendum claiming summary 5.0 was “optimistic by ~50%” was **wrong about the direction of bias for the full archive** — it overfitted a sparse FIT map. Both methods agree at **5.0** once FIT coverage is adequate.

## Central estimates

| Map | n FIT ids used | central weeks | IQR | n_fit_baseline |
|---|---:|---:|---|---:|
| Summary only (no FIT) | 0 | 5.0 | [3, 14] | 0 |
| Old shortlist.csv ∩ MMP | 20 | 7.5 | [3, 14] | 2 |
| shortlist_v2 MMP (current) | 101 | 5.0 | [3, 14] | 8 |

## Per-layoff weeks side-by-side

| restart | summary weeks | summary status | old-shortlist FIT weeks | old status / proxy | v2 FIT weeks | v2 status / proxy |
|---|---:|---|---:|---|---:|---|
| 2009-10-24 | None | plateaued_lower | None | plateaued_lower / speed_hr | None | plateaued_lower / speed_hr |
| 2010-01-09 | 3 | recovered | 3 | recovered / speed_hr | 3 | recovered / speed_hr |
| 2010-05-23 | None | plateaued_lower | None | plateaued_lower / avg_power_60plus | None | plateaued_lower / fit_mmp_5min |
| 2010-10-24 | 26 | recovered | 26 | recovered / speed_hr | 26 | recovered / speed_hr |
| 2011-01-02 | 5 | recovered | 5 | recovered / speed_hr | 5 | recovered / speed_hr |
| 2011-11-20 | 12 | recovered | 12 | recovered / avg_power_60plus | 12 | recovered / avg_power_60plus |
| 2012-01-07 | 5 | recovered | 12 | recovered / fit_mmp_5min | 5 | recovered / fit_mmp_5min |
| 2012-10-29 | 3 | recovered | 3 | recovered / avg_power_60plus | 3 | recovered / fit_mmp_20min |
| 2013-01-12 | 14 | recovered | 14 | recovered / avg_power_60plus | 14 | recovered / fit_mmp_20min |
| 2013-06-16 | 3 | recovered | 3 | recovered / avg_power_60plus | 3 | recovered / fit_mmp_1min |
| 2014-01-21 | 19 | recovered | 19 | recovered / avg_power_60plus | 19 | recovered / avg_power_60plus |
| 2014-05-17 | 3 | recovered | 3 | recovered / avg_power_60plus | 3 | recovered / fit_mmp_20min |
| 2015-01-01 | 3 | recovered | 3 | recovered / avg_power_60plus | 3 | recovered / avg_power_60plus |
| 2015-07-26 | 10 | recovered | 10 | recovered / fit_mmp_5min | 10 | recovered / fit_mmp_5min |
| 2016-05-13 | None | plateaued_lower | None | plateaued_lower / speed_hr | None | plateaued_lower / fit_mmp_5min |

## What moved between old FIT map and v2

- **2012-01-07**: 12 (recovered, fit_mmp_5min) → 5 (recovered, fit_mmp_5min)

### Recovered-week multisets

- Old FIT map recovered weeks: [3, 3, 3, 3, 3, 5, 10, 12, 12, 14, 19, 26]
- v2 FIT map recovered weeks: [3, 3, 3, 3, 3, 5, 5, 10, 12, 14, 19, 26]

Median of `[3,3,3,3,3,5,10,12,12,14,19,26]` = **7.5**; median of `[3,3,3,3,3,5,5,10,12,14,19,26]` = **5.0** (only material swap is 2012-01-07: 12 → 5).

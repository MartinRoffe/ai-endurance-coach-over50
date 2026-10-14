# Rebuild failure comparison (first 21 days)

_Generated 2026-08-07T22:54:47_

n_recovered=12, n_failed (plateaued_lower)=3.
Source: major layoffs in `findings.rebuild_fit.layoffs` (fallback `rebuild`).

## Per-restart features

| restart | status | layoff_d | month | rides_14d | w1_h | w2_h | w3_h | wow1→2 | longest_14d_h | intensity | further_gap |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2009-10-24 | plateaued_lower | 49 | 10 | 5 | 4.75 | 10.86 | 5.74 | 1.28 | 10.86 | 0.5 | True |
| 2010-05-23 | plateaued_lower | 42 | 5 | 2 | 7.63 | 0.0 | 0.0 | -1.0 | 6.66 | 0.5 | True |
| 2016-05-13 | plateaued_lower | 43 | 5 | 7 | 3.35 | 3.15 | 0.0 | -0.06 | 2.22 | 0.57 | True |
| 2010-01-09 | recovered | 47 | 1 | 8 | 2.42 | 5.49 | 7.41 | 1.27 | 2.01 | 0.46 | False |
| 2010-10-24 | recovered | 113 | 10 | 1 | 0.67 | 0.0 | 1.67 | -1.0 | 0.67 | 0.5 | True |
| 2011-01-02 | recovered | 56 | 1 | 2 | 1.29 | 0.74 | 2.16 | -0.43 | 1.29 | 0.33 | True |
| 2011-11-20 | recovered | 49 | 11 | 2 | 3.06 | 0.0 | 0.0 | -1.0 | 2.08 | 0.0 | True |
| 2012-01-07 | recovered | 42 | 1 | 2 | 2.0 | 0.29 | 5.18 | -0.85 | 2.0 | 0.5 | False |
| 2012-10-29 | recovered | 66 | 10 | 7 | 4.01 | 3.51 | 1.0 | -0.12 | 2.2 | 0.75 | True |
| 2013-01-12 | recovered | 60 | 1 | 4 | 0.01 | 2.3 | 8.11 | 201.27 | 0.95 | 0.57 | True |
| 2013-06-16 | recovered | 42 | 6 | 3 | 3.27 | 2.54 | 8.35 | -0.22 | 2.54 | 0.62 | False |
| 2014-01-21 | recovered | 81 | 1 | 5 | 1.15 | 0.78 | 0.0 | -0.32 | 0.5 | 0.6 | True |
| 2014-05-17 | recovered | 51 | 5 | 3 | 3.61 | 0.0 | 0.0 | -1.0 | 2.15 | 0.5 | True |
| 2015-01-01 | recovered | 43 | 1 | 3 | 2.08 | 4.0 | 6.54 | 0.92 | 2.08 | 0.5 | False |
| 2015-07-26 | recovered | 50 | 7 | 2 | 2.95 | 0.0 | 0.0 | -1.0 | 1.91 | 0.5 | True |

## Group medians

| metric | recovered median | failed median |
|---|---:|---:|
| layoff_days | 50.5 | 43 |
| restart_month | 3.0 | 5 |
| rides_14d | 3.0 | 5 |
| rides_21d | 4.5 | 7 |
| week1_h | 2.25 | 4.75 |
| week2_h | 0.76 | 3.15 |
| week3_h | 1.915 | 0.0 |
| wow_w1_w2 | -0.375 | -0.06 |
| wow_w2_w3 | 1.265 | -0.735 |
| intensity_share | 0.5 | 0.5 |
| longest_ride_14d_h | 2.005 | 6.66 |
| ef_trend_w1_w3 | -0.10795 | — |
| further_ge10d_gap_rate | 0.67 | 1.00 |

## Verdict

**Null result at n_failed=3.** No metric cleanly separates `plateaued_lower` from `recovered` (medians/ranges overlap on all compared features: ramp, ride count, intensity share, longest ride, EF trend, layoff length, restart month, further ≥10-day gap). Do not invent a causal pattern from three failures.

## Notes

- Intensity share = fraction of first-21-day rides above that restart's own median avg_hr or NP/avg_power.
- Weekly load uses Garmin TSS/training_load when present, else est_kJ = avg_power×duration_s/1000.
- EF trend requires NP+HR (or avg_power+HR); often sparse in Edge-era CSV rows.

# Shortlist v1 diagnosis — Alps exclusion

## Root cause

The Haute Route Alps activities **are present** in `activities_2009_2016.csv` with `avg_power` and elevation, but Garmin list-API fields `normalized_power` and `tss` are **null** on these 2012 Edge-era records.

v1 `build_shortlist` used a **single composite score**: post-layoff (+50…+30), top-15 NP (+30), top-15 duration (+20), EF needing NP (+25/+15). Alps Day 4 (`277575228`) only earned `longest` (+20). The shortlist cut at N=35 was dominated by layoff+NP+EF stacks (70–120). **Limit 35 truncated all Alps rides.** Not a string-sort bug and not a duration filter.

Cut line at rank 35: score **45.0**.

## Alps ID score replay

| Activity ID | Date | Score | Rank | In top 35? | Bumps | NP | avg_p | elev |
|---|---|---:|---:|---|---|---:|---:|---:|
| 277575486 | 2012-08-19 | 20.0 | 86 | no | longest(+20) | None | 232.0 | 2801.0 |
| 277575362 | 2012-08-20 | 0 | unscored | no | (no bumps fired) | None | 219.0 | 2523.0 |
| 277575279 | 2012-08-21 | 0 | unscored | no | (no bumps fired) | None | 192.0 | 920.0 |
| 277575228 | 2012-08-23 | 20.0 | 84 | no | longest(+20) | None | 225.0 | 3473.0 |
| 277575139 | 2012-08-24 | 20.0 | 85 | no | longest(+20) | None | 204.0 | 2982.0 |

## Top 10 v1 shortlist (for contrast)

| Rank | ID | Date | Score | Reasons |
|---:|---|---|---:|---|
| 1 | 661536652 | 2015-01-01 | 120.0 | post_layoff_2014-11-19, high_np, high_ef, low_ef |
| 2 | 844896374 | 2015-07-26 | 105.0 | post_layoff_2015-06-06, high_np, high_ef |
| 3 | 64516091 | 2011-01-02 | 90.0 | post_layoff_2010-07-03, post_layoff_2010-11-07 |
| 4 | 157077232 | 2012-01-07 | 90.0 | post_layoff_2011-10-02, post_layoff_2011-11-26 |
| 5 | 891471506 | 2015-09-07 | 90.0 | post_layoff_2015-06-06, high_np, high_ef |
| 6 | 64516089 | 2011-01-10 | 80.0 | post_layoff_2010-07-03, post_layoff_2010-11-07 |
| 7 | 710914369 | 2012-01-15 | 80.0 | post_layoff_2011-10-02, post_layoff_2011-11-26 |
| 8 | 629508349 | 2014-06-08 | 75.0 | post_layoff_2014-03-27, high_np, low_ef |
| 9 | 36562652 | 2010-05-23 | 70.0 | post_layoff_2010-04-11, longest |
| 10 | 64516086 | 2011-01-22 | 70.0 | post_layoff_2010-07-03, post_layoff_2010-11-07 |

## CSV NP / TSS null rates by year (cycling)

| Year | n | NP null % | TSS null % | avg_power null % |
|---|---:|---:|---:|---:|
| 2009 | 64 | 100.0 | 100.0 | 100.0 |
| 2010 | 46 | 100.0 | 100.0 | 73.9 |
| 2011 | 74 | 100.0 | 100.0 | 56.8 |
| 2012 | 89 | 100.0 | 100.0 | 15.7 |
| 2013 | 82 | 100.0 | 100.0 | 0.0 |
| 2014 | 50 | 96.0 | 100.0 | 50.0 |
| 2015 | 115 | 82.6 | 100.0 | 22.6 |
| 2016 | 59 | 100.0 | 100.0 | 88.1 |

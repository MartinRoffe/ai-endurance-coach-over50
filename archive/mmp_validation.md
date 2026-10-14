# MMP validation (Issue 1)

_Generated 2026-08-07T22:54:13_

## Root cause

Prior pipeline left missing samples as `None` and computed MMP only on contiguous non-None segments,
which excludes unrecordecd coast/pause time and can inflate long windows / flatten duration ratios.

Corrected `archive/mmp_engine.py`: keep 0 W; wall-clock 1 Hz; gaps >8 s → 0 W; ≤8 s Smart hold;
spikes >1800 W rejected; rolling MMP on the full series.

Annual rows still take **max across rides**. Flat year-level ratios may mean a steady plateau ride
(same-ride MMP-20≈MMP-60 is physically expected for near-constant power), not a remaining bug.

## 1a Zero handling (Day 4)

Wall-clock zero% = **7.76%**; recorded TCX zeros = 1593.
MMP-60 zeros-as-zero **252.7 W**; after dropping zeros from series **252.7 W** (Δ 0.0).
Day 4’s best hour is a climb with few zeros inside the window — drop-zeros barely moves it.

## Cross-check A — `277575228` Day 4

- MMP-60 expected 253 → got **252.7** → PASS
- Decoupling expected −3.3% → got **-2.2%** → PASS
- MMP curve: `{'mmp_5s': 864.4, 'mmp_1min': 340.9, 'mmp_2min': 277.8, 'mmp_5min': 265.0, 'mmp_20min': 257.0, 'mmp_60min': 252.7}`

## Cross-check B — `741976271` CP 282 / W′ 7.0 kJ

**OPEN:** could not obtain FIT/TCX for this activity ID from Garmin in this run.

## Corrected annual MMP table

| Year | 1min | 2min | 5min | 20min | 60min | 5:60 | 20:60 | flag | MMP60 owner | same-ride 20:60 |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|
| 2010 | 392.7 | 321.7 | 265.4 | 222.3 | 187.7 | 1.414 | 1.184 | FAIL | 29857461 | 1.101 |
| 2011 | 435.4 | 386.0 | 287.3 | 210.3 | 179.0 | 1.605 | 1.175 | FAIL | 710562678 | 1.169 |
| 2012 | 422.0 | 352.1 | 310.4 | 281.7 | 267.1 | 1.162 | 1.055 | ok | 277575486 | 1.055 |
| 2013 | 491.9 | 349.1 | 317.7 | 302.3 | 296.3 | 1.072 | 1.02 | FAIL | 356001204 | 1.02 |
| 2014 | 389.1 | 343.4 | 312.0 | 273.8 | 258.6 | 1.206 | 1.059 | ok | 542927862 | 1.054 |
| 2015 | 433.3 | 356.7 | 329.9 | 303.7 | 271.5 | 1.215 | 1.119 | ok | 948762554 | 1.075 |
| 2016 | 268.1 | 255.6 | 246.4 | 213.9 | 172.5 | 1.428 | 1.24 | FAIL | 1024480755 | 1.24 |

### Flag reading

- **2013** same-ride owner `356001204`: 20:60=1.02 with 0.23% zeros → **steady plateau**; MMP-60 296.3 W stands as MEASURED_MMP.
- **2010/2011/2016** fail high-side: weak hour coverage on shortlist — year MMP-60 is **open**/likely incomplete.
- **2012/2014/2015** pass bands.

## 1b–1e

Wall-clock enforced by 1 Hz grid. Smart Recording via median Δt. Missing → 0 W. Spikes >1800 W rejected.

## Cross-check B (continued) — partial local evidence

Garmin login for fresh download failed in this environment. Activity `741976271` is in the CSV as **2015-04-09** “SQT @ Lee Valley Velodrome” (not 11 Apr). The 11 Apr track races are separate IDs (`744349000`…).

Local FIT for **`744349104`** (40 Lap Points, 11 Apr 2015) only:

- MMP-2/5/20 = 320.0 / 306.5 / 262.8 W
- Two-parameter CP fit from those points: **CP 267.6 W, W′ 6.92 kJ**
- vs stated CP **282 W / W′ 7.0 kJ** → W′ ≈PASS; CP **FAIL by ~14 W** on this single race’s mean-max alone.

**OPEN:** Full CP lore cannot be confirmed until `741976271` and the other 11 Apr FITs are fetched. Do not treat 267.6 as overturning 282 without the rest of the set.

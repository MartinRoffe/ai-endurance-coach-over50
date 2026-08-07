# Power Training

This app uses a **dual-channel** model: heart rate drives recovery and readiness
decisions; measured watts drive pacing, load, and interval targets once your power
meter is active. This page covers setup, what unlocks, and where to find each
feature in the dashboard.

For tab-by-tab UI detail, see **[Performance](tabs/performance.md)**. For the
technical pipeline, open **[Architecture](architecture.md)** or
`/architecture` in the running dashboard.

---

## When power matters

The app considers your power meter **active** when you have recorded **at least
three rides with power data in the last 60 days** (`power_meter_active()`). Until
then, power-specific charts and coach context stay hidden or fall back to
HR-based estimates.

| Stays HR-primary (always) | Watts-primary when power active |
|---|---|
| Readiness composite score | Interval and climb pacing targets |
| HRV traffic light and session modulation | Coggan TSS and IF per ride |
| Garmin PMC projection (CTL/ATL/TSB on Performance) | Power PMC (Coggan CTL/ATL/TSB from daily TSS) |
| Fatigue alerts (HRV trend, deep TSB, etc.) | Measured FTP and W/kg charts |
| HRV-guided session swaps | Power zone polarisation |
| | Pw:HR decoupling on long rides |
| | Garmin structured workouts with %FTP targets |
| | Ride mechanical work (kJ) on nutrition surfaces |
| | Coach and analysis commentary on watts |

**Two load channels:** Garmin's training-load units (used for the main PMC chart
and TSB projection) are **not** the same as Coggan TSS. When power is active,
the Performance tab shows **both** — use Garmin PMC for readiness-adjacent
fatigue, and power TSS/PMC for pacing and interval load. Do not compare absolute
TSB numbers to TrainingPeaks or other tools.

---

## Setup checklist

1. **Record power on rides** — enable your meter (e.g. Favero Assioma) in Garmin
   Connect and complete at least a few outdoor rides with power data synced.
2. **Backfill and ingest** — from the terminal or Performance tab:
   ```bash
   endurance-coach --activate-power 30
   ```
   Or click **Activate power** on the Performance tab (`GET /activate-power?days=30`;
   accepts 7–90 days). This fetches activities, fills power columns, computes
   TSS where FTP is known, mines Pw:HR decoupling on rides ≥75 min, and seeds
   FTP from past test sessions if found.
3. **Check the activation checklist** on the Performance tab — six steps:
   record a power ride → run activation → reach ≥3 power rides in 60d → zones
   and decoupling populated → measured FTP watts saved → W/kg chart visible.
4. **Establish FTP** — complete a ramp or 20-minute FTP test session from your
   plan (see [FTP lifecycle](#ftp-lifecycle) below). The Readiness tab shows a
   **power baseline** card if the meter is active but no watts FTP exists yet.
5. **Re-sync Garmin workouts** — after a new FTP value is saved, a **stale
   workouts** banner appears on Performance. Hit **Sync workouts** (or
   `endurance-coach --workouts`) so scheduled sessions pick up updated %FTP
   targets. The app does not auto-push workout template changes.

Hardware setup and ramp-test protocol for Haute Route prep:
**Haute Route → Power protocol** (`/haute-route/power-protocol`).

---

## FTP lifecycle

**Auto-population from analysis.** When a post-workout analysis runs on an FTP
test session, the app saves to `ftp_tests`:

- **20-minute effort** — average watts over the qualifying effort × 0.95.
- **Ramp test** — 0.75 × best 1-minute wattage from ascending steps.

HR values (LTHR, max) are saved alongside watts when available.

**Power baseline card (Readiness).** If `power_meter_active()` is true but no
`ftp_w` row exists, the dashboard prompts you to schedule a ramp or baseline test
via the same Apply flow as HRV modulation.

**Retest cadence.** An FTP re-test card appears when the last test is more than
**42 days** old (or the table is empty more than three weeks into the plan).
Apply it to slot a test into an upcoming plan day.

**Stale workouts banner.** Saving a new `ftp_w` sets a cache flag. Clear it by
running `/sync-workouts` or `endurance-coach --workouts` — this re-uploads
cycling templates with current %FTP targets.

**App FTP vs Garmin profile FTP.** The app's measured FTP in `ftp_tests` and the
FTP set on your head unit / Garmin Connect profile are **independent**. Analysis
uses the app value for %FTP and TSS; Garmin power time-in-zone charts use the
device profile. Keep them aligned manually. If they diverge by more than ~7%,
analysis warns that zone percentages are miscalibrated.

**Threshold evidence / Accept estimate.** After FIT ingest of a hard 2×20 or
sustained ≥19 min effort above 103% of current FTP, Readiness shows an
**FTP likely stale** card with **Accept estimate** (writes `ftp_tests`, sets the
stale-workouts flag) or **Schedule retest**. You can also force a value:

```bash
endurance-coach --set-ftp 214 --date 2026-07-22
```

**FIT interval analysis.** On `/analysis-refresh`, power rides download the
original FIT when available; the Analysis tab also has **Upload FIT**. Per-step
metrics (NP, band compliance, 5-min splits, decoupling) appear on the activity
card and feed coach chat. After HTML template changes, run
`pip install --force-reinstall .` so the running server picks them up.

**HR calibration.** When device max HR or stored LTHR disagree with recent
evidence (12-month peak HR, threshold-effort HR, optional `hr_max_reference` in
`text_cache` / env), Readiness shows an **HR calibration** card. Update the
Garmin profile manually; Accept estimate updates app FTP/LTHR only.

---

## Performance tab (power surfaces)

**Route:** `/performance`

When power is active, these appear in addition to the standard Garmin PMC and
HR-based charts:

- **Weekly TSS bars** — summed Coggan TSS per week from power rides.
- **Power PMC** — CTL/ATL/TSB computed from daily TSS (42/7-day EMA), independent
  of Garmin's load model.
- **FTP trend** — dual-axis chart of LTHR and measured FTP watts over test history.
- **Measured W/kg** — primary trend from FTP test dates and body weight; VO₂max
  estimate shown as secondary overlay when power is active.
- **W/kg goal projection** — optional target weight and FTP paths (save via form
  on Performance).
- **Power zone polarisation** — stacked weekly bars from power zone data (parallel
  to the HR polarisation chart).
- **Pw:HR decoupling** — scatter/trend for rides ≥75 min: HR drift minus power
  drift (cardiac drift vs true aerobic decoupling).
- **Dual-channel caveat card** — explains which decisions use HR vs watts.
- **Last quality session snapshot** — normalised power vs %FTP for a recent
  quality ride (in the trends block).
- **Power profile** — collapsible Coggan 7-zone table from latest measured FTP.
- **Activation CTA** — link to `/activate-power` when onboarding is incomplete.

HR durability drift (late-ride HR rise on long rides) remains on Performance
regardless of power — it complements Pw:HR decoupling for aerobic fitness.

---

## Garmin workouts (%FTP)

Structured cycling workouts uploaded via `endurance-coach --workouts` or
`/sync-workouts` use **absolute watt ranges** (from %FTP × measured FTP) on
quality and endurance builders when:

- `power_meter_active()` is true, and
- a measured `ftp_w` exists in `ftp_tests`.

Z1 recovery builders stay HR/RPE only. Interval and endurance steps include an
HR backstop in the workout description for days when you ride without the meter.

**Future-only re-sync:** `--workouts` and `/sync-workouts` only unschedule and
re-schedule from **today** onward (`--from-date YYYY-MM-DD` to override). Past
calendar entries are left alone; library templates are rebuilt so new schedules
get current watt targets.

**Coverage:** remaining charity/event-prep/position-bridge days, **August
Tenerife** camp rides (`CAMP_PUSH_WORKOUTS`), and **Haute Route** bike + KB/Gym
strength through **31 Dec 2026**. Christmas Tenerife structured days in the HR
plan are pushed; KB + Trunk / Gym days upload as fitness-equipment kettlebell
workouts (not Recovery Spin).

Per-date overrides from coach chat, HRV modulation, or FTP retest use the same
`ftp_w` when pushing a single day to Garmin (`/apply-plan-change`).

---

## Haute Route power layer

On the **Haute Route** calendar (`/haute-route`):

- **%FTP prescriptions** on planned sessions when FTP is known (watt ranges on
  calendar tiles).
- **Planned TSS** on week headers (estimated from typical intensity factors).
- **Power familiarization bridge** — display card for 14 Sep – 4 Oct 2026 before
  the 46-week plan starts in earnest.
- **Peak-simulation decoupling warnings** — banner on weeks 36–43 if recent
  Pw:HR decoupling exceeds ~8%.
- **Power protocol page** — Favero setup, ramp FTP procedure, live zone table.

Stage pacing plans (expandable cards) use dual-channel %FTP and kJ grounding
when power is active.

---

## Coach and email

**Coach chat** injects extra context when power is active: Coggan zone table,
weekly TSS, measured W/kg, Pw:HR decoupling series, power zone distribution,
HR plan watt targets, and today's ride kJ. The system prompt uses
`hr_channel_note()` — watts for intervals and climbs; HR for readiness, heat,
altitude, and fatigue.

**Daily email** includes measured FTP and W/kg in the header when a power
profile exists. The Monday **weekly briefing** adds dual-channel intensity cues
and FTP retest notes when relevant.

Post-workout **Analysis** cards show power zones and per-rep watts on interval
sessions when data is present.

---

## FAQ

**Why doesn't my power meter show as active?**
You need ≥3 rides with `has_power_meter` in the last 60 days. Run
`--activate-power` after syncing new rides to Garmin.

**Garmin PMC vs Coggan TSS — which do I trust?**
Garmin PMC for "how recovered am I" alongside HRV and readiness. Coggan TSS/PMC
for "how hard was that ride" and interval pacing. They use different scales.

**Why weren't my Garmin workouts updated automatically after FTP changed?**
Template re-sync is manual (`/sync-workouts`) so you control when watch workouts
change. The stale-workouts banner reminds you.

**Measured vs estimated W/kg?**
**Measured** — from FTP test watts ÷ weight on test dates (primary when power
active). **Estimated** — ACSM formula from VO₂max and weight (useful before a
meter or as a secondary line on Performance).

**When should I re-run `--activate-power`?**
After a long gap without syncing, when adding historical rides, or if power
columns look empty on recent activities. Safe to run repeatedly; it backfills
without duplicating analyses unnecessarily.

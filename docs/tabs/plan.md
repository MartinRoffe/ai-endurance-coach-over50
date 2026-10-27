# Plan: Sessions, Guide & Compliance

**Nav:** the **Plan** tab → sticky subnav **Sessions**, **Guide**, and **Compliance**.

- **Sessions** — interactive calendar (do the work, mark completion)
- **Guide** — written version of the live 12-month fitness block
- **Compliance** — adherence stats across the block

---

## Sessions

**Route:** `/calendar`

### What it's for

The live calendar is the general-fitness year, 12 Oct 2026 – 3 Oct 2027
(procedure week, return, Christmas Tenerife, Keswick, the Lakes, Scotland,
then maintenance). The cancelled Ghent→Amsterdam block is an archive at
`/training/charity`.

> 📸 *Screenshot: the Sessions tab showing a training week with completion badges and a compound-session day.*

### What you'll see

- **One tile per session**, each showing the type, label, and planned duration.
  Completed sessions get a **completion badge**.
- **Split compound days.** A day with two sessions (e.g. kettlebells +
  stair-climber, or rucking + kettlebells) renders as **two independently
  clickable sub-tiles**, each with its own completion badge and its own detail.
- **Interference flags.** A quality bike session (tempo, sweet-spot, threshold,
  hill repeats, FTP test) gets an amber **⚠️** badge if you logged strength work
  in the previous 24 hours — a heads-up that the two may blunt each other.
- **Event-day plans.** Charity-ride pacing cards are omitted while the charity
  ride is cancelled.
- **A Mersea countdown**, when that build is active.
- **Haute Route calendar** (separate tab) shows **%FTP watt ranges** on planned
  sessions when measured FTP exists, plus a power familiarization bridge card.

### How to use it

- **Open a session for detail.** Click a tile to open its modal. Interval
  sessions show the work/rest structure; kettlebell sessions show the exercise
  list (with video links); rucking sessions show their route spec.
- **Log back-to-back fatigue.** On consecutive cycling days, a modal lets you
  record how the second day felt (a fatigue rating plus a note). This builds a
  back-to-back history the coach can reference.
- **Apply a session change** from the same modulation flow used on the home page,
  where offered — local override plus a best-effort single-date Garmin push.

### Sync workouts vs Apply

| Action | What it does |
|--------|----------------|
| **Apply** (Readiness / Coach) | One-day override + surgical Garmin push for that date only |
| **Sync workouts** / `--workouts` | Full re-upload: unschedule the plan range, rebuild templates, re-schedule all dates (override-aware). Use after FTP changes when %FTP targets are stale |

---

## Guide

**Route:** `/training`

### What it's for

The written version of the live fitness block (12 Oct 2026 – 3 Oct 2027):
procedure week, return, Tenerife, the Keswick ruck build, the Lakes weekend,
Scotland, then maintenance through the October 2027 checkpoint. Use **Sessions**
for the day you are actually doing.

### What you'll see

One card per phase. A phase that repeats shows the week; a phase that changes
(the camp, the ruck build, Scotland) lists each week. Garmin receives weekend
outdoor rides (`Z2 Easy`, `Long Ride (Easy)`) and weekday rower sessions
(`Threshold — rower`, `VO2 — rower`, `Z2 — rower`) as cardio workouts.
Saturday rucks push as hiking workouts at 10 kg (the 13 Feb rehearsal is
20.4 kg). MaxiClimber, strength, hikes, Teide, and BUSAR stay calendar-only.
Bike rides are outdoors and only at the weekend.

The cancelled Ghent→Amsterdam 12-week bible is an archive at `/training/charity`.

---

## Compliance

**Route:** `/compliance`

### What it's for

A closer look at *which kinds* of training you're keeping up with across the
fitness year (12 Oct 2026 – 3 Oct 2027).

### What you'll see

- **Overall adherence** — sessions and training time done vs planned.
- **Per-discipline breakdown** — completion rate by bike, strength, and ruck.
- **Phase dividers** for procedure, return, Tenerife, the Keswick build, the Lakes, Scotland, and maintenance.
- **Cumulative adherence chart** and week-by-week session log with day dots.

> 📸 *Screenshot: the Compliance tab showing per-discipline adherence bars.*

### Good to know

- **Completion is matched from your synced activities**, so a session only counts
  once the matching activity has landed in Garmin Connect.
- **Compound days are tracked per sub-session** — completing the kettlebell half
  but not the stair-climber half shows up accurately rather than as all-or-nothing.
- **Camp ride days** use estimated durations from distance and elevation for
  volume percentages; see [Power Training](../power-training.md) for how camp
  sessions are matched.

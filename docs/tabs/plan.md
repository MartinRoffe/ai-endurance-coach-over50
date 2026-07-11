# Plan: Sessions, Guide & Compliance

**Nav:** the **Plan** tab → sticky subnav **Sessions**, **Guide**, and **Compliance**.

- **Sessions** — interactive calendar (do the work, mark completion)
- **Guide** — static programme reference (zones, weekly pattern, tables)
- **Compliance** — adherence stats across the block

---

## Sessions

**Route:** `/calendar`

### What it's for

A unified calendar of every planned session — the 12-week build plan, the
Tenerife camp, and the event-prep block — with completion tracking and a few
smart flags layered on top.

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
- **Event-day plans.** For the charity ride days, expandable cards show
  AI-generated pacing and fuelling plans (carbs per hour, fluids, sodium, and
  framing versus your longest training ride).
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
  where offered.

---

## Guide

**Route:** `/training`

### What it's for

Static programme reference — weekly pattern, zones, and the full 12-week tables.
Use this when you want the written programme bible; use **Sessions** for day-to-day
scheduling and completion.

### What you'll see

Programme overview, zone guidance, and week-by-week session tables for the
charity-ride build.

---

## Compliance

**Route:** `/compliance`

### What it's for

A closer look at *which kinds* of training you're keeping up with across the
entire block through to the charity ride.

### What you'll see

- **Overall adherence** — sessions and training time done vs planned.
- **Per-discipline breakdown** — completion rate by bike, strength, and ruck.
- **18 weeks total** — 12-week plan, then three Tenerife camp weeks, then three
  event-prep weeks (including charity ride days), with phase dividers on the page.
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

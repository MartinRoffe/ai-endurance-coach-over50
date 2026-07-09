# Architecture Diagram

For a visual, interactive map of how the app fits together — modules, data
flow, SQLite schema, dashboard tabs, power-meter pipeline, and coach chat — open
the architecture diagram.

## View it

**In the running dashboard** (after `endurance-coach --serve`):

```
http://127.0.0.1:8743/architecture
```

**From a clone** (no server needed):

```
open architecture.html
```

Or open `architecture.html` from the repository root in any browser.

## What's inside

The diagram is a standalone HTML page with Mermaid flowcharts and reference
tables covering:

- **System overview** — CLI + FastAPI sharing the same core modules
- **Module map** — `metrics.py`, `history/` (SQLite stores), `analysis/` (power,
  intervals, AI), `server/` (FastAPI routes), `plan.py`, `power_profile.py`, etc.
- **Data flow** — Garmin fetch → SQLite → dashboard / email / coach
- **Database schema** — all SQLite tables and relationships (including power
  columns on `activities`, `ftp_tests.ftp_w`, `activity_power_durability`)
- **Dashboard tabs** — routes, templates, and key endpoints per page
- **Power meter** — dual-channel HR + power backfill, `power_meter_active()`
  gate, Coggan TSS, and coaching surfaces
- **Coach chat** — context assembly, tools, streaming, and memory

For user-facing power setup and dual-channel behaviour, see
**[Power Training](power-training.md)**.

Use it when onboarding to the codebase or tracing where a feature lives. The
text module list in the [project README](../README.md#architecture) and
[CLAUDE.md](../CLAUDE.md) stays the quick reference; the HTML diagram is the
full picture.

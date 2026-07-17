# Architecture Diagram

Interactive Mermaid map of how the app fits together — modules, data flow,
SQLite schema, dashboard tabs, power-meter pipeline, and coach chat.

Use this when onboarding to the codebase or tracing where a feature lives. For
day-to-day product use, start with [How the app works](how-it-works.md). For how
Claude is prompted and tooled, see [AI Architecture](ai-architecture.md).

## What's inside

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

In the Help centre the live diagram is embedded below this intro. You can also
open it fullscreen at `/architecture` in the dashboard, or open
`architecture.html` from the repository root in any browser.

For user-facing power setup and dual-channel behaviour, see
**[Power Training](power-training.md)**.

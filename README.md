# AI Endurance Coach Dashboard

Personal training readiness dashboard powered by Garmin Connect data and Claude AI.
Fetches daily metrics (HRV, sleep, stress, recovery), scores them against a 30-day
rolling baseline, and delivers a daily email briefing and live web dashboard.

**Help** — full walkthrough inside the dashboard at
[`/help`](http://127.0.0.1:8743/help) (How the app works → tabs → Coach, plus
Architecture and AI Architecture). Markdown sources live in [`docs/`](docs/README.md).

**⚡ [Power Training](docs/power-training.md)** — power meter setup, dual-channel HR + watts, TSS/PMC.

**🏗 Architecture** — interactive Mermaid map in Help (**For developers** → Architecture)
or fullscreen at `/architecture` ([docs/architecture.md](docs/architecture.md)).

## Features

**Readiness & alerts**
- **Daily readiness score** — composite z-score across 10+ Garmin wellness metrics
- **Fatigue alert system** — proactive HIGH/MODERATE banners for HRV decline (4 days), deep TSB, volume spike, illness risk, and high monotony; prepended to the daily email
- **HRV traffic light** — green/amber/red session modulation with one-click Apply overrides
- **Weekly coach briefing** — Monday-morning Claude Haiku briefing (form summary, key session, execution cue), cached per ISO week

**Power training (dual-channel)**
- **Power meter activation** — `--activate-power` backfills watts, TSS, decoupling; gate at ≥3 power rides in 60d
- **Measured FTP & W/kg** — ramp/20-min auto-extract, FTP trend chart (HR + watts), body and Performance tiles
- **Coggan TSS & power PMC** — weekly TSS bars and CTL/ATL/TSB independent of Garmin load
- **Power zone polarisation & Pw:HR decoupling** — on Performance when power active
- **Garmin %FTP workouts** — structured plan workouts with power targets when FTP known
- **Dual-channel coach** — watts for pacing/intervals; HR for readiness, HRV, and modulation

**AI**
- **AI Coach chat** — conversational coach with full training context, plan-change proposals, and cross-session memory
- **AI coaching advice** via Claude in the daily email (falls back to rule-based if no API key)
- **Post-workout HR/power zone analysis** with Claude commentary per activity
- **Session RPE logging** — emoji-based perceived effort on each analysis card, stored in SQLite, surfaced in coach context

**Performance & load**
- **Garmin PMC** — CTL/ATL/TSB with projection to event and taper scenarios
- **FTP trend chart** — LTHR and measured watts from test history, auto-populated from activity analyses
- **Zone 2 cardiac drift & HR durability** — aerobic fitness signals for long rides
- **Training polarisation charts** — HR zones always; power zones when meter active
- **W/kg goal projection** — optional target on Performance tab

**Calendar & compliance**
- **12-week cycling training plan** with structured workout uploads to Garmin Connect
- **Tenerife camp & event prep** on unified calendar; compliance tracks all 18 weeks
- **Split compound session tiles** — KB+MaxiClimber and Ruck+KB days render as two independent clickable cards
- **Interference load flag** — amber ⚠️ badge on quality bike sessions when strength was logged within 24 h
- **Back-to-back session tracker** — consecutive cycling pairs table with a fatigue log modal
- **Plan compliance view** — per-week adherence with discipline breakdown across plan + camp + event prep

**Nutrition tracking**
- **Garmin food log integration** — calories, carbs, protein, and fat pulled daily from Garmin Connect food diary
- **Readiness tab nutrition card** — logged kcal, TDEE, balance, macros, and ride kJ when power data exists
- **Body tab macro tiles** — today's carbs/protein plus 14-day rolling averages
- **Coach macro context** — AI coach receives daily and 14-day-average macro breakdown

**Other**
- **Body composition tracking** — weight, fat %, muscle mass, blood pressure (Garmin + Withings)
- **Withings sync** — push Withings body measurements to Garmin Connect
- **Daily email** with readiness score, measured FTP/W/kg when available, planned workout, and fatigue alerts
- **Haute Route Alpes 2028 plan** — two-year rebuild hub (medical pause → Year 1 hills → Year 2 cycling); 46-week week-by-week gated until Year 2
- **Tenerife cycling camp** itinerary (Aug 2026 historical); Christmas 2026 camp tentative; charity ride cancelled

## Prerequisites

- Python 3.11+
- Garmin Connect account
- Anthropic API key (optional — falls back to rule-based advice without it)
- Gmail account with an [App Password](https://support.google.com/accounts/answer/185833) (for email delivery)
- Power meter (optional — unlocks measured FTP, TSS, and %FTP Garmin workouts)

## Setup

```bash
git clone <repo-url>
cd ai-endurance-coach-over50
cp .env.example .env        # fill in credentials (see Configuration below)
pip install .
endurance-coach --backfill 30   # build 30-day baseline on first run
endurance-coach --activate-power 30   # optional: backfill power/TSS if you use a meter
```

## Configuration

Copy `.env.example` to `.env` and populate:

| Variable | Required | Description |
|---|---|---|
| `GARMIN_EMAIL` | ✓ | Garmin Connect login email |
| `GARMIN_PASSWORD` | ✓ | Garmin Connect password |
| `ANTHROPIC_API_KEY` | — | Claude API key for AI advice, coach chat, and workout analysis |
| `GMAIL_ADDRESS` | — | Sender address for daily email |
| `GMAIL_APP_PASSWORD` | — | Gmail App Password |
| `REPORT_TO` | — | Recipient email (defaults to `GMAIL_ADDRESS`) |
| `DASHBOARD_USER` | — | Basic auth username (dashboard is open if unset) |
| `DASHBOARD_PASSWORD` | — | Basic auth password |
| `HOST` | — | Dashboard bind address (default `127.0.0.1`; Tailscale IP or `0.0.0.0`) |

Scheduled jobs (macOS launchd and Linux systemd) do not see your shell environment. Copy `.env` to `~/.ai_endurance_coach_over50/.env` as well — `--setup-schedule` does this when that file is missing.

The dashboard binds to **127.0.0.1** by default (`--host`, or `HOST` / `COACH_BIND_HOST` in `.env`). `HOST` wins. That default is localhost only. On the always-on Ubuntu machine, set `HOST` to the Tailscale IPv4 (or `0.0.0.0`) and set `DASHBOARD_USER` and `DASHBOARD_PASSWORD` — with either blank, every route is open. See [docs/deploy-ubuntu.md](docs/deploy-ubuntu.md). Do not port-forward the app onto a public network.

## Usage

```bash
# Terminal readiness report
endurance-coach

# Web dashboard at http://127.0.0.1:8743 (localhost only)
endurance-coach --serve

# Send daily email (add --dry-run to preview without sending)
endurance-coach --email [--dry-run]

# Backfill historical data to build the 30-day baseline
endurance-coach --backfill 30

# Backfill power ingest + TSS (7–90 days)
endurance-coach --activate-power 30

# Upload structured cycling workouts to Garmin Connect
endurance-coach --workouts [--dry-run]

# Install the always-on server and the morning email
# macOS launchd writes 07:00. Linux systemd uses deploy/systemd (08:00).
endurance-coach --setup-schedule
```

## Architecture

**Visual diagram:** [architecture.html](architecture.html) in the repo root (or `http://127.0.0.1:8743/architecture` when the server is running). See [docs/architecture.md](docs/architecture.md) for a short guide to what's covered.

```
ai_endurance_coach_over50/
├── cli.py              Entry point; argument dispatch
├── client.py           Garmin Connect session/token handling
├── metrics.py          Garmin API calls → DailyMetrics dataclass
├── history/            SQLite persistence (db, metrics, activities, training, body, coach stores)
├── analysis/           Post-workout AI, power/TSS, intervals, prefetch, stage plans
├── server/             FastAPI dashboard (routes, context, coach, projection)
├── display.py          Value formatting, activity enrichment
├── alerts.py           Fatigue alert checks
├── report.py           HTML email, Claude advice, weekly briefing
├── plan.py             12-week plan + Tenerife + event prep
├── hr_plan.py          46-week Haute Route plan
├── power_profile.py    Coggan zones from measured ftp_w
├── energy.py           Ride kJ and planned session mechanical work
├── wkg_projection.py   W/kg goal projection charts
├── modulation.py       HRV traffic light and session swaps
├── workouts.py         Structured %FTP workout upload to Garmin
├── body.py             Body composition and blood pressure
├── withings.py         Withings → Garmin sync
├── architecture.html   Bundled system diagram (also at /architecture)
└── templates/          HTML templates for each dashboard tab
```

Data is stored in `~/.ai_endurance_coach_over50/history.db` (SQLite, auto-migrating schema).
Key power tables/columns: `activities` (avg/norm power, tss, if), `ftp_tests` (ftp_w),
`activity_power_durability` (Pw:HR decoupling).

## How the readiness score works

Each metric (HRV, sleep duration, sleep score, stress, resting HR, body battery, SpO₂, respiration, ACWR, acute training load) is z-scored against a 30-day rolling window. Lower-is-better fields (stress, ACWR, acute load) are sign-flipped so **positive always means above-average readiness**. The composite score is the mean across all scored fields that have enough baseline data. Power data does not enter the composite — see [dual-channel model](docs/power-training.md).

## AI Coach

The coach chat tab streams responses from Claude with full training context: Garmin PMC and power TSS when active, power profile and measured W/kg, today's readiness, all remaining plan sessions, recent activities, body composition, active plan overrides, RPE logs, and back-to-back fatigue history. The coach can propose session changes that appear as confirmation cards before being applied. Cross-session memory is maintained in SQLite.

Post-workout analysis uses Claude Sonnet. Recovery suggestions, workout descriptions, nutrition targets, fuelling plans, and weekly briefings use Claude Haiku.

## AI text caching

| Cache | Location | What it holds | How to clear |
|-------|----------|---------------|--------------|
| `_advice_cache` | `server/shared.py` in-process dict | Daily readiness advice | Restart server |
| `daily_advice` | SQLite table | Per-date advice (survives restart) | `DELETE FROM daily_advice WHERE date = '...'` |
| `text_cache` | SQLite table | Workout descriptions, weekly briefings, stage plans, `workouts_stale_ftp` | `DELETE FROM text_cache WHERE key = '...'` |
| `activity_analyses` | SQLite table | Per-activity coach analysis | `DELETE FROM activity_analyses WHERE activity_id IN (...)` then hit `/analysis-refresh` |
| `workout_descriptions` | SQLite table | 2-sentence coaching notes per session label | `DELETE FROM workout_descriptions WHERE label = '...'` |
| `nutrition_targets` | SQLite table | Daily macro targets per session type+duration | `DELETE FROM nutrition_targets WHERE session_key = '...'` |
| `fuelling_plans` | SQLite table | In-ride carb/fluid/sodium plans | `DELETE FROM fuelling_plans WHERE session_key = '...'` |

`workouts_stale_ftp` is set when a new measured FTP is saved; cleared on `/sync-workouts`.

## Background service

```bash
# macOS launchd: 07:00 email + server. Linux: deploy/systemd (08:00, matches the loaded Mac agent)
endurance-coach --setup-schedule
```

On macOS, restart the server after code changes:

```bash
launchctl kickstart -k "gui/$(id -u)/com.ai-endurance-coach-over50.server"
```

On Linux:

```bash
systemctl --user restart ai-endurance-coach.service
```

### Moving from the Mac to an always-on Ubuntu laptop

The step-by-step is [docs/deploy-ubuntu.md](docs/deploy-ubuntu.md): venv under `~/.ai_endurance_coach_over50/venv`, `rsync -a` of the data dir (then `chmod 600` on `.env`), the units in `deploy/systemd/`, and `sudo loginctl enable-linger "$USER"`. The timer is 08:00, the same clock as the launchd agent loaded on the Mac. Replace the copied `email.sh` — it points at the Mac pyenv. Unload the Mac agents only after the Tailscale URL works.

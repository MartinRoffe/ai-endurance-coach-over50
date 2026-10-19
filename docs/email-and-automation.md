# Email & Automation

Beyond the live dashboard, the app can email you each morning and run itself in
the background. This page covers the email, the weekly briefing, scheduling, and
the full set of command-line flags.

## The daily readiness email

Each morning the app can send an HTML email summarising your day:

- Your **readiness score** and the metrics behind it.
- **Measured FTP and W/kg** in the header when a power profile exists.
- The **planned workout** for the day (including any override you've applied).
- A **recent-activity summary**.
- Any **HIGH fatigue alerts**, pushed to the very top as a callout, followed by
  an HRV amber/red modulation note when relevant.

If you've set an Anthropic API key, the advice text is written by Claude;
otherwise it falls back to clear rule-based advice.

> 📸 *Screenshot: a daily readiness email in an inbox.*

Send one on demand:

```bash
endurance-coach --email            # send now
endurance-coach --email --dry-run  # preview in the terminal without sending
```

You can also trigger it from the **Send Email** action on the
[Readiness](tabs/readiness.md) page.

### Why the email sometimes waits

The email deliberately holds off until your overnight data (sleep score and
morning body battery) has synced from the watch. If that data isn't there yet,
the run exits and — under the scheduled setup below — retries about 30 minutes
later. This stops you getting an empty 7 a.m. email before your watch has synced.

## The weekly briefing

On Mondays the email leads with a short coach briefing — a summary of your
current form, the key session of the week, and an execution cue. When power is
active, the briefing may include dual-channel intensity notes and FTP retest
reminders. It's generated once per week and cached, so it's consistent all week.

## Why a 7 a.m. email used to arrive later (or not at all)

The macOS job is a launchd `StartCalendarInterval`. That fires at the clock
time only while the Mac is awake and you are logged in. Apple's launchd runs a
missed interval the next time the computer wakes, so a shut lid turns "07:00"
into "whenever the lid opened" — recent sends landing around 12:00 and 14:26
match that, not a second schedule.

Two further bugs made it worse:

- The plist this repo installed used **Hour 8**, while the docs said 7 a.m.
  An email at about 08:04 is an 08:00 start plus Garmin login, not a late 07:00.
- The email agent had **no `RunAtLoad`**. If the Mac was powered off through
  the slot, or the user session never unlocked that day, the job did not run.
  Only exit code 2 (watch not synced yet) was retried. Garmin, SMTP, and
  missing-environment failures exited immediately, and many of those errors
  were swallowed or logged at DEBUG. The scheduled process only shows WARNING
  and above, so `daily.log` often had no traceback. Non-interactive Garmin MFA
  now fails with exit code 3 and a clear message (refresh tokens once in a
  terminal) instead of hanging on `input()`.

`--setup-schedule` now installs a 07:00 job with catch-up, and the email
command logs failures. A `sent_YYYY-MM-DD` file plus an exclusive lock means
the catch-up cannot send a second email the same day. The shell wrapper still
retries while the watch has not synced (until 10:00, or three hours from a
later wake) and writes a timestamped line for every attempt.

## Running it in the background

```bash
endurance-coach --setup-schedule
```

On **macOS** this installs two launchd agents: the dashboard (`RunAtLoad` +
`KeepAlive`) and the email (`StartCalendarInterval` at 07:00 **and**
`RunAtLoad`, so a login after 07:00 still sends once).

On Linux it installs the units in `deploy/systemd/` (also copied by hand in [docs/deploy-ubuntu.md](deploy-ubuntu.md)):

- `ai-endurance-coach.service` — dashboard, `Restart=on-failure`, logs to `~/.ai_endurance_coach_over50/server.log`. Bind address comes from `HOST` in the data-dir `.env` (default `127.0.0.1`).
- `ai-endurance-coach-email.service` + `ai-endurance-coach-email.timer` — **08:00**, matching the launchd agent loaded on the Mac (`Hour` 8, no `RunAtLoad`). `Persistent=true` runs a missed 08:00 at next boot. `TimeoutStartSec=infinity` so the watch-sync retry is not killed by systemd's 90-second start timeout. The wrapper retries only exit code 2, every 30 minutes, for three hours after it starts, and logs to `daily.log`.

Set `DASHBOARD_USER` and `DASHBOARD_PASSWORD` before `HOST` is anything other than localhost. With either blank, every route is open — including `/send-email`, `/sync-workouts`, and `/apply-plan-change`. The full list is in [deploy-ubuntu.md](deploy-ubuntu.md).

After changing code, restart the server:

```bash
# macOS
launchctl kickstart -k "gui/$(id -u)/com.ai-endurance-coach-over50.server"

# Linux
systemctl --user restart ai-endurance-coach.service
```

> **Background runs need their own environment.** launchd and systemd do not
> see your shell. `--setup-schedule` copies `./.env` to
> `~/.ai_endurance_coach_over50/.env` when that file is missing, and the
> wrapper scripts point `DOTENV_PATH` at it.

### Moving from a Mac to an always-on Ubuntu laptop

Follow [deploy-ubuntu.md](deploy-ubuntu.md): rsync the data dir (keep `.env` mode `600`), install the venv, copy `deploy/systemd/` and `deploy/email.sh`, then `loginctl enable-linger`. The committed timer is **08:00**, matching the launchd agent loaded on the Mac. Leave the Mac agents loaded until the Tailscale URL works.

## All command-line flags

| Command | What it does |
|---|---|
| `endurance-coach` | Fetch today's data and print a readiness report in the terminal |
| `endurance-coach --serve` | Start the web dashboard at **http://127.0.0.1:8743** (localhost; `--host` / `HOST` / `COACH_BIND_HOST` to change the bind) |
| `endurance-coach --email [--dry-run]` | Send the daily email (or preview it) |
| `endurance-coach --backfill 30` | Pull the last *N* days from Garmin to build your baseline |
| `endurance-coach --activate-power 30` | Backfill power ingest, TSS, decoupling, and FTP seed (7–90 days; also `GET /activate-power` on Performance) |
| `endurance-coach --workouts [--dry-run]` | Upload the plan's structured cycling workouts to Garmin Connect and schedule them on their dates |
| `endurance-coach --withings-sync` | Push recent Withings measurements to Garmin, then continue the fetch |
| `endurance-coach --setup-schedule` | macOS: 07:00 email + always-on server. Linux: the 08:00 units in `deploy/systemd/` |

### About `--workouts`

This builds structured cycling workouts for each distinct session type in the
plan, uploads them to Garmin Connect once, and schedules each on its planned
dates — so the workouts appear on your watch ready to follow. Use `--dry-run`
first to see what would be uploaded. When a power meter is active and FTP is
known, quality and endurance builders include **%FTP** power targets (Z1 sessions
stay HR-only). Re-run after FTP changes — see [Power Training](power-training.md).

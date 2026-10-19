# Ubuntu (always-on) deploy

Move the dashboard and the morning email off the MacBook onto the HP Envy running Ubuntu, and open the dashboard over Tailscale. The Mac launchd agents stay as they are until you unload them yourself.

The units in [`deploy/systemd/`](../deploy/systemd/) follow the agents loaded on the Mac today:

| Mac (launchd) | Ubuntu (systemd --user) |
|---|---|
| `com.ai-endurance-coach-over50.server` — `RunAtLoad` + `KeepAlive`, logs to `~/.ai_endurance_coach_over50/server.log` | `ai-endurance-coach.service` — `Restart=on-failure`, same `server.log` |
| `com.ai-endurance-coach-over50.daily` — calendar **08:00**, no `RunAtLoad`, logs to `daily.log` | `ai-endurance-coach-email.timer` — `OnCalendar=*-*-* 08:00:00`, `Persistent=true` (a missed 08:00 runs at next boot, which is what launchd does for a missed calendar interval) |
| `email.sh` — retry **only exit code 2** every 30 minutes, stop **three hours after the process starts**, print `Watch never synced by 10:00 — giving up` | [`deploy/email.sh`](../deploy/email.sh) — the same rules, without the Mac `date -v` / pyenv paths |

`--setup-schedule` on a Mac still writes a **07:00** agent with `RunAtLoad`. That is not what is loaded on this Mac, and this move does not reload it.

## 1. Install Python and the package

On the Envy:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip rsync
git clone git@github.com:MartinRoffe/ai-endurance-coach-over50.git
cd ai-endurance-coach-over50
python3 -m venv ~/.ai_endurance_coach_over50/venv
~/.ai_endurance_coach_over50/venv/bin/pip install .
~/.ai_endurance_coach_over50/venv/bin/endurance-coach --help
```

The systemd units call `~/.ai_endurance_coach_over50/venv/bin/endurance-coach`. After code changes, reinstall with that venv's pip and restart the user service (below). Templates are package data, so a reinstall is required before the running server sees HTML changes.

## 2. Copy the data directory from the Mac

From the Mac, over Tailscale (MagicDNS name or the Envy's `100.x` address):

```bash
rsync -a ~/.ai_endurance_coach_over50/ envy:~/.ai_endurance_coach_over50/
```

`-a` keeps modes, times, and the Garmin token files. Confirm `.env` did not land world-readable:

```bash
ssh envy 'chmod 600 ~/.ai_endurance_coach_over50/.env && ls -l ~/.ai_endurance_coach_over50/.env'
```

That directory holds `history.db`, `.env`, Garmin tokens, `sent_YYYY-MM-DD` markers, and the logs. Do not commit it.

The copied `email.sh` and `serve.sh` point at the Mac pyenv (`/Users/.../.pyenv/...`). Replace the email wrapper with the Linux one, and leave the Mac copies on the Mac untouched:

```bash
# on the Envy, from the git checkout
cp deploy/email.sh ~/.ai_endurance_coach_over50/email.sh
chmod 755 ~/.ai_endurance_coach_over50/email.sh
```

Create the venv **before** rsync if rsync would otherwise refuse to merge, or rsync first and then create the venv. If rsync runs second it will not delete the venv (`-a` without `--delete`).

## 3. Choose the bind address

Default is `127.0.0.1`. To open the dashboard on the tailnet, set `HOST` in `~/.ai_endurance_coach_over50/.env` (this wins over `COACH_BIND_HOST`):

```bash
# tailnet only — preferred
HOST=100.x.x.x    # tailscale ip -4

# every interface, including Wi-Fi
# HOST=0.0.0.0
```

Set both of these as well. If either is blank, **every route is unauthenticated**:

```bash
DASHBOARD_USER=...
DASHBOARD_PASSWORD=...
```

### Routes that are unsafe on the tailnet without that auth

The app attaches HTTP Basic to the whole FastAPI app. It is a no-op when `DASHBOARD_USER` or `DASHBOARD_PASSWORD` is empty. These routes then do something with side effects or spend API credit:

- `GET /send-email` — sends the daily email
- `GET /sync-workouts` — deletes and re-uploads Garmin workouts
- `GET /refresh`, `GET /analysis-refresh`, `GET /body-refresh`, `GET /withings-sync`, `GET /activate-power` — talk to Garmin or Withings
- `GET /recovery-suggestion`, `POST /regenerate-advice`, `POST /regenerate-body-advice`, `POST /coach-memory/update` — call Claude
- `POST /coach-chat`, `POST /coach-chat-stream`, `POST /coach-tts` — coach chat and speech (API spend; chat can propose plan changes)
- `POST /apply-plan-change` — writes a plan override and pushes that day to Garmin
- `DELETE /coach-history`
- `POST /upload-fit`
- `POST /log-rpe`, `POST /log-wellness`, `POST /log-fuelling`, `POST /log-btb`, `POST /wkg-goal`, `POST /accept-ftp-estimate`
- `POST /climbs/pin`, `POST /climbs/merge`, `POST /climbs/named/{id}`, `POST /climbs/essay`
- `GET /nutrition-test` — raw Garmin food-log payload

The HTML pages (`/`, `/body`, `/sleep`, `/calendar`, `/coach`, `/memory`, `/coach-history`, `/api/ftp-tests`, `/api/search`, `/btb-summary`) are the health and training record. `/docs` and `/redoc` are disabled.

`HOST=0.0.0.0` also listens on the café or home LAN, not only Tailscale. Prefer `HOST` set to the Tailscale IPv4. If `ufw` is enabled, allow the port on the tailnet interface only:

```bash
sudo ufw allow in on tailscale0 to any port 8743 proto tcp
```

## 4. Enable the user units without a login session

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/ai-endurance-coach.service \
   deploy/systemd/ai-endurance-coach-email.service \
   deploy/systemd/ai-endurance-coach-email.timer \
   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ai-endurance-coach.service
systemctl --user enable --now ai-endurance-coach-email.timer
sudo loginctl enable-linger "$USER"
```

`enable-linger` lets the user manager keep running after you disconnect, so the dashboard and the 08:00 timer do not die at logout. Check it:

```bash
loginctl show-user "$USER" -p Linger
```

`Linger=yes` is what you want. The same units are what `endurance-coach --setup-schedule` writes on Linux (`apply` also runs `loginctl enable-linger` when it can).

## 5. Check that it is up

```bash
systemctl --user status ai-endurance-coach.service
systemctl --user status ai-endurance-coach-email.timer
systemctl --user list-timers ai-endurance-coach-email.timer
journalctl --user -u ai-endurance-coach.service -n 40 --no-pager
tail -n 40 ~/.ai_endurance_coach_over50/server.log
```

The service appends stdout and stderr to `server.log`. The email oneshot appends to `daily.log` (same paths as launchd). `journalctl` shows start/stop lines on top of that.

A dry run of the email, without sending:

```bash
~/.ai_endurance_coach_over50/venv/bin/endurance-coach --email --dry-run
```

Trigger the timer once without waiting for 08:00:

```bash
systemctl --user start ai-endurance-coach-email.service
tail -n 20 ~/.ai_endurance_coach_over50/daily.log
```

After a code change:

```bash
~/.ai_endurance_coach_over50/venv/bin/pip install --force-reinstall .
systemctl --user restart ai-endurance-coach.service
```

## 6. Tailscale URL

On the Envy:

```bash
tailscale ip -4
tailscale status
```

With `HOST` set to that IPv4 (or `0.0.0.0`), open:

```text
http://<tailscale-ipv4>:8743
http://<magicdns-name>:8743
```

The MagicDNS name is the first column of `tailscale status` (often `something.tailXXXX.ts.net`). The browser will ask for `DASHBOARD_USER` / `DASHBOARD_PASSWORD`.

From the Mac, leave the launchd agents loaded until this URL and a dry-run email look right. Unload them only when you want the Mac to stop sending as well:

```bash
launchctl bootout "gui/$(id -u)/com.ai-endurance-coach-over50.server"
launchctl bootout "gui/$(id -u)/com.ai-endurance-coach-over50.daily"
```

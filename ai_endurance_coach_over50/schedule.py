"""Install the daily email and the always-on dashboard.

macOS uses launchd user agents (07:00 in this installer, with RunAtLoad).
The agents actually loaded on the Mac today are 08:00 with no RunAtLoad;
``deploy/systemd/`` and the Linux branch copy that loaded schedule.
Linux uses systemd --user units. Both load
``~/.ai_endurance_coach_over50/.env`` (or ``ENDURANCE_COACH_HOME``).
The dashboard listens on 127.0.0.1 unless ``HOST`` (or ``COACH_BIND_HOST``)
is set. The email catches up after sleep or power-off, and the Python CLI
refuses a second send the same day.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from .paths import data_dir

EMAIL_LABEL = "com.ai-endurance-coach-over50.daily"
SERVER_LABEL = "com.ai-endurance-coach-over50.server"
SYSTEMD_SERVER = "ai-endurance-coach.service"
SYSTEMD_EMAIL = "ai-endurance-coach-email.service"
SYSTEMD_TIMER = "ai-endurance-coach-email.timer"


def _deadline_python() -> str:
    # 07:00 start waits until at least 10:00; a later catch-up gets three hours.
    return (
        "from datetime import datetime, timedelta; "
        "now=datetime.now(); "
        "ten=now.replace(hour=10, minute=0, second=0, microsecond=0); "
        "plus=now+timedelta(hours=3); "
        "deadline=plus if now>=ten else max(ten, plus); "
        "print(int(deadline.timestamp()))"
    )


def render_serve_script(python: str, project_dir: str, env_file: Path) -> str:
    return (
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        f"export PYTHONPATH={project_dir}\n"
        f"export DOTENV_PATH={env_file}\n"
        "# Bind address: HOST or COACH_BIND_HOST in the env file, else 127.0.0.1.\n"
        f"exec {python} -m ai_endurance_coach_over50.cli --serve\n"
    )


def render_email_script(python: str, project_dir: str, env_file: Path) -> str:
    deadline = _deadline_python()
    return (
        "#!/bin/bash\n"
        "# Daily readiness email.\n"
        "# The Python CLI holds an exclusive lock and a sent_YYYY-MM-DD sentinel,\n"
        "# so a 07:00 timer plus a catch-up-on-wake/login cannot double-send.\n"
        "# Exit 2 means the watch has not synced overnight data yet.\n"
        "set -u\n"
        f"export PYTHONPATH={project_dir}\n"
        f"export DOTENV_PATH={env_file}\n"
        "echo \"$(date '+%Y-%m-%dT%H:%M:%S%z') email job starting (pid $$)\"\n"
        "START_DAY=$(date +%Y-%m-%d)\n"
        f"DEADLINE=$({python} -c \"{deadline}\") || exit 1\n"
        "while true; do\n"
        "    TODAY=$(date +%Y-%m-%d)\n"
        "    if [ \"$TODAY\" != \"$START_DAY\" ]; then\n"
        "        echo \"$(date '+%Y-%m-%dT%H:%M:%S%z') calendar day changed — stopping retry loop\"\n"
        "        exit 2\n"
        "    fi\n"
        "    echo \"$(date '+%Y-%m-%dT%H:%M:%S%z') email attempt\"\n"
        f"    {python} -m ai_endurance_coach_over50.cli --withings-sync --email --fetch\n"
        "    CODE=$?\n"
        "    echo \"$(date '+%Y-%m-%dT%H:%M:%S%z') email attempt exit $CODE\"\n"
        "    if [ \"$CODE\" -eq 0 ]; then\n"
        "        exit 0\n"
        "    fi\n"
        "    NOW=$(date +%s)\n"
        "    if [ \"$NOW\" -ge \"$DEADLINE\" ]; then\n"
        "        echo \"$(date '+%Y-%m-%dT%H:%M:%S%z') email job giving up for today (last exit $CODE)\"\n"
        "        exit \"$CODE\"\n"
        "    fi\n"
        "    echo \"$(date '+%Y-%m-%dT%H:%M:%S%z') email not sent (exit $CODE); retrying in 30 min\"\n"
        "    sleep 1800\n"
        "done\n"
    )


def render_launchd_plist(label: str, script: Path, log_name: str, extra_keys: str) -> str:
    log = data_dir() / f"{log_name}.log"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>{script}</string>
    </array>
    {extra_keys}
    <key>StandardOutPath</key>
    <string>{log}</string>
    <key>StandardErrorPath</key>
    <string>{log}</string>
</dict>
</plist>
"""


def email_launchd_keys() -> str:
    # RunAtLoad catches a login after 07:00 (sleep/power-off miss). The CLI
    # sentinel makes a second same-day run a no-op. StartCalendarInterval
    # itself also coalesces onto the next wake — that is why a shut lid
    # delivers the email at unlock time rather than at 07:00.
    return """<key>RunAtLoad</key>
    <true/>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>7</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>"""


def server_launchd_keys() -> str:
    return """<key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>"""


def render_linux_email_script() -> str:
    """Retry loop copied from the macOS ``email.sh`` the launchd agent runs.

    Exit 0 finishes. Exit 2 (watch not synced) sleeps 30 minutes and tries
    again. Any other code stops. The deadline is three hours after the
    process starts (``date -v+3H`` on the Mac). The give-up line is the
    same text the Mac wrapper prints.
    """
    return """#!/bin/bash
# Daily readiness email. Same retry rules as the macOS launchd wrapper.
# Exit 0: sent. Exit 2: watch has not synced — retry every 30 minutes.
# Any other status stops immediately (no retry).
# Deadline is three hours after start (same as the Mac wrapper).
set -u
DATA="${ENDURANCE_COACH_HOME:-$HOME/.ai_endurance_coach_over50}"
export DOTENV_PATH="${DOTENV_PATH:-$DATA/.env}"
BIN="${ENDURANCE_COACH_BIN:-$DATA/venv/bin/endurance-coach}"
if [ ! -x "$BIN" ]; then
    BIN="$(command -v endurance-coach || true)"
fi
if [ -z "${BIN}" ]; then
    echo "endurance-coach not found" >&2
    exit 1
fi
PY="${BIN%/*}/python"
if [ ! -x "$PY" ]; then
    PY="$(command -v python3)"
fi
DEADLINE="$("$PY" -c "from datetime import datetime, timedelta; print(int((datetime.now()+timedelta(hours=3)).timestamp()))")" || exit 1
while true; do
    "$BIN" --withings-sync --email --fetch
    CODE=$?
    if [ "$CODE" -eq 0 ]; then
        exit 0
    fi
    if [ "$CODE" -ne 2 ]; then
        exit "$CODE"
    fi
    NOW=$(date +%s)
    if [ "$NOW" -ge "$DEADLINE" ]; then
        echo "Watch never synced by 10:00 — giving up"
        exit 2
    fi
    echo "Watch not synced yet, retrying in 30 min…"
    sleep 1800
done
"""


def render_systemd_server() -> str:
    # No --host: the CLI reads HOST / COACH_BIND_HOST from DOTENV_PATH
    # (default 127.0.0.1). Logs are the same files launchd appends to.
    return """[Unit]
Description=AI Endurance Coach dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=%h/.ai_endurance_coach_over50/venv/bin/endurance-coach --serve
Environment=DOTENV_PATH=%h/.ai_endurance_coach_over50/.env
Environment=PATH=%h/.ai_endurance_coach_over50/venv/bin:/usr/local/bin:/usr/bin:/bin
Restart=on-failure
RestartSec=5
StandardOutput=append:%h/.ai_endurance_coach_over50/server.log
StandardError=append:%h/.ai_endurance_coach_over50/server.log

[Install]
WantedBy=default.target
"""


def render_systemd_email_service() -> str:
    return """[Unit]
Description=AI Endurance Coach daily readiness email
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/bash %h/.ai_endurance_coach_over50/email.sh
Environment=DOTENV_PATH=%h/.ai_endurance_coach_over50/.env
Environment=PATH=%h/.ai_endurance_coach_over50/venv/bin:/usr/local/bin:/usr/bin:/bin
# The script retries for up to three hours while the watch syncs.
# systemd's default start timeout (90s) would kill that loop.
TimeoutStartSec=infinity
StandardOutput=append:%h/.ai_endurance_coach_over50/daily.log
StandardError=append:%h/.ai_endurance_coach_over50/daily.log
"""


def render_systemd_email_timer() -> str:
    # Hour 8 matches the loaded launchd plist (StartCalendarInterval).
    # Persistent=true is launchd's missed-interval catch-up: if the machine
    # was off at 08:00, the job runs at next boot. There is no RunAtLoad
    # on the Mac daily agent, so this timer does not fire on every login.
    return f"""[Unit]
Description=Daily 08:00 readiness email (same clock as the macOS launchd agent)

[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true
AccuracySec=1min
Unit={SYSTEMD_EMAIL}

[Install]
WantedBy=timers.target
"""


def _ensure_env_file(home: Path) -> Path:
    env_file = home / ".env"
    src_env = Path.cwd() / ".env"
    home.mkdir(parents=True, exist_ok=True)
    if not env_file.exists() and src_env.exists():
        shutil.copy2(src_env, env_file)
        env_file.chmod(0o600)
    return env_file


def _write_scripts(home: Path, env_file: Path, *, system: str) -> tuple[Path, Path]:
    python = sys.executable
    project_dir = str(Path(__file__).resolve().parent.parent)
    serve_script = home / "serve.sh"
    email_script = home / "email.sh"
    serve_script.write_text(render_serve_script(python, project_dir, env_file))
    if system == "Linux":
        email_script.write_text(render_linux_email_script())
    else:
        email_script.write_text(render_email_script(python, project_dir, env_file))
    serve_script.chmod(0o755)
    email_script.chmod(0o755)
    return serve_script, email_script


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def setup_schedule(
    *,
    system: str | None = None,
    apply: bool = True,
    launch_agents_dir: Path | None = None,
    systemd_dir: Path | None = None,
) -> list[str]:
    """Write wrapper scripts and install the platform scheduler.

    ``apply=False`` writes the unit files but does not call launchctl,
    systemctl, or loginctl. Returns lines for the CLI to print.
    """
    system = system or platform.system()
    home = data_dir()
    env_file = _ensure_env_file(home)
    serve_script, email_script = _write_scripts(home, env_file, system=system)
    lines = [
        f"Scripts: {serve_script}",
        f"         {email_script}",
        f"Env:     {env_file}",
    ]

    if system == "Darwin":
        lines.extend(_install_launchd(
            serve_script, email_script,
            agents_dir=launch_agents_dir,
            apply=apply,
        ))
    elif system == "Linux":
        lines.extend(_install_systemd(
            email_script,
            unit_dir=systemd_dir,
            apply=apply,
        ))
    else:
        lines.append(
            f"No scheduler integration for {system}. "
            "Run serve.sh for the dashboard and email.sh from cron at 07:00."
        )
    lines.append(
        "Dashboard bind defaults to 127.0.0.1. Set HOST in the data-dir .env "
        "(Tailscale IP or 0.0.0.0) to listen beyond localhost."
    )
    return lines


def _install_launchd(
    serve_script: Path,
    email_script: Path,
    *,
    agents_dir: Path | None,
    apply: bool,
) -> list[str]:
    agents = agents_dir or (Path.home() / "Library" / "LaunchAgents")
    agents.mkdir(parents=True, exist_ok=True)
    email_plist = agents / f"{EMAIL_LABEL}.plist"
    server_plist = agents / f"{SERVER_LABEL}.plist"
    email_plist.write_text(render_launchd_plist(
        EMAIL_LABEL, email_script, "daily", email_launchd_keys(),
    ))
    server_plist.write_text(render_launchd_plist(
        SERVER_LABEL, serve_script, "server", server_launchd_keys(),
    ))
    lines = [
        "macOS launchd agents written.",
        "Email: 07:00 plus RunAtLoad catch-up (once-per-day sentinel).",
        f"Logs:  {data_dir() / 'daily.log'}  and  {data_dir() / 'server.log'}",
    ]
    if not apply:
        lines.append("launchctl not invoked (apply=False).")
        return lines
    for path, name in ((server_plist, "server"), (email_plist, "daily email")):
        _run(["launchctl", "unload", str(path)])
        result = _run(["launchctl", "load", str(path)])
        if result.returncode == 0:
            lines.append(f"Loaded {name}.")
        else:
            err = (result.stderr or result.stdout or "").strip()
            lines.append(f"Could not load {name}: {err}")
    lines.append(
        "Restart the server after code changes: "
        'launchctl kickstart -k "gui/$(id -u)/com.ai-endurance-coach-over50.server"'
    )
    return lines


def _install_systemd(
    email_script: Path,
    *,
    unit_dir: Path | None,
    apply: bool,
) -> list[str]:
    units = unit_dir or (Path.home() / ".config" / "systemd" / "user")
    units.mkdir(parents=True, exist_ok=True)
    (units / SYSTEMD_SERVER).write_text(render_systemd_server())
    (units / SYSTEMD_EMAIL).write_text(render_systemd_email_service())
    (units / SYSTEMD_TIMER).write_text(render_systemd_email_timer())
    lines = [
        f"systemd user units written to {units}.",
        "Server: Restart=on-failure. Logs: ~/.ai_endurance_coach_over50/server.log",
        "Email: 08:00 timer, Persistent=true, retry exit 2 every 30 min for 3 hours.",
        f"Email script: {email_script}",
        f"Logs: {data_dir() / 'daily.log'} and journalctl --user -u {SYSTEMD_SERVER}",
    ]
    if not apply:
        lines.append("systemctl not invoked (apply=False).")
        lines.append(_linger_hint())
        lines.append(_mac_disable_hint())
        return lines

    reload = _run(["systemctl", "--user", "daemon-reload"])
    if reload.returncode != 0:
        err = (reload.stderr or reload.stdout or "systemctl --user daemon-reload failed").strip()
        lines.append(err)
        lines.append("Enable later with:")
        lines.append(f"  systemctl --user enable --now {SYSTEMD_SERVER}")
        lines.append(f"  systemctl --user enable --now {SYSTEMD_TIMER}")
    else:
        for unit in (SYSTEMD_SERVER, SYSTEMD_TIMER):
            result = _run(["systemctl", "--user", "enable", "--now", unit])
            if result.returncode == 0:
                lines.append(f"Enabled {unit}.")
            else:
                err = (result.stderr or result.stdout or "").strip()
                lines.append(f"Could not enable {unit}: {err}")
    lines.extend(_enable_linger())
    lines.append(_mac_disable_hint())
    return lines


def _linger_hint() -> str:
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or "$USER"
    return (
        f"So the user services keep running without a login session: "
        f"sudo loginctl enable-linger {user}"
    )


def _enable_linger() -> list[str]:
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    if not user:
        return [_linger_hint()]
    result = _run(["loginctl", "enable-linger", user])
    if result.returncode == 0:
        return [f"loginctl linger enabled for {user}."]
    err = (result.stderr or result.stdout or "").strip()
    return [
        f"Could not enable linger ({err})." if err else "Could not enable linger.",
        _linger_hint(),
    ]


def _mac_disable_hint() -> str:
    return (
        "If this laptop replaces a Mac, unload the old agents there: "
        f"launchctl bootout gui/$(id -u) {EMAIL_LABEL} "
        f"and launchctl bootout gui/$(id -u) {SERVER_LABEL}"
    )

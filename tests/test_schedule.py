"""Scheduler installers: macOS launchd and Linux systemd user units."""
import inspect

from ai_endurance_coach_over50.paths import data_dir
from ai_endurance_coach_over50.schedule import (
    render_linux_email_script,
    setup_schedule,
)
from ai_endurance_coach_over50.server import run

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def test_server_bind_defaults_to_localhost():
    host = inspect.signature(run).parameters["host"].default
    assert host == "127.0.0.1"


def test_linux_systemd_units(tmp_path):
    unit_dir = tmp_path / "systemd"
    lines = setup_schedule(system="Linux", apply=False, systemd_dir=unit_dir)
    text = "\n".join(lines)
    assert "systemctl not invoked" in text
    assert "enable-linger" in text

    server = (unit_dir / "ai-endurance-coach.service").read_text()
    email = (unit_dir / "ai-endurance-coach-email.service").read_text()
    timer = (unit_dir / "ai-endurance-coach-email.timer").read_text()
    assert "Restart=on-failure" in server
    assert "RestartSec=5" in server
    assert "DOTENV_PATH=" in server
    assert "TimeoutStartSec=infinity" in email
    assert "Type=oneshot" in email
    assert "OnCalendar=*-*-* 08:00:00" in timer
    assert "Persistent=true" in timer
    assert "07:00" not in timer
    assert "StandardOutput=append:%h/.ai_endurance_coach_over50/server.log" in server
    assert "StandardOutput=append:%h/.ai_endurance_coach_over50/daily.log" in email
    assert "--host" not in server
    assert (ROOT / "deploy/systemd/ai-endurance-coach.service").read_text() == server
    assert (ROOT / "deploy/systemd/ai-endurance-coach-email.service").read_text() == email
    assert (ROOT / "deploy/systemd/ai-endurance-coach-email.timer").read_text() == timer

    serve = (data_dir() / "serve.sh").read_text()
    email_sh = (data_dir() / "email.sh").read_text()
    assert "--serve" in serve
    assert "--host" not in serve
    assert "0.0.0.0" not in serve
    assert email_sh == render_linux_email_script()
    assert (ROOT / "deploy/email.sh").read_text() == email_sh
    assert "--withings-sync --email --fetch" in email_sh
    assert "sleep 1800" in email_sh
    assert 'exit "$CODE"' in email_sh
    assert "--email-incomplete" in email_sh
    assert "sending with the data on hand" in email_sh
    assert "giving up" not in email_sh
    assert "pyenv" not in email_sh
    assert "/Users/" not in email_sh
    env = data_dir() / ".env"
    # No project .env in the test sandbox; the path is still the redirected home.
    assert env.parent == data_dir()


def test_macos_launchd_is_7am_with_catchup(tmp_path):
    agents = tmp_path / "LaunchAgents"
    lines = setup_schedule(
        system="Darwin", apply=False, launch_agents_dir=agents,
    )
    assert "launchctl not invoked" in "\n".join(lines)
    email = (agents / "com.ai-endurance-coach-over50.daily.plist").read_text()
    server = (agents / "com.ai-endurance-coach-over50.server.plist").read_text()
    assert "<key>Hour</key>" in email
    assert "<integer>7</integer>" in email
    assert "<integer>8</integer>" not in email
    assert "<key>RunAtLoad</key>" in email
    assert "<true/>" in email
    assert "<key>KeepAlive</key>" in server
    assert "--host" not in (data_dir() / "serve.sh").read_text()
    assert "--serve" in (data_dir() / "serve.sh").read_text()

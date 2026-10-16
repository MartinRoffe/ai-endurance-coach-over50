"""Data dir, bind address, and the absence of Mac-only paths in the package."""
from pathlib import Path

from ai_endurance_coach_over50.paths import dashboard_bind_host, data_dir
from ai_endurance_coach_over50.schedule import setup_schedule

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "ai_endurance_coach_over50"


def test_default_data_dir_is_dotdir_not_library(monkeypatch):
    monkeypatch.delenv("ENDURANCE_COACH_HOME", raising=False)
    path = data_dir()
    assert path == Path.home() / ".ai_endurance_coach_over50"
    assert "Library" not in path.parts


def test_endurance_coach_home_overrides_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("ENDURANCE_COACH_HOME", str(tmp_path / "elsewhere"))
    assert data_dir() == tmp_path / "elsewhere"


def test_bind_host_default_and_overrides(monkeypatch):
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("COACH_BIND_HOST", raising=False)
    assert dashboard_bind_host() == "127.0.0.1"

    monkeypatch.setenv("COACH_BIND_HOST", "100.1.2.3")
    assert dashboard_bind_host() == "100.1.2.3"

    monkeypatch.setenv("HOST", "0.0.0.0")
    assert dashboard_bind_host() == "0.0.0.0"

    monkeypatch.setenv("HOST", "   ")
    assert dashboard_bind_host() == "100.1.2.3"


def test_linux_units_do_not_use_macos_paths(tmp_path):
    unit_dir = tmp_path / "systemd"
    setup_schedule(system="Linux", apply=False, systemd_dir=unit_dir)
    blob = "\n".join(p.read_text() for p in unit_dir.iterdir())
    email = (data_dir() / "email.sh").read_text()
    blob += "\n" + email
    assert "/Users/" not in blob
    assert "pyenv" not in blob
    assert "osascript" not in blob
    assert "date -v" not in email
    assert "LaunchAgents" not in blob


def test_package_sources_have_no_hardcoded_mac_paths():
    offenders = []
    for path in PKG.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in ("/Users/", "osascript", ".pyenv"):
            if needle in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {needle}")
    assert offenders == []


def test_darwin_launch_agents_stay_under_library(tmp_path):
    """The Mac installer still targets ~/Library/LaunchAgents, and only on Darwin."""
    agents = tmp_path / "LaunchAgents"
    lines = setup_schedule(system="Darwin", apply=False, launch_agents_dir=agents)
    assert "launchctl not invoked" in "\n".join(lines)
    assert (agents / "com.ai-endurance-coach-over50.daily.plist").is_file()
    assert (agents / "com.ai-endurance-coach-over50.server.plist").is_file()
    assert not list(agents.glob("*.service"))

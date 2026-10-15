"""Non-interactive Garmin MFA must fail clearly, not hang on input()."""
from unittest.mock import MagicMock

import pytest

from ai_endurance_coach_over50.client import GarminAuthError, _prompt_mfa, get_api


def test_prompt_mfa_raises_when_stdin_not_a_tty(monkeypatch):
    monkeypatch.setattr("ai_endurance_coach_over50.client.sys.stdin.isatty", lambda: False)
    with pytest.raises(GarminAuthError, match="no interactive terminal"):
        _prompt_mfa()


def test_get_api_surfaces_mfa_when_non_interactive(monkeypatch, tmp_path):
    monkeypatch.setattr("ai_endurance_coach_over50.client.sys.stdin.isatty", lambda: False)
    monkeypatch.setattr(
        "ai_endurance_coach_over50.client.tokenstore_path",
        lambda: tmp_path / "session",
    )

    class _FakeGarmin:
        def __init__(self, *a, **k):
            self.prompt_mfa = k.get("prompt_mfa")

        def login(self, tokenstore=None):
            raise RuntimeError("MFA code required")

    monkeypatch.setattr("ai_endurance_coach_over50.client.garminconnect.Garmin", _FakeGarmin)
    with pytest.raises(GarminAuthError, match="MFA"):
        get_api("a@b.c", "secret")

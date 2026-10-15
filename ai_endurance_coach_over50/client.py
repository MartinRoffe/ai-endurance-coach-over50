from __future__ import annotations

import logging
import sys

import garminconnect

from .paths import data_dir

logger = logging.getLogger(__name__)


def tokenstore_path():
    """Garmin token directory. Resolved at call time so tests can redirect it."""
    return data_dir() / "session"


class GarminAuthError(RuntimeError):
    """Garmin login needs interaction (MFA) that this process cannot provide."""


def _prompt_mfa() -> str:
    """Ask for MFA only in an interactive terminal; fail clearly otherwise."""
    if not sys.stdin.isatty():
        raise GarminAuthError(
            "Garmin MFA required but this process has no interactive terminal "
            "(scheduled email / systemd / launchd). Run endurance-coach once in a "
            "terminal to refresh the token store, then retry."
        )
    return input("Garmin MFA code: ")


def get_api(email: str, password: str) -> garminconnect.Garmin:
    store = tokenstore_path()
    store.parent.mkdir(parents=True, exist_ok=True)
    api = garminconnect.Garmin(
        email,
        password,
        prompt_mfa=_prompt_mfa,
    )
    # 0.3.x: login(tokenstore=path) loads cached tokens if present,
    # falls back to credentials, and saves new tokens automatically.
    try:
        api.login(tokenstore=str(store))
    except GarminAuthError:
        raise
    except Exception as exc:
        # garminconnect may wrap MFA prompts; surface non-interactive failures.
        msg = str(exc).lower()
        if "mfa" in msg or "multi-factor" in msg or "verification" in msg:
            if not sys.stdin.isatty():
                raise GarminAuthError(
                    "Garmin login needs MFA and this process is non-interactive. "
                    "Run endurance-coach once in a terminal to refresh tokens."
                ) from exc
        raise
    return api

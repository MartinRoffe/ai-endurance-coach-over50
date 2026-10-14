from __future__ import annotations

import logging

import garminconnect

from .paths import data_dir

logger = logging.getLogger(__name__)


def tokenstore_path():
    """Garmin token directory. Resolved at call time so tests can redirect it."""
    return data_dir() / "session"


def get_api(email: str, password: str) -> garminconnect.Garmin:
    store = tokenstore_path()
    store.parent.mkdir(parents=True, exist_ok=True)
    api = garminconnect.Garmin(
        email,
        password,
        prompt_mfa=lambda: input("Garmin MFA code: "),
    )
    # 0.3.x: login(tokenstore=path) loads cached tokens if present,
    # falls back to credentials, and saves new tokens automatically.
    api.login(tokenstore=str(store))
    return api

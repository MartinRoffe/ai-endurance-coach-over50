"""Filesystem locations for the coach's private data directory.

The default is ``~/.ai_endurance_coach_over50``. Set ``ENDURANCE_COACH_HOME``
to point somewhere else (the test suite does this so nothing touches the real
home directory). Read the variable at call time — do not cache the path at
import.
"""
from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    override = os.environ.get("ENDURANCE_COACH_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".ai_endurance_coach_over50"


def dashboard_bind_host() -> str:
    """Address for ``endurance-coach --serve``.

    ``HOST`` wins, then ``COACH_BIND_HOST``, then localhost. Read this after
    dotenv has loaded — an empty value is ignored so a blank line in ``.env``
    does not bind the empty string.
    """
    for key in ("HOST", "COACH_BIND_HOST"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return "127.0.0.1"

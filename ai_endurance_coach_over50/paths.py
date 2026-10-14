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

"""Athlete equipment flags.

``HAS_TURBO`` is the switch for a trainer. It is false until Martin has one.
Weekday bike sessions then resolve to the indoor rower, and weekend rides stay
outdoors. Set the environment variable ``HAS_TURBO=true`` (or change the
default below) to put those weekday sessions back on the bike. The week
tables do not need a second edit.

``HAS_ROWER`` is the switch for an indoor rower. It is false: Martin has no
rower access. Rower sessions then become a shorter MaxiClimber session.
Set ``HAS_ROWER=true`` to put those sessions back on the rower.
"""
from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# No turbo trainer. Weekend rides are outdoors; weekday bike work is on the rower.
HAS_TURBO = _env_bool("HAS_TURBO", False)
# No rower right now. Rower sessions resolve to a shorter MaxiClimber session.
HAS_ROWER = _env_bool("HAS_ROWER", False)


def has_turbo() -> bool:
    """Live read so tests can flip ``settings.HAS_TURBO`` without a rewrite."""
    return bool(HAS_TURBO)


def has_rower() -> bool:
    """Live read so tests can flip ``settings.HAS_ROWER`` without a rewrite."""
    return bool(HAS_ROWER)

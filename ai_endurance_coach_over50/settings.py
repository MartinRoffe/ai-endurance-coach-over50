"""Athlete equipment flags.

``HAS_TURBO`` is the switch for a trainer. It is false: there is no turbo,
and older notes about a smart turbo or Rouvy are wrong. Weekend rides stay
outdoors. Weekday bike sessions on or before 24 Oct 2026 resolve to the
indoor rower. From 25 Oct 2026 there is no rower, so those sessions are
MaxiClimber. Set ``HAS_TURBO=true`` only if a trainer actually exists.
"""
from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# No turbo trainer. Weekend rides are outdoors. From 25 Oct 2026 weekday
# indoor work is the MaxiClimber, not the rower.
HAS_TURBO = _env_bool("HAS_TURBO", False)


def has_turbo() -> bool:
    """Live read so tests can flip ``settings.HAS_TURBO`` without a rewrite."""
    return bool(HAS_TURBO)

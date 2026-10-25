"""Athlete equipment and nutrition display flags.

``HAS_TURBO`` is the switch for a trainer. It is false until Martin has one.
Weekday bike sessions then resolve to the indoor rower, and weekend rides stay
outdoors. Set the environment variable ``HAS_TURBO=true`` (or change the
default below) to put those weekday sessions back on the bike. The week
tables do not need a second edit.

``SHOW_APP_SHOPPING_LIST`` is off. Chef owns the shop. Set
``SHOW_APP_SHOPPING_LIST=true`` to print the app's own list on Nutrition.
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

# Chef owns the shop. The app's own list stays in the page, off unless asked.
SHOW_APP_SHOPPING_LIST = _env_bool("SHOW_APP_SHOPPING_LIST", False)


def has_turbo() -> bool:
    """Live read so tests can flip ``settings.HAS_TURBO`` without a rewrite."""
    return bool(HAS_TURBO)


def show_app_shopping_list() -> bool:
    """Live read so tests can flip ``settings.SHOW_APP_SHOPPING_LIST``."""
    return bool(SHOW_APP_SHOPPING_LIST)

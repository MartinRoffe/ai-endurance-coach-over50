"""Shared server infrastructure: templates, auth, caches, small formatting helpers."""
from __future__ import annotations

import logging
import os
import secrets
import threading

from datetime import date
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import Optional


load_dotenv()

logger = logging.getLogger(__name__)

# In-process AI-text caches. Routes are plain `def` (threadpool workers), so
# guard check-and-generate with a lock — also stops two concurrent page loads
# firing duplicate billable Claude calls for the same date.
_advice_cache: dict[str, str] = {}
_pmc_cache: dict[str, str] = {}
_ai_cache_lock = threading.Lock()

_BIKE_TYPE_KEYS = {"road_biking", "cycling", "virtual_ride", "indoor_cycling", "mountain_biking"}
_HARD_LABELS = {"Tempo Intervals", "FTP Test", "FTP Re-test"}
_HARD_SESSION_TYPES = {"tempo", "ftp", "long"}

QUALITY_BIKE_LABELS = {
    "Tempo Intervals", "Hill Repeats", "Sweetspot Ride", "Over-Unders",
    "Threshold Ride", "FTP Test", "FTP Re-test", "Final FTP Test",
}


# templates/ lives in the package root, one level above server/
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
TEMPLATES.env.filters["format_thousands"] = lambda v: f"{int(v):,}" if v is not None else "—"

_security = HTTPBasic(auto_error=False)

def _require_auth(credentials: Optional[HTTPBasicCredentials] = Depends(_security)) -> None:
    expected_user = os.getenv("DASHBOARD_USER", "")
    expected_pass = os.getenv("DASHBOARD_PASSWORD", "")
    if not expected_user or not expected_pass:
        return  # auth not configured — open access (local-only use)
    if credentials is None or not (
        secrets.compare_digest(credentials.username.encode(), expected_user.encode())
        and secrets.compare_digest(credentials.password.encode(), expected_pass.encode())
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )


_UNSCORED = {"training_load_chronic", "vo2_max"}

_BADGE_STYLES: dict[str, str] = {
    # HRV status
    "BALANCED":   "border-emerald-600 text-emerald-300 bg-emerald-900/30",
    "UNBALANCED": "border-yellow-600 text-yellow-300 bg-yellow-900/30",
    "LOW":        "border-orange-600 text-orange-300 bg-orange-900/30",
    "POOR":       "border-red-600 text-red-300 bg-red-900/30",
    # Training status
    "PRODUCTIVE":    "border-emerald-600 text-emerald-300 bg-emerald-900/30",
    "PEAKING":       "border-emerald-600 text-emerald-300 bg-emerald-900/30",
    "MAINTAINING":   "border-blue-600 text-blue-300 bg-blue-900/30",
    "RECOVERING":    "border-blue-600 text-blue-300 bg-blue-900/30",
    "UNPRODUCTIVE":  "border-yellow-600 text-yellow-300 bg-yellow-900/30",
    "DETRAINING":    "border-orange-600 text-orange-300 bg-orange-900/30",
    "OVERREACHING":  "border-red-600 text-red-300 bg-red-900/30",
    "BELOW TARGET":  "border-yellow-600 text-yellow-300 bg-yellow-900/30",
    # ACWR
    "OPTIMAL":    "border-emerald-600 text-emerald-300 bg-emerald-900/30",
    "HIGH":       "border-orange-600 text-orange-300 bg-orange-900/30",
    "VERY HIGH":  "border-red-600 text-red-300 bg-red-900/30",
}
_DEFAULT_BADGE = "border-slate-600 text-slate-300 bg-slate-800/50"


def _badge_cls(text: str) -> str:
    return _BADGE_STYLES.get(text.upper(), _DEFAULT_BADGE)


def _value_colour(z: Optional[float]) -> str:
    if z is None:
        return "text-white"
    if z >= 1.0:
        return "text-emerald-400"
    if z >= 0.25:
        return "text-green-400"
    if z >= -0.25:
        return "text-yellow-400"
    if z >= -1.0:
        return "text-orange-400"
    return "text-red-400"


def _fmt_dur(seconds: float) -> str:
    m = int(seconds / 60)
    if m < 60:
        return f"{m}m"
    return f"{m // 60}h{m % 60:02d}m" if m % 60 else f"{m // 60}h"


def _fmt_min(minutes: int) -> str:
    if minutes == 0:
        return "—"
    if minutes < 60:
        return f"{minutes}m"
    h, m = divmod(minutes, 60)
    return f"{h}h{m:02d}m" if m else f"{h}h"


def _today() -> date:
    from datetime import date as _date
    return _date.today()


def date_fromisoformat_safe(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return _today()

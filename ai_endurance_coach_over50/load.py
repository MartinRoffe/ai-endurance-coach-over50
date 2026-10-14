"""Session load for caps and alerts.

Foster's session RPE is the preferred load: RPE (1–10) × minutes.
When no RPE is logged, the load stays the duration in minutes so a week
that has not been rated is still comparable with the old minute proxy.

Rucks and hikes then pick up two multipliers:

- pack: +2% load per kilogram carried (20.4 kg → ×1.408)
- vertical gain: +2% load per 100 m climbed (1,000 m → ×1.20)

Both default to 1 when the weight or the climb is unknown.
"""
from __future__ import annotations

import re

RPE_MIN = 1
RPE_MAX = 10

# A logged RPE at or above this, on the 1–10 scale, counts as a hard recent session.
RPE_HIGH = 7

PACK_LOAD_PER_KG = 0.02
VERT_LOAD_PER_100M = 0.02

TERRAIN_TYPES = frozenset({"ruck", "hike", "scramble"})
TERRAIN_ACTIVITY_KEYS = frozenset({
    "hiking", "walking", "trail_running", "rucking", "load_carry",
})

_PACK_KG = re.compile(r"(\d+(?:\.\d+)?)\s*kg", re.IGNORECASE)


def pack_kg_from_label(label: str | None) -> float:
    match = _PACK_KG.search(label or "")
    if not match:
        return 0.0
    return float(match.group(1))


def is_terrain(stype: str | None, label: str | None = None, type_key: str | None = None) -> bool:
    if (stype or "") in TERRAIN_TYPES:
        return True
    if (type_key or "") in TERRAIN_ACTIVITY_KEYS:
        return True
    low = (label or "").lower()
    return "ruck" in low or "pack test" in low or "hill walk" in low or "hike" in low


def foster_load(
    minutes: float,
    rpe: float | None = None,
    *,
    pack_kg: float = 0.0,
    vert_m: float = 0.0,
    terrain: bool = False,
) -> float:
    """RPE × minutes when ``rpe`` is set, otherwise minutes, then terrain factors."""
    if minutes <= 0:
        return 0.0
    base = float(minutes) if rpe is None else float(rpe) * float(minutes)
    if terrain or pack_kg or vert_m:
        base *= 1.0 + PACK_LOAD_PER_KG * max(0.0, float(pack_kg))
        base *= 1.0 + VERT_LOAD_PER_100M * max(0.0, float(vert_m)) / 100.0
    return base


def activity_load(activity: dict, rpe: float | None = None) -> float:
    """Foster load for one logged activity, with pack and climb when present."""
    seconds = activity.get("duration_seconds") or 0
    minutes = float(seconds) / 60.0
    label = activity.get("name") or activity.get("type_label") or ""
    stype = activity.get("type_key") or ""
    terrain = is_terrain(None, label, stype)
    pack = pack_kg_from_label(label) if terrain else 0.0
    vert = activity.get("elevation_gain") or 0.0
    return foster_load(minutes, rpe, pack_kg=pack, vert_m=float(vert or 0), terrain=terrain)


def planned_load(session: tuple | None) -> float:
    """Plan-side load. Uses minutes, plus pack factor when the label carries kg."""
    if not session:
        return 0.0
    stype, label, dur = session[0], session[1], int(session[2] or 0)
    if stype == "rest" or dur <= 0:
        return 0.0
    terrain = is_terrain(stype, label)
    pack = pack_kg_from_label(label) if terrain else 0.0
    return foster_load(dur, None, pack_kg=pack, vert_m=0.0, terrain=terrain)

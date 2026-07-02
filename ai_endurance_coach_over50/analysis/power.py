"""Power enrichment and activity-detail fetching from the Garmin API."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from ..plan import session_for_date_extended
from .db import load_analysis, patch_analysis_power
from .intervals import (
    _CYCLING_TYPES,
    _FTP_SESSION_LABELS,
    _INTERVAL_CONFIG,
    _extract_ftp_effort,
    _extract_interval_data,
    _extract_power_durability,
)


# ── Fetch detail from Garmin API ─────────────────────────────────────────────

def _power_summary_from_activity(activity: dict) -> dict:
    return {
        "avg_power_w":     activity.get("avg_power_w"),
        "max_power_w":     activity.get("max_power_w"),
        "norm_power_w":    activity.get("norm_power_w"),
        "has_power_meter": bool(activity.get("has_power_meter")),
    }


def _power_summary_from_dto(s: dict) -> dict:
    avg = s.get("averagePower")
    max_p = s.get("maxPower")
    np = s.get("normativePower") or s.get("normalizedPower")
    has_pm = s.get("hasPowerMeter")
    if has_pm is None:
        if avg is not None:
            has_pm = float(avg) > 0
        elif max_p is not None:
            has_pm = float(max_p) > 0
    return {
        "avg_power_w":     round(float(avg)) if avg is not None else None,
        "max_power_w":     round(float(max_p)) if max_p is not None else None,
        "norm_power_w":    round(float(np)) if np is not None else None,
        "has_power_meter": bool(has_pm),
    }


def activity_has_power_signal(act: dict) -> bool:
    return bool(act.get("has_power_meter") or act.get("avg_power_w") or act.get("max_power_w"))


def activity_needs_power_enrichment(act: dict) -> bool:
    if act.get("type_key") not in _CYCLING_TYPES:
        return False
    if not activity_has_power_signal(act):
        return False
    return (
        act.get("avg_power_w") is None
        or act.get("norm_power_w") is None
        or not act.get("has_power_meter")
    )


def _fetch_power_summary_from_api(api: Any, activity_id: int) -> dict:
    summary_raw = api.get_activity(activity_id)
    return _power_summary_from_dto(summary_raw.get("summaryDTO", {}))


def enrich_activities_power(api: Any, activities: list[dict]) -> int:
    """Fill missing avg/NP from Garmin detail API; patch analysis power zones."""
    from ..history import patch_activity_power

    enriched = 0
    for act in activities:
        if not activity_needs_power_enrichment(act):
            continue
        act_id = act["activity_id"]
        try:
            power = _fetch_power_summary_from_api(api, act_id)
            if not power.get("has_power_meter") and not power.get("avg_power_w"):
                continue
            patch_fields = {
                "avg_power_w": power.get("avg_power_w"),
                "max_power_w": power.get("max_power_w") or act.get("max_power_w"),
                "norm_power_w": power.get("norm_power_w"),
                "has_power_meter": 1 if power.get("has_power_meter") else act.get("has_power_meter"),
            }
            if not patch_activity_power(act_id, patch_fields):
                continue
            act.update(patch_fields)
            enriched += 1

            existing = load_analysis(act_id)
            if existing and existing.get("power_zones_json"):
                continue
            detail = fetch_activity_detail(
                api, act_id, activity=act, session_label=_session_label_for_activity(act),
            )
            if existing and detail.get("power_zones"):
                patch_analysis_power(act_id, detail)
        except Exception:
            pass
    return enriched


def sync_power_data(api: Any, days: int = 14) -> dict:
    """Enrich incomplete power fields and backfill zones on recent cycling rides."""
    from ..history import load_recent_activities

    activities = load_recent_activities(days=days)
    enriched = enrich_activities_power(api, activities)
    return {"enriched": enriched, "checked": len(activities)}


def _fetch_power_zones(api: Any, activity_id: int) -> list[dict]:
    """Return per-zone seconds from Garmin power time-in-zones endpoint."""
    import logging
    _log = logging.getLogger(__name__)
    try:
        raw = api.get_activity_power_in_timezones(activity_id)
    except Exception as e:
        _log.debug("Power zones fetch failed: %s", e)
        return []
    if not raw:
        return []
    if isinstance(raw, list):
        zones_list = raw
    elif isinstance(raw, dict):
        zones_list = raw.get("timeInZoneDTOList") or raw.get("zones") or []
        if not zones_list and raw.get("secsInZone") is not None:
            zones_list = [raw]
    else:
        return []
    if not zones_list:
        return []
    total_secs = sum(z.get("secsInZone", 0) for z in zones_list) or 1
    return [
        {
            "zone":  z.get("zoneNumber") or z.get("zone"),
            "secs":  round(z.get("secsInZone", 0)),
            "pct":   round(z.get("secsInZone", 0) / total_secs * 100),
            "low_w": z.get("zoneLowBoundary"),
        }
        for z in sorted(zones_list, key=lambda x: x.get("zoneNumber") or x.get("zone") or 0)
    ]


def fetch_activity_detail(api: Any, activity_id: int, activity: Optional[dict] = None,
                          session_label: Optional[str] = None) -> dict:
    """Return a merged dict of activity summary + HR zones.

    Uses inline fields from the activity row when available (avoids two extra
    API calls). Falls back to API for activities saved before the new columns.
    For FTP test sessions, additionally fetches lap splits to extract the
    20-min effort HR.
    """
    if activity and activity.get("hr_zone_1_sec") is not None:
        total_secs = sum(activity.get(f"hr_zone_{z}_sec") or 0 for z in range(1, 6)) or 1
        hr_zones = [
            {
                "zone": z,
                "secs": round(activity.get(f"hr_zone_{z}_sec") or 0),
                "pct": round((activity.get(f"hr_zone_{z}_sec") or 0) / total_secs * 100),
                "low_bpm": None,
            }
            for z in range(1, 6)
        ]
        result = {
            "training_effect":       activity.get("aerobic_te"),
            "training_effect_label": activity.get("training_effect_label"),
            "aerobic_te_message":    None,
            "anaerobic_te":          activity.get("anaerobic_te"),
            "training_load":         activity.get("training_load"),
            "avg_respiration":       activity.get("avg_respiration"),
            "hr_zones":              hr_zones,
        }
        result.update(_power_summary_from_activity(activity))
        if activity_needs_power_enrichment(activity):
            try:
                result.update(_fetch_power_summary_from_api(api, activity_id))
            except Exception:
                pass
        if result.get("has_power_meter"):
            result["power_zones"] = _fetch_power_zones(api, activity_id)
        if session_label in _FTP_SESSION_LABELS:
            result.update(_extract_ftp_effort(api, activity_id))
        elif session_label in _INTERVAL_CONFIG:
            result.update(_extract_interval_data(api, activity_id, session_label,
                                                 activity.get("type_key") if activity else None))
        return result

    summary_raw = api.get_activity(activity_id)
    s = summary_raw.get("summaryDTO", {})

    hr_zones_raw = api.get_activity_hr_in_timezones(activity_id)
    total_secs = sum(z.get("secsInZone", 0) for z in hr_zones_raw) or 1
    hr_zones = [
        {
            "zone": z["zoneNumber"],
            "secs": round(z["secsInZone"]),
            "pct": round(z["secsInZone"] / total_secs * 100),
            "low_bpm": z.get("zoneLowBoundary"),
        }
        for z in sorted(hr_zones_raw, key=lambda x: x["zoneNumber"])
    ]

    result = {
        "training_effect":       s.get("trainingEffect"),
        "training_effect_label": s.get("trainingEffectLabel"),
        "aerobic_te_message":    s.get("aerobicTrainingEffectMessage"),
        "anaerobic_te":          s.get("anaerobicTrainingEffect"),
        "training_load":         s.get("activityTrainingLoad"),
        "avg_respiration":       s.get("avgRespirationRate"),
        "hr_zones":              hr_zones,
    }
    result.update(_power_summary_from_dto(s))
    if result.get("has_power_meter"):
        result["power_zones"] = _fetch_power_zones(api, activity_id)
    if session_label in _FTP_SESSION_LABELS:
        result.update(_extract_ftp_effort(api, activity_id))
    elif session_label in _INTERVAL_CONFIG:
        result.update(_extract_interval_data(api, activity_id, session_label,
                                                 activity.get("type_key") if activity else None))
    return result


def _session_label_for_activity(act: dict) -> Optional[str]:
    act_date = act.get("date")
    if not act_date:
        return None
    try:
        sess = session_for_date_extended(date.fromisoformat(act_date))
        return sess[1] if sess else None
    except Exception:
        return None


def _try_save_ftp_from_detail(act: dict, detail: dict, session_label: Optional[str]) -> bool:
    """Seed ftp_tests.ftp_w from an FTP-labelled session when not already logged."""
    if session_label not in _FTP_SESSION_LABELS or not detail.get("ftp_effort_avg_hr"):
        return False
    act_date = act.get("date")
    if not act_date:
        return False
    try:
        from ..history import save_ftp_test, load_ftp_tests
        d_obj = date.fromisoformat(act_date)
        if any(t["date"] == d_obj.isoformat() for t in load_ftp_tests()):
            return False
        ftp_w = detail.get("ftp_w")
        if not ftp_w and detail.get("ftp_effort_avg_w"):
            ftp_w = round(detail["ftp_effort_avg_w"] * 0.95)
        save_ftp_test(
            d_obj.isoformat(), act["activity_id"],
            int(detail["ftp_effort_avg_hr"]),
            int(detail["ftp_effort_max_hr"]) if detail.get("ftp_effort_max_hr") else None,
            None,
            ftp_w=ftp_w,
        )
        return True
    except Exception:
        return False


def refresh_power_backfill(api: Any, days: int = 30) -> dict:
    """Phase 6 workflow: re-fetch activities, mine power zones/decoupling on historical rides."""
    from ..metrics import fetch_activities
    from .generate import refresh_analyses
    from ..history import (
        load_activities_by_date,
        power_durability_exists,
        save_activities,
        save_power_durability,
    )

    stats = {
        "days": days,
        "activities_fetched": 0,
        "power_rides": 0,
        "durability_added": 0,
        "power_patched": 0,
        "ftp_seeded": 0,
    }

    acts = fetch_activities(api, days=days)
    save_activities(acts)
    stats["activities_fetched"] = len(acts)
    enrich_activities_power(api, acts)

    start = date.today() - timedelta(days=days - 1)
    power_acts: list[dict] = []
    for _d, day_acts in load_activities_by_date(start, date.today()).items():
        for act in day_acts:
            if activity_has_power_signal(act) and act.get("type_key") in _CYCLING_TYPES:
                power_acts.append(act)
    stats["power_rides"] = len(power_acts)

    for act in power_acts:
        act_id = act["activity_id"]
        if ((act.get("duration_seconds") or 0) >= 90 * 60
                and not power_durability_exists(act_id)):
            try:
                pd_row = _extract_power_durability(api, act)
                if pd_row:
                    save_power_durability(act_id, pd_row)
                    stats["durability_added"] += 1
            except Exception:
                pass

        session_label = _session_label_for_activity(act)
        try:
            detail = fetch_activity_detail(
                api, act_id, activity=act, session_label=session_label,
            )
            existing = load_analysis(act_id)
            if existing:
                needs_zones = not existing.get("power_zones_json") and detail.get("power_zones")
                needs_w = not existing.get("ftp_effort_avg_w") and detail.get("ftp_effort_avg_w")
                if needs_zones or needs_w or detail.get("interval_reps"):
                    if patch_analysis_power(act_id, detail):
                        stats["power_patched"] += 1
                if _try_save_ftp_from_detail(act, detail, session_label):
                    stats["ftp_seeded"] += 1
        except Exception:
            pass

    refresh_analyses(api, days=days)
    return stats

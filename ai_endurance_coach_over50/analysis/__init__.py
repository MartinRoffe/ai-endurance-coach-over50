"""Post-training analysis: fetch activity detail from Garmin and generate Claude commentary.

Facade package: every name that used to live in the single-file analysis.py is
re-exported here so callers keep doing ``from .analysis import X`` unchanged.
Tests that monkeypatch analysis functions must target the defining sub-module
(e.g. ``analysis.power.fetch_activity_detail``), not this facade.
"""
from .db import (  # noqa: F401
    _ensure_analysis_schema,
    load_analysis,
    patch_analysis_power,
    save_detail,
)
from .intervals import (  # noqa: F401
    _CLIMBING_INTERVAL_LABELS,
    _CLIMBING_TYPES,
    _CYCLING_TYPES,
    _FTP_FALLBACK_LABELS,
    _FTP_SESSION_LABELS,
    _INTERVAL_CONFIG,
    _INTERVAL_PRESCRIBED,
    _NONWORK_INTENSITIES,
    _RAMP_SESSION_LABELS,
    _WORK_INTENSITIES,
    _drop_stubs,
    _extract_durability,
    _extract_ftp_effort,
    _extract_interval_data,
    _extract_power_durability,
    _ftp_effort_from_summary,
    _lap_dur,
    _lap_power,
    _merge_same_step_laps,
    _work_laps_from_steps,
    estimate_lthr_from_effort,
)
from .power import (  # noqa: F401
    _fetch_power_summary_from_api,
    _fetch_power_zones,
    _power_summary_from_activity,
    _power_summary_from_dto,
    _session_label_for_activity,
    _try_save_ftp_from_detail,
    activity_has_power_signal,
    activity_needs_power_enrichment,
    enrich_activities_power,
    fetch_activity_detail,
    refresh_power_backfill,
    sync_power_data,
)
from .prompts import (  # noqa: F401
    _DUAL_CHANNEL_SYSTEM,
    _RUCK_TYPES,
    _RUNNING_TYPES,
    _activity_has_power_data,
    _build_analysis_prompt,
    _coach_system_prompt,
    _fmt_secs,
    _rule_based_analysis,
    _rule_based_recovery,
    _te_label,
)
from .generate import (  # noqa: F401
    _find_compound_companion,
    generate_analysis,
    generate_recovery_suggestion,
    load_analyses_for_activities,
    refresh_analyses,
    retrieve_relevant_analyses,
)
from .prefetch import (  # noqa: F401
    _FUEL_MIN_DURATION,
    _FUEL_TYPES,
    _SESSION_TYPE_DESC,
    _STEP_SUMMARIES,
    _ensure_fuelling_schema,
    _ensure_nutrition_schema,
    _ensure_workout_desc_schema,
    _load_fuelling_plans,
    _load_nutrition_targets,
    _load_workout_descs,
    default_fuelling_plan,
    fuelling_session_key,
    prefetch_fuelling_plans,
    prefetch_nutrition_targets,
    prefetch_workout_descriptions,
)
from .stage_plans import (  # noqa: F401
    HR_STAGE_PLAN_CACHE_VER,
    _PEAK_DECOUPLING_THRESHOLD,
    generate_charity_day_plans,
    generate_hr_stage_plans,
    peak_sim_decoupling_flags,
)

"""SQLite persistence, baseline statistics, and z-score calculations.

Facade package: every name that used to live in the single-file history.py is
re-exported here so callers keep doing ``from .history import X`` unchanged.

NOTE: tests must patch ``history.db.DB_PATH`` (not ``history.DB_PATH``) — the
package-level re-export is a snapshot that ``_conn()`` never reads.
"""
from .db import (  # noqa: F401
    DB_PATH,
    NUMERIC_FIELDS,
    _ACTIVITY_COLS,
    _conn,
    _ensure_activities_schema,
    _ensure_blood_pressure_schema,
    _ensure_body_metrics_schema,
    _ensure_btb_schema,
    _ensure_coach_memory_schema,
    _ensure_coach_schema,
    _ensure_durability_schema,
    _ensure_ftp_schema,
    _ensure_fuelling_log_schema,
    _ensure_power_durability_schema,
    _ensure_rpe_schema,
    _ensure_schema,
)
from .text_cache import (  # noqa: F401
    delete_advice,
    get_cached_text,
    load_advice,
    save_advice,
    set_cached_text,
)
from .metrics_store import (  # noqa: F401
    HIGHER_IS_BETTER,
    LOWER_IS_BETTER,
    SCORED_FIELDS,
    _UNSCORED,
    _stats_from_rows,
    baseline_stats,
    composite_score,
    field_baseline,
    history_for_chart,
    load,
    raw_history,
    save,
    seven_day_composite_trend_csv,
    sleep_history,
    z_score,
)
from .activities_store import (  # noqa: F401
    ACTIVITY_MATCH,
    _ZONE_BIKE_KEYS,
    load_activities_by_date,
    load_recent_activities,
    patch_activity_power,
    save_activities,
    zone_distribution,
)
from .body_store import (  # noqa: F401
    _weight_kg_on_date,
    estimated_wkg_history,
    latest_bmr,
    latest_estimated_wkg,
    latest_lean_mass_kg,
    latest_measured_wkg,
    latest_weight_kg,
    load_blood_pressure,
    load_body_metrics,
    measured_wkg_history,
    pmc_history,
    save_blood_pressure,
    save_body_metrics,
    tdee_history,
    vo2_history,
)
from .coach_store import (  # noqa: F401
    clear_coach_history,
    delete_plan_override,
    get_coach_memory,
    get_plan_override,
    list_plan_overrides,
    load_coach_history,
    load_session_rpe,
    save_coach_message,
    save_session_rpe,
    set_coach_memory,
    set_plan_override,
)
from .training_store import (  # noqa: F401
    _BTB_BIKE_KEYS,
    acclimation_latest,
    count_power_rides,
    durability_exists,
    ftp_retest_due,
    gut_training_summary,
    intensity_distribution_by_week,
    intensity_distribution_by_week_power,
    load_btb_summary,
    load_durability,
    load_fuelling_logs,
    load_ftp_tests,
    load_power_durability,
    power_activation_status,
    power_durability_exists,
    power_meter_active,
    save_btb_note,
    save_durability,
    save_ftp_test,
    save_fuelling_log,
    save_power_durability,
    weekly_monotony_strain,
)

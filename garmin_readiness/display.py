from __future__ import annotations

from typing import Optional


FIELD_LABELS: dict[str, tuple[str, str]] = {
    # field: (display name, unit)
    "sleep_score":           ("Sleep Score",          "/100"),
    "sleep_seconds":         ("Sleep Duration",       ""),
    "hrv_last_night":        ("HRV Last Night",       " ms"),
    "hrv_weekly_avg":        ("HRV Weekly Avg",       " ms"),
    "body_battery_morning":  ("Body Battery",         "/100"),
    "avg_stress":            ("Avg Stress",           "/100"),
    "rest_stress":           ("Rest Stress",          "/100"),
    "acwr":                  ("Acute:Chronic Ratio",  ""),
    "training_load_acute":   ("Acute Load (7d)",      ""),
    "training_load_chronic": ("Chronic Load (28d)",   ""),
    "vo2_max":               ("VO2 Max",              " ml/kg/min"),
}


def fmt_value(field: str, value: Optional[float]) -> str:
    if value is None:
        return "—"
    if field == "sleep_seconds":
        h, rem = divmod(int(value), 3600)
        m = rem // 60
        return f"{h}h {m:02d}m"
    if field in ("sleep_score", "body_battery_morning", "avg_stress", "rest_stress"):
        return f"{value:.0f}"
    if field in ("hrv_last_night", "hrv_weekly_avg", "vo2_max"):
        return f"{value:.1f}"
    if field == "acwr":
        return f"{value:.2f}"
    if field in ("training_load_acute", "training_load_chronic"):
        return f"{value:.0f}"
    return f"{value:.1f}"


def readiness_label(z: Optional[float]) -> tuple[str, str]:
    """Returns (label, css_colour_class) for the composite z-score."""
    if z is None:
        return "Building baseline…", "text-zinc-400"
    if z >= 1.0:
        return "Above Average", "text-emerald-400"
    if z >= 0.25:
        return "Good", "text-green-400"
    if z >= -0.25:
        return "Average", "text-yellow-400"
    if z >= -1.0:
        return "Below Average", "text-orange-400"
    return "Low", "text-red-400"

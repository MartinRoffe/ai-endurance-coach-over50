"""Proactive fatigue alert checks."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import statistics
from datetime import date, timedelta
from typing import Optional

from .energy import (
    EA_WARN_KCAL_PER_KG_FFM,
    MUSCLE_DROP_KG,
    MUSCLE_DROP_MIN_DAYS,
    MUSCLE_DROP_MIN_READINGS,
    energy_availability,
    fat_free_mass_kg,
    weight_trend_kg_per_day,
)
from .history import (
    history_for_chart,
    load,
    load_activities_by_date,
    load_body_metrics,
    load_ftp_tests,
    load_session_rpe,
    pmc_history,
    raw_history,
    weekly_monotony_strain,
)
from .load import activity_load, planned_load
from .modulation import assess_hrv_ln
from .plan import session_for_date
from .wkg_projection import performance_guard


def _signal_z(rows: list[dict], field: str) -> Optional[float]:
    """Z-score of today's value for `field` vs its own baseline (all prior rows).

    Returns None (signal abstains) when today's value is missing, fewer than
    7 baseline samples exist, or the baseline has no variance.
    """
    today_val = rows[-1].get(field) if rows else None
    if today_val is None:
        return None
    baseline = [r.get(field) for r in rows[:-1] if r.get(field) is not None]
    if len(baseline) < 7:
        return None
    stdev = statistics.pstdev(baseline)
    if stdev == 0:
        return None
    return (today_val - statistics.mean(baseline)) / stdev


def check_fatigue_alerts(today: date) -> list[dict]:
    alerts: list[dict] = []

    # 1. HRV_TREND: 4 consecutive mornings of declining HRV
    rows = raw_history(5)
    hrv_vals = [r["hrv_last_night"] for r in rows if r.get("hrv_last_night") is not None]
    if len(hrv_vals) >= 4:
        last4 = hrv_vals[-4:]
        if all(last4[i] < last4[i - 1] for i in range(1, 4)):
            alerts.append({
                "type": "HRV_TREND",
                "severity": "HIGH",
                "message": (
                    f"HRV has declined for 4 consecutive mornings "
                    f"({last4[0]:.0f} → {last4[-1]:.0f} ms). "
                    "Consider reducing today's intensity."
                ),
            })

    # 2. TSB_DEEP: TSB below -180 for 5+ of the last 6 days
    hist = pmc_history(days=6)
    tsb_vals = [h["tsb"] for h in hist if h.get("tsb") is not None]
    if sum(1 for v in tsb_vals if v < -180) >= 5:
        alerts.append({
            "type": "TSB_DEEP",
            "severity": "HIGH",
            "message": (
                "Form (TSB) has been very negative for 5+ days. "
                "A rest or recovery day is overdue."
            ),
        })

    # 3. VOLUME_SPIKE: actual this week >20% over planned.
    # Foster load (RPE × minutes, with pack and climb factors) when an RPE
    # is logged; otherwise minutes, still with those factors on rucks and hikes.
    mon = today - timedelta(days=today.weekday())
    planned_load_sum = 0.0
    for i in range(7):
        planned_load_sum += planned_load(session_for_date(mon + timedelta(days=i)))

    if planned_load_sum > 0:
        acts_this_week = load_activities_by_date(mon, today)
        rpe_by_id: dict[str, int] = {}
        try:
            for row in load_session_rpe(14):
                if row.get("activity_id") is not None and row.get("rpe") is not None:
                    rpe_by_id[str(row["activity_id"])] = int(row["rpe"])
        except Exception:
            logger.warning("check_fatigue_alerts RPE lookup failed", exc_info=True)
        actual_load = 0.0
        used_rpe = False
        for day_acts in acts_this_week.values():
            for act in day_acts:
                rpe = rpe_by_id.get(str(act.get("activity_id")))
                if rpe is not None:
                    used_rpe = True
                actual_load += activity_load(act, rpe)
        if actual_load > planned_load_sum * 1.20:
            unit = "Foster load" if used_rpe else "load"
            alerts.append({
                "type": "VOLUME_SPIKE",
                "severity": "MODERATE",
                "message": (
                    f"You're tracking {round((actual_load / planned_load_sum - 1) * 100)}% over planned {unit} this week "
                    f"({actual_load:.0f} vs {planned_load_sum:.0f} planned). Protect the rest of the week."
                ),
            })

    # 4. ILLNESS_RISK: 2-of-3 — depressed HRV, elevated resting HR (or rest
    #    stress as fallback), degraded sleep. Distinct from fatigue: the
    #    intervention is full rest, not just easier training.
    rows31 = raw_history(31)
    # Only evaluate when the latest row really is `today` — before the watch
    # syncs, rows31[-1] is yesterday and we'd report stale values as today's.
    if rows31 and rows31[-1].get("date") == today.isoformat():
        hrv_state = assess_hrv_ln(rows31, today.isoformat(), rows31[-1].get("hrv_last_night"))
        rhr_z = _signal_z(rows31, "resting_hr")
        if rhr_z is None:
            rhr_z = _signal_z(rows31, "rest_stress")  # fallback signal
        sleep_z = _signal_z(rows31, "sleep_score")

        triggers = []
        today_row = rows31[-1]
        if hrv_state and hrv_state["below_band"]:
            from .modulation import _hrv_reason
            triggers.append(_hrv_reason(hrv_state))
        if rhr_z is not None and rhr_z > 1.5:
            if today_row.get("resting_hr") is not None:
                triggers.append(f"resting HR {today_row['resting_hr']:.0f} bpm ({rhr_z:+.1f}σ)")
            else:
                triggers.append(f"resting stress elevated ({rhr_z:+.1f}σ)")
        if sleep_z is not None and sleep_z < -1.5:
            triggers.append(f"sleep score {today_row['sleep_score']:.0f} ({sleep_z:+.1f}σ)")

        if len(triggers) >= 2:
            alerts.append({
                "type": "ILLNESS_RISK",
                "severity": "HIGH",
                "message": (
                    "Possible illness onset: " + ", ".join(triggers) + ". "
                    "Consider full rest (not just an easy spin) and monitor temperature."
                ),
            })

    # 5. MONOTONY_HIGH: Foster monotony > 2.0 in the most recent meaningful week
    try:
        ms = weekly_monotony_strain(weeks=2)
        recent = None
        for wk in reversed(ms):
            elapsed = (today - wk["week_start"]).days + 1
            if elapsed >= 4 and wk.get("monotony") is not None:
                recent = wk
                break
        if recent and recent["monotony"] > 2.0:
            alerts.append({
                "type": "MONOTONY_HIGH",
                "severity": "MODERATE",
                "message": (
                    f"Training monotony is {recent['monotony']:.1f} (>2.0) with strain "
                    f"{recent['strain']:.0f} — too-similar daily loads raise illness/overuse "
                    "risk. Make hard days harder and easy days easier."
                ),
            })
    except Exception:
        logger.warning("check_fatigue_alerts failed", exc_info=True)

    # 6. WEIGHT_PERFORMANCE: weight loss appears to be costing performance —
    #    the race-weight discovery signal (falling FTP watts and/or a sustained
    #    readiness-composite sag while still cutting weight).
    try:
        readings = [
            (r["date"], r["weight_kg"])
            for r in load_body_metrics(90)
            if r.get("weight_kg")
        ]
        weight_slope = weight_trend_kg_per_day(readings)
        comp_z_series = [c for (_d, c) in history_for_chart(14)]
        guard = performance_guard(load_ftp_tests(), weight_slope, comp_z_series)
        if guard["firing"]:
            alerts.append({
                "type": "WEIGHT_PERFORMANCE",
                "severity": "MODERATE",
                "message": (
                    "Weight loss may be costing performance: "
                    + "; ".join(guard["reasons"]) + ". "
                    "You may be near your effective race weight — hold at "
                    "maintenance for 2-3 weeks and re-test."
                ),
            })
    except Exception:
        logger.warning("check_fatigue_alerts failed", exc_info=True)

    # 7. LOW_EA: intake minus exercise kcal, per kg of fat-free mass, under 30.
    try:
        metrics = load(today)
        readings = load_body_metrics(30)
        latest = readings[-1] if readings else None
        if metrics is not None and latest is not None:
            ffm = fat_free_mass_kg(latest.get("weight_kg"), latest.get("fat_pct"))
            ea = energy_availability(
                metrics.calories_consumed,
                metrics.active_calories,
                ffm,
            )
            if ea is not None and ea < EA_WARN_KCAL_PER_KG_FFM:
                alerts.append({
                    "type": "LOW_EA",
                    "severity": "HIGH",
                    "message": (
                        f"Energy availability is {ea:.0f} kcal/kg fat-free mass "
                        f"(below {EA_WARN_KCAL_PER_KG_FFM:.0f}). Eat more today, "
                        "especially carbohydrate, and do not push the deficit."
                    ),
                })
    except Exception:
        logger.warning("check_fatigue_alerts failed", exc_info=True)

    # 8. MUSCLE_DOWN: scale muscle mass trending down across the cut.
    try:
        points = []
        for row in load_body_metrics(60):
            if row.get("muscle_mass_kg") is None:
                continue
            points.append((date.fromisoformat(row["date"]), float(row["muscle_mass_kg"])))
        if len(points) >= MUSCLE_DROP_MIN_READINGS:
            span = (points[-1][0] - points[0][0]).days
            early = points[: max(1, len(points) // 2)]
            late = points[len(points) // 2 :]
            early_mean = sum(v for _, v in early) / len(early)
            late_mean = sum(v for _, v in late) / len(late)
            if span >= MUSCLE_DROP_MIN_DAYS and early_mean - late_mean >= MUSCLE_DROP_KG:
                alerts.append({
                    "type": "MUSCLE_DOWN",
                    "severity": "HIGH",
                    "message": (
                        f"Muscle mass is down {early_mean - late_mean:.1f} kg "
                        f"across {span} days ({early_mean:.1f} → {late_mean:.1f} kg). "
                        "Hold the protein floor and ease the deficit until it stabilises."
                    ),
                })
    except Exception:
        logger.warning("check_fatigue_alerts failed", exc_info=True)

    return alerts

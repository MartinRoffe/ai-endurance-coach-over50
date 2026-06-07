"""Proactive fatigue alert checks."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .history import load_activities_by_date, pmc_history, raw_history
from .plan import session_for_date


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

    # 3. VOLUME_SPIKE: actual this week >20% over planned
    mon = today - timedelta(days=today.weekday())
    planned_min = 0
    for i in range(7):
        sess = session_for_date(mon + timedelta(days=i))
        if sess and sess[0] != "rest" and sess[2]:
            planned_min += sess[2]

    if planned_min > 0:
        acts_this_week = load_activities_by_date(mon, today)
        actual_min = sum(
            int((a.get("duration_seconds") or 0) / 60)
            for day_acts in acts_this_week.values()
            for a in day_acts
        )
        if actual_min > planned_min * 1.20:
            planned_h = planned_min / 60
            actual_h = actual_min / 60
            alerts.append({
                "type": "VOLUME_SPIKE",
                "severity": "MODERATE",
                "message": (
                    f"You're tracking {round((actual_min / planned_min - 1) * 100)}% over planned volume this week "
                    f"({actual_h:.1f}h vs {planned_h:.1f}h planned). Protect the rest of the week."
                ),
            })

    return alerts

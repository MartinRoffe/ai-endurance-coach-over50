"""Analysis prompt builders, coach system prompts, and rule-based fallbacks."""
from __future__ import annotations

from datetime import date
from typing import Optional

from ..coach_voice import COACH_VOICE, hr_channel_note
from ..plan import COMPOUND_SESSIONS, maxi_target_zone, session_for_date_extended
from .intervals import _CYCLING_TYPES


def _fmt_secs(s: int) -> str:
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{sec:02d}s"


def _te_label(label: Optional[str]) -> str:
    if not label:
        return "unknown"
    return label.replace("_", " ").title()


_RUNNING_TYPES = {"running", "trail_running", "treadmill_running"}
_RUCK_TYPES    = {"hiking", "walking", "load_carry", "rucking"}


_DUAL_CHANNEL_SYSTEM = (
    "Dual-channel coaching (2012 Haute Route lessons — now with real strain-gauge power): "
    "power for instant objective intensity, pacing ceilings on climbs (cap, not target), and "
    "interval execution; HR + readiness for fatigue, heat, altitude, and cardiac drift. "
    "Pw:HR decoupling matters — HR rising while power is flat or falling is an early fade warning. "
    "Distinguish late-ride patterns carefully: (1) heat cardiac drift = power held roughly steady "
    "while HR rises in >25 °C — expected physiology, not an aerobic deficiency; "
    "(2) fuel/glycogen fade = final-third power down materially (≥~8–10%) while HR stays high "
    "or rises — treat as under-fuelling / empty legs, not 'just heat', and do not call the ride "
    "a clean successful Zone 2 long if the last third collapsed. "
    "When HR and power disagree, say which channel you trust and why: with measured FTP on record, "
    "prefer absolute watts / NP / %FTP for intensity and HR/drift for fatigue, heat, durability, "
    "and fuelling — do not default to 'power zones are wrong'. "
    "If HR data looks corrupt (flat avg=max, or 0% in all HR zones) but power zones are present, "
    "base intensity assessment on power and flag the HR sensor issue."
)

# Final-third power drop that usually means empty legs, not mild heat drift.
_FUEL_FADE_POWER_DROP_PCT = -8.0
_HEAT_TEMP_C = 25.0


def classify_late_ride_fade(
    power_drift_pct: float | None,
    hr_drift_pct: float | None,
    max_temp_c: float | None = None,
) -> str | None:
    """Classify late-ride Pw:HR pattern for analysis prompts.

    Returns ``\"fuel_fade\"``, ``\"heat_drift\"``, or None when the signal is weak/ambiguous.
    """
    if power_drift_pct is None or hr_drift_pct is None:
        return None
    # Power collapsing while HR holds or rises → glycogen / under-fuelling pattern.
    if power_drift_pct <= _FUEL_FADE_POWER_DROP_PCT and hr_drift_pct >= -2.0:
        return "fuel_fade"
    # Power roughly held, HR up, hot day → expected cardiac drift.
    hot = max_temp_c is not None and max_temp_c >= _HEAT_TEMP_C
    if hot and abs(power_drift_pct) < 5.0 and hr_drift_pct > 5.0:
        return "heat_drift"
    return None


def _max_temp_c(activity: dict) -> float | None:
    raw = activity.get("max_temperature")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _durability_coaching_lines(pd_row: dict, max_temp_c: float | None) -> list[str]:
    """Expand power-durability row into prompt lines with fade interpretation."""
    sign = lambda v: f"{float(v):+.1f}"
    lines = [
        f"Pw:HR decoupling: {sign(pd_row['decoupling_pct'])}% "
        f"(HR drift {sign(pd_row.get('hr_drift_pct') or 0)}%, "
        f"power drift {sign(pd_row.get('power_drift_pct') or 0)}%)"
    ]
    first_p = pd_row.get("first_third_power")
    final_p = pd_row.get("final_third_power")
    first_hr = pd_row.get("first_third_hr")
    final_hr = pd_row.get("final_third_hr")
    if first_p is not None and final_p is not None:
        hr_bit = ""
        if first_hr is not None and final_hr is not None:
            hr_bit = f", HR {float(first_hr):.0f}→{float(final_hr):.0f} bpm"
        lines.append(
            f"Thirds: first {float(first_p):.0f} W → final {float(final_p):.0f} W{hr_bit}"
        )
    kind = classify_late_ride_fade(
        pd_row.get("power_drift_pct"),
        pd_row.get("hr_drift_pct"),
        max_temp_c,
    )
    if kind == "fuel_fade":
        lines.append(
            "Fade pattern: FUEL/GLYCOGEN — final-third power fell hard while HR stayed elevated. "
            "Do NOT dismiss as heat alone. Call out under-fuelling / empty legs as the primary "
            "late-ride failure mode; heat may have contributed but did not cause the power collapse."
        )
    elif kind == "heat_drift":
        lines.append(
            "Fade pattern: HEAT CARDIAC DRIFT — power was held while HR rose in the heat. "
            "Treat as expected heat physiology, not an aerobic fitness deficiency."
        )
    return lines


def _fuelling_context_lines(
    activity: dict,
    *,
    fuel_fade: bool = False,
) -> list[str]:
    """Inject planned/actual in-ride carbs when available; warn when long + fade + unknown."""
    act_id = activity.get("activity_id")
    act_date = activity.get("date") or ""
    dur_secs = int(activity.get("duration_seconds") or 0)
    dur_min = dur_secs // 60
    if dur_min < 75:
        return []

    planned = None
    actual = None
    fluid_ok = None
    note = None
    try:
        from ..history import load_fuelling_logs
        logs = load_fuelling_logs(120)
        match = None
        if act_id is not None:
            match = next(
                (r for r in logs if r.get("activity_id") is not None
                 and int(r["activity_id"]) == int(act_id)),
                None,
            )
        if match is None and act_date:
            match = next((r for r in logs if r.get("date") == act_date), None)
        if match:
            planned = match.get("planned_carbs_g_per_hr")
            actual = match.get("actual_carbs_g_per_hr")
            fluid_ok = bool(match.get("fluid_ok"))
            note = match.get("note")
    except Exception:
        pass

    if planned is None and act_date:
        try:
            from ..nutrition_plan import gut_training_target_g_per_hr
            d_obj = date.fromisoformat(act_date)
            planned = gut_training_target_g_per_hr(d_obj) if dur_min >= 150 else 55
        except Exception:
            planned = 90 if dur_min >= 150 else 55

    lines: list[str] = []
    if actual is not None:
        plan_bit = f" (plan target ~{float(planned):.0f} g/h)" if planned is not None else ""
        fluid_bit = ""
        if fluid_ok is not None:
            fluid_bit = "; fluids OK" if fluid_ok else "; fluids short"
        note_bit = f"; note: {note}" if note else ""
        lines.append(
            f"In-ride fuelling logged: ~{float(actual):.0f} g carbs/h{plan_bit}{fluid_bit}{note_bit}."
        )
        if planned and actual < 0.6 * float(planned):
            lines.append(
                "Fuelling adherence is well below target. If late-ride power collapsed, "
                "treat under-fuelling as the primary cause — not pacing polish or heat alone."
            )
    else:
        plan_bit = f"~{float(planned):.0f} g/h" if planned is not None else "60–90 g/h"
        lines.append(
            f"In-ride fuelling: not logged. Plan target for a ride this long is {plan_bit}."
        )
        if fuel_fade or dur_min >= 150:
            lines.append(
                "Without a carb log, do not assume fuelling was adequate. "
                "If final-third power fell hard with HR still high, prefer under-fuelling "
                "over a clean 'successful aerobic long' narrative."
            )
    return lines


def _activity_has_power_data(activity: dict, detail: dict) -> bool:
    if detail.get("has_power_meter") or activity.get("has_power_meter"):
        return True
    return bool(
        detail.get("avg_power_w") or activity.get("avg_power_w")
        or detail.get("norm_power_w") or activity.get("norm_power_w")
    )


def _coach_system_prompt(
    type_key: str,
    activity_name: str = "",
    *,
    has_power: Optional[bool] = None,
) -> str:
    from ..history import power_meter_active
    if has_power is None:
        has_power = power_meter_active()
    if has_power and type_key in _CYCLING_TYPES:
        tail = (
            _DUAL_CHANNEL_SYSTEM + " "
            "Discuss both watts and HR when both are available. Reference the numbers. "
            "No bullet markdown — short paragraphs only. Address the athlete as 'you'."
        )
    else:
        tail = (
            hr_channel_note(False) + " "
            "Reference the numbers. "
            "No bullet markdown — short paragraphs only. Address the athlete as 'you'."
        )
    is_ruck = type_key in _RUCK_TYPES or "load carry" in activity_name.lower()
    if type_key in _CYCLING_TYPES:
        return (
            COACH_VOICE + "\n\n"
            "Right now: you're reviewing one of Martin's completed cycling rides. " + tail
        )
    if type_key == "stair_climbing":
        return (
            COACH_VOICE + "\n\n"
            "Right now: you're reviewing a completed MaxiClimber session. "
            "The MaxiClimber is a full-body vertical climbing machine (arms AND legs simultaneously) "
            "used here as a structured cardio interval tool — not a strength exercise. "
            "Treat it like a cardio interval session: evaluate HR zone execution, interval quality, "
            "aerobic vs anaerobic balance, and recovery between efforts. " + tail
        )
    if type_key == "strength_training":
        return (
            COACH_VOICE + "\n\n"
            "Right now: you're reviewing a completed kettlebell and strength session. " + tail
        )
    if is_ruck:
        return (
            COACH_VOICE + "\n\n"
            "Right now: you're reviewing a completed ruck (weighted load-carry) session. " + tail
        )
    if type_key in _RUNNING_TYPES:
        return (
            COACH_VOICE + "\n\n"
            "Right now: you're reviewing a completed run. " + tail
        )
    return (
        COACH_VOICE + "\n\n"
        "Right now: you're reviewing a completed training session. " + tail
    )


def _build_analysis_prompt(activity: dict, detail: dict, companion: Optional[dict] = None) -> str:
    act_date = activity.get("date", "")
    d_obj = date.fromisoformat(act_date) if act_date else None

    dur_secs = int(activity.get("duration_seconds") or 0)
    dur_fmt = _fmt_secs(dur_secs)
    dist_km = round((activity.get("distance_meters") or 0) / 1000, 1)
    type_key = activity.get("type_key", "")
    avg_speed_kmh = (
        round(dist_km / (dur_secs / 3600), 1)
        if type_key in _CYCLING_TYPES and dur_secs > 0 and dist_km > 0
        else None
    )
    avg_hr = activity.get("avg_hr")
    max_hr = activity.get("max_hr")
    calories = activity.get("calories")
    elev = activity.get("elevation_gain")
    name = activity.get("name") or activity.get("type_key", "ride")

    _ftp_labels = {"FTP Test", "FTP Re-test", "Final FTP Test"}
    _is_ftp = False
    if d_obj:
        try:
            sess_early = session_for_date_extended(d_obj)
            _is_ftp = bool(sess_early and sess_early[1] in _ftp_labels)
        except Exception:
            pass
    this_test_effort_w = detail.get("ftp_effort_avg_w")
    this_test_ftp = detail.get("ftp_w")
    if this_test_ftp is None and this_test_effort_w:
        try:
            this_test_ftp = round(float(this_test_effort_w) * 0.95)
        except (TypeError, ValueError):
            this_test_ftp = None

    hr_zones = detail.get("hr_zones", [])
    zone_lines = []
    for z in hr_zones:
        bar = "█" * max(1, z["pct"] // 5)
        bpm_str = f"≥{z['low_bpm']}bpm" if z.get("low_bpm") else f"Zone {z['zone']}"
        zone_lines.append(f"  Z{z['zone']} ({bpm_str}): {bar} {z['pct']}%  {_fmt_secs(z['secs'])}")

    has_power = _activity_has_power_data(activity, detail)
    avg_pwr = detail.get("avg_power_w") or activity.get("avg_power_w")
    np_pwr = detail.get("norm_power_w") or activity.get("norm_power_w")
    max_pwr = detail.get("max_power_w") or activity.get("max_power_w")
    power_zones = detail.get("power_zones") or []
    power_zone_lines: list[str] = []
    for z in power_zones:
        bar = "█" * max(1, z["pct"] // 5)
        w_str = f"≥{z['low_w']}W" if z.get("low_w") else f"Zone {z['zone']}"
        power_zone_lines.append(f"  Z{z['zone']} ({w_str}): {bar} {z['pct']}%  {_fmt_secs(z['secs'])}")

    ftp_w = None
    ftp_date = None
    ftp_stale = False
    ftp_hr_lthr = None
    if has_power:
        try:
            from ..history import load_ftp_tests, ftp_retest_due
            from ..plan import PLAN_START
            from .power import ftp_w_on_date
            if d_obj:
                ftp_w = ftp_w_on_date(d_obj)
                for t in reversed(load_ftp_tests()):
                    td = date.fromisoformat(t["date"]) if t.get("date") else None
                    if td and td <= d_obj and t.get("ftp_w") and int(t["ftp_w"]) == int(ftp_w or 0):
                        ftp_date = t.get("date")
                        ftp_hr_lthr = t.get("ftp_hr")
                        break
                if ftp_w and not ftp_date:
                    for t in reversed(load_ftp_tests()):
                        td = date.fromisoformat(t["date"]) if t.get("date") else None
                        if td and td <= d_obj and t.get("ftp_w"):
                            ftp_date = t.get("date")
                            ftp_hr_lthr = t.get("ftp_hr")
                            break
            else:
                for t in reversed(load_ftp_tests()):
                    if t.get("ftp_w"):
                        ftp_w = t["ftp_w"]
                        ftp_date = t.get("date")
                        ftp_hr_lthr = t.get("ftp_hr")
                        break
            ftp_stale = ftp_retest_due(d_obj or date.today(), plan_start=PLAN_START) is not None
        except Exception:
            pass

    # Garmin computes the power time-in-zone buckets against the FTP in the
    # athlete's Garmin *profile*, which this app never sets, reads, or reconciles
    # with the measured FTP in ftp_tests. Two failure modes make those zone
    # percentages untrustworthy and must override the coach's reading of them:
    #   (1) uncalibrated — no measured FTP on record, so the buckets run against
    #       an unverified/default profile FTP;
    #   (2) mismatch — the FTP implied by the zone boundaries diverges from the
    #       measured FTP (Coggan Z4/threshold low boundary ≈ 91% FTP). Threshold
    #       is ~7% so a 202 vs 214 W split is flagged.
    # A stale-but-present measured FTP is still the intensity anchor; it only
    # triggers a soft retest note, not the UNCALIBRATED narrative.
    power_uncalibrated = bool(power_zone_lines) and ftp_w is None
    power_zone_mismatch = False
    implied_ftp = None
    z4_low_w = None
    if ftp_w and power_zones:
        z4 = next((z for z in power_zones if z.get("zone") == 4 and z.get("low_w")), None)
        if z4 and z4.get("low_w"):
            z4_low_w = z4["low_w"]
            implied_ftp = z4_low_w / 0.91
            if abs(implied_ftp - ftp_w) / ftp_w > 0.07:
                power_zone_mismatch = True

    hr_zone_secs = sum(z.get("secs") or 0 for z in hr_zones)
    hr_suspect = (
        hr_zone_secs == 0
        or (avg_hr is not None and max_hr is not None and avg_hr == max_hr and dur_secs > 20 * 60)
    )
    data_quality_lines: list[str] = []
    if has_power and hr_suspect and power_zone_lines:
        data_quality_lines.append(
            "Data quality: HR zone data is missing or implausible on this file — "
            "treat power zones and watts as the primary intensity evidence; "
            "note the HR strap/recording issue briefly."
        )
    elif has_power and power_uncalibrated:
        data_quality_lines.append(
            "Data quality: power zones are UNCALIBRATED — no measured FTP is on "
            "record, so Garmin built the power time-in-zone buckets against an unverified "
            "profile FTP (often a stale/high default). Do NOT narrate the power-zone "
            "percentages as the effort distribution, and do NOT conclude the ride was "
            "easy/soft-pedalled from a high share of low zones — that is almost always a "
            "too-high FTP, not the athlete coasting. Treat HR and RPE as the primary "
            "intensity evidence (e.g. read interval efforts from peak watts vs HR, not "
            "zone shares). Recommend setting an FTP or running an FTP test to calibrate."
        )
    elif has_power and power_zone_mismatch:
        data_quality_lines.append(
            f"Data quality: the Garmin power zones imply an FTP of ~{int(implied_ftp)} W "
            f"(threshold/Z4 boundary {int(z4_low_w)} W ≈ 91% FTP), but the measured FTP on "
            f"record is {int(ftp_w)} W — a >7% divergence. The power-zone percentages are "
            "likely miscalibrated; prioritise HR/RPE and absolute watts over power-zone "
            "shares, and do not read the zone distribution as the true effort distribution. "
            "Use the measured FTP above for all %FTP / IF claims."
        )
    elif has_power and hr_zone_secs > 0 and power_zone_lines:
        ftp_anchor = f"{int(ftp_w)} W"
        if ftp_date:
            ftp_anchor += f" (tested {ftp_date})"
        data_quality_lines.append(
            f"Dual-channel read: measured FTP {ftp_anchor} is on record and Garmin "
            "power-zone boundaries align with it. Treat absolute watts, NP, and %FTP/IF "
            "as the primary intensity read. If HR and power diverge, prefer physiology/"
            "pacing — cardiac drift, heat, duration, surges, or early cardiac efficiency — "
            "not an uncalibrated profile FTP story (that is already ruled out when zones "
            "align). Power-hard / HR-easy on long rides often means drift/heat; divergence "
            "isolated to late reps points to genuine leg/metabolic fatigue."
        )
    if has_power and ftp_w is not None and ftp_stale and not power_uncalibrated:
        data_quality_lines.append(
            f"FTP note: measured FTP {int(ftp_w)} W is more than 42 days old — recommend "
            "a retest soon. Still use NP / %FTP against this measured FTP as the intensity "
            "anchor; do not treat power zones as unverified solely because the test is aged."
        )
    if ftp_hr_lthr and avg_hr is not None:
        data_quality_lines.append(
            f"LTHR on record: {int(ftp_hr_lthr)} bpm. Do not claim the ride was "
            "'entirely Z1–Z2' without checking average/peak HR against this LTHR."
        )

    power_summary_lines: list[str] = []
    if has_power and (avg_pwr or np_pwr or max_pwr):
        pwr_parts = []
        if avg_pwr:
            pwr_parts.append(f"avg {int(avg_pwr)} W")
        if np_pwr:
            pwr_parts.append(f"NP {int(np_pwr)} W")
        if max_pwr:
            pwr_parts.append(f"max {int(max_pwr)} W")
        if ftp_w:
            # On an FTP-test day the record in ftp_tests may still be the *prior*
            # value when this prompt runs (save happens after analysis). Label it
            # so the model does not conflate it with THIS TEST RESULT.
            if (
                _is_ftp
                and this_test_ftp
                and int(ftp_w) != int(this_test_ftp)
            ):
                ftp_label = f"Prior FTP on record (pre-test, zone context only): {int(ftp_w)} W"
            else:
                ftp_label = f"Measured FTP: {int(ftp_w)} W"
            if ftp_date:
                ftp_label += f" (as of {ftp_date})"
            power_summary_lines.append(ftp_label)
        if ftp_w and np_pwr:
            pwr_parts.append(f"{round(np_pwr / ftp_w * 100)}% FTP")
        if_val = activity.get("intensity_factor")
        tss_val = activity.get("tss")
        if if_val is not None:
            pwr_parts.append(f"IF {float(if_val):.3f}")
        if tss_val is not None:
            pwr_parts.append(f"TSS {float(tss_val):.1f}")
        power_summary_lines.append("Power: " + ", ".join(pwr_parts))

    min_temp = activity.get("min_temperature")
    max_temp = activity.get("max_temperature")
    max_temp_c = _max_temp_c(activity)
    temp_line = ""
    if min_temp is not None or max_temp is not None:
        lo = f"{float(min_temp):.0f}" if min_temp is not None else "?"
        hi = f"{float(max_temp):.0f}" if max_temp is not None else "?"
        temp_line = (
            f"Ambient temperature: {lo}–{hi} °C. "
            "Heat cardiac drift (power held, HR up) above ~25 °C is expected physiology. "
            "Power collapse in the final third with HR still high is fuel fade — do not "
            "blame heat alone."
        )

    durability_lines: list[str] = []
    fuel_fade = False
    act_id = activity.get("activity_id")
    if act_id is not None:
        try:
            from ..history import get_durability, get_power_durability
            pd_row = get_power_durability(int(act_id))
            if pd_row and pd_row.get("decoupling_pct") is not None:
                durability_lines.extend(_durability_coaching_lines(pd_row, max_temp_c))
                fuel_fade = (
                    classify_late_ride_fade(
                        pd_row.get("power_drift_pct"),
                        pd_row.get("hr_drift_pct"),
                        max_temp_c,
                    )
                    == "fuel_fade"
                )
            else:
                dur_row = get_durability(int(act_id))
                if dur_row and dur_row.get("drift_pct") is not None:
                    durability_lines.append(
                        f"Late-ride HR drift: {dur_row['drift_pct']:+.1f}% "
                        f"(first-third {dur_row.get('first_third_hr') or 0:.0f} bpm → "
                        f"final-third {dur_row.get('final_third_hr') or 0:.0f} bpm)"
                    )
        except Exception:
            pass

    fuelling_lines = _fuelling_context_lines(activity, fuel_fade=fuel_fade)

    te = detail.get("training_effect")
    te_label = _te_label(detail.get("training_effect_label"))
    tl = detail.get("training_load")
    resp = detail.get("avg_respiration")
    aerobic_msg = (detail.get("aerobic_te_message") or "").replace("_", " ")

    # Planned session context
    plan_line = ""
    compound_lines: list[str] = []
    if d_obj:
        session = session_for_date_extended(d_obj)
        if session:
            stype, slabel, sdur = session
            plan_line = f"\nPlanned workout for this day: {slabel} ({stype}, {sdur}m total)"
            dur_min = int(dur_secs / 60)
            if not COMPOUND_SESSIONS.get(slabel):
                over_pct = (dur_min - sdur) / sdur * 100 if sdur else 0
                if dur_min >= sdur * 0.95 and over_pct <= 25:
                    plan_line += (
                        f"\nNote: actual duration ({dur_min}m) is within normal range of the plan ({sdur}m). "
                        "Do NOT flag this as significantly exceeding or cutting short the plan."
                    )
                elif dur_min < sdur * 0.95:
                    pass  # genuinely short — Claude can comment
                # over 25% is a genuine overrun — no note needed
            if COMPOUND_SESSIONS.get(slabel):
                if companion:
                    comp_dur = int((companion.get("duration_seconds") or 0) / 60)
                    comp_name = companion.get("name") or companion.get("type_key", "")
                    comp_hr = companion.get("avg_hr")
                    comp_cal = companion.get("calories")
                    combined_min = int(dur_secs / 60) + comp_dur
                    compound_lines = [
                        "",
                        "Combined session context: both components were completed today.",
                        f"Companion activity — {comp_name}: {comp_dur}m, avg HR {comp_hr} bpm, {comp_cal} kcal",
                        f"Combined duration: ~{combined_min}m (plan target: {sdur}m)",
                        "Analyse this component in the context of the full combined session.",
                    ]
                else:
                    compound_lines = [
                        "",
                        f"Note: the plan calls for a combined {slabel} session ({sdur}m total).",
                        "Only this component was logged today. Do not flag the duration as short.",
                    ]

    equipment_note = (
        "Equipment note: this 'stair_climbing' activity was performed on a MaxiClimber — "
        "a vertical climbing machine that works arms AND legs simultaneously (not legs-only). "
        "It is used here as a structured cardio interval tool with timed work/rest sets at the prescribed HR "
        "zone stated below. "
        "Analyse it as a cardio interval session: focus on HR zone adherence during work intervals, "
        "recovery completeness during rest intervals, and overall aerobic training effect. "
        "Do NOT treat it as a strength or resistance session."
        if type_key == "stair_climbing" else
        "Activity note: 'load carry' and 'rucking' are the same activity — walking or hiking with a weighted pack. "
        "Do not treat them as different session types. A planned ruck and a logged load carry are equivalent."
        if "load carry" in name.lower() else ""
    )

    # Prescribed HR-zone target for MaxiClimber sessions, so the coach evaluates
    # execution against the actual plan target (e.g. Z2–3 in a standard week) and
    # does not assume a harder protocol such as Norwegian 4×4.
    target_zone_line = ""
    if d_obj and type_key in ("stair_climbing", "indoor_cardio"):
        tz = maxi_target_zone(d_obj)
        if tz:
            target_zone_line = (
                f"Prescribed target zone for THIS session: {tz}. "
                "Judge execution against THIS target only — do NOT assume a higher-intensity "
                "protocol (e.g. Norwegian 4×4 / Z4) unless the prescribed zone above says so. "
                "Reaching Z2–Z3 on a Z2–Z3 day is a success, not a shortfall."
            )

    _ftp_labels = {"FTP Test", "FTP Re-test", "Final FTP Test"}
    # _is_ftp / this_test_ftp computed earlier (before power summary) so Measured FTP
    # can be labelled prior-vs-this-test correctly.
    ftp_effort_avg_hr = detail.get("ftp_effort_avg_hr")
    ftp_effort_max_hr = detail.get("ftp_effort_max_hr")
    ftp_effort_line = ""
    if _is_ftp and (ftp_effort_avg_hr or this_test_ftp):
        bits: list[str] = []
        if this_test_effort_w and this_test_ftp:
            bits.append(
                f"THIS TEST RESULT: 20-min avg power {int(this_test_effort_w)} W → "
                f"FTP {int(this_test_ftp)} W (95% of 20-min watts). "
                "Cite THIS figure as today's FTP — never quote a prior ftp_tests record "
                "(e.g. an older Measured FTP line) as the outcome of this ride."
            )
        if ftp_effort_avg_hr:
            max_str = f", max HR {int(ftp_effort_max_hr)} bpm" if ftp_effort_max_hr else ""
            bits.append(
                f"20-minute test effort HR: avg {int(ftp_effort_avg_hr)} bpm{max_str}. "
                "LTHR ≈ 95% of that all-out 20-min avg HR (same discount as FTP watts)."
            )
        ftp_effort_line = " ".join(bits)
    ftp_note = (
        "Session structure note: this is an FTP test. The standard structure is "
        "~15m warm-up (Z1–Z2), 3m priming effort, 5m Z1 recovery, then a 20-minute all-out effort (target Z4–Z5), "
        "followed by ~17m cool-down (Z1–Z2). The HR zone distribution across the full activity will therefore "
        "show significant Z1–Z2 time from the warm-up and cool-down — this is expected and correct. "
        "Focus your analysis on whether the 20-minute test effort was well-executed: "
        "was max HR high, did the athlete sustain effort into Z4–Z5, and how does the training load reflect the test demand? "
        "The headline FTP number must match THIS TEST RESULT above when watts are present."
        if _is_ftp else ""
    )

    # Interval rep summary for structured sessions
    from .intervals import _INTERVAL_PRESCRIBED
    interval_reps = detail.get("interval_reps") or []
    interval_lines: list[str] = []
    session_label_for_prescribed = None
    if d_obj:
        sess = session_for_date_extended(d_obj)
        if sess:
            session_label_for_prescribed = sess[1]
    if interval_reps:
        prescribed = _INTERVAL_PRESCRIBED.get(session_label_for_prescribed or "")
        if prescribed:
            interval_lines.append(f"Prescribed interval target: {prescribed}")
            interval_lines.append(
                "Grade each block against that single target (cadence + power). "
                "Uneven power across blocks with flat/falling HR is pacing/terrain, not fatigue."
            )
        interval_lines.append("Interval rep data (from lap splits):")
        for rep in interval_reps:
            dur_s = rep.get("duration_secs") or 0
            dur_fmt_rep = f"{dur_s // 60}m{dur_s % 60:02d}s"
            avg = f"avg HR {rep['avg_hr']} bpm" if rep.get("avg_hr") else ""
            mx  = f", max {rep['max_hr']} bpm" if rep.get("max_hr") else ""
            pwr = f", avg {rep['avg_power_w']} W" if rep.get("avg_power_w") else ""
            interval_lines.append(f"  {rep['name']} {rep['rep']}: {avg}{mx}{pwr} ({dur_fmt_rep})")
        if len(interval_reps) >= 2:
            first_hr = interval_reps[0].get("avg_hr") or 0
            last_hr  = interval_reps[-1].get("avg_hr") or 0
            drift = last_hr - first_hr
            sign = "+" if drift >= 0 else ""
            interval_lines.append(
                f"HR drift across reps: {sign}{drift} bpm (rep 1 → rep {len(interval_reps)}) — "
                + ("expected accumulation" if drift > 0 else "HR stayed flat or dropped")
            )

    # FIT-derived interval execution (when available)
    fit_interval_lines = detail.get("fit_interval_prompt_lines") or []
    if fit_interval_lines:
        interval_lines.extend(fit_interval_lines)

    if has_power and power_zone_lines:
        ask_lines = [
            "Please provide:",
            "1. A one-sentence headline: how well was this session executed?",
            "2. Two or three sentences cross-reading HR and power — zone distributions, "
            "any HR↔power divergence, late-ride fade (heat drift vs fuel fade), "
            "fuelling when relevant, and whether intensity matched the planned session.",
            "3. One sentence on the training effect and what it means for fitness adaptation.",
            "4. One sentence on recovery — how demanding was this relatively?",
            "Keep it under 180 words. Plain paragraphs, no headers or bullets.",
        ]
    else:
        ask_lines = [
            "Please provide:",
            "1. A one-sentence headline: how well was this session executed?",
            "2. Two or three sentences on the HR zone distribution — was it appropriate for this session type?",
            "3. One sentence on the training effect and what it means for fitness adaptation.",
            "4. One sentence on recovery — how demanding was this relatively?",
            "Keep it under 150 words. Plain paragraphs, no headers or bullets.",
        ]

    lines = [
        f"Activity: {name}",
        f"Date: {act_date}",
        f"Duration: {dur_fmt}  Distance: {dist_km} km" + (f"  Avg speed: {avg_speed_kmh} km/h" if avg_speed_kmh else ""),
        f"Avg HR: {avg_hr} bpm  Max HR: {max_hr} bpm",
        *power_summary_lines,
        *durability_lines,
        *fuelling_lines,
        temp_line,
        f"Calories: {calories}  Elevation gain: {elev} m",
        f"Aerobic training effect: {te} ({te_label}) — {aerobic_msg}",
        f"Training load: {tl}",
        f"Avg respiration: {resp} breaths/min" if resp else "",
        *data_quality_lines,
        equipment_note,
        target_zone_line,
        ftp_note,
        ftp_effort_line,
        *interval_lines,
        "",
        "Heart rate zone distribution:",
        *zone_lines,
        *([""] + ["Power zone distribution:"] + power_zone_lines if power_zone_lines else []),
        plan_line,
        *compound_lines,
        "",
        *ask_lines,
    ]
    return "\n".join(l for l in lines if l is not None)


def _rule_based_analysis(activity: dict, detail: dict) -> str:
    te = detail.get("training_effect") or 0
    te_label = _te_label(detail.get("training_effect_label"))
    hr_zones = detail.get("hr_zones", [])
    has_power = _activity_has_power_data(activity, detail)
    np_pwr = detail.get("norm_power_w") or activity.get("norm_power_w")

    z2_pct = next((z["pct"] for z in hr_zones if z["zone"] == 2), 0)
    z3_pct = next((z["pct"] for z in hr_zones if z["zone"] == 3), 0)
    high_zone_pct = sum(z["pct"] for z in hr_zones if z["zone"] >= 4)
    hr_zone_secs = sum(z.get("secs") or 0 for z in hr_zones)

    if has_power and hr_zone_secs == 0 and np_pwr:
        return (
            f"Power data looks usable (NP {int(np_pwr)} W) but HR zones are missing or corrupt on this file — "
            f"intensity should be judged from power, not heart rate. "
            f"Aerobic training effect: {te:.1f} ({te_label}). "
            "Check the HR strap before the next ride."
        )

    if high_zone_pct > 20:
        intensity = "high-intensity session with significant time in zones 4-5"
    elif z3_pct > 40:
        intensity = "moderate-intensity session predominantly in zone 3"
    elif z2_pct > 40:
        intensity = "good aerobic session with solid zone 2 work"
    else:
        intensity = "mixed-intensity session"

    return (
        f"This was a {intensity}. "
        f"Aerobic training effect: {te:.1f} ({te_label}). "
        f"{'Consider more zone 2 work to build aerobic base.' if z2_pct < 20 else 'Zone distribution looks reasonable for this type of session.'}"
    )


def _rule_based_recovery(stype: str, days_left: int) -> str:
    if days_left >= 2:
        if stype == "strength":
            return (
                "You still have time to fit this in. A shorter KB + MaxiClimber session — "
                "even 30 minutes — is better than nothing. If fatigue is running high, skip it "
                "and keep the rest of your week on track.\n\n"
                "Consistency matters more than any single session at this stage of the plan."
            )
        elif stype in ("ftp",):
            return (
                "An FTP test requires you to be fresh — don't squeeze it in if you're tired. "
                "Push it to the next day where you have at least one rest day beforehand.\n\n"
                "If the week is too disrupted, skip this test cycle and catch it next scheduled opportunity."
            )
        elif stype in ("bike", "tempo", "long"):
            return (
                "You have days left to reschedule. If you feel good, slot this ride in soon — "
                "consider shortening it slightly if time is tight. One missed aerobic session "
                "won't derail your fitness.\n\n"
                "If energy is low, skip it entirely. Protect the quality of your remaining sessions."
            )
        else:
            return (
                "With days still available, try to fit this in when energy allows. A shortened "
                "version at 60–70% of planned duration still delivers training stimulus.\n\n"
                "If you're run down, skip it and focus on executing the rest of the week well."
            )
    else:
        return (
            "With limited days left this week, it's better to skip this session rather than "
            "cramming it in on a tired body. Forced make-up sessions near week's end often "
            "compromise the next week's training.\n\n"
            "Come back fresh on Monday and stay consistent from there."
        )

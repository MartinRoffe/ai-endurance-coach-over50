"""Sonnet climb analysis essays (Phase 2), cached in text_cache."""
from __future__ import annotations

import os
from typing import Any, Optional

from ..coach_voice import COACH_VOICE
from ..history import get_cached_text, named_climb_summary, set_cached_text
from ..llm import MODEL_SMART

_MIN_ESSAY_GAIN_M = 40.0
_MIN_ESSAY_DURATION_S = 180.0


def climb_essay_cache_key(
    *,
    named_climb_id: Optional[int],
    activity_id: int,
    climb_index: int,
) -> str:
    if named_climb_id is not None:
        return f"climb_essay_v1_{named_climb_id}_{activity_id}"
    return f"climb_essay_v1_a{activity_id}_c{climb_index}"


def build_climb_essay_prompt(
    climb: dict[str, Any],
    *,
    named: Optional[dict[str, Any]] = None,
    prior_summary: Optional[dict[str, Any]] = None,
    activity_name: Optional[str] = None,
    activity_date: Optional[str] = None,
    activity_id: Optional[int] = None,
) -> str:
    """Assemble deterministic prompt lines (unit-testable without LLM)."""
    lines: list[str] = []
    label = (named or {}).get("name") or f"Climb #{climb.get('climb_index', '?')}"
    lines.append(f"Climb: {label}")
    if activity_date or activity_name:
        bits = [b for b in (activity_date, activity_name) if b]
        lines.append(f"Ride: {' · '.join(bits)}")
    lines.append("")
    lines.append("Metrics:")
    for key, fmt in [
        ("start_km", "Start km: {}"),
        ("length_m", "Length: {} m"),
        ("gain_m", "Gain: {} m"),
        ("avg_grade", "Avg grade: {}%"),
        ("max_grade", "Max grade: {}%"),
        ("duration_min", "Duration: {} min"),
        ("vam_m_h", "VAM: {} m/h"),
        ("vam_confidence", "VAM confidence: {}"),
        ("avg_power", "Avg power: {} W"),
        ("np", "NP: {} W"),
        ("wkg", "Measured W/kg: {}"),
        ("est_wkg_from_vam", "VAM-estimated W/kg: {}"),
        ("pct_ftp", "%FTP: {}"),
        ("first_half_w", "First-half power: {} W"),
        ("second_half_w", "Second-half power: {} W"),
        ("fade_pct", "Fade (1st−2nd half): {}%"),
        ("avg_cadence", "Avg cadence: {} rpm"),
        ("pct_below_60", "% time <60 rpm: {}"),
        ("pct_70_85", "% time 70–85 rpm: {}"),
        ("avg_hr", "Avg HR: {}"),
    ]:
        val = climb.get(key)
        if val is not None:
            lines.append("  " + fmt.format(val))

    if prior_summary and prior_summary.get("attempts"):
        attempts = list(prior_summary["attempts"])
        # Split current attempt from earlier history
        prior_only = []
        current_ord = None
        for i, a in enumerate(attempts, start=1):
            same = False
            if activity_id is not None and int(a.get("activity_id") or 0) == int(activity_id):
                same = True
            elif activity_date and a.get("date") == activity_date:
                # fallback when activity_id missing
                same = int(a.get("climb_index") or -1) == int(climb.get("climb_index") or -2)
            if same:
                current_ord = i
            else:
                prior_only.append(a)

        n_total = len(attempts)
        attempt_n = current_ord or (len(prior_only) + 1)
        lines.append("")
        if attempt_n <= 1 and not prior_only:
            lines.append(
                f"Attempt history: this is attempt 1 of 1 on {label} — a true first attempt / baseline."
            )
        else:
            lines.append(
                f"Attempt history: this is attempt {attempt_n} of {n_total} on {label} — "
                f"NOT a first attempt. You MUST compare to prior attempts and the PB; "
                f"do not call this a baseline or first attempt."
            )
            lines.append(f"  Prior attempts on record: {len(prior_only)}")
            for a in prior_only[-5:]:
                m = a.get("metrics") or {}
                bits = [a.get("date") or "?"]
                if m.get("vam_m_h") is not None:
                    bits.append(f"VAM {m['vam_m_h']}")
                if m.get("duration_s") is not None:
                    bits.append(f"{float(m['duration_s'])/60:.1f} min")
                if m.get("avg_power") is not None:
                    bits.append(f"{m['avg_power']} W")
                if m.get("wkg") is not None:
                    bits.append(f"{m['wkg']} W/kg")
                lines.append("  - " + ", ".join(str(b) for b in bits))
            if prior_summary.get("pb_vam") is not None:
                lines.append(f"  Season PB VAM: {prior_summary['pb_vam']} m/h")
            if prior_summary.get("pb_time_s") is not None:
                lines.append(f"  Season PB time: {prior_summary['pb_time_s']:.0f} s")
            if prior_summary.get("pb_wkg") is not None:
                lines.append(f"  Season PB W/kg: {prior_summary['pb_wkg']}")
            this_vam = climb.get("vam_m_h")
            pb_vam = prior_summary.get("pb_vam")
            if this_vam and pb_vam and float(pb_vam) > 0:
                delta_pb = (float(this_vam) - float(pb_vam)) / float(pb_vam) * 100
                lines.append(f"  This VAM vs season PB: {delta_pb:+.1f}%")
            this_t = climb.get("duration_s")
            pb_t = prior_summary.get("pb_time_s")
            if this_t and pb_t and float(pb_t) > 0:
                # negative = slower than PB
                delta_t = (float(pb_t) - float(this_t)) / float(pb_t) * 100
                lines.append(
                    f"  This time vs season PB: {delta_t:+.1f}% "
                    f"({'faster' if delta_t > 0 else 'slower' if delta_t < 0 else 'equal'})"
                )

    lines.append("")
    lines.append(
        "Write 2–4 short paragraphs for a masters (50+) cyclist. Focus on sustainable "
        "W/kg, even or slight negative-split pacing, and whether cadence stayed in a "
        "workable band (≥~70 rpm) vs grinding <60 rpm. Do not cite pro VAM leaderboards "
        "(1600+ m/h). If shallow-grade VAM confidence is low, say so. "
        "If this is attempt 2+, open by acknowledging the comparison to the prior best "
        "(faster/slower, higher/lower VAM) — never describe it as a first attempt. "
        "End with one concrete cue for the next time on this climb. Address the athlete "
        "as 'you'. No bullet points."
    )
    return "\n".join(lines)


def _rule_based_climb_essay(climb: dict[str, Any], named: Optional[dict] = None) -> str:
    label = (named or {}).get("name") or "This climb"
    bits = []
    if climb.get("vam_m_h"):
        bits.append(f"VAM {climb['vam_m_h']:.0f} m/h")
    if climb.get("avg_power"):
        bits.append(f"{climb['avg_power']} W")
    if climb.get("avg_cadence"):
        bits.append(f"{climb['avg_cadence']} rpm")
    summary = ", ".join(bits) if bits else "limited metrics"
    fade = climb.get("fade_pct")
    pacing = ""
    if fade is not None:
        if fade > 5:
            pacing = " Power faded in the second half — next time start a touch easier and finish stronger."
        elif fade < -3:
            pacing = " Nice negative split — keep that restraint at the base."
        else:
            pacing = " Pacing held fairly even."
    cad_note = ""
    if (climb.get("pct_below_60") or 0) > 25:
        cad_note = " A lot of time under 60 rpm — easier gearing would spare the knees on repeats."
    return (
        f"{label}: {summary} over {climb.get('gain_m', '?')} m at "
        f"{climb.get('avg_grade', '?')}%.{pacing}{cad_note} "
        f"Climbing gains for 50+ come from sustainable W/kg, even pacing, and strength work "
        f"— not from forcing low-cadence grinds."
    )


def generate_climb_essay(
    climb: dict[str, Any],
    *,
    activity_id: int,
    named_climb_id: Optional[int] = None,
    activity_name: Optional[str] = None,
    activity_date: Optional[str] = None,
    force: bool = False,
) -> str:
    """Generate (or return cached) Sonnet essay for a climb attempt."""
    key = climb_essay_cache_key(
        named_climb_id=named_climb_id,
        activity_id=activity_id,
        climb_index=int(climb.get("climb_index") or 0),
    )
    if not force:
        cached = get_cached_text(key)
        if cached:
            return cached

    # Cost control: skip anonymous short rollers unless named
    if named_climb_id is None:
        if float(climb.get("gain_m") or 0) < _MIN_ESSAY_GAIN_M:
            return ""
        if float(climb.get("duration_s") or 0) < _MIN_ESSAY_DURATION_S:
            return ""

    named = None
    prior = None
    if named_climb_id is not None:
        prior = named_climb_summary(named_climb_id)
        named = prior

    prompt = build_climb_essay_prompt(
        climb,
        named=named,
        prior_summary=prior,
        activity_name=activity_name,
        activity_date=activity_date,
        activity_id=activity_id,
    )

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        text = _rule_based_climb_essay(climb, named)
        set_cached_text(key, text)
        return text

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    try:
        msg = client.messages.create(
            model=MODEL_SMART,
            max_tokens=900,
            system=(
                COACH_VOICE + "\n\n"
                "You are analysing a single climb segment from a FIT file for a masters "
                "endurance cyclist. Be specific to the numbers provided. Prefer personal "
                "trends and pacing/cadence cues over absolute VAM bravado."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text
        set_cached_text(key, text)
        return text
    except Exception:
        text = _rule_based_climb_essay(climb, named)
        set_cached_text(key, text)
        return text


def clear_climb_essay(
    *,
    named_climb_id: Optional[int],
    activity_id: int,
    climb_index: int,
) -> None:
    from ..history import _conn
    key = climb_essay_cache_key(
        named_climb_id=named_climb_id,
        activity_id=activity_id,
        climb_index=climb_index,
    )
    with _conn() as con:
        con.execute("DELETE FROM text_cache WHERE key = ?", (key,))


def maybe_generate_named_climb_essays(
    activity: dict,
    climbs: list[dict],
    matched: list[dict],
) -> dict[str, str]:
    """Generate essays for matched named climbs; return map climb_index → text."""
    by_idx = {int(m["climb_index"]): m for m in matched}
    out: dict[str, str] = {}
    for climb in climbs:
        idx = int(climb.get("climb_index") or 0)
        m = by_idx.get(idx)
        if not m:
            continue
        text = generate_climb_essay(
            climb,
            activity_id=int(activity["activity_id"]),
            named_climb_id=int(m["named_climb_id"]),
            activity_name=activity.get("name"),
            activity_date=activity.get("date"),
        )
        if text:
            out[str(idx)] = text
    return out

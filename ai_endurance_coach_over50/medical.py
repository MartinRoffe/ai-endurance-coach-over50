"""Medical pause + two-year rebuild target (post kidney-stone / stent reset).

Single source of truth for:
- the medical-pause window (no structured training until follow-up)
- cancelled charity ride metadata
- Haute Route Alpes **2028** as the A-event (dates TBC)
- Year-1 / Year-2 phase skeleton (not a day-by-day plan yet)

Consulted *before* event-prep / charity / bridge / Haute Route session lookups
so the app stops prescribing race-week and HR Base load while recovering.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

# ── Medical pause ─────────────────────────────────────────────────────────────
# Stent removal 8 Sep 2026; not cleared for structured training until follow-up.
# End date is the knob to extend once the follow-up is booked.
MEDICAL_PAUSE_START = date(2026, 9, 1)
MEDICAL_PAUSE_END = date(2026, 9, 21)  # inclusive; extend after follow-up
STENT_REMOVAL_DATE = date(2026, 9, 8)

# Event-prep / charity / position-bridge window that the pause overrides
_EVENT_WINDOW_START = date(2026, 9, 1)
_EVENT_WINDOW_END = date(2026, 10, 4)  # day before former HR Base start

CHARITY_CANCELLED = True
CHARITY_CANCEL_REASON = (
    "Cancelled after kidney stones, ureteric blockage / function issues, "
    "emergency stent, lasertripsy, and second stent (removal 8 Sep 2026)."
)

# ── A-event: Haute Route Alpes 2028 (official dates not yet published) ───────
HR_A_EVENT_NAME = "Haute Route Alpes 2028"
# Placeholder: last full week of August 2028 (Sun–Sat). Labelled TBC everywhere.
HR_A_EVENT_START = date(2028, 8, 20)
HR_A_EVENT_END = date(2028, 8, 26)
HR_A_EVENT_DATES_TBC = True

# Year 2 cycling-specific block — not written yet; gate keeps old 46-week tuples offline
YEAR2_START = date(2027, 10, 4)  # Monday
YEAR2_PLAN_ACTIVE = False

# Christmas 2026 Tenerife — Year 1, tentative until post-stent follow-up
XMAS_CAMP_TENTATIVE = False
XMAS_CAMP_ARRIVE = date(2026, 12, 22)
XMAS_CAMP_BIKE_START = date(2026, 12, 23)
XMAS_CAMP_BIKE_END = date(2026, 12, 31)
XMAS_CAMP_HOME = date(2027, 1, 2)

# May 2027 race-sim was HR-2027-specific — not part of the live 2028 rebuild
MAY_2027_RACE_SIM_ACTIVE = False

# Seed facts for coach memory / system context (do not invent clinical advice)
MEDICAL_HISTORY_SUMMARY = (
    "Kidney stones with ureteric blockage and kidney function issues. "
    "Emergency surgery for a stent, then lasertripsy and a second stent. "
    "Stent removed 8 Sep 2026. "
    "The charity ride (Ghent→Amsterdam 13–14 Sep 2026) is cancelled. "
    "Clinic on 15 Oct 2026: ESWL was not performed because the fragments had "
    "already passed. Only a confirmation CT remains. Structured training is "
    "live from the week of 19 Oct. Until the confirmation CT: stop for flank "
    "pain, fever or blood. "
    "Haute Route Alpes 2028 is a later horizon, not the live A-event. "
    "He is not in a medical pause (that ended 21 Sep 2026). "
    "Live goals: Tenerife camp 21 Dec 2026–2 Jan 2027, BUSAR 20–21 Feb 2027, "
    "Lake District 27–28 Feb 2027, Scotland from 22 Mar 2027. "
    "The live year is general fitness for road and hills through 3 Oct 2027. "
    "Christmas Tenerife (21 Dec 2026–2 Jan 2027) is confirmed. Stored ride minutes "
    "are a ceiling; shorten the ride when fitness is not there. "
    "Year 2 (~Oct 2027 onward) is the cycling-specific Haute Route block and is not written yet. "
    "No kilogram target before Christmas. From 4 Jan 2027 the goal is 84–85 kg by 31 Mar 2027 "
    "(about 0.5 kg a week), using ordinary day-type deficits, not a hard cut."
)

# Thin phase skeleton — not week-by-week sessions
REBUILD_PHASES: list[dict] = [
    {
        "id": "medical_pause",
        "label": "Medical pause",
        "approx": "1–21 Sep 2026",
        "content": "Rest / optional easy walk. Stent out 8 Sep. This window has ended.",
        "status": "done",
    },
    {
        "id": "return_to_training",
        "label": "Return to training",
        "approx": "15 Oct 2026 clinic (no ESWL); confirmation CT pending",
        "content": (
            "Clinic 15 Oct 2026: fragments had already passed, so ESWL was not "
            "performed. Only a confirmation CT remains. Structured training is "
            "live. Until the confirmation CT: stop for flank pain, fever or blood."
        ),
        "status": "done",
    },
    {
        "id": "year1",
        "label": "Year 1 — aerobic + hills",
        "approx": "19 Oct 2026 → ~Sep 2027",
        "content": (
            "Hard sessions from Tue 20 Oct; autumn/winter hill-walk blocks; "
            "strength twice a week. Christmas Tenerife 2026 is confirmed; "
            "stored ride minutes are a ceiling."
        ),
        "status": "active",
    },
    {
        "id": "year1_checkpoint",
        "label": "Year 1 checkpoint",
        "approx": "~Aug 2027",
        "content": "Fitness / hill week — not Haute Route. Decision gate for Year 2 specificity.",
        "status": "upcoming",
    },
    {
        "id": "year2",
        "label": "Year 2 — Haute Route specific",
        "approx": "~Oct 2027 → Aug 2028",
        "content": "Cycling-specific block (reshape former 46-week plan once Year 1 is real).",
        "status": "upcoming",
    },
    {
        "id": "event",
        "label": "Haute Route Alpes 2028",
        "approx": "Late Aug 2028 (TBC)",
        "content": "Seven-stage Alps event. Stage details placeholder until 2028 route is published.",
        "status": "upcoming",
    },
]


def in_medical_pause(d: date) -> bool:
    """True when *d* falls in the medical-pause window (inclusive)."""
    return MEDICAL_PAUSE_START <= d <= MEDICAL_PAUSE_END


def in_event_override_window(d: date) -> bool:
    """True for dates that were event-prep / charity / bridge and must not prescribe load."""
    return _EVENT_WINDOW_START <= d <= _EVENT_WINDOW_END


def pause_session_for_date(d: date) -> tuple[str, str, int]:
    """Session while medically paused: rest, or optional easy walk on selected days.

    Walk days are Mon / Wed / Fri — light foot volume only, no bike / strength / scramble.
    """
    if d.weekday() in (0, 2, 4):  # Mon, Wed, Fri
        return ("hike", "Optional easy walk", 30)
    return ("rest", "Medical rest", 0)


def should_prescribe_training(d: date) -> bool:
    """False when the app must not schedule structured training for *d*."""
    if in_medical_pause(d) and in_event_override_window(d):
        return False
    if CHARITY_CANCELLED and date(2026, 9, 13) <= d <= date(2026, 9, 14):
        return False
    return True


def should_push_garmin_date(d: date) -> bool:
    """Garmin schedule filter: skip pause window, cancelled charity, and pre-Year-2 HR."""
    if not should_prescribe_training(d):
        return False
    if in_medical_pause(d):
        return False
    # Position bridge overlaps pause end — still no quality push while paused
    if in_event_override_window(d) and in_medical_pause(d):
        return False
    if in_event_override_window(d) and CHARITY_CANCELLED and d >= MEDICAL_PAUSE_START:
        # Cancelled race weekend + remaining prep/bridge: do not re-push bike quality
        return False
    return True


def year2_sessions_live() -> bool:
    """Whether the cycling-specific Haute Route week-by-week plan is active."""
    return YEAR2_PLAN_ACTIVE


def hr_a_event_summary() -> str:
    """Single-line A-event description for coach/advice prompts."""
    tbc = " (dates TBC)" if HR_A_EVENT_DATES_TBC else ""
    return (
        f"{HR_A_EVENT_NAME}: {HR_A_EVENT_START.strftime('%-d')}–"
        f"{HR_A_EVENT_END.strftime('%-d %b %Y')}{tbc}"
    )


def medical_pause_banner(d: Optional[date] = None) -> Optional[dict]:
    """Dashboard / calendar banner payload, or None if not in pause."""
    ref = d or date.today()
    if not in_medical_pause(ref):
        return None
    days_to_stent = (STENT_REMOVAL_DATE - ref).days
    if days_to_stent > 0:
        stent_line = f"Stent removal in {days_to_stent} day(s) ({STENT_REMOVAL_DATE.isoformat()})."
    elif days_to_stent == 0:
        stent_line = "Stent removal today."
    else:
        stent_line = (
            f"Stent removed {STENT_REMOVAL_DATE.isoformat()} — "
            "awaiting post-removal follow-up before structured training."
        )
    return {
        "status": "medical",
        "headline": "Medical pause — no structured training",
        "reason": (
            f"{stent_line} Charity ride cancelled. "
            "Rest or optional very light walking only until cleared. "
            f"A-event: {HR_A_EVENT_NAME} (late Aug 2028, dates TBC)."
        ),
        "stent_removal": STENT_REMOVAL_DATE.isoformat(),
        "pause_end": MEDICAL_PAUSE_END.isoformat(),
    }


def medical_context_lines() -> list[str]:
    """Inject into coach system / advice context."""
    lines = [
        "## Medical status (authoritative — do not contradict)",
        f"  {MEDICAL_HISTORY_SUMMARY}",
        f"  Pause window: {MEDICAL_PAUSE_START.isoformat()} → {MEDICAL_PAUSE_END.isoformat()} (inclusive).",
        f"  Stent removal: {STENT_REMOVAL_DATE.isoformat()}.",
        f"  Charity ride (Ghent→Amsterdam 13–14 Sep 2026): CANCELLED.",
        "  Live goals, in order: Tenerife camp 21 Dec 2026–2 Jan 2027, "
        "BUSAR 20–21 Feb 2027, Lake District 27–28 Feb 2027, Scotland from 22 Mar 2027. "
        f"Haute Route Alpes 2028 ({hr_a_event_summary()}) is not the live A-event. "
        "The medical pause has ended. Do not coach him as paused.",
        "  Do NOT prescribe Sweetspot, Tempo, VO2, Pre-Event Long, charity fuelling, "
        "or Haute Route race weeks. The 46-week Haute Route template is not the live plan. "
        "Clinic 15 Oct 2026: ESWL not performed (fragments already passed). "
        "Confirmation CT still pending. Structured training is live from 19 Oct.",
        "  Until the confirmation CT: stop for flank pain, fever or blood.",
        "  Hiking and scrambling are allowed outside the paused window. "
        "No running (unchanged athlete constraint).",
    ]
    if XMAS_CAMP_TENTATIVE:
        lines.append(
            f"  Christmas Tenerife {XMAS_CAMP_ARRIVE.isoformat()}–{XMAS_CAMP_HOME.isoformat()}: "
            "TENTATIVE — confirm after follow-up; easy volume / walk+bike if allowed, not race-sim."
        )
    else:
        lines.append(
            f"  Christmas Tenerife {XMAS_CAMP_ARRIVE.isoformat()}–{XMAS_CAMP_HOME.isoformat()}: "
            "CONFIRMED. Easy rides only. Stored minutes are a ceiling "
            "(longest 3 h on 26 Dec 2026); shorten the ride when fitness is not there. "
            "The 5–6 h Teide / Masca / finale grid is not scheduled."
        )
    if not MAY_2027_RACE_SIM_ACTIVE:
        lines.append("  May 2027 Tenerife race-sim camp: not part of the live plan.")
    lines.append(
        "  First hard session is Tue 20 Oct 2026. Two non-adjacent hard sessions "
        "a week from the week of 26 Oct. Strength starts Wed 21 Oct."
    )
    from .fitness_plan import BUSAR_STANDARDS, GRAVEL_BIKE_ACTIVE, gravel_sunday_note
    lines.append(f"  {gravel_sunday_note()}")
    if not GRAVEL_BIKE_ACTIVE:
        lines.append("  GRAVEL_BIKE_ACTIVE is false. Do not prescribe gravel-bike sessions.")
    lines.append(
        "  BUSAR test is Sat 20 and Sun 21 Feb 2027 (before the Lakes weekend). "
        "Standards: " + " ".join(BUSAR_STANDARDS)
    )
    if not YEAR2_PLAN_ACTIVE:
        lines.append(
            f"  Year 2 week-by-week Haute Route block: not started. "
            f"Write it after the 3 Oct 2027 fitness checkpoint "
            f"(placeholder start {YEAR2_START.isoformat()}). "
            "Do not prescribe sweetspot or VO2 before that."
        )
    lines.append("  Rebuild phases:")
    for p in REBUILD_PHASES:
        lines.append(f"    - [{p['status']}] {p['label']} ({p['approx']}): {p['content']}")
    return lines


def charity_status_summary() -> str:
    """Coach/advice line for the cancelled charity ride."""
    return (
        "Ghent→Amsterdam charity ride (13–14 Sep 2026): CANCELLED — medical "
        "(kidney stones / stent). Historical training block retained; not a live A-event."
    )

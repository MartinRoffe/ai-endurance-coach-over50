"""Hard caps applied after any plan session or AI suggestion.

The stored week templates are unchanged. Callers that prescribe a session
(dashboard, daily email, coach context, plan-change proposals, Garmin pushes
of an override) run the result through this module.

Thresholds are module constants so they can be tuned in one place.

Defaults
--------
MAX_WEEKLY_LOAD_INCREASE = 0.10
    Planned load may rise by at most 10% versus the previous week's prescribed
    load. Load is the session duration in minutes (the plan's load proxy), or
    an explicit TSS / training-load figure when the caller passes one. A
    previous week with no load is not percentage-capped.

MAX_HARD_SESSIONS_PER_WEEK = 2
    At most two hard / intensity sessions Monday–Sunday.

MIN_REST_DAYS_PER_WEEK = 1
    Every week keeps at least one full rest day.

MEDICAL_RETURN_EASY_DAYS = 7
    After a logged procedure (stent removal, the 15 Oct 2026 procedure) or the
    end of the medical pause, and for the whole procedure week, sessions are
    easy-only. Easy means not a hard type/label and not longer than
    EASY_ONLY_MAX_MIN (75).

Red-flag symptoms the app already models (illness 2-of-3 from HRV, resting
HR, and sleep, plus flank pain / fever / blood in the urine recorded on the
day's session note) replace the session with rest. That override wins.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping, Optional

# ── Tunable thresholds ───────────────────────────────────────────────────────

MAX_WEEKLY_LOAD_INCREASE = 0.10
MAX_HARD_SESSIONS_PER_WEEK = 2
MIN_REST_DAYS_PER_WEEK = 1
MEDICAL_RETURN_EASY_DAYS = 7
EASY_ONLY_MAX_MIN = 75
MIN_USEFUL_MIN = 20

HARD_TYPES = frozenset({
    "tempo", "ftp", "sweetspot", "vo2", "threshold", "intervals", "back_to_back",
})
HARD_LABEL_TOKENS = (
    "sweetspot", "vo2", "tempo", "threshold", "ftp",
    "interval", "hill repeat", "over-under", "over under", "heavy",
)
RED_FLAG_PHRASES = (
    "flank pain",
    "fever",
    "blood in the urine",
    "blood in urine",
    "haematuria",
    "hematuria",
)

_PRIORITY = (
    "red_flag",
    "procedure",
    "medical_return",
    "rest_day",
    "back_to_back",
    "hard_count",
    "weekly_load",
)
REST: tuple[str, str, int] = ("rest", "Rest", 0)
Session = tuple[str, str, int]


def weekly_load_reason() -> str:
    pct = int(round(MAX_WEEKLY_LOAD_INCREASE * 100))
    return f"Capped: +{pct}% weekly load limit"


def reason_text(code: str) -> str:
    return {
        "red_flag": "Capped: red-flag symptoms — rest",
        "procedure": "Capped: rest on procedure day",
        "medical_return": "Capped: easy-only return after procedure",
        "rest_day": "Capped: at least one rest day per week",
        "back_to_back": "Capped: no back-to-back hard days",
        "hard_count": f"Capped: {MAX_HARD_SESSIONS_PER_WEEK} hard sessions per week",
        "weekly_load": weekly_load_reason(),
    }[code]


def _norm(session: tuple) -> Session:
    stype = str(session[0] or "rest")
    label = str(session[1] or "Rest")
    dur = int(session[2] or 0)
    return (stype, label, dur)


def is_rest(session: tuple) -> bool:
    stype, label, dur = _norm(session)
    if stype == "rest":
        return True
    return dur <= 0 and "rest" in label.lower()


def is_hard(session: tuple) -> bool:
    if is_rest(session):
        return False
    stype, label, _dur = _norm(session)
    if stype in HARD_TYPES:
        return True
    low = label.lower()
    return any(tok in low for tok in HARD_LABEL_TOKENS)


def is_return_safe(session: tuple) -> bool:
    """Easy enough for the post-procedure / pause return window."""
    if is_rest(session):
        return True
    if is_hard(session):
        return False
    stype, label, dur = _norm(session)
    if dur > EASY_ONLY_MAX_MIN:
        return False
    if stype in ("strength", "gym"):
        low = label.lower()
        if not any(w in low for w in ("easy", "light", "maintenance", "optional")):
            return False
    return True


def as_easy(session: tuple, *, max_min: Optional[int] = None) -> Session:
    """Drop intensity. Duration is kept unless ``max_min`` shortens it."""
    stype, label, dur = _norm(session)
    if max_min is not None and dur > max_min:
        dur = max_min
    low = label.lower()
    if stype in ("hike", "scramble") or "walk" in low:
        return ("hike", "Easy walk", dur)
    if stype == "ruck" or "ruck" in low:
        return ("ruck", "Easy Walk (no load)", dur)
    if stype in ("strength", "gym"):
        return ("strength", "Strength — easy circuit", dur)
    if stype == "long" or "long ride" in low:
        return ("long", "Long Ride (Easy)", dur)
    if stype == "endurance":
        return ("endurance", "Z2 Easy", dur)
    return ("bike", "Z2 Easy", dur)


def session_load(session: tuple, explicit: Optional[float] = None) -> float:
    """Minutes, unless the caller supplies TSS or Garmin training load."""
    if explicit is not None:
        return float(explicit)
    if is_rest(session):
        return 0.0
    return float(_norm(session)[2])


@dataclass
class CappedDay:
    date: date
    original: Session
    session: Session
    reason: Optional[str]
    load: float

    @property
    def changed(self) -> bool:
        return self.session != self.original


class _Slot:
    def __init__(self, day: date, session: Session, load: float, load_is_duration: bool) -> None:
        self.date = day
        self.original = session
        self.session = session
        self.load = load
        self.load_is_duration = load_is_duration
        self.reason_code: Optional[str] = None
        self.locked = False

    def _note(self, code: str) -> None:
        if self.reason_code is None or _PRIORITY.index(code) < _PRIORITY.index(self.reason_code):
            self.reason_code = code

    def _sync_duration_load(self) -> None:
        if self.load_is_duration:
            self.load = 0.0 if is_rest(self.session) else float(self.session[2])

    def assign(self, session: tuple, code: str) -> None:
        if self.locked:
            return
        session = _norm(session)
        if session == self.session:
            return
        self.session = session
        self._sync_duration_load()
        self._note(code)

    def force(self, session: tuple, code: str) -> None:
        session = _norm(session)
        if session != self.session:
            self.session = session
            self._sync_duration_load()
            self._note(code)
        self.locked = True


def _procedure_dates() -> tuple[date, ...]:
    from .fitness_plan import PROCEDURE_START
    from .medical import STENT_REMOVAL_DATE
    # Thursday of the procedure week is the logged procedure day.
    return (STENT_REMOVAL_DATE, PROCEDURE_START + timedelta(days=3))


def in_easy_return(day: date) -> bool:
    """Procedure week, plus MEDICAL_RETURN_EASY_DAYS after each procedure and the pause."""
    from .fitness_plan import in_procedure_week
    from .medical import MEDICAL_PAUSE_END

    if in_procedure_week(day):
        return True
    anchors = list(_procedure_dates()) + [MEDICAL_PAUSE_END]
    for anchor in anchors:
        start = anchor + timedelta(days=1)
        end = anchor + timedelta(days=MEDICAL_RETURN_EASY_DAYS)
        if start <= day <= end:
            return True
    return False


def red_flag_reason(day: date) -> Optional[str]:
    """Illness 2-of-3, or a logged medical stop-symptom on this date."""
    from .history import list_session_notes
    from .modulation import _illness_triggers

    note = (list_session_notes().get(day.isoformat()) or "").lower()
    if any(phrase in note for phrase in RED_FLAG_PHRASES):
        return reason_text("red_flag")
    _triggers, illness = _illness_triggers(day)
    if illness:
        return reason_text("red_flag")
    return None


def _over_budget(total: float, budget: float) -> bool:
    return total > budget + 1e-6


def apply_caps(
    days: list[tuple[date, tuple]],
    *,
    previous_load: Optional[float] = None,
    previous_day: Optional[tuple] = None,
    red_flags: Optional[Mapping[date, object]] = None,
    loads: Optional[Mapping[date, float]] = None,
) -> list[CappedDay]:
    """Cap one Monday–Sunday week. ``days`` is seven ``(date, session)`` pairs.

    ``previous_load`` is the prior week's prescribed load in the same units.
    ``previous_day`` is that week's Sunday, so a hard Monday cannot follow it.
    ``loads`` overrides duration with TSS or Garmin training load for the
    percentage cap. ``red_flags`` marks dates that must be rest.
    """
    flags = red_flags or {}
    slots: list[_Slot] = []
    for day, session in days:
        norm = _norm(session)
        if loads is not None and day in loads:
            slots.append(_Slot(day, norm, float(loads[day]), False))
        else:
            slots.append(_Slot(day, norm, session_load(norm), True))

    for slot in slots:
        if flags.get(slot.date):
            if not is_rest(slot.session):
                slot.force(REST, "red_flag")
            else:
                slot.locked = True

    procedures = set(_procedure_dates())
    for slot in slots:
        if slot.date not in procedures or slot.locked:
            continue
        if not is_rest(slot.session):
            slot.force(REST, "procedure")
        else:
            slot.locked = True

    for slot in slots:
        if slot.locked or not in_easy_return(slot.date):
            continue
        if not is_return_safe(slot.session):
            slot.assign(as_easy(slot.session, max_min=EASY_ONLY_MAX_MIN), "medical_return")

    seen = 0
    for slot in slots:
        if not is_hard(slot.session):
            continue
        seen += 1
        if seen > MAX_HARD_SESSIONS_PER_WEEK:
            slot.assign(as_easy(slot.session), "hard_count")

    prev = _norm(previous_day) if previous_day is not None else None
    for slot in slots:
        if prev is not None and is_hard(prev) and is_hard(slot.session):
            slot.assign(as_easy(slot.session), "back_to_back")
        prev = slot.session

    rest_count = sum(1 for slot in slots if is_rest(slot.session))
    while rest_count < MIN_REST_DAYS_PER_WEEK:
        idx = _rest_candidate(slots)
        if idx is None:
            break
        slots[idx].assign(REST, "rest_day")
        rest_count += 1

    if previous_load is not None and previous_load > 0:
        budget = previous_load * (1.0 + MAX_WEEKLY_LOAD_INCREASE)
        guard = 0
        while _over_budget(_total(slots), budget) and guard < 400:
            guard += 1
            before = _total(slots)
            idx = _longest(slots)
            if idx is None:
                break
            _trim(slots[idx], _total(slots) - budget)
            if _total(slots) >= before - 1e-9:
                break

    out: list[CappedDay] = []
    for slot in slots:
        changed = slot.session != slot.original
        out.append(CappedDay(
            date=slot.date,
            original=slot.original,
            session=slot.session,
            reason=reason_text(slot.reason_code) if changed and slot.reason_code else None,
            load=slot.load,
        ))
    return out


def _total(slots: list[_Slot]) -> float:
    return sum(slot.load for slot in slots)


def _longest(slots: list[_Slot]) -> Optional[int]:
    best: Optional[int] = None
    best_key: Optional[tuple] = None
    for i, slot in enumerate(slots):
        if slot.locked or is_rest(slot.session) or slot.load <= 0:
            continue
        key = (slot.load, slot.session[2], i)
        if best_key is None or key > best_key:
            best_key = key
            best = i
    return best


def _rest_candidate(slots: list[_Slot]) -> Optional[int]:
    best: Optional[int] = None
    best_key: Optional[tuple] = None
    for i, slot in enumerate(slots):
        if slot.locked or is_rest(slot.session):
            continue
        key = (1 if is_hard(slot.session) else 0, slot.load, -i)
        if best_key is None or key < best_key:
            best_key = key
            best = i
    return best


def _trim(slot: _Slot, overflow: float) -> None:
    if slot.load_is_duration:
        cut = int(math.ceil(overflow - 1e-9))
        new_dur = slot.session[2] - cut
        if new_dur < MIN_USEFUL_MIN:
            slot.assign(REST, "weekly_load")
        else:
            slot.assign((slot.session[0], slot.session[1], new_dur), "weekly_load")
        return
    if slot.load <= 0:
        return
    new_load = slot.load - overflow
    ratio = new_load / slot.load if slot.load else 0.0
    new_dur = int(math.floor(slot.session[2] * ratio)) if slot.session[2] else 0
    if new_load <= 1e-6 or (slot.session[2] and new_dur < MIN_USEFUL_MIN):
        slot.session = REST
        slot.load = 0.0
        slot._note("weekly_load")
        return
    slot.session = (slot.session[0], slot.session[1], new_dur)
    slot.load = new_load
    slot._note("weekly_load")


def _lookup(day: date) -> Optional[tuple]:
    from .hr_plan import hr_session_for_date
    from .plan import session_for_date_extended
    return session_for_date_extended(day) or hr_session_for_date(day)


def _raw_week(monday: date) -> list[tuple[date, Session]]:
    out: list[tuple[date, Session]] = []
    for i in range(7):
        day = monday + timedelta(days=i)
        sess = _lookup(day)
        out.append((day, _norm(sess) if sess else REST))
    return out


def _week_has_plan(monday: date) -> bool:
    return any(_lookup(monday + timedelta(days=i)) for i in range(7))


def prescribed_week(
    monday: date,
    cache: Optional[dict] = None,
    *,
    symptoms: bool = True,
    depth: int = 0,
) -> list[CappedDay]:
    """Prescribed Monday–Sunday, capped against the previous prescribed week."""
    monday = monday - timedelta(days=monday.weekday())
    cache = cache if cache is not None else {}
    key = (monday.isoformat(), symptoms)
    if key in cache:
        return cache[key]

    previous_load: Optional[float] = None
    previous_day: Optional[Session] = None
    prev_monday = monday - timedelta(days=7)
    if depth < 120 and _week_has_plan(prev_monday):
        prev = prescribed_week(prev_monday, cache, symptoms=False, depth=depth + 1)
        previous_load = sum(day.load for day in prev)
        previous_day = prev[-1].session

    flags: dict[date, str] = {}
    if symptoms:
        for i in range(7):
            day = monday + timedelta(days=i)
            flag = red_flag_reason(day)
            if flag:
                flags[day] = flag

    capped = apply_caps(
        _raw_week(monday),
        previous_load=previous_load,
        previous_day=previous_day,
        red_flags=flags,
    )
    cache[key] = capped
    return capped


def prescribed_session(day: date) -> CappedDay:
    """The session to show or schedule for ``day`` after caps."""
    monday = day - timedelta(days=day.weekday())
    return prescribed_week(monday)[day.weekday()]


def cap_suggested_session(day: date, session: tuple) -> CappedDay:
    """Cap one AI or athlete suggestion against the rest of that week."""
    monday = day - timedelta(days=day.weekday())
    cache: dict = {}
    previous_load: Optional[float] = None
    previous_day: Optional[Session] = None
    prev_monday = monday - timedelta(days=7)
    if _week_has_plan(prev_monday):
        prev = prescribed_week(prev_monday, cache, symptoms=False)
        previous_load = sum(item.load for item in prev)
        previous_day = prev[-1].session
    days = _raw_week(monday)
    days[day.weekday()] = (day, _norm(session))
    flags: dict[date, str] = {}
    flag = red_flag_reason(day)
    if flag:
        flags[day] = flag
    return apply_caps(
        days,
        previous_load=previous_load,
        previous_day=previous_day,
        red_flags=flags,
    )[day.weekday()]


def cap_proposal(proposal: dict) -> dict:
    """Rewrite a coach ``propose_plan_change`` payload so it respects the caps."""
    try:
        day = date.fromisoformat(str(proposal.get("date") or ""))
    except ValueError:
        return proposal
    stype = proposal.get("session_type")
    label = proposal.get("session_label") or proposal.get("label")
    dur = proposal.get("duration_min")
    if not stype or not label or dur is None:
        return proposal
    capped = cap_suggested_session(day, (stype, label, int(dur)))
    if not capped.changed:
        return proposal
    out = dict(proposal)
    out["session_type"] = capped.session[0]
    out["session_label"] = capped.session[1]
    out["label"] = capped.session[1]
    out["duration_min"] = capped.session[2]
    out["safety_line"] = capped.reason
    prior = (out.get("reason") or "").strip()
    out["reason"] = f"{prior} {capped.reason}".strip() if prior else capped.reason
    return out

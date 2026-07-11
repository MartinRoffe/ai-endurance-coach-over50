"""Haute Route Alpes 2027 — 10-month training plan (Oct 2026 → Aug 2027).

Plan start: Mon 5 Oct 2026 (3 weeks post charity ride)
Event:      Mon 23 Aug – Sun 29 Aug 2027 (7 stages, 808 km, 19,255 m)

Phase structure:
  Phase 1 — Base          Wks  1–13   Oct  5 → Jan  3  (aerobic engine + gym;
                                                       Tenerife volume camp wks 12–13)
  Phase 2 — Build         Wks 14–25   Jan  4 → Mar 28  (wk 14 absorbs camp; then FTP/VO2/TTE)
  Phase 3 — Specific      Wks 26–35   Mar 29 → Jun  7  (back-to-back + Tenerife race-sim camp wk 31)
  Phase 4 — Peak          Wks 36–43   Jun  8 → Aug  2  (multi-day simulation)
  Phase 5 — Taper         Wks 44–46   Aug  3 → Aug 22  (arrive fresh)
  Event                              Aug 23 – Aug 29

Tenerife camps (bike hire windows):
  Christmas volume camp — arrive 22 Dec 2026, bike 23–31 Dec, home 2 Jan 2027
    (August-style overload: hard/easy rhythm, Teide repeats — Base aerobic boost)
  May race-simulation camp — wk 31 (from 3 May 2027): consecutive stage-sim days
    rehearsing Haute Route pacing, fuelling, and back-to-back mountain fatigue
"""
from __future__ import annotations

from datetime import date, timedelta

HR_EVENT_NAME = "Haute Route Alpes 2027"
HR_PLAN_START = date(2026, 10, 5)
assert HR_PLAN_START.weekday() == 0, "Plan must start on Monday"

HR_EVENT_START = date(2027, 8, 23)
HR_EVENT_END   = date(2027, 8, 29)

# Phase metadata — week_start/week_end are 1-indexed, inclusive
HR_PHASES: list[dict] = [
    {"name": "base",     "label": "Base",          "colour": "emerald", "week_start":  1, "week_end": 13},
    {"name": "build",    "label": "Build",          "colour": "blue",    "week_start": 14, "week_end": 25},
    {"name": "specific", "label": "Specific Build", "colour": "violet",  "week_start": 26, "week_end": 35},
    {"name": "peak",     "label": "Peak",           "colour": "orange",  "week_start": 36, "week_end": 43},
    {"name": "taper",    "label": "Taper",          "colour": "rose",    "week_start": 44, "week_end": 46},
]

# Session types used in this plan:
#   rest | endurance | sweetspot | tempo | vo2 | recovery | long | ftp | gym | back_to_back
#
# Each week: list of 7 sessions Mon–Sun, each (type, label, duration_min)

HR_TRAINING_WEEKS: list[list[tuple[str, str, int]]] = [

    # ── PHASE 1: BASE ──────────────────────────────────────────────────────────
    # Goal: aerobic engine, structural durability, gym strength. 7–11 hrs/wk.
    # 3:1 build:deload cadence. FTP baseline in wk 8.

    # WK 01 — Transition · 7 hrs (Oct 5)01
    [
        ("rest",      "Rest",                    0),
        ("endurance", "Z2 Endurance",           60),
        ("sweetspot", "Low Cadence Sweetspot",  60),
        ("recovery",  "Recovery + Core",        45),
        ("endurance", "Z2 Steady",              60),
        ("gym",       "Gym — Strength",         60),
        ("long",      "Long Ride",              90),
    ],
    # WK 02 — Base build · 8 hrs (Oct 12)02
    [
        ("rest",      "Rest",                    0),
        ("endurance", "Z2 Endurance",           60),
        ("sweetspot", "Low Cadence Sweetspot",  60),
        ("recovery",  "Recovery + Core",        45),
        ("tempo",     "Tempo Intervals 2×20",   75),
        ("gym",       "Gym — Strength",         60),
        ("long",      "Long Ride",             120),
    ],
    # WK 03 — Base build · 9 hrs (Oct 19)03
    [
        ("rest",      "Rest",                    0),
        ("endurance", "Z2 Endurance",           60),
        ("sweetspot", "Low Cadence Sweetspot",  60),
        ("recovery",  "Recovery + Core",        45),
        ("tempo",     "Tempo Intervals 2×20",   75),
        ("gym",       "Gym — Strength",         60),
        ("long",      "Long Ride",             150),
    ],
    # WK 04 — Deload · 6 hrs (Oct 26)04
    [
        ("rest",      "Rest",                    0),
        ("endurance", "Z2 Easy",                45),
        ("recovery",  "Recovery Spin",          45),
        ("rest",      "Rest",                    0),
        ("endurance", "Z2 Easy",                45),
        ("gym",       "Gym — Maintenance",      45),
        ("long",      "Long Ride (Easy)",       75),
    ],
    # WK 05 — Base build · 9 hrs (Nov 2)05
    [
        ("rest",      "Rest",                    0),
        ("endurance", "Z2 Endurance",           60),
        ("sweetspot", "Low Cadence Sweetspot",  60),
        ("recovery",  "Recovery + Core",        45),
        ("tempo",     "Tempo Intervals 2×20",   90),
        ("gym",       "Gym — Strength",         60),
        ("long",      "Long Ride",             150),
    ],
    # WK 06 — Base build · 10 hrs (Nov 9)06
    [
        ("rest",      "Rest",                    0),
        ("endurance", "Z2 Endurance",           60),
        ("sweetspot", "Low Cadence Sweetspot",  75),
        ("recovery",  "Recovery + Core",        45),
        ("tempo",     "Tempo Intervals 2×20",   90),
        ("gym",       "Gym — Strength",         60),
        ("long",      "Long Ride",             180),
    ],
    # WK 07 — Base build · 10 hrs (Nov 16)07
    [
        ("rest",      "Rest",                    0),
        ("endurance", "Z2 Endurance",           60),
        ("sweetspot", "Low Cadence Sweetspot",  75),
        ("recovery",  "Recovery + Core",        45),
        ("tempo",     "Tempo Intervals 3×15",   90),
        ("gym",       "Gym — Strength",         60),
        ("long",      "Long Ride",             180),
    ],
    # WK 08 — Deload + FTP Baseline · 7 hrs (Nov 23)08
    [
        ("rest",      "Rest",                    0),
        ("ftp",       "FTP Baseline Test",      60),
        ("recovery",  "Recovery Spin",          45),
        ("rest",      "Rest",                    0),
        ("endurance", "Z2 Easy",                45),
        ("gym",       "Gym — Maintenance",      45),
        ("long",      "Long Ride (Easy)",       90),
    ],
    # WK 09 — Base build · 10 hrs (Nov 30)09
    [
        ("rest",      "Rest",                    0),
        ("endurance", "Z2 Endurance",           60),
        ("sweetspot", "Low Cadence Sweetspot",  75),
        ("recovery",  "Recovery + Core",        45),
        ("tempo",     "Tempo Intervals 3×20",  105),
        ("gym",       "Gym — Strength",         60),
        ("long",      "Long Ride",             210),
    ],
    # WK 10 — Base build · 11 hrs (Dec 7)10
    [
        ("rest",      "Rest",                    0),
        ("endurance", "Z2 Endurance",           60),
        ("sweetspot", "Low Cadence Sweetspot",  75),
        ("recovery",  "Recovery + Core",        45),
        ("tempo",     "Tempo Intervals 3×20",  105),
        ("gym",       "Gym — Strength",         60),
        ("long",      "Long Ride",             240),
    ],
    # WK 11 — Base peak · 11 hrs (Dec 14)11
    # Final UK quality week before Tenerife — arrive at camp fit, not flat.
    [
        ("rest",      "Rest",                    0),
        ("endurance", "Z2 Endurance",           60),
        ("sweetspot", "Low Cadence Sweetspot",  75),
        ("recovery",  "Recovery + Core",        45),
        ("tempo",     "Tempo Intervals 3×20",  105),
        ("gym",       "Gym — Strength",         60),
        ("long",      "Long Ride",             270),
    ],
    # WK 12 — Tenerife Christmas camp · week 1 · ~12 hrs (Dec 21)12
    # Arrive Tue 22 Dec; bike hire Wed 23–Thu 31 Dec. August-style hard/easy
    # overload (Teide repeats) — the Base aerobic volume boost.
    [
        ("rest",      "Tenerife — Pre-Camp Rest",       0),   # Mon 21
        ("rest",      "Tenerife — Travel Arrive",       0),   # Tue 22
        ("long",      "Tenerife — Leg Openers",       120),   # Wed 23
        ("long",      "Tenerife — Tamaimo / Teno",    210),   # Thu 24
        ("endurance", "Tenerife — Christmas Easy",     90),   # Fri 25
        ("long",      "Tenerife — Teide West",        300),   # Sat 26
        ("rest",      "Tenerife — Mid-Camp Rest",       0),   # Sun 27
    ],
    # WK 13 — Tenerife Christmas camp · week 2 · ~18.5 hrs (Dec 28)13
    # Three hard mountain days including the finale on last hire day (31 Dec).
    # No bike 1 Jan; fly home 2 Jan; full rest 3 Jan before Build absorption.
    [
        ("long",      "Tenerife — Masca + North",     330),   # Mon 28
        ("recovery",  "Tenerife — Active Recovery",    90),   # Tue 29
        ("long",      "Tenerife — Teide Full Loop",   330),   # Wed 30
        ("long",      "Tenerife — Camp Finale",       360),   # Thu 31 — last hire day
        ("rest",      "Tenerife — New Year Rest",       0),   # Fri 1 Jan
        ("rest",      "Tenerife — Travel Home",         0),   # Sat 2 Jan
        ("rest",      "Tenerife — Post-Camp Rest",      0),   # Sun 3 Jan
    ],

    # ── PHASE 2: BUILD ─────────────────────────────────────────────────────────
    # Goal: raise FTP, extend TTE, VO2 max development. 10–14 hrs/wk.
    # VO2 replaces easy Z2 on Tuesdays. Sundays extend to 5+ hrs by end of phase.
    # Wk 14 absorbs the Christmas camp before quality work resumes.

    # WK 14 — Post-camp absorption · ~5.5 hrs (Jan 4)14
    # Deliberately easy — let the Tenerife overload land before VO2/Build quality.
    [
        ("rest",      "Rest",                    0),
        ("endurance", "Z2 Easy",                45),
        ("recovery",  "Recovery Spin",          45),
        ("recovery",  "Strength + Core",        60),
        ("endurance", "Z2 Easy",                45),
        ("endurance", "Z2 Easy",                45),
        ("long",      "Long Ride (Easy)",       90),
    ],
    # WK 15 — Build re-entry · ~8.5 hrs (Jan 11)15
    # Soft first quality week after Christmas camp soak (wk 14) — VO2 4×3 only,
    # long capped at 3 h. Full Build dose resumes wk 16 neighbour / wk 18.
    [
        ("rest",      "Rest",                    0),
        ("vo2",       "VO2 Intervals 4×3 min",  60),
        ("sweetspot", "Low Cadence Sweetspot",  60),
        ("recovery",  "Strength + Core",        60),
        ("tempo",     "Tempo Intervals 2×15",   75),
        ("endurance", "Z2 Endurance",           60),
        ("long",      "Long Ride",             180),
    ],
    # WK 16 — Absorption · ~8.5 hrs (Jan 18)16
    # Was a 3rd consecutive build week; softened to a reduced-load absorption week
    # to give a masters-friendly 2:1 load:recovery rhythm (VO2 dropped to Z2, long
    # ride and tempo trimmed). Lowers projected CTL here by design.
    [
        ("rest",      "Rest",                    0),
        ("endurance", "Z2 Endurance",           60),
        ("sweetspot", "Low Cadence Sweetspot",  60),
        ("recovery",  "Strength + Core",        60),
        ("tempo",     "Tempo Intervals 2×15",   75),
        ("endurance", "Z2 Easy",                45),
        ("long",      "Long Ride",             180),
    ],
    # WK 17 — Deload · 7 hrs (Jan 25)17
    [
        ("rest",      "Rest",                    0),
        ("vo2",       "VO2 Intervals 4×3 min",  60),
        ("recovery",  "Recovery Spin",          45),
        ("rest",      "Rest",                    0),
        ("tempo",     "Tempo Intervals 2×15",   75),
        ("endurance", "Z2 Easy",                45),
        ("long",      "Long Ride (Easy)",       90),
    ],
    # WK 18 — Build · 12 hrs (Feb 1)18
    # First full Build quality week (VO2 6×3) after post-camp re-entry.
    [
        ("rest",      "Rest",                    0),
        ("vo2",       "VO2 Intervals 6×3 min",  60),
        ("sweetspot", "Low Cadence Sweetspot",  75),
        ("recovery",  "Strength + Core",        60),
        ("tempo",     "Tempo Intervals 3×20",  105),
        ("endurance", "Z2 Endurance",           75),
        ("long",      "Long Ride",             270),
    ],
    # WK 19 — Build · 12 hrs (Feb 8)19
    [
        ("rest",      "Rest",                    0),
        ("vo2",       "VO2 Intervals 6×3 min",  60),
        ("sweetspot", "Low Cadence Sweetspot",  90),
        ("recovery",  "Strength + Core",        60),
        ("tempo",     "Tempo Intervals 3×20",  105),
        ("endurance", "Z2 Endurance",           75),
        ("long",      "Long Ride",             270),
    ],
    # WK 20 — Absorption · ~9 hrs (Feb 15)20
    # 3rd consecutive build week softened to an absorption week (2:1 rhythm).
    [
        ("rest",      "Rest",                    0),
        ("endurance", "Z2 Endurance",           60),
        ("sweetspot", "Low Cadence Sweetspot",  60),
        ("recovery",  "Strength + Core",        60),
        ("tempo",     "Tempo Intervals 2×15",   75),
        ("endurance", "Z2 Easy",                45),
        ("long",      "Long Ride",             210),
    ],
    # WK 21 — Deload + FTP Re-test · 8 hrs (Feb 22)21
    [
        ("rest",      "Rest",                    0),
        ("ftp",       "FTP Re-test",            60),
        ("recovery",  "Recovery Spin",          45),
        ("rest",      "Rest",                    0),
        ("tempo",     "Tempo Intervals 2×15",   75),
        ("endurance", "Z2 Easy",                60),
        ("long",      "Long Ride (Easy)",      105),
    ],
    # WK 22 — Build · 13 hrs (Mar 1)22
    [
        ("rest",      "Rest",                    0),
        ("vo2",       "VO2 Intervals 5×4 min",  75),
        ("sweetspot", "Low Cadence Sweetspot",  90),
        ("recovery",  "Strength + Core",        60),
        ("tempo",     "Under-Overs 3×10 min",  105),
        ("endurance", "Z2 Endurance",           90),
        ("long",      "Long Ride",             300),
    ],
    # WK 23 — Build · 13 hrs (Mar 8)23
    [
        ("rest",      "Rest",                    0),
        ("vo2",       "VO2 Intervals 5×4 min",  75),
        ("sweetspot", "Low Cadence Sweetspot",  90),
        ("recovery",  "Strength + Core",        60),
        ("tempo",     "Under-Overs 3×10 min",  105),
        ("endurance", "Z2 Endurance",           90),
        ("long",      "Long Ride",             330),
    ],
    # WK 24 — Build peak · 14 hrs (Mar 15)24
    [
        ("rest",      "Rest",                    0),
        ("vo2",       "VO2 Intervals 5×4 min",  75),
        ("sweetspot", "Low Cadence Sweetspot",  90),
        ("recovery",  "Strength + Core",        60),
        ("tempo",     "Under-Overs 3×10 min",  105),
        ("endurance", "Z2 Endurance",           90),
        ("long",      "Long Ride",             360),
    ],
    # WK 25 — Deload · 8 hrs (Mar 22)25
    [
        ("rest",      "Rest",                    0),
        ("endurance", "Z2 Easy",                60),
        ("recovery",  "Recovery Spin",          45),
        ("rest",      "Rest",                    0),
        ("tempo",     "Tempo Intervals 2×15",   75),
        ("endurance", "Z2 Endurance",           60),
        ("long",      "Long Ride (Easy)",      120),
    ],

    # ── PHASE 3: SPECIFIC BUILD ────────────────────────────────────────────────
    # Goal: multi-day fatigue resistance, climbing volume, back-to-back days.
    # 5-day mountain training camp in wk 31. 14–16 hrs/wk at peak.

    # WK 26 — Specific entry · 14 hrs (Mar 29)26
    [
        ("rest",         "Rest",                    0),
        ("vo2",          "VO2 Intervals 5×4 min",  75),
        ("sweetspot",    "Low Cadence Sweetspot",  90),
        ("recovery",     "Strength + Core",        60),
        ("tempo",        "Under-Overs 3×10 min",  105),
        ("back_to_back", "Back-to-Back Day 1",    210),
        ("back_to_back", "Back-to-Back Day 2",    150),
    ],
    # WK 27 — Specific · 15 hrs (Apr 5)27
    [
        ("rest",         "Rest",                    0),
        ("vo2",          "VO2 Intervals 5×4 min",  75),
        ("sweetspot",    "Low Cadence Sweetspot",  90),
        ("recovery",     "Strength + Core",        60),
        ("tempo",        "Under-Overs 3×10 min",  105),
        ("back_to_back", "Back-to-Back Day 1",    240),
        ("back_to_back", "Back-to-Back Day 2",    180),
    ],
    # WK 28 — Absorption · ~9.5 hrs (Apr 12)28
    # 3rd consecutive specific-build week softened to an absorption week (2:1).
    # Keeps a SHORTER back-to-back to retain multi-day specificity, drops the
    # VO2 + under-overs to Z2, trims volume.
    [
        ("rest",         "Rest",                    0),
        ("endurance",    "Z2 Endurance",           60),
        ("sweetspot",    "Low Cadence Sweetspot",  75),
        ("recovery",     "Strength + Core",        60),
        ("endurance",    "Z2 Endurance",           75),
        ("back_to_back", "Back-to-Back Day 1 (Easy)", 180),
        ("back_to_back", "Back-to-Back Day 2 (Easy)", 120),
    ],
    # WK 29 — Deload · 9 hrs (Apr 19)29
    [
        ("rest",      "Rest",                    0),
        ("vo2",       "VO2 Intervals 4×3 min",  60),
        ("recovery",  "Recovery Spin",          45),
        ("rest",      "Rest",                    0),
        ("tempo",     "Tempo Intervals 2×20",   90),
        ("endurance", "Z2 Endurance",           75),
        ("long",      "Long Ride (Easy)",      150),
    ],
    # WK 30 — Specific build · 16 hrs (Apr 26)30
    [
        ("rest",         "Rest",                    0),
        ("vo2",          "VO2 Intervals 5×4 min",  75),
        ("sweetspot",    "Low Cadence Sweetspot",  90),
        ("recovery",     "Strength + Core",        60),
        ("tempo",        "Under-Overs 3×12 min",  105),
        ("back_to_back", "Back-to-Back Day 1",    300),
        ("back_to_back", "Back-to-Back Day 2",    210),
    ],
    # WK 31 — TENERIFE RACE-SIMULATION CAMP · Haute Route rehearsal (May 3)31
    # Second Tenerife overload: consecutive stage-sim days practising pacing,
    # fuelling, and back-to-back mountain fatigue — closer to race week than the
    # Christmas volume camp. Indicative sessions; adapt on the ground.
    [
        ("long",         "Camp — Arrival + Leg Openers", 120),
        ("back_to_back", "Camp — Stage Sim 1",           360),
        ("back_to_back", "Camp — Stage Sim 2",           330),
        ("recovery",     "Camp — Active Recovery",       120),
        ("back_to_back", "Camp — Stage Sim 3",           360),
        ("back_to_back", "Camp — Stage Sim 4",           300),
        ("rest",         "Camp — Rest / Travel Home",      0),
    ],
    # WK 32 — Post-camp recovery · 7 hrs (May 10)32
    # Masters soak week 1 after May race-sim — no FTP yet; legs absorb camp first.
    [
        ("rest",      "Rest",                    0),
        ("recovery",  "Recovery Spin",          45),
        ("endurance", "Z2 Easy",                45),
        ("recovery",  "Recovery + Core",        45),
        ("endurance", "Z2 Easy",                45),
        ("endurance", "Z2 Endurance",           60),
        ("long",      "Long Ride (Easy)",      120),
    ],
    # WK 33 — Post-camp re-entry · ~11 hrs (May 17)33
    # Second soak / progressive return — no VO2, shortened BTB before Specific resumes.
    # Former 16 h BTB peak deferred to wk 34.
    [
        ("rest",         "Rest",                    0),
        ("endurance",    "Z2 Endurance",           60),
        ("sweetspot",    "Low Cadence Sweetspot",  60),
        ("recovery",     "Strength + Core",        60),
        ("tempo",        "Tempo Intervals 2×15",   75),
        ("back_to_back", "Back-to-Back Day 1",    210),
        ("back_to_back", "Back-to-Back Day 2",    150),
    ],
    # WK 34 — Specific peak · 16 hrs (May 24)34
    # Full Specific load resumes after two post-camp soak weeks; FTP re-test Tue.
    [
        ("rest",         "Rest",                    0),
        ("ftp",          "FTP Re-test",            60),
        ("sweetspot",    "Low Cadence Sweetspot",  90),
        ("recovery",     "Strength + Core",        60),
        ("tempo",        "Under-Overs 3×12 min",  105),
        ("back_to_back", "Back-to-Back Day 1",    330),
        ("back_to_back", "Back-to-Back Day 2",    240),
    ],
    # WK 35 — Deload · 9 hrs (May 31)35
    [
        ("rest",      "Rest",                    0),
        ("vo2",       "VO2 Intervals 4×3 min",  60),
        ("recovery",  "Recovery Spin",          45),
        ("rest",      "Rest",                    0),
        ("tempo",     "Tempo Intervals 2×20",   90),
        ("endurance", "Z2 Endurance",           90),
        ("long",      "Long Ride (Easy)",      165),
    ],

    # ── PHASE 4: PEAK ──────────────────────────────────────────────────────────
    # Goal: event simulation, peak durability. Two 3-day simulation blocks.
    # 14–17 hrs/wk. Gym dropped to maintenance only.

    # WK 36 — Peak entry · 15 hrs (Jun 7)36
    [
        ("rest",         "Rest",                    0),
        ("tempo",        "Under-Overs 3×12 min",   90),
        ("sweetspot",    "Low Cadence Sweetspot",  75),
        ("recovery",     "Strength + Core",        60),
        ("endurance",    "Z2 Endurance",           90),
        ("back_to_back", "Simulation Day 1",      330),
        ("back_to_back", "Simulation Day 2",      270),
    ],
    # WK 37 — Peak · 17 hrs — first 3-day block (Jun 14)37
    [
        ("rest",         "Rest",                    0),
        ("tempo",        "Under-Overs 3×12 min",   90),
        ("sweetspot",    "Low Cadence Sweetspot",  75),
        ("recovery",     "Strength + Core",        60),
        ("back_to_back", "Simulation Day 1",      330),
        ("back_to_back", "Simulation Day 2",      300),
        ("back_to_back", "Simulation Day 3",      210),
    ],
    # WK 38 — Deload · 8 hrs (Jun 21)38
    [
        ("rest",      "Rest",                    0),
        ("recovery",  "Recovery Spin",          60),
        ("endurance", "Z2 Endurance",           60),
        ("rest",      "Rest",                    0),
        ("tempo",     "Tempo Intervals 2×20",   90),
        ("endurance", "Z2 Endurance",           75),
        ("long",      "Long Ride (Easy)",      120),
    ],
    # WK 39 — Peak · 17 hrs — second 3-day block (Jun 28)39
    [
        ("rest",         "Rest",                    0),
        ("tempo",        "Under-Overs 3×12 min",   90),
        ("sweetspot",    "Low Cadence Sweetspot",  75),
        ("recovery",     "Strength + Core",        60),
        ("back_to_back", "Simulation Day 1",      360),
        ("back_to_back", "Simulation Day 2",      330),
        ("back_to_back", "Simulation Day 3",      240),
    ],
    # WK 40 — Absorption · ~11 hrs (Jul 5)40
    # Breaks up a 4-week unbroken peak stretch (wks 39–42, deloads only at 38/43):
    # softened to an absorption week so there is real recovery BETWEEN the two
    # 3-day simulation blocks (wk39 and wk42). Masters athletes can't absorb four
    # consecutive peak weeks. Intensity dropped to Z2, sim block shortened.
    [
        ("rest",         "Rest",                    0),
        ("recovery",     "Recovery Spin",          60),
        ("endurance",    "Z2 Endurance",           75),
        ("recovery",     "Strength + Core",        60),
        ("endurance",    "Z2 Endurance",           90),
        ("long",         "Long Ride",             210),
        ("long",         "Long Ride (Easy)",      150),
    ],
    # WK 41 — Peak prep · 12 hrs (Jul 12)41
    # No FTP test here — keeps the week clean before the final 3-day sim (wk 42).
    # Final FTP moved to wk 43 deload Tuesday.
    [
        ("rest",      "Rest",                    0),
        ("endurance", "Z2 Endurance",           75),
        ("sweetspot", "Low Cadence Sweetspot",  75),
        ("recovery",  "Strength + Core",        60),
        ("tempo",     "Under-Overs 3×10 min",   90),
        ("endurance", "Z2 Endurance",           90),
        ("long",      "Long Ride",             240),
    ],
    # WK 42 — Peak final block · 16 hrs (Jul 19)42
    [
        ("rest",         "Rest",                    0),
        ("tempo",        "Under-Overs 3×12 min",   90),
        ("sweetspot",    "Low Cadence Sweetspot",  75),
        ("recovery",     "Strength + Core",        60),
        ("back_to_back", "Simulation Day 1",      330),
        ("back_to_back", "Simulation Day 2",      300),
        ("back_to_back", "Simulation Day 3",      210),
    ],
    # WK 43 — Pre-taper deload + FTP Final · 9 hrs (Jul 26)43
    [
        ("rest",      "Rest",                    0),
        ("ftp",       "FTP Final Test",         60),
        ("recovery",  "Recovery Spin",          45),
        ("recovery",  "Recovery + Core",        45),
        ("tempo",     "Tempo Intervals 2×15",   75),
        ("endurance", "Z2 Endurance",           60),
        ("long",      "Long Ride (Easy)",      120),
    ],

    # ── PHASE 5: TAPER ─────────────────────────────────────────────────────────
    # 60% → 40% → race-week volume. Same intensity, halved duration.

    # WK 44 — Taper wk 1 · ~6 hrs (Aug 2)44
    [
        ("rest",      "Rest",                    0),
        ("tempo",     "Under-Overs 2×10 min",   75),
        ("sweetspot", "Low Cadence Sweetspot",  60),
        ("recovery",  "Recovery + Core",        45),
        ("endurance", "Z2 Endurance",           60),
        ("endurance", "Z2 Easy",                45),
        ("long",      "Long Ride (Moderate)",  180),
    ],
    # WK 45 — Taper wk 2 · ~4 hrs (Aug 9)45
    # Heat protocol starts in the final 10 days (from Fri 13 Aug).
    [
        ("rest",      "Rest",                    0),
        ("tempo",     "Tempo Sharpener",        60),
        ("recovery",  "Recovery Spin",          45),
        ("rest",      "Rest",                    0),
        ("endurance", "Heat Z2",                60),   # heat 1/5 — Fri 13 Aug
        ("endurance", "Z2 Easy",                45),
        ("endurance", "Heat Z2",                60),   # heat 2/5 — Sun 15 Aug
    ],
    # WK 46 — Race week · arrive fresh (Aug 16)46
    # Heat sessions 3–5; last heat Fri 20 Aug (= event − 3 days).
    [
        ("rest",      "Rest",                    0),
        ("endurance", "Heat Z2",                60),   # heat 3/5 — Tue 17 Aug
        ("endurance", "Heat Z2",                60),   # heat 4/5 — Wed 18 Aug
        ("recovery",  "Leg Openers",            30),
        ("endurance", "Heat Z2",                60),   # heat 5/5 — Fri 20 Aug (event − 3)
        ("rest",      "Rest",                    0),
        ("rest",      "Travel — Nice",           0),
    ],
]


def _destack_quality(weeks: list[list[tuple[str, str, int]]]) -> list[list[tuple[str, str, int]]]:
    """Insert the mid-week recovery day BETWEEN two adjacent quality days.

    The Build/Specific/Peak template runs Tue = hardest quality (VO2 or
    under-overs), Wed = sweetspot, Thu = recovery (Strength + Core). That stacks
    two quality days back-to-back — too much intensity density for a 50+ athlete.
    Where that exact Tue-quality / Wed-sweetspot / Thu-recovery pattern occurs,
    swap Wed and Thu so the hardest session (Tue) is flanked by Mon rest and Wed
    recovery, and the two remaining quality days (Thu sweetspot, Fri tempo) are
    the less-taxing ones.

    Reordering only — weekly duration and per-type totals are unchanged, so
    `_hr_ctl_projection` (which sums each week) is unaffected. Applied once to the
    single source of truth so the calendar, session lookup and projection all see
    the same order, and any future week matching the pattern is handled too.
    """
    QUALITY = {"vo2", "tempo"}
    for wk in weeks:
        if (len(wk) == 7 and wk[1][0] in QUALITY
                and wk[2][0] == "sweetspot" and wk[3][0] == "recovery"):
            wk[2], wk[3] = wk[3], wk[2]
    return weeks


HR_TRAINING_WEEKS = _destack_quality(HR_TRAINING_WEEKS)

# ── Event stages ──────────────────────────────────────────────────────────────
HR_EVENT_STAGES: list[dict] = [
    {"day": 1, "date": date(2027, 8, 23), "label": "Nice → Cuneo",             "km": 182, "elev_m": 4020, "key_climb": "Col de la Lombarde 2340m"},
    {"day": 2, "date": date(2027, 8, 24), "label": "Cuneo → Col d'Izoard",     "km": 141, "elev_m": 3610, "key_climb": "Col d'Agnel 2744m"},
    {"day": 3, "date": date(2027, 8, 25), "label": "Briançon → Alpe d'Huez",  "km": 81,  "elev_m": 2375, "key_climb": "Col du Lautaret 2060m"},
    {"day": 4, "date": date(2027, 8, 26), "label": "TT — Alpe d'Huez",        "km": 16,  "elev_m": 1125, "key_climb": "Alpe d'Huez — 21 hairpins"},
    {"day": 5, "date": date(2027, 8, 27), "label": "Alpe d'Huez → Megève",    "km": 169, "elev_m": 3525, "key_climb": "Col du Glandon 1924m"},
    {"day": 6, "date": date(2027, 8, 28), "label": "Megève → Côte 2000",      "km": 100, "elev_m": 2560, "key_climb": "Col de la Colombière 1609m"},
    {"day": 7, "date": date(2027, 8, 29), "label": "Megève → Thonon-les-Bains","km": 119, "elev_m": 2040, "key_climb": "Col de Joux-Plane 1712m"},
]

# Heat protocol — sessions are scheduled as "Heat Z2" endurance rides in wks 45–46
# (5×60 min; last on Fri 20 Aug = event − 3 days). Banner summarises the protocol.
HR_HEAT_PROTOCOL: dict = {
    "phase": "taper",
    "start_week": 45,
    "title": "Heat protocol — final 10 days (scheduled)",
    "note": (
        "Five Heat Z2 sessions are on the calendar (Fri 13, Sun 15, Tue 17, Wed 18, "
        "Fri 20 Aug) — extra layers or indoor trainer with no fan. Last session is "
        "3 days pre-event. Sodium 500–800 mg/h; weigh before/after to calibrate fluid loss."
    ),
}

# ── Power prescription metadata (display + coach; tuples untouched) ───────────

HR_POWER_TARGETS: dict[str, tuple[int, int]] = {
    "endurance": (56, 75),
    "sweetspot": (88, 94),
    "tempo": (76, 90),
    "vo2": (106, 120),
    "ftp": (95, 105),
    "long": (56, 75),
    "back_to_back": (56, 75),
    "recovery": (0, 55),
}

HR_POWER_LABEL_OVERRIDES: dict[str, str] = {
    "Under-Overs 2×10 min": "alternate 95%/105% FTP",
    "Under-Overs 3×10 min": "alternate 95%/105% FTP",
    "Under-Overs 3×12 min": "alternate 95%/105% FTP",
    "Long Ride": "cap sustained climbs at 70–80% FTP",
    "Long Ride (Moderate)": "cap sustained climbs at 70–80% FTP",
    "Back-to-Back Day 1": "cap sustained climbs at 70–80% FTP",
    "Back-to-Back Day 2": "cap sustained climbs at 70–80% FTP",
    "Camp — Mountain Stage": "cap sustained climbs at 70–80% FTP",
    "Camp — Summit Day": "cap sustained climbs at 70–80% FTP",
    "Camp — Stage Sim 1": "cap sustained climbs at 70–80% FTP — race-week pacing",
    "Camp — Stage Sim 2": "cap sustained climbs at 70–80% FTP — race-week pacing",
    "Camp — Stage Sim 3": "cap sustained climbs at 70–80% FTP — race-week pacing",
    "Camp — Stage Sim 4": "cap sustained climbs at 70–80% FTP — race-week pacing",
    "Tenerife — Leg Openers": "Z1–2 only — travel shakeout",
    "Tenerife — Tamaimo / Teno": "cap sustained climbs at 70–80% FTP",
    "Tenerife — Christmas Easy": "Z1–2 coffee pace",
    "Tenerife — Teide West": "cap sustained climbs at 70–80% FTP",
    "Tenerife — Masca + North": "cap sustained climbs at 70–80% FTP",
    "Tenerife — Teide Full Loop": "cap sustained climbs at 70–80% FTP",
    "Tenerife — Camp Finale": "cap sustained climbs at 70–80% FTP — last hire day",
    "Tenerife — Active Recovery": "Z1 only",
    "Simulation Day 1": "cap sustained climbs at 70–80% FTP",
    "Simulation Day 2": "cap sustained climbs at 70–80% FTP",
    "Simulation Day 3": "cap sustained climbs at 70–80% FTP",
}

HR_TYPICAL_IF: dict[str, float] = {
    "endurance": 0.65,
    "sweetspot": 0.91,
    "tempo": 0.83,
    "vo2": 1.05,
    "ftp": 1.00,
    "long": 0.67,
    "back_to_back": 0.67,
    "recovery": 0.55,
}


def power_target_for(stype: str, label: str) -> tuple[int, int] | str | None:
    """%FTP range or coaching override string for an HR-plan session."""
    if label in HR_POWER_LABEL_OVERRIDES:
        return HR_POWER_LABEL_OVERRIDES[label]
    return HR_POWER_TARGETS.get(stype)


def power_watts_range(ftp_w: int, target: tuple[int, int] | str | None) -> str | None:
    if not target or not ftp_w:
        return target if isinstance(target, str) else None
    if isinstance(target, str):
        return target
    lo, hi = target
    return f"{round(ftp_w * lo / 100)}–{round(ftp_w * hi / 100)} W ({lo}–{hi}% FTP)"


# ── Lessons from the failed 2012 Haute Route attempt ──────────────────────────
# Derived from analysis of the athlete's own 2012 TCX files (inaugural Haute
# Route Alps, Geneva→Nice). He was pulled by the broom wagon on Day 3 after the
# first climb — a depletion blow-up — and rested Day 4 (Alpe d'Huez TT). The HR
# data is the trustworthy axis (the 2012 "power" was strap-estimated virtual
# power). Surfaced as a banner on /haute-route AND injected into coach context so
# pacing/fuelling advice is anchored to what actually went wrong last time.
LESSONS_2012: dict = {
    "title": "Lessons from 2012 (DNF — broom wagon, Day 3)",
    "summary": (
        "Failed the inaugural Haute Route in 2012: pulled by the broom wagon on Day 3 "
        "after the first climb, then forced to rest Day 4 (the Alpe d'Huez TT). The "
        "ride files show it was an executional failure, not a fitness ceiling."
    ),
    "evidence": [
        "Day 1 raced like a one-day event — 54% of 6+ hours above 80% of max HR, "
        "9% above 90%. The whole week's matches spent on the opening stage.",
        "Day 2 the top end vanished (time above 90% HRmax fell 9%→0%) — an unread "
        "fatigue warning.",
        "Day 3 depletion blow-up, visible in HR alone: avg HR only 129 on a climbing "
        "stage, couldn't get above 178 (vs 193/185 earlier). 'Nothing in me.'",
        "The rest day proved capacity was intact — Day 4 climbed 3,425 m with the "
        "engine fully back. The failure was management, not fitness.",
        "Day 5 paced right (negative decoupling, HR drifting down) — same rider, "
        "opposite outcome, purely a function of how he rode.",
        "Gearing forced grinding: 50-34 / 12-25 left only 47 rpm at 8 km/h in the "
        "easiest gear — hardware locked him into glycogen-heavy cadence.",
    ],
    "lessons": [
        "PACING: Day 1 must feel almost too easy — cap well below threshold "
        "(Z2, only steepest pitches into Z3). On race climbs power is a cap, not a "
        "target (~70–80% FTP early stages).",
        "FUELLING: target 80–90 g carbs/hour (~500 g on the big days). In 2012 he "
        "'had no idea about fuelling' — the Day-3 collapse is what that debt looks "
        "like when it comes due. Train the gut for it.",
        "GEARING + CADENCE: fit 11-36 cassette (36×36 spins ~63 rpm at 8 km/h vs 47 "
        "in 2012) and train climbing at 75–85 rpm — low cadence burns glycogen faster "
        "at 50+.",
        "WEIGHT: 78 kg was his proven 2012 race weight — the blow-up was pacing and "
        "fuelling, not spare kilos. Target ~80 kg walking weight, ~78 kg for the event.",
        "MONITOR FATIGUE: the Day-2 signal (top-end HR disappearing) was readable and "
        "ignored. Heed amber on the HRV traffic light / back-to-back fatigue logs.",
    ],
    "build_targets": [
        "Engine: realistic FTP 270–280 W at 78 kg (3.46–3.59 W/kg) beats chasing "
        "the old 301 W strap estimate — finish the week fuelled and paced, not watt-maxxed.",
        "Power meter: watts for pacing ceilings on climbs; HR + HRV for readiness. "
        "See /haute-route/power-protocol for FTP test protocol.",
    ],
}


def hr_2012_lessons_context() -> list[str]:
    """Markdown-ish lines injecting the 2012 lessons into the coach chat context."""
    lines = [f"## {LESSONS_2012['title']}", LESSONS_2012["summary"], "  What the data showed:"]
    lines += [f"  - {e}" for e in LESSONS_2012["evidence"]]
    lines.append("  Carry into 2027:")
    lines += [f"  - {l}" for l in LESSONS_2012["lessons"]]
    lines.append("  Build targets:")
    lines += [f"  - {t}" for t in LESSONS_2012.get("build_targets", [])]
    return lines


_HR_PLAN_DAYS = len(HR_TRAINING_WEEKS) * 7  # 322


def _fmt_dur(dur: int) -> str:
    if not dur:
        return ""
    if dur < 60:
        return f"{dur}m"
    if dur % 60:
        return f"{dur // 60}h{dur % 60:02d}m"
    return f"{dur // 60}h"


def phase_for_week(week_num: int) -> dict | None:
    """Return the phase dict for a 1-indexed week number, or None."""
    for p in HR_PHASES:
        if p["week_start"] <= week_num <= p["week_end"]:
            return p
    return None


def hr_session_for_date(d: date) -> tuple[str, str, int] | None:
    """Return (type, label, duration_min) for the given date, or None if outside the plan."""
    delta = (d - HR_PLAN_START).days
    if delta < 0 or delta >= _HR_PLAN_DAYS:
        return None
    from .history import get_plan_override
    ov = get_plan_override(d.isoformat())
    if ov:
        return (ov["session_type"], ov["label"], ov["duration_min"])
    week_idx, day_idx = divmod(delta, 7)
    return HR_TRAINING_WEEKS[week_idx][day_idx]


def build_hr_calendar_weeks() -> list[dict]:
    """Return one dict per training week for template rendering."""
    from .history import list_plan_overrides, load_ftp_tests
    overrides = {o["date"]: o for o in list_plan_overrides()}
    today = date.today()
    ftp_w = None
    for t in reversed(load_ftp_tests()):
        if t.get("ftp_w"):
            ftp_w = int(t["ftp_w"])
            break
    weeks = []
    for wk_idx, sessions in enumerate(HR_TRAINING_WEEKS):
        week_num = wk_idx + 1
        wk_start = HR_PLAN_START + timedelta(weeks=wk_idx)
        phase = phase_for_week(week_num)
        days = []
        total_min = 0
        planned_tss = 0.0
        for day_offset, (stype, label, dur) in enumerate(sessions):
            d = wk_start + timedelta(days=day_offset)
            ov = overrides.get(d.isoformat())
            if ov:
                dur = ov["duration_min"]
                if ov.get("session_type"):
                    stype = ov["session_type"]
                if ov.get("label"):
                    label = ov["label"]
            total_min += dur
            pt = power_target_for(stype, label)
            if stype != "gym" and stype != "rest" and dur > 0:
                if_typ = HR_TYPICAL_IF.get(stype, 0.65)
                planned_tss += (dur / 60) * (if_typ ** 2) * 100
            days.append({
                "date": d,
                "day_num": d.day,
                "month_abbr": d.strftime("%b"),
                "type": stype,
                "label": label,
                "dur_fmt": _fmt_dur(dur),
                "dur_min": dur,
                "is_today": d == today,
                "is_past": d < today,
                "overridden": bool(ov),
                "power_target": pt,
                "power_watts": power_watts_range(ftp_w, pt) if ftp_w else (
                    pt if isinstance(pt, str) else None
                ),
            })
        weeks.append({
            "week_num": week_num,
            "start": wk_start,
            "phase": phase,
            "days": days,
            "total_hrs": round(total_min / 60, 1),
            "planned_tss": round(planned_tss),
        })
    return weeks


def build_hr_event_weeks() -> list[dict]:
    """Return two Mon–Sun rows covering the Haute Route Alpes event (Aug 23–29 2027)."""
    today = date.today()
    stages_by_date = {s["date"]: s for s in HR_EVENT_STAGES}
    grid_start = date(2027, 8, 23)  # Monday
    weeks = []
    for wk in range(1):
        wk_start = grid_start + timedelta(weeks=wk)
        cells = []
        for day_off in range(7):
            d = wk_start + timedelta(days=day_off)
            stage = stages_by_date.get(d)
            if stage:
                cells.append({
                    "date": d, "day_num": d.day, "month_abbr": d.strftime("%b"),
                    "label": stage["label"], "km": stage["km"],
                    "elev_m": stage["elev_m"], "key_climb": stage["key_climb"],
                    "day_num_stage": stage["day"],
                    "is_today": d == today, "is_past": d < today, "is_event": True,
                })
            else:
                cells.append({
                    "date": d, "day_num": d.day, "month_abbr": d.strftime("%b"),
                    "is_event": False,
                })
        weeks.append({"week_label": wk_start.strftime("%-d %b"), "days": cells})
    return weeks

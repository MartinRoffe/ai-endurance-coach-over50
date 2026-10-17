# General fitness · 12 Oct 2026 – 3 Oct 2027

Road cycling and mountain walking for the trips in this year. Haute Route Alpes 2028 stays the later goal. This file is the same week table the app reads from `ai_endurance_coach_over50/fitness_plan.py`.

Athlete: over 50, measured max HR **191** (zones unchanged), working FTP about **220 W**, weight about **89–92 kg**.

## Rules

- Clinic **Thu 15 Oct 2026**: ESWL was not performed — the fragments had already passed. Only a confirmation CT remains. That day is attended with no treatment. Fri 16 Oct is rest. Sat 17 is a **45-minute hill walk with a light pack**. Sun 18 is a **1-hour easy ride**. These weekend sessions are normal plan days, not optional.
- There is **no** 7-day post-procedure easy-only window after 15 Oct. `MEDICAL_RETURN_EASY_DAYS` still exists for stent removal and any future logged procedure; 15 Oct is not a procedure date in `safety._procedure_dates`.
- The first hard session is **Tue 20 Oct** (threshold on the rower, 2×8 min, RPE 7–8, heart rate Z4 160–167). From the week of **26 Oct** there are two hard sessions (Tuesday and Thursday), never back to back.
- A hard session is threshold or VO2, on the rower or the MaxiClimber on weekdays. Bike rides are outdoors and only at the weekend. Caps still apply: at most two hard days a week, at least one rest day, and no more than about 10% more weekly load than the previous prescribed week. The clearance week of 12 Oct is not the load base. Camp weeks are not trimmed by that percentage.
- `HAS_TURBO` in `settings.py` is false. Turning it on restores the stored weekday bike sessions without editing the week tables.
- Until the confirmation CT: stop for flank pain, fever or blood. Keep drinking: **2–3 L** a day, plus about **500 ml** per training hour.
- Morning check: soreness, mood, energy, flank pain, fever, blood, fluids. Flank pain, fever, or blood forces rest.
- On foot every week. The bike does not train descents or a pack.
- Pull-ups, three days a week (Tue, Thu, Sat) from 27 Oct through 19 Feb: negatives, then band-assisted, then strict reps. The bar is in use from 27 Oct. Strict reps are still 0, so the first phase is negatives.
- Strength is twice a week from **21 Oct** through 8 Feb: a lighter endurance session (Wednesday, because Thursday is hard) and a load session (Saturday, after Friday's rest). From January the load work is a sandbag after Tuesday's hard rower session, and Saturday is the hill ruck. Every 4th week the bells and the sets get lighter. The week of 15 Feb is a taper. Labels do not use the word "heavy", because that word counts as a hard session.

## Tenerife · same hours, weekday sessions on the rower

Weekday camp hours move to the rower at the same duration (threshold or VO2, or easy Z2). **Sat 26 Dec** is the optional outdoor Teide ride (about 5 hours). There is no 580 km or 14,000 m target. Shorten a session when fitness is not there.

Home Sundays reach **3 hours on Sun 22 Nov 2026**.

## Weeks through Scotland

### Clearance

| Week of | Mon | Tue | Wed | Thu | Fri | Sat | Sun |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 12 Oct 2026 | Rest | Easy walk · 30m | Z2 — rower · 40m | Attended — no treatment | Rest | Easy hill walk — light pack · 45m | Long Ride (Easy) · outdoor · 1h |

### Return

One hard day in the week of 19 Oct. Two from the week of 26 Oct. Wednesday is the lighter strength day from 21 Oct. Saturday is the load day, lighter every 4th week (9 Nov, 7 Dec). Sunday reaches 3 hours on 22 Nov.

| Week of | Mon | Tue | Wed | Thu | Fri | Sat | Sun |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 19 Oct 2026 | Rest | Threshold — rower · 40m | Strength — endurance · 45m | Easy steps · 30m | Rest | Strength — load · 50m | Long Ride (Easy) · outdoor · 1h10 |
| 26 Oct 2026 | Rest | Threshold — rower · 40m | Strength — endurance · 45m | VO2 — rower · 35m | Rest | Strength — load · 50m | Long Ride (Easy) · outdoor · 1h25 |
| 2 Nov 2026 | Rest | VO2 — rower · 40m | Strength — endurance · 50m | Threshold — rower · 35m | Rest | Strength — load · 55m | Long Ride (Easy) · outdoor · 1h40 |
| 9 Nov 2026 | Rest | Threshold — rower · 45m | Strength — endurance · 50m | VO2 — rower · 40m | Rest | Strength — load · 55m | Long Ride (Easy) · outdoor · 1h55 |
| 16 Nov 2026 | Rest | VO2 — rower · 40m | Strength — endurance · 30m | Threshold — rower · 35m | Rest | Strength — load · 50m | Long Ride (Easy) · outdoor · 3h |
| 23 Nov 2026 | Rest | Threshold — rower · 40m | Strength — endurance · 30m | VO2 — MaxiClimber · 35m | Rest | Strength — load · 1h20 | Long Ride (Easy) · outdoor · 3h |
| 30 Nov 2026 | Rest | VO2 — rower · 40m | Strength — endurance · 45m | Threshold — rower · 40m | Rest | Strength — load · 1h | Long Ride (Easy) · outdoor · 3h |
| 7 Dec 2026 | Rest | Threshold — rower · 40m | Strength — endurance · 40m | VO2 — rower · 40m | Rest | Strength — load · 1h40 | Long Ride (Easy) · outdoor · 3h |
| 14 Dec 2026 | Rest | Threshold — rower · 40m | Strength — endurance · 40m | VO2 — rower · 40m | Rest | Strength — load · 1h40 | Long Ride (Easy) · outdoor · 3h |

### Tenerife · 21 Dec 2026 – 3 Jan 2027

| Week of | Mon | Tue | Wed | Thu | Fri | Sat | Sun |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 21 Dec 2026 | Tenerife — travel | Z2 — rower · 1h15 | Threshold — rower · 3h | Z2 — rower · 1h30 | Z2 — rower · 1h | Teide — optional long day · outdoor · 5h | Tenerife — mid-camp rest |
| 28 Dec 2026 | Threshold — rower · 4h | Z2 — rower · 1h30 | VO2 — rower · 3h30 | Z2 — rower · 1h30 | New Year rest | Travel home | Post-camp rest |

### Keswick build · 4 Jan – 21 Feb 2027

Tuesday is a hard rower session, then sandbag deadlift sets (not a kettlebell — the heaviest bell is 24 kg, and there is no trap bar). Wednesday is the lighter strength day. Thursday is the second hard session. The week of 25 Jan keeps the shape and cuts the sets. The Saturday pack reaches **20.4 kg** on 6 Feb. Sat 13 Feb is a timed 3-mile pack-test rehearsal. The week of 8 Feb is step-overs and burpee pull-ups, with only Thursday as a hard cardio day. The week of 15 Feb is the taper. Sat 20 and Sun 21 Feb are the test.

| Week of | Mon | Tue | Wed | Thu | Fri | Sat | Sun |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 4 Jan 2027 | Rest | Threshold — rower, then sandbag · 50m | Strength — endurance · 1h | VO2 — rower · 40m | Rest | Hill ruck 10 kg · 1h10 | Long Ride (Easy) · outdoor · 1h30 |
| 11 Jan 2027 | Rest | Threshold — rower, then sandbag · 50m | Strength — endurance · 40m | VO2 — MaxiClimber · 40m | Rest | Hill ruck 12 kg · 1h10 | Long Ride (Easy) · outdoor · 1h30 |
| 18 Jan 2027 | Rest | Threshold — rower, then sandbag · 50m | Strength — endurance · 55m | Threshold — rower · 40m | Rest | Hill ruck 15 kg · 1h10 | Long Ride (Easy) · outdoor · 1h30 |
| 25 Jan 2027 | Rest | Threshold — rower, then sandbag · 50m | Strength — endurance · 1h | Threshold — rower · 40m | Rest | Hill ruck 18 kg · 1h10 | Long Ride (Easy) · outdoor · 1h30 |
| 1 Feb 2027 | Rest | Threshold — rower, then sandbag · 50m | Strength — endurance · 1h | VO2 — rower · 40m | Rest | Hill ruck 20.4 kg · 1h10 | Long Ride (Easy) · outdoor · 1h30 |
| 8 Feb 2027 | Rest | Strength — step-overs + burpee pull-ups · 45m | Strength — endurance · 45m | Threshold — rower · 35m | Rest | Pack test rehearsal 20.4 kg · 1h | Long Ride (Easy) · outdoor · 1h15 |
| 15 Feb 2027 | Rest | Strength — light · 25m | Z2 — rower · 45m | Easy walk · 30m | Rest | BUSAR test | BUSAR test |

### Lakes · 27–28 Feb 2027, Keswick

The week of 22 Feb stays light. Default routes: Saturday high is Skiddaw by Jenkin Hill, lower is High Spy–Cat Bells. Sunday high is Blencathra by Blease Fell (leave Sharp Edge and Hall’s Fell). Lower is Walla Crag–Bleaberry Fell. The following week is walks, a short weekday rower, and a short outdoor ride on Sunday.

| Week of | Mon | Tue | Wed | Thu | Fri | Sat | Sun |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 22 Feb 2027 | Rest | Strength — light · 25m | Z2 — rower · 45m | Easy walk · 30m | Rest | Keswick — Skiddaw or High Spy · 6h | Keswick — Blencathra or Walla Crag · 4h |
| 1 Mar 2027 | Rest | Easy walk · 40m | Z2 — rower · 45m | Easy walk · 30m | Rest | Easy walk · 1h | Z2 Easy · outdoor · 45m |

### Scotland prep · ready from Mon 22 Mar 2027

Hours are ceilings. Exact hills are chosen that week from the conditions report (same pattern as Keswick). Overnight winter pack is about 22 kg when a night out is planned. Fitness is not winter skill — ice axe, crampons, and navigation need a skills refresh before relying on them.

| Week of | Mon | Tue | Wed | Thu | Fri | Sat | Sun |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 8 Mar 2027 | Rest | Strength — heavy · 45m | Z2 — rower · 1h | Step-downs + steps · 30m | Rest | Long hill walk · 3h | Back-to-back hill walk · 2h |
| 15 Mar 2027 | Rest | Strength — heavy · 40m | Z2 — rower · 1h | Step-downs + steps · 30m | Rest | Long hill walk · 3h30 | Long Ride (Easy) · outdoor · 1h30 |
| 22 Mar 2027 | Scotland — day on foot · 4h | Scotland — day on foot · 3h | Rest | Scotland — day on foot · 4h | Scotland — day on foot · 2h30 | Rest | Rest |

## April–October 2027

From **Mon 29 Mar** through **Sun 3 Oct** the same week repeats. October is a checkpoint, not the start of a Haute Route interval plan.

| Mon | Tue | Wed | Thu | Fri | Sat | Sun |
| --- | --- | --- | --- | --- | --- | --- |
| Rest | Strength — maintenance · 45m | Z2 — rower · 1h15 | Easy steps · 30m | Rest | Saturday hill walk · 2h | Long Ride (Easy) · outdoor · 3h |

## Session library

**Threshold / VO2.** One hard session from 20 Oct, two from 26 Oct. Weekdays are rower or MaxiClimber. A 40-minute threshold row is 2×8 min at RPE 7–8, heart rate Z4 160–167 (max HR 191, Garmin lactate-threshold zones). There is no rower test yet, so the 500 m split is not a target — a 2,000 m or 20-minute test would set one. Easy weekday aerobic work is a Z2 rower, or the MaxiClimber for the same duration. Rower sessions are pushed to Garmin as cardio workouts. MaxiClimber stays calendar-only.

**Kettlebell.** Swings, goblet squats, presses, rows, carries, get-ups, and step-ups. Bells are 8, 12, 14, 16, 20 and 24 kg. The heaviest bell is not the deadlift.

**Pull-ups.** Extra line on Tue, Thu, and Sat. Negatives 3×3–5 from 27 Oct (the bar is in, strict reps are still 0). Band-assisted 3×4–6 in January. Strict, or stay on the band, 3×3–5 in February.

**Sandbag.** After Tuesday's hard rower session from 4 Jan. Sets leave 2 reps in reserve. A barbell is fine if you have one. There is no trap bar. The test standard is still 102 kg × 15 in one minute, which is not the January load.

**Hill ruck.** 10 kg on 9 Jan, then 12, 15, 18, and **20.4 kg** on 6 Feb. Duration stays about 70 minutes while the kilograms rise. 13 Feb is the timed 3-mile rehearsal at 20.4 kg.

**Weekend outdoor rides (Z2 Easy · outdoor, Long Ride (Easy) · outdoor).** Pushed to Garmin as cycling workouts. Flat quiet loop, heart rate leads on climbs, Assioma pedals still record power. Lights in the dark months. Wind or weather: rower or MaxiClimber for the same duration at zone 2.

**Teide — optional long day · outdoor.** About 5 hours on 26 Dec. Not pushed.

## What the app does with this

- The dashboard and calendar read these weeks from `fitness_plan.py`.
- Garmin receives weekend outdoor **Z2 Easy** and **Long Ride (Easy)** as cycling workouts, and **Threshold — rower**, **VO2 — rower**, and **Z2 — rower** as cardio workouts. MaxiClimber, kettlebell, hikes, rucks, strength, and Teide are not pushed.
- Intake is at maintenance from **9 Oct 2026 through 3 Jan 2027**. From **4 Jan through 31 Mar 2027** the ease deficit applies: rest and recovery −650 kcal, training −550, ruck −450, long −350, hard −250. The target is **84–85 kg** by **31 Mar 2027** (`CUT_TARGET_KG` 84.5), about 0.5 kg a week. Hard days keep carbohydrate up. Protein stays on the lean-mass floor.
- Gravel bike flag is off.
- Haute Route Alpes 2028 stays the named goal. The week-by-week race block stays off until after the **3 Oct 2027** checkpoint.

## BUSAR — 20–21 Feb 2027

Both days are the test. The week of 15 Feb is light. Not pushed to Garmin.

| Component | Standard |
| --- | --- |
| Pack test | 3 miles flat with 45 lb (20.4 kg) in under 45 minutes |
| Step-overs | 20 lb pack plus a sandbag or the 24 kg kettlebell, up and over a picnic table for 30 minutes |
| Deadlift | Train with a sandbag or a barbell. Test standard remains 225 lb (102 kg), at least 15 reps in one minute. No trap bar yet. |
| Burpee pull-ups | 20 lb pack, at least 50 in 10 minutes. Current strict pull-ups: 0. Bar from 27 Oct. Negatives, then a band, then strict reps. |

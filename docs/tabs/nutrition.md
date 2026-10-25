# Nutrition

**Nav:** top-level **Nutrition** tab.

Sticky subnav primaries: **Today** · **Ride Fuel** · **Sunday Prep** · **Cut**.

Secondary (More): **This week** (meal week-viewer) via demoted links.

Legacy recipe URLs (`/nutrition/recipes*`) stay for deep links from Sunday Prep
components; they are not primary tabs.

Use **Cycle week 1–4** for the food rotation (not training-plan week numbers).
Week 4 is the recovery cycle week.

---

## Today

**Route:** `/nutrition`

Four numbers and one habit, from `today_card()`:

- **Calories** — one figure. Easy or rest is stable TDEE minus 600. Hard is minus 250. Long is maintenance plus ride fuel.
- **Protein** — one midpoint from the lean-mass target, eaten as four doses (breakfast, lunch, dinner, evening dairy).
- **Carbs** — one gram figure that fits the day's calories, after protein and about a quarter of the day for fat. On a long ride, on-bike fuel is added on top of the base and this figure includes it.
- **Fluids** — 2.5–3 L plus 0.5 L per training hour. Urine pale.
- **Habit** — veg or fruit at every meal, plus creatine 3–5 g.

Logged food is compared with calories and protein only. TDEE, the deficit, calibration, per-meal macros, and the 7-day energy-availability note sit in **Advanced**.

Meals are names only: breakfast, a soup for lunch, a one-pot for dinner, and evening dairy. Chicken and rice stays in the rotation, about once or twice a week.

A one-line stone rule sits under the habit: calcium from dairy with meals, salt under about 6 g off the bike, skip spinach, chia, nuts, beetroot and rhubarb (or pair a small portion with dairy), lemon or lime in water, spread animal protein, vitamin C at a standard dose.

---

## Calorie targets: burn vs target vs logged

Three distinct numbers appear across Nutrition and Body:

- **Burn (TDEE today)** — today's estimated expenditure *so far*: Katch-McArdle
  BMR + Garmin active calories. Optional 28-day weight-trend calibration is
  **applied only when confidence is high** (≥70% intake coverage typical);
  limited/inactive confidence means the correction is shown but not applied.
  Mid-day “vs burn” is informational only — do not eat to this number.
- **Intake target** — what you should eat in the morning, from `today_targets()`:
  **stable TDEE** (7-day average burn) **minus a session-type deficit**
  (`stable_tdee − deficit`), plus long-ride fuel top-up beyond 2 h when needed.
  This is periodized cut fueling: larger deficit on rest/easy days, near
  maintenance on long/quality days.
  - **Maintenance** (9 Oct 2026–3 Jan 2027): deficit 0 through the kidney-stone
    return and Christmas. The earlier July–September 2026 window has expired.
  - **Ease** (4 Jan–31 Mar 2027, `CUT_PHASES` in `energy.py`): toward 84–85 kg by
    31 Mar (`CUT_TARGET_KG` 84.5). About 0.5 kg/week. Easy −600, hard −250, long 0
    plus ride fuel. Protein stays on the lean-mass lock.
  - Floor 1,600 kcal. There is no live camp-nutrition window.
  - Optional `session_work_kcal` (FTP × % targets) is context only — it does
    **not** change the crowned intake when stable TDEE exists.
- **Logged** — what the Garmin food diary says you ate.

Primary gauge is **vs plan** (logged vs intake target). “Vs weekly burn” on the
Cut page compares logged to stable TDEE, not today’s incomplete burn.

**Weight goal:** 84–85 kg by 31 Mar 2027, on `/nutrition/cut`. There is no kilogram
target before Christmas. Maintenance (no deficit) runs 9 Oct 2026 through
3 Jan 2027, including Christmas camp. From 4 Jan through 31 Mar the ordinary
day-type deficits apply (five easy days, one hard day and one long day, about
460 kcal/day, ~0.5 kg/week). Hard days take a smaller deficit so carbohydrate
stays up. Protein lean-mass floor stays locked.
Energy availability uses logged food minus **session** calories (not Garmin
active calories) over 7 days, and only when food is logged on at least 5 of
those days. Under 30 kcal/kg fat-free mass raises a moderate alert. The Cut page shows
today’s prescription + **why**, a weekly deficit budget strip, and Garmin
logged vs intake target. Full meal plan stays on Nutrition Today. On rest days,
delaying the first meal (≈12–14 h overnight) is fine if the protein floor is
still hit by evening. After changing deficit maps, clear stale AI targets:
`DELETE FROM nutrition_targets WHERE session_key LIKE '%_v2_%'`.

Meals are a rotating library of about eight one-pots and six soups
(`meal_library.py`). Each portion is one protein dose. The carb side changes
with the day type. Portions are not scaled to force the plate onto the calorie
target.

**Calibration confidence** (Body tab + Cut page): `high` / `limited` / `inactive`
reflects intake coverage, weigh-ins, body-comp freshness, and whether the
correction is near the ±25% clamp. Low confidence → model TDEE only (no large
negative offset), so planned deficits actually bite.

**Camp mode** applies to the finished August 2026 Tenerife window only.
Christmas Tenerife stays at maintenance calories with normal easy-ride fuelling.
The May 2027 race-sim window is not in the live plan.

**Recipe macros:** plated weekday-dinner figures follow
`nutrition_plan.WEEKDAY_DINNERS` (build **620 kcal**, recovery **560 kcal**,
including the 150 g protein dessert). Cook the full batch; plate the smaller
carb side listed on each dinner card. Do not use the old ~700–740 “full side”
figures — those overshot the intake target.

---

## This week (Meals)

**Route:** `/nutrition/meals` (secondary nav)

4-week cycle (weeks 1–3 build with distinct dinner batches, week 4 recovery).
Server-rendered from `nutrition_plan.py` — breakfasts and weekday dinners injected
via `_assemble_meals()`. **This week** shows training-calendar badges; meal-slot
skeletons follow the planned session (via `meal_day_type_for_session`); breakfast
and dinner still rotate on the nutrition cycle (weeks 1–4).

---

## Sunday Prep

**Route:** `/nutrition/sunday`

Primary Sunday batch workflow: tickable cook list, timed parallel schedule for the
current cycle week, inline Dinner A / Dinner B methods, and a **Components** list
(chicken, rice, oats, scotch eggs / muffins, yogurt pots, oat bars) linking to
legacy recipe methods. Quiet links to Shopping and the rice-cake calculator.

---

## Fuelling

**Route:** `/nutrition/fuelling` (secondary nav)

**Weekends only** for in-ride solids:

- **Batch calculator** — rice cakes + electrolyte bottles keyed to planned ride length
- **Weekday rides ≤90 min** — banana before, nothing on the bike
- **Post-ride recovery** — chocolate milk → protein overnight oats jar
- **Friday prep** — rice cakes (24 h fridge set) + electrolyte bottles

Maltodextrin drink protocols remain optional for winter / event gut training.

---

## Recipes (legacy deep links)

**Routes:** `/nutrition/recipes` and subpaths (overnight oats, weekend fuel,
griddle, weekday dinners archive, travel checklist).

**Homemade rice cakes:** `/nutrition/recipes#standard-rice-cake` (bacon and egg,
about 12 from one batch) and `#sweet-rice-cakes` (banana and honey, about 10).
`/nutrition/recipes/weekend-fuel` redirects to the savoury recipe. Carbohydrate
per cake is calculated from the ingredients.

Still available for bookmarks and Sunday Prep component links. Prefer **Sunday
Prep** for the active week’s cook day.

**One-pots and soups:** `/nutrition/recipes/weekday-dinners` — the live library
(methods for each pot and soup). Chicken and rice is included, not every day.

---

## Shopping

**Route:** `/nutrition/shopping-list` (the Lidl URL serves the same page)

One list for this cook-week’s batches plus everyday staples (yoghurt, milk,
eggs, fruit, lemons, creatine). Use it at Asda or Lidl.

---

## Garmin integration

Carbs and protein logged in your Garmin food diary appear on:

- The **Today** readiness pill (link into Nutrition)
- The **Nutrition** Today banner
- The **Body** tab macro tiles (today + 14-day averages)
- **Coach** context (simple rules + checklist lead the nutrition block)

Protein targets use lean-mass-based floors from `protein_target_g()`.

When FTP is known, in-ride fuelling plans and calorie tiers may use **estimated
mechanical work (kJ)** from planned session power. See
**[Power Training](../power-training.md)**.

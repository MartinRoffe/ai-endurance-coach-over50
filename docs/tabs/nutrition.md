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

Prescribed meal table for the day (from `build_today_food()`), meals-total vs
intake target, and Garmin logged strip (logged / intake target / vs plan / carbs /
protein). Short Sunday-fuel callout when a long ride is upcoming.

Dinner and breakfast methods live on **Sunday Prep**, not a separate recipes hub.

Fixed weekday pattern: overnight oats Mon/Wed/Fri; scotch egg + yogurt Tue/Thu
(egg muffins Tue/Thu in recovery week only). Mon–Thu dinners are Sunday batch
(Batch A Mon/Tue, Batch B Wed/Thu — cycle-week rotation); Fri–Sun are griddle.

---

## Calorie targets: burn vs target vs logged

Three distinct numbers appear across Nutrition and Body:

- **Burn (TDEE)** — today's estimated expenditure: Katch-McArdle BMR + Garmin
  active calories + optional 28-day weight-trend calibration (applied only when
  confidence is **high** — typically ≥70% intake coverage). Shown on the Body
  tab as "TDEE Today". It is *incomplete until end of day*, so mid-day "vs burn"
  comparisons are informational only.
- **Intake target** — what you should eat: **stable TDEE** (7-day average of
  calibrated-or-model daily burn, preferring days with real active-calorie data)
  minus a session-type deficit. During the **Base Cut** (15 Sep–20 Dec 2026)
  hard deficits are rest/recovery −550, training −450, ruck −300, long −100;
  ease phase (23 Nov–20 Dec) uses rest −350 / training −250 / ruck −150 /
  long −50. Floored at 1,600 kcal; long rides add ~175 kcal per hour beyond 2 h.
  Computed by `resolve_calorie_target()`; Tenerife camp windows suspend the
  UK deficit entirely. See **Cut** (`/nutrition/cut`) for pace vs 80–81 kg.
- **Logged** — what the Garmin food diary says you ate.

**Base Cut (Sep–Dec 2026):** dedicated page at `/nutrition/cut` — target **80.5 kg**
(band 80–81) by Christmas camp (21 Dec). Hard cut 15 Sep–22 Nov, ease
23 Nov–20 Dec, then camp fueling. Protein lean-mass floor is locked at cut
start. The Cut page also shows **today’s Garmin logged kcal vs intake target**
(gap / room left); the full meal plan stays on Nutrition Today. After changing
deficit maps, clear stale AI targets:
`DELETE FROM nutrition_targets WHERE session_key LIKE '%_v2_%'`.

Prescribed meals in `nutrition_plan.py` are portioned so each day type's meal
kcal sum lands within ~100 kcal of its target at the design TDEE (~2,000).
Flexible carb/fat slots (rice, snacks, dessert starch, on-bike fuel) scale
further when stable TDEE drifts — protein anchors stay fixed. The Today page
flags any gap portions cannot close without cutting protein.

**Calibration confidence** (Body tab + Cut page): `high` / `limited` / `inactive`
reflects intake coverage, weigh-ins, body-comp freshness, and whether the
correction is near the ±25% clamp. Low confidence → model TDEE only (no large
negative offset), so planned deficits actually bite.

**Camp mode** (Tenerife windows): UK batch meals and weekday "nothing on the bike"
rules are suspended. Nutrition Today shows camp fuelling from actual ride
intensity; see `/tenerife` for the hard-day template.

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
via `_assemble_meals()`. **This week** shows training-calendar badges; meal-pattern
tabs are cycle weeks 1–4.

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

Still available for bookmarks and Sunday Prep component links. Prefer **Sunday
Prep** for the active week’s cook day.

**Weekday dinners archive:** `/nutrition/recipes/weekday-dinners` — full 4-week
A/B methods (same partial as Sunday Prep; plated macros match `WEEKDAY_DINNERS`).

---

## Shopping

**Route:** `/nutrition/shopping-list` and `/nutrition/lidl-shopping-list`

Primary tab. Category filters (breakfast, lunch, weekday dinners, weekend ride,
griddle, staples). Cycle week 1–4 buttons filter dinner ingredients to the
current food cycle. Switch stores via the Asda / Lidl controls on the page.

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

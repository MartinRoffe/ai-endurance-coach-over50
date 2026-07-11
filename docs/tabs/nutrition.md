# Nutrition

**Nav:** top-level **Nutrition** tab.

Sticky subnav: **Today** · **Meals** · **Sunday Prep** · **Fuelling** · **Recipes** ·
**Shopping**.

Use **Cycle week 1–4** for the food rotation (not training-plan week numbers).
Week 4 is the recovery cycle week.

---

## Today

**Route:** `/nutrition`

Five simple rules, today's checklist, Garmin logged-intake strip, and primary CTAs
to Sunday Prep, Meals, Fuelling, and Shopping.

Fixed weekday pattern: overnight oats Mon/Wed/Fri; scotch egg + yogurt Tue/Thu
(egg muffins Tue/Thu in recovery week only). Mon–Thu dinners are Sunday batch
(Batch A Mon/Tue, Batch B Wed/Thu — cycle-week rotation); Fri–Sun are griddle.

---

## Meals

**Route:** `/nutrition/meals`

4-week cycle (weeks 1–3 build with distinct dinner batches, week 4 recovery).
Server-rendered from `nutrition_plan.py` — breakfasts and weekday dinners injected
via `_assemble_meals()`. **This week** shows training-calendar badges; meal-pattern
tabs are cycle weeks 1–4.

---

## Sunday Prep

**Route:** `/nutrition/sunday`

Primary Sunday batch workflow: tickable cook list, timed parallel schedule for the
current cycle week, and inline Dinner A / Dinner B methods. Links out to Shopping,
Friday rice-cake calculator, and component recipes.

---

## Fuelling

**Route:** `/nutrition/fuelling`

**Weekends only** for in-ride solids:

- **Batch calculator** — rice cakes + electrolyte bottles keyed to planned ride length
- **Weekday rides ≤90 min** — banana before, nothing on the bike
- **Post-ride recovery** — chocolate milk → protein overnight oats jar
- **Friday prep** — rice cakes (24 h fridge set) + electrolyte bottles

Maltodextrin drink protocols remain optional for winter / event gut training.

---

## Recipes

**Route:** `/nutrition/recipes`

Component recipes (chicken, rice, breakfasts, lunches) plus fridge/storage rules.
Recipe library sub-tabs: overnight oats, weekend ride fuel, griddle, weekday
dinners (all cycle weeks), travel checklist.

**Weekday dinners archive:** `/nutrition/recipes/weekday-dinners` — full 4-week A/B
methods (also inlined for the active week on Sunday Prep).

---

## Shopping

**Route:** `/nutrition/shopping-list` and `/nutrition/lidl-shopping-list`

Category filters (breakfast, lunch, weekday dinners, weekend ride, griddle, staples).
Cycle week 1–4 buttons filter dinner ingredients to the current food cycle.

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

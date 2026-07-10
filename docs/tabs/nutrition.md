# Nutrition

**Nav:** top-level **Nutrition** tab (not under Health).

Sub-pages use a sticky bar below the main navigation: Overview · Daily Menus ·
Ride Fuelling · Recipes · Asda · Lidl.

---

## Overview

**Route:** `/nutrition`

**Follow This** section at the top: five simple rules + today's checklist (breakfast,
lunch, pre-session fuel, dinner, weekend rice-cake prep). Calorie tiers, Garmin
logged-intake summary, and hub cards to sub-pages.

Fixed weekday pattern: overnight oats Mon/Wed/Fri; scotch egg + yogurt Tue/Thu
(egg muffins Tue/Thu in recovery week only). Mon–Thu dinners are Sunday batch
(Batch A Mon/Tue, Batch B Wed/Thu — week-specific rotation); Fri–Sun are griddle.
Week 4 is recovery with lighter ~560 kcal dinners.

---

## Daily Menus

**Route:** `/nutrition/meals`

4-week cycle (weeks 1–3 build with distinct dinner batches, week 4 recovery).
Server-rendered from `nutrition_plan.py` — breakfasts and weekday dinners injected
via `_assemble_meals()`.

---

## Ride Fuelling

**Route:** `/nutrition/fuelling`

**Weekends only** for in-ride solids:

- **Batch calculator** — rice cakes + electrolyte bottles keyed to planned ride length
- **Weekday rides ≤90 min** — banana before, nothing on the bike
- **Post-ride recovery** — chocolate milk → protein overnight oats jar
- **Friday prep** — rice cakes (24 h fridge set) + electrolyte bottles

Maltodextrin drink protocols remain optional for winter / event gut training.

---

## Recipes & Prep

**Route:** `/nutrition/recipes`

Sunday batch: chicken, rice, overnight oats, scotch eggs, yogurt pots, **and both
weekday dinner batches**. Tue/Thu (+ Sat) mid-morning snack is a shop-bought Nature
Valley Protein bar by default (home-baked oat bars are an optional alternative —
recipe #03). Friday eve: weekend rice cakes per calculator.

**Weekday dinners:** `/nutrition/recipes/weekday-dinners` — 4-week A/B rotation,
protein dessert standard, no spicy food.

---

## Shopping

**Route:** `/nutrition/shopping-list` and `/nutrition/lidl-shopping-list`

Category filters (breakfast, lunch, weekday dinners, weekend ride, griddle, staples).
Week 1–4 buttons filter dinner ingredients to the current cycle week.

---

## Garmin integration

Carbs and protein logged in your Garmin food diary appear on:

- The **Readiness** tab nutrition card (including **ride work kJ** when today's
  ride has power data)
- The **Nutrition** overview banner
- The **Body** tab macro tiles (today + 14-day averages)
- **Coach** context (simple rules + checklist lead the nutrition block)

Protein targets use lean-mass-based floors from `protein_target_g()`.

When FTP is known, in-ride fuelling plans and calorie tiers may use **estimated
mechanical work (kJ)** from planned session power. See
**[Power Training](../power-training.md)**.

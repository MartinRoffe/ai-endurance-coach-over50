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
(egg muffins Tue/Thu in recovery week only). Weeks 1–3 are identical; week 4 is
recovery.

---

## Daily Menus

**Route:** `/nutrition/meals`

4-week cycle (weeks 1–3 build, week 4 recovery). Server-rendered from
`nutrition_plan.py` — no Set A/B breakfast rotation.

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

Sunday batch: chicken, rice, overnight oats, scotch eggs, yogurt pots. Tue/Thu (+ Sat)
mid-morning snack is a shop-bought Nature Valley Protein bar by default (home-baked oat
bars are an optional alternative — recipe #03). Friday eve: weekend rice cakes per calculator.

---

## Shopping

**Route:** `/nutrition/shopping-list` and `/nutrition/lidl-shopping-list`

Category filters (breakfast, lunch, weekend ride, griddle, staples). No Set A/B
toggle.

---

## Garmin integration

Carbs and protein logged in your Garmin food diary appear on:

- The **Readiness** tab nutrition card
- The **Nutrition** overview banner
- The **Body** tab macro tiles (today + 14-day averages)
- **Coach** context (simple rules + checklist lead the nutrition block)

Protein targets use lean-mass-based floors from `protein_target_g()`.

# Replace Gousto with Sunday batch-cooked weekday dinners

## Context

The athlete is no longer using Gousto meal kits for Mon–Thu evening meals. Today those four dinner slots (~660–730 kcal, 60–65 g protein each) are outsourced: no recipes, no shopping items, no prep tasks. They must become first-class plan content: **Sunday batch-cooked dinners** (Batch A eaten Mon+Tue, Batch B eaten Wed+Thu), sized for **2 people** (his portion macro-tracked), **no spicy food**, supporting the cut (~0.5 kg/week) and the 185–200 g/day protein floor he struggles to hit. Weekend griddle dinners (Fri–Sun) are unchanged.

User decisions: Sunday batch + reheat · 2 portions · no spicy · new dedicated dinner recipes page.

## Nutrition content (the rotation)

Each portion includes the standard **protein dessert** (150 g skyr / 0% Greek yogurt: +90 kcal, +15 g P) to close the slot at 60–68 g protein — this is the key easy-protein lever. Macros below are his portion **including** dessert:

| Week | Batch A (Mon+Tue, fridge) | Batch B (Wed+Thu, freeze Sun → fridge Tue eve) |
|---|---|---|
| 1 | Chicken & root-veg traybake + roast potatoes — (700 kcal, 66 P, 52 C) | Beef (5%) & red-lentil ragù + basmati — (730, 64, 84) |
| 2 | Mild coconut chicken curry (korma-style, no chilli) + basmati — (720, 65, 58) | Turkey mince bolognese + wholewheat spaghetti — (700, 68, 62) |
| 3 | One-pot chicken & chorizo rice (mild) — (740, 65, 60) | Smoky bean & beef stew (no heat) + mash/bread — (710, 62, 66) |
| 4 (recovery, lighter) | Lean cottage pie, half-cauli mash — (560, 62, 40) | Chicken & veg casserole + small potatoes — (560, 60, 40) |

Build weeks match the old Gousto slot (~700–740 kcal); recovery week matches the 2050 kcal tier with lighter ~560 kcal dinners. Portion arithmetic (e.g. W1A: 300 g raw chicken thigh + 250 g roast potato/root veg + oil + dessert) is worked out and goes in recipe cards.

**Easy protein boosters** (new content): the protein dessert as standard; cottage cheese pot (+34 g P), half-scoop whey in yogurt (+12 g P) as fallback when the day runs short.

## Implementation

### 1. `ai_endurance_coach_over50/nutrition_plan.py` (core change)

- **Add `WEEKDAY_DINNERS`** dict after `BREAKFASTS` (~line 174): keyed by cycle week 0–3 → `{"A": tuple, "B": tuple}`, tuple = `(name, detail, kcal, protein_g, carbs_g)` with the macros above. Names use `" + "` separators so `_meal_components()`/`_week_shopping_tally()` split usefully. Details state: Sunday-cooked, serves 2×2 nights, reheat piping hot, protein dessert included in macros, link mention of the recipes page.
- **Add** `_DINNER_BATCH_BY_WEEKDAY = {0:"A", 1:"A", 2:"B", 3:"B"}`, `_WEEKDAY_DINNER_TYPES = frozenset({"rest","training","bike","thursday","recovery_weekday"})`, and `weekday_dinner(cycle_week, weekday) -> tuple|None` (returns `("Dinner", ...)` or None for Fri–Sun).
- **Modify `_assemble_meals()`** (line 200): before breakfast injection, if `dtype in _WEEKDAY_DINNER_TYPES` and `weekday_dinner()` returns a tuple, replace the last meal tuple. Dinner stays last → `_pre_dinner_protein()`, `today_checklist()` `meals[-1]` untouched. `bike_fri` excluded (Friday = griddle).
- **Recovery collapsed card**: `build_meal_week(3)` renders one Mon–Fri card via `_assemble_meals("recovery_weekday", 3, 0)` (would show only Batch A). Add `_recovery_dinner_summary()` producing a synthetic dinner row naming both W4 batches ("cottage pie Mon/Tue · chicken casserole Wed/Thu · lighter griddle Fri", macros 560/62/40 — both batches match) and swap it in for that card.
- **Rewrite Gousto text**: `SIMPLE_RULES` L104 (dinner rule) + add one booster rule ("protein dessert closes every weekday dinner; short? cottage cheese or half-scoop whey"); `PRINCIPLES` L123, L129; `protein_note` strings L231, L249, L267, L309; the now-unreachable fallback dinner tuples L239, 257, 278, 320 (generic "Sunday batch dinner — see rotation"); `recovery_weekday` dinner L390 (becomes Friday-only fallback: "Lighter griddle pick (Fri)"); `_WEEK_BANNERS` L608 — weeks 1–3 are no longer identical, name each week's two batches; fix "Weeks 1–3: identical" claim in `meal_cycle_full()` docstring/output.

All six consumers (`today_checklist`, `build_meal_week`/meals.html, `nutrition_coach_context`, `nutrition_week_context`, `meal_cycle_full`/coach `get_meal_cycle` tool, `_week_shopping_tally`) flow through `_assemble_meals()` — no other code changes needed for propagation.

### 2. New recipes page + route

- **New template** `templates/recipes-weekday-dinners.html`, cloned structurally from `recipes-griddle.html` (hero, TOC, `.recipe` cards with ingredients/method, macros footer, print styles). Sets `active_tab='nutrition'`, `nutrition_section='recipes'`, `recipes_section='recipes_weekday_dinners'`. Content: batch-logic primer (A fridge Mon/Tue, B freezer→fridge Tue eve, 2-person portions, no-spice, protein dessert standard), 8 recipe cards (4 weeks × A/B, per-portion macros matching `WEEKDAY_DINNERS` exactly, 2-person ingredient quantities), **Easy Protein Boosters** section, reheat/food-safety card (rice-based W3A: reheat once, piping hot).
- **Route** in `server/__init__.py` after the griddle route (~L1017): `GET /nutrition/recipes/weekday-dinners` → template, empty context.
- **Links**: new tab in `recipes_subnav.html`; TOC entry in `recipes.html`; cross-link from `recipes-griddle.html` TOC; link from the rewritten nutrition.html dinner card and meals.html banner.

### 3. Shopping lists (dinner ingredients, week-aware)

`templates/shopping_list_data.html`:
- `SHOP_CATEGORY_IDS` → add `"dinner"`; `DEFAULT_SHOP_CATS = ["breakfast","lunch","dinner"]`; label "Weekday dinners".
- New optional item field `weeks: [0,2]` (cycle-week indices; absent = all weeks). Add ~18–22 dinner items modelled on the existing schema: per-week proteins (chicken thighs top-up, 5% mince, turkey breast mince, chorizo), carbs (wholewheat spaghetti W2, extra potatoes W1/W4, crusty bread W3), red lentils W1, light coconut milk + mild korma paste W2, mixed-bean tins W3, cauliflower W4, passata `weeks:[0,1,2]`, root veg W1, casserole veg W4 — plus a weekly skyr/0% Greek yogurt line ("protein dessert Mon–Thu + boosters") with no `weeks`.
- `itemVisibleForWeek(item, cycleWeek)`: keep `freq:"recovery"` → week 3 only; add `if (item.weeks && !item.weeks.includes(cycleWeek)) return false`.

`templates/shopping_list_render.html` + `shopping_list_controls.html`: replace the binary build/recovery toggle with **four week buttons (W1–W3 build, W4 recovery)** — `weekMode` string becomes `cycleWeek` int 0–3, initialised from server `{{ cycle_week }}`; back-compat map legacy `?week=build|recovery` URL params and stale `localStorage` values; update the core-shop £ hint text (core now includes dinners).

`asda-shopping-list.html` + `lidl-shopping-list.html`: replace the "Gousto covers Mon–Thu dinners (not on this list)" banners/footers (Asda L85/L87/L107; Lidl L99/L101/L129) with the new dinner-on-list story; pass `cycleWeek: {{ cycle_week }}` into `initShoppingList`. `_shopping_list_context()` already returns `cycle_week` — no server change.

### 4. Sunday prep & storage (`templates/recipes.html`)

- **§17 storage table**: two new rows — Batch A (fridge, eaten day 1–2, well inside cooked-meat window) and Batch B (**freeze Sunday, move to fridge Tuesday evening** — avoids day-4 fridge meat; all four B recipes freeze well). Rice-based W3A note: cool fast, reheat once.
- **§18 schedule**: dinner batches share the already-hot oven/hob — insert steps 1b (Batch A into the 200 °C oven alongside lunch chicken), 2b (Batch B simmering on hob, hands-off), 6b (portion: A → fridge ×4, B → freezer ×4, label). Lead text: "~2 h" → "~2½ h, now including all four weekday dinners". Rewrite the Weeknights row (L750, last Gousto mention): reheat batch piping hot, protein dessert after, Tuesday night move Batch B to fridge.
- **§16 lead**: mention dinner batches run in parallel, link new page.

### 5. `templates/nutrition.html` + `templates/meals.html`

- nutrition.html: rename `.pc-gousto` → `.pc-dinners` (L56, L328); rewrite the principle card (L328–332) — "Dinners: Sunday Batch + Griddle", A/B rotation, no spice, protein dessert, link to new page; rewrite W4 recovery note (L377).
- meals.html: delete dead `.pc-gousto` CSS (L56); update the week banner (drop "weeks 1–3 identical", mention batch dinners, link recipes page).

### 6. Leave untouched

Root-level legacy static files `nutrition-plan.html` and `fuel_plan_6.html` are not served by the app — leave as-is. Stale AI caches (`daily_advice`, weekly briefing in `text_cache`, coach memo) may mention Gousto until they naturally refresh; no code change.

### 7. Tests

- New `tests/test_weekday_dinners.py`:
  - For every (cycle_week 0–3 × weekday 0–3 × applicable day type): last `_assemble_meals` tuple is slot "Dinner", protein ≥ 58, Mon/Tue share Batch A name, Wed differs from Mon.
  - Recovery-week dinners ≤ 600 kcal; build weeks ≥ 650.
  - Friday (`bike_fri`; `recovery_weekday` wd=4) keeps the griddle dinner.
  - Regression guard: `"gousto"` (case-insensitive) absent from `meal_cycle_full()`, `SIMPLE_RULES`+`PRINCIPLES`, and `json.dumps([build_meal_week(i) for i in range(4)])`.
  - `build_meal_week(3)` collapsed card dinner names both W4 batches.
- Existing suite unaffected (only `test_nutrition_kj.py` imports from `nutrition_plan`, just `adjust_for_session_kj`).

### 8. Docs

CLAUDE.md nutrition note: one line describing `WEEKDAY_DINNERS` injection (mirrors `BREAKFASTS` pattern) + the new route.

## Verification

1. `pytest` (full suite + new test file).
2. `pip install --force-reinstall .` (templates are package data), then `launchctl kickstart -k "gui/$(id -u)/com.ai-endurance-coach-over50.server"`.
3. Browse `http://127.0.0.1:8743`:
   - `/nutrition` — checklist shows today's batch dinner; rewritten dinner card; recovery note.
   - `/nutrition/meals` — 4 week tabs: Mon/Tue = A, Wed/Thu = B, names differ W1–W3; W4 collapsed card shows dual-batch summary; macro pills render.
   - `/nutrition/recipes` — updated §16–18 + TOC link; `/nutrition/recipes/weekday-dinners` — new page, subnav active.
   - Both shopping lists — "Weekday dinners" category on by default; W1–W4 buttons switch dinner items; recovery-only items still W4; legacy `?week=build` URL and stale localStorage don't break.
4. Coach context: `python -c "from ai_endurance_coach_over50.nutrition_plan import meal_cycle_full; print(meal_cycle_full())"` — week-specific dinners, zero "Gousto".
5. `grep -rin gousto ai_endurance_coach_over50/` → empty.

## Critical files

- `ai_endurance_coach_over50/nutrition_plan.py` (WEEKDAY_DINNERS + `_assemble_meals` injection + text rewrites)
- `ai_endurance_coach_over50/templates/recipes-weekday-dinners.html` (new; model: `recipes-griddle.html`)
- `ai_endurance_coach_over50/templates/shopping_list_data.html` / `shopping_list_render.html` / `shopping_list_controls.html`
- `ai_endurance_coach_over50/templates/recipes.html`, `nutrition.html`, `meals.html`, `asda-shopping-list.html`, `lidl-shopping-list.html`
- `ai_endurance_coach_over50/server/__init__.py` (one new route ~L1017)
- `tests/test_weekday_dinners.py` (new)

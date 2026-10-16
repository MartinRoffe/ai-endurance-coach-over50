"""Breakfasts, Sunday batches, and weekend plates.

Ingredient grams are raw weights for the whole batch (or for one plate when
servings is 1). Macros are computed in model.py.
"""
from __future__ import annotations

from .model import Ingredient, Recipe


def _ing(*pairs: tuple[str, float]) -> tuple[Ingredient, ...]:
    return tuple(Ingredient(food_id, grams) for food_id, grams in pairs)


def _R(
    id: str,
    name: str,
    slot: str,
    servings: int,
    items: tuple[Ingredient, ...],
    method: tuple[str, ...],
    equipment: tuple[str, ...],
    fridge: str,
    freezer: str,
    protein: str,
    summary: str,
    serve_with: tuple[Ingredient, ...] = (),
    batch: bool = False,
) -> Recipe:
    return Recipe(
        id=id,
        name=name,
        slot=slot,
        servings=servings,
        ingredients=items,
        method=method,
        equipment=equipment,
        fridge=fridge,
        freezer=freezer,
        protein=protein,
        summary=summary,
        serve_with=serve_with,
        batch=batch,
    )


# ── Breakfasts (one plate) ────────────────────────────────────────────────────

PORRIDGE = _R(
    "porridge",
    "Porridge",
    "breakfast",
    1,
    _ing(("oats", 60), ("milk_semi", 300), ("banana", 100), ("salt", 0.3)),
    (
        "Weigh 60 g porridge oats into a small saucepan.",
        "Pour in 300 ml semi-skimmed milk.",
        "Bring to a simmer, stirring so it does not catch, then cook on low for 5 minutes until the oats are soft.",
        "Stir in a pinch of salt (0.3 g).",
        "Slice 100 g banana on top and eat it straight away.",
    ),
    ("Saucepan", "Wooden spoon"),
    "Eat this morning. Leftover porridge keeps in the fridge until the next day and reheats with a splash of milk.",
    "Not a freezer dish.",
    "oats",
    "Oats simmered in milk, banana on top. The milk is the calcium with breakfast.",
)

OVERNIGHT_OATS = _R(
    "overnight-oats",
    "Overnight oats",
    "breakfast",
    1,
    _ing(("oats", 55), ("milk_semi", 250), ("yoghurt_hp", 120), ("apple", 120)),
    (
        "The night before, weigh 55 g oats into a jar or tub.",
        "Stir in 250 ml semi-skimmed milk and 120 g plain high-protein yoghurt.",
        "Cover and leave in the fridge overnight.",
        "In the morning, chop 120 g apple on top. Eat it cold.",
    ),
    ("Jar or tub", "Spoon"),
    "Make it the night before. Eat it the next morning. Do not keep it a second night.",
    "Not a freezer dish.",
    "oats",
    "Oats soaked in milk and yoghurt overnight, apple in the morning.",
)

SCRAMBLED_EGGS = _R(
    "scrambled-eggs",
    "Scrambled eggs on toast",
    "breakfast",
    1,
    _ing(
        ("egg", 174),
        ("milk_semi", 280),
        ("butter", 8),
        ("bread", 80),
        ("tomato", 100),
        ("black_pepper", 0.2),
    ),
    (
        "Crack 3 eggs (174 g) into a jug with 30 ml of the milk and a little black pepper. Beat them.",
        "Melt 8 g butter in a non-stick pan on a medium-low heat.",
        "Pour in the eggs and stir slowly until they are just set, about 2 to 3 minutes. Take them off while they still look slightly soft.",
        "Toast 2 slices of white bread (80 g). Halve 100 g tomato and warm it in the same pan.",
        "Drink the remaining 250 ml milk with the plate.",
    ),
    ("Non-stick frying pan", "Toaster"),
    "Eat straight away. Eggs are not a batch item.",
    "Not a freezer dish.",
    "eggs",
    "Three eggs scrambled in butter on toast, tomatoes, and a glass of milk.",
)

POACHED_EGGS = _R(
    "poached-eggs",
    "Poached eggs on toast",
    "breakfast",
    1,
    _ing(
        ("egg", 116),
        ("bread", 80),
        ("butter", 8),
        ("tomato", 100),
        ("milk_semi", 250),
    ),
    (
        "Bring a wide pan of water to a bare simmer. Do not salt the water.",
        "Crack 2 eggs (116 g) in, one at a time, and poach for 3 minutes for a soft yolk.",
        "Lift them out with a slotted spoon.",
        "Toast 2 slices of white bread (80 g) and spread with 8 g butter. Add 100 g sliced tomato.",
        "Drink 250 ml semi-skimmed milk with the plate.",
    ),
    ("Saucepan", "Slotted spoon", "Toaster"),
    "Eat straight away.",
    "Not a freezer dish.",
    "eggs",
    "Two poached eggs on buttered toast, tomato, and a glass of milk.",
)

OMELETTE = _R(
    "omelette",
    "Mushroom and tomato omelette",
    "breakfast",
    1,
    _ing(
        ("egg", 174),
        ("mushroom", 80),
        ("tomato", 80),
        ("butter", 8),
        ("bread", 40),
        ("milk_semi", 200),
        ("lettuce", 40),
        ("black_pepper", 0.2),
    ),
    (
        "Slice 80 g mushrooms and 80 g tomato.",
        "Melt 8 g butter in a non-stick pan and soften the mushrooms and tomato for 3 minutes. Tip them onto a plate.",
        "Beat 3 eggs (174 g) with a little black pepper.",
        "Pour the eggs into the same pan on a medium heat. When the base is set, scatter the vegetables over, fold the omelette, and slide it out.",
        "Serve with 1 slice of toast (40 g), 40 g lettuce, and 200 ml milk.",
    ),
    ("Non-stick frying pan", "Toaster"),
    "Eat straight away.",
    "Not a freezer dish.",
    "eggs",
    "A three-egg omelette with mushroom and tomato, toast, and milk. No cheese.",
)

YOGHURT_BOWL = _R(
    "yoghurt-bowl",
    "Yoghurt bowl with fruit and oat granola",
    "breakfast",
    1,
    _ing(
        ("yoghurt_hp", 250),
        ("oats", 40),
        ("honey", 12),
        ("olive_oil", 4),
        ("banana", 80),
        ("blueberry", 80),
    ),
    (
        "Heat the oven to 160°C. Stir 40 g oats with 12 g honey and 4 g olive oil.",
        "Spread the oats on a small tray and bake for 12 minutes, stirring once, until they smell toasted. Cool them. This is the granola, oats only.",
        "Spoon 250 g plain high-protein yoghurt into a bowl.",
        "Add the cooled oats, 80 g sliced banana, and 80 g blueberries.",
    ),
    ("Oven", "Baking tray", "Bowl"),
    "The granola keeps in a jar for a week. Build the bowl the morning you eat it.",
    "Not a freezer dish.",
    "dairy",
    "High-protein yoghurt, toasted oats, banana, and blueberries.",
)

CEREAL = _R(
    "cereal-milk",
    "Cereal with milk",
    "breakfast",
    1,
    _ing(("cornflakes", 40), ("milk_semi", 300), ("yoghurt_hp", 150), ("banana", 80)),
    (
        "Put 40 g cornflakes in a bowl.",
        "Pour on 300 ml semi-skimmed milk.",
        "Slice 80 g banana on top and eat it straight away, before the flakes go soft.",
        "Spoon 150 g plain high-protein yoghurt into a separate small bowl and eat it with the cereal. It is the breakfast dairy, not a topping for dinner.",
    ),
    ("Bowl",),
    "Eat straight away.",
    "Not a freezer dish.",
    "dairy",
    "Cornflakes, milk, banana, and a side bowl of high-protein yoghurt.",
)

FULL_ENGLISH = _R(
    "full-english",
    "Full English",
    "breakfast",
    1,
    _ing(
        ("egg", 116),
        ("bacon", 35),
        ("sausage", 45),
        ("baked_beans", 120),
        ("tomato", 80),
        ("mushroom", 70),
        ("bread", 40),
        ("olive_oil", 6),
        ("milk_semi", 200),
    ),
    (
        "Heat a griddle or Blackstone to a medium heat and brush it with 6 g olive oil.",
        "Put 1 plain pork sausage (45 g) on the griddle. Turn it until it is cooked through, about 10 minutes.",
        "Add 1 back-bacon rasher (35 g), 70 g mushrooms, and 80 g halved tomato. Cook the bacon until the fat is clear.",
        "Heat 120 g baked beans in a small pan on the side.",
        "Fry 2 eggs (116 g) on the griddle, or in a ring if you want a tidy edge.",
        "Toast 1 slice of white bread (40 g).",
        "Drink 200 ml semi-skimmed milk with the plate.",
    ),
    ("Griddle or Blackstone", "Small saucepan", "Toaster"),
    "Cook it on Saturday morning and eat it then. It does not keep.",
    "Not a freezer dish.",
    "eggs",
    "Griddle breakfast: egg, bacon, sausage, beans, tomato, mushroom, toast, and milk.",
)

BREAKFASTS: dict[str, Recipe] = {
    r.id: r
    for r in (
        PORRIDGE,
        OVERNIGHT_OATS,
        SCRAMBLED_EGGS,
        POACHED_EGGS,
        OMELETTE,
        YOGHURT_BOWL,
        CEREAL,
        FULL_ENGLISH,
    )
}

# Weekday rotation, Saturday excluded (that morning is the Full English).
WEEKDAY_BREAKFAST_IDS = (
    "porridge",
    "overnight-oats",
    "scrambled-eggs",
    "poached-eggs",
    "omelette",
    "yoghurt-bowl",
    "cereal-milk",
)


# ── Sunday batches ────────────────────────────────────────────────────────────
# servings is the written batch the method describes. The week cooks the sum of the plates.

W0_SOUP = _R(
    "turkey-leek-potato-soup",
    "Turkey, leek and potato soup",
    "soup",
    4,
    _ing(
        ("turkey_mince", 780),
        ("leek", 400),
        ("potato", 520),
        ("cabbage", 200),
        ("onion", 160),
        ("garlic", 12),
        ("olive_oil", 8),
        ("salt", 4),
        ("parsley", 12),
    ),
    (
        "Dice 520 g potato and slice 400 g leek, 200 g cabbage, and 160 g onion. Chop 12 g garlic.",
        "Heat 8 g olive oil in the soup-maker jug or a large pot and soften the onion, leek, and garlic for 5 minutes. If the soup maker has no sauté step, do this in a pan first.",
        "Add 780 g turkey thigh mince and stir until it loses its pink colour.",
        "Add the potato, cabbage, 4 g salt, and water to the soup-maker fill line (about 1.2 litres).",
        "Run the chunky programme, about 25 minutes. Check the potato is soft. If you are on the hob, simmer 25 minutes with the lid on.",
        "Stir in 12 g chopped parsley. Cool the jug in cold water, then portion into 4 tubs.",
    ),
    ("Soup maker", "Knife", "Four tubs"),
    "Eat Monday to Wednesday from the fridge. Cool it within 90 minutes of cooking.",
    "Freeze the fourth tub on Sunday.",
    "turkey",
    "Chunky turkey soup with leek, cabbage, and potato. Soup maker, chunky programme.",
    batch=True,
)

W0_POT_A = _R(
    "beef-mushroom-pasta",
    "Beef and mushroom pasta",
    "dinner",
    4,
    _ing(
        ("beef_mince", 740),
        ("pasta", 160),
        ("passata", 320),
        ("mushroom", 280),
        ("onion", 160),
        ("garlic", 10),
        ("olive_oil", 8),
        ("oregano", 2),
        ("salt", 4),
        ("black_pepper", 1),
    ),
    (
        "Chop 160 g onion, 10 g garlic, and 280 g mushrooms.",
        "Warm 8 g olive oil in a frying pan, soften the onion and garlic for 5 minutes, then brown 740 g lean beef mince.",
        "Tip the mince, onion, mushrooms, 320 g passata, 2 g oregano, 4 g salt, and 1 g black pepper into the slow cooker. Add 160 ml water.",
        "Cook on low for 6 hours, or on high for 3 hours, until the mince is tender.",
        "Boil 160 g dried pasta in a separate pan until just tender, about 8 minutes. Drain it.",
        "Stir the pasta through the sauce. Cool, then divide into 4 tubs. The pasta is already in the dish, so do not add bread or potato.",
    ),
    ("Frying pan", "Slow cooker", "Saucepan", "Four tubs"),
    "Fridge portions are for this week's plates. Eat within 3 days.",
    "Four portions, one for each plate. Nothing extra to freeze.",
    "beef",
    "Slow-cooker beef and mushroom sauce, pasta stirred in at the end. Low for 6 hours.",
    batch=True,
)

W0_POT_B = _R(
    "salmon-couscous-peas",
    "Salmon, couscous and peas",
    "dinner",
    4,
    _ing(
        ("salmon", 740),
        ("couscous", 180),
        ("pea", 280),
        ("lemon", 40),
        ("olive_oil", 8),
        ("parsley", 12),
        ("salt", 3),
        ("black_pepper", 1),
    ),
    (
        "Cut 740 g salmon into 8 even pieces and season with 3 g salt and 1 g black pepper.",
        "Put 180 g couscous in a wide lidded pan with 220 ml boiling water, 40 g lemon juice, and 8 g olive oil. Cover and leave for 5 minutes.",
        "Fluff the couscous, then fold in 280 g frozen peas.",
        "Lay the salmon on top, cover, and cook on the lowest hob heat for 10 minutes until the salmon flakes and the peas are hot.",
        "Stir in 12 g parsley. Divide into 4 tubs and cool them fast. Fish is not a slow-cooker dish.",
        "The couscous is the carbohydrate. Do not add bread, rice, or potato.",
    ),
    ("Lidded saucepan", "Four tubs"),
    "Keep Tuesday's portion in the fridge and eat it by Tuesday night.",
    "Freeze the other three tubs on Sunday. Move one to the fridge on Wednesday night for Thursday. Leave the spare two frozen.",
    "fish",
    "Hob pot: couscous, peas, and salmon steamed on top for 10 minutes.",
    batch=True,
)

W1_SOUP = _R(
    "pork-apple-cabbage-soup",
    "Pork, apple and cabbage soup",
    "soup",
    4,
    _ing(
        ("pork_loin", 780),
        ("cabbage", 480),
        ("apple", 360),
        ("onion", 160),
        ("garlic", 12),
        ("olive_oil", 8),
        ("thyme", 2),
        ("salt", 4),
    ),
    (
        "Dice 780 g pork loin. Shred 480 g white cabbage, slice 160 g onion and 12 g garlic, and chop 360 g apple.",
        "Brown the pork in 8 g olive oil in a pan. Soften the onion and garlic with it.",
        "Tip everything into the soup maker with the cabbage, apple, 2 g dried thyme, 4 g salt, and water to the fill line.",
        "Run the chunky programme, about 25 minutes, until the pork is tender. On the hob, simmer 30 minutes with the lid on.",
        "Cool and portion into 4 tubs. There is no potato, rice, or pasta in the soup.",
        "When you eat a bowl, toast or cut 50 g white bread to go with it. Do not freeze the bread.",
    ),
    ("Soup maker", "Frying pan", "Four tubs"),
    "Eat three bowls Monday to Wednesday from the fridge. Cool within 90 minutes.",
    "Freeze the fourth tub on Sunday. Freeze the soup, not the bread.",
    "pork",
    "Chunky pork, apple, and cabbage soup. Bread on the side of the bowls you eat.",
    serve_with=_ing(("bread", 50)),
    batch=True,
)

W1_POT_A = _R(
    "turkey-rice-peppers",
    "Turkey, rice and peppers",
    "dinner",
    4,
    _ing(
        ("turkey_mince", 760),
        ("rice", 104),
        ("milk_semi", 200),
        ("pepper", 280),
        ("courgette", 200),
        ("pea", 200),
        ("onion", 160),
        ("garlic", 10),
        ("olive_oil", 8),
        ("salt", 4),
        ("parsley", 8),
    ),
    (
        "Rinse 104 g basmati rice until the water runs almost clear.",
        "Chop 160 g onion, 10 g garlic, 280 g peppers, and 200 g courgette.",
        "Soften the onion and garlic in 8 g olive oil, then brown 760 g turkey mince.",
        "Put the mince, rice, pepper, courgette, 200 g frozen peas, 4 g salt, 200 ml semi-skimmed milk, and 240 ml water into the slow cooker.",
        "Cook on high for 1 hour 45 minutes. Check the rice. If there is still a hard core, give it another 15 minutes. Do not leave rice on low all day.",
        "Stir in 8 g parsley, cool, and divide into 4 tubs. The milk is in the sauce. Do not add yoghurt on top. The rice is the carbohydrate, so do not add bread or potato.",
    ),
    ("Frying pan", "Slow cooker", "Four tubs"),
    "Fridge portions keep 3 days. Cool within 90 minutes.",
    "Four portions, one for each plate. Nothing extra to freeze.",
    "turkey",
    "Slow-cooker turkey rice with pepper, courgette, and peas. High for 1 hour 45 minutes.",
    batch=True,
)

W1_POT_B = _R(
    "cod-potato-milk",
    "Cod, potato and milk pot",
    "dinner",
    4,
    _ing(
        ("cod", 760),
        ("potato", 600),
        ("milk_semi", 600),
        ("pea", 200),
        ("onion", 120),
        ("olive_oil", 8),
        ("dill", 8),
        ("lemon", 30),
        ("salt", 3),
    ),
    (
        "Dice 600 g potato and slice 120 g onion.",
        "Warm 8 g olive oil in a wide lidded pan, soften the onion for 5 minutes, then add the potato, 600 ml semi-skimmed milk, 150 ml water, and 3 g salt.",
        "Simmer with the lid on for 12 minutes until the potato is nearly soft.",
        "Lay 760 g cod on top, add 200 g frozen peas, cover, and cook 8 minutes until the fish flakes.",
        "Stir in 8 g dill and 30 g lemon juice. Divide into 4 tubs and cool them fast.",
        "The milk is the calcium in the sauce. Do not add yoghurt on top. The potato is the carbohydrate.",
    ),
    ("Lidded saucepan", "Four tubs"),
    "Keep Tuesday's portion in the fridge and eat it by Tuesday.",
    "Freeze the other three on Sunday. Thaw one on Wednesday night for Thursday. Leave two frozen.",
    "fish",
    "Short hob simmer: potato in milk, cod and peas for the last 8 minutes.",
    batch=True,
)

W2_SOUP = _R(
    "turkey-broccoli-soup",
    "Turkey and broccoli soup",
    "soup",
    4,
    _ing(
        ("turkey_mince", 780),
        ("broccoli", 480),
        ("onion", 180),
        ("milk_semi", 400),
        ("garlic", 12),
        ("olive_oil", 8),
        ("salt", 4),
    ),
    (
        "Chop 480 g broccoli, 180 g onion, and 12 g garlic.",
        "Soften the onion and garlic in 8 g olive oil, then brown 780 g turkey mince.",
        "Add the broccoli, 4 g salt, and 900 ml water.",
        "Run the soup maker on the smooth programme for about 20 minutes, or simmer 20 minutes on the hob and blend until it is as smooth as you like.",
        "Stir in 400 ml semi-skimmed milk and heat for 2 minutes. Do not boil it hard once the milk is in.",
        "Cool and portion into 4 tubs. Serve each eaten bowl with 50 g white bread. The bread is not in the frozen tub.",
    ),
    ("Soup maker", "Stick blender if you are on the hob", "Four tubs"),
    "Eat three bowls from the fridge Monday to Wednesday.",
    "Freeze the fourth tub on Sunday, without the bread.",
    "turkey",
    "Smooth turkey and broccoli soup, milk stirred in at the end, bread on the side.",
    serve_with=_ing(("bread", 50)),
    batch=True,
)

W2_POT_A = _R(
    "beef-lentil-pasta",
    "Beef and lentil pasta",
    "dinner",
    4,
    _ing(
        ("beef_mince", 740),
        ("red_lentil", 96),
        ("pasta", 112),
        ("passata", 320),
        ("onion", 160),
        ("mushroom", 200),
        ("carrot", 160),
        ("garlic", 10),
        ("olive_oil", 8),
        ("oregano", 2),
        ("salt", 4),
    ),
    (
        "Rinse 96 g red lentils. Chop 160 g onion, 10 g garlic, 200 g mushrooms, and 160 g carrot.",
        "Brown 740 g lean beef mince with the onion and garlic in 8 g olive oil.",
        "Add the lentils, carrot, mushrooms, 320 g passata, 2 g oregano, 4 g salt, and 400 ml water to the slow cooker.",
        "Cook on low for 6 hours, or high for 3 hours. The lentils should be soft but they stay a small part of the pot, about 24 g dry each.",
        "Boil 112 g pasta until just tender, drain, and stir it through the sauce.",
        "Cool and divide into 4 tubs. Pasta is already in the bowl, so do not add a carb side.",
    ),
    ("Frying pan", "Slow cooker", "Saucepan", "Four tubs"),
    "Fridge portions keep 3 days.",
    "Four portions, one for each plate. Nothing extra to freeze.",
    "beef",
    "Slow-cooker beef with a modest amount of red lentil, pasta stirred in at the end. Low for 6 hours.",
    batch=True,
)

W2_POT_B = _R(
    "salmon-beans-potato",
    "Salmon, green beans and potatoes",
    "dinner",
    4,
    _ing(
        ("salmon", 740),
        ("potato", 560),
        ("green_bean", 320),
        ("lemon", 40),
        ("olive_oil", 8),
        ("dill", 8),
        ("salt", 3),
    ),
    (
        "Dice 560 g potato. Trim 320 g green beans.",
        "Simmer the potato in a lidded pan with 400 ml water and 3 g salt for 10 minutes.",
        "Add the beans and lay 740 g salmon on top. Cover and cook on low for 10 minutes until the salmon flakes and the potato is soft.",
        "Drain any excess water. Stir in 8 g olive oil, 40 g lemon juice, and 8 g dill.",
        "Divide into 4 tubs and cool them fast. This is a hob dish, not a slow cooker.",
        "The potato is the carbohydrate.",
    ),
    ("Lidded saucepan", "Four tubs"),
    "Fridge the Tuesday portion and eat it by Tuesday.",
    "Freeze three tubs on Sunday. Thaw one Wednesday night for Thursday. Leave two frozen.",
    "fish",
    "Hob pot: salmon steamed over potato and green beans for 10 minutes.",
    batch=True,
)

W3_SOUP = _R(
    "beef-swede-soup",
    "Beef and swede soup",
    "soup",
    4,
    _ing(
        ("beef_mince", 780),
        ("swede", 720),
        ("cabbage", 280),
        ("onion", 160),
        ("garlic", 12),
        ("olive_oil", 8),
        ("thyme", 2),
        ("salt", 4),
    ),
    (
        "Dice 720 g swede. Shred 280 g cabbage. Chop 160 g onion and 12 g garlic.",
        "Brown 780 g lean beef mince with the onion and garlic in 8 g olive oil.",
        "Add the swede, cabbage, 2 g thyme, 4 g salt, and water to the soup-maker fill line.",
        "Run the chunky programme, about 28 minutes, until the swede is soft. On the hob, simmer 30 minutes.",
        "Cool and portion into 4 tubs.",
        "Eat each bowl with 50 g white bread. Do not put the bread in the tub.",
    ),
    ("Soup maker", "Frying pan", "Four tubs"),
    "Eat three bowls from the fridge Monday to Wednesday.",
    "Freeze the fourth tub on Sunday, without the bread.",
    "beef",
    "Chunky beef and swede soup. Bread on the side.",
    serve_with=_ing(("bread", 50)),
    batch=True,
)

W3_POT_A = _R(
    "turkey-meatball-pasta",
    "Turkey meatballs and pasta",
    "dinner",
    4,
    _ing(
        ("turkey_mince", 780),
        ("pasta", 160),
        ("passata", 400),
        ("mushroom", 240),
        ("onion", 160),
        ("garlic", 10),
        ("olive_oil", 8),
        ("oregano", 2),
        ("salt", 4),
    ),
    (
        "Chop 160 g onion, 10 g garlic, and 240 g mushrooms very fine. Mix them with 780 g turkey mince, 2 g oregano, and 4 g salt.",
        "Roll the mix into small balls, about 16.",
        "Brown the balls in 8 g olive oil in a frying pan, in two batches.",
        "Tip them into the slow cooker with 400 g passata and 120 ml water.",
        "Cook on low for 5 hours, or high for 2 hours 30 minutes.",
        "Boil 160 g pasta until just tender, drain, and stir it through. Cool and divide into 4 tubs. No extra carbohydrate on the side.",
    ),
    ("Frying pan", "Slow cooker", "Saucepan", "Four tubs"),
    "Fridge portions keep 3 days.",
    "Four portions, one for each plate. Nothing extra to freeze.",
    "turkey",
    "Slow-cooker turkey meatballs in passata, pasta stirred in. Low for 5 hours.",
    batch=True,
)

W3_POT_B = _R(
    "lemon-chicken-rice",
    "Lemon chicken and rice",
    "dinner",
    4,
    _ing(
        ("chicken_breast", 740),
        ("rice", 200),
        ("pepper", 280),
        ("green_bean", 280),
        ("lemon", 60),
        ("garlic", 12),
        ("olive_oil", 8),
        ("parsley", 12),
        ("salt", 3),
    ),
    (
        "Cut 740 g chicken breast into thick strips. Chop 280 g peppers and 12 g garlic. Trim 280 g green beans.",
        "Rinse 200 g basmati rice.",
        "Warm 8 g olive oil in a pan, colour the chicken for 3 minutes, then add the garlic and pepper for 2 minutes.",
        "Put the chicken, rice, beans, 60 g lemon juice, 3 g salt, and 420 ml water into the slow cooker.",
        "Cook on high for 1 hour 45 minutes, until the rice is tender and the chicken is cooked through. Give it 15 minutes more if the rice is still firm.",
        "Stir in 12 g parsley. Divide into 4 tubs. The rice is the carbohydrate. Do not add yoghurt.",
    ),
    ("Frying pan", "Slow cooker", "Four tubs"),
    "Fridge the Tuesday portion and eat it by Tuesday.",
    "Freeze three tubs on Sunday. Thaw one Wednesday night for Thursday. Leave two frozen.",
    "chicken",
    "Slow-cooker lemon chicken and rice with pepper and green beans. High for 1 hour 45 minutes.",
    batch=True,
)

BATCHES: dict[str, Recipe] = {
    r.id: r
    for r in (
        W0_SOUP,
        W0_POT_A,
        W0_POT_B,
        W1_SOUP,
        W1_POT_A,
        W1_POT_B,
        W2_SOUP,
        W2_POT_A,
        W2_POT_B,
        W3_SOUP,
        W3_POT_A,
        W3_POT_B,
    )
}


# ── Weekend plates (cooked that day, one serving) ────────────────────────────

def _weekend(
    id: str,
    name: str,
    items: tuple[Ingredient, ...],
    method: tuple[str, ...],
    equipment: tuple[str, ...],
    protein: str,
    summary: str,
) -> Recipe:
    return _R(
        id,
        name,
        "weekend",
        1,
        items,
        method,
        equipment,
        "Cook it when you eat it. Fridge leftovers the same day only.",
        "Not a batch dish.",
        protein,
        summary,
    )


WEEKEND: dict[str, Recipe] = {
    r.id: r
    for r in (
        _weekend(
            "turkey-tomato-roll",
            "Turkey and tomato roll",
            _ing(
                ("turkey_breast", 175),
                ("bread", 80),
                ("tomato", 100),
                ("lettuce", 40),
                ("olive_oil", 2),
                ("black_pepper", 0.2),
            ),
            (
                "Heat a griddle or Blackstone to medium-high.",
                "Brush 175 g turkey breast with 2 g olive oil and a little black pepper.",
                "Grill it for about 4 minutes a side, until the thickest part is cooked through and no longer pink.",
                "Rest it 2 minutes, then slice it.",
                "Fill 80 g white bread (a roll or two slices) with the turkey, 100 g tomato, and 40 g lettuce.",
            ),
            ("Griddle or Blackstone",),
            "turkey",
            "Griddled turkey breast in a roll with tomato and lettuce.",
        ),
        _weekend(
            "steak-mushroom-potato",
            "Griddled steak, mushrooms and potato",
            _ing(
                ("beef_steak", 185),
                ("potato", 250),
                ("mushroom", 100),
                ("olive_oil", 2),
                ("salt", 0.5),
                ("black_pepper", 0.3),
            ),
            (
                "Dice 250 g potato. Boil it for 8 minutes, drain, and shake the pan so the edges roughen.",
                "Heat a griddle or Blackstone. Toss the potato with 2 g olive oil and cook it, turning, until browned, about 8 minutes.",
                "Push the potato aside. Season 185 g lean steak with 0.5 g salt and a little black pepper and cook it to your liking, about 3 minutes a side for medium.",
                "Fry 100 g mushrooms in the remaining 3 g oil beside the steak.",
                "Rest the steak for 3 minutes, then eat it with the potato and mushrooms.",
            ),
            ("Griddle or Blackstone", "Saucepan"),
            "beef",
            "Griddled lean steak with mushrooms and potato wedges.",
        ),
        _weekend(
            "chicken-pepper-roll",
            "Griddled chicken and pepper roll",
            _ing(
                ("chicken_breast", 175),
                ("pepper", 100),
                ("bread", 80),
                ("lettuce", 30),
                ("olive_oil", 2),
                ("lemon", 10),
                ("black_pepper", 0.2),
            ),
            (
                "Heat a griddle or Blackstone to medium-high.",
                "Toss 175 g chicken breast and 100 g sliced pepper with 2 g olive oil and a little black pepper.",
                "Grill the chicken for about 5 minutes a side, until it is cooked through. Grill the pepper alongside until it is soft.",
                "Rest the chicken 2 minutes, slice it, and squeeze 10 g lemon juice over it.",
                "Eat it in 80 g white bread with 30 g lettuce.",
            ),
            ("Griddle or Blackstone",),
            "chicken",
            "Griddled chicken and pepper in a roll.",
        ),
        _weekend(
            "pork-chop-apple-cabbage",
            "Pork chop, apple and cabbage",
            _ing(
                ("pork_loin", 185),
                ("cabbage", 150),
                ("apple", 100),
                ("olive_oil", 2),
                ("salt", 0.5),
            ),
            (
                "Shred 150 g white cabbage and slice 100 g apple.",
                "Heat a griddle or a wide pan with 2 g olive oil.",
                "Cook a 185 g pork loin chop for about 5 minutes a side, until the juices run clear. Lift it out to rest.",
                "Soften the cabbage and apple in the same pan for 5 minutes with 0.5 g salt.",
                "Serve the chop on the cabbage and apple.",
            ),
            ("Griddle or frying pan",),
            "pork",
            "Pan pork chop with cabbage and apple. No extra potato.",
        ),
        _weekend(
            "beef-patty-roll",
            "Beef patty and roll",
            _ing(
                ("beef_mince", 175),
                ("bread", 80),
                ("lettuce", 40),
                ("tomato", 80),
                ("onion", 30),
                ("olive_oil", 2),
                ("salt", 0.4),
                ("black_pepper", 0.2),
            ),
            (
                "Mix 175 g lean beef mince with 0.4 g salt and a little black pepper. Shape one patty.",
                "Heat a griddle or Blackstone, oil it with 2 g olive oil, and cook the patty for about 4 minutes a side.",
                "Slice 30 g onion onto the griddle beside it.",
                "Eat the patty in 80 g white bread with 40 g lettuce and 80 g tomato.",
            ),
            ("Griddle or Blackstone",),
            "beef",
            "Griddled lean beef patty in a roll with salad.",
        ),
        _weekend(
            "pork-chop-potato",
            "Pork chop and potato wedges",
            _ing(
                ("pork_loin", 175),
                ("potato", 230),
                ("apple", 80),
                ("olive_oil", 2),
                ("salt", 0.5),
            ),
            (
                "Heat the oven to 200°C, or heat a griddle if you are cooking outside.",
                "Cut 230 g potato into wedges, toss with 1 g olive oil and 0.5 g salt, and roast for 25 minutes, turning once. On a griddle, par-boil the wedges for 6 minutes first, then brown them.",
                "Cook a 175 g pork chop in the remaining 1 g oil for about 5 minutes a side, until the juices run clear.",
                "Warm 80 g sliced apple in the pan for the last 3 minutes.",
                "Rest the chop 2 minutes and eat it with the wedges and apple.",
            ),
            ("Oven or griddle", "Frying pan"),
            "pork",
            "Pork chop with potato wedges and apple.",
        ),
        _weekend(
            "mushroom-omelette-toast",
            "Mushroom omelette and toast",
            _ing(
                ("egg", 199),
                ("mushroom", 100),
                ("tomato", 80),
                ("butter", 2),
                ("bread", 40),
                ("milk_semi", 150),
                ("lettuce", 40),
            ),
            (
                "Slice 100 g mushrooms and soften them in 2 g butter for 4 minutes. Add 80 g tomato for the last minute.",
                "Beat 3 eggs plus a little extra (199 g) and pour them into the pan on a medium heat.",
                "When the base is set, fold the omelette and slide it onto a plate.",
                "Toast 40 g white bread. Serve with 40 g lettuce and 150 ml milk.",
            ),
            ("Non-stick frying pan", "Toaster"),
            "eggs",
            "Sunday omelette with mushrooms, toast, and a glass of milk.",
        ),
        _weekend(
            "turkey-peas-potato",
            "Turkey, peas and potato",
            _ing(
                ("turkey_breast", 165),
                ("potato", 220),
                ("pea", 100),
                ("olive_oil", 2),
                ("lemon", 10),
                ("salt", 0.4),
            ),
            (
                "Dice 220 g potato and boil it until tender, about 12 minutes. Add 100 g frozen peas for the last 3 minutes. Drain.",
                "Heat a griddle or pan with 2 g olive oil. Season 165 g turkey breast with 0.4 g salt and cook it about 4 minutes a side, until cooked through.",
                "Rest the turkey, slice it, and squeeze 10 g lemon juice over it.",
                "Eat it with the potato and peas.",
            ),
            ("Saucepan", "Griddle or frying pan"),
            "turkey",
            "Griddled turkey breast with potato and peas.",
        ),
        _weekend(
            "steak-salad-bread",
            "Steak, tomato and bread",
            _ing(
                ("beef_steak", 185),
                ("bread", 70),
                ("tomato", 120),
                ("lettuce", 50),
                ("cucumber", 50),
                ("olive_oil", 2),
                ("lemon", 10),
                ("salt", 0.4),
            ),
            (
                "Heat a griddle or Blackstone until it is hot.",
                "Oil 185 g lean steak with 2 g olive oil, season with 0.4 g salt, and cook about 3 minutes a side. Rest it for 3 minutes.",
                "Toss 120 g tomato, 50 g lettuce, and 50 g cucumber with 10 g lemon juice.",
                "Slice the steak and eat it with the salad and 70 g white bread.",
            ),
            ("Griddle or Blackstone",),
            "beef",
            "Griddled steak with a plain salad and bread. No potato.",
        ),
        _weekend(
            "jacket-beans",
            "Jacket potato, turkey and beans",
            _ing(
                ("turkey_breast", 160),
                ("potato", 200),
                ("baked_beans", 150),
                ("olive_oil", 2),
                ("salt", 0.3),
            ),
            (
                "Heat the oven to 200°C. Prick a 200 g potato, rub it with 2 g olive oil and 0.3 g salt, and bake for 50 minutes until the centre is soft. A microwave for 6 minutes, then 12 minutes in the oven, is fine if you are short of time.",
                "Heat a non-stick pan and cook 160 g turkey breast, sliced, for about 5 minutes until no longer pink.",
                "Heat 150 g baked beans in a small pan.",
                "Split the potato and fill it with the turkey and the beans. No cheese.",
            ),
            ("Oven", "Frying pan", "Small saucepan"),
            "turkey",
            "Baked potato filled with turkey and beans. The potato is the carbohydrate.",
        ),
        _weekend(
            "salmon-peas-potato",
            "Griddled salmon, peas and potato",
            _ing(
                ("salmon", 195),
                ("potato", 120),
                ("pea", 80),
                ("lemon", 15),
                ("olive_oil", 2),
                ("dill", 4),
                ("salt", 0.3),
            ),
            (
                "Boil 120 g diced potato until tender, about 10 minutes. Add 80 g frozen peas for the last 3 minutes. Drain and toss with 4 g dill.",
                "Heat a griddle or Blackstone. Oil 195 g salmon with 2 g olive oil and 0.3 g salt.",
                "Cook the salmon skin-side down for 4 minutes, turn it, and give it 3 minutes more, until it flakes.",
                "Squeeze 15 g lemon juice over it and eat it with the potato and peas.",
            ),
            ("Griddle or Blackstone", "Saucepan"),
            "fish",
            "Griddled salmon with potato and peas.",
        ),
    )
}


# cycle week 0..3 → recipe ids
WEEKS: tuple[dict[str, str], ...] = (
    {
        "soup": W0_SOUP.id,
        "pot_a": W0_POT_A.id,
        "pot_b": W0_POT_B.id,
        "sat_lunch": "turkey-tomato-roll",
        "sat_dinner": "steak-mushroom-potato",
        "sun_lunch": "chicken-pepper-roll",
        "sun_dinner": "pork-chop-apple-cabbage",
        "fri_dinner": "beef-patty-roll",
    },
    {
        "soup": W1_SOUP.id,
        "pot_a": W1_POT_A.id,
        "pot_b": W1_POT_B.id,
        "sat_lunch": "beef-patty-roll",
        "sat_dinner": "pork-chop-potato",
        "sun_lunch": "mushroom-omelette-toast",
        "sun_dinner": "turkey-peas-potato",
        "fri_dinner": "chicken-pepper-roll",
    },
    {
        "soup": W2_SOUP.id,
        "pot_a": W2_POT_A.id,
        "pot_b": W2_POT_B.id,
        "sat_lunch": "chicken-pepper-roll",
        "sat_dinner": "steak-salad-bread",
        "sun_lunch": "jacket-beans",
        "sun_dinner": "pork-chop-apple-cabbage",
        "fri_dinner": "turkey-tomato-roll",
    },
    {
        "soup": W3_SOUP.id,
        "pot_a": W3_POT_A.id,
        "pot_b": W3_POT_B.id,
        "sat_lunch": "jacket-beans",
        "sat_dinner": "salmon-peas-potato",
        "sun_lunch": "mushroom-omelette-toast",
        "sun_dinner": "steak-mushroom-potato",
        "fri_dinner": "pork-chop-apple-cabbage",
    },
)

# Mon–Fri lunch, then dinner. Friday dinner is fresh (fri_dinner), not a second pot A.
# Plate counts: soup 3, pot A 4, pot B 2.
WEEKDAY_PLATE: tuple[tuple[str, str], ...] = (
    ("soup", "pot_a"),
    ("soup", "pot_b"),
    ("soup", "pot_a"),
    ("pot_a", "pot_b"),
    ("pot_a", "fri_dinner"),
)

# Written batch size. The week cooks the sum of the plates actually eaten.
COOKED_SERVINGS = {"soup": 4, "pot_a": 4, "pot_b": 4}


def recipe_by_id(recipe_id: str) -> Recipe:
    if recipe_id in BREAKFASTS:
        return BREAKFASTS[recipe_id]
    if recipe_id in BATCHES:
        return BATCHES[recipe_id]
    if recipe_id in WEEKEND:
        return WEEKEND[recipe_id]
    raise KeyError(recipe_id)


def all_recipes() -> list[Recipe]:
    return list(BREAKFASTS.values()) + list(BATCHES.values()) + list(WEEKEND.values())

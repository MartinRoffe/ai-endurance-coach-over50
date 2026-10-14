"""Rotating one-pot and soup library.

Low-oxalate, moderate salt, one protein dose per portion. Batch four portions
and freeze. Chicken and rice is in the rotation, not every day.

Lunch is a soup-maker soup. Dinner is a slow-cooker or one-pot. Breakfast and
an evening dairy bowl are the other two protein doses.
"""
from __future__ import annotations

from datetime import date

# Foods left out for calcium-oxalate stones: spinach, chia, nuts, beetroot, rhubarb.
# Cheese is not used. Mild seasoning is fine. Salt the plate lightly.

PROTEIN_DOSE_G = 40

CARB_SIDE = {
    "easy": "Carb side: about a quarter plate of potato, rice or pasta.",
    "hard": "Carb side: about half a plate, plus a banana before and after training.",
    "long": "Carb side: a larger plate across the day (about 6–7 g/kg), plus 60–90 g/h on the bike.",
}

_CARB_G = {"easy": 30, "hard": 60, "long": 90}

# id, name, protein family, method, shop lines for 4 portions, short method.
# protein family is used to cap chicken at 1–2 servings in any 7 days.

ONE_POTS: list[dict] = [
    {
        "id": "chicken-rice",
        "name": "Lemon chicken and rice",
        "protein": "chicken",
        "kind": "dinner",
        "method": "Slow cooker or one pot. 4 portions, freeze three.",
        "shop": ["Chicken thigh fillets 700 g", "Basmati rice 300 g", "Courgette 2", "Lemon 1"],
        "steps": (
            "Brown the chicken. Add rice, chopped courgette, water to cover, lemon zest and a little salt. "
            "Slow cook on low until the rice is tender (or simmer, covered, about 25 minutes). "
            "Finish each bowl with a spoon of yoghurt so the calcium lands with the meal."
        ),
    },
    {
        "id": "turkey-stew",
        "name": "Turkey and potato stew",
        "protein": "turkey",
        "kind": "dinner",
        "method": "Slow cooker. 4 portions, freeze three.",
        "shop": ["Turkey mince 600 g", "Potatoes 800 g", "Carrot 3", "Courgette 1", "Passata 400 g"],
        "steps": (
            "Soften onion and garlic in a little oil. Add turkey mince, diced potato, carrot, courgette and passata. "
            "Slow cook until the potato is soft. Season mildly. Yoghurt on the portion."
        ),
    },
    {
        "id": "beef-stew",
        "name": "Lean beef stew",
        "protein": "beef",
        "kind": "dinner",
        "method": "Slow cooker. 4 portions, freeze three.",
        "shop": ["Lean beef stewing steak 700 g", "Potatoes 700 g", "Carrot 3", "Beef stock cube 1"],
        "steps": (
            "Brown the beef. Add potato, carrot and a lightly salted stock. "
            "Slow cook until the beef is tender. Yoghurt or a glass of milk with the bowl."
        ),
    },
    {
        "id": "pork-apple",
        "name": "Pork loin, apple and cabbage",
        "protein": "pork",
        "kind": "dinner",
        "method": "Slow cooker or one pot. 4 portions, freeze three.",
        "shop": ["Pork loin 700 g", "White cabbage 400 g", "Apple 2", "Potatoes 500 g"],
        "steps": (
            "Cube the pork. Add shredded cabbage, sliced apple and potato. A splash of water and mild mustard. "
            "Cook until the pork is tender. Dairy on the side."
        ),
    },
    {
        "id": "cod-potato",
        "name": "Cod and potato pot",
        "protein": "fish",
        "kind": "dinner",
        "method": "One pot, short simmer (fish does not want a long slow cook). 4 portions.",
        "shop": ["Cod fillets 700 g", "Potatoes 700 g", "Milk 500 ml", "Frozen peas 200 g", "Lemon 1"],
        "steps": (
            "Simmer diced potato in milk until nearly soft. Add cod and peas for the last 8 minutes. "
            "Dill or parsley, lemon, light salt. The milk is the calcium with the meal."
        ),
    },
    {
        "id": "lentil-beef",
        "name": "Beef and lentil pot",
        "protein": "beef",
        "kind": "dinner",
        "method": "Slow cooker. Lentils stay a modest part of the pot. 4 portions, freeze three.",
        "shop": ["Lean beef mince 500 g", "Red lentils 120 g", "Passata 400 g", "Carrot 2", "Rice 250 g"],
        "steps": (
            "Brown the mince. Add a modest amount of rinsed lentils, carrot, passata and water. "
            "Cook until the lentils are soft, then serve over rice. Yoghurt on top. Not a lentil-only meal."
        ),
    },
    {
        "id": "turkey-meatballs",
        "name": "Turkey meatballs and pasta",
        "protein": "turkey",
        "kind": "dinner",
        "method": "One pot. 4 portions, freeze three.",
        "shop": ["Turkey mince 600 g", "Passata 500 g", "Pasta 320 g", "Courgette 1"],
        "steps": (
            "Roll the mince into balls and brown them. Add passata and courgette, then pasta and water. "
            "Simmer until the pasta is done. A spoon of yoghurt in the bowl."
        ),
    },
    {
        "id": "salmon-rice",
        "name": "Salmon, rice and peas",
        "protein": "fish",
        "kind": "dinner",
        "method": "One pot. 4 portions.",
        "shop": ["Salmon fillets 600 g", "Basmati rice 300 g", "Frozen peas 250 g", "Lemon 1"],
        "steps": (
            "Rinse the rice, add water and a little salt, and simmer. "
            "Lay the salmon on top for the last 10 minutes, then fold through the peas and lemon. "
            "Milk or yoghurt with the meal."
        ),
    },
]

SOUPS: list[dict] = [
    {
        "id": "chicken-soup",
        "name": "Chicken and rice soup",
        "protein": "chicken",
        "kind": "soup",
        "method": "Soup maker or one pot. 4 portions, freeze three.",
        "shop": ["Chicken thigh fillets 600 g", "Basmati rice 200 g", "Carrot 2", "Courgette 1"],
        "steps": (
            "Simmer chicken and chopped carrot, then shred the chicken. "
            "Add rice and courgette and cook until the rice is soft. Light salt. Yoghurt in the bowl if you want."
        ),
    },
    {
        "id": "turkey-soup",
        "name": "Turkey and cabbage soup",
        "protein": "turkey",
        "kind": "soup",
        "method": "Soup maker. 4 portions, freeze three.",
        "shop": ["Turkey mince 500 g", "White cabbage 300 g", "Carrot 2", "Potato 400 g"],
        "steps": (
            "Brown the mince. Add cabbage, carrot, potato and water. "
            "Blend a little if you like it smooth, or leave it chunky. Mild herbs only."
        ),
    },
    {
        "id": "beef-soup",
        "name": "Beef and potato soup",
        "protein": "beef",
        "kind": "soup",
        "method": "Soup maker. 4 portions, freeze three.",
        "shop": ["Lean beef mince 500 g", "Potatoes 600 g", "Carrot 2", "Beef stock cube 1"],
        "steps": (
            "Brown the mince. Add potato, carrot and a light stock. Cook until soft. "
            "Season mildly. Milk or yoghurt with the bowl."
        ),
    },
    {
        "id": "fish-chowder",
        "name": "Fish and potato soup",
        "protein": "fish",
        "kind": "soup",
        "method": "Soup maker, short cook once the potato is soft. 4 portions.",
        "shop": ["White fish fillets 600 g", "Potatoes 600 g", "Milk 600 ml", "Frozen peas 150 g"],
        "steps": (
            "Cook potato in milk and a splash of water. Add fish and peas at the end so the fish stays tender. "
            "Lemon, dill, light salt. The milk is the calcium."
        ),
    },
    {
        "id": "lentil-soup",
        "name": "Lentil soup with yoghurt",
        "protein": "lentil",
        "kind": "soup",
        "method": "Soup maker. Lentils in moderation, dairy on top. 4 portions, freeze three.",
        "shop": ["Red lentils 200 g", "Carrot 2", "Potato 300 g", "Passata 300 g", "Greek yoghurt 400 g"],
        "steps": (
            "Simmer a modest amount of rinsed lentils with carrot, potato and passata. "
            "Each bowl gets a large spoon of yoghurt — that is part of the protein dose and the calcium."
        ),
    },
    {
        "id": "pork-soup",
        "name": "Pork and cabbage soup",
        "protein": "pork",
        "kind": "soup",
        "method": "Soup maker. 4 portions, freeze three.",
        "shop": ["Pork loin 500 g", "White cabbage 300 g", "Potato 400 g", "Carrot 1"],
        "steps": (
            "Dice the pork and brown it. Add cabbage, potato, carrot and water. "
            "Cook until the pork is tender. Light salt. Yoghurt on the side."
        ),
    },
]

_BY_ID = {m["id"]: m for m in ONE_POTS + SOUPS}

# 14-day eat rotation: (soup id, dinner id). Chicken on at most 2 days in any 7.
EAT_ROTATION: list[tuple[str, str]] = [
    ("turkey-soup", "beef-stew"),
    ("lentil-soup", "pork-apple"),
    ("fish-chowder", "turkey-stew"),
    ("beef-soup", "salmon-rice"),
    ("pork-soup", "chicken-rice"),
    ("turkey-soup", "cod-potato"),
    ("lentil-soup", "turkey-meatballs"),
    ("fish-chowder", "lentil-beef"),
    ("pork-soup", "turkey-meatballs"),
    ("turkey-soup", "chicken-rice"),
    ("lentil-soup", "beef-stew"),
    ("chicken-soup", "pork-apple"),
    ("beef-soup", "salmon-rice"),
    ("fish-chowder", "turkey-stew"),
]

# What to batch this cook-week (4 portions each). At most one chicken recipe.
COOK_WEEKS: list[dict] = [
    {"pots": ["beef-stew", "pork-apple"], "soups": ["turkey-soup", "lentil-soup"]},
    {"pots": ["turkey-stew", "salmon-rice"], "soups": ["fish-chowder", "beef-soup"]},
    {"pots": ["chicken-rice", "cod-potato"], "soups": ["pork-soup", "turkey-soup"]},
    {"pots": ["turkey-meatballs", "lentil-beef"], "soups": ["chicken-soup", "fish-chowder"]},
]

BREAKFASTS = [
    {
        "id": "eggs-yoghurt",
        "name": "Eggs and Greek yoghurt",
        "detail": (
            "3 eggs and about 250 g Greek yoghurt or skyr, plus fruit. "
            "One protein dose."
        ),
    },
    {
        "id": "skyr-oats",
        "name": "Skyr, oats and fruit",
        "detail": (
            "About 350 g skyr or Greek yoghurt, a small handful of oats, and fruit. "
            "One protein dose."
        ),
    },
]

EVENING_DAIRY = {
    "name": "Evening dairy",
    "detail": (
        "About 350 g Greek yoghurt or skyr, or enough kefir to match that protein. "
        "Milk can top the bowl up. This dose is also calcium, eaten in the evening, not extra meat."
    ),
}

STAPLES = [
    "Greek yoghurt or skyr 1 kg",
    "Semi-skimmed milk 2 L",
    "Eggs 12",
    "Oats 500 g",
    "Bananas",
    "Other fruit (apples, blueberries, pears)",
    "Lemons and limes",
    "Creatine monohydrate",
    "Onions and garlic",
    "Mild herbs (dill, parsley, oregano)",
]


def meal_by_id(meal_id: str) -> dict:
    return _BY_ID[meal_id]


def rotation_index(cycle_week: int, weekday: int) -> int:
    return (cycle_week * 7 + weekday) % len(EAT_ROTATION)


def rotation_index_for_date(d: date) -> int:
    return d.toordinal() % len(EAT_ROTATION)


def _pair(index: int) -> tuple[dict, dict]:
    soup_id, pot_id = EAT_ROTATION[index % len(EAT_ROTATION)]
    return _BY_ID[soup_id], _BY_ID[pot_id]


def chicken_serves(indexes: list[int]) -> int:
    """How many lunch-or-dinner slots in these rotation indexes use chicken."""
    n = 0
    for i in indexes:
        soup, pot = _pair(i)
        if soup["protein"] == "chicken":
            n += 1
        if pot["protein"] == "chicken":
            n += 1
    return n


def _portion(meal: dict, kind: str, slot: str) -> tuple:
    side = CARB_SIDE.get(kind, CARB_SIDE["easy"])
    carbs = _CARB_G.get(kind, 30)
    detail = f"{meal['method']} {meal['steps']} {side}"
    kcal = PROTEIN_DOSE_G * 4 + carbs * 4 + 80
    return (slot, meal["name"], detail, kcal, PROTEIN_DOSE_G, carbs)


def day_meals(index: int, kind: str) -> list[tuple]:
    """Breakfast, soup lunch, one-pot dinner, evening dairy. Protein dose each."""
    soup, pot = _pair(index)
    bf = BREAKFASTS[index % len(BREAKFASTS)]
    bf_carbs = 25 if kind == "easy" else (40 if kind == "hard" else 50)
    breakfast = (
        "Breakfast",
        bf["name"],
        bf["detail"],
        PROTEIN_DOSE_G * 4 + bf_carbs * 4 + 40,
        PROTEIN_DOSE_G,
        bf_carbs,
    )
    evening_carbs = 15
    evening = (
        "Evening",
        EVENING_DAIRY["name"],
        EVENING_DAIRY["detail"],
        PROTEIN_DOSE_G * 4 + evening_carbs * 4,
        PROTEIN_DOSE_G,
        evening_carbs,
    )
    return [
        breakfast,
        _portion(soup, kind, "Lunch"),
        _portion(pot, kind, "Dinner"),
        evening,
    ]


def dinner_tuple(cycle_week: int, weekday: int, kind: str = "easy") -> tuple:
    meals = day_meals(rotation_index(cycle_week, weekday), kind)
    return next(m for m in meals if m[0] == "Dinner")


def recipe_url(slot: str, name: str) -> str | None:
    slot_l = (slot or "").lower()
    name_l = (name or "").lower()
    if "oat" in name_l or "skyr" in name_l:
        return "/nutrition/recipes/overnight-oats"
    if slot_l == "breakfast" and "egg" in name_l:
        return "/nutrition/recipes#eggs"
    for meal in ONE_POTS + SOUPS:
        if meal["name"].lower() == name_l or meal["name"].lower() in name_l:
            page = "weekday-dinners" if meal["kind"] == "dinner" else "weekday-dinners"
            return f"/nutrition/recipes/{page}#{meal['id']}"
    if slot_l == "evening":
        return "/nutrition/recipes/weekday-dinners#evening-dairy"
    return None


def cook_plan(cycle_week: int) -> dict:
    """The two one-pots and two soups to batch this week."""
    block = COOK_WEEKS[cycle_week % len(COOK_WEEKS)]
    return {
        "pots": [_BY_ID[i] for i in block["pots"]],
        "soups": [_BY_ID[i] for i in block["soups"]],
    }


def shopping_list(cycle_week: int) -> list[dict]:
    """One merged list for this week's batches, plus everyday staples."""
    plan = cook_plan(cycle_week)
    grouped: dict[str, list[str]] = {}
    for meal in plan["pots"] + plan["soups"]:
        for line in meal["shop"]:
            grouped.setdefault(meal["name"], []).append(line)
    rows = [{"group": name, "items": items} for name, items in grouped.items()]
    rows.append({"group": "Every week", "items": list(STAPLES)})
    return rows


def banned_foods_in_library() -> list[str]:
    """Return any banned words that slipped into the library text."""
    banned = ("cheese", "spinach", "chia", "beetroot", "beet root", "rhubarb", "almond", "cashew", "peanut")
    blob = []
    for meal in ONE_POTS + SOUPS + BREAKFASTS:
        blob.append(meal.get("name", ""))
        blob.append(meal.get("detail", ""))
        blob.append(meal.get("steps", ""))
        blob.append(" ".join(meal.get("shop") or []))
    blob.append(EVENING_DAIRY["detail"])
    text = "\n".join(blob).lower()
    return [word for word in banned if word in text]

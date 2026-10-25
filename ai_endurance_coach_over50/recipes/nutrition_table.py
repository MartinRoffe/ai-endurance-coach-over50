"""Per-100 g nutrition for recipe maths.

Values are rounded from McCance & Widdowson / the UK Composition of Foods
Integrated Dataset (CoFID), raw unless the name says otherwise. Energy is
kcal per 100 g. Calcium is mg per 100 g.

High-protein yoghurt is the exception: CoFID Greek-style yoghurt is a
different product (more fat, less protein). That row is a packet-typical
plain 0% high-protein yoghurt sold in UK supermarkets, not a CoFID line.

Recipe totals are never typed in. They are summed from these rows.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Food:
    id: str
    name: str
    aisle: str
    kcal: float
    protein: float
    carbs: float
    fat: float
    calcium: float
    source: str
    liquid: bool = False


# aisle names are the shopping groups (Lidl and Asda both use these sections).
_F = Food

FOODS: dict[str, Food] = {
    f.id: f
    for f in (
        _F("milk_semi", "Semi-skimmed milk", "Dairy and eggs", 47, 3.5, 4.8, 1.8, 120, "CoFID milk, semi-skimmed", True),
        _F("yoghurt_hp", "Plain high-protein yoghurt", "Dairy and eggs", 57, 10.0, 3.8, 0.2, 140, "Packet-typical UK 0% high-protein yoghurt, not CoFID Greek-style"),
        _F("egg", "Eggs", "Dairy and eggs", 131, 12.6, 0.0, 9.0, 46, "CoFID egg, chicken, whole, raw"),
        _F("butter", "Butter", "Dairy and eggs", 744, 0.6, 0.6, 82.0, 18, "CoFID butter, salted"),
        _F("oats", "Porridge oats", "Store cupboard", 374, 11.0, 60.0, 8.0, 52, "CoFID oats, rolled"),
        _F("cornflakes", "Cornflakes", "Store cupboard", 378, 7.1, 84.0, 0.9, 13, "CoFID cornflakes, unfortified calcium"),
        _F("bread", "White bread", "Bakery", 219, 7.9, 42.7, 1.6, 177, "CoFID bread, white, sliced (calcium-fortified flour)"),
        _F("rice", "Basmati rice, dry", "Store cupboard", 351, 7.1, 79.0, 0.5, 7, "CoFID rice, white, basmati, raw"),
        _F("pasta", "Dried pasta", "Store cupboard", 353, 12.0, 71.0, 1.8, 22, "CoFID pasta, white, raw"),
        _F("couscous", "Couscous, dry", "Store cupboard", 364, 12.8, 74.0, 1.8, 20, "CoFID couscous, raw"),
        _F("potato", "Potatoes", "Fruit and veg", 77, 2.0, 17.2, 0.1, 5, "CoFID potato, old, raw"),
        _F("red_lentil", "Red lentils, dry", "Store cupboard", 329, 24.6, 56.0, 1.5, 51, "CoFID lentils, red, split, raw"),
        _F("passata", "Passata", "Store cupboard", 29, 1.4, 4.2, 0.2, 13, "CoFID tomatoes, canned, plain (passata equivalent)"),
        _F("baked_beans", "Baked beans in tomato sauce", "Store cupboard", 81, 4.8, 12.5, 0.6, 45, "CoFID beans, baked, canned in tomato sauce"),
        _F("honey", "Honey", "Store cupboard", 304, 0.4, 76.4, 0.0, 5, "CoFID honey"),
        _F("maltodextrin", "Maltodextrin", "Store cupboard", 400, 0.0, 100.0, 0.0, 0, "Typical maltodextrin powder, 4 kcal per gram"),
        _F("olive_oil", "Olive oil", "Store cupboard", 884, 0.0, 0.0, 100.0, 0, "CoFID oil, olive", True),
        # Shop plain rice cake. The day calorie card prices standard-rice-cake
        # and sweet-rice-cakes instead. The shop buys those ingredients.
        _F("rice_cake", "Plain rice cakes", "Store cupboard", 387, 8.0, 81.0, 2.8, 10, "CoFID rice cakes, plain"),
        _F("sushi_rice", "Sushi rice, dry", "Store cupboard", 352, 5.6, 85.6, 0.9, 6, "CoFID 2021 rice, white, pudding, raw (short-grain; no sushi-rice row)"),
        _F("soy_sauce", "Soy sauce", "Store cupboard", 79, 3.0, 17.9, 0.0, 17, "CoFID 2021 soy sauce, light and dark varieties", True),
        _F("sesame_oil", "Sesame oil", "Store cupboard", 898, 0.2, 0.0, 99.7, 10, "CoFID 2021 oil, sesame", True),
        _F("rice_vinegar", "Rice vinegar", "Store cupboard", 22, 0.4, 0.6, 0.0, 3, "CoFID 2021 vinegar (no separate rice-vinegar row)", True),
        _F(
            "cinnamon",
            "Ground cinnamon",
            "Store cupboard",
            247,
            4.0,
            27.5,
            1.2,
            1002,
            "USDA FDC spices, cinnamon, ground; available carbohydrate is by difference minus fibre. CoFID cinnamon has no carbohydrate value",
        ),
        _F("salt", "Salt", "Store cupboard", 0, 0.0, 0.0, 0.0, 0, "Salt has no energy; use a pinch only"),
        _F("oregano", "Dried oregano", "Store cupboard", 306, 11.0, 50.0, 10.0, 160, "CoFID oregano, dried"),
        _F("thyme", "Dried thyme", "Store cupboard", 276, 9.1, 45.0, 7.4, 189, "CoFID thyme, dried"),
        _F("chicken_breast", "Chicken breast, skinless", "Meat and fish", 106, 24.0, 0.0, 1.1, 6, "CoFID chicken, breast, raw, meat only"),
        _F("turkey_mince", "Turkey thigh mince", "Meat and fish", 148, 20.5, 0.0, 7.4, 12, "CoFID turkey, mince, raw"),
        _F("turkey_breast", "Turkey breast", "Meat and fish", 105, 24.0, 0.0, 1.0, 8, "CoFID turkey, breast, raw"),
        _F("beef_mince", "Lean beef mince (5% fat)", "Meat and fish", 137, 21.0, 0.0, 5.9, 8, "CoFID beef, mince, raw, extra lean"),
        _F("beef_steak", "Lean beef steak", "Meat and fish", 129, 23.0, 0.0, 4.0, 5, "CoFID beef, stewing steak / frying steak, raw, lean"),
        _F("pork_loin", "Pork loin", "Meat and fish", 127, 22.0, 0.0, 4.4, 7, "CoFID pork, loin, raw, lean"),
        _F("bacon", "Back bacon", "Meat and fish", 215, 16.5, 0.0, 16.5, 7, "CoFID bacon, rashers, back, raw"),
        _F("sausage", "Plain pork sausages", "Meat and fish", 267, 13.0, 9.0, 19.5, 40, "CoFID pork sausages, raw"),
        _F("cod", "Cod fillet", "Meat and fish", 80, 18.3, 0.0, 0.7, 8, "CoFID cod, flesh only, raw"),
        _F("salmon", "Salmon fillet", "Meat and fish", 182, 20.2, 0.0, 11.0, 12, "CoFID salmon, raw"),
    )
}

_MORE = (
    _F("banana", "Bananas", "Fruit and veg", 95, 1.2, 23.2, 0.3, 6, "CoFID banana, flesh only"),
    _F("apple", "Apples", "Fruit and veg", 47, 0.4, 11.8, 0.1, 4, "CoFID apples, eating, flesh and skin, raw"),
    _F("blueberry", "Blueberries", "Fruit and veg", 40, 0.7, 9.1, 0.2, 8, "CoFID blueberries"),
    _F("lemon", "Lemon juice", "Fruit and veg", 7, 0.3, 1.6, 0.0, 5, "CoFID lemon juice, fresh", True),
    _F("onion", "Onions", "Fruit and veg", 36, 1.2, 7.9, 0.2, 25, "CoFID onions, raw"),
    _F("garlic", "Garlic", "Fruit and veg", 98, 7.9, 16.3, 0.6, 19, "CoFID garlic, raw"),
    _F("leek", "Leeks", "Fruit and veg", 22, 1.6, 2.9, 0.5, 48, "CoFID leeks, raw"),
    _F("cabbage", "White cabbage", "Fruit and veg", 27, 1.4, 5.0, 0.2, 52, "CoFID cabbage, white, raw"),
    _F("carrot", "Carrots", "Fruit and veg", 35, 0.6, 7.9, 0.3, 30, "CoFID carrots, old, raw"),
    _F("courgette", "Courgettes", "Fruit and veg", 18, 1.8, 1.8, 0.4, 25, "CoFID courgette, raw"),
    _F("mushroom", "Mushrooms", "Fruit and veg", 13, 1.8, 0.4, 0.5, 7, "CoFID mushrooms, raw"),
    _F("tomato", "Tomatoes", "Fruit and veg", 18, 0.7, 3.1, 0.3, 10, "CoFID tomatoes, raw"),
    _F("broccoli", "Broccoli", "Fruit and veg", 34, 2.8, 3.2, 0.9, 47, "CoFID broccoli, raw"),
    _F("green_bean", "Green beans", "Fruit and veg", 24, 1.9, 3.2, 0.5, 36, "CoFID beans, green, raw"),
    _F("pea", "Frozen peas", "Frozen", 77, 5.7, 11.0, 0.7, 21, "CoFID peas, frozen, raw"),
    _F("pepper", "Peppers", "Fruit and veg", 31, 1.0, 6.4, 0.3, 8, "CoFID peppers, red, raw"),
    _F("swede", "Swede", "Fruit and veg", 24, 0.7, 5.0, 0.3, 53, "CoFID swede, raw"),
    _F("cucumber", "Cucumber", "Fruit and veg", 10, 0.7, 1.5, 0.1, 17, "CoFID cucumber, raw"),
    _F("lettuce", "Lettuce", "Fruit and veg", 14, 0.8, 1.8, 0.3, 28, "CoFID lettuce, average, raw"),
    _F("parsley", "Fresh parsley", "Fruit and veg", 34, 3.0, 2.7, 1.3, 200, "CoFID parsley, fresh"),
    _F("dill", "Fresh dill", "Fruit and veg", 43, 3.5, 7.0, 1.1, 208, "CoFID dill, fresh"),
    _F("black_pepper", "Black pepper", "Store cupboard", 251, 10.4, 64.8, 3.3, 443, "CoFID pepper, black"),
)
for _food in _MORE:
    FOODS[_food.id] = _food

DAIRY_IDS = frozenset({"milk_semi", "yoghurt_hp"})

AISLE_ORDER = (
    "Fruit and veg",
    "Meat and fish",
    "Dairy and eggs",
    "Bakery",
    "Frozen",
    "Store cupboard",
)


def food(food_id: str) -> Food:
    try:
        return FOODS[food_id]
    except KeyError as exc:
        raise KeyError(f"unknown food {food_id}") from exc


def macros_for(food_id: str, grams: float) -> dict[str, float]:
    """Nutrients in ``grams`` of a food. All zeros when grams is 0."""
    row = food(food_id)
    scale = float(grams) / 100.0
    calcium = row.calcium * scale
    return {
        "kcal": row.kcal * scale,
        "protein": row.protein * scale,
        "carbs": row.carbs * scale,
        "fat": row.fat * scale,
        "calcium": calcium,
        "dairy_calcium": calcium if food_id in DAIRY_IDS else 0.0,
        "grams": float(grams),
    }


def add_macros(total: dict[str, float], part: dict[str, float]) -> dict[str, float]:
    for key in ("kcal", "protein", "carbs", "fat", "calcium", "dairy_calcium", "grams"):
        total[key] = total.get(key, 0.0) + part.get(key, 0.0)
    return total


def empty_macros() -> dict[str, float]:
    return {
        "kcal": 0.0,
        "protein": 0.0,
        "carbs": 0.0,
        "fat": 0.0,
        "calcium": 0.0,
        "dairy_calcium": 0.0,
        "grams": 0.0,
    }

"""Facade over the recipe library.

Pages and search still import these names. The meals, macros, and shopping
grams come from ``recipes`` — nothing here invents a calorie total.
"""
from __future__ import annotations

from .recipes.catalog import all_recipes
from .recipes.menu import (
    BREAKFAST_RECIPES,
    cook_plan,
    shopping_list,
)
from .recipes.model import batch_grams_by_food, numbered_method, portion_macros, shop_line

# Kept so older imports do not break. The day's protein target is not this number.
PROTEIN_DOSE_G = 40

CARB_SIDE = {
    "easy": "Carb side: about a quarter plate of potato, rice or pasta.",
    "hard": "Carb side: about half a plate, plus a banana before and after training.",
    "long": "Carb side: a larger plate across the day (about 6–7 g/kg), plus 60–90 g/h on the bike.",
}


def _public_batch(recipe) -> dict:
    macros = portion_macros(recipe, 1)
    shop = [shop_line(food_id, grams) for food_id, grams in batch_grams_by_food(recipe).items()]
    return {
        "id": recipe.id,
        "name": recipe.name,
        "protein": recipe.protein,
        "kind": "soup" if recipe.slot == "soup" else "dinner",
        "method": recipe.summary,
        "shop": shop,
        "steps": numbered_method(recipe),
        "per_portion_kcal": int(round(macros["kcal"])),
        "per_portion_protein": int(round(macros["protein"])),
    }


ONE_POTS: list[dict] = [
    _public_batch(recipe) for recipe in all_recipes() if recipe.slot == "dinner" and recipe.batch
]
SOUPS: list[dict] = [
    _public_batch(recipe) for recipe in all_recipes() if recipe.slot == "soup"
]

BREAKFASTS: list[dict] = [
    {
        "id": recipe.id,
        "name": recipe.name,
        "detail": recipe.summary,
    }
    for recipe in BREAKFAST_RECIPES
]

_BY_NAME = {recipe.name.lower(): recipe for recipe in all_recipes()}


def recipe_url(slot: str, name: str) -> str | None:
    """Page anchor for a meal name, when the library has that dish."""
    recipe = _BY_NAME.get((name or "").strip().lower())
    if recipe is None:
        return None
    if recipe.id == "overnight-oats":
        return "/nutrition/recipes/overnight-oats"
    if recipe.batch:
        return f"/nutrition/recipes/weekday-dinners#{recipe.id}"
    return f"/nutrition/sunday#{recipe.id}"


def banned_foods_in_library() -> list[str]:
    """Ingredient names that the stone and preference rules forbid.

    A method line that says the dish has no cheese is not an ingredient.
    """
    banned = (
        "cheese", "parmesan", "cheddar", "feta", "halloumi", "mozzarella",
        "chilli", "chili", "cayenne", "harissa", "jalapeno", "jalapeño",
        "chorizo", "sriracha", "spicy", "offal", "liver", "kidney",
        "spinach", "chia", "almond", "cashew", "walnut", "peanut",
        "beetroot", "rhubarb",
    )
    found: list[str] = []
    for recipe in all_recipes():
        blob = " ".join(
            [recipe.name, recipe.summary, recipe.protein]
            + [item.food_id.replace("_", " ") for item in recipe.ingredients]
            + [item.food_id.replace("_", " ") for item in recipe.serve_with]
        ).lower()
        blob = blob.replace("no cheese", "").replace("without cheese", "")
        for word in banned:
            if word in blob:
                found.append(f"{recipe.id}: {word}")
    return found


__all__ = [
    "BREAKFASTS",
    "CARB_SIDE",
    "ONE_POTS",
    "PROTEIN_DOSE_G",
    "SOUPS",
    "banned_foods_in_library",
    "cook_plan",
    "recipe_url",
    "shopping_list",
]

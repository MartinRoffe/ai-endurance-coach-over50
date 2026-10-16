"""Recipe records and macro maths. Totals come from the ingredient table."""
from __future__ import annotations

from dataclasses import dataclass

from .nutrition_table import add_macros, empty_macros, food, macros_for

# Carbohydrate weighed on its own, so a plate can grow or shrink without a second starch.
STARCH_IDS = frozenset({"rice", "pasta", "couscous", "potato", "bread"})


@dataclass(frozen=True)
class Ingredient:
    food_id: str
    grams: float

    def __post_init__(self) -> None:
        if self.grams <= 0:
            raise ValueError(f"{self.food_id} needs a positive gram weight")
        food(self.food_id)


@dataclass(frozen=True)
class Recipe:
    id: str
    name: str
    slot: str
    servings: int
    ingredients: tuple[Ingredient, ...]
    method: tuple[str, ...]
    equipment: tuple[str, ...]
    fridge: str
    freezer: str
    protein: str
    summary: str
    serve_with: tuple[Ingredient, ...] = ()
    batch: bool = False

    def __post_init__(self) -> None:
        if self.servings < 1:
            raise ValueError(f"{self.id} needs at least one serving")
        if not self.method:
            raise ValueError(f"{self.id} needs a method")
        if not self.ingredients:
            raise ValueError(f"{self.id} needs ingredients")
        if not self.equipment:
            raise ValueError(f"{self.id} needs equipment")


def _sum_items(items: tuple[Ingredient, ...], scale: float) -> dict[str, float]:
    total = empty_macros()
    for item in items:
        add_macros(total, macros_for(item.food_id, item.grams * scale))
    return total


def portion_macros(
    recipe: Recipe,
    multiplier: float = 1.0,
    *,
    side_multiplier: float | None = None,
    extra_bread_g: float = 0.0,
) -> dict[str, float]:
    """Nutrients in one eaten portion.

    ``multiplier`` scales meat, vegetables, and sauce. ``side_multiplier`` scales
    rice, pasta, potato, couscous, and bread, including a slice served beside a soup.
    Extra bread is only for plates with no starch of their own.
    """
    if multiplier <= 0:
        raise ValueError("multiplier must be positive")
    if side_multiplier is None:
        side_multiplier = multiplier
    if side_multiplier < 0:
        raise ValueError("side_multiplier cannot be negative")
    total = empty_macros()
    for item in recipe.ingredients:
        scale = side_multiplier if item.food_id in STARCH_IDS else multiplier
        add_macros(total, macros_for(item.food_id, item.grams * scale / recipe.servings))
    add_macros(total, _sum_items(recipe.serve_with, side_multiplier))
    if extra_bread_g > 0:
        add_macros(total, macros_for("bread", extra_bread_g))
    return total


def portion_grams_by_food(
    recipe: Recipe,
    multiplier: float = 1.0,
    *,
    side_multiplier: float | None = None,
    extra_bread_g: float = 0.0,
) -> dict[str, float]:
    if side_multiplier is None:
        side_multiplier = multiplier
    out: dict[str, float] = {}
    for item in recipe.ingredients:
        scale = side_multiplier if item.food_id in STARCH_IDS else multiplier
        grams = item.grams * scale / recipe.servings
        if grams <= 0:
            continue
        out[item.food_id] = out.get(item.food_id, 0.0) + grams
    for item in recipe.serve_with:
        grams = item.grams * side_multiplier
        if grams <= 0:
            continue
        out[item.food_id] = out.get(item.food_id, 0.0) + grams
    if extra_bread_g > 0:
        out["bread"] = out.get("bread", 0.0) + extra_bread_g
    return out


def batch_grams_by_food(recipe: Recipe) -> dict[str, float]:
    """Raw grams for the whole cooked batch. Bread served on the side is not included."""
    out: dict[str, float] = {}
    for item in recipe.ingredients:
        out[item.food_id] = out.get(item.food_id, 0.0) + item.grams
    return out


def numbered_method(recipe: Recipe) -> str:
    return " ".join(f"{i}. {step}" for i, step in enumerate(recipe.method, start=1))


def shop_line(food_id: str, grams: float) -> str:
    row = food(food_id)
    amount = int(round(grams))
    unit = "ml" if row.liquid else "g"
    return f"{row.name} — {amount} {unit}"

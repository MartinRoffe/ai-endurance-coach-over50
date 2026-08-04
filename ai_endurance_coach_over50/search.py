"""Global app search: keyword index over pages, Help, plan, nutrition, live data."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path


# ── Result shape ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SearchHit:
    id: str
    type: str  # page | help | plan | nutrition | shopping | activity | memory | alias
    title: str
    subtitle: str
    url: str
    score: float = 0.0
    haystack: str = ""  # lowercased match text (built at index time)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "subtitle": self.subtitle,
            "url": self.url,
            "score": round(self.score, 3),
        }


_TYPE_BOOST = {
    "page": 12.0,
    "alias": 11.0,
    "help": 9.0,
    "nutrition": 8.0,
    "plan": 7.0,
    "memory": 6.0,
    "activity": 5.0,
    "shopping": 2.0,
}

_HINTS: list[dict] = [
    {"id": "hint-today", "type": "page", "title": "Today", "subtitle": "Readiness dashboard", "url": "/", "score": 0},
    {"id": "hint-coach", "type": "page", "title": "Coach", "subtitle": "AI coach chat", "url": "/coach", "score": 0},
    {"id": "hint-calendar", "type": "page", "title": "Plan", "subtitle": "Training calendar", "url": "/calendar", "score": 0},
    {"id": "hint-nutrition", "type": "page", "title": "Nutrition", "subtitle": "Eat today", "url": "/nutrition", "score": 0},
    {"id": "hint-faq", "type": "help", "title": "FAQ", "subtitle": "Help & troubleshooting", "url": "/help/faq", "score": 0},
]


def _fold(s: str) -> str:
    """Lowercase + strip accents so 'ragu' matches 'ragù'."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", _fold(s)).strip()


def _entry(
    *,
    id: str,
    type: str,
    title: str,
    subtitle: str,
    url: str,
    extra: str = "",
) -> SearchHit:
    hay = _norm(f"{title} {subtitle} {extra}")
    return SearchHit(id=id, type=type, title=title, subtitle=subtitle, url=url, haystack=hay)


# ── Static builders ───────────────────────────────────────────────────────────

def _pages() -> list[SearchHit]:
    rows = [
        ("/", "Today", "Readiness dashboard"),
        ("/performance", "Performance", "PMC, TSS, power, durability"),
        ("/analysis", "Analysis", "Post-workout coach analyses"),
        ("/calendar", "Plan", "Training calendar & sessions"),
        ("/training", "Training Guide", "How the plan works"),
        ("/compliance", "Compliance", "Plan adherence"),
        ("/sleep", "Sleep", "Sleep quality history"),
        ("/body", "Body", "Composition, BP, W/kg, fluid"),
        ("/coach", "Coach", "AI coach chat"),
        ("/memory", "Memory", "Coach long-term memo"),
        ("/tenerife", "Tenerife", "Camp itinerary & nutrition"),
        ("/haute-route", "Haute Route", "46-week Alpes 2027 plan"),
        ("/haute-route/2012-postmortem", "2012 Post-mortem", "Haute Route failure analysis"),
        ("/haute-route/power-protocol", "Power Protocol", "FTP test & power meter setup"),
        ("/architecture", "Architecture", "System diagram"),
        ("/help", "Help", "In-app user guide"),
        ("/nutrition", "Nutrition — Today", "Eat today checklist"),
        ("/nutrition/sunday", "Sunday Prep", "Batch cook schedule"),
        ("/nutrition/lidl-shopping-list", "Lidl Shopping List", "Weekly shop"),
        ("/nutrition/shopping-list", "Asda Shopping List", "Click-to-add weekly shop"),
        ("/nutrition/fuelling", "Ride Fuelling", "Rice cakes, carbs/h, electrolytes"),
        ("/nutrition/meals", "This Week Menus", "Daily meal menus"),
        ("/nutrition/recipes", "Cook Once · Week", "Batch recipes hub"),
        ("/nutrition/recipes/overnight-oats", "Overnight Oats", "High-protein jars"),
        ("/nutrition/recipes/weekend-fuel", "Weekend Ride Fuel", "Rice cakes & on-bike fuel"),
        ("/nutrition/recipes/griddle", "Blackstone Griddle", "Fri–Sun griddle recipes"),
        ("/nutrition/recipes/weekday-dinners", "Weekday Batch Dinners", "Sunday A/B dinners"),
        ("/nutrition/recipes/travel", "Weekend Away", "Travel food checklist"),
    ]
    return [
        _entry(id=f"page-{url}", type="page", title=title, subtitle=sub, url=url)
        for url, title, sub in rows
    ]


def _help_docs_mod():
    """Load help_docs.py without importing server/__init__.py (avoids circular import)."""
    import importlib.util
    import sys

    name = "_aeco50_help_docs"
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().parent / "server" / "help_docs.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("help_docs.py not found")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _help() -> list[SearchHit]:
    hd = _help_docs_mod()
    HELP_PAGES = hd.HELP_PAGES
    HELP_TITLES = hd.HELP_TITLES
    docs_root = hd.docs_root

    out: list[SearchHit] = []
    root = docs_root()
    for page_id, rel in HELP_PAGES.items():
        title = HELP_TITLES.get(page_id, page_id)
        body = ""
        path = root / rel
        if path.is_file():
            try:
                body = path.read_text(encoding="utf-8")[:4000]
            except OSError:
                body = ""
        # Strip markdown noise for matching
        body_plain = re.sub(r"[#>*`\[\]]+", " ", body)
        out.append(
            _entry(
                id=f"help-{page_id}",
                type="help",
                title=title,
                subtitle="Help",
                url=f"/help/{page_id}",
                extra=body_plain,
            )
        )
    # Nutrition help section aliases
    for frag, label in (
        ("today", "Nutrition — Today"),
        ("calorie-targets-burn-vs-target-vs-logged", "Calorie targets"),
        ("this-week-meals", "This week meals"),
        ("sunday-prep", "Sunday Prep (Help)"),
        ("fuelling", "Fuelling (Help)"),
        ("recipes-legacy-deep-links", "Recipes (Help)"),
        ("shopping", "Shopping (Help)"),
        ("garmin-integration", "Garmin nutrition integration"),
    ):
        out.append(
            _entry(
                id=f"help-nutrition-{frag}",
                type="help",
                title=label,
                subtitle="Help · Nutrition",
                url=f"/help/nutrition#{frag}",
                extra="nutrition",
            )
        )
    return out


def _plan() -> list[SearchHit]:
    from .plan import (
        CAMP_GRID_WORKOUTS,
        CHARITY_DAYS,
        EVENT_PREP_DAYS,
        PLAN_START,
        TRAINING_WEEKS,
    )
    from .hr_plan import HR_EVENT_STAGES, HR_PLAN_START, HR_TRAINING_WEEKS
    from .analysis.prefetch import _load_workout_descs

    out: list[SearchHit] = []
    seen: set[str] = set()

    def add_session(label: str, d: date, *, hr: bool = False, extra: str = "") -> None:
        key = f"{'hr' if hr else 'cal'}:{label}:{d.isoformat()}"
        if key in seen:
            return
        seen.add(key)
        # One hit per label (first occurrence) — keep label-level id for dedupe in match
        label_key = f"{'hr' if hr else 'plan'}-label-{_norm(label)}"
        if label_key in seen:
            return
        seen.add(label_key)
        base = "/haute-route" if hr else "/calendar"
        out.append(
            _entry(
                id=label_key,
                type="plan",
                title=label,
                subtitle=f"{'Haute Route' if hr else 'Plan'} · {d.strftime('%d %b %Y').lstrip('0')}",
                url=f"{base}?date={d.isoformat()}",
                extra=extra,
            )
        )

    for wk_idx, sessions in enumerate(TRAINING_WEEKS):
        wk_start = PLAN_START + timedelta(weeks=wk_idx)
        for day_idx, (stype, label, _dur) in enumerate(sessions):
            if stype == "rest" or not label:
                continue
            add_session(label, wk_start + timedelta(days=day_idx))

    for d, info in CAMP_GRID_WORKOUTS.items():
        add_session(info["label"], d, extra="camp")

    for ep in EVENT_PREP_DAYS:
        add_session(ep["label"], ep["date"], extra="event prep")

    for cd in CHARITY_DAYS:
        add_session(
            cd["label"],
            cd["date"],
            extra=f"charity {cd.get('km', '')} km",
        )

    for wk_idx, sessions in enumerate(HR_TRAINING_WEEKS):
        wk_start = HR_PLAN_START + timedelta(weeks=wk_idx)
        for day_idx, (stype, label, _dur) in enumerate(sessions):
            if stype == "rest" or not label:
                continue
            add_session(label, wk_start + timedelta(days=day_idx), hr=True)

    for st in HR_EVENT_STAGES:
        add_session(
            st["label"],
            st["date"],
            hr=True,
            extra=f"{st.get('key_climb', '')} stage {st.get('day', '')}",
        )
        if st.get("key_climb"):
            out.append(
                _entry(
                    id=f"hr-climb-{st['day']}",
                    type="plan",
                    title=st["key_climb"],
                    subtitle=f"Haute Route stage {st['day']} · {st['label']}",
                    url=f"/haute-route?date={st['date'].isoformat()}",
                    extra=st["label"],
                )
            )

    try:
        for label, desc in _load_workout_descs().items():
            if not label:
                continue
            lid = f"wdesc-{_norm(label)}"
            if lid in seen:
                # Enrich existing subtitle isn't possible on frozen hits; add separate desc hit
                pass
            out.append(
                _entry(
                    id=lid,
                    type="plan",
                    title=label,
                    subtitle=(desc or "")[:120],
                    url="/calendar",
                    extra=desc or "",
                )
            )
    except Exception:
        pass

    return out


_RECIPE_ANCHORS: list[tuple[str, str, str, str]] = [
    # url, anchor, title, subtitle
    ("/nutrition/recipes", "chicken", "Batch-Roasted Chicken Thighs", "Cook once"),
    ("/nutrition/recipes", "chinese-chicken", "Soy-Glazed Chinese Thighs", "Wednesday lunch"),
    ("/nutrition/recipes", "rice", "Big-Batch Basmati", "Cook once"),
    ("/nutrition/recipes", "oatbars", "Protein Oat Bars / Flapjacks", "Cook once"),
    ("/nutrition/recipes", "yogurt", "Greek-Yogurt Pots", "Cook once"),
    ("/nutrition/recipes", "overnight-oats", "High-Protein Overnight Oats", "Cook once"),
    ("/nutrition/recipes", "egg-muffins", "Egg & Veg Muffins", "Recovery breakfast"),
    ("/nutrition/recipes", "scotch-eggs", "Baked Scotch Eggs", "Tue/Thu breakfast"),
    ("/nutrition/recipes", "porridge", "Hot Porridge", "Post-ruck"),
    ("/nutrition/recipes", "recovery", "Big Recovery Porridge", "Post-ride"),
    ("/nutrition/recipes", "chickenrice", "Chicken & Rice Bowl", "Lunch"),
    ("/nutrition/recipes", "chinese-lunch", "Chinese Chicken + Egg Fried Rice", "Wednesday lunch"),
    ("/nutrition/recipes", "tunapasta", "Tuna Pasta", "Optional lunch"),
    ("/nutrition/recipes", "paella", "Friday Paella Pouch + Prawns", "Friday lunch"),
    ("/nutrition/recipes", "sunday-prep", "Sunday Breakfast Prep", "Prep"),
    ("/nutrition/recipes", "storage", "Fridge Life & Storage", "Prep"),
    ("/nutrition/recipes/overnight-oats", "base", "Overnight Oats — Shared Protein Base", "Oats"),
    ("/nutrition/recipes/overnight-oats", "weekday", "Three Jars, Three Flavours", "Oats rotation"),
    ("/nutrition/recipes/overnight-oats", "efpro", "EF Pro Cycling Athlete Oats", "Oats flavour"),
    ("/nutrition/recipes/overnight-oats", "strawberries", "Strawberries 'n' Cream Oats", "Oats flavour"),
    ("/nutrition/recipes/overnight-oats", "classic", "Cycling Labs Classic Oats", "Oats flavour"),
    ("/nutrition/recipes/overnight-oats", "banoffee-quick", "Quick Banoffee Oats", "Oats flavour"),
    ("/nutrition/recipes/overnight-oats", "banoffee-gcn", "GCN Banoffee Pie Overnight Oats", "Oats flavour"),
    ("/nutrition/recipes/overnight-oats", "berry-default", "Mixed Berry Pot (Default)", "Oats flavour"),
    ("/nutrition/recipes/weekend-fuel", "standard", "Bacon & Egg Rice Cakes", "Weekend fuel"),
    ("/nutrition/recipes/weekend-fuel", "rice-cakes", "Rice Cake Variations", "Weekend fuel"),
    ("/nutrition/recipes/weekend-fuel", "flapjack", "Classic Ride Flapjack", "Weekend fuel"),
    ("/nutrition/recipes/weekend-fuel", "fuel", "On-Bike & During-Exercise Fuel", "Drinks & solids"),
    ("/nutrition/recipes/griddle", "griddle-primer", "Griddle Primer", "Blackstone"),
    ("/nutrition/recipes/griddle", "r1", "Griddle Full English", "Blackstone"),
    ("/nutrition/recipes/griddle", "r2", "American Pancakes & Crispy Bacon", "Blackstone"),
    ("/nutrition/recipes/griddle", "r3", "Double Smash Burgers", "Blackstone"),
    ("/nutrition/recipes/griddle", "r4", "Chicken & Pepper Fajitas", "Friday griddle"),
    ("/nutrition/recipes/griddle", "r5", "Chicken & Chorizo Paella", "Saturday pre-ride"),
    ("/nutrition/recipes/griddle", "r6", "Chinese-Style Beef Stir Fry", "Sunday recovery"),
    ("/nutrition/recipes/weekday-dinners", "batch-primer", "Batch Logic", "Weekday dinners"),
    ("/nutrition/recipes/weekday-dinners", "boosters", "Easy Protein Boosters", "Weekday dinners"),
    ("/nutrition/recipes/weekday-dinners", "safety", "Reheat & Food Safety", "Weekday dinners"),
    ("/nutrition/fuelling", "calculator", "How many rice cakes?", "Fuelling"),
    ("/nutrition/fuelling", "targets", "Fuelling core targets", "60–90 g/h"),
    ("/nutrition/fuelling", "homemade", "Drinks & solid fuel", "Electrolytes"),
    ("/nutrition/fuelling", "postride", "Immediate post-ride", "Recovery"),
    ("/nutrition/fuelling", "weekend", "Weekend long rides", "Fuelling"),
    ("/nutrition/sunday", "cook-list", "Sunday cook list", "Sunday Prep"),
    ("/nutrition/sunday", "schedule", "Sunday schedule", "Sunday Prep"),
    ("/nutrition/sunday", "components", "Sunday components", "Batch chicken, basmati, oats"),
    ("/nutrition/sunday", "dinners", "Dinner methods", "Sunday Prep"),
]

_WEEKDAY_DINNER_ANCHORS = {
    # (cycle_week, weekday) -> HTML id
    **{(cw, wd): f"w{cw + 1}-{day}"
       for cw in range(4)
       for wd, day in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun"))}
}


def _nutrition() -> list[SearchHit]:
    from .nutrition_plan import (
        BREAKFASTS,
        CALORIE_TIERS,
        CAMP_NUTRITION_WINDOWS,
        DAY_TYPES,
        EVENING_DINNERS,
        SUPPLEMENTS,
    )

    out: list[SearchHit] = []

    for key, tier in CALORIE_TIERS.items():
        out.append(
            _entry(
                id=f"tier-{key}",
                type="nutrition",
                title=tier["label"],
                subtitle=f"Calorie tier · ~{tier['kcal']} kcal",
                url="/nutrition",
                extra=str(tier.get("note", "")),
            )
        )

    for dtype, data in DAY_TYPES.items():
        out.append(
            _entry(
                id=f"daytype-{dtype}",
                type="nutrition",
                title=data["label"],
                subtitle="Daily menu archetype",
                url="/nutrition/meals",
                extra=data.get("protein_note", ""),
            )
        )
        for meal in data.get("meals") or []:
            slot, name, detail = meal[0], meal[1], meal[2]
            out.append(
                _entry(
                    id=f"meal-{dtype}-{_norm(name)[:40]}",
                    type="nutrition",
                    title=name,
                    subtitle=f"{data['label']} · {slot}",
                    url="/nutrition/meals",
                    extra=detail,
                )
            )

    _bf_urls = {
        "mwf": "/nutrition/recipes/overnight-oats",
        "scotch_tuth": "/nutrition/recipes#scotch-eggs",
        "muffin_tuth": "/nutrition/recipes#egg-muffins",
    }
    for key, (name, detail, *_rest) in BREAKFASTS.items():
        out.append(
            _entry(
                id=f"bf-{key}",
                type="nutrition",
                title=name,
                subtitle="Breakfast",
                url=_bf_urls.get(key, "/nutrition/recipes"),
                extra=detail,
            )
        )

    _day_labels = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    for cw, nights in EVENING_DINNERS.items():
        for wd, (name, detail, *_rest) in nights.items():
            anchor = _WEEKDAY_DINNER_ANCHORS[(cw, wd)]
            out.append(
                _entry(
                    id=f"dinner-{anchor}",
                    type="nutrition",
                    title=name,
                    subtitle=f"Evening plate · Week {cw + 1} {_day_labels[wd]}",
                    url=f"/nutrition/recipes/weekday-dinners#{anchor}",
                    extra=detail,
                )
            )
            out.append(
                _entry(
                    id=f"sunday-{anchor}",
                    type="nutrition",
                    title=f"{name} (Sunday Prep)",
                    subtitle=f"Sunday prep · Week {cw + 1} {_day_labels[wd]}",
                    url=f"/nutrition/sunday#{anchor}",
                    extra=detail,
                )
            )

    out.append(
        _entry(
            id="nutrition-protein-dessert",
            type="nutrition",
            title="Protein dessert (skyr / 0% Greek yogurt)",
            subtitle="Evening plate closer",
            url="/nutrition/recipes/weekday-dinners#boosters",
            extra="150 g skyr protein dessert boosters",
        )
    )

    for url, anchor, title, sub in _RECIPE_ANCHORS:
        out.append(
            _entry(
                id=f"recipe-{anchor}-{url.count('/')}",
                type="nutrition",
                title=title,
                subtitle=sub,
                url=f"{url}#{anchor}",
            )
        )

    for name, dose, detail in SUPPLEMENTS:
        out.append(
            _entry(
                id=f"supp-{_norm(name)[:30]}",
                type="nutrition",
                title=name,
                subtitle=f"Supplement · {dose}",
                url="/nutrition",
                extra=detail,
            )
        )

    for start, end, label in CAMP_NUTRITION_WINDOWS:
        out.append(
            _entry(
                id=f"camp-nut-{start.isoformat()}",
                type="nutrition",
                title=label,
                subtitle=f"Camp nutrition · {start.isoformat()} → {end.isoformat()}",
                url="/tenerife",
                extra="3200 3800 kcal carbs protein fuelling",
            )
        )

    for label in (
        "Carb-Loading Breakfast",
        "Continuous Fuelling",
        "Mid-Ride Café",
        "Recovery Meal — Golden Window",
        "Main Recovery Meal",
        "Bridge Snack",
        "Replenishment Dinner",
        "Casein Protein Hit",
    ):
        out.append(
            _entry(
                id=f"camp-meal-{_norm(label)[:40]}",
                type="nutrition",
                title=label,
                subtitle="Camp hard-day template",
                url="/tenerife",
                extra="tenerife camp nutrition",
            )
        )

    for label, url in (
        ("Travel — pack from home", "/nutrition/recipes/travel"),
        ("Travel — buy on arrival", "/nutrition/recipes/travel"),
        ("Travel — gear & containers", "/nutrition/recipes/travel"),
        ("Gut training 60 g/h", "/nutrition/fuelling#targets"),
        ("Gut training 75 g/h", "/nutrition/fuelling#targets"),
        ("Gut training 90 g/h", "/nutrition/fuelling#targets"),
        ("Electrolyte bottle E1", "/nutrition/fuelling#homemade"),
        ("Electrolyte bottle E2", "/nutrition/fuelling#homemade"),
        ("Maltodextrin fructose carb drink", "/nutrition/recipes/weekend-fuel#fuel"),
        ("Recovery chocolate milk", "/nutrition/fuelling#postride"),
    ):
        out.append(
            _entry(
                id=f"nut-extra-{_norm(label)[:40]}",
                type="nutrition",
                title=label,
                subtitle="Nutrition",
                url=url,
            )
        )

    # Shopping categories
    for cat, label in (
        ("breakfast", "Shopping · Breakfast"),
        ("lunch", "Shopping · Lunch"),
        ("dinner", "Shopping · Weekday dinners"),
        ("ride", "Shopping · Weekend ride"),
        ("griddle", "Shopping · Griddle"),
        ("staples", "Shopping · Shared staples"),
    ):
        out.append(
            _entry(
                id=f"shop-cat-{cat}",
                type="shopping",
                title=label,
                subtitle="Filter",
                url=f"/nutrition/lidl-shopping-list?cat={cat}",
                extra=cat,
            )
        )

    for cw in range(4):
        out.append(
            _entry(
                id=f"shop-week-{cw}",
                type="shopping",
                title=f"Shopping · Cycle week {cw + 1}",
                subtitle="Week filter",
                url=f"/nutrition/lidl-shopping-list?week={cw}",
            )
        )

    out.extend(_shopping_items())
    return out


def _shopping_items() -> list[SearchHit]:
    path = Path(__file__).resolve().parent / "templates" / "shopping_list_data.html"
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[SearchHit] = []
    seen: set[str] = set()
    for m in re.finditer(r'name:"((?:\\.|[^"\\])*)"', text):
        name = m.group(1).replace('\\"', '"')
        key = _norm(name)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(
            _entry(
                id=f"shop-item-{key[:50]}",
                type="shopping",
                title=name,
                subtitle="Shopping list item",
                url="/nutrition/lidl-shopping-list",
                extra="asda lidl groceries",
            )
        )
    return out


def _aliases() -> list[SearchHit]:
    pairs: list[tuple[str, str, str, str]] = [
        ("HRV", "Heart-rate variability readiness", "/", "readiness traffic light"),
        ("readiness", "Today readiness", "/", "composite score"),
        ("CTL", "Chronic Training Load", "/performance", "PMC fitness"),
        ("ATL", "Acute Training Load", "/performance", "PMC fatigue"),
        ("TSB", "Training Stress Balance", "/performance", "form"),
        ("PMC", "Performance Management Chart", "/performance", "CTL ATL TSB"),
        ("TSS", "Training Stress Score", "/performance", "power load"),
        ("FTP", "Functional Threshold Power", "/performance", "watts test"),
        ("FTP test", "FTP / ramp test", "/haute-route/power-protocol", "power protocol"),
        ("W/kg", "Watts per kilo", "/body", "measured estimated"),
        ("fuelling", "Ride fuelling", "/nutrition/fuelling", "carbs rice cakes"),
        ("carbs", "Carbohydrate fuelling", "/nutrition/fuelling", "g/h"),
        ("body water", "Scale body water vs fluid intake", "/body", "hydration TBW"),
        ("fluid intake", "Logged fluid intake", "/body", "water ml garmin"),
        ("monotony", "Foster monotony / strain", "/performance", "training variety"),
        ("interference", "Strength before quality bike", "/calendar", "calendar warning"),
        ("BTB", "Back-to-back rides", "/calendar", "fatigue"),
        ("RPE", "Session RPE", "/analysis", "perceived effort"),
        ("TDEE", "Total daily energy expenditure", "/nutrition", "calorie target"),
        ("protein floor", "Daily protein target", "/nutrition", "macros"),
        ("creatine", "Creatine supplement", "/nutrition", "supplements"),
        ("Lidl", "Lidl shopping list", "/nutrition/lidl-shopping-list", ""),
        ("Asda", "Asda shopping list", "/nutrition/shopping-list", ""),
        ("Blackstone", "Griddle recipes", "/nutrition/recipes/griddle", ""),
        ("rice cakes", "Bacon & egg rice cakes", "/nutrition/recipes/weekend-fuel#standard", ""),
        ("Haute Route", "Haute Route Alpes plan", "/haute-route", ""),
        ("Tenerife", "Tenerife camp", "/tenerife", ""),
        ("architecture", "System architecture", "/help/architecture", ""),
    ]
    return [
        _entry(
            id=f"alias-{_norm(term)}",
            type="alias",
            title=term,
            subtitle=label,
            url=url,
            extra=extra,
        )
        for term, label, url, extra in pairs
    ]


@lru_cache(maxsize=1)
def _static_index() -> tuple[SearchHit, ...]:
    hits: list[SearchHit] = []
    hits.extend(_pages())
    hits.extend(_help())
    hits.extend(_plan())
    hits.extend(_nutrition())
    hits.extend(_aliases())
    return tuple(hits)


def clear_search_cache() -> None:
    _static_index.cache_clear()


# ── Scoring / live ────────────────────────────────────────────────────────────

def _score_hit(hit: SearchHit, q: str) -> float:
    hay = hit.haystack
    title_l = _norm(hit.title)
    if not q:
        return 0.0
    score = _TYPE_BOOST.get(hit.type, 1.0)
    if title_l == q:
        score += 100
    elif title_l.startswith(q):
        score += 60
    elif f" {q}" in f" {title_l}":
        score += 40
    elif q in title_l:
        score += 25
    elif hay.startswith(q) or f" {q}" in f" {hay}":
        score += 15
    elif q in hay:
        score += 8
    else:
        # Multi-token: all tokens must appear
        tokens = [t for t in q.split() if t]
        if len(tokens) > 1 and all(t in hay for t in tokens):
            score += 12
        else:
            return 0.0
    return score


def _live(q: str, limit: int = 15) -> list[SearchHit]:
    out: list[SearchHit] = []
    try:
        from .history import get_coach_memory, load_recent_activities
        from .history.db import _conn
        from .analysis.db import _ensure_analysis_schema
    except Exception:
        return out

    try:
        memo = get_coach_memory()
        if memo and memo.get("memo") and q in _norm(memo["memo"]):
            snippet = memo["memo"].strip().replace("\n", " ")
            out.append(
                SearchHit(
                    id="memory-memo",
                    type="memory",
                    title="Coach memory",
                    subtitle=snippet[:140],
                    url="/memory",
                    score=_TYPE_BOOST["memory"] + 20,
                    haystack=_norm(snippet),
                )
            )
    except Exception:
        pass

    try:
        for a in load_recent_activities(90):
            name = a.get("name") or ""
            type_key = a.get("type_key") or ""
            d = a.get("date") or ""
            aid = a.get("activity_id")
            if aid is None:
                continue
            hay = _norm(f"{name} {type_key} {d}")
            if q not in hay and not all(t in hay for t in q.split()):
                continue
            title = name or type_key or f"Activity {aid}"
            out.append(
                SearchHit(
                    id=f"act-{aid}",
                    type="activity",
                    title=title,
                    subtitle=f"{d} · {type_key}",
                    url=f"/analysis#card-{aid}",
                    score=_TYPE_BOOST["activity"] + (10 if q in _norm(name) else 3),
                    haystack=hay,
                )
            )
    except Exception:
        pass

    # Analysis text substring (lightweight)
    try:
        with _conn() as con:
            _ensure_analysis_schema(con)
            rows = con.execute(
                """
                SELECT a.activity_id, a.name, a.date, a.type_key, an.analysis_text
                FROM activity_analyses an
                JOIN activities a ON a.activity_id = an.activity_id
                WHERE an.analysis_text IS NOT NULL AND an.analysis_text != ''
                ORDER BY a.date DESC
                LIMIT 80
                """
            ).fetchall()
        for r in rows:
            text = r["analysis_text"] or ""
            hay = _norm(f"{r['name']} {text}")
            if q not in hay:
                continue
            # Snippet around first match
            low = text.lower()
            idx = low.find(q)
            if idx < 0:
                idx = 0
            start = max(0, idx - 40)
            snippet = text[start : start + 120].replace("\n", " ").strip()
            if start > 0:
                snippet = "…" + snippet
            out.append(
                SearchHit(
                    id=f"analysis-{r['activity_id']}",
                    type="activity",
                    title=r["name"] or f"Analysis {r['activity_id']}",
                    subtitle=snippet,
                    url=f"/analysis#card-{r['activity_id']}",
                    score=_TYPE_BOOST["activity"] + 6,
                    haystack=hay,
                )
            )
    except Exception:
        pass

    out.sort(key=lambda h: (-h.score, h.title.lower()))
    return out[:limit]


def search(q: str, limit: int = 25) -> list[dict]:
    """Return ranked search hits for query *q*."""
    q = _norm(q)
    if not q:
        return list(_HINTS)[:limit]

    scored: list[SearchHit] = []
    for hit in _static_index():
        s = _score_hit(hit, q)
        if s <= 0:
            continue
        scored.append(
            SearchHit(
                id=hit.id,
                type=hit.type,
                title=hit.title,
                subtitle=hit.subtitle,
                url=hit.url,
                score=s,
                haystack=hit.haystack,
            )
        )

    scored.extend(_live(q, limit=max(8, limit // 2)))

    # Dedupe by url+title
    seen: set[str] = set()
    unique: list[SearchHit] = []
    for h in sorted(scored, key=lambda x: (-x.score, x.title.lower())):
        key = f"{h.url}|{h.title}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(h)
        if len(unique) >= limit:
            break

    return [h.as_dict() for h in unique]

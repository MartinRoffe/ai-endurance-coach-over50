"""The single nutrition page, redirects, and the email meal lines."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_endurance_coach_over50.nutrition_plan import build_today_food
from ai_endurance_coach_over50.nutrition_view import meal_share_line
from ai_endurance_coach_over50.plan import PLAN_START
from ai_endurance_coach_over50.report import _daily_food_html
from ai_endurance_coach_over50.server import app

_ROOT = Path(__file__).resolve().parents[1] / "ai_endurance_coach_over50" / "templates"
_SERVED = (
    "nutrition.html",
    "nutrition_subnav.html",
    "fuelling.html",
    "cut.html",
    "recipes-index.html",
    "recipes-travel.html",
    "travel_checklist_data.html",
    "travel_checklist_render.html",
    "nav.html",
)
_BANNED = re.compile(
    r"\b("
    r"cheese|parmesan|cheddar|feta|halloumi|mozzarella|"
    r"chilli|chili|cayenne|harissa|jalapeno|jalapeño|chorizo|sriracha|spicy|"
    r"offal|liver|kidneys?|spinach|chia|almonds?|cashews?|walnuts?|"
    r"peanuts?|peanut butter|beetroot|rhubarb"
    r")\b",
    re.IGNORECASE,
)
_SAFE = (
    (re.compile(r"\bno\s+cheese\b", re.I), ""),
    (re.compile(r"\bwithout\s+cheese\b", re.I), ""),
    (re.compile(r"\bkidney return\b", re.I), ""),
    (re.compile(r"\bkidney stone[s]?\b", re.I), ""),
    (re.compile(r"\bkidney function\b", re.I), ""),
)


def _clean(text: str) -> str:
    # The stone line names foods to skip. It is an instruction, not a plate.
    text = re.sub(r'<p class="stone-line">.*?</p>', "", text, flags=re.S)
    for pattern, repl in _SAFE:
        text = pattern.sub(repl, text)
    return text


def test_served_templates_have_no_banned_foods():
    problems = []
    for name in _SERVED:
        path = _ROOT / name
        assert path.is_file(), name
        found = _BANNED.findall(_clean(path.read_text(encoding="utf-8")))
        if found:
            problems.append(f"{name}: {found}")
    assert problems == []


@pytest.fixture
def client():
    return TestClient(app)


def test_old_nutrition_urls_redirect(client):
    redirects = {
        "/nutrition/meals": "/nutrition#week",
        "/nutrition/sunday": "/nutrition#batch",
        "/nutrition/shopping-list": "/nutrition#shop",
        "/nutrition/lidl-shopping-list": "/nutrition#shop",
        "/nutrition/recipes/overnight-oats": "/nutrition/recipes#overnight-oats",
        "/nutrition/recipes/weekend-fuel": "/nutrition/recipes#standard-rice-cake",
        "/nutrition/recipes/griddle": "/nutrition/recipes",
        "/nutrition/recipes/weekday-dinners": "/nutrition#batch",
        "/nutrition-test": "/nutrition",
    }
    for path, target in redirects.items():
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 302, path
        assert response.headers["location"] == target


def _assert_day(client, day: date):
    food = build_today_food(PLAN_START, day)
    page = client.get(f"/nutrition?date={day.isoformat()}")
    assert page.status_code == 200, day
    html = page.text
    assert "kcal" in html
    assert 'id="week"' in html
    assert 'id="shop"' in html
    assert 'id="advanced"' in html
    email = _daily_food_html(day)
    assert 'href="/nutrition"' in email
    for meal in food.get("meals") or []:
        line = meal_share_line(meal)
        assert line in html, line
        assert line in email, line
    cleaned = _clean(html)
    found = _BANNED.findall(cleaned)
    assert found == [], found
    return html


def test_easy_day_renders(client):
    _assert_day(client, date(2026, 10, 17))


def test_long_day_renders(client):
    _assert_day(client, date(2026, 10, 18))


def test_cut_phase_day_renders(client):
    _assert_day(client, date(2027, 1, 4))


def test_hard_day_renders(client, monkeypatch):
    from ai_endurance_coach_over50 import plan as plan_mod

    monkeypatch.setattr(
        plan_mod, "session_for_date_extended", lambda d: ("threshold", "Threshold", 50)
    )
    html = _assert_day(client, date(2027, 1, 5))
    assert 'id="ride-fuel"' in html


def test_recipe_index_and_fuelling_render_clean(client):
    for path in ("/nutrition/recipes", "/nutrition/fuelling", "/nutrition/cut", "/nutrition/recipes/travel"):
        response = client.get(path)
        assert response.status_code == 200, path
        found = _BANNED.findall(_clean(response.text))
        assert found == [], (path, found)
    index = client.get("/nutrition/recipes").text
    assert "Method" in index
    assert 'id="overnight-oats"' in index

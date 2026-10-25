"""Chef owns recipes, the plan, and the shop. The page shows evening targets."""
from __future__ import annotations

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from ai_endurance_coach_over50 import nutrition_plan as np_mod
from ai_endurance_coach_over50 import settings
from ai_endurance_coach_over50.nutrition_plan import (
    evening_plate_target,
    prep_cycle_week_index,
    prep_week_day_targets,
    today_targets,
)
from ai_endurance_coach_over50.plan import PLAN_START
from ai_endurance_coach_over50.recipes.menu import shopping_list
from ai_endurance_coach_over50.server import app

_LONG = date(2026, 11, 1)
_CUT = date(2027, 1, 4)


@pytest.fixture
def client():
    return TestClient(app)


def _page(client, day: date, **params) -> str:
    query = {"date": day.isoformat(), **params}
    response = client.get("/nutrition", params=query)
    assert response.status_code == 200
    return response.text


def _first_shop_item(day: date) -> str:
    week = prep_cycle_week_index(PLAN_START, day)
    groups = shopping_list(week, prep_week_day_targets(PLAN_START, day))
    return groups[0]["items"][0]


def _evening_base(day: date) -> int:
    tt = today_targets(day)
    return int(tt.get("plate_kcal") or tt["kcal"])


def test_show_app_shopping_list_defaults_off(monkeypatch):
    monkeypatch.setattr(settings, "SHOW_APP_SHOPPING_LIST", False)
    assert settings.show_app_shopping_list() is False


def test_evening_targets_at_1900_and_shop_hidden(client, monkeypatch):
    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 1900)
    monkeypatch.setattr(settings, "SHOW_APP_SHOPPING_LIST", False)
    assert _evening_base(_LONG) == 1900

    html = _page(client, _LONG)
    section = _evening_section(html)
    assert "target" in section.lower()
    assert "Chef" in section
    for label, key in (
        ("Rest", "rest"),
        ("Training or ruck", "training"),
        ("Long ride", "long"),
    ):
        kcal, protein, carbs = evening_plate_target(key, 1900)
        assert label in section
        assert str(kcal) in section
        assert str(protein) in section
        assert str(carbs) in section
    assert "One list, in grams" not in html
    assert _first_shop_item(_LONG) not in html
    assert "app_shop=1" in html
    assert 'id="shop"' in html


def test_app_shop_query_shows_the_list(client, monkeypatch):
    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 1900)
    monkeypatch.setattr(settings, "SHOW_APP_SHOPPING_LIST", False)
    item = _first_shop_item(_LONG)
    html = _page(client, _LONG, app_shop="1")
    assert item in html
    assert "One list, in grams" in html
    assert "Chef" in html


def test_setting_on_shows_the_list_without_a_query(client, monkeypatch):
    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 1900)
    monkeypatch.setattr(settings, "SHOW_APP_SHOPPING_LIST", True)
    html = _page(client, _LONG)
    assert _first_shop_item(_LONG) in html


def _evening_section(html: str) -> str:
    match = re.search(r'<section id="evening-targets".*?</section>', html, re.S)
    assert match, "evening targets section"
    return match.group(0)


def test_cut_day_scales_evening_targets(client, monkeypatch):
    monkeypatch.setattr(np_mod, "_stable_tdee", lambda days=7: 2200)
    monkeypatch.setattr(settings, "SHOW_APP_SHOPPING_LIST", False)
    base = _evening_base(_CUT)
    assert base == 1600
    section = _evening_section(_page(client, _CUT))
    rest_kcal, rest_p, rest_c = evening_plate_target("rest", base)
    assert rest_kcal == 480
    assert f"{rest_kcal}" in section
    assert f"{rest_p}" in section
    assert f"{rest_c}" in section
    assert "570" not in section
    train_kcal, _, _ = evening_plate_target("training", base)
    long_kcal, _, _ = evening_plate_target("long", base)
    assert str(train_kcal) in section
    assert str(long_kcal) in section
    assert "1,600" in section or "1600" in section

"""Global app search index."""
from __future__ import annotations

from ai_endurance_coach_over50.search import clear_search_cache, search


def setup_function():
    clear_search_cache()


def _titles(q: str) -> list[str]:
    return [r["title"] for r in search(q, limit=25)]


def _urls(q: str) -> list[str]:
    return [r["url"] for r in search(q, limit=25)]


def test_empty_query_returns_hints():
    hits = search("", limit=10)
    assert hits
    assert any(h["url"] == "/" for h in hits)
    assert any("coach" in h["url"] for h in hits)


def test_ctl_alias_to_performance():
    urls = _urls("ctl")
    assert any(u == "/performance" for u in urls)


def test_overnight_oats_recipe():
    titles = " ".join(_titles("overnight oats")).lower()
    assert "oat" in titles
    urls = _urls("overnight oats")
    assert any("overnight-oats" in u or "recipes" in u for u in urls)


def test_weekday_dinner_ragu():
    hits = search("ragu", limit=10)
    assert hits
    assert any("weekday-dinners" in h["url"] or "sunday" in h["url"] for h in hits)


def test_lidl_page():
    urls = _urls("lidl")
    assert any("lidl-shopping-list" in u for u in urls)


def test_help_nutrition():
    urls = _urls("nutrition")
    assert any(u.startswith("/help/nutrition") or u == "/nutrition" for u in urls)


def test_ftp_alias():
    urls = _urls("ftp")
    assert any("/performance" in u or "power-protocol" in u for u in urls)


def test_shopping_item_indexed():
    hits = search("bananas", limit=15)
    assert any(h["type"] == "shopping" for h in hits)

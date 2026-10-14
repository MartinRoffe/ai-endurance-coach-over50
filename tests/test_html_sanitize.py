"""Untrusted HTML is sanitised, and templates do not mark it safe themselves."""
from pathlib import Path

from ai_endurance_coach_over50.html_sanitize import markdown_to_safe_html, sanitize_html

_TEMPLATES = Path(__file__).resolve().parents[1] / "ai_endurance_coach_over50" / "templates"


def test_templates_have_no_safe_filter():
    offenders = []
    for path in _TEMPLATES.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        if "| safe" in text or "|safe" in text:
            offenders.append(str(path.relative_to(_TEMPLATES)))
    assert offenders == []


def test_sanitize_strips_script_and_event_handlers():
    raw = '<p>ok</p><script>alert(1)</script><img src="x" onerror="alert(1)"><strong>keep</strong>'
    out = str(sanitize_html(raw))
    assert "<script>" not in out
    assert "onerror" not in out
    assert "<img" not in out
    assert "<p>ok</p>" in out
    assert "<strong>keep</strong>" in out


def test_sanitize_keeps_relative_help_and_nutrition_links():
    raw = (
        '<a href="/nutrition/recipes#rice">plate</a>'
        '<a href="/help/getting-started">help</a>'
        '<a href="#section">here</a>'
        '<a href="javascript:alert(1)">bad</a>'
        '<a href="data:text/html,hi">data</a>'
        '<a href="vbscript:msg">vb</a>'
    )
    out = str(sanitize_html(raw))
    assert 'href="/nutrition/recipes#rice"' in out
    assert 'href="/help/getting-started"' in out
    assert 'href="#section"' in out
    assert "javascript:" not in out
    assert "data:" not in out
    assert "vbscript:" not in out


def test_markdown_renders_emphasis_and_strips_raw_html():
    out = str(markdown_to_safe_html("Ride **easy** today.\n\n<script>alert(1)</script>"))
    assert "<strong>easy</strong>" in out
    assert "<p>" in out
    assert "<script>" not in out

"""Render untrusted or authored markdown to HTML and sanitise it.

Jinja autoescape stays on. The only strings marked safe are the result of
``sanitize_html`` — a strict tag and attribute allow-list. Garmin, Withings,
user, and model text must not be passed through ``| safe`` in templates.
"""
from __future__ import annotations

import logging
import re
from html import escape

import bleach
from markupsafe import Markup

logger = logging.getLogger(__name__)

# Tags produced by the markdown extensions we actually use (tables, fenced
# code, nl2br). No images, no style, no event handlers.
ALLOWED_TAGS = frozenset({
    "a", "p", "br", "hr",
    "strong", "em", "b", "i",
    "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "code", "pre", "blockquote",
    "table", "thead", "tbody", "tr", "th", "td",
})

_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_ID_RE = re.compile(r"[A-Za-z][\w:.-]*")
_SAFE_HREF_RE = re.compile(r"^(https?://|mailto:)", re.IGNORECASE)


def _allow_attr(tag: str, name: str, value: str) -> bool:
    """Allow-list for attributes. Rejects javascript:, data:, and style."""
    if tag == "a" and name == "href":
        href = (value or "").strip()
        lower = href.lower()
        if lower.startswith(("javascript:", "data:", "vbscript:")):
            return False
        if href.startswith("/") and not href.startswith("//"):
            return True
        if href.startswith("#"):
            return True
        return bool(_SAFE_HREF_RE.match(href))
    if tag == "a" and name == "title":
        return True
    if tag in {"th", "td"} and name == "align":
        return value in {"left", "center", "right"}
    if tag in _HEADING_TAGS and name == "id":
        return bool(_ID_RE.fullmatch(value or ""))
    return False


def sanitize_html(value: str | None) -> Markup:
    """Return HTML that is safe to render unescaped. Empty input stays empty."""
    if not value:
        return Markup("")
    cleaned = bleach.clean(
        str(value),
        tags=ALLOWED_TAGS,
        attributes=_allow_attr,
        strip=True,
    )
    return Markup(cleaned)


def markdown_to_safe_html(text: str | None) -> Markup:
    """Markdown → HTML, then the allow-list. Used for AI narratives."""
    if not text:
        return Markup("")
    try:
        import markdown as md
        raw = md.markdown(text, extensions=["tables", "fenced_code", "nl2br"])
    except Exception:
        logger.warning("markdown render failed; escaping as text", exc_info=True)
        raw = "<pre>" + escape(text) + "</pre>"
    return sanitize_html(raw)

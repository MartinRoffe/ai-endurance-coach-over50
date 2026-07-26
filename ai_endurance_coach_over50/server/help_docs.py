"""In-app Help centre: resolve and render packaged Markdown docs."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import markdown as md


# page_id → relative path under docs root
HELP_PAGES: dict[str, str] = {
    "how-it-works": "how-it-works.md",
    "getting-started": "getting-started.md",
    "concepts": "concepts.md",
    "power-training": "power-training.md",
    "position": "position.md",
    "readiness": "tabs/readiness.md",
    "performance": "tabs/performance.md",
    "plan": "tabs/plan.md",
    "nutrition": "tabs/nutrition.md",
    "health": "tabs/health.md",
    "events": "tabs/events.md",
    "coach": "tabs/coach.md",
    "email-and-automation": "email-and-automation.md",
    "faq": "faq.md",
    "architecture": "architecture.md",
    "ai-architecture": "ai-architecture.md",
    "coach-chat-walkthrough": "coach-chat-walkthrough.md",
}

HELP_TITLES: dict[str, str] = {
    "how-it-works": "How the app works",
    "getting-started": "Getting Started",
    "concepts": "Key Concepts",
    "power-training": "Power Training",
    "position": "Strength rebuild & road position",
    "readiness": "Readiness",
    "performance": "Performance & Analysis",
    "plan": "Plan",
    "nutrition": "Nutrition",
    "health": "Health",
    "events": "Events",
    "coach": "Coach",
    "email-and-automation": "Email & Automation",
    "faq": "FAQ & Troubleshooting",
    "architecture": "Architecture",
    "ai-architecture": "AI Architecture",
    "coach-chat-walkthrough": "Coach chat walkthrough",
}

# Sidebar: (section_label, [(page_id, label), ...])
HELP_NAV: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Using the app",
        [
            ("how-it-works", "How it works"),
            ("getting-started", "Getting started"),
            ("concepts", "Key concepts"),
            ("power-training", "Power training"),
            ("position", "Strength & position"),
            ("readiness", "Readiness"),
            ("performance", "Performance"),
            ("plan", "Plan"),
            ("nutrition", "Nutrition"),
            ("health", "Health"),
            ("events", "Events"),
            ("coach", "Coach"),
            ("email-and-automation", "Email & automation"),
            ("faq", "FAQ"),
        ],
    ),
    (
        "For developers",
        [
            ("architecture", "Architecture"),
            ("ai-architecture", "AI Architecture"),
            ("coach-chat-walkthrough", "Coach chat walkthrough"),
        ],
    ),
]

DEFAULT_HELP_PAGE = "how-it-works"

_MD_EXTS = ["tables", "fenced_code", "toc", "sane_lists", "nl2br"]

# filename (with or without tabs/) → page_id
_FILE_TO_PAGE: dict[str, str] = {}
for _pid, _rel in HELP_PAGES.items():
    _FILE_TO_PAGE[_rel] = _pid
    _FILE_TO_PAGE[Path(_rel).name] = _pid


@dataclass(frozen=True)
class HelpPage:
    page_id: str
    title: str
    html: str
    embed_architecture: bool = False


def docs_root() -> Path:
    """Prefer repo docs/ when present (dev); else packaged help_docs/."""
    pkg = Path(__file__).resolve().parent.parent
    repo_docs = pkg.parent / "docs"
    if repo_docs.is_dir() and (repo_docs / "how-it-works.md").is_file():
        return repo_docs
    packaged = pkg / "help_docs"
    return packaged


def _strip_screenshot_placeholders(text: str) -> str:
    # Remove blockquotes that are only screenshot placeholders.
    return re.sub(
        r"(?m)^>\s*📸\s*\*?[^\n]*\n(?:^>\s*[^\n]*\n)*\n?",
        "",
        text,
    )


def _rewrite_md_links(html: str, current_rel: str) -> str:
    """Rewrite href="….md" / relative doc links to /help/{page_id}."""
    current_dir = Path(current_rel).parent

    def repl(m: re.Match[str]) -> str:
        href = m.group(1)
        if href.startswith(("http://", "https://", "mailto:", "#", "/")):
            return m.group(0)
        path_part, _, frag = href.partition("#")
        if not path_part.endswith(".md"):
            return m.group(0)
        # Resolve relative to the current markdown file's directory
        resolved = (current_dir / path_part).as_posix()
        # Normalise ./ and ../
        parts: list[str] = []
        for p in resolved.split("/"):
            if p in ("", "."):
                continue
            if p == "..":
                if parts:
                    parts.pop()
                continue
            parts.append(p)
        norm = "/".join(parts)
        page_id = _FILE_TO_PAGE.get(norm) or _FILE_TO_PAGE.get(Path(norm).name)
        if not page_id:
            return m.group(0)
        suffix = f"#{frag}" if frag else ""
        return f'href="/help/{page_id}{suffix}"'

    return re.sub(r'href="([^"]+)"', repl, html)


@lru_cache(maxsize=1)
def _md() -> md.Markdown:
    return md.Markdown(extensions=_MD_EXTS)


def render_help_page(page_id: str) -> Optional[HelpPage]:
    rel = HELP_PAGES.get(page_id)
    if not rel:
        return None
    path = docs_root() / rel
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8")
    raw = _strip_screenshot_placeholders(raw)
    converter = _md()
    converter.reset()
    body = converter.convert(raw)
    body = _rewrite_md_links(body, rel)
    return HelpPage(
        page_id=page_id,
        title=HELP_TITLES.get(page_id, page_id),
        html=body,
        embed_architecture=(page_id == "architecture"),
    )

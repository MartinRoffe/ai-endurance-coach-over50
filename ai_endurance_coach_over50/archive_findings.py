"""Locate archive/findings.json for dashboard and coach context.

Runtime (launchd) uses site-packages with an arbitrary cwd, so we never rely on
cwd alone. Preferred durable location matches the rest of the app:

    ~/.ai_endurance_coach_over50/archive/findings.json

The repo-tree ``archive/`` copy is still searched for local CLI / analysis runs.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from .paths import data_dir

logger = logging.getLogger(__name__)


def home_archive() -> Path:
    """Durable copy of findings.json. Honours ENDURANCE_COACH_HOME."""
    return data_dir() / "archive"


def find_archive_dir() -> Optional[Path]:
    env = os.getenv("ARCHIVE_DIR")
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p

    candidates: list[Path] = [
        home_archive(),
        Path.cwd() / "archive",
        # Source checkout: …/ai_endurance_coach_over50/archive_findings.py → repo/archive
        Path(__file__).resolve().parent.parent / "archive",
    ]

    # When installed into site-packages, also peek at PYTHONPATH entries for a
    # checkout that still has an archive/ folder.
    for entry in (os.getenv("PYTHONPATH") or "").split(os.pathsep):
        if not entry:
            continue
        root = Path(entry)
        # PYTHONPATH may be the repo root or …/site-packages
        for cand in (root / "archive", root.parent / "archive"):
            candidates.append(cand)

    seen: set[Path] = set()
    for cand in candidates:
        try:
            cand = cand.resolve()
        except Exception:
            logger.warning("could not resolve archive candidate %s", cand, exc_info=True)
            continue
        if cand in seen:
            continue
        seen.add(cand)
        if cand.is_dir() and (
            (cand / "findings.json").is_file() or (cand / "garmin_fetch.py").is_file()
        ):
            return cand
    return None


def load_archive_findings() -> Optional[dict[str, Any]]:
    root = find_archive_dir()
    if root is None:
        return None
    path = root / "findings.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("could not read archive findings %s", path)
        return None


def publish_findings(findings_path: Path) -> Path:
    """Copy findings.json into the home archive so launchd can always read it."""
    dest_dir = home_archive()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "findings.json"
    dest.write_text(findings_path.read_text(encoding="utf-8"), encoding="utf-8")
    return dest

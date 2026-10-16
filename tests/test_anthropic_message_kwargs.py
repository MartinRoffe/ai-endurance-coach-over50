"""Message calls must match the installed anthropic SDK signatures.

anthropic 1.0 removed ``temperature``, ``top_p``, and ``top_k`` from
``messages.create`` / ``messages.stream``. Those methods take no ``**kwargs``,
so a leftover keyword raises ``TypeError`` before a request is sent.
"""
import ast
import inspect
from datetime import date
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

import pytest

from anthropic.resources.messages.messages import Messages

from ai_endurance_coach_over50.metrics import DailyMetrics
from ai_endurance_coach_over50.report import generate_advice

ROOT = Path(__file__).resolve().parents[1]
_SCAN_ROOTS = (
    ROOT / "ai_endurance_coach_over50",
    ROOT / "archive",
    ROOT / "tests",
)
_CREATE_PARAMS = set(inspect.signature(Messages.create).parameters) - {"self"}
_STREAM_PARAMS = set(inspect.signature(Messages.stream).parameters) - {"self"}


def _message_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"create", "stream"}:
            continue
        inner = node.func.value
        if isinstance(inner, ast.Attribute) and inner.attr == "messages":
            yield node


def test_repo_message_calls_match_installed_sdk():
    """Would have failed on temperature=0 against anthropic 1.4.0."""
    offenders: list[str] = []
    for scan_root in _SCAN_ROOTS:
        if not scan_root.is_dir():
            continue
    for path in scan_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in _message_calls(tree):
            allowed = _CREATE_PARAMS if call.func.attr == "create" else _STREAM_PARAMS
            for kw in call.keywords:
                if kw.arg is None or kw.arg not in allowed:
                    name = "**kwargs" if kw.arg is None else kw.arg
                    rel = path.relative_to(ROOT)
                    offenders.append(f"{rel}:{call.lineno} messages.{call.func.attr}({name}=)")
    assert offenders == []


def test_generate_advice_binds_on_messages_create():
    target = date(2026, 10, 11)
    metrics = DailyMetrics(date=target, sleep_score=80, body_battery_morning=60, hrv_last_night=42)
    captured: dict = {}

    class _Block:
        text = "Keep today easy and aerobic."

    class _Message:
        content = [_Block()]

    class _Messages:
        def create(self, **kwargs):
            inspect.signature(Messages.create).bind(None, **kwargs)
            captured.update(kwargs)
            return _Message()

    class _Client:
        def __init__(self, api_key):
            self.messages = _Messages()

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("ai_endurance_coach_over50.report.anthropic.Anthropic", _Client):
            text = generate_advice(metrics, {}, 0.2, mode="pre")

    assert text == "Keep today easy and aerobic."
    assert "temperature" not in captured
    assert captured["model"]


def _version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in value.split(".")[:3]:
        digits = ""
        for char in piece:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits or "0"))
    return tuple(parts)


def test_installed_anthropic_is_in_the_pinned_range():
    """pyproject allows anthropic>=1.4,<2 — 1.0 dropped sampling kwargs."""
    installed = _version_tuple(version("anthropic"))
    assert installed >= (1, 4)
    assert installed < (2, 0)
    assert "temperature" not in _CREATE_PARAMS
    assert "temperature" not in _STREAM_PARAMS
    with pytest.raises(TypeError):
        inspect.signature(Messages.create).bind(
            None, model="m", max_tokens=1, messages=[], temperature=0,
        )

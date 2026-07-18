"""Athlete-facing coach error messages for Anthropic failures."""
from __future__ import annotations

from ai_endurance_coach_over50.server.coach import _coach_user_error_message


def test_credit_balance_message():
    msg = _coach_user_error_message(
        Exception(
            "Error code: 400 - Your credit balance is too low to access the Anthropic API. "
            "Please go to Plans & Billing to upgrade or purchase credits."
        )
    )
    assert "credits are exhausted" in msg
    assert "console.anthropic.com" in msg


def test_generic_message_hides_raw_exception():
    msg = _coach_user_error_message(RuntimeError("secret-key-xyz exploded"))
    assert "temporarily unavailable" in msg
    assert "secret-key-xyz" not in msg


def test_rate_limit_message():
    msg = _coach_user_error_message(Exception("Error code: 429 - rate_limit_error: Rate limit exceeded"))
    assert "rate limit" in msg.lower()


def test_invalid_api_key_message():
    msg = _coach_user_error_message(Exception("Error code: 401 - invalid x-api-key"))
    assert "API key is invalid" in msg

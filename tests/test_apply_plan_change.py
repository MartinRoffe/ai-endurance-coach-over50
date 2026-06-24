"""apply-plan-change request validation."""
import pytest
from pydantic import ValidationError

from ai_endurance_coach_over50.server import _ApplyChangeRequest


def test_rest_day_allows_zero_duration():
    req = _ApplyChangeRequest(
        date="2026-06-28",
        duration_min=0,
        reason="Athlete unavailable",
        session_type="rest",
        label="Rest Day",
    )
    assert req.duration_min == 0


def test_negative_duration_rejected():
    with pytest.raises(ValidationError):
        _ApplyChangeRequest(date="2026-06-28", duration_min=-1, reason="bad")

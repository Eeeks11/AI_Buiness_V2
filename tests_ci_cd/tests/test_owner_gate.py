"""Tests for owner gate signature and authorization modules."""

from __future__ import annotations

from typing import Any, Dict, Sequence

import pytest

from pytest_mock import MockerFixture
from config_settings import config as config_module
from models.core import ConstitutionalError
from owner_control.owner_gate.authorization import require_owner_approval
from owner_control.owner_gate.signature import sign_action, verify_owner_signature


def _configure_owner_environment(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """Configure environment variables for owner authorization tests."""
    monkeypatch.setenv("OWNER_AUTH_MODE", mode)
    monkeypatch.setenv("OWNER_ID", "owner_tester")
    monkeypatch.setenv("OWNER_SIGNATURE_KEY", "super_secret_signature_key_value_1234567890")
    monkeypatch.setenv("OWNER_GATE_ENABLED", "true")
    config_module._settings = None  # Reset cached settings


def _assert_log_event(log_calls: Sequence[Any], event_name: str) -> None:
    """Assert that a log call contains the specified event name."""
    assert any(
        call.kwargs.get("extra", {}).get("event") == event_name for call in log_calls
    ), f"Expected log event '{event_name}' not found"


def test_sign_and_verify_software_mode(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """Ensure software mode produces verifiable signatures."""
    _configure_owner_environment(monkeypatch, "SOFTWARE")
    log_spy = mocker.patch("owner_control.owner_gate.signature.logger.info")

    payload: Dict[str, Any] = {
        "action": "execute_decision",
        "proposal": {"id": "proposal-1"},
        "owner_id": "owner_tester",
    }

    signature = sign_action(owner_id="owner_tester", payload=payload)

    assert signature.startswith("software:")
    assert verify_owner_signature("owner_tester", payload, signature) is True
    assert (
        verify_owner_signature(
            "owner_tester",
            {**payload, "proposal": {"id": "tampered"}},
            signature,
        )
        is False
    )
    assert verify_owner_signature("other_owner", payload, signature) is False

    _assert_log_event(log_spy.call_args_list, "owner_sign_attempt")
    _assert_log_event(log_spy.call_args_list, "owner_sign_result")


def test_sign_action_hardware_mode_raises(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hardware mode should raise until hardware integration is available."""
    _configure_owner_environment(monkeypatch, "HARDWARE")

    with pytest.raises(ConstitutionalError, match="Hardware signing not configured"):
        sign_action(owner_id="owner_tester", payload={"action": "test"})

    assert (
        verify_owner_signature(
            "owner_tester", {"action": "test"}, "hardware:signature:placeholder"
        )
        is False
    )


def test_mock_mode_signature_deterministic(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mock mode should generate deterministic signatures for testing."""
    _configure_owner_environment(monkeypatch, "MOCK")

    payload: Dict[str, Any] = {
        "action": "execute_decision",
        "proposal": {"id": "proposal-mock"},
        "owner_id": "owner_tester",
    }

    signature_one = sign_action("owner_tester", payload)
    signature_two = sign_action("owner_tester", payload)

    assert signature_one == signature_two
    assert signature_one.startswith("mock_owner_signature:")
    assert verify_owner_signature("owner_tester", payload, signature_one) is True


def test_require_owner_approval_enforces_signature(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """Decorator should block execution without valid owner signature."""
    _configure_owner_environment(monkeypatch, "SOFTWARE")
    auth_log_spy = mocker.patch("owner_control.owner_gate.authorization.logger.info")

    payload: Dict[str, Any] = {
        "action": "execute_decision",
        "proposal": {"id": "proposal-auth"},
        "owner_id": "owner_tester",
    }

    @require_owner_approval("test_action")
    def protected_action(state: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "ok", "proposal_id": state["authorization_payload"]["proposal"]["id"]}

    missing_signature_state: Dict[str, Any] = {
        "authorization_payload": payload,
        "owner_id": "owner_tester",
    }

    with pytest.raises(
        ConstitutionalError, match="Rule 10 Violation: test_action requires owner approval"
    ):
        protected_action(missing_signature_state)

    signature = sign_action("owner_tester", payload)
    valid_state: Dict[str, Any] = {
        "authorization_payload": payload,
        "owner_id": "owner_tester",
        "owner_signature": signature,
    }

    result = protected_action(valid_state)
    assert result["status"] == "ok"
    assert result["proposal_id"] == "proposal-auth"

    tampered_state = {**valid_state, "authorization_payload": {**payload, "proposal": {"id": "tampered"}}}

    with pytest.raises(ConstitutionalError, match="requires owner approval"):
        protected_action(tampered_state)

    _assert_log_event(auth_log_spy.call_args_list, "owner_gate_check")
    _assert_log_event(auth_log_spy.call_args_list, "owner_gate_passed")


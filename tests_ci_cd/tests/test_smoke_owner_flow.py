"""Smoke tests for end-to-end owner authorization flow."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any, Dict

import pytest
from pytest_mock import MockerFixture

from config_settings import config as config_module
from owner_control.owner_gate.signature import sign_action
from governance_layer.orchestrator import langgraph_state_machine as sm


def _configure_owner_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure environment variables for smoke flow tests."""
    monkeypatch.setenv("OWNER_AUTH_MODE", "SOFTWARE")
    monkeypatch.setenv("OWNER_ID", "owner_tester")
    monkeypatch.setenv("OWNER_SIGNATURE_KEY", "super_secret_signature_key_value_1234567890")
    monkeypatch.setenv("OWNER_GATE_ENABLED", "true")
    config_module._settings = None


class FakeStateGraph:
    """Lightweight replacement for StateGraph in tests."""

    def __init__(self, _state_type: Any) -> None:
        self.nodes: Dict[str, Any] = {}

    def add_node(self, name: str, func: Any) -> None:
        self.nodes[name] = func

    def set_entry_point(self, entry: str) -> None:
        self.entry = entry

    def add_edge(self, _start: str, _end: str) -> None:
        return

    def compile(self) -> SimpleNamespace:
        def invoke(state: Dict[str, Any]) -> Dict[str, Any]:
            ordered_phases = [
                sm.GovernancePhase.IDEATION,
                sm.GovernancePhase.DELIBERATION,
                sm.GovernancePhase.VOTING,
                sm.GovernancePhase.EXECUTION,
            ]
            current_state = state
            for phase in ordered_phases:
                current_state = self.nodes[phase](current_state)
            return current_state

        return SimpleNamespace(invoke=invoke)


def test_owner_signature_enables_execution(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """Owner signature should allow execution through governance cycle."""
    _configure_owner_environment(monkeypatch)

    mocker.patch("utilities.logger.log_event")
    mocker.patch(
        "governance_layer.orchestrator.langgraph_state_machine.StateGraph",
        FakeStateGraph,
    )
    mocker.patch(
        "governance_layer.orchestrator.langgraph_state_machine.build_agent_context",
        return_value={
            "timestamp": "2025-01-01T00:00:00Z",
            "recent_activity_summary": "",
            "relevant_precedents": [],
            "trend_analysis": "",
            "constitutional_rules": {},
        },
    )
    mocker.patch(
        "governance_layer.orchestrator.langgraph_state_machine.call_llm",
        return_value="llm-response",
    )
    mocker.patch(
        "governance_layer.orchestrator.langgraph_state_machine.validate_constitutional_compliance",
        return_value=SimpleNamespace(
            is_compliant=True,
            violated_rules=[],
            error_messages=[],
            validation_details={},
        ),
    )

    auth_log_spy = mocker.patch(
        "owner_control.owner_gate.authorization.logger.info"
    )

    proposal: Dict[str, Any] = {
        "id": "proposal-smoke",
        "title": "Deploy Feature",
        "description": "Execute new feature rollout.",
        "financial_impact": 50000.0,
        "legal_risk": 0.1,
        "status": "approved",
    }

    authorization_payload = {
        "action": "execute_decision",
        "proposal": copy.deepcopy(proposal),
        "owner_id": "owner_tester",
    }
    signature = sign_action("owner_tester", authorization_payload)

    final_state = sm.run_governance_cycle(
        proposal=proposal,
        owner_signature=signature,
        owner_id="owner_tester",
    )

    assert final_state["execution_result"]["status"] == "executed"
    assert final_state["authorization_payload"]["action"] == "execute_decision"
    assert final_state["errors"] == []

    assert any(
        call.kwargs.get("extra", {}).get("event") == "owner_gate_passed"
        for call in auth_log_spy.call_args_list
    ), "Expected owner gate pass log entry"


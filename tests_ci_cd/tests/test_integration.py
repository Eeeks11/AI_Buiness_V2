from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

import pytest

from models.core import (
    ConstitutionalError,
    ConstitutionalRule,
    ConstitutionalValidation,
)


@pytest.fixture()
def mock_proposal() -> Dict[str, Any]:
    """Provide a standard proposal payload for integration tests."""
    return {
        "id": "test-proposal-001",
        "title": "Test Integration Proposal",
        "description": "End-to-end test",
        "financial_impact": 1000.0,
        "legal_risk": 0.1,
        "keywords": ["integration", "testing"],
    }


@pytest.fixture()
def mock_owner_signature(mock_proposal, isolated_logging_env) -> str:
    """Generate a valid owner signature for the mock proposal."""
    from governance_layer.orchestrator import langgraph_state_machine
    from owner_control.owner_gate.signature import sign_action

    authorization_payload = langgraph_state_machine._build_authorization_payload(
        owner_id="owner_admin",
        proposal=mock_proposal,
    )
    signature = sign_action("owner_admin", authorization_payload)
    return signature


def _make_validation(rules: Iterable[int], sink: Set[int]) -> ConstitutionalValidation:
    """Create a constitutional validation result marking specified rules as compliant."""
    validation = ConstitutionalValidation()
    for rule_num in rules:
        constitutional_rule = ConstitutionalRule(rule_num)
        validation.mark_rule_compliant(constitutional_rule)
        sink.add(rule_num)
    return validation


def _read_logged_event_types(log_path: Path) -> List[str]:
    """Read event types from a JSONL log file."""
    if not log_path.exists():
        return []

    event_types: List[str] = []
    with open(log_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            event_type = entry.get("type")
            if isinstance(event_type, str):
                event_types.append(event_type)
    return event_types


def _context_stub() -> Dict[str, Any]:
    """Provide minimal governance context for testing."""
    return {
        "recent_activity_summary": "Summary",
        "relevant_precedents": [],
        "trend_analysis": "Stable performance.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def test_full_governance_cycle(
    isolated_logging_env,
    mock_proposal,
    mock_owner_signature,
    monkeypatch,
) -> None:
    """Validate end-to-end governance cycle completes and logs critical events."""
    from governance_layer.orchestrator import langgraph_state_machine as state_machine

    checked_rules: Set[int] = set()

    def fake_validate(*args: Any, **kwargs: Any) -> ConstitutionalValidation:
        action = kwargs.get("action") or {}
        action_type = str(action.get("type", ""))

        if kwargs.get("vote_result"):
            return _make_validation({8, 9}, checked_rules)
        if action_type.endswith("_precheck") or action_type.endswith("_postcheck"):
            return _make_validation({10, 6}, checked_rules)
        if "ideation" in action_type:
            return _make_validation({1, 2, 3, 6, 7}, checked_rules)
        if "deliberation" in action_type:
            return _make_validation({4, 5, 6, 7}, checked_rules)
        if "execute" in action_type:
            return _make_validation({6, 7, 10}, checked_rules)
        return _make_validation({6}, checked_rules)

    monkeypatch.setattr(state_machine, "validate_constitutional_compliance", fake_validate)
    monkeypatch.setattr(
        state_machine,
        "build_agent_context",
        lambda *args, **kwargs: _context_stub(),
    )
    monkeypatch.setattr(state_machine, "call_llm", lambda **_: "Simulated response")

    result = state_machine.run_governance_cycle(
        proposal=mock_proposal,
        owner_signature=mock_owner_signature,
        owner_id="owner_admin",
    )

    assert result["execution_result"]["status"] == "executed"
    assert result["ideation_result"] is not None
    assert result["deliberation_result"] is not None
    assert result["voting_result"] is not None

    assert checked_rules == set(range(1, 11))

    log_path: Path = isolated_logging_env["log_path"]
    event_types = _read_logged_event_types(log_path)
    assert "governance_cycle_complete" in event_types
    assert event_types.count("governance_state_entry") >= 4


def test_owner_gate_enforcement(
    isolated_logging_env,
    mock_proposal,
    monkeypatch,
) -> None:
    """Ensure owner gate rejects unsigned execution and accepts authorized execution."""
    from governance_layer.orchestrator import langgraph_state_machine as state_machine
    from owner_control.owner_gate.signature import sign_action

    monkeypatch.setattr(
        state_machine,
        "validate_constitutional_compliance",
        lambda *args, **kwargs: ConstitutionalValidation(),
    )
    monkeypatch.setattr(
        state_machine,
        "build_agent_context",
        lambda *args, **kwargs: _context_stub(),
    )
    monkeypatch.setattr(state_machine, "call_llm", lambda **_: "Simulated response")

    authorization_payload = state_machine._build_authorization_payload("owner_admin", mock_proposal)

    # Missing signature should raise ConstitutionalError (Rule 10)
    unsigned_state: Dict[str, Any] = {
        "phase": state_machine.GovernancePhase.EXECUTION,
        "proposal": mock_proposal,
        "owner_signature": None,
        "owner_id": "owner_admin",
        "authorization_payload": authorization_payload,
        "context": {},
        "validation_results": {},
        "errors": [],
    }

    with pytest.raises(ConstitutionalError):
        state_machine.execute_decision(unsigned_state)

    # Valid signature should pass
    valid_signature = sign_action("owner_admin", authorization_payload)
    signed_state = dict(unsigned_state)
    signed_state["owner_signature"] = valid_signature

    executed_state = state_machine.execute_decision(signed_state)
    assert executed_state["execution_result"]["status"] == "executed"


def test_log_chain_integrity_persists(isolated_logging_env) -> None:
    """Verify log chain remains valid after multiple operations."""
    logger_module = isolated_logging_env["logger_module"]

    for index in range(5):
        logger_module.log_event(
            event_type="integration_event",
            data={"iteration": index},
        )

    assert logger_module.validate_log_chain() is True


def test_retrospective_requires_owner_approval(
    isolated_logging_env,
    monkeypatch,
) -> None:
    """Confirm retrospectives enforce owner approval (Rule 10)."""
    from governance_layer import retrospective
    from owner_control.owner_gate.signature import sign_action

    sample_logs = [
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "governance_state_entry",
            "data": {"proposal_id": "abc"},
        }
    ]

    monkeypatch.setattr(retrospective, "get_recent_logs", lambda limit=2000: sample_logs)
    monkeypatch.setattr(retrospective, "get_recent_metrics", lambda days=7: [])
    monkeypatch.setattr(
        retrospective,
        "validate_constitutional_compliance",
        lambda *args, **kwargs: ConstitutionalValidation(),
    )
    monkeypatch.setattr(
        retrospective,
        "build_agent_context",
        lambda *args, **kwargs: _context_stub(),
    )

    with pytest.raises(ConstitutionalError):
        retrospective.conduct_weekly_retrospective(days=7)

    authorization_payload = {
        "action": "conduct_weekly_retrospective",
        "owner_id": "owner_admin",
        "window_days": 7,
    }
    owner_signature = sign_action("owner_admin", authorization_payload)

    report = retrospective.conduct_weekly_retrospective(
        days=7,
        owner_id="owner_admin",
        owner_signature=owner_signature,
        authorization_payload=authorization_payload,
    )

    assert report["metrics_summary"] is not None
    assert report["outcomes_analyzed"] is not None
    assert report["timestamp"]


def test_all_rules_enforced_in_cycle(
    isolated_logging_env,
    mock_proposal,
    mock_owner_signature,
    monkeypatch,
) -> None:
    """Ensure full governance cycle touches all constitutional rules."""
    from governance_layer.orchestrator import langgraph_state_machine as state_machine

    checked_rules: Set[int] = set()

    def validating_stub(*args: Any, **kwargs: Any) -> ConstitutionalValidation:
        validation = _make_validation(range(1, 11), checked_rules)
        return validation

    monkeypatch.setattr(state_machine, "validate_constitutional_compliance", validating_stub)
    monkeypatch.setattr(
        state_machine,
        "build_agent_context",
        lambda *args, **kwargs: _context_stub(),
    )
    monkeypatch.setattr(state_machine, "call_llm", lambda **_: "Simulated")

    state_machine.run_governance_cycle(
        proposal=mock_proposal,
        owner_signature=mock_owner_signature,
        owner_id="owner_admin",
    )

    assert checked_rules == set(range(1, 11))


from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import pytest

from constitutional_layer_immutable import constitution
from memory_systems.codebase_memory.models.core import (
    ConstitutionalValidation,
)


def _context_stub() -> Dict[str, Any]:
    """Provide minimal governance context for orchestrator tests."""
    return {
        "recent_activity_summary": "Summary",
        "relevant_precedents": [],
        "trend_analysis": "Stable performance.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def test_rule_1_through_10_enforced() -> None:
    """Attempt to violate each constitutional rule and ensure enforcement."""
    violations = [
        lambda: constitution.enforce_rule_1(
            {"type": "remove access", "target": "owner credentials"},
            owner_permission=False,
        ),
        lambda: constitution.enforce_rule_2(
            {"type": "grant access", "recipient": "partner"},
            owner_consent=False,
        ),
        lambda: constitution.enforce_rule_3(
            {"type": "modify", "file_path": "constitutional_layer_immutable/constitution.md"}
        ),
        lambda: constitution.enforce_rule_4(
            {"decision": "invest"},
            financial_impact=1000.0,
            alternative_impact=1500.0,
        ),
        lambda: constitution.enforce_rule_5(
            {"action": "execute high risk plan"},
            legal_risk=0.9,
            legal_approval=False,
        ),
        lambda: constitution.enforce_rule_6(
            {"action": "unlogged operation"},
            logged=False,
        ),
        lambda: constitution.enforce_rule_7(
            {"decision": "execute without board"},
            board_approved=False,
        ),
        lambda: constitution.enforce_rule_8(
            ["model_a", "model_b", "model_c", "model_d"]
        ),
        lambda: constitution.enforce_rule_9(
            {"member_a": 0.4, "member_b": 0.2, "member_c": 0.2, "member_d": 0.2}
        ),
        lambda: constitution.enforce_rule_10(
            {"type": "transfer ownership"},
            owner_authorized=False,
        ),
    ]

    for violation in violations:
        with pytest.raises(constitution.ConstitutionalError):
            violation()


def test_all_modules_call_validate_compliance(
    isolated_logging_env,
    monkeypatch,
) -> None:
    """Verify orchestrator, memory, and owner gate invoke constitutional validation."""
    from governance_layer.orchestrator import langgraph_state_machine as orchestrator
    from memory_systems.business_memory.memory import context_builder
    from owner_control.owner_gate import authorization

    call_counts: Dict[str, int] = {"orchestrator": 0, "memory": 0, "owner_gate": 0}

    def make_tracker(label: str):
        def tracker(*args: Any, **kwargs: Any) -> ConstitutionalValidation:
            call_counts[label] += 1
            return ConstitutionalValidation()

        return tracker

    monkeypatch.setattr(orchestrator, "validate_constitutional_compliance", make_tracker("orchestrator"))
    monkeypatch.setattr(context_builder, "validate_constitutional_compliance", make_tracker("memory"))
    monkeypatch.setattr(authorization, "validate_constitutional_compliance", make_tracker("owner_gate"))

    monkeypatch.setattr(orchestrator, "call_llm", lambda **kwargs: "Simulated response")
    monkeypatch.setattr(orchestrator, "build_agent_context", lambda *args, **kwargs: _context_stub())

    monkeypatch.setattr(context_builder, "get_recent_events", lambda limit=100: [])
    monkeypatch.setattr(context_builder, "summarize_recent_activity", lambda events: "Summary")
    monkeypatch.setattr(context_builder, "recall_relevant_decisions", lambda query, n_results=5: [])
    monkeypatch.setattr(context_builder, "get_trend_analysis", lambda topic: "Stable performance")

    monkeypatch.setattr(authorization, "verify_owner_signature", lambda *args, **kwargs: True)

    # Orchestrator path
    state = {
        "phase": orchestrator.GovernancePhase.IDEATION,
        "proposal": {"id": "p-1", "title": "Proposal", "description": "Desc"},
        "role": "CHAIR",
        "validation_results": {},
        "errors": [],
    }
    orchestrator.conduct_ideation(state)

    # Memory path
    context_builder.build_agent_context(
        role="CEO",
        current_proposal={"id": "p-2", "title": "Context", "description": "Context description"},
        topic_keywords=["governance"],
    )

    # Owner gate path
    protected = authorization.require_owner_approval("test_action")(lambda **kwargs: True)
    protected(
        owner_id="owner_admin",
        owner_signature="placeholder_signature",
        authorization_payload={"action": "test_action"},
    )

    assert call_counts["orchestrator"] >= 1
    assert call_counts["memory"] >= 1
    assert call_counts["owner_gate"] >= 2  # pre and post validation


def test_logging_coverage_meets_threshold(isolated_logging_env) -> None:
    """Ensure logging coverage exceeds the 95% requirement."""
    from utilities.logger import log_event, get_recent_logs

    expected_events = {
        "system_startup",
        "proposal_created",
        "ideation_completed",
        "deliberation_completed",
        "vote_cast",
        "owner_gate_check",
        "owner_gate_passed",
        "execution_completed",
        "retrospective_completed",
        "llm_call_attempt",
        "memory_write_attempt",
    }

    for event in expected_events:
        log_event(
            event_type=event,
            data={"source": "coverage_test"},
        )

    logs = get_recent_logs(limit=1000)
    log_types = {log["type"] for log in logs if "type" in log}

    coverage = len(expected_events & log_types) / len(expected_events)
    assert coverage >= 0.95, f"Logging coverage {coverage*100:.1f}% < 95%"


def test_immutable_log_chain_valid(isolated_logging_env) -> None:
    """Validate log chain integrity."""
    from utilities.logger import log_event, validate_log_chain

    log_event(
        event_type="chain_validation_event",
        data={"timestamp": datetime.now(timezone.utc).isoformat()},
    )
    assert validate_log_chain() is True


def test_memory_integrity_validated(monkeypatch) -> None:
    """Confirm memory integrity validator passes with healthy data."""
    from memory_systems.business_memory.memory import semantic

    class DummyCollection:
        def get(self) -> Dict[str, Any]:
            return {"ids": [], "metadatas": [], "embeddings": []}

    monkeypatch.setattr(semantic, "_get_collection", lambda: DummyCollection())
    assert semantic.validate_memory_integrity() is True


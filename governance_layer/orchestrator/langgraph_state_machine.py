"""
LangGraph State Machine for Governance

Implements governance cycle with state machine: IDEATION → DELIBERATION → VOTING → EXECUTION.
Each state transition includes constitutional validation gates.
"""

# Standard library
import copy
import logging
from typing import Any, Dict, Optional, TypedDict, Union
from pathlib import Path
import sys

# Third-party
from langgraph.graph import StateGraph, END

# Local - models first (single source of truth)
project_root = Path(__file__).parent.parent.parent
from models.core import (
    BoardSession,
    ConstitutionalError,
    ConstitutionalValidation,
    Proposal,
    ProposalStatus,
)

# Local - constitutional enforcement
sys.path.insert(0, str(project_root / "constitutional_layer_immutable"))
from constitution import validate_constitutional_compliance
from owner_control.owner_gate.authorization import require_owner_approval

# Local - memory systems
sys.path.insert(0, str(project_root / "memory_systems" / "business_memory" / "memory"))
from context_builder import build_agent_context

# Local - orchestrator
sys.path.insert(0, str(project_root / "governance_layer" / "orchestrator"))
from llm_router import call_llm

logger = logging.getLogger(__name__)


# Type aliases for governance state tracking
ProposalData = Union[Proposal, Dict[str, Any]]
BoardSessionData = Optional[BoardSession]
VotingResultData = Optional[Dict[str, ProposalStatus]]


# State machine phases
class GovernancePhase:
    """Governance cycle phases."""
    IDEATION = "IDEATION"
    DELIBERATION = "DELIBERATION"
    VOTING = "VOTING"
    EXECUTION = "EXECUTION"


class GovernanceState(TypedDict, total=False):
    """
    State dictionary for governance cycle.
    
    Contains all information needed to progress through the governance cycle.
    """
    phase: str
    proposal: ProposalData
    proposal_status: ProposalStatus
    board_session: BoardSessionData
    owner_signature: Optional[str]
    owner_id: Optional[str]
    authorization_payload: Optional[Dict[str, Any]]
    context: Optional[Dict[str, Any]]
    ideation_result: Optional[Dict[str, Any]]
    deliberation_result: Optional[Dict[str, Any]]
    voting_result: VotingResultData
    execution_result: Optional[Dict[str, Any]]
    validation_results: Dict[str, ConstitutionalValidation]
    errors: list[str]


def _build_authorization_payload(owner_id: Optional[str], proposal: Dict) -> Dict:
    """Construct authorization payload for owner signature verification."""
    payload: Dict = {
        "action": "execute_decision",
        "proposal": copy.deepcopy(proposal),
    }
    if owner_id is not None:
        payload["owner_id"] = owner_id
    return payload


def conduct_ideation(state: GovernanceState) -> GovernanceState:
    """
    Conduct ideation phase of governance cycle.
    
    Builds context and generates initial proposal ideas using LLM.
    Validates proposal format after ideation.
    
    Args:
        state: Current governance state
        
    Returns:
        Updated state with ideation_result
        
    Raises:
        ConstitutionalError: If validation fails
    """
    logger.info(f"Entering IDEATION phase for proposal {state['proposal'].get('id', 'unknown')}")
    
    try:
        # Build context for ideation
        role = state.get("role", "CHAIR")
        context = build_agent_context(
            role=role,
            current_proposal=state["proposal"],
            topic_keywords=state["proposal"].get("keywords", [])
        )
        state["context"] = context
        
        # Log state entry (Rule 6)
        from utilities.logger import log_event as base_log_event
        base_log_event(
            event_type="governance_state_entry",
            data={
                "phase": GovernancePhase.IDEATION,
                "proposal_id": state["proposal"].get("id")
            },
            metadata={"function": "conduct_ideation"}
        )
        
        # Generate ideation using LLM
        ideation_prompt = (
            f"Based on the following context, generate initial ideas for this proposal:\n\n"
            f"Proposal: {state['proposal'].get('title', '')}\n"
            f"Description: {state['proposal'].get('description', '')}\n\n"
            f"Recent Activity: {context.get('recent_activity_summary', '')}\n"
            f"Relevant Precedents: {len(context.get('relevant_precedents', []))} found\n"
            f"Trend Analysis: {context.get('trend_analysis', '')[:500]}\n\n"
            f"Generate creative ideas that align with constitutional rules and maximize financial benefit."
        )
        
        ideation_response = call_llm(
            provider="openai/gpt-4o",
            prompt=ideation_prompt,
            temperature=0.8,
            max_tokens=1500
        )
        
        state["ideation_result"] = {
            "ideas": ideation_response,
            "timestamp": context["timestamp"]
        }
        
        # Constitutional validation gate: Validate proposal format
        validation = validate_constitutional_compliance(
            action={
                "type": "ideation",
                "proposal_id": state["proposal"].get("id"),
                "logged": True
            },
            context={"log_path": str(project_root / "audit_compliance" / "logs" / "events.jsonl")}
        )
        
        state["validation_results"]["ideation"] = validation
        
        if not validation.is_compliant:
            logger.error(
                f"Ideation validation failed: {validation.violated_rules}",
                extra={"proposal_id": state["proposal"].get("id")}
            )
            state["errors"].append(
                f"Ideation validation failed: {validation.violated_rules}"
            )
            raise ConstitutionalError(
                f"Rule 6 Violation: Ideation phase failed constitutional validation. "
                f"Violations: {validation.violated_rules}"
            )
        
        logger.info(f"Ideation phase completed for proposal {state['proposal'].get('id')}")
        return state
        
    except ConstitutionalError:
        raise
    except Exception as e:
        logger.error(f"Error in ideation phase: {e}", exc_info=True)
        state["errors"].append(f"Ideation error: {str(e)}")
        raise ConstitutionalError(f"Rule 6 Violation: Ideation phase failed. Error: {e}")


def conduct_deliberation(state: GovernanceState) -> GovernanceState:
    """
    Conduct deliberation phase of governance cycle.
    
    Board members deliberate on the proposal with full context.
    Validates legal/security review after deliberation.
    
    Args:
        state: Current governance state
        
    Returns:
        Updated state with deliberation_result
        
    Raises:
        ConstitutionalError: If validation fails
    """
    logger.info(f"Entering DELIBERATION phase for proposal {state['proposal'].get('id', 'unknown')}")
    
    try:
        # Build context for deliberation
        if not state.get("context"):
            role = state.get("role", "CHAIR")
            context = build_agent_context(
                role=role,
                current_proposal=state["proposal"],
                topic_keywords=state["proposal"].get("keywords", [])
            )
            state["context"] = context
        else:
            context = state["context"]
        
        # Log state entry (Rule 6)
        from utilities.logger import log_event as base_log_event
        base_log_event(
            event_type="governance_state_entry",
            data={
                "phase": GovernancePhase.DELIBERATION,
                "proposal_id": state["proposal"].get("id")
            },
            metadata={"function": "conduct_deliberation"}
        )
        
        # Conduct deliberation using LLM
        deliberation_prompt = (
            f"Deliberate on this proposal with full board context:\n\n"
            f"Proposal: {state['proposal'].get('title', '')}\n"
            f"Description: {state['proposal'].get('description', '')}\n"
            f"Financial Impact: {state['proposal'].get('financial_impact', 0)}\n"
            f"Legal Risk: {state['proposal'].get('legal_risk', 0)}\n\n"
            f"Constitutional Rules: {context.get('constitutional_rules', {})}\n"
            f"Recent Activity: {context.get('recent_activity_summary', '')[:500]}\n"
            f"Relevant Precedents: {len(context.get('relevant_precedents', []))} found\n"
            f"Trend Analysis: {context.get('trend_analysis', '')[:500]}\n\n"
            f"Provide deliberation considering: financial priority, legal protection, and board composition."
        )
        
        deliberation_response = call_llm(
            provider="anthropic/claude-3-5-sonnet-20241022",
            prompt=deliberation_prompt,
            temperature=0.7,
            max_tokens=2000
        )
        
        state["deliberation_result"] = {
            "deliberation": deliberation_response,
            "timestamp": context["timestamp"]
        }
        
        # Constitutional validation gate: Validate legal/security review
        validation = validate_constitutional_compliance(
            action={
                "type": "deliberation",
                "proposal_id": state["proposal"].get("id"),
                "logged": True,
                "legal_risk": state["proposal"].get("legal_risk", 0)
            },
            context={
                "log_path": str(project_root / "audit_compliance" / "logs" / "events.jsonl"),
                "legal_approval": state["proposal"].get("legal_approval", False)
            }
        )
        
        state["validation_results"]["deliberation"] = validation
        
        if not validation.is_compliant:
            logger.error(
                f"Deliberation validation failed: {validation.violated_rules}",
                extra={"proposal_id": state["proposal"].get("id")}
            )
            state["errors"].append(
                f"Deliberation validation failed: {validation.violated_rules}"
            )
            raise ConstitutionalError(
                f"Rule 5 Violation: Deliberation phase failed constitutional validation. "
                f"Violations: {validation.violated_rules}"
            )
        
        logger.info(f"Deliberation phase completed for proposal {state['proposal'].get('id')}")
        return state
        
    except ConstitutionalError:
        raise
    except Exception as e:
        logger.error(f"Error in deliberation phase: {e}", exc_info=True)
        state["errors"].append(f"Deliberation error: {str(e)}")
        raise ConstitutionalError(f"Rule 6 Violation: Deliberation phase failed. Error: {e}")


def conduct_voting(state: GovernanceState) -> GovernanceState:
    """
    Conduct voting phase of governance cycle.
    
    Board members vote on the proposal. Validates vote result (Rules 8, 9).
    
    Args:
        state: Current governance state
        
    Returns:
        Updated state with voting_result
        
    Raises:
        ConstitutionalError: If validation fails
    """
    logger.info(f"Entering VOTING phase for proposal {state['proposal'].get('id', 'unknown')}")
    
    try:
        # Log state entry (Rule 6)
        from utilities.logger import log_event as base_log_event
        base_log_event(
            event_type="governance_state_entry",
            data={
                "phase": GovernancePhase.VOTING,
                "proposal_id": state["proposal"].get("id")
            },
            metadata={"function": "conduct_voting"}
        )
        
        # Simulate voting (in full implementation, this would call board members)
        # For now, create a mock voting result
        votes = state.get("votes", {})
        if not votes:
            # Default votes for testing
            votes = {
                "member1": 0.20,
                "member2": 0.20,
                "member3": 0.20,
                "member4": 0.20,
                "member5": 0.20
            }
        
        state["voting_result"] = {
            "votes": votes,
            "timestamp": state.get("context", {}).get("timestamp", "")
        }
        
        # Constitutional validation gate: Validate vote result (Rules 8, 9)
        from models.core import VoteResult, create_vote_result
        
        try:
            vote_result = create_vote_result(
                session_id=state.get("session_id", "default_session"),
                proposal_id=state["proposal"].get("id"),
                votes=votes
            )
            
            validation = validate_constitutional_compliance(
                vote_result=vote_result,
                context={"log_path": str(project_root / "audit_compliance" / "logs" / "events.jsonl")}
            )
            
            state["validation_results"]["voting"] = validation
            
            if not validation.is_compliant:
                logger.error(
                    f"Voting validation failed: {validation.violated_rules}",
                    extra={"proposal_id": state["proposal"].get("id")}
                )
                state["errors"].append(
                    f"Voting validation failed: {validation.violated_rules}"
                )
                raise ConstitutionalError(
                    f"Rule 8/9 Violation: Voting phase failed constitutional validation. "
                    f"Violations: {validation.violated_rules}"
                )
        except ConstitutionalError:
            raise
        except Exception as e:
            logger.error(f"Vote result validation error: {e}", exc_info=True)
            raise ConstitutionalError(f"Rule 8/9 Violation: Vote result invalid. Error: {e}")
        
        logger.info(f"Voting phase completed for proposal {state['proposal'].get('id')}")
        return state
        
    except ConstitutionalError:
        raise
    except Exception as e:
        logger.error(f"Error in voting phase: {e}", exc_info=True)
        state["errors"].append(f"Voting error: {str(e)}")
        raise ConstitutionalError(f"Rule 6 Violation: Voting phase failed. Error: {e}")


@require_owner_approval("execute_decision")
def execute_decision(state: GovernanceState) -> GovernanceState:
    """
    Execute decision phase of governance cycle.
    
    Executes the approved decision. Validates owner signature (Rule 10) before execution.
    
    Args:
        state: Current governance state
        
    Returns:
        Updated state with execution_result
        
    Raises:
        ConstitutionalError: If validation fails
    """
    logger.info(f"Entering EXECUTION phase for proposal {state['proposal'].get('id', 'unknown')}")
    
    try:
        # Log state entry (Rule 6)
        from utilities.logger import log_event as base_log_event
        base_log_event(
            event_type="governance_state_entry",
            data={
                "phase": GovernancePhase.EXECUTION,
                "proposal_id": state["proposal"].get("id")
            },
            metadata={"function": "execute_decision"}
        )
        
        validation = validate_constitutional_compliance(
            action={
                "type": "execute",
                "proposal_id": state["proposal"].get("id"),
                "owner_authorized": True,
                "logged": True
            },
            context={"log_path": str(project_root / "audit_compliance" / "logs" / "events.jsonl")}
        )
        
        state["validation_results"]["execution"] = validation
        
        if not validation.is_compliant:
            logger.error(
                f"Execution validation failed: {validation.violated_rules}",
                extra={"proposal_id": state["proposal"].get("id")}
            )
            state["errors"].append(
                f"Execution validation failed: {validation.violated_rules}"
            )
            raise ConstitutionalError(
                f"Rule 10 Violation: Execution phase failed constitutional validation. "
                f"Violations: {validation.violated_rules}"
            )
        
        # Execute decision (placeholder - actual execution logic would go here)
        state["execution_result"] = {
            "status": "executed",
            "timestamp": state.get("context", {}).get("timestamp", ""),
            "proposal_id": state["proposal"].get("id")
        }
        
        logger.info(f"Execution phase completed for proposal {state['proposal'].get('id')}")
        return state
        
    except ConstitutionalError:
        raise
    except Exception as e:
        logger.error(f"Error in execution phase: {e}", exc_info=True)
        state["errors"].append(f"Execution error: {str(e)}")
        raise ConstitutionalError(f"Rule 6 Violation: Execution phase failed. Error: {e}")


def run_governance_cycle(
    proposal: Dict,
    owner_signature: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> Dict:
    """
    Execute full governance cycle through state machine.
    
    Progresses through: IDEATION → DELIBERATION → VOTING → EXECUTION
    At each state: builds context, logs entry/exit, validates constitutional compliance.
    
    Args:
        proposal: Dictionary containing proposal details
        owner_signature: Optional owner signature for execution phase
        owner_id: Optional owner identifier associated with the signature
        
    Returns:
        Complete session dictionary with all results
        
    Raises:
        ConstitutionalError: If any gate fails
        
    Example:
        >>> session = run_governance_cycle(
        ...     proposal={"id": "prop1", "title": "New Feature"},
        ...     owner_signature="valid_signature"
        ... )
        >>> assert session["execution_result"]["status"] == "executed"
    """
    logger.info(f"Starting governance cycle for proposal {proposal.get('id', 'unknown')}")
    
    # Initialize state
    authorization_payload = _build_authorization_payload(owner_id, proposal)

    initial_state: GovernanceState = {
        "phase": GovernancePhase.IDEATION,
        "proposal": proposal,
        "owner_signature": owner_signature,
        "owner_id": owner_id,
        "authorization_payload": authorization_payload,
        "context": None,
        "ideation_result": None,
        "deliberation_result": None,
        "voting_result": None,
        "execution_result": None,
        "validation_results": {},
        "errors": []
    }
    
    # Build state machine
    workflow = StateGraph(GovernanceState)
    
    # Add nodes
    workflow.add_node(GovernancePhase.IDEATION, conduct_ideation)
    workflow.add_node(GovernancePhase.DELIBERATION, conduct_deliberation)
    workflow.add_node(GovernancePhase.VOTING, conduct_voting)
    workflow.add_node(GovernancePhase.EXECUTION, execute_decision)
    
    # Add edges
    workflow.set_entry_point(GovernancePhase.IDEATION)
    workflow.add_edge(GovernancePhase.IDEATION, GovernancePhase.DELIBERATION)
    workflow.add_edge(GovernancePhase.DELIBERATION, GovernancePhase.VOTING)
    workflow.add_edge(GovernancePhase.VOTING, GovernancePhase.EXECUTION)
    workflow.add_edge(GovernancePhase.EXECUTION, END)
    
    # Compile and run
    app = workflow.compile()
    
    try:
        # Run state machine
        final_state = app.invoke(initial_state)
        
        # Log completion (Rule 6)
        from utilities.logger import log_event as base_log_event
        base_log_event(
            event_type="governance_cycle_complete",
            data={
                "proposal_id": proposal.get("id"),
                "phases_completed": [
                    GovernancePhase.IDEATION,
                    GovernancePhase.DELIBERATION,
                    GovernancePhase.VOTING,
                    GovernancePhase.EXECUTION
                ],
                "errors": final_state.get("errors", [])
            },
            metadata={"function": "run_governance_cycle"}
        )
        
        logger.info(f"Governance cycle completed for proposal {proposal.get('id')}")
        return final_state
        
    except ConstitutionalError:
        raise
    except Exception as e:
        logger.error(f"Governance cycle failed: {e}", exc_info=True)
        raise ConstitutionalError(
            f"Rule 6 Violation: Governance cycle failed. Error: {e}"
        )


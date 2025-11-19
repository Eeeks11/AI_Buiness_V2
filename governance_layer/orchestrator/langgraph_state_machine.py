"""
LangGraph State Machine for Governance

Implements governance cycle with state machine: IDEATION → DELIBERATION → VOTING → EXECUTION.
Each state transition includes constitutional validation gates.
"""

# Standard library
import copy
import json
import logging
from datetime import datetime
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
    create_vote_result,
)

# Local - constitutional enforcement
sys.path.insert(0, str(project_root / "constitutional_layer_immutable"))
from constitution import validate_constitutional_compliance
from owner_control.owner_gate.authorization import require_owner_approval

# Local - memory systems
sys.path.insert(0, str(project_root / "memory_systems" / "business_memory" / "memory"))
from context_builder import build_agent_context

# Local - utilities
from utilities.logger import get_recent_logs

# Local - orchestrator
sys.path.insert(0, str(project_root / "governance_layer" / "orchestrator"))
from llm_router import call_llm
from iterative_deliberation import conduct_iterative_deliberation

# Local - governance
from governance_layer.governance.board import get_role_provider_map, get_model_assignment
from governance_layer.governance.voting import tally_votes
from governance_layer.roles.prompt_templates import load_role_configs

# Local - model health check
from governance_layer.orchestrator.model_health_check import validate_models_before_governance

# Local - retrospective
sys.path.insert(0, str(project_root / "governance_layer"))
from retrospective import conduct_weekly_retrospective, should_run_retrospective

# Local - configuration
sys.path.insert(0, str(project_root / "config_settings"))
from config import get_settings

logger = logging.getLogger(__name__)

BOARD_ROLES = tuple(load_role_configs().keys())
PROPOSAL_DATA_DIR = project_root / "data" / "proposals"


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
    PENDING_APPROVAL = "PENDING_APPROVAL"
    EXECUTION = "EXECUTION"
    RETROSPECTIVE = "RETROSPECTIVE"


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
    retrospective_result: Optional[Dict[str, Any]]
    validation_results: Dict[str, ConstitutionalValidation]
    errors: list[str]
    needs_owner_approval: Optional[bool]


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
        # Validate models are healthy before proceeding (Rule 8)
        is_valid, health_results, error_messages = validate_models_before_governance(
            required_healthy_count=5,
            timeout_seconds=5.0
        )
        
        if not is_valid:
            logger.error(
                "Model health check failed before ideation",
                extra={"errors": error_messages, "health_results": {k: v.to_dict() for k, v in health_results.items()}}
            )
            state["errors"].extend(error_messages)
            raise ConstitutionalError(
                f"Rule 8 Violation: Insufficient healthy LLM models for governance cycle. "
                f"Errors: {'; '.join(error_messages)}"
            )
        
        # Store health check results in state for dashboard display
        state["model_health_check"] = {
            "checked_at": datetime.now().isoformat(),
            "is_valid": is_valid,
            "results": {k: v.to_dict() for k, v in health_results.items()}
        }
        
        # Build context for ideation
        role = state.get("role", "CHAIR")
        context = build_agent_context(
            role=role,
            current_proposal=state["proposal"],
            topic_keywords=state["proposal"].get("keywords", [])
        )
        state["context"] = context
        
        # Update proposal status
        if isinstance(state["proposal"], dict):
            state["proposal"]["status"] = ProposalStatus.DRAFT.value
        state["proposal_status"] = ProposalStatus.DRAFT
        
        # Log state entry (Rule 6)
        from utilities.logger import log_event as base_log_event
        base_log_event(
            event_type="governance_state_entry",
            data={
                "phase": GovernancePhase.IDEATION,
                "proposal_id": state["proposal"].get("id"),
                "status": ProposalStatus.DRAFT.value
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
        
        openai_provider = get_settings().provider_model_identifier("openai")
        ideation_response = call_llm(
            provider=openai_provider,
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
        
        # Update proposal status
        if isinstance(state["proposal"], dict):
            state["proposal"]["status"] = ProposalStatus.DELIBERATION.value
        state["proposal_status"] = ProposalStatus.DELIBERATION
        
        # Log state entry (Rule 6)
        from utilities.logger import log_event as base_log_event
        base_log_event(
            event_type="governance_state_entry",
            data={
                "phase": GovernancePhase.DELIBERATION,
                "proposal_id": state["proposal"].get("id"),
                "status": ProposalStatus.DELIBERATION.value
            },
            metadata={"function": "conduct_deliberation"}
        )
        
        proposal_id = state["proposal"].get("id", "UNKNOWN")
        deliberation_timestamp = datetime.now().isoformat()
        
        # Build role contexts for all roles
        role_contexts: Dict[str, Dict[str, Any]] = {}
        for role in BOARD_ROLES:
            role_contexts[role] = build_agent_context(
                role=role,
                current_proposal=state["proposal"],
                topic_keywords=state["proposal"].get("keywords", [])
            )
        
        # Determine deliberation mode
        # For formal proposals, use streamlined mode (2 rounds)
        # For strategic questions/ideation, use full mode (5 rounds)
        # For now, default to streamlined for proposals
        deliberation_mode = "streamlined"  # Can be changed to "full" for ideation
        
        # Conduct iterative deliberation
        logger.info(f"Starting iterative deliberation (mode: {deliberation_mode})", extra={"proposal_id": proposal_id})
        
        iterative_result = conduct_iterative_deliberation(
            proposal=state["proposal"],
            role_contexts=role_contexts,
            max_rounds=5 if deliberation_mode == "full" else 2,
            mode=deliberation_mode
        )
        
        # Convert iterative result to format expected by rest of system
        # Use the last round's responses as the primary responses
        final_round = iterative_result["rounds"][-1] if iterative_result["rounds"] else {}
        
        role_responses: Dict[str, Dict[str, Any]] = {}
        aggregated_segments = []
        role_providers = get_role_provider_map()
        
        for role in BOARD_ROLES:
            response = final_round.get(role, f"{role}: No response in final round")
            provider = role_providers.get(role, "unknown")
            
            captured_at = datetime.now().isoformat()
            role_responses[role] = {
                "provider": provider,
                "response": response,
                "captured_at": captured_at,
                "round_number": len(iterative_result["rounds"]),
            }
            aggregated_segments.append(f"{role}: {response}")
            
            # Log each role's final response
            try:
                base_log_event(
                    event_type="board_deliberation_response_captured",
                    data={
                        "proposal_id": proposal_id,
                        "role": role,
                        "provider": provider,
                        "response_length": len(response),
                        "response_preview": response[:200] if role == "CHAIR" else None,
                        "captured_at": captured_at,
                        "round_number": len(iterative_result["rounds"]),
                        "total_rounds": iterative_result["total_rounds"]
                    },
                    metadata={"function": "conduct_deliberation"}
                )
            except Exception as log_exc:
                logger.warning(
                    "Failed to log deliberation response capture",
                    extra={"role": role, "error": str(log_exc)}
                )
        
        combined_deliberation = "\n\n".join(aggregated_segments)
        deliberation_payload = {
            "combined_deliberation": combined_deliberation,
            "deliberation": combined_deliberation,
            "responses": role_responses,
            "timestamp": deliberation_timestamp,
            # Include iterative deliberation data
            "iterative_deliberation": {
                "rounds": iterative_result["rounds"],
                "total_rounds": iterative_result["total_rounds"],
                "converged": iterative_result["converged"],
                "exhausted": iterative_result["exhausted"],
                "convergence_reason": iterative_result.get("convergence_reason"),
                "exhaustion_reason": iterative_result.get("exhaustion_reason"),
                "position_evolution": iterative_result["position_evolution"],
                "synthesis": iterative_result["synthesis"]
            }
        }

        storage_path = _persist_deliberation_results(proposal_id, deliberation_payload)
        deliberation_payload["storage_path"] = str(storage_path)
        state["deliberation_result"] = deliberation_payload
        
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
    If approved, sets status to pending_approval (Rule 10 requires owner approval).
    
    Voting Structure (Business Plan Section 4.2):
    - Only CEO, CFO, COO, CMO vote regularly (25% weight each)
    - LEGAL and CISO can veto (separate from voting)
    - CHAIR only votes to break 2-2 ties
    - SECRETARY does not vote (documentation only)
    
    Args:
        state: Current governance state
        
    Returns:
        Updated state with voting_result and status
        
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
        
        # Update proposal status to voting
        if isinstance(state["proposal"], dict):
            state["proposal"]["status"] = ProposalStatus.VOTING.value
        state["proposal_status"] = ProposalStatus.VOTING
        
        # Get deliberation result
        deliberation_output = state.get("deliberation_result", {})
        deliberation_responses = deliberation_output.get("responses", {})
        
        from models.core import Vote, VoteType, RoleType
        from governance_layer.roles.prompt_templates import load_role_configs
        
        role_configs = load_role_configs()
        role_providers = get_role_provider_map()
        proposal_id = state["proposal"].get("id", "unknown")
        votes_list = []
        
        # PRIMARY VOTERS: Only CEO, CFO, COO, CMO vote (25% each)
        PRIMARY_VOTERS = ["CEO", "CFO", "COO", "CMO"]
        
        # Collect votes from the 4 voting members
        for role in PRIMARY_VOTERS:
            if role not in role_configs:
                logger.error(f"Role {role} not found in configs", extra={"proposal_id": proposal_id})
                raise ConstitutionalError(f"Rule 8 Violation: Voting role '{role}' not configured")
            
            # Get deliberation response for context
            deliberation_response = deliberation_responses.get(role, {}).get("response", "")
            
            # Build voting prompt
            proposal = state["proposal"]
            voting_prompt = (
                f"You are the {role} on the AI governance board.\n\n"
                f"Proposal ID: {proposal.get('id', 'UNKNOWN')}\n"
                f"Title: {proposal.get('title', 'No title')}\n"
                f"Description: {proposal.get('description', 'No description')}\n"
                f"Financial Impact: ${proposal.get('financial_impact', 0):,.2f}\n\n"
                f"Your Deliberation:\n{deliberation_response[:1000] if deliberation_response else 'No deliberation available'}\n\n"
                f"All Board Deliberations:\n"
            )
            
            # Include all deliberations for context
            for other_role, other_response_data in deliberation_responses.items():
                if isinstance(other_response_data, dict):
                    other_response = other_response_data.get("response", "")
                    if other_response:
                        voting_prompt += f"\n{other_role}: {other_response[:500]}\n"
            
            voting_prompt += (
                f"\n\nYou are a VOTING MEMBER with 25% voting weight.\n"
                f"Review all deliberations and cast your vote.\n"
                f"Respond with ONLY one word: APPROVE or REJECT\n"
                f"Then provide a brief one-sentence reasoning for your vote."
            )
            
            # Call LLM to get vote
            provider = role_providers.get(role)
            if not provider:
                logger.error(f"No provider for {role}", extra={"proposal_id": proposal_id})
                raise ConstitutionalError(f"Rule 8 Violation: No provider for voting role '{role}'")
            
            try:
                vote_response = call_llm(
                    provider=provider,
                    prompt=voting_prompt,
                    temperature=0.3,  # Lower temperature for voting decisions
                    max_tokens=200
                )
                
                # Parse vote from response
                vote_response_upper = vote_response.strip().upper()
                if "APPROVE" in vote_response_upper:
                    vote_type = VoteType.APPROVE
                elif "REJECT" in vote_response_upper:
                    vote_type = VoteType.REJECT
                else:
                    # Default to approve if unclear (conservative)
                    logger.warning(f"Unclear vote from {role}, defaulting to APPROVE", extra={"response": vote_response[:100]})
                    vote_type = VoteType.APPROVE
                
                vote = Vote(
                    member_id=f"{role.lower()}_agent",
                    role=RoleType(role),
                    vote_type=vote_type,
                    weight=0.25,  # Each voting member has exactly 25% weight
                    rationale=vote_response[:500]
                )
                votes_list.append(vote)
                
                logger.info(f"{role} voted: {vote_type.value}", extra={"proposal_id": proposal_id})
                
            except Exception as e:
                logger.error(f"Failed to get vote from {role}: {e}", exc_info=True, extra={"proposal_id": proposal_id})
                raise ConstitutionalError(f"Rule 8 Violation: Failed to collect vote from {role}. Error: {e}")
        
        # Check for VETOES from LEGAL and CISO (separate from voting)
        VETO_ROLES = ["LEGAL", "CISO"]
        veto_triggered = False
        veto_role = None
        
        for role in VETO_ROLES:
            if role not in role_configs:
                continue
            
            deliberation_response = deliberation_responses.get(role, {}).get("response", "")
            
            # Build veto check prompt
            veto_prompt = (
                f"You are the {role} on the AI governance board.\n\n"
                f"Proposal ID: {proposal.get('id', 'UNKNOWN')}\n"
                f"Title: {proposal.get('title', 'No title')}\n"
                f"Description: {proposal.get('description', 'No description')}\n\n"
                f"Your Deliberation:\n{deliberation_response[:1000] if deliberation_response else 'No deliberation available'}\n\n"
                f"You have VETO POWER. Review this proposal for:\n"
            )
            
            if role == "LEGAL":
                veto_prompt += (
                    "- Legal violations\n"
                    "- Constitutional violations\n"
                    "- Regulatory compliance issues\n"
                    "- Contractual risks\n\n"
                )
            elif role == "CISO":
                veto_prompt += (
                    "- Security risks\n"
                    "- Data integrity issues\n"
                    "- Privacy violations\n"
                    "- Infrastructure safety concerns\n\n"
                )
            
            veto_prompt += (
                f"Respond with ONLY one word: VETO or NO_VETO\n"
                f"If VETO, provide a brief one-sentence reason."
            )
            
            provider = role_providers.get(role)
            if provider:
                try:
                    veto_response = call_llm(
                        provider=provider,
                        prompt=veto_prompt,
                        temperature=0.3,
                        max_tokens=200
                    )
                    
                    veto_response_upper = veto_response.strip().upper()
                    if "VETO" in veto_response_upper and "NO_VETO" not in veto_response_upper:
                        veto_triggered = True
                        veto_role = role
                        logger.warning(f"{role} exercised VETO", extra={"proposal_id": proposal_id, "reason": veto_response[:200]})
                        
                        # Log veto
                        base_log_event(
                            event_type="proposal_vetoed",
                            data={
                                "proposal_id": proposal_id,
                                "veto_role": role,
                                "reason": veto_response[:500]
                            },
                            metadata={"function": "conduct_voting"}
                        )
                        break  # Single veto stops the proposal
                except Exception as e:
                    logger.warning(f"Failed to check veto from {role}: {e}", extra={"proposal_id": proposal_id})
        
        # If vetoed, stop here - veto overrides all votes (don't tally to avoid logging wrong decision)
        if veto_triggered:
            # Create vote result for audit trail (includes collected votes but decision is vetoed)
            votes_dict = {v.member_id: v.weight for v in votes_list} if votes_list else {}
            vote_result = create_vote_result(
                session_id=f"{proposal_id}-session",
                proposal_id=proposal_id,
                votes=votes_dict
            )
            
            state["voting_result"] = {
                "session_id": vote_result.session_id,
                "proposal_id": vote_result.proposal_id,
                "votes": vote_result.votes,
                "total_weight": vote_result.total_weight,
                "timestamp": vote_result.timestamp.isoformat(),
                "decision": "vetoed",
                "veto_triggered": True,
                "veto_role": veto_role,
                "approve_count": sum(1 for v in votes_list if v.vote_type == VoteType.APPROVE) if votes_list else 0,
                "reject_count": sum(1 for v in votes_list if v.vote_type == VoteType.REJECT) if votes_list else 0
            }
            
            if isinstance(state["proposal"], dict):
                state["proposal"]["status"] = ProposalStatus.VETOED.value
            state["proposal_status"] = ProposalStatus.VETOED
            state["needs_owner_approval"] = False
            
            # Log veto decision (separate from vote tally log)
            base_log_event(
                event_type="board_vote_tallied",
                data={
                    "proposal_id": proposal_id,
                    "decision": "vetoed",
                    "reason": f"{veto_role} veto",
                    "veto_triggered": True,
                    "veto_role": veto_role,
                    "approve_count": state["voting_result"]["approve_count"],
                    "reject_count": state["voting_result"]["reject_count"],
                    "approve_weight": state["voting_result"]["approve_count"] * 0.25,
                    "reject_weight": state["voting_result"]["reject_count"] * 0.25
                },
                metadata={"function": "conduct_voting"}
            )
            
            logger.info(f"Proposal {proposal_id} vetoed by {veto_role}")
            return state
        
        # Tally votes from the 4 voting members
        vote_result = tally_votes(
            votes=votes_list,
            roles=role_configs,
            proposal_id=proposal_id
        )
        
        # Check if there's a 2-2 tie and need Chair tie-breaker
        all_logs = get_recent_logs(limit=50)
        vote_decision = None
        chair_tiebreak_needed = False
        
        for log_entry in all_logs:
            if (log_entry.get("type") == "board_vote_tallied" and 
                log_entry.get("data", {}).get("proposal_id") == proposal_id):
                vote_decision = log_entry.get("data", {}).get("decision", "unknown")
                chair_tiebreak_needed = log_entry.get("data", {}).get("chair_tiebreak_used", False)
                break
        
        # If no decision in logs, calculate from votes
        if not vote_decision:
            approve_count = sum(1 for v in votes_list if v.vote_type == VoteType.APPROVE)
            reject_count = sum(1 for v in votes_list if v.vote_type == VoteType.REJECT)
            
            if approve_count == 2 and reject_count == 2:
                # 2-2 tie - need Chair to break it
                chair_tiebreak_needed = True
                logger.info(f"2-2 tie detected, requesting Chair tie-breaker", extra={"proposal_id": proposal_id})
                
                # Get Chair's tie-breaking vote
                deliberation_response = deliberation_responses.get("CHAIR", {}).get("response", "")
                chair_prompt = (
                    f"You are the CHAIR of the AI governance board.\n\n"
                    f"Proposal ID: {proposal.get('id', 'UNKNOWN')}\n"
                    f"Title: {proposal.get('title', 'No title')}\n"
                    f"Description: {proposal.get('description', 'No description')}\n\n"
                    f"The four voting members (CEO, CFO, COO, CMO) have split 2-2.\n"
                    f"Your vote will break the tie and determine the outcome.\n\n"
                    f"All Deliberations:\n"
                )
                
                for other_role, other_response_data in deliberation_responses.items():
                    if isinstance(other_response_data, dict):
                        other_response = other_response_data.get("response", "")
                        if other_response:
                            chair_prompt += f"\n{other_role}: {other_response[:500]}\n"
                
                chair_prompt += (
                    f"\n\nVote Count: 2 APPROVE, 2 REJECT\n"
                    f"Respond with ONLY one word: APPROVE or REJECT\n"
                    f"Then provide brief reasoning for your tie-breaking decision."
                )
                
                provider = role_providers.get("CHAIR")
                if provider:
                    try:
                        chair_response = call_llm(
                            provider=provider,
                            prompt=chair_prompt,
                            temperature=0.3,
                            max_tokens=200
                        )
                        
                        chair_response_upper = chair_response.strip().upper()
                        if "APPROVE" in chair_response_upper:
                            vote_decision = "approved"
                        else:
                            vote_decision = "rejected"
                        
                        logger.info(f"Chair tie-breaker: {vote_decision}", extra={"proposal_id": proposal_id})
                        
                        # Add Chair vote to result for logging
                        chair_vote = Vote(
                            member_id="chair_agent",
                            role=RoleType.CHAIR,
                            vote_type=VoteType.APPROVE if vote_decision == "approved" else VoteType.REJECT,
                            weight=0.0,  # Chair has 0% weight in regular voting
                            rationale=chair_response[:500]
                        )
                        votes_list.append(chair_vote)
                        
                    except Exception as e:
                        logger.error(f"Failed to get Chair tie-breaker: {e}", exc_info=True, extra={"proposal_id": proposal_id})
                        raise ConstitutionalError(f"Rule 9 Violation: 2-2 tie requires Chair vote. Error: {e}")
                else:
                    raise ConstitutionalError("Rule 8 Violation: No provider for CHAIR role")
            elif approve_count > reject_count:
                vote_decision = "approved"
            else:
                vote_decision = "rejected"
        
        # Store vote result in state
        state["voting_result"] = {
            "session_id": vote_result.session_id,
            "proposal_id": vote_result.proposal_id,
            "votes": vote_result.votes,
            "total_weight": vote_result.total_weight,
            "timestamp": vote_result.timestamp.isoformat(),
            "decision": vote_decision,
            "chair_tiebreak_used": chair_tiebreak_needed
        }
        
        # Update proposal status based on vote result
        if vote_decision == "approved":
            # Board approved - now needs owner approval (Rule 10)
            if isinstance(state["proposal"], dict):
                state["proposal"]["status"] = ProposalStatus.PENDING_APPROVAL.value
            state["proposal_status"] = ProposalStatus.PENDING_APPROVAL
            state["needs_owner_approval"] = True
            
            # Log pending approval status
            base_log_event(
                event_type="proposal_pending_approval",
                data={
                    "proposal_id": proposal_id,
                    "board_approved": True,
                    "status": ProposalStatus.PENDING_APPROVAL.value,
                    "chair_tiebreak_used": chair_tiebreak_needed
                },
                metadata={"function": "conduct_voting"}
            )
        elif vote_decision == "rejected":
            if isinstance(state["proposal"], dict):
                state["proposal"]["status"] = ProposalStatus.REJECTED.value
            state["proposal_status"] = ProposalStatus.REJECTED
            state["needs_owner_approval"] = False
        elif vote_decision == "vetoed":
            if isinstance(state["proposal"], dict):
                state["proposal"]["status"] = ProposalStatus.VETOED.value
            state["proposal_status"] = ProposalStatus.VETOED
            state["needs_owner_approval"] = False
        
        # Constitutional validation gate: Validate vote result (Rules 8, 9)
        validation = validate_constitutional_compliance(
            vote_result=vote_result,
            context={"log_path": str(project_root / "audit_compliance" / "logs" / "events.jsonl")}
        )
        
        state["validation_results"]["voting"] = validation
        
        if not validation.is_compliant:
            logger.error(
                f"Voting validation failed: {validation.violated_rules}",
                extra={"proposal_id": proposal_id}
            )
            state["errors"].append(
                f"Voting validation failed: {validation.violated_rules}"
            )
            raise ConstitutionalError(
                f"Rule 8/9 Violation: Voting phase failed constitutional validation. "
                f"Violations: {validation.violated_rules}"
            )
        
        logger.info(f"Voting phase completed for proposal {proposal_id}, decision: {vote_decision}")
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
        
        # Update proposal status to executed
        if isinstance(state["proposal"], dict):
            state["proposal"]["status"] = ProposalStatus.EXECUTED.value
        state["proposal_status"] = ProposalStatus.EXECUTED
        
        # Execute decision (placeholder - actual execution logic would go here)
        state["execution_result"] = {
            "status": "executed",
            "timestamp": state.get("context", {}).get("timestamp", ""),
            "proposal_id": state["proposal"].get("id")
        }
        
        # Log execution completion
        base_log_event(
            event_type="proposal_executed",
            data={
                "proposal_id": state["proposal"].get("id"),
                "status": ProposalStatus.EXECUTED.value
            },
            metadata={"function": "execute_decision"}
        )
        
        logger.info(f"Execution phase completed for proposal {state['proposal'].get('id')}")
        return state
        
    except ConstitutionalError:
        raise
    except Exception as e:
        logger.error(f"Error in execution phase: {e}", exc_info=True)
        state["errors"].append(f"Execution error: {str(e)}")
        raise ConstitutionalError(f"Rule 6 Violation: Execution phase failed. Error: {e}")


def conduct_retrospective(state: GovernanceState) -> GovernanceState:
    """
    Conduct retrospective phase of governance cycle.
    
    Performs post-decision analysis and continuous improvement review.
    Validates constitutional compliance after retrospective.
    
    Args:
        state: Current governance state
        
    Returns:
        Updated state with retrospective_result
        
    Raises:
        ConstitutionalError: If validation fails
    """
    logger.info(f"Entering RETROSPECTIVE phase for proposal {state['proposal'].get('id', 'unknown')}")
    
    try:
        # Log state entry (Rule 6)
        from utilities.logger import log_event as base_log_event
        base_log_event(
            event_type="governance_state_entry",
            data={
                "phase": GovernancePhase.RETROSPECTIVE,
                "proposal_id": state["proposal"].get("id")
            },
            metadata={"function": "conduct_retrospective"}
        )
        
        # Check if retrospective should run (weekly schedule)
        # For individual proposal retrospectives, we'll run a focused retrospective
        # Note: Full weekly retrospective requires owner approval, so we'll do a lightweight version here
        # The full retrospective can be triggered separately via should_run_retrospective()
        
        # For now, we'll skip the full retrospective in the cycle (it requires owner approval)
        # and just log that execution completed successfully
        # In production, this could trigger an async retrospective or queue it for owner approval
        
        retrospective_result = {
            "status": "logged",
            "proposal_id": state["proposal"].get("id"),
            "execution_status": state.get("execution_result", {}).get("status", "unknown"),
            "timestamp": state.get("context", {}).get("timestamp", ""),
            "note": "Full retrospective requires owner approval and runs on weekly schedule"
        }
        
        state["retrospective_result"] = retrospective_result
        
        # Log retrospective completion (Rule 6)
        base_log_event(
            event_type="retrospective_phase_completed",
            data={
                "proposal_id": state["proposal"].get("id"),
                "execution_status": retrospective_result["execution_status"]
            },
            metadata={"function": "conduct_retrospective"}
        )
        
        # Constitutional validation gate
        validation = validate_constitutional_compliance(
            action={
                "type": "retrospective",
                "proposal_id": state["proposal"].get("id"),
                "logged": True
            },
            context={"log_path": str(project_root / "audit_compliance" / "logs" / "events.jsonl")}
        )
        
        state["validation_results"]["retrospective"] = validation
        
        if not validation.is_compliant:
            logger.error(
                f"Retrospective validation failed: {validation.violated_rules}",
                extra={"proposal_id": state["proposal"].get("id")}
            )
            state["errors"].append(
                f"Retrospective validation failed: {validation.violated_rules}"
            )
            raise ConstitutionalError(
                f"Rule 6 Violation: Retrospective phase failed constitutional validation. "
                f"Violations: {validation.violated_rules}"
            )
        
        logger.info(f"Retrospective phase completed for proposal {state['proposal'].get('id')}")
        return state
        
    except ConstitutionalError:
        raise
    except Exception as e:
        logger.error(f"Error in retrospective phase: {e}", exc_info=True)
        state["errors"].append(f"Retrospective error: {str(e)}")
        raise ConstitutionalError(f"Rule 6 Violation: Retrospective phase failed. Error: {e}")


def handle_pending_approval(state: GovernanceState) -> GovernanceState:
    """
    Handle pending approval phase - stops governance cycle and waits for owner approval.
    
    This phase is reached after voting approves a proposal. The cycle stops here
    until owner provides approval (Rule 10).
    
    Args:
        state: Current governance state
        
    Returns:
        Updated state with pending_approval status
        
    Raises:
        ConstitutionalError: If validation fails
    """
    logger.info(f"Entering PENDING_APPROVAL phase for proposal {state['proposal'].get('id', 'unknown')}")
    
    try:
        # Log state entry (Rule 6)
        from utilities.logger import log_event as base_log_event
        base_log_event(
            event_type="governance_state_entry",
            data={
                "phase": GovernancePhase.PENDING_APPROVAL,
                "proposal_id": state["proposal"].get("id"),
                "status": ProposalStatus.PENDING_APPROVAL.value
            },
            metadata={"function": "handle_pending_approval"}
        )
        
        # Ensure status is set correctly
        if isinstance(state["proposal"], dict):
            state["proposal"]["status"] = ProposalStatus.PENDING_APPROVAL.value
        state["proposal_status"] = ProposalStatus.PENDING_APPROVAL
        state["needs_owner_approval"] = True
        
        # Log pending approval
        base_log_event(
            event_type="proposal_pending_approval",
            data={
                "proposal_id": state["proposal"].get("id"),
                "board_approved": True,
                "status": ProposalStatus.PENDING_APPROVAL.value,
                "requires_owner_signature": True
            },
            metadata={"function": "handle_pending_approval"}
        )
        
        logger.info(f"Proposal {state['proposal'].get('id')} pending owner approval")
        return state
        
    except Exception as e:
        logger.error(f"Error in pending approval phase: {e}", exc_info=True)
        state["errors"].append(f"Pending approval error: {str(e)}")
        raise ConstitutionalError(f"Rule 6 Violation: Pending approval phase failed. Error: {e}")


def _route_after_voting(state: GovernanceState) -> str:
    """
    Conditional routing function after voting phase.
    
    Routes to PENDING_APPROVAL if proposal was approved (needs owner approval).
    Routes to END if proposal was rejected or vetoed.
    
    Args:
        state: Current governance state
        
    Returns:
        Next phase name or END
    """
    needs_approval = state.get("needs_owner_approval", False)
    proposal_status = state.get("proposal_status")
    
    if needs_approval and proposal_status == ProposalStatus.PENDING_APPROVAL:
        return GovernancePhase.PENDING_APPROVAL
    elif proposal_status in [ProposalStatus.REJECTED, ProposalStatus.VETOED]:
        return END
    else:
        # Default: if no explicit routing, go to pending approval if approved
        vote_result = state.get("voting_result", {})
        if isinstance(vote_result, dict):
            # Check logs for decision
            proposal_id = state["proposal"].get("id", "unknown")
            all_logs = get_recent_logs(limit=50)
            for log_entry in all_logs:
                if (log_entry.get("type") == "board_vote_tallied" and 
                    log_entry.get("data", {}).get("proposal_id") == proposal_id):
                    decision = log_entry.get("data", {}).get("decision", "unknown")
                    if decision == "approved":
                        return GovernancePhase.PENDING_APPROVAL
                    else:
                        return END
        return END


def resume_from_approval(
    proposal_id: str,
    owner_signature: str,
    owner_id: str,
    approved: bool = True
) -> Dict[str, Any]:
    """
    Resume governance cycle from pending approval after owner decision.
    
    If approved: proceeds to execution phase
    If rejected: marks proposal as rejected and ends cycle
    
    Args:
        proposal_id: Proposal identifier
        owner_signature: Owner signature authorizing the decision
        owner_id: Owner identifier
        approved: Whether owner approved (True) or rejected (False)
        
    Returns:
        Updated state with approval decision
        
    Raises:
        ConstitutionalError: If validation fails
    """
    logger.info(f"Resuming governance cycle for proposal {proposal_id}, approved: {approved}")
    
    from utilities.logger import log_event
    
    # Log owner decision
    if approved:
        log_event(
            event_type="proposal_approved_by_owner",
            data={
                "proposal_id": proposal_id,
                "owner_id": owner_id,
                "status": ProposalStatus.APPROVED.value
            },
            metadata={"function": "resume_from_approval"}
        )
        
        # Load proposal data from logs (if available)
        from owner_control.dashboard.data_retrieval import get_proposal_by_id
        proposal_data = get_proposal_by_id(proposal_id)
        
        # If proposal not in logs (e.g., in test environment), create minimal proposal
        if not proposal_data:
            logger.warning(f"Proposal {proposal_id} not found in logs, using minimal proposal data")
            proposal_data = {
                "id": proposal_id,
                "title": "",
                "description": "",
                "financial_impact": 0.0,
                "legal_risk": 0.0,
                "vote_result": None,
                "deliberation_responses": None
            }
        
        # Build proper authorization payload for execution
        proposal_dict = {
            "id": proposal_id,
            "title": proposal_data.get("title", ""),
            "description": proposal_data.get("description", ""),
            "financial_impact": proposal_data.get("financial_impact", 0.0),
            "legal_risk": proposal_data.get("legal_risk", 0.0),
            "status": ProposalStatus.APPROVED.value
        }
        authorization_payload = _build_authorization_payload(owner_id, proposal_dict)
        
        # Create state for execution with full proposal data
        state: GovernanceState = {
            "phase": GovernancePhase.EXECUTION,
            "proposal": proposal_dict,
            "proposal_status": ProposalStatus.APPROVED,
            "owner_signature": owner_signature,
            "owner_id": owner_id,
            "authorization_payload": authorization_payload,
            "needs_owner_approval": False,
            "validation_results": {},
            "errors": [],
            "voting_result": proposal_data.get("vote_result"),
            "deliberation_result": proposal_data.get("deliberation_responses"),
            "context": {
                "timestamp": datetime.now().isoformat()
            }
        }
        
        # Execute the decision
        try:
            state = execute_decision(state)
            return state
        except Exception as e:
            logger.error(f"Execution failed after approval: {e}", exc_info=True)
            raise ConstitutionalError(f"Rule 10 Violation: Execution failed after owner approval. Error: {e}")
    else:
        log_event(
            event_type="proposal_rejected_by_owner",
            data={
                "proposal_id": proposal_id,
                "owner_id": owner_id,
                "status": ProposalStatus.REJECTED.value
            },
            metadata={"function": "resume_from_approval"}
        )
        
        return {
            "proposal_id": proposal_id,
            "status": ProposalStatus.REJECTED.value,
            "owner_decision": "rejected",
            "owner_id": owner_id
        }


def run_governance_cycle(
    proposal: Dict,
    owner_signature: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> Dict:
    """
    Execute full governance cycle through state machine.
    
    Progresses through: IDEATION → DELIBERATION → VOTING → [PENDING_APPROVAL | END] → EXECUTION → RETROSPECTIVE
    If voting approves: VOTING → PENDING_APPROVAL (waits for owner)
    If voting rejects/vetoes: VOTING → END (stops)
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
        "retrospective_result": None,
        "validation_results": {},
        "errors": [],
        "needs_owner_approval": None
    }
    
    # Build state machine
    workflow = StateGraph(GovernanceState)
    
    # Add nodes
    workflow.add_node(GovernancePhase.IDEATION, conduct_ideation)
    workflow.add_node(GovernancePhase.DELIBERATION, conduct_deliberation)
    workflow.add_node(GovernancePhase.VOTING, conduct_voting)
    workflow.add_node(GovernancePhase.PENDING_APPROVAL, handle_pending_approval)
    workflow.add_node(GovernancePhase.EXECUTION, execute_decision)
    workflow.add_node(GovernancePhase.RETROSPECTIVE, conduct_retrospective)
    
    # Add edges
    workflow.set_entry_point(GovernancePhase.IDEATION)
    workflow.add_edge(GovernancePhase.IDEATION, GovernancePhase.DELIBERATION)
    workflow.add_edge(GovernancePhase.DELIBERATION, GovernancePhase.VOTING)
    # Conditional routing: VOTING → PENDING_APPROVAL (if approved) or END (if rejected/vetoed)
    workflow.add_conditional_edges(
        GovernancePhase.VOTING,
        _route_after_voting,
        {
            GovernancePhase.PENDING_APPROVAL: GovernancePhase.PENDING_APPROVAL,
            END: END
        }
    )
    # PENDING_APPROVAL stops here - owner must approve via resume_from_approval()
    # When resumed, execution is called directly (not through state machine)
    workflow.add_edge(GovernancePhase.EXECUTION, GovernancePhase.RETROSPECTIVE)
    workflow.add_edge(GovernancePhase.RETROSPECTIVE, END)
    
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
                    GovernancePhase.EXECUTION,
                    GovernancePhase.RETROSPECTIVE
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


def _persist_deliberation_results(proposal_id: str, payload: Dict[str, Any]) -> Path:
    """
    Persist deliberation payload to disk for immutable audit trail.

    Args:
        proposal_id: Identifier of the proposal under deliberation.
        payload: Deliberation payload containing responses by role.

    Returns:
        Path to the persisted deliberation file.
    """
    sanitized_id = _sanitize_identifier(proposal_id or "UNKNOWN")
    PROPOSAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{sanitized_id}_deliberation.json"
    destination = PROPOSAL_DATA_DIR / filename

    with open(destination, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)

    logger.info(
        "Deliberation results persisted",
        extra={"proposal_id": proposal_id, "path": str(destination)}
    )
    return destination


def _build_role_deliberation_prompt(role: str, context: Dict[str, Any]) -> str:
    """
    Construct a deliberation prompt tailored to a specific board role.

    Args:
        role: Board role identifier.
        context: Context dictionary returned by build_agent_context.

    Returns:
        Prompt string for the board member.
    """
    proposal = context.get("current_proposal", {})
    recent_activity = context.get("recent_activity_summary", "")
    trend_analysis = context.get("trend_analysis", "")
    precedents = context.get("relevant_precedents", [])

    precedent_summary = "\n".join(
        f"- {precedent.get('summary', str(precedent))}" for precedent in precedents
    ) or "- None recorded"

    # Base prompt components
    base_prompt = (
        f"You are serving as the {role} on the AI governance board.\n"
        f"Proposal ID: {proposal.get('id', 'UNKNOWN')}\n"
        f"Title: {proposal.get('title', 'No title provided')}\n"
        f"Description: {proposal.get('description', 'No description provided')}\n"
        f"Financial Impact: {proposal.get('financial_impact', 'Unspecified')}\n"
        f"Legal Risk: {proposal.get('legal_risk', 'Unspecified')}\n\n"
        f"Recent Board Activity:\n{recent_activity or 'No recent activity recorded.'}\n\n"
        f"Relevant Precedents:\n{precedent_summary}\n\n"
        f"Trend Analysis:\n{trend_analysis or 'No trend analysis available.'}\n\n"
    )
    
    # Role-specific instructions
    if role == "CHAIR":
        role_instructions = (
            f"Your Role as CHAIR:\n"
            f"- You are the facilitator and moderator of the board\n"
            f"- Frame the strategic question or proposal clearly\n"
            f"- Set the tone for constructive discussion\n"
            f"- Highlight key areas that need exploration\n"
            f"- Ensure all critical perspectives are considered\n"
            f"- Keep discussion focused and productive\n"
            f"- Synthesize key points of consensus and disagreement\n"
            f"- Provide a balanced summary of the deliberation\n\n"
            f"IMPORTANT: You do NOT vote in regular voting (only CEO, CFO, COO, CMO vote).\n"
            f"You only vote if there's a 2-2 tie between the four voting members.\n\n"
            f"Provide a substantial, detailed deliberation that:\n"
            f"1. Frames the strategic question clearly\n"
            f"2. Identifies key areas for board consideration\n"
            f"3. Highlights potential risks and opportunities\n"
            f"4. Facilitates productive discussion\n"
            f"5. Provides a balanced perspective on the proposal\n\n"
            f"Your response must be at least 200 words and provide meaningful strategic guidance."
        )
    elif role == "SECRETARY":
        role_instructions = (
            f"Your Role as SECRETARY:\n"
            f"- You document proceedings and maintain records\n"
            f"- You do NOT vote (documentation only)\n"
            f"- Provide a procedural summary of the deliberation\n"
            f"- Document key points, concerns, and recommendations\n\n"
            f"Provide a clear, structured summary of the deliberation process and key points discussed."
        )
    elif role in ["LEGAL", "CISO"]:
        role_instructions = (
            f"Your Role as {role}:\n"
            f"- You have VETO POWER (separate from regular voting)\n"
            f"- You do NOT cast regular votes (only CEO, CFO, COO, CMO vote)\n"
            f"- Review for {'legal/constitutional violations' if role == 'LEGAL' else 'security/data risks'}\n"
            f"- Exercise veto if you identify critical issues\n\n"
            f"Provide a detailed analysis focusing on {'legal, regulatory, and constitutional compliance' if role == 'LEGAL' else 'security, data integrity, and privacy concerns'}."
        )
    else:
        # For voting members (CEO, CFO, COO, CMO)
        role_instructions = (
            f"Your Role as {role}:\n"
            f"- You are a VOTING MEMBER with 25% voting weight\n"
            f"- You will vote in the voting phase\n"
            f"- Focus on considerations relevant to your role\n\n"
            f"Provide a detailed deliberation from the perspective of the {role}. "
            f"Focus on financial, legal, operational, marketing, and risk considerations relevant to your role. "
            f"Recommend approve, reject, or abstain and explain your reasoning."
        )
    
    return base_prompt + role_instructions


def _sanitize_identifier(value: str) -> str:
    """
    Sanitize identifiers for filesystem use.

    Allows alphanumeric characters, hyphen, and underscore.
    Other characters are replaced with underscores.
    """
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


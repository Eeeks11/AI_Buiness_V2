"""
Board Governance Workflows

Implements ideation, deliberation, and voting cycles with constitutional
logging and validation to satisfy Week 6 governance requirements.
"""

# Standard library
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import sys

# Local - models first (single source of truth)
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "memory_systems" / "codebase_memory"))
from models.core import ConstitutionalError, Proposal, RoleType, Vote, VoteResult, VoteType

# Local - constitutional enforcement
sys.path.insert(0, str(project_root / "constitutional_layer_immutable"))
from constitution import validate_constitutional_compliance

# Local - memory systems
sys.path.insert(0, str(project_root / "memory_systems" / "business_memory" / "memory"))
from context_builder import build_agent_context

# Local - orchestrator utilities
sys.path.insert(0, str(project_root / "governance_layer" / "orchestrator"))
from llm_router import call_llm

# Local - role utilities
sys.path.insert(0, str(project_root / "governance_layer" / "roles"))
from prompt_templates import generate_role_prompt, load_role_configs

# Local - voting
sys.path.insert(0, str(project_root / "governance_layer" / "governance"))
from voting import tally_votes

# Local - utilities
from utilities.logger import log_event

logger = logging.getLogger(__name__)

ROLE_PROVIDER_MAP: Dict[str, str] = {
    "CEO": "openai/gpt-4o",
    "CFO": "anthropic/claude-3-5-sonnet-20241022",
    "COO": "google/gemini-1.5-pro",
    "CMO": "x-ai/grok-beta",
    "LEGAL": "openai/gpt-4o",
    "CISO": "mistralai/mistral-large",
    "CHAIR": "anthropic/claude-3-5-sonnet-20241022",
    "SECRETARY": "google/gemini-1.5-pro"
}


def conduct_ideation(proposal: Proposal) -> Dict[str, Any]:
    """
    Conduct ideation by generating prompts for each board role.
    
    Args:
        proposal: Proposal under consideration.
    
    Returns:
        Dictionary containing role prompts, contexts, and metadata.
    
    Raises:
        ConstitutionalError: If context generation or validation fails.
    """
    logger.info("Starting board ideation", extra={"proposal_id": proposal.id})

    try:
        role_configs = load_role_configs()
        role_contexts: Dict[str, Dict[str, Any]] = {}
        role_prompts: Dict[str, str] = {}

        proposal_payload = proposal.model_dump()

        for role in role_configs.keys():
            context = build_agent_context(
                role=role,
                current_proposal=proposal_payload,
                topic_keywords=proposal_payload.get("keywords", [])
            )
            prompt = generate_role_prompt(role_name=role, context=context)
            role_contexts[role] = context
            role_prompts[role] = prompt

        timestamp = datetime.now().isoformat()

        try:
            log_event(
                event_type="board_ideation_conducted",
                data={
                    "proposal_id": proposal.id,
                    "role_count": len(role_prompts),
                    "timestamp": timestamp
                },
                metadata={"function": "conduct_ideation"}
            )
        except Exception as exc:
            logger.warning("Failed to log ideation event", extra={"error": str(exc)})

        validation = validate_constitutional_compliance(
            action={
                "type": "conduct_ideation",
                "proposal_id": proposal.id,
                "logged": True
            },
            context={"log_path": str(project_root / "audit_compliance" / "logs" / "events.jsonl")}
        )

        if not validation.is_compliant:
            logger.error(
                "Ideation validation failed",
                extra={"proposal_id": proposal.id, "violations": validation.violated_rules}
            )
            raise ConstitutionalError(
                f"Rule 6 Violation: Ideation invalid. Violations: {validation.violated_rules}"
            )

        logger.info("Board ideation completed", extra={"proposal_id": proposal.id})
        return {
            "proposal": proposal_payload,
            "role_prompts": role_prompts,
            "role_contexts": role_contexts,
            "timestamp": timestamp
        }
    except ConstitutionalError:
        raise
    except Exception as exc:
        logger.error("Unexpected ideation error", exc_info=True)
        raise ConstitutionalError(f"Rule 6 Violation: Ideation process failed. Error: {exc}") from exc


def conduct_deliberation(ideation_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Conduct deliberation using generated role prompts and LLM router.
    
    Args:
        ideation_output: Output from conduct_ideation containing role prompts and metadata.
    
    Returns:
        Dictionary mapping roles to deliberation summaries and associated metadata.
    
    Raises:
        ConstitutionalError: If deliberation fails or validation is unsuccessful.
    """
    proposal_id = ideation_output.get("proposal", {}).get("id", "UNKNOWN")
    logger.info("Starting board deliberation", extra={"proposal_id": proposal_id})

    try:
        role_prompts = ideation_output.get("role_prompts", {})
        deliberation_responses: Dict[str, str] = {}

        for role, prompt in role_prompts.items():
            provider = ROLE_PROVIDER_MAP.get(role, "openai/gpt-4o")
            deliberation_responses[role] = call_llm(
                provider=provider,
                prompt=prompt,
                temperature=0.6,
                max_tokens=1800
            )

        timestamp = datetime.now().isoformat()

        try:
            log_event(
                event_type="board_deliberation_conducted",
                data={
                    "proposal_id": proposal_id,
                    "response_count": len(deliberation_responses),
                    "timestamp": timestamp
                },
                metadata={"function": "conduct_deliberation"}
            )
        except Exception as exc:
            logger.warning("Failed to log deliberation event", extra={"error": str(exc)})

        validation = validate_constitutional_compliance(
            action={
                "type": "conduct_deliberation",
                "proposal_id": proposal_id,
                "logged": True
            },
            context={
                "log_path": str(project_root / "audit_compliance" / "logs" / "events.jsonl"),
                "legal_approval": ideation_output.get("proposal", {}).get("legal_approval", False)
            }
        )

        if not validation.is_compliant:
            logger.error(
                "Deliberation validation failed",
                extra={"proposal_id": proposal_id, "violations": validation.violated_rules}
            )
            raise ConstitutionalError(
                f"Rule 6 Violation: Deliberation invalid. Violations: {validation.violated_rules}"
            )

        logger.info("Board deliberation completed", extra={"proposal_id": proposal_id})
        return {
            "proposal": ideation_output.get("proposal", {}),
            "role_prompts": role_prompts,
            "deliberation_responses": deliberation_responses,
            "timestamp": timestamp
        }
    except ConstitutionalError:
        raise
    except Exception as exc:
        logger.error("Unexpected deliberation error", exc_info=True)
        raise ConstitutionalError(f"Rule 6 Violation: Deliberation process failed. Error: {exc}") from exc


def _determine_vote_type(role: str, directives: Dict[str, str]) -> VoteType:
    """
    Determine the vote type for a role based on provided directives.
    
    Args:
        role: Role identifier (e.g., 'CEO').
        directives: Mapping of role names to requested vote actions.
    
    Returns:
        VoteType aligned with the directive (defaults to approve).
    
    Raises:
        ConstitutionalError: If the directive is unsupported.
    """
    directive = directives.get(role, "approve").lower()
    if directive == "approve":
        return VoteType.APPROVE
    if directive == "reject":
        return VoteType.REJECT
    if directive == "abstain":
        return VoteType.ABSTAIN
    if directive == "veto":
        return VoteType.VETO
    raise ConstitutionalError(f"Rule 9 Violation: Unsupported vote directive '{directive}' for role {role}")


def conduct_vote(deliberation_output: Dict[str, Any]) -> VoteResult:
    """
    Conduct voting phase based on deliberation responses.
    
    Args:
        deliberation_output: Output from conduct_deliberation including responses.
    
    Returns:
        VoteResult capturing the weighted vote distribution.
    
    Raises:
        ConstitutionalError: If voting fails or validation is unsuccessful.
    """
    proposal = deliberation_output.get("proposal", {})
    proposal_id = proposal.get("id", "UNKNOWN")
    logger.info("Starting board vote", extra={"proposal_id": proposal_id})

    try:
        role_configs = load_role_configs()
        vote_directives = deliberation_output.get("vote_directives", {})
        deliberation_responses = deliberation_output.get("deliberation_responses", {})

        votes: List[Vote] = []
        for role, config in role_configs.items():
            vote_type = _determine_vote_type(role, vote_directives)

            rationale = deliberation_responses.get(role, "")
            votes.append(
                Vote(
                    member_id=f"{role.lower()}_agent",
                    role=RoleType(role),
                    vote_type=vote_type,
                    weight=float(config.get("voting_weight", 0.0)),
                    rationale=rationale[:500]
                )
            )

        vote_result = tally_votes(votes=votes, roles=role_configs, proposal_id=proposal_id)

        try:
            log_event(
                event_type="board_vote_conducted",
                data={
                    "proposal_id": proposal_id,
                    "vote_count": len(votes),
                    "timestamp": datetime.now().isoformat()
                },
                metadata={"function": "conduct_vote"}
            )
        except Exception as exc:
            logger.warning("Failed to log voting event", extra={"error": str(exc)})

        validation = validate_constitutional_compliance(
            vote_result=vote_result,
            context={"log_path": str(project_root / "audit_compliance" / "logs" / "events.jsonl")}
        )

        if not validation.is_compliant:
            logger.error(
                "Voting validation failed",
                extra={"proposal_id": proposal_id, "violations": validation.violated_rules}
            )
            raise ConstitutionalError(
                f"Rule 9 Violation: Vote invalid. Violations: {validation.violated_rules}"
            )

        logger.info("Board vote completed", extra={"proposal_id": proposal_id})
        return vote_result
    except ConstitutionalError:
        raise
    except Exception as exc:
        logger.error("Unexpected voting error", exc_info=True)
        raise ConstitutionalError(f"Rule 6 Violation: Voting process failed. Error: {exc}") from exc


"""
Board Governance Workflows

Implements ideation, deliberation, and voting cycles with constitutional
logging and validation to satisfy Week 6 governance requirements.
"""

# Standard library
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import sys

# Local - models first (single source of truth)
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from models.core import (
    BoardMember,
    BoardSession,
    ConstitutionalError,
    Proposal,
    RoleType,
    Vote,
    VoteResult,
    VoteType,
)

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

_ROLE_PROVIDER_CONFIG_PATH = project_root / "config_settings" / "role_provider_map.json"
_DEFAULT_ROLE_PROVIDER_MAP: Dict[str, str] = {
    "CHAIR": "openai/gpt-5",
    "CEO": "openai/gpt-5",
    "COO": "x-ai/grok-4",
    "CMO": "google/gemini-2.5-pro",
    "CFO": "anthropic/claude-4.5-sonnet",
    "LEGAL": "mistralai/mistral-large-2",
    "CISO": "x-ai/grok-4",
    "SECRETARY": "anthropic/claude-4.5-sonnet",
}

_ROLE_PROVIDER_CACHE: Optional[Dict[str, str]] = None


def _load_role_provider_map() -> Dict[str, str]:
    """
    Load role-to-provider assignments from configuration, ensuring defaults exist.

    Returns:
        Dictionary mapping role identifiers to provider strings.
    """
    config_data: Dict[str, str] = {}

    if _ROLE_PROVIDER_CONFIG_PATH.exists():
        try:
            with open(_ROLE_PROVIDER_CONFIG_PATH, "r", encoding="utf-8") as handle:
                config_data = json.load(handle)
        except json.JSONDecodeError as exc:
            logger.error(
                "Role provider configuration file malformed",
                extra={"path": str(_ROLE_PROVIDER_CONFIG_PATH), "error": str(exc)},
            )
            raise ConstitutionalError(
                f"Rule 6 Violation: Role provider configuration invalid. Error: {exc}"
            ) from exc
    else:
        try:
            _ROLE_PROVIDER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_ROLE_PROVIDER_CONFIG_PATH, "w", encoding="utf-8") as handle:
                json.dump(_DEFAULT_ROLE_PROVIDER_MAP, handle, indent=2, ensure_ascii=False)
            logger.info(
                "Role provider configuration file created with defaults",
                extra={"path": str(_ROLE_PROVIDER_CONFIG_PATH)},
            )
        except Exception as exc:
            logger.error(
                "Failed to create default role provider configuration",
                extra={"path": str(_ROLE_PROVIDER_CONFIG_PATH), "error": str(exc)},
            )
            raise ConstitutionalError(
                f"Rule 6 Violation: Unable to initialize role provider configuration. Error: {exc}"
            ) from exc

    merged_map = {role.upper(): provider for role, provider in _DEFAULT_ROLE_PROVIDER_MAP.items()}
    merged_map.update({role.upper(): provider for role, provider in config_data.items()})

    role_configs = load_role_configs()
    missing_roles = [role for role in role_configs.keys() if role not in merged_map]
    if missing_roles:
        logger.error(
            "Role provider configuration missing assignments",
            extra={"missing_roles": missing_roles},
        )
        raise ConstitutionalError(
            f"Rule 8 Violation: Provider assignments missing for roles: {missing_roles}"
        )

    provider_families = {provider.split("/")[0] for provider in merged_map.values() if isinstance(provider, str)}
    if len(provider_families) < 5:
        logger.error(
            "Insufficient provider diversity for board roles",
            extra={"unique_providers": sorted(provider_families)},
        )
        raise ConstitutionalError(
            "Rule 8 Violation: Board roles must be distributed across at least five distinct providers."
        )

    return merged_map


def get_role_provider_map(refresh: bool = False) -> Dict[str, str]:
    """
    Retrieve the cached role-to-provider mapping (optionally refreshing it).
    """
    global _ROLE_PROVIDER_CACHE
    if refresh or _ROLE_PROVIDER_CACHE is None:
        _ROLE_PROVIDER_CACHE = _load_role_provider_map()
    return dict(_ROLE_PROVIDER_CACHE)


ROLE_PROVIDER_MAP: Dict[str, str] = get_role_provider_map(refresh=True)


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
        role_providers = get_role_provider_map()
        deliberation_responses: Dict[str, str] = {}

        for role, prompt in role_prompts.items():
            provider = role_providers.get(role)
            if not provider:
                logger.error(
                    "No provider assigned for role",
                    extra={"role": role, "proposal_id": proposal_id},
                )
                raise ConstitutionalError(
                    f"Rule 8 Violation: No provider configured for board role '{role}'"
                )
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
        board_members: List[BoardMember] = []
        for role, config in role_configs.items():
            vote_type = _determine_vote_type(role, vote_directives)

            rationale = deliberation_responses.get(role, "")
            member_vote = Vote(
                member_id=f"{role.lower()}_agent",
                role=RoleType(role),
                vote_type=vote_type,
                weight=float(config.get("voting_weight", 0.0)),
                rationale=rationale[:500]
            )
            votes.append(member_vote)
            board_members.append(
                BoardMember(
                    member_id=member_vote.member_id,
                    role=member_vote.role,
                    model_name=config.get("model_name", f"{role.lower()}_delegate"),
                    voting_weight=member_vote.weight,
                    is_active=True,
                )
            )

        vote_result = tally_votes(votes=votes, roles=role_configs, proposal_id=proposal_id)

        board_session_snapshot = BoardSession(
            id=vote_result.session_id,
            members=board_members,
        )

        try:
            log_event(
                event_type="board_vote_conducted",
                data={
                    "proposal_id": proposal_id,
                    "vote_count": len(votes),
                    "active_members": len(board_session_snapshot.get_active_members()),
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


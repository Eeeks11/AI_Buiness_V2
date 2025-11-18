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

# Local - configuration
sys.path.insert(0, str(project_root / "config_settings"))
from config import get_settings

# Local - voting
sys.path.insert(0, str(project_root / "governance_layer" / "governance"))
from voting import tally_votes

# Local - utilities
from utilities.logger import log_event

logger = logging.getLogger(__name__)

_ROLE_PROVIDER_CONFIG_PATH = project_root / "config_settings" / "role_provider_map.json"
_ROLE_PROVIDER_CACHE: Optional[Dict[str, str]] = None


def _load_role_provider_map() -> Dict[str, str]:
    """
    Load role-to-provider assignments from configuration, ensuring defaults exist.

    Returns:
        Dictionary mapping role identifiers to provider strings.
    """
    config_data: Dict[str, str] = {}

    settings = get_settings()
    default_map: Dict[str, str] = {
        "CHAIR": settings.provider_model_identifier("openai"),
        "CEO": settings.provider_model_identifier("openai"),
        "COO": settings.provider_model_identifier("xai"),
        "CMO": settings.provider_model_identifier("google"),
        "CFO": settings.provider_model_identifier("anthropic"),
        "LEGAL": settings.provider_model_identifier("mistral"),
        "CISO": settings.provider_model_identifier("xai"),
        "SECRETARY": settings.provider_model_identifier("anthropic"),
    }

    if _ROLE_PROVIDER_CONFIG_PATH.exists():
        try:
            with open(_ROLE_PROVIDER_CONFIG_PATH, "r", encoding="utf-8") as handle:
                raw_data = json.load(handle)
                if isinstance(raw_data, dict):
                    config_data = raw_data
                else:
                    logger.warning(
                        "Role provider configuration is not a dictionary; ignoring contents",
                        extra={"path": str(_ROLE_PROVIDER_CONFIG_PATH)},
                    )
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

    merged_map = {role.upper(): provider for role, provider in default_map.items()}
    for role, provider in config_data.items():
        role_key = role.upper()
        if role_key not in merged_map:
            continue
        if provider is None:
            continue
        provider_value = str(provider).strip()
        if provider_value.upper() in {"ENV", "AUTO", "DEFAULT"}:
            continue
        merged_map[role_key] = provider_value

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


def _synthesize_ideation_results(
    role_responses: Dict[str, str],
    role_contexts: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Synthesize ideation results by aggregating and categorizing ideas into themes.
    
    Implements Section 5.3 Step 3: Synthesis.
    
    Args:
        role_responses: Dictionary mapping role names to their ideation responses.
        role_contexts: Dictionary mapping role names to their context data.
    
    Returns:
        Dictionary containing synthesized themes, clusters, and evidence summaries.
    """
    logger.info("Synthesizing ideation results", extra={"role_count": len(role_responses)})
    
    # Aggregate all ideas from role responses
    all_ideas: List[str] = []
    for role, response in role_responses.items():
        # Extract ideas from response (simple extraction - could be enhanced with LLM)
        ideas = response.split("\n")
        all_ideas.extend([idea.strip() for idea in ideas if idea.strip()])
    
    # Categorize into themes (simplified - could use LLM for better categorization)
    themes: Dict[str, List[str]] = {
        "financial": [],
        "operational": [],
        "strategic": [],
        "market": [],
        "technical": [],
        "other": []
    }
    
    financial_keywords = ["profit", "revenue", "cost", "financial", "roi", "investment", "budget"]
    operational_keywords = ["process", "efficiency", "operation", "workflow", "delivery"]
    strategic_keywords = ["strategy", "vision", "long-term", "growth", "expansion"]
    market_keywords = ["market", "customer", "demand", "competition", "brand"]
    technical_keywords = ["system", "infrastructure", "technology", "platform", "api"]
    
    for idea in all_ideas:
        idea_lower = idea.lower()
        categorized = False
        for keyword in financial_keywords:
            if keyword in idea_lower:
                themes["financial"].append(idea)
                categorized = True
                break
        if categorized:
            continue
        for keyword in operational_keywords:
            if keyword in idea_lower:
                themes["operational"].append(idea)
                categorized = True
                break
        if categorized:
            continue
        for keyword in strategic_keywords:
            if keyword in idea_lower:
                themes["strategic"].append(idea)
                categorized = True
                break
        if categorized:
            continue
        for keyword in market_keywords:
            if keyword in idea_lower:
                themes["market"].append(idea)
                categorized = True
                break
        if categorized:
            continue
        for keyword in technical_keywords:
            if keyword in idea_lower:
                themes["technical"].append(idea)
                categorized = True
                break
        if not categorized:
            themes["other"].append(idea)
    
    # Summarize supporting evidence
    evidence_summary = {
        "total_ideas": len(all_ideas),
        "ideas_by_theme": {theme: len(ideas) for theme, ideas in themes.items()},
        "roles_contributing": list(role_responses.keys())
    }
    
    return {
        "themes": themes,
        "evidence_summary": evidence_summary,
        "all_ideas": all_ideas
    }


def _shortlist_ideas(
    synthesized_results: Dict[str, Any],
    proposal: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Short-list ideas by ranking them by profitability potential, strategic fit, and resource alignment.
    
    Implements Section 5.3 Step 4: Short-Listing.
    
    Args:
        synthesized_results: Output from _synthesize_ideation_results().
        proposal: Original proposal dictionary.
    
    Returns:
        List of ranked ideas with scores and rankings.
    """
    logger.info("Short-listing ideas", extra={"total_ideas": len(synthesized_results.get("all_ideas", []))})
    
    ideas = synthesized_results.get("all_ideas", [])
    themes = synthesized_results.get("themes", {})
    
    # Score each idea (simplified scoring - could be enhanced with LLM)
    scored_ideas: List[Dict[str, Any]] = []
    
    for idea in ideas:
        score = 0.0
        
        # Profitability potential (0-1.0)
        profitability_score = 0.5  # Default
        if any(kw in idea.lower() for kw in ["profit", "revenue", "roi", "income", "revenue"]):
            profitability_score = 0.8
        if any(kw in idea.lower() for kw in ["cost reduction", "efficiency", "optimize"]):
            profitability_score = 0.7
        
        # Strategic fit (0-1.0)
        strategic_fit = 0.5  # Default
        if idea in themes.get("strategic", []):
            strategic_fit = 0.8
        if any(kw in idea.lower() for kw in ["align", "fit", "support", "enable"]):
            strategic_fit = 0.7
        
        # Resource alignment (0-1.0) - simplified
        resource_alignment = 0.5  # Default
        
        # Combined score (weighted)
        combined_score = (
            profitability_score * 0.5 +
            strategic_fit * 0.3 +
            resource_alignment * 0.2
        )
        
        scored_ideas.append({
            "idea": idea,
            "profitability_score": profitability_score,
            "strategic_fit": strategic_fit,
            "resource_alignment": resource_alignment,
            "combined_score": combined_score
        })
    
    # Sort by combined score (descending)
    scored_ideas.sort(key=lambda x: x["combined_score"], reverse=True)
    
    # Add ranking
    for idx, idea in enumerate(scored_ideas, 1):
        idea["rank"] = idx
    
    return scored_ideas


def _assign_ideas_to_roles(
    shortlisted_ideas: List[Dict[str, Any]],
    role_configs: Dict[str, Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Assign selected ideas to individual roles or working groups for deeper analysis.
    
    Implements Section 5.3 Step 5: Assignment.
    
    Args:
        shortlisted_ideas: Output from _shortlist_ideas().
        role_configs: Role configuration dictionary.
    
    Returns:
        Dictionary mapping role names to assigned ideas.
    """
    logger.info("Assigning ideas to roles", extra={"ideas_count": len(shortlisted_ideas)})
    
    # Take top 5 ideas for assignment
    top_ideas = shortlisted_ideas[:5]
    
    # Map ideas to roles based on themes and role responsibilities
    assignments: Dict[str, List[Dict[str, Any]]] = {role: [] for role in role_configs.keys()}
    
    for idea_data in top_ideas:
        idea = idea_data["idea"].lower()
        
        # Assign to CEO for strategic ideas
        if any(kw in idea for kw in ["strategy", "vision", "growth", "expansion"]):
            assignments["CEO"].append(idea_data)
        # Assign to CFO for financial ideas
        elif any(kw in idea for kw in ["profit", "revenue", "cost", "financial", "roi"]):
            assignments["CFO"].append(idea_data)
        # Assign to COO for operational ideas
        elif any(kw in idea for kw in ["process", "efficiency", "operation", "workflow"]):
            assignments["COO"].append(idea_data)
        # Assign to CMO for market ideas
        elif any(kw in idea for kw in ["market", "customer", "demand", "brand"]):
            assignments["CMO"].append(idea_data)
        # Assign to CISO for security/technical ideas
        elif any(kw in idea for kw in ["security", "data", "infrastructure", "system"]):
            assignments["CISO"].append(idea_data)
        # Default to CHAIR for coordination
        else:
            assignments["CHAIR"].append(idea_data)
    
    return assignments


def _generate_ideation_summary(
    proposal: Dict[str, Any],
    synthesized_results: Dict[str, Any],
    shortlisted_ideas: List[Dict[str, Any]],
    assignments: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, Any]:
    """
    Generate Strategic Ideation Summary as specified in Section 5.6.
    
    Args:
        proposal: Original proposal dictionary.
        synthesized_results: Output from _synthesize_ideation_results().
        shortlisted_ideas: Output from _shortlist_ideas().
        assignments: Output from _assign_ideas_to_roles().
    
    Returns:
        Complete Strategic Ideation Summary dictionary.
    """
    logger.info("Generating Strategic Ideation Summary")
    
    # Extract top ideas
    top_ideas = shortlisted_ideas[:5]
    
    # Calculate profitability indicators
    avg_profitability = sum(idea["profitability_score"] for idea in top_ideas) / len(top_ideas) if top_ideas else 0.0
    avg_strategic_fit = sum(idea["strategic_fit"] for idea in top_ideas) / len(top_ideas) if top_ideas else 0.0
    
    # Identify risks and dependencies (simplified)
    risks = []
    dependencies = []
    required_resources = []
    
    for idea_data in top_ideas:
        idea = idea_data["idea"].lower()
        if any(kw in idea for kw in ["risk", "uncertainty", "challenge"]):
            risks.append(idea_data["idea"])
        if any(kw in idea for kw in ["depend", "require", "need"]):
            dependencies.append(idea_data["idea"])
        if any(kw in idea for kw in ["resource", "budget", "team", "infrastructure"]):
            required_resources.append(idea_data["idea"])
    
    # Generate nominations for follow-up proposals
    nominations = [
        {
            "idea": idea_data["idea"],
            "rank": idea_data["rank"],
            "profitability_score": idea_data["profitability_score"],
            "assigned_to": [
                role for role, ideas in assignments.items()
                if any(a["idea"] == idea_data["idea"] for a in ideas)
            ]
        }
        for idea_data in top_ideas
    ]
    
    summary = {
        "proposal_id": proposal.get("id"),
        "thematic_clusters": synthesized_results.get("themes", {}),
        "profitability_indicators": {
            "average_profitability_score": avg_profitability,
            "average_strategic_fit": avg_strategic_fit,
            "high_potential_ideas": len([i for i in top_ideas if i["profitability_score"] > 0.7])
        },
        "risks": risks[:5],  # Top 5 risks
        "dependencies": dependencies[:5],  # Top 5 dependencies
        "required_resources": required_resources[:5],  # Top 5 resources
        "nominations_for_follow_up": nominations,
        "timestamp": datetime.now().isoformat()
    }
    
    return summary


def conduct_ideation(proposal: Proposal) -> Dict[str, Any]:
    """
    Conduct ideation by generating prompts for each board role.
    
    Implements Section 5: Strategic Ideation Framework.
    Includes: Exploration, Synthesis, Short-Listing, Assignment, and Summary generation.
    
    Args:
        proposal: Proposal under consideration.
    
    Returns:
        Dictionary containing role prompts, contexts, synthesized results, short-listed ideas,
        assignments, and Strategic Ideation Summary.
    
    Raises:
        ConstitutionalError: If context generation or validation fails.
    """
    logger.info("Starting board ideation", extra={"proposal_id": proposal.id})

    try:
        role_configs = load_role_configs()
        role_contexts: Dict[str, Dict[str, Any]] = {}
        role_prompts: Dict[str, str] = {}

        proposal_payload = proposal.model_dump()

        # Step 1: Exploration - Generate prompts for each role
        for role in role_configs.keys():
            context = build_agent_context(
                role=role,
                current_proposal=proposal_payload,
                topic_keywords=proposal_payload.get("keywords", [])
            )
            prompt = generate_role_prompt(role_name=role, context=context)
            role_contexts[role] = context
            role_prompts[role] = prompt

        # Step 2: Get ideation responses from each role (simulated - in full implementation would call LLMs)
        # For now, we'll use the prompts as placeholders for responses
        role_responses: Dict[str, str] = {}
        for role, prompt in role_prompts.items():
            # In full implementation, this would call LLM for each role
            # For now, use prompt as placeholder response
            role_responses[role] = f"Ideation response from {role} based on: {prompt[:200]}..."

        # Step 3: Synthesis
        synthesized_results = _synthesize_ideation_results(role_responses, role_contexts)

        # Step 4: Short-Listing
        shortlisted_ideas = _shortlist_ideas(synthesized_results, proposal_payload)

        # Step 5: Assignment
        assignments = _assign_ideas_to_roles(shortlisted_ideas, role_configs)

        # Step 6: Generate Strategic Ideation Summary
        ideation_summary = _generate_ideation_summary(
            proposal_payload,
            synthesized_results,
            shortlisted_ideas,
            assignments
        )

        timestamp = datetime.now().isoformat()

        try:
            log_event(
                event_type="board_ideation_conducted",
                data={
                    "proposal_id": proposal.id,
                    "role_count": len(role_prompts),
                    "ideas_generated": len(synthesized_results.get("all_ideas", [])),
                    "ideas_shortlisted": len(shortlisted_ideas),
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
            "role_responses": role_responses,
            "synthesized_results": synthesized_results,
            "shortlisted_ideas": shortlisted_ideas,
            "assignments": assignments,
            "ideation_summary": ideation_summary,
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


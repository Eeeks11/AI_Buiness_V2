"""
Role Prompt Templates

Generates governance-aware prompts tailored to each board role while enforcing
constitutional logging and validation requirements.
"""

# Standard library
import json
import logging
from pathlib import Path
from typing import Any, Dict
import sys

# Local - models first (single source of truth)
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "Memory Systems" / "Codebase Memory"))
from models.core import ConstitutionalError

# Local - constitutional enforcement
sys.path.insert(0, str(project_root / "Constitutional Layer (Immutable)"))
from constitution import validate_constitutional_compliance

# Local - utilities
sys.path.insert(0, str(project_root / "Utilities"))
from logger import log_event

logger = logging.getLogger(__name__)

_ROLE_CONFIGS_CACHE: Dict[str, Dict[str, Any]] | None = None
_ROLE_CONFIG_PATH = Path(__file__).parent / "role_configs.json"


def load_role_configs() -> Dict[str, Dict[str, Any]]:
    """
    Load board role configurations from JSON.
    
    Returns:
        Dictionary keyed by role name containing role configuration.
    
    Raises:
        ConstitutionalError: If configuration file is missing or invalid.
    """
    global _ROLE_CONFIGS_CACHE

    if _ROLE_CONFIGS_CACHE is not None:
        return _ROLE_CONFIGS_CACHE

    logger.debug("Loading role configurations", extra={"path": str(_ROLE_CONFIG_PATH)})

    if not _ROLE_CONFIG_PATH.exists():
        logger.error("Role configuration file not found", extra={"path": str(_ROLE_CONFIG_PATH)})
        raise ConstitutionalError(
            "Rule 6 Violation: Role configuration file missing; cannot ensure transparent governance setup"
        )

    try:
        with open(_ROLE_CONFIG_PATH, "r", encoding="utf-8") as file:
            role_configs = json.load(file)
    except Exception as exc:
        logger.error("Failed to load role configuration file", exc_info=True)
        raise ConstitutionalError(
            f"Rule 6 Violation: Unable to load role configurations. Error: {exc}"
        ) from exc

    # Basic structure validation
    if not isinstance(role_configs, dict) or len(role_configs) < 5:
        logger.error("Invalid role configuration structure", extra={"config": role_configs})
        raise ConstitutionalError(
            "Rule 8 Violation: Role configuration must define minimum 5 board roles"
        )

    _ROLE_CONFIGS_CACHE = role_configs
    return role_configs


def generate_role_prompt(role_name: str, context: Dict[str, Any]) -> str:
    """
    Generate a governance-compliant prompt for the specified board role.
    
    Args:
        role_name: Role identifier (e.g., 'CEO', 'LEGAL').
        context: Context dictionary produced by the memory context builder.
    
    Returns:
        Multi-line prompt string tailored to the role.
    
    Raises:
        ConstitutionalError: If role is unknown or validation fails.
    """
    logger.info(
        "Generating role prompt",
        extra={"role": role_name, "proposal_id": context.get("current_proposal", {}).get("id")}
    )

    role_key = role_name.upper()
    role_configs = load_role_configs()

    if role_key not in role_configs:
        logger.error("Unknown role requested", extra={"role": role_name})
        raise ConstitutionalError(
            f"Rule 8 Violation: Unknown board role '{role_name}' requested for prompt generation"
        )

    role_config = role_configs[role_key]
    proposal = context.get("current_proposal", {})
    constitutional_rules = context.get("constitutional_rules", {})
    recent_activity = context.get("recent_activity_summary", "")
    precedents = context.get("relevant_precedents", [])
    trend_analysis = context.get("trend_analysis", "")

    responsibilities = "\n".join(
        f"- {responsibility}" for responsibility in role_config.get("responsibilities", [])
    )
    rule_summary = "\n".join(
        f"- {identifier}: {description}"
        for identifier, description in constitutional_rules.items()
    ) or "- Constitutional rules unavailable."
    precedent_summary = "\n".join(
        f"- {precedent.get('summary', str(precedent))}" for precedent in precedents
    ) or "- None recorded"

    prompt = (
        f"You are serving as the {role_config.get('name')} of the AI Board.\n\n"
        f"Board Responsibilities:\n{responsibilities}\n\n"
        f"Proposal Under Review:\n"
        f"- ID: {proposal.get('id', 'UNKNOWN')}\n"
        f"- Title: {proposal.get('title', 'No title provided')}\n"
        f"- Description: {proposal.get('description', 'No description provided')}\n"
        f"- Financial Impact: {proposal.get('financial_impact', 'Unspecified')}\n"
        f"- Legal Risk: {proposal.get('legal_risk', 'Unspecified')}\n\n"
        f"Constitutional Guardrails:\n{rule_summary}\n\n"
        f"Recent Board Activity Summary:\n{recent_activity or 'No recent activity recorded.'}\n\n"
        f"Relevant Precedents:\n{precedent_summary}\n\n"
        f"Trend Analysis:\n{trend_analysis or 'Trend analysis unavailable.'}\n\n"
        f"Your Task:\n"
        f"- Evaluate the proposal strictly within constitutional boundaries.\n"
        f"- Highlight financial, legal, security, and operational considerations relevant to your role.\n"
        f"- Recommend approve, reject, abstain, or veto (if empowered) with clear rationale.\n"
        f"- Reference Rule 4 (financial priority) and Rule 9 (voting weight guardrail) in your reasoning.\n"
    )

    try:
        log_event(
            event_type="role_prompt_generated",
            data={
                "role": role_key,
                "proposal_id": proposal.get("id"),
                "prompt_length": len(prompt),
                "has_precedents": bool(precedents),
                "veto_power": role_config.get("veto_power", False)
            },
            metadata={"function": "generate_role_prompt"}
        )
    except Exception as exc:
        logger.warning("Failed to log role prompt generation", extra={"error": str(exc)})

    validation = validate_constitutional_compliance(
        action={
            "type": "generate_role_prompt",
            "role": role_key,
            "proposal_id": proposal.get("id"),
            "logged": True
        },
        context={
            "log_path": str(project_root / "Audit & Compliance" / "logs" / "events.jsonl"),
            "logged": True
        }
    )

    if not validation.is_compliant:
        logger.error(
            "Role prompt failed constitutional validation",
            extra={"role": role_key, "violations": validation.violated_rules}
        )
        raise ConstitutionalError(
            f"Rule 6 Violation: Prompt generation blocked. Violations: {validation.violated_rules}"
        )

    logger.info("Role prompt generated successfully", extra={"role": role_key})
    return prompt


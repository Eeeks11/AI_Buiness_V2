"""
Context Builder

Constructs context windows from episodic and semantic memory for decision-making.
This satisfies business plan requirement for 'continuous AI analysis and self-optimization' (Page 2).
"""

# Standard library
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import sys

# Local - models first (single source of truth)
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "memory_systems" / "codebase_memory"))
from models.core import ConstitutionalValidation, ConstitutionalError

# Local - constitutional enforcement
sys.path.insert(0, str(project_root / "constitutional_layer_immutable"))
from constitution import validate_constitutional_compliance

# Import from same directory
sys.path.insert(0, str(project_root / "memory_systems" / "business_memory" / "memory"))
from episodic import get_recent_events, summarize_recent_activity
from semantic import recall_relevant_decisions, get_trend_analysis

logger = logging.getLogger(__name__)


def build_agent_context(
    role: str,
    current_proposal: Dict,
    topic_keywords: Optional[List[str]] = None
) -> Dict:
    """
    Assemble complete context for agent decision-making.
    
    This function builds a comprehensive context dictionary that includes:
    - Constitutional rules (from constitution.py)
    - Role information
    - Current proposal
    - Recent activity summary (from episodic memory)
    - Relevant precedents (from semantic memory)
    - Trend analysis (from semantic memory)
    - Timestamp
    
    This satisfies the business plan requirement for 'continuous AI analysis
    and self-optimization' by providing agents with full historical context
    and learned patterns.
    
    Args:
        role: Board role of the agent (e.g., "CEO", "CFO", "LEGAL")
        current_proposal: Dictionary containing the current proposal details
        topic_keywords: Optional list of keywords to guide semantic memory recall
        
    Returns:
        Dictionary containing complete context with all components:
            - constitutional_rules: List of constitutional rules
            - role: Agent role
            - current_proposal: Current proposal dictionary
            - recent_activity_summary: Summary of recent activity
            - relevant_precedents: List of relevant past decisions
            - trend_analysis: Trend analysis for proposal topic
            - timestamp: ISO format timestamp
            - validation: ConstitutionalValidation result
            
    Raises:
        ConstitutionalError: If constitutional validation fails
        
    Example:
        >>> context = build_agent_context(
        ...     role="CEO",
        ...     current_proposal={"id": "prop1", "title": "New Feature"},
        ...     topic_keywords=["feature", "development"]
        ... )
        >>> assert "constitutional_rules" in context
        >>> assert "recent_activity_summary" in context
    """
    logger.info(
        f"Building agent context for role {role}, proposal {current_proposal.get('id', 'unknown')}"
    )
    
    # Get constitutional rules
    try:
        sys.path.insert(0, str(project_root / "constitutional_layer_immutable"))
        from constitution import (
            enforce_rule_1,
            enforce_rule_2,
            enforce_rule_3,
            enforce_rule_4,
            enforce_rule_5,
            enforce_rule_6,
            enforce_rule_7,
            enforce_rule_8,
            enforce_rule_9,
            enforce_rule_10
        )
        
        # Import ConstitutionalRule enum
        from models.core import ConstitutionalRule
        
        # Build rules dictionary
        constitutional_rules = {
            "rule_1": "Access Control - AI cannot change owner access without permission",
            "rule_2": "No Unauthorized Access - AI cannot grant access without owner consent",
            "rule_3": "Immutable Constitution - Constitution cannot be altered",
            "rule_4": "Financial Priority - Maximize owner's financial benefit",
            "rule_5": "Legal Protection - Protect owner's legal interests",
            "rule_6": "Full Transparency - All decisions must be logged",
            "rule_7": "Board Approval - All decisions require board approval",
            "rule_8": "Board Composition - Minimum 5 distinct AI models",
            "rule_9": "Voting Weight Limit - No member > 25% voting weight",
            "rule_10": "Human Ownership Lock - Owner retains ultimate authority"
        }
        
    except Exception as e:
        logger.error(f"Failed to load constitutional rules: {e}", exc_info=True)
        raise ConstitutionalError(
            f"Rule 3 Violation: Failed to load constitutional rules. Error: {e}"
        )
    
    # Get recent activity summary from episodic memory
    try:
        recent_events = get_recent_events(limit=100)
        recent_activity_summary = summarize_recent_activity(recent_events)
    except Exception as e:
        logger.warning(f"Failed to get recent activity summary: {e}")
        recent_activity_summary = "Unable to retrieve recent activity summary."
    
    # Get relevant precedents from semantic memory
    try:
        # Build query from proposal and topic keywords
        if topic_keywords:
            query = " ".join(topic_keywords)
        else:
            # Extract keywords from proposal
            title = current_proposal.get("title", "")
            description = current_proposal.get("description", "")
            query = f"{title} {description}".strip()
        
        if query:
            relevant_precedents = recall_relevant_decisions(query, n_results=5)
        else:
            relevant_precedents = []
    except Exception as e:
        logger.warning(f"Failed to recall relevant precedents: {e}")
        relevant_precedents = []
    
    # Get trend analysis from semantic memory
    try:
        # Determine topic for trend analysis
        if topic_keywords:
            topic = " ".join(topic_keywords[:3])  # Use first 3 keywords
        else:
            topic = current_proposal.get("title", "general decisions")
        
        trend_analysis = get_trend_analysis(topic)
    except Exception as e:
        logger.warning(f"Failed to get trend analysis: {e}")
        trend_analysis = "Unable to retrieve trend analysis."
    
    # Assemble complete context
    context = {
        "constitutional_rules": constitutional_rules,
        "role": role,
        "current_proposal": current_proposal,
        "recent_activity_summary": recent_activity_summary,
        "relevant_precedents": relevant_precedents,
        "trend_analysis": trend_analysis,
        "timestamp": datetime.now().isoformat(),
        "topic_keywords": topic_keywords or []
    }
    
    # Validate constitutional compliance before returning
    try:
        validation = validate_constitutional_compliance(
            action={
                "type": "build_context",
                "role": role,
                "proposal_id": current_proposal.get("id")
            },
            context={
                "logged": True,  # Context building is logged
                "log_path": str(project_root / "audit_compliance" / "logs" / "events.jsonl")
            }
        )
        context["validation"] = {
            "is_compliant": validation.is_compliant,
            "violated_rules": [rule.value for rule in validation.violated_rules],
            "error_messages": validation.error_messages
        }
        
        if not validation.is_compliant:
            logger.warning(
                f"Constitutional validation failed during context building: "
                f"{validation.violated_rules}"
            )
            raise ConstitutionalError(
                f"Rule 6 Violation: Context building failed constitutional validation. "
                f"Violations: {validation.violated_rules}"
            )
    except ConstitutionalError:
        raise
    except Exception as e:
        logger.error(f"Constitutional validation error during context building: {e}", exc_info=True)
        raise ConstitutionalError(
            f"Rule 6 Violation: Failed to validate context. Error: {e}"
        )
    
    # Log context build operation (Rule 6)
    try:
        from utilities.logger import log_event as base_log_event
        base_log_event(
            event_type="context_built",
            data={
                "role": role,
                "proposal_id": current_proposal.get("id"),
                "precedents_count": len(relevant_precedents),
                "has_trend_analysis": bool(trend_analysis)
            },
            metadata={"function": "build_agent_context"}
        )
    except Exception as e:
        logger.warning(f"Failed to log context build operation: {e}")
    
    logger.info(
        f"Built complete context for role {role}: "
        f"{len(relevant_precedents)} precedents, trend analysis included"
    )
    
    return context

"""
Episodic Memory System

Stores and retrieves specific events, decisions, and actions with temporal context.
Implements Rule 6: Full Transparency by logging all events to persistent storage.
"""

# Standard library
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import sys

# Third-party
import litellm

# Local - models first (single source of truth)
project_root = Path(__file__).parent.parent.parent.parent
from models.core import ConstitutionalValidation, APIResponse, ConstitutionalError

# Local - configuration
sys.path.insert(0, str(project_root / "config_settings"))
from config import get_settings, resolve_litellm_model

# Local - constitutional enforcement
sys.path.insert(0, str(project_root / "constitutional_layer_immutable"))
from constitution import validate_constitutional_compliance

# Local - utilities
sys.path.insert(0, str(project_root))
from utilities.logger import log_event as base_log_event, get_recent_logs

logger = logging.getLogger(__name__)


def _coerce_temperature(model_name: str, requested: float) -> float:
    """
    Adjust temperature for models (like GPT-5) that only support fixed values.
    """
    normalized = (model_name or "").strip().lower()
    if normalized.startswith("gpt-5") and requested != 1.0:
        logger.info(
            "Adjusting temperature to 1.0 for fixed-temperature model",
            extra={"model_name": model_name, "requested_temperature": requested},
        )
        return 1.0
    return requested


def log_event(
    event_type: str,
    data: Dict,
    metadata: Optional[Dict] = None
) -> Dict:
    """
    Log an event to episodic memory with constitutional validation.
    
    This function enforces Rule 6: Full Transparency by ensuring all events
    are logged to a persistent, accessible record. Constitutional compliance
    is validated before logging.
    
    Args:
        event_type: Type identifier for the event (e.g., 'board_decision', 'vote_cast')
        data: Dictionary containing event data
        metadata: Optional dictionary with additional metadata
        
    Returns:
        Dictionary containing the logged entry with timestamp
        
    Raises:
        ConstitutionalError: If constitutional validation fails
        
    Example:
        >>> entry = log_event(
        ...     event_type="board_decision",
        ...     data={"proposal_id": "prop1", "outcome": "approved"},
        ...     metadata={"session_id": "sess1"}
        ... )
        >>> assert "timestamp" in entry
    """
    # Validate constitutional compliance before logging (Rule 6)
    try:
        validation = validate_constitutional_compliance(
            action={
                "type": "log_event",
                "event_type": event_type,
                "logged": True
            }
        )
        if not validation.is_compliant:
            logger.error(
                f"Constitutional validation failed for event {event_type}: "
                f"{validation.violated_rules}"
            )
            raise ConstitutionalError(
                f"Rule 6 Violation: Cannot log event without constitutional compliance. "
                f"Violations: {validation.violated_rules}"
            )
    except Exception as e:
        logger.error(f"Constitutional validation error for event {event_type}: {e}", exc_info=True)
        raise
    
    try:
        entry = base_log_event(
            event_type=event_type,
            data=data,
            metadata=metadata or {},
        )
        logger.info(
            "Logged episodic event via immutable logger",
            extra={
                "event_type": event_type,
                "timestamp": entry.get("timestamp"),
                "chain_hash": entry.get("chain_hash"),
            },
        )
        return entry
    except ConstitutionalError:
        raise
    except Exception as e:
        logger.error(f"Failed to log episodic event {event_type}: {e}", exc_info=True)
        raise


def get_recent_events(limit: int = 100) -> List[Dict]:
    """
    Retrieve the most recent events from episodic memory.
    
    Reads from audit_compliance/logs/events.jsonl and returns
    the last N events, most recent first.
    
    Args:
        limit: Maximum number of events to retrieve (default: 100)
        
    Returns:
        List of event dictionaries, most recent first
        
    Example:
        >>> events = get_recent_events(limit=10)
        >>> for event in events:
        ...     print(f"{event['timestamp']}: {event['type']}")
    """
    try:
        entries = get_recent_logs(limit=limit)
        logger.debug(f"Retrieved {len(entries)} recent events from episodic memory")
        return entries
    except Exception as e:
        logger.error(f"Failed to read episodic memory log file: {e}", exc_info=True)
        return []


def summarize_recent_activity(events: List[Dict]) -> str:
    """
    Summarize recent board activities using LLM.
    
    Uses LiteLLM to call gpt-4o-mini for summarization. The summary focuses on:
    - Decisions made
    - Votes cast
    - Outcomes
    - Reasoning
    
    This function logs the LLM call for Rule 6 compliance.
    
    Args:
        events: List of event dictionaries to summarize
        
    Returns:
        String containing the summary of recent activity
        
    Raises:
        ConstitutionalError: If LLM call fails or constitutional validation fails
        
    Example:
        >>> events = get_recent_events(limit=50)
        >>> summary = summarize_recent_activity(events)
        >>> print(summary)
    """
    if not events:
        logger.warning("No events provided for summarization")
        return "No recent activity to summarize."

    settings = get_settings()
    provider_identifier = settings.provider_model_identifier("openai")
    model_name = resolve_litellm_model(provider_identifier)
    
    # Log LLM call attempt (Rule 6)
    try:
        base_log_event(
            event_type="llm_call_attempt",
            data={
                "provider": provider_identifier,
                "purpose": "summarize_recent_activity",
                "event_count": len(events)
            },
            metadata={"function": "summarize_recent_activity"}
        )
    except Exception as e:
        logger.error(f"Failed to log LLM call attempt: {e}", exc_info=True)
        # Continue despite logging failure
    
    # Prepare prompt
    events_text = json.dumps(events, indent=2, ensure_ascii=False)
    prompt = (
        f"Summarize these board activities: {events_text}\n\n"
        f"Focus on:\n"
        f"1. Decisions made\n"
        f"2. Votes cast\n"
        f"3. Outcomes\n"
        f"4. Reasoning\n\n"
        f"Provide a concise summary in plain text."
    )
    
    try:
        # Call LLM via LiteLLM
        effective_temperature = _coerce_temperature(model_name, 0.7)
        response = litellm.completion(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a board activity summarizer. Provide clear, concise summaries."},
                {"role": "user", "content": prompt}
            ],
            temperature=effective_temperature,
            max_tokens=1000
        )
        
        summary = response.choices[0].message.content.strip()
        
        # Log successful LLM call (Rule 6)
        try:
            base_log_event(
                event_type="llm_call_success",
                data={
                    "provider": provider_identifier,
                    "purpose": "summarize_recent_activity",
                    "response_length": len(summary)
                },
                metadata={"function": "summarize_recent_activity"}
            )
        except Exception as e:
            logger.warning(f"Failed to log LLM call success: {e}")
        
        logger.info(f"Generated activity summary: {len(summary)} characters")
        return summary
        
    except Exception as e:
        logger.error(f"LLM call failed for activity summarization: {e}", exc_info=True)
        
        # Log failed LLM call (Rule 6)
        try:
            base_log_event(
                event_type="llm_call_failure",
                data={
                    "provider": provider_identifier,
                    "purpose": "summarize_recent_activity",
                    "error": str(e)
                },
                metadata={"function": "summarize_recent_activity"}
            )
        except Exception as log_error:
            logger.error(f"Failed to log LLM call failure: {log_error}")
        
        raise ConstitutionalError(
            f"Rule 6 Violation: Failed to summarize recent activity. LLM call failed: {e}"
        )
    
    # TODO: Week 9 Arweave batch pinning now orchestrated centrally in utilities.logger

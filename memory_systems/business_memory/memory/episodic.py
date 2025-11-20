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
import tiktoken

# Suppress LiteLLM verbose info messages globally
litellm_logger = logging.getLogger("LiteLLM")
litellm_logger.setLevel(logging.ERROR)  # Only show errors, suppress INFO/WARNING

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

# Rate limit protection: Track last memory call time
_last_memory_call_time: Optional[datetime] = None

# Cache memory summaries to avoid redundant calls
_memory_cache: Dict[str, str] = {}


def get_cached_summary_key() -> str:
    """Generate cache key based on current hour"""
    return datetime.now().strftime("%Y%m%d%H")  # Cache for 1 hour


def should_skip_memory_summarization() -> bool:
    """
    Check if we should skip memory to preserve TPM budget.
    Returns True if we should skip.
    """
    global _last_memory_call_time
    
    # If called within last 2 minutes, skip
    if _last_memory_call_time:
        time_since_last = (datetime.now() - _last_memory_call_time).total_seconds()
        if time_since_last < 120:  # 2 minutes
            logger.warning(
                f"Skipping memory summarization - called {time_since_last:.0f}s ago "
                f"(rate limit protection)"
            )
            return True
    
    return False


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


def count_tokens_precise(text: str, model: str = "gpt-4o") -> int:
    """
    Count tokens precisely using tiktoken (OpenAI's token counter).
    
    Args:
        text: Text to count tokens for
        model: Model name to use for encoding (default: gpt-4o)
        
    Returns:
        Number of tokens in the text
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception as e:
        # Fallback to rough estimate if tiktoken fails
        logger.warning(f"Tiktoken failed, using rough estimate: {e}")
        return len(text) // 4


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


def summarize_recent_activity(events: List[Dict], force_refresh: bool = False) -> str:
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

    # Check cache first (unless force_refresh)
    global _memory_cache
    if not force_refresh:
        cache_key = get_cached_summary_key()
        if cache_key in _memory_cache:
            logger.info("Using cached memory summary", extra={"cache_key": cache_key})
            return _memory_cache[cache_key]
    
    # Rate limit protection: Skip memory if called too recently
    if should_skip_memory_summarization():
        return "Memory summarization skipped to preserve rate limits"

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
    
    # Token counting and truncation to prevent token overflow
    # Rough estimation: ~4 characters per token for English text
    # Target: Keep total request under 15,000 tokens (60,000 chars)
    # Reserve ~5,000 tokens (20,000 chars) for prompt template and output
    # So events should be limited to ~10,000 tokens (40,000 chars) - safer for rate limits
    # With 8 board members × 3 rounds = lots of memory calls, lower limit prevents cumulative exhaustion
    MAX_EVENT_CHARS = 40000  # ~10,000 tokens - safer for rate limits
    PROMPT_TEMPLATE_CHARS = 200  # Approximate size of prompt template
    
    # Convert events to JSON and check size
    events_text = json.dumps(events, indent=2, ensure_ascii=False)
    total_chars = len(events_text) + PROMPT_TEMPLATE_CHARS
    
    # Use precise token counting (fallback to rough estimate if needed)
    estimated_tokens = count_tokens_precise(events_text, model="gpt-4o")
    
    original_event_count = len(events)
    
    # If exceeding limits, truncate to most recent events
    # Use character-based check for truncation (faster), but precise token count for logging
    if len(events_text) > MAX_EVENT_CHARS:
        logger.warning(
            f"Event summary exceeds token limit ({estimated_tokens:.0f} tokens, {total_chars} chars). "
            f"Truncating to most recent events.",
            extra={
                "original_event_count": original_event_count,
                "estimated_tokens": estimated_tokens,
                "total_chars": total_chars
            }
        )
        
        # Truncate events: keep most recent events that fit
        truncated_events = []
        current_size = 0
        
        # Iterate backwards (most recent first) to keep latest events
        for event in reversed(events):
            event_json = json.dumps(event, indent=2, ensure_ascii=False)
            if current_size + len(event_json) + PROMPT_TEMPLATE_CHARS <= MAX_EVENT_CHARS:
                truncated_events.insert(0, event)  # Insert at beginning to maintain order
                current_size += len(event_json)
            else:
                break
        
        events = truncated_events
        events_text = json.dumps(events, indent=2, ensure_ascii=False)
        
        # Recalculate precise token count after truncation
        final_estimated_tokens = count_tokens_precise(events_text, model="gpt-4o")
        
        logger.info(
            f"Truncated events from {original_event_count} to {len(events)} events "
            f"({len(events_text)} chars, ~{final_estimated_tokens:.0f} tokens)",
            extra={
                "original_count": original_event_count,
                "truncated_count": len(events),
                "final_chars": len(events_text),
                "final_estimated_tokens": final_estimated_tokens
            }
        )
    else:
        final_estimated_tokens = estimated_tokens
    
    # Prepare prompt
    prompt = (
        f"Summarize these board activities: {events_text}\n\n"
        f"Focus on:\n"
        f"1. Decisions made\n"
        f"2. Votes cast\n"
        f"3. Outcomes\n"
        f"4. Reasoning\n\n"
        f"Provide a concise summary in plain text."
    )
    
    # Calculate precise token count for full prompt (enhanced logging)
    prompt_tokens = count_tokens_precise(prompt, model="gpt-4o")
    
    logger.info(
        f"Memory summarization token estimate: ~{final_estimated_tokens:.0f} input tokens "
        f"({len(events_text) + PROMPT_TEMPLATE_CHARS} chars) for {len(events)} events, "
        f"~{prompt_tokens:.0f} total prompt tokens",
        extra={
            "event_count": len(events),
            "estimated_tokens": int(final_estimated_tokens),
            "prompt_tokens": int(prompt_tokens),
            "char_count": len(events_text),
            "truncated": original_event_count > len(events)
        }
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
        
        # Update last call time for rate limit protection
        global _last_memory_call_time
        _last_memory_call_time = datetime.now()
        
        # Cache the result before returning
        cache_key = get_cached_summary_key()
        _memory_cache[cache_key] = summary
        
        # Log successful LLM call (Rule 6) with enhanced details
        try:
            base_log_event(
                event_type="llm_call_success",
                data={
                    "provider": provider_identifier,
                    "purpose": "summarize_recent_activity",
                    "response_length": len(summary),
                    "input_events": len(events),
                    "input_tokens": int(final_estimated_tokens),
                    "prompt_tokens": int(prompt_tokens)
                },
                metadata={"function": "summarize_recent_activity"}
            )
        except Exception as e:
            logger.warning(f"Failed to log LLM call success: {e}")
        
        logger.info(
            f"Memory summarization complete: {len(summary)} char response",
            extra={
                "response_length": len(summary),
                "input_events": len(events),
                "input_tokens": int(final_estimated_tokens),
                "prompt_tokens": int(prompt_tokens),
                "cached": True
            }
        )
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

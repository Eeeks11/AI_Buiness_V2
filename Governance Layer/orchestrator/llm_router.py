"""
LLM Router with Governance Hooks

Routes LLM calls to appropriate providers with constitutional compliance validation.
Enforces Rule 6: Full Transparency by logging all LLM calls.
"""

# Standard library
import logging
import time
from typing import List
from pathlib import Path
import sys

# Third-party
import litellm

# Local - models first (single source of truth)
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "Memory Systems" / "Codebase Memory"))
from models.core import ConstitutionalError, APIResponse

# Local - constitutional enforcement
sys.path.insert(0, str(project_root / "Constitutional Layer (Immutable)"))
from constitution import validate_constitutional_compliance

# Local - configuration
sys.path.insert(0, str(project_root / "Config & Settings"))
from config import get_settings

# Local - utilities
sys.path.insert(0, str(project_root / "Utilities"))
from logger import log_event

logger = logging.getLogger(__name__)


# Provider mapping
PROVIDER_MAP = {
    "openai/gpt-4o": "gpt-4o",
    "anthropic/claude-3-5-sonnet-20241022": "claude-3-5-sonnet-20241022",
    "google/gemini-1.5-pro": "gemini/gemini-1.5-pro",
    "x-ai/grok-beta": "grok-beta",
    "mistralai/mistral-large": "mistral-large"
}


def call_llm(
    provider: str,
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 2000
) -> str:
    """
    Call LLM with governance hooks and constitutional compliance.
    
    Before calling LLM:
    - Logs LLM call attempt (Rule 6)
    - Validates constitutional compliance (Rule 6)
    
    Uses LiteLLM's completion() function with retry logic (3 attempts with exponential backoff).
    After successful call, logs response length.
    
    Args:
        provider: Provider identifier (e.g., "openai/gpt-4o", "anthropic/claude-3-5-sonnet-20241022")
        prompt: Prompt text to send to LLM
        temperature: Temperature parameter (default: 0.7)
        max_tokens: Maximum tokens in response (default: 2000)
        
    Returns:
        Response text from LLM
        
    Raises:
        ConstitutionalError: If constitutional validation fails or LLM call fails after retries
        
    Example:
        >>> response = call_llm(
        ...     provider="openai/gpt-4o",
        ...     prompt="Analyze this proposal...",
        ...     temperature=0.7
        ... )
        >>> assert len(response) > 0
    """
    logger.info(f"Calling LLM: {provider}", extra={"provider": provider, "prompt_length": len(prompt)})
    
    # Log LLM call attempt (Rule 6)
    try:
        log_event(
            event_type="llm_call_attempt",
            data={
                "provider": provider,
                "prompt": prompt[:200],  # Truncate for logging
                "prompt_length": len(prompt),
                "temperature": temperature,
                "max_tokens": max_tokens
            },
            metadata={"function": "call_llm"}
        )
    except Exception as e:
        logger.warning(f"Failed to log LLM call attempt: {e}")
    
    # Validate constitutional compliance (Rule 6)
    try:
        validation = validate_constitutional_compliance(
            action={
                "type": "llm_call",
                "provider": provider,
                "logged": True
            },
            context={
                "log_path": str(project_root / "Audit & Compliance" / "logs" / "events.jsonl")
            }
        )
        
        if not validation.is_compliant:
            logger.error(
                f"Constitutional validation failed for LLM call: {validation.violated_rules}",
                extra={"provider": provider}
            )
            raise ConstitutionalError(
                f"Rule 6 Violation: LLM call failed constitutional validation. "
                f"Violations: {validation.violated_rules}"
            )
    except ConstitutionalError:
        raise
    except Exception as e:
        logger.error(f"Constitutional validation error for LLM call: {e}", exc_info=True)
        raise ConstitutionalError(
            f"Rule 6 Violation: Failed to validate LLM call. Error: {e}"
        )
    
    # Map provider to LiteLLM model name
    model_name = PROVIDER_MAP.get(provider)
    if not model_name:
        logger.error(f"Unknown provider: {provider}")
        raise ConstitutionalError(
            f"Unknown LLM provider: {provider}. "
            f"Supported providers: {list(PROVIDER_MAP.keys())}"
        )
    
    # Retry logic: 3 attempts with exponential backoff
    max_retries = 3
    base_delay = 1.0  # seconds
    
    for attempt in range(max_retries):
        try:
            # Call LLM via LiteLLM
            response = litellm.completion(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a helpful AI assistant for board governance."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Log successful LLM call (Rule 6)
            try:
                log_event(
                    event_type="llm_call_success",
                    data={
                        "provider": provider,
                        "response_length": len(response_text),
                        "attempt": attempt + 1
                    },
                    metadata={"function": "call_llm"}
                )
            except Exception as e:
                logger.warning(f"Failed to log LLM call success: {e}")
            
            logger.info(
                f"LLM call successful: {provider}",
                extra={"provider": provider, "response_length": len(response_text)}
            )
            return response_text
            
        except Exception as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(
                    f"LLM call failed (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}",
                    extra={"provider": provider, "attempt": attempt + 1}
                )
                time.sleep(delay)
            else:
                # Final attempt failed
                logger.error(
                    f"LLM call failed after {max_retries} attempts: {e}",
                    exc_info=True,
                    extra={"provider": provider}
                )
                
                # Log failed LLM call (Rule 6)
                try:
                    log_event(
                        event_type="llm_call_failure",
                        data={
                            "provider": provider,
                            "error": str(e),
                            "attempts": max_retries
                        },
                        metadata={"function": "call_llm"}
                    )
                except Exception as log_error:
                    logger.error(f"Failed to log LLM call failure: {log_error}")
                
                raise ConstitutionalError(
                    f"Rule 6 Violation: LLM call failed after {max_retries} attempts. "
                    f"Provider: {provider}, Error: {e}"
                )
    
    # Should never reach here, but just in case
    raise ConstitutionalError(f"Rule 6 Violation: LLM call failed unexpectedly")


def get_available_providers() -> List[str]:
    """
    Get list of available LLM providers from settings.
    
    Validates Rule 8: len(providers) >= 5
    
    Returns:
        List of provider identifiers
        
    Raises:
        ConstitutionalError: If fewer than 5 providers available (Rule 8 violation)
        
    Example:
        >>> providers = get_available_providers()
        >>> assert len(providers) >= 5
        >>> assert "openai/gpt-4o" in providers
    """
    try:
        settings = get_settings()
        active_models = settings.active_models
        
        # Map active models to provider identifiers
        model_to_provider = {
            "openai": "openai/gpt-4o",
            "anthropic": "anthropic/claude-3-5-sonnet-20241022",
            "google": "google/gemini-1.5-pro",
            "xai": "x-ai/grok-beta",
            "mistral": "mistralai/mistral-large"
        }
        
        providers = [model_to_provider[model] for model in active_models if model in model_to_provider]
        
        # Validate Rule 8: Minimum 5 providers
        if len(providers) < 5:
            logger.error(
                f"Rule 8 Violation: Only {len(providers)} providers available, minimum 5 required",
                extra={"providers": providers}
            )
            raise ConstitutionalError(
                f"Rule 8 Violation: System must have minimum 5 active LLM providers. "
                f"Found {len(providers)} providers: {providers}"
            )
        
        logger.info(f"Retrieved {len(providers)} available providers", extra={"providers": providers})
        return providers
        
    except ConstitutionalError:
        raise
    except Exception as e:
        logger.error(f"Error getting available providers: {e}", exc_info=True)
        raise ConstitutionalError(
            f"Rule 8 Violation: Failed to get available providers. Error: {e}"
        )


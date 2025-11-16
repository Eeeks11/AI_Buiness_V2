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
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from models.core import ConstitutionalError, APIResponse

# Local - constitutional enforcement
sys.path.insert(0, str(project_root / "constitutional_layer_immutable"))
from constitution import validate_constitutional_compliance

# Local - configuration
sys.path.insert(0, str(project_root / "config_settings"))
from config import get_settings, resolve_litellm_model

# Local - utilities
from utilities.logger import log_event

logger = logging.getLogger(__name__)


def _coerce_temperature(provider: str, requested_temperature: float) -> float:
    """
    Adjust temperature for providers that only accept fixed values.

    GPT-5 endpoints currently refuse temperatures other than 1.0. Rather than
    forcing callers to remember that caveat, we coerce the value here and note
    the adjustment in the logs.
    """
    settings = get_settings()
    openai_identifier = settings.provider_model_identifier("openai").strip().lower()
    normalized_provider = (provider or "").strip().lower()
    if (
        settings.openai_version.lower().startswith("gpt-5")
        and normalized_provider.startswith(openai_identifier)
        and requested_temperature != 1.0
    ):
        logger.info(
            "Adjusting temperature to 1.0 for provider requiring fixed temperature",
            extra={"provider": provider, "requested_temperature": requested_temperature},
        )
        return 1.0
    return requested_temperature


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
        provider: Provider identifier (e.g., "openai/<model>", "anthropic/<model>")
        prompt: Prompt text to send to LLM
        temperature: Temperature parameter (default: 0.7)
        max_tokens: Maximum tokens in response (default: 2000)
        
    Returns:
        Response text from LLM
        
    Raises:
        ConstitutionalError: If constitutional validation fails or LLM call fails after retries
        
    Example:
        >>> response = call_llm(
        ...     provider="openai/<model>",
        ...     prompt="Analyze this proposal...",
        ...     temperature=0.7
        ... )
        >>> assert len(response) > 0
    """
    logger.info(f"Calling LLM: {provider}", extra={"provider": provider, "prompt_length": len(prompt)})
    effective_temperature = _coerce_temperature(provider, temperature)
    
    # Log LLM call attempt (Rule 6)
    try:
        log_event(
            event_type="llm_call_attempt",
            data={
                "provider": provider,
                "prompt": prompt[:200],  # Truncate for logging
                "prompt_length": len(prompt),
                "temperature": effective_temperature,
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
                "log_path": str(project_root / "audit_compliance" / "logs" / "events.jsonl")
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
    model_name = _resolve_model_name(provider)
    
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
                temperature=effective_temperature,
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
        >>> settings = get_settings()
        >>> assert settings.provider_model_identifier("openai") in providers
    """
    try:
        settings = get_settings()
        active_models = settings.active_models
        
        # Map active models to provider identifiers
        providers = []
        for model in active_models:
            try:
                providers.append(settings.provider_model_identifier(model))
            except ConstitutionalError as exc:
                logger.error(
                    "Failed to resolve provider identifier",
                    extra={"model": model, "error": str(exc)}
                )
                raise
        
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


def _resolve_model_name(provider: str) -> str:
    """
    Resolve LiteLLM model name for a provider identifier using centralized configuration.
    """
    try:
        return resolve_litellm_model(provider)
    except ConstitutionalError:
        raise
    except Exception as exc:
        logger.error(f"Unsupported provider identifier: {provider}", exc_info=True)
        raise ConstitutionalError(
            f"Unknown LLM provider: {provider}. Unable to resolve LiteLLM model. Error: {exc}"
        ) from exc


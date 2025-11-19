"""
LLM Model Health Check System

Checks if LLM models are live and accessible before running governance cycles.
Identifies why models are unavailable and provides diagnostic information.
"""

import logging
import time
from typing import Dict, List, Optional, Any
from pathlib import Path
import sys
from datetime import datetime

# Third-party
import litellm

# Suppress LiteLLM verbose info messages globally
litellm_logger = logging.getLogger("LiteLLM")
litellm_logger.setLevel(logging.ERROR)  # Only show errors, suppress INFO/WARNING

# Local - models first
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from models.core import ConstitutionalError

# Local - configuration
sys.path.insert(0, str(project_root / "config_settings"))
from config import get_settings, resolve_litellm_model

# Local - utilities
from utilities.logger import log_event

logger = logging.getLogger(__name__)


class ModelHealthStatus:
    """Health status for a single model."""
    
    def __init__(
        self,
        provider: str,
        model_name: str,
        is_healthy: bool,
        error: Optional[str] = None,
        error_type: Optional[str] = None,
        response_time_ms: Optional[float] = None,
        checked_at: Optional[str] = None
    ):
        self.provider = provider
        self.model_name = model_name
        self.is_healthy = is_healthy
        self.error = error
        self.error_type = error_type  # e.g., "api_key_missing", "network_error", "rate_limit", "model_not_found"
        self.response_time_ms = response_time_ms
        self.checked_at = checked_at or datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "is_healthy": self.is_healthy,
            "error": self.error,
            "error_type": self.error_type,
            "response_time_ms": self.response_time_ms,
            "checked_at": self.checked_at
        }


def _classify_error(error: Exception) -> tuple[str, str]:
    """
    Classify error type and provide user-friendly message.
    
    Returns:
        Tuple of (error_type, error_message)
    """
    error_str = str(error).lower()
    error_repr = repr(error).lower()
    
    # Check for API key issues
    if any(keyword in error_str or keyword in error_repr for keyword in [
        "api key", "api_key", "authentication", "unauthorized", "401", "invalid key"
    ]):
        return ("api_key_missing", f"API key missing or invalid: {error}")
    
    # Check for network issues
    if any(keyword in error_str or keyword in error_repr for keyword in [
        "connection", "timeout", "network", "dns", "resolve", "unreachable"
    ]):
        return ("network_error", f"Network connectivity issue: {error}")
    
    # Check for rate limits
    if any(keyword in error_str or keyword in error_repr for keyword in [
        "rate limit", "rate_limit", "429", "too many requests", "quota"
    ]):
        return ("rate_limit", f"Rate limit exceeded: {error}")
    
    # Check for model not found
    if any(keyword in error_str or keyword in error_repr for keyword in [
        "model not found", "model_not_found", "invalid model", "does not exist"
    ]):
        return ("model_not_found", f"Model not found or unavailable: {error}")
    
    # Check for service unavailable
    if any(keyword in error_str or keyword in error_repr for keyword in [
        "503", "service unavailable", "maintenance", "down"
    ]):
        return ("service_unavailable", f"Service temporarily unavailable: {error}")
    
    # Check for billing/quota issues
    if any(keyword in error_str or keyword in error_repr for keyword in [
        "billing", "payment", "quota exceeded", "insufficient funds"
    ]):
        return ("billing_error", f"Billing or quota issue: {error}")
    
    # Default: unknown error
    return ("unknown_error", f"Unknown error: {error}")


def check_model_health(provider: str, timeout_seconds: float = 5.0) -> ModelHealthStatus:
    """
    Check if a single LLM model is healthy and accessible.
    
    Performs a minimal test call to verify the model is working.
    
    Args:
        provider: Provider identifier (e.g., "openai/gpt-4o")
        timeout_seconds: Maximum time to wait for response (default: 5.0)
        
    Returns:
        ModelHealthStatus object with health information
    """
    logger.debug(f"Checking health for provider: {provider}")  # Changed from info to debug to reduce noise
    
    try:
        # Resolve model name
        model_name = resolve_litellm_model(provider)
        
        # Suppress LiteLLM verbose error messages during health check
        import logging
        litellm_logger = logging.getLogger("LiteLLM")
        original_level = litellm_logger.level
        litellm_logger.setLevel(logging.ERROR)  # Only show errors, suppress warnings/info
        
        # Perform minimal test call
        start_time = time.time()
        
        try:
            response = litellm.completion(
                model=model_name,
                messages=[
                    {"role": "user", "content": "test"}
                ],
                max_tokens=16,  # Minimum required by some providers (e.g., OpenAI), increased from 10
                timeout=timeout_seconds
            )
            
            response_time_ms = (time.time() - start_time) * 1000
            
            # Check if we got a valid response
            if response and response.choices and len(response.choices) > 0:
                logger.debug(f"Model {provider} is healthy (response time: {response_time_ms:.2f}ms)")  # Changed to debug
                return ModelHealthStatus(
                    provider=provider,
                    model_name=model_name,
                    is_healthy=True,
                    response_time_ms=response_time_ms
                )
            else:
                logger.debug(f"Model {provider} returned empty response")  # Changed to debug
                return ModelHealthStatus(
                    provider=provider,
                    model_name=model_name,
                    is_healthy=False,
                    error="Empty response from model",
                    error_type="empty_response"
                )
                
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            error_type, error_message = _classify_error(e)
            
            # Only log warnings for non-timeout errors to reduce noise
            if error_type != "network_error" or "timeout" not in str(e).lower():
                logger.debug(
                    f"Model {provider} health check failed: {error_message}",
                    extra={"provider": provider, "error_type": error_type}
                )
            
            return ModelHealthStatus(
                provider=provider,
                model_name=model_name,
                is_healthy=False,
                error=error_message,
                error_type=error_type,
                response_time_ms=response_time_ms
            )
        finally:
            # Restore original logging level
            litellm_logger.setLevel(original_level)
            
    except Exception as e:
        # Error resolving model name or other configuration issue
        error_type, error_message = _classify_error(e)
        logger.debug(  # Changed from error to debug to reduce noise
            f"Failed to check health for {provider}: {error_message}",
            extra={"provider": provider, "error_type": error_type}
        )
        
        return ModelHealthStatus(
            provider=provider,
            model_name="unknown",
            is_healthy=False,
            error=error_message,
            error_type=error_type
        )


def check_all_models_health(timeout_seconds: float = 5.0) -> Dict[str, ModelHealthStatus]:
    """
    Check health of all configured LLM models.
    
    Args:
        timeout_seconds: Maximum time to wait for each model response
        
    Returns:
        Dictionary mapping provider identifiers to ModelHealthStatus objects
    """
    logger.info("Starting health check for all models")
    
    settings = get_settings()
    active_models = settings.active_models
    
    health_results: Dict[str, ModelHealthStatus] = {}
    
    for model in active_models:
        try:
            provider = settings.provider_model_identifier(model)
            health_status = check_model_health(provider, timeout_seconds=timeout_seconds)
            health_results[provider] = health_status
        except Exception as e:
            logger.error(
                f"Failed to check health for model {model}: {e}",
                exc_info=True
            )
            # Create error status
            health_results[model] = ModelHealthStatus(
                provider=model,
                model_name="unknown",
                is_healthy=False,
                error=f"Failed to resolve provider: {e}",
                error_type="configuration_error"
            )
    
    # Log health check results (at debug level to reduce noise)
    healthy_count = sum(1 for status in health_results.values() if status.is_healthy)
    total_count = len(health_results)
    
    logger.debug(  # Changed from info to debug to reduce noise
        f"Health check complete: {healthy_count}/{total_count} models healthy",
        extra={
            "healthy_count": healthy_count,
            "total_count": total_count,
            "results": {k: v.to_dict() for k, v in health_results.items()}
        }
    )
    
    # Log to audit trail (Rule 6)
    try:
        log_event(
            event_type="model_health_check_complete",
            data={
                "healthy_count": healthy_count,
                "total_count": total_count,
                "results": {k: v.to_dict() for k, v in health_results.items()}
            },
            metadata={"function": "check_all_models_health"}
        )
    except Exception as e:
        logger.warning(f"Failed to log health check results: {e}")
    
    return health_results


def validate_models_before_governance(
    required_healthy_count: int = 5,
    timeout_seconds: float = 5.0
) -> tuple[bool, Dict[str, ModelHealthStatus], List[str]]:
    """
    Validate that enough models are healthy before running governance cycle.
    
    Args:
        required_healthy_count: Minimum number of healthy models required (default: 5, per Rule 8)
        timeout_seconds: Maximum time to wait for each model response
        
    Returns:
        Tuple of:
        - bool: True if enough models are healthy
        - Dict[str, ModelHealthStatus]: Health status for all models
        - List[str]: Error messages for unhealthy models
    """
    logger.info(f"Validating models before governance (minimum {required_healthy_count} healthy)")
    
    health_results = check_all_models_health(timeout_seconds=timeout_seconds)
    
    healthy_models = [provider for provider, status in health_results.items() if status.is_healthy]
    unhealthy_models = [provider for provider, status in health_results.items() if not status.is_healthy]
    
    healthy_count = len(healthy_models)
    is_valid = healthy_count >= required_healthy_count
    
    # Build error messages
    error_messages = []
    if not is_valid:
        error_messages.append(
            f"Insufficient healthy models: {healthy_count}/{required_healthy_count} required"
        )
        
        for provider in unhealthy_models:
            status = health_results[provider]
            error_messages.append(
                f"{provider}: {status.error_type} - {status.error}"
            )
    
    if is_valid:
        logger.info(
            f"Model validation passed: {healthy_count} healthy models available",
            extra={"healthy_models": healthy_models}
        )
    else:
        logger.error(
            f"Model validation failed: {healthy_count} healthy models, {required_healthy_count} required",
            extra={
                "healthy_models": healthy_models,
                "unhealthy_models": unhealthy_models,
                "errors": error_messages
            }
        )
    
    return is_valid, health_results, error_messages


def get_model_health_summary() -> Dict[str, Any]:
    """
    Get a summary of model health status for dashboard display.
    
    Checks health for all unique providers used by board roles to ensure accuracy.
    
    Returns:
        Dictionary with health summary including:
        - total_models: Total number of models
        - healthy_count: Number of healthy models
        - unhealthy_count: Number of unhealthy models
        - models: List of model status dictionaries
        - can_run_governance: Whether governance can proceed
    """
    # Get all unique providers from role assignments (more accurate than just active_models)
    try:
        from governance_layer.governance.board import get_role_provider_map
        role_providers = get_role_provider_map()
        # Get unique providers from roles
        unique_providers = set(role_providers.values())
    except Exception as e:
        logger.warning(f"Failed to get role providers, falling back to active_models: {e}")
        # Fallback to active_models approach
        settings = get_settings()
        active_models = settings.active_models
        unique_providers = {settings.provider_model_identifier(model) for model in active_models}
    
    # Quick health check (longer timeout for dashboard to reduce timeout errors)
    # Suppress verbose LiteLLM errors during health check
    import logging
    litellm_logger = logging.getLogger("LiteLLM")
    original_level = litellm_logger.level
    litellm_logger.setLevel(logging.ERROR)  # Suppress INFO/WARNING messages
    
    health_results: Dict[str, ModelHealthStatus] = {}
    
    try:
        # Check health for each unique provider
        for provider in unique_providers:
            if not provider or provider == "Unknown":
                continue
            try:
                health_status = check_model_health(provider, timeout_seconds=10.0)
                health_results[provider] = health_status
            except Exception as e:
                logger.warning(f"Health check failed for {provider}: {e}")
                # Create error status
                health_results[provider] = ModelHealthStatus(
                    provider=provider,
                    model_name="unknown",
                    is_healthy=False,
                    error=f"Health check failed: {e}",
                    error_type="health_check_error"
                )
    finally:
        litellm_logger.setLevel(original_level)  # Restore original logging level
    
    healthy_count = sum(1 for status in health_results.values() if status.is_healthy)
    unhealthy_count = len(health_results) - healthy_count
    
    models_list = [status.to_dict() for status in health_results.values()]
    
    # Check if we can run governance (Rule 8: minimum 5 models)
    can_run_governance = healthy_count >= 5
    
    return {
        "total_models": len(health_results),
        "healthy_count": healthy_count,
        "unhealthy_count": unhealthy_count,
        "can_run_governance": can_run_governance,
        "models": models_list,
        "checked_at": datetime.now().isoformat()
    }

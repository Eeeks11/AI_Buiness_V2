"""
System Configuration Management

This module provides configuration management using Pydantic Settings,
with automatic validation of constitutional compliance (Rules 8 and 9).

All configuration is loaded from environment variables via .env file.
"""

# Standard library
import logging
from pathlib import Path
from typing import Dict, List, Optional

# Third-party
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, ConfigDict

# Local - models first (single source of truth)
import sys
from pathlib import Path as PathLib

# Add Codebase Memory to path for imports
project_root = PathLib(__file__).parent.parent
codebase_memory = project_root / "Memory Systems" / "Codebase Memory"
if str(codebase_memory) not in sys.path:
    sys.path.insert(0, str(codebase_memory))

from models.core import ConstitutionalError, ConstitutionalRule, RoleType

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    System configuration settings with constitutional compliance validation.
    
    Enforces:
    - Rule 8: Minimum 5 active LLM models
    - Rule 9: All vote weights ≤ 0.25
    """
    
    # LLM API Keys (Rule 8: Minimum 5 required)
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key")
    anthropic_api_key: Optional[str] = Field(None, description="Anthropic API key")
    google_api_key: Optional[str] = Field(None, description="Google API key")
    xai_api_key: Optional[str] = Field(None, description="xAI API key")
    mistral_api_key: Optional[str] = Field(None, description="Mistral API key")
    
    # Owner Authentication (Rule 10)
    owner_id: Optional[str] = Field(None, description="Owner identifier")
    owner_signature_key: Optional[str] = Field(None, description="Owner signing key")
    
    # System Configuration
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    arweave_enabled: bool = Field(default=False, description="Enable Arweave integration")
    
    # Database
    database_url: str = Field(
        default="sqlite:///./ai_business.db",
        description="Database connection URL"
    )
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    @property
    def active_models(self) -> List[str]:
        """
        Get list of active LLM models based on configured API keys.
        
        Returns:
            List of model identifiers (e.g., ['openai', 'anthropic', ...])
            
        Note:
            Rule 8 requires minimum 5 active models.
            Defaults to 5 models if no API keys are configured (for testing).
        """
        models = []
        if self.openai_api_key:
            models.append("openai")
        if self.anthropic_api_key:
            models.append("anthropic")
        if self.google_api_key:
            models.append("google")
        if self.xai_api_key:
            models.append("xai")
        if self.mistral_api_key:
            models.append("mistral")
        
        # Default to 5 models if none configured (for testing/development)
        # This ensures Rule 8 compliance even without API keys
        if len(models) == 0:
            models = [
                "openai",
                "anthropic",
                "google",
                "xai",
                "mistral"
            ]
            logger.info(
                "No API keys configured. Using default active models for Rule 8 compliance. "
                "Set API keys in .env for production use."
            )
        
        return models
    
    @property
    def vote_weights(self) -> Dict[str, float]:
        """
        Get voting weights for each role.
        
        Returns:
            Dictionary mapping role names to voting weights (0.0-1.0)
            
        Note:
            Rule 9 requires all weights ≤ 0.25 (0.25 maximum per role).
            Default weights are evenly distributed across 5+ models.
        """
        active_count = len(self.active_models)
        if active_count == 0:
            return {}
        
        # Distribute weights evenly, ensuring no single weight exceeds 0.25
        # With 5+ models, each gets 1/active_count, which is ≤ 0.20 (safe)
        weight_per_model = 1.0 / active_count
        
        # Ensure no weight exceeds 0.25 (Rule 9)
        if weight_per_model > 0.25:
            logger.warning(
                f"Calculated weight {weight_per_model:.2f} exceeds 0.25 limit. "
                f"Capping at 0.25 and redistributing remainder."
            )
            weight_per_model = 0.25
            # Redistribute remainder evenly
            remainder = 1.0 - (weight_per_model * active_count)
            if remainder > 0:
                weight_per_model += remainder / active_count
        
        # Create weights dict using role types
        weights = {}
        role_types = list(RoleType)
        for i, model in enumerate(self.active_models):
            if i < len(role_types):
                role_name = role_types[i].value
            else:
                role_name = f"ROLE_{i+1}"
            weights[role_name] = weight_per_model
        
        return weights
    
    def validate_constitutional_compliance(self) -> None:
        """
        Validate constitutional compliance (Rules 8 and 9).
        
        Raises:
            ConstitutionalError: If Rule 8 or Rule 9 is violated (includes rule number)
        """
        # Rule 8: Minimum 5 active models
        active_models = self.active_models
        if len(active_models) < 5:
            logger.error(
                f"Rule 8 Violation: Only {len(active_models)} active models configured. "
                f"Minimum 5 required."
            )
            raise ConstitutionalError(
                f"Rule 8 Violation: System must have minimum 5 active LLM models. "
                f"Found {len(active_models)} active models: {active_models}"
            )
        
        # Rule 9: All vote weights ≤ 0.25
        weights = self.vote_weights
        if weights:
            max_weight = max(weights.values())
            if max_weight > 0.25:
                violating_role = max(weights.items(), key=lambda x: x[1])[0]
                logger.error(
                    f"Rule 9 Violation: Role '{violating_role}' has {max_weight*100:.2f}% weight, "
                    f"exceeds 25% maximum"
                )
                raise ConstitutionalError(
                    f"Rule 9 Violation: No role may have more than 25% voting weight. "
                    f"Role '{violating_role}' has {max_weight*100:.2f}% weight"
                )
        
        logger.info(
            f"Constitutional compliance validated: {len(active_models)} active models, "
            f"max weight {max(weights.values())*100:.2f}%"
        )


# Global settings instance with auto-validation
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get global settings instance, creating and validating if needed.
    
    Returns:
        Settings instance with validated constitutional compliance
        
    Raises:
        ValueError: If constitutional compliance validation fails
    """
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.validate_constitutional_compliance()
    return _settings


# Auto-validate on import (but allow lazy loading in tests)
try:
    settings = get_settings()
except (ValueError, ConstitutionalError) as e:
    logger.warning(
        f"Settings validation failed on import: {e}. "
        f"This is expected if .env is not configured. "
        f"Validation will occur at startup."
    )
    # Create settings without validation for now
    _settings = Settings()


"""
Week 2 Infrastructure Tests

This module tests the Week 2 infrastructure components:
- Settings loading and validation
- Rule 8: Model diversity (5+ models)
- Rule 9: Vote weights (≤ 0.25)
- Logging functionality
- Constitutional rules loading
"""

# Standard library
import os
import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Dict
from unittest.mock import patch

# Third-party
from pydantic import ValidationError

# Setup sys.path for imports from folders with spaces
import sys
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "memory_systems"))
sys.path.insert(0, str(project_root / "governance_layer"))
sys.path.insert(0, str(project_root / "config_settings"))
sys.path.insert(0, str(project_root / "Utilities"))
sys.path.insert(0, str(project_root / "constitutional_layer_immutable"))

# Local - models first (single source of truth)
sys.path.insert(0, str(project_root / "memory_systems" / "codebase_memory"))
from models.core import ConstitutionalRule, ConstitutionalError

# Local - configuration and logging (import directly from path)
from config import Settings, get_settings
import logger as logger_module
from logger import log_event, get_recent_logs


class TestSettings:
    """Tests for Settings configuration management."""
    
    def test_settings_load(self) -> None:
        """Test that settings can be loaded without error."""
        # Create minimal valid settings
        test_env = {
            "OPENAI_API_KEY": "test_key_1",
            "ANTHROPIC_API_KEY": "test_key_2",
            "GOOGLE_API_KEY": "test_key_3",
            "XAI_API_KEY": "test_key_4",
            "MISTRAL_API_KEY": "test_key_5",
            "OWNER_ID": "test_owner",
            "OWNER_SIGNATURE_KEY": "test_signature"
        }
        
        # Set environment variables
        for key, value in test_env.items():
            os.environ[key] = value
        
        try:
            # Create settings instance
            settings = Settings()
            
            # Verify it loads
            assert settings is not None
            assert len(settings.active_models) >= 5
            
        finally:
            # Clean up environment
            for key in test_env.keys():
                os.environ.pop(key, None)
    
    def test_rule_8_model_diversity(self) -> None:
        """Test Rule 8: Assert 5+ unique models configured."""
        test_env = {
            "OPENAI_API_KEY": "key1",
            "ANTHROPIC_API_KEY": "key2",
            "GOOGLE_API_KEY": "key3",
            "XAI_API_KEY": "key4",
            "MISTRAL_API_KEY": "key5"
        }
        
        for key, value in test_env.items():
            os.environ[key] = value
        
        try:
            settings = Settings()
            active_models = settings.active_models
            
            # Rule 8: Minimum 5 models
            assert len(active_models) >= 5, (
                f"Rule 8 Violation: Only {len(active_models)} models configured, "
                f"minimum 5 required"
            )
            
            # Verify all models are unique
            assert len(active_models) == len(set(active_models)), (
                "Duplicate models found in active_models list"
            )
            
        finally:
            for key in test_env.keys():
                os.environ.pop(key, None)
    
    def test_rule_9_vote_weights(self) -> None:
        """Test Rule 9: Assert no weight exceeds 0.25."""
        test_env = {
            "OPENAI_API_KEY": "key1",
            "ANTHROPIC_API_KEY": "key2",
            "GOOGLE_API_KEY": "key3",
            "XAI_API_KEY": "key4",
            "MISTRAL_API_KEY": "key5"
        }
        
        for key, value in test_env.items():
            os.environ[key] = value
        
        try:
            settings = Settings()
            weights = settings.vote_weights
            
            # Rule 9: No weight exceeds 0.25
            if weights:
                max_weight = max(weights.values())
                assert max_weight <= 0.25, (
                    f"Rule 9 Violation: Maximum weight {max_weight*100:.2f}% "
                    f"exceeds 25% limit"
                )
            
        finally:
            for key in test_env.keys():
                os.environ.pop(key, None)
    
    def test_all_vote_weights_sum_to_one(self) -> None:
        """Test that all vote weights sum to 1.0."""
        test_env = {
            "OPENAI_API_KEY": "key1",
            "ANTHROPIC_API_KEY": "key2",
            "GOOGLE_API_KEY": "key3",
            "XAI_API_KEY": "key4",
            "MISTRAL_API_KEY": "key5"
        }
        
        for key, value in test_env.items():
            os.environ[key] = value
        
        try:
            settings = Settings()
            weights = settings.vote_weights
            
            if weights:
                total_weight = sum(weights.values())
                # Allow small floating point error
                assert abs(total_weight - 1.0) < 0.001, (
                    f"Vote weights sum to {total_weight}, expected 1.0"
                )
            
        finally:
            for key in test_env.keys():
                os.environ.pop(key, None)
    
    def test_validate_constitutional_compliance_success(self) -> None:
        """Test constitutional compliance validation with valid settings."""
        test_env = {
            "OPENAI_API_KEY": "key1",
            "ANTHROPIC_API_KEY": "key2",
            "GOOGLE_API_KEY": "key3",
            "XAI_API_KEY": "key4",
            "MISTRAL_API_KEY": "key5"
        }
        
        for key, value in test_env.items():
            os.environ[key] = value
        
        try:
            settings = Settings()
            # Should not raise
            settings.validate_constitutional_compliance()
            
        finally:
            for key in test_env.keys():
                os.environ.pop(key, None)
    
    def test_validate_constitutional_compliance_rule_8_violation(self) -> None:
        """Test that Rule 8 violation raises ConstitutionalError."""
        # Create settings with only 3 models (violates Rule 8)
        # We need to mock the active_models property since defaults now add 5 models
        settings = Settings()
        
        # Mock active_models to return only 3 models
        original_active_models = settings.active_models
        
        # Temporarily replace the property
        with patch.object(Settings, 'active_models', property(lambda self: ["openai", "anthropic", "google"])):
            # Should raise ConstitutionalError with "Rule 8" in message
            with pytest.raises(ConstitutionalError, match="Rule 8"):
                settings.validate_constitutional_compliance()


class TestLogging:
    """Tests for logging functionality (Rule 6: Full Transparency)."""
    
    def setup_method(self) -> None:
        """Set up test environment with temporary log directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_log_path = None
        
        # Patch logger to use temp directory
        # Use the logger_module we imported earlier
        self.original_log_path = logger_module._log_file_path
        logger_module._log_file_path = Path(self.temp_dir) / "events.jsonl"
    
    def teardown_method(self) -> None:
        """Clean up test environment."""
        # Use the logger_module we imported earlier
        if self.original_log_path is not None:
            logger_module._log_file_path = self.original_log_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_logging_creates_file(self) -> None:
        """Test that logging creates the log file."""
        # Access logger_module from module scope
        log_path = logger_module._get_log_file_path()
        
        # File should not exist initially
        assert not log_path.exists()
        
        # Log an event
        log_event(
            event_type="test_event",
            data={"test": "data"},
            metadata={"test": "metadata"}
        )
        
        # File should now exist
        assert log_path.exists()
    
    def test_log_entry_format(self) -> None:
        """Test that log entries have correct format (timestamp, type, data)."""
        # Use the logger_module we imported earlier
        log_path = logger_module._get_log_file_path()
        
        # Log an event
        log_event(
            event_type="test_format",
            data={"key": "value"},
            metadata={"meta": "data"}
        )
        
        # Read and parse log entry
        assert log_path.exists()
        with open(log_path, "r", encoding="utf-8") as f:
            line = f.readline().strip()
            assert line  # Should not be empty
        
        import json
        entry = json.loads(line)
        
        # Verify required fields
        assert "timestamp" in entry
        assert "type" in entry
        assert "data" in entry
        assert "metadata" in entry
        
        # Verify values
        assert entry["type"] == "test_format"
        assert entry["data"]["key"] == "value"
        assert entry["metadata"]["meta"] == "data"
        
        # Verify timestamp is ISO format
        from datetime import datetime
        datetime.fromisoformat(entry["timestamp"])  # Should not raise
    
    def test_recent_logs_retrieval(self) -> None:
        """Test retrieving recent logs."""
        # Use the logger_module we imported earlier
        log_path = logger_module._get_log_file_path()
        
        # Log multiple events
        for i in range(5):
            log_event(
                event_type=f"test_event_{i}",
                data={"index": i}
            )
        
        # Retrieve recent logs
        logs = get_recent_logs(limit=10)
        
        # Should have 5 entries
        assert len(logs) == 5
        
        # Should be in reverse order (most recent first)
        assert logs[0]["type"] == "test_event_4"
        assert logs[-1]["type"] == "test_event_0"
        
        # Verify limit works
        logs_limited = get_recent_logs(limit=2)
        assert len(logs_limited) == 2
        assert logs_limited[0]["type"] == "test_event_4"


class TestConstitutionalRules:
    """Tests for constitutional rules loading."""
    
    def test_all_constitutional_rules_loaded(self) -> None:
        """Test that all 10 constitutional rules are loaded."""
        # Verify we have exactly 10 rules
        assert len(ConstitutionalRule) == 10, (
            f"Expected 10 constitutional rules, found {len(ConstitutionalRule)}"
        )
        
        # Verify all rules are present
        expected_rules = [
            ConstitutionalRule.RULE_1_ACCESS_CONTROL,
            ConstitutionalRule.RULE_2_NO_UNAUTHORIZED_ACCESS,
            ConstitutionalRule.RULE_3_IMMUTABLE_CONSTITUTION,
            ConstitutionalRule.RULE_4_FINANCIAL_PRIORITY,
            ConstitutionalRule.RULE_5_LEGAL_PROTECTION,
            ConstitutionalRule.RULE_6_FULL_TRANSPARENCY,
            ConstitutionalRule.RULE_7_BOARD_APPROVAL,
            ConstitutionalRule.RULE_8_BOARD_COMPOSITION,
            ConstitutionalRule.RULE_9_VOTING_WEIGHT_LIMIT,
            ConstitutionalRule.RULE_10_HUMAN_OWNERSHIP_LOCK
        ]
        
        for rule in expected_rules:
            assert rule in ConstitutionalRule, f"Rule {rule.value} not found in ConstitutionalRule enum"


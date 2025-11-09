"""
Comprehensive tests for orchestrator systems.

Tests state machine, LLM router, and full governance cycle.
"""

# Standard library
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys

# Setup sys.path for imports from folders with spaces
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "memory_systems"))
sys.path.insert(0, str(project_root / "governance_layer"))
sys.path.insert(0, str(project_root / "config_settings"))
sys.path.insert(0, str(project_root / "constitutional_layer_immutable"))

# Local - models first (single source of truth)
sys.path.insert(0, str(project_root / "memory_systems" / "codebase_memory"))
from models.core import ConstitutionalError, VoteResult

# Local - orchestrator (import directly from path)
orchestrator_path = project_root / "governance_layer" / "orchestrator"
sys.path.insert(0, str(orchestrator_path))
from langgraph_state_machine import (
    run_governance_cycle,
    conduct_ideation,
    conduct_deliberation,
    conduct_voting,
    execute_decision,
    GovernancePhase,
    GovernanceState
)
from llm_router import call_llm, get_available_providers


@pytest.fixture
def mock_proposal():
    """Create mock proposal for testing."""
    return {
        "id": "test_prop_1",
        "title": "Test Proposal",
        "description": "This is a test proposal",
        "financial_impact": 1000.0,
        "legal_risk": 0.1,
        "keywords": ["test", "proposal"]
    }


@pytest.fixture
def mock_state(mock_proposal):
    """Create mock governance state for testing."""
    return {
        "phase": GovernancePhase.IDEATION,
        "proposal": mock_proposal,
        "owner_signature": "mock_owner_signature",
        "context": None,
        "ideation_result": None,
        "deliberation_result": None,
        "voting_result": None,
        "execution_result": None,
        "validation_results": {},
        "errors": []
    }


class TestStateMachine:
    """Tests for state machine transitions."""
    
    @patch("langgraph_state_machine.build_agent_context")
    @patch("langgraph_state_machine.call_llm")
    @patch("langgraph_state_machine.validate_constitutional_compliance")
    def test_state_machine_transitions(
        self,
        mock_validate,
        mock_llm,
        mock_context,
        mock_state
    ):
        """Test that state machine transitions through all phases."""
        # Mock dependencies
        mock_context.return_value = {
            "constitutional_rules": {},
            "role": "CHAIR",
            "recent_activity_summary": "Summary",
            "relevant_precedents": [],
            "trend_analysis": "Analysis",
            "timestamp": "2024-01-01T00:00:00"
        }
        mock_llm.return_value = "LLM response"
        mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])
        
        # Test ideation
        state = conduct_ideation(mock_state.copy())
        assert state["ideation_result"] is not None
        assert state["phase"] == GovernancePhase.IDEATION
    
    @patch("langgraph_state_machine.validate_constitutional_compliance")
    def test_constitutional_gates(self, mock_validate, mock_state):
        """Test that constitutional gates validate correctly."""
        # Mock validation failure
        mock_validation = MagicMock()
        mock_validation.is_compliant = False
        mock_validation.violated_rules = [1, 2]
        mock_validate.return_value = mock_validation
        
        # Test that gate blocks invalid input
        with pytest.raises(ConstitutionalError, match="Rule.*Violation"):
            with patch("langgraph_state_machine.build_agent_context"):
                with patch("langgraph_state_machine.call_llm"):
                    conduct_ideation(mock_state.copy())
    
    @patch("langgraph_state_machine.build_agent_context")
    def test_gate_blocks_invalid(self, mock_context, mock_state):
        """Test that invalid input is blocked at gate."""
        mock_context.return_value = {
            "constitutional_rules": {},
            "role": "CHAIR",
            "recent_activity_summary": "Summary",
            "relevant_precedents": [],
            "trend_analysis": "Analysis",
            "timestamp": "2024-01-01T00:00:00"
        }
        
        with patch("langgraph_state_machine.call_llm"):
            with patch("langgraph_state_machine.validate_constitutional_compliance") as mock_validate:
                mock_validation = MagicMock()
                mock_validation.is_compliant = False
                mock_validation.violated_rules = [6]
                mock_validate.return_value = mock_validation
                
                with pytest.raises(ConstitutionalError):
                    conduct_ideation(mock_state.copy())
    
    @patch("langgraph_state_machine.build_agent_context")
    def test_memory_context_injection(self, mock_context, mock_state):
        """Test that each state receives memory context."""
        mock_context.return_value = {
            "constitutional_rules": {"rule_1": "Test"},
            "role": "CEO",
            "recent_activity_summary": "Recent activity",
            "relevant_precedents": [{"summary": "Precedent"}],
            "trend_analysis": "Trend analysis",
            "timestamp": "2024-01-01T00:00:00"
        }
        
        with patch("langgraph_state_machine.call_llm"):
            with patch("langgraph_state_machine.validate_constitutional_compliance") as mock_validate:
                mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])
                
                state = conduct_ideation(mock_state.copy())
                
                assert state["context"] is not None
                assert "recent_activity_summary" in state["context"]
                assert "relevant_precedents" in state["context"]


class TestLLMRouter:
    """Tests for LLM router."""
    
    @patch("llm_router.litellm.completion")
    @patch("llm_router.log_event")
    @patch("llm_router.validate_constitutional_compliance")
    def test_llm_router_calls_all_providers(
        self,
        mock_validate,
        mock_log,
        mock_completion
    ):
        """Test that all providers can be called."""
        # Mock dependencies
        mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response"
        mock_completion.return_value = mock_response
        
        # Test all providers
        providers = [
            "openai/gpt-4o",
            "anthropic/claude-3-5-sonnet-20241022",
            "google/gemini-1.5-pro",
            "x-ai/grok-beta",
            "mistralai/mistral-large"
        ]
        
        for provider in providers:
            response = call_llm(provider=provider, prompt="Test prompt")
            assert len(response) > 0
    
    @patch("llm_router.litellm.completion")
    @patch("llm_router.log_event")
    @patch("llm_router.validate_constitutional_compliance")
    def test_llm_router_logs_calls(
        self,
        mock_validate,
        mock_log,
        mock_completion
    ):
        """Test that every LLM call is logged."""
        # Mock dependencies
        mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response"
        mock_completion.return_value = mock_response
        
        # Call LLM
        call_llm(provider="openai/gpt-4o", prompt="Test prompt")
        
        # Verify logging
        assert mock_log.call_count >= 2  # At least attempt and success logs
    
    @patch("llm_router.litellm.completion")
    @patch("llm_router.log_event")
    @patch("llm_router.validate_constitutional_compliance")
    def test_llm_router_retry_logic(
        self,
        mock_validate,
        mock_log,
        mock_completion
    ):
        """Test that router retries on failure."""
        # Mock dependencies
        mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])
        
        # Mock failure then success
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response"
        mock_completion.side_effect = [Exception("Error"), mock_response]
        
        # Call LLM (should retry)
        response = call_llm(provider="openai/gpt-4o", prompt="Test prompt")
        
        # Verify retry
        assert mock_completion.call_count == 2
        assert response == "Response"
    
    @patch("llm_router.get_settings")
    def test_get_available_providers(self, mock_settings):
        """Test that available providers are returned."""
        # Mock settings
        mock_settings_instance = MagicMock()
        mock_settings_instance.active_models = [
            "openai",
            "anthropic",
            "google",
            "xai",
            "mistral"
        ]
        mock_settings.return_value = mock_settings_instance
        
        # Get providers
        providers = get_available_providers()
        
        # Verify providers
        assert len(providers) == 5
        assert "openai/gpt-4o" in providers
        assert "anthropic/claude-3-5-sonnet-20241022" in providers
    
    @patch("llm_router.get_settings")
    def test_get_available_providers_rule_8(self, mock_settings):
        """Test that Rule 8 is enforced (minimum 5 providers)."""
        # Mock settings with fewer than 5 providers
        mock_settings_instance = MagicMock()
        mock_settings_instance.active_models = ["openai", "anthropic"]
        mock_settings.return_value = mock_settings_instance
        
        # Get providers (should raise error)
        with pytest.raises(ConstitutionalError, match="Rule 8 Violation"):
            get_available_providers()


class TestFullGovernanceCycle:
    """Tests for full governance cycle."""
    
    @patch("langgraph_state_machine.conduct_ideation")
    @patch("langgraph_state_machine.conduct_deliberation")
    @patch("langgraph_state_machine.conduct_voting")
    @patch("langgraph_state_machine.execute_decision")
    def test_full_governance_cycle(
        self,
        mock_execute,
        mock_voting,
        mock_deliberation,
        mock_ideation,
        mock_proposal
    ):
        """Test end-to-end governance cycle."""
        # Mock state transitions
        mock_ideation.return_value = {
            "phase": GovernancePhase.DELIBERATION,
            "proposal": mock_proposal,
            "ideation_result": {"ideas": "Test ideas"},
            "validation_results": {},
            "errors": []
        }
        mock_deliberation.return_value = {
            "phase": GovernancePhase.VOTING,
            "proposal": mock_proposal,
            "deliberation_result": {"deliberation": "Test deliberation"},
            "validation_results": {},
            "errors": []
        }
        mock_voting.return_value = {
            "phase": GovernancePhase.EXECUTION,
            "proposal": mock_proposal,
            "voting_result": {"votes": {}},
            "validation_results": {},
            "errors": []
        }
        mock_execute.return_value = {
            "phase": GovernancePhase.EXECUTION,
            "proposal": mock_proposal,
            "execution_result": {"status": "executed"},
            "validation_results": {},
            "errors": []
        }
        
        # Run cycle
        with patch("langgraph_state_machine.StateGraph") as mock_graph:
            mock_app = MagicMock()
            mock_app.invoke = MagicMock(return_value=mock_execute.return_value)
            mock_graph.return_value.compile.return_value = mock_app
            
            result = run_governance_cycle(
                proposal=mock_proposal,
                owner_signature="mock_owner_signature"
            )
            
            # Verify result
            assert result["execution_result"]["status"] == "executed"
    
    @patch("langgraph_state_machine.conduct_ideation")
    def test_governance_cycle_handles_errors(self, mock_ideation, mock_proposal):
        """Test that governance cycle handles errors correctly."""
        # Mock error
        mock_ideation.side_effect = ConstitutionalError("Test error")
        
        # Run cycle (should raise error)
        with patch("langgraph_state_machine.StateGraph") as mock_graph:
            mock_app = MagicMock()
            mock_app.invoke = MagicMock(side_effect=ConstitutionalError("Test error"))
            mock_graph.return_value.compile.return_value = mock_app
            
            with pytest.raises(ConstitutionalError):
                run_governance_cycle(
                    proposal=mock_proposal,
                    owner_signature="mock_owner_signature"
                )

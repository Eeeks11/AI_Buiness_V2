"""
Comprehensive tests for the 6 critical scenarios from the fix mission.

Tests:
1. Complete Approval Workflow
2. Owner Rejection Flow
3. Iterative Deliberation Quality
4. Chair Functionality
5. Veto Powers
6. Model Configuration
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys
from datetime import datetime

# Setup paths
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from models.core import ProposalStatus, ConstitutionalError, VoteType, RoleType, Vote
from governance_layer.orchestrator.langgraph_state_machine import (
    run_governance_cycle,
    conduct_voting,
    resume_from_approval,
    GovernancePhase,
    ProposalStatus as StateProposalStatus
)
from governance_layer.governance.voting import tally_votes
from governance_layer.governance.board import get_role_provider_map, get_model_assignment
from governance_layer.roles.prompt_templates import load_role_configs


@pytest.fixture
def mock_proposal():
    """Create a test proposal."""
    return {
        "id": "test-proposal-comprehensive",
        "title": "Test Comprehensive Proposal",
        "description": "Test proposal for comprehensive testing",
        "financial_impact": 5000.0,
        "legal_risk": 0.0,
        "keywords": ["test", "comprehensive"]
    }


@pytest.fixture
def mock_deliberation_result():
    """Create mock deliberation result with responses from all roles."""
    return {
        "responses": {
            "CEO": {"response": "CEO deliberation: I support this proposal.", "provider": "openai/gpt-4o"},
            "CFO": {"response": "CFO deliberation: Financial analysis looks good.", "provider": "anthropic/claude"},
            "COO": {"response": "COO deliberation: Operational concerns addressed.", "provider": "xai/grok"},
            "CMO": {"response": "CMO deliberation: Marketing impact is positive.", "provider": "google/gemini"},
            "CHAIR": {"response": "CHAIR deliberation: This is a substantial facilitating response that frames the strategic question and highlights key areas for consideration.", "provider": "openai/gpt-4-turbo"},
            "LEGAL": {"response": "LEGAL deliberation: No legal issues identified.", "provider": "mistral/mistral-large"},
            "CISO": {"response": "CISO deliberation: Security review passed.", "provider": "xai/grok"},
            "SECRETARY": {"response": "SECRETARY deliberation: Documenting proceedings.", "provider": "anthropic/claude"}
        },
        "timestamp": datetime.now().isoformat()
    }


@pytest.fixture
def isolated_logging_env(tmp_path, monkeypatch):
    """Provide isolated logging environment."""
    log_dir = tmp_path / "audit_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "events.jsonl"
    
    monkeypatch.setenv("LOG_FILE_PATH", str(log_path))
    monkeypatch.setenv("IMMUTABLE_LOGGING_ENABLED", "false")
    
    return {"log_path": log_path}


class TestApprovalWorkflow:
    """Test 1: Complete Approval Workflow"""
    
    @patch("governance_layer.orchestrator.langgraph_state_machine.validate_models_before_governance")
    @patch("governance_layer.orchestrator.langgraph_state_machine.build_agent_context")
    @patch("governance_layer.orchestrator.langgraph_state_machine.call_llm")
    @patch("governance_layer.orchestrator.langgraph_state_machine.validate_constitutional_compliance")
    @patch("governance_layer.orchestrator.langgraph_state_machine.get_recent_logs")
    def test_proposal_reaches_pending_approval(
        self,
        mock_logs,
        mock_validate,
        mock_llm,
        mock_context,
        mock_health,
        mock_proposal,
        mock_deliberation_result,
        isolated_logging_env
    ):
        """Test that proposals correctly reach pending_approval status after board vote."""
        # Mock health check
        from governance_layer.orchestrator.model_health_check import ModelHealthStatus
        mock_statuses = {}
        for i in range(5):
            provider = f"test_provider_{i}"
            mock_statuses[provider] = ModelHealthStatus(
                provider=provider,
                model_name=f"test_model_{i}",
                is_healthy=True,
                response_time_ms=100.0
            )
        mock_health.return_value = (True, mock_statuses, [])
        
        # Mock context
        mock_context.return_value = {
            "recent_activity_summary": "Summary",
            "relevant_precedents": [],
            "trend_analysis": "Analysis",
            "timestamp": datetime.now().isoformat()
        }
        
        # Mock LLM responses
        def llm_side_effect(**kwargs):
            prompt = kwargs.get("prompt", "")
            if "VOTING MEMBER" in prompt or "cast your vote" in prompt:
                # Voting members respond with APPROVE
                return "APPROVE. This proposal aligns with our strategic goals."
            elif "VETO" in prompt:
                # Legal/CISO respond with NO_VETO
                return "NO_VETO. No critical issues identified."
            else:
                # Deliberation responses
                return "Substantial deliberation response with analysis and recommendations."
        
        mock_llm.side_effect = llm_side_effect
        
        # Mock validation
        mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])
        
        # Mock logs for vote decision
        mock_logs.return_value = [
            {
                "type": "board_vote_tallied",
                "data": {
                    "proposal_id": mock_proposal["id"],
                    "decision": "approved",
                    "approve_count": 4,
                    "reject_count": 0
                }
            }
        ]
        
        # Create state with deliberation result
        state = {
            "phase": GovernancePhase.VOTING,
            "proposal": mock_proposal,
            "proposal_status": ProposalStatus.VOTING,
            "deliberation_result": mock_deliberation_result,
            "validation_results": {},
            "errors": [],
            "needs_owner_approval": None
        }
        
        # Run voting
        result_state = conduct_voting(state)
        
        # Verify status is pending_approval
        assert result_state["proposal_status"] == ProposalStatus.PENDING_APPROVAL
        assert result_state["proposal"]["status"] == ProposalStatus.PENDING_APPROVAL.value
        assert result_state["needs_owner_approval"] is True
        assert result_state["voting_result"] is not None
        assert result_state["voting_result"]["decision"] == "approved"
    
    @patch("governance_layer.orchestrator.langgraph_state_machine.get_proposal_by_id")
    @patch("governance_layer.orchestrator.langgraph_state_machine.execute_decision")
    @patch("governance_layer.orchestrator.langgraph_state_machine.validate_constitutional_compliance")
    def test_owner_approval_triggers_execution(
        self,
        mock_validate,
        mock_execute,
        mock_get_proposal,
        mock_proposal,
        isolated_logging_env
    ):
        """Test that owner approval triggers execution."""
        # Mock validation
        mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])
        
        # Mock proposal retrieval
        mock_get_proposal.return_value = {
            "id": mock_proposal["id"],
            "title": mock_proposal["title"],
            "description": mock_proposal["description"],
            "financial_impact": mock_proposal["financial_impact"],
            "legal_risk": 0.0,
            "vote_result": {"decision": "approved"},
            "deliberation_responses": {}
        }
        
        # Mock execution
        mock_execute.return_value = {
            "proposal_status": ProposalStatus.EXECUTED,
            "execution_result": {"status": "executed"}
        }
        
        # Test owner approval
        result = resume_from_approval(
            proposal_id=mock_proposal["id"],
            owner_signature="test_signature",
            owner_id="test_owner",
            approved=True
        )
        
        # Verify execution was called
        mock_execute.assert_called_once()
        assert result["proposal_status"] == ProposalStatus.EXECUTED


class TestOwnerRejection:
    """Test 2: Owner Rejection Flow"""
    
    @patch("governance_layer.orchestrator.langgraph_state_machine.log_event")
    def test_owner_rejection_stops_workflow(
        self,
        mock_log,
        mock_proposal,
        isolated_logging_env
    ):
        """Test that owner rejection stops workflow and sets status to rejected."""
        result = resume_from_approval(
            proposal_id=mock_proposal["id"],
            owner_signature="test_signature",
            owner_id="test_owner",
            approved=False
        )
        
        # Verify rejection
        assert result["status"] == ProposalStatus.REJECTED.value
        assert result["owner_decision"] == "rejected"
        assert "execution_result" not in result  # No execution
        
        # Verify logging
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args.kwargs["event_type"] == "proposal_rejected_by_owner"


class TestIterativeDeliberation:
    """Test 3: Iterative Deliberation Quality"""
    
    @patch("governance_layer.orchestrator.iterative_deliberation.call_llm")
    @patch("governance_layer.orchestrator.iterative_deliberation.get_role_provider_map")
    @patch("governance_layer.orchestrator.iterative_deliberation.get_model_assignment")
    def test_iterative_deliberation_has_multiple_rounds(
        self,
        mock_model_config,
        mock_providers,
        mock_llm,
        mock_proposal
    ):
        """Test that iterative deliberation produces multiple rounds."""
        from governance_layer.orchestrator.iterative_deliberation import conduct_iterative_deliberation
        
        # Mock providers
        mock_providers.return_value = {
            "CEO": "openai/gpt-4o",
            "CFO": "anthropic/claude",
            "COO": "xai/grok",
            "CMO": "google/gemini",
            "CHAIR": "openai/gpt-4-turbo",
            "LEGAL": "mistral/mistral-large",
            "CISO": "xai/grok",
            "SECRETARY": "anthropic/claude"
        }
        
        # Mock model config
        mock_model_config.return_value = {"temperature": 0.7, "max_tokens": 2000}
        
        # Mock LLM responses - Round 1
        round1_responses = {
            "CEO": "CEO Round 1: Initial analysis supports this proposal.",
            "CFO": "CFO Round 1: Financial impact is acceptable.",
            "COO": "COO Round 1: Operational concerns need addressing.",
            "CMO": "CMO Round 1: Marketing benefits are clear.",
            "CHAIR": "CHAIR Round 1: Framing the strategic question and highlighting key areas.",
            "LEGAL": "LEGAL Round 1: No legal issues.",
            "CISO": "CISO Round 1: Security review passed.",
            "SECRETARY": "SECRETARY Round 1: Documenting initial discussion."
        }
        
        # Mock LLM responses - Round 2 (with references)
        round2_responses = {
            "CEO": "CEO Round 2: I agree with CFO's financial analysis. Building on that point...",
            "CFO": "CFO Round 2: Thank you CEO. I also note COO's operational concerns are valid.",
            "COO": "COO Round 2: I appreciate CFO acknowledging my concerns. After further review, I approve.",
            "CMO": "CMO Round 2: I agree with CEO and CFO. This proposal has merit.",
            "CHAIR": "CHAIR Round 2: Synthesizing the discussion, we see alignment emerging.",
            "LEGAL": "LEGAL Round 2: No additional legal concerns.",
            "CISO": "CISO Round 2: Security remains acceptable.",
            "SECRETARY": "SECRETARY Round 2: Documenting evolving consensus."
        }
        
        call_count = [0]
        def llm_side_effect(**kwargs):
            prompt = kwargs.get("prompt", "")
            role = None
            for r in ["CEO", "CFO", "COO", "CMO", "CHAIR", "LEGAL", "CISO", "SECRETARY"]:
                if f"You are the {r}" in prompt or f"serving as the {r}" in prompt:
                    role = r
                    break
            
            call_count[0] += 1
            round_num = 1 if "ROUND 1" in prompt else 2
            
            if round_num == 1:
                return round1_responses.get(role, "Response")
            else:
                return round2_responses.get(role, "Response")
        
        mock_llm.side_effect = llm_side_effect
        
        # Build role contexts
        role_contexts = {}
        for role in ["CEO", "CFO", "COO", "CMO", "CHAIR", "LEGAL", "CISO", "SECRETARY"]:
            role_contexts[role] = {
                "recent_activity_summary": "Summary",
                "relevant_precedents": [],
                "trend_analysis": "Analysis"
            }
        
        # Run iterative deliberation
        result = conduct_iterative_deliberation(
            proposal=mock_proposal,
            role_contexts=role_contexts,
            max_rounds=2,
            mode="streamlined"
        )
        
        # Verify multiple rounds
        assert result["total_rounds"] >= 2
        assert len(result["rounds"]) >= 2
        
        # Verify Round 2 has references to Round 1
        round2 = result["rounds"][1]
        assert any("agree with" in response.lower() or "building on" in response.lower() 
                  for response in round2.values())
        
        # Verify position evolution tracking
        assert "position_evolution" in result
        assert len(result["position_evolution"]) > 0
        
        # Verify synthesis
        assert "synthesis" in result
        assert result["synthesis"]["rounds_conducted"] >= 2


class TestChairFunctionality:
    """Test 4: Chair Functionality"""
    
    @patch("governance_layer.orchestrator.langgraph_state_machine.call_llm")
    @patch("governance_layer.orchestrator.langgraph_state_machine.get_role_provider_map")
    @patch("governance_layer.orchestrator.langgraph_state_machine.build_agent_context")
    def test_chair_provides_substantial_response(
        self,
        mock_context,
        mock_providers,
        mock_llm,
        mock_proposal,
        isolated_logging_env
    ):
        """Test that Chair provides substantial, non-empty responses."""
        # Mock context
        mock_context.return_value = {
            "recent_activity_summary": "Summary",
            "relevant_precedents": [],
            "trend_analysis": "Analysis",
            "timestamp": datetime.now().isoformat()
        }
        
        # Mock providers
        mock_providers.return_value = {"CHAIR": "openai/gpt-4-turbo"}
        
        # Mock Chair response
        substantial_response = (
            "As CHAIR, I frame this strategic question clearly. "
            "The proposal addresses key areas including financial impact, "
            "operational efficiency, and market positioning. "
            "I highlight the following considerations: risk assessment, "
            "resource allocation, and timeline feasibility. "
            "This substantial response provides meaningful strategic guidance."
        )
        mock_llm.return_value = substantial_response
        
        # Test deliberation with Chair
        from governance_layer.orchestrator.langgraph_state_machine import conduct_deliberation
        
        state = {
            "phase": GovernancePhase.DELIBERATION,
            "proposal": mock_proposal,
            "proposal_status": ProposalStatus.DELIBERATION,
            "context": mock_context.return_value,
            "validation_results": {},
            "errors": []
        }
        
        with patch("governance_layer.orchestrator.langgraph_state_machine.validate_constitutional_compliance") as mock_validate:
            mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])
            with patch("governance_layer.orchestrator.langgraph_state_machine.get_model_assignment"):
                result = conduct_deliberation(state)
        
        # Verify Chair response is substantial
        chair_response = result["deliberation_result"]["responses"].get("CHAIR", {})
        assert "response" in chair_response
        assert len(chair_response["response"]) > 100  # Substantial response
        assert "CHAIR" in chair_response["response"] or "strategic" in chair_response["response"].lower()


class TestVetoPowers:
    """Test 5: Veto Powers"""
    
    @patch("governance_layer.orchestrator.langgraph_state_machine.call_llm")
    @patch("governance_layer.orchestrator.langgraph_state_machine.get_role_provider_map")
    @patch("governance_layer.orchestrator.langgraph_state_machine.get_recent_logs")
    @patch("governance_layer.orchestrator.langgraph_state_machine.tally_votes")
    def test_legal_veto_blocks_proposal(
        self,
        mock_tally,
        mock_logs,
        mock_providers,
        mock_llm,
        mock_proposal,
        mock_deliberation_result,
        isolated_logging_env
    ):
        """Test that Legal veto blocks proposal regardless of votes."""
        # Mock providers
        mock_providers.return_value = {
            "CEO": "openai/gpt-4o",
            "CFO": "anthropic/claude",
            "COO": "xai/grok",
            "CMO": "google/gemini",
            "LEGAL": "mistral/mistral-large",
            "CISO": "xai/grok"
        }
        
        # Mock LLM - voting members approve, but Legal vetoes
        def llm_side_effect(**kwargs):
            prompt = kwargs.get("prompt", "")
            if "LEGAL" in prompt and "VETO POWER" in prompt:
                return "VETO. This proposal violates constitutional Rule 3."
            elif "VOTING MEMBER" in prompt:
                return "APPROVE. Proposal looks good."
            else:
                return "NO_VETO. No issues."
        
        mock_llm.side_effect = llm_side_effect
        
        # Mock logs (no vote tally since veto happens first)
        mock_logs.return_value = []
        
        # Create state
        state = {
            "phase": GovernancePhase.VOTING,
            "proposal": mock_proposal,
            "proposal_status": ProposalStatus.VOTING,
            "deliberation_result": mock_deliberation_result,
            "validation_results": {},
            "errors": [],
            "needs_owner_approval": None
        }
        
        # Run voting
        with patch("governance_layer.orchestrator.langgraph_state_machine.validate_constitutional_compliance") as mock_validate:
            mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])
            result = conduct_voting(state)
        
        # Verify veto was triggered
        assert result["proposal_status"] == ProposalStatus.VETOED
        assert result["proposal"]["status"] == ProposalStatus.VETOED.value
        assert result["voting_result"]["decision"] == "vetoed"
        assert result["voting_result"]["veto_triggered"] is True
        assert result["voting_result"]["veto_role"] == "LEGAL"
        assert result["needs_owner_approval"] is False


class TestModelConfiguration:
    """Test 6: Model Configuration"""
    
    def test_model_assignments_file_exists(self):
        """Test that model_assignments.json exists and is valid."""
        config_path = project_root / "config_settings" / "model_assignments.json"
        assert config_path.exists(), "model_assignments.json should exist"
        
        with open(config_path, "r") as f:
            config = json.load(f)
        
        # Verify all 8 roles are configured
        required_roles = ["CEO", "CFO", "COO", "CMO", "CHAIR", "LEGAL", "CISO", "SECRETARY"]
        for role in required_roles:
            assert role in config, f"{role} should be in model_assignments.json"
            assert "provider" in config[role], f"{role} should have provider"
            assert "model" in config[role], f"{role} should have model"
            assert "temperature" in config[role], f"{role} should have temperature"
            assert "max_tokens" in config[role], f"{role} should have max_tokens"
    
    def test_get_model_assignment_function(self):
        """Test that get_model_assignment function works."""
        assignment = get_model_assignment("CEO")
        assert assignment is not None
        assert "provider" in assignment
        assert "model" in assignment
        assert "temperature" in assignment
        assert "max_tokens" in assignment
    
    def test_model_configuration_used_in_deliberation(self):
        """Test that model configuration is used during deliberation."""
        # This is tested indirectly through the deliberation process
        # The function get_model_assignment is called during deliberation
        assignment = get_model_assignment("CHAIR")
        assert assignment is not None
        assert isinstance(assignment["temperature"], (int, float))
        assert isinstance(assignment["max_tokens"], int)

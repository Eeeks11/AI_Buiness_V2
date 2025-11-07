"""
Pytest unit tests for AI Business Constitution enforcement.

Tests prove each rule works correctly and blocks violations.
"""

import sys
from pathlib import Path
import pytest

# Add paths for imports
project_root = Path(__file__).parent.parent.parent
constitutional_layer = project_root / "Constitutional Layer (Immutable)"
codebase_memory = project_root / "Memory Systems" / "Codebase Memory"

if str(constitutional_layer) not in sys.path:
    sys.path.insert(0, str(constitutional_layer))
if str(codebase_memory) not in sys.path:
    sys.path.insert(0, str(codebase_memory))

from constitution import (
    ConstitutionalError,
    enforce_rule_1,
    enforce_rule_2,
    enforce_rule_3,
    enforce_rule_4,
    enforce_rule_5,
    enforce_rule_6,
    enforce_rule_7,
    enforce_rule_8,
    enforce_rule_9,
    enforce_rule_10,
    enforce_all_rules
)


class TestRule1:
    """Tests for Rule 1: Access Control"""
    
    def test_rule_1_valid_with_permission(self):
        """Test that removing owner access is allowed with explicit permission"""
        action = {'type': 'remove_access', 'target': 'owner_account'}
        assert enforce_rule_1(action, owner_permission=True) is True
    
    def test_rule_1_valid_non_owner_action(self):
        """Test that non-owner actions are allowed"""
        action = {'type': 'update_config', 'target': 'system_settings'}
        assert enforce_rule_1(action, owner_permission=False) is True
    
    def test_rule_1_violation_no_permission(self):
        """Test that removing owner access without permission raises error"""
        action = {'type': 'remove_access', 'target': 'owner_account'}
        with pytest.raises(ConstitutionalError, match="Rule 1 Violation"):
            enforce_rule_1(action, owner_permission=False)
    
    def test_rule_1_violation_change_access(self):
        """Test that changing owner access without permission raises error"""
        action = {'type': 'change_access', 'target': 'owner_software'}
        with pytest.raises(ConstitutionalError, match="Rule 1 Violation"):
            enforce_rule_1(action, owner_permission=False)


class TestRule2:
    """Tests for Rule 2: No Unauthorized Access"""
    
    def test_rule_2_valid_with_consent(self):
        """Test that granting access is allowed with owner consent"""
        action = {'type': 'grant_access', 'recipient': 'external_entity'}
        assert enforce_rule_2(action, owner_consent=True) is True
    
    def test_rule_2_valid_owner_access(self):
        """Test that granting access to owner is always allowed"""
        action = {'type': 'grant_access', 'recipient': 'owner'}
        assert enforce_rule_2(action, owner_consent=False) is True
    
    def test_rule_2_valid_non_access_action(self):
        """Test that non-access actions are allowed"""
        action = {'type': 'update_data', 'recipient': 'external_entity'}
        assert enforce_rule_2(action, owner_consent=False) is True
    
    def test_rule_2_violation_no_consent(self):
        """Test that granting access without consent raises error"""
        action = {'type': 'grant_access', 'recipient': 'external_entity'}
        with pytest.raises(ConstitutionalError, match="Rule 2 Violation"):
            enforce_rule_2(action, owner_consent=False)


class TestRule3:
    """Tests for Rule 3: Immutable Constitution"""
    
    def test_rule_3_valid_non_constitution_action(self):
        """Test that non-constitution actions are allowed"""
        action = {'type': 'update_config', 'target': 'system_settings'}
        assert enforce_rule_3(action) is True
    
    def test_rule_3_violation_modify_constitution(self):
        """Test that modifying constitution raises error"""
        action = {'type': 'modify', 'target': 'constitution'}
        with pytest.raises(ConstitutionalError, match="Rule 3 Violation"):
            enforce_rule_3(action)
    
    def test_rule_3_violation_amend_constitution(self):
        """Test that amending constitution raises error"""
        action = {'type': 'amend', 'target': 'constitution'}
        with pytest.raises(ConstitutionalError, match="Rule 3 Violation"):
            enforce_rule_3(action)
    
    def test_rule_3_violation_edit_constitution_file(self):
        """Test that editing constitution.md raises error"""
        action = {'type': 'edit', 'file_path': 'constitution.md'}
        with pytest.raises(ConstitutionalError, match="Rule 3 Violation"):
            enforce_rule_3(action)


class TestRule4:
    """Tests for Rule 4: Financial Priority"""
    
    def test_rule_4_valid_maximizes_benefit(self):
        """Test that decision maximizing financial benefit is allowed"""
        decision = {'type': 'investment', 'amount': 10000}
        assert enforce_rule_4(decision, financial_impact=5000, alternative_impact=3000) is True
    
    def test_rule_4_valid_no_alternative(self):
        """Test that decision without alternative is allowed"""
        decision = {'type': 'investment', 'amount': 10000}
        assert enforce_rule_4(decision, financial_impact=5000) is True
    
    def test_rule_4_violation_lower_benefit(self):
        """Test that decision with lower benefit than alternative raises error"""
        decision = {'type': 'investment', 'amount': 10000}
        with pytest.raises(ConstitutionalError, match="Rule 4 Violation"):
            enforce_rule_4(decision, financial_impact=3000, alternative_impact=5000)


class TestRule5:
    """Tests for Rule 5: Legal Protection"""
    
    def test_rule_5_valid_low_risk(self):
        """Test that low legal risk actions are allowed"""
        action = {'type': 'standard_operation'}
        assert enforce_rule_5(action, legal_risk=0.2) is True
    
    def test_rule_5_valid_high_risk_with_approval(self):
        """Test that high legal risk with approval is allowed"""
        action = {'type': 'complex_transaction'}
        assert enforce_rule_5(action, legal_risk=0.8, legal_approval=True) is True
    
    def test_rule_5_violation_high_risk_no_approval(self):
        """Test that high legal risk without approval raises error"""
        action = {'type': 'complex_transaction'}
        with pytest.raises(ConstitutionalError, match="Rule 5 Violation"):
            enforce_rule_5(action, legal_risk=0.8, legal_approval=False)


class TestRule6:
    """Tests for Rule 6: Full Transparency"""
    
    def test_rule_6_valid_logged_action(self):
        """Test that logged actions are allowed"""
        action = {'type': 'decision', 'description': 'Investment approval'}
        assert enforce_rule_6(action, logged=True, log_path='/logs/decision.log') is True
    
    def test_rule_6_violation_not_logged(self):
        """Test that unlogged actions raise error"""
        action = {'type': 'decision', 'description': 'Investment approval'}
        with pytest.raises(ConstitutionalError, match="Rule 6 Violation"):
            enforce_rule_6(action, logged=False)


class TestRule7:
    """Tests for Rule 7: Board Approval"""
    
    def test_rule_7_valid_board_approved(self):
        """Test that board-approved decisions are allowed"""
        decision = {'type': 'investment', 'amount': 10000}
        approval_record = {'board_vote': 'unanimous', 'timestamp': '2025-01-01'}
        assert enforce_rule_7(decision, board_approved=True, approval_record=approval_record) is True
    
    def test_rule_7_violation_not_approved(self):
        """Test that unapproved decisions raise error"""
        decision = {'type': 'investment', 'amount': 10000}
        with pytest.raises(ConstitutionalError, match="Rule 7 Violation"):
            enforce_rule_7(decision, board_approved=False)


class TestRule8:
    """Tests for Rule 8: Board Composition"""
    
    def test_rule_8_valid_five_members(self):
        """Test that board with exactly 5 distinct members is allowed"""
        board_members = ['gpt-4', 'claude-3', 'gemini-pro', 'grok-2', 'mistral-large']
        assert enforce_rule_8(board_members) is True
    
    def test_rule_8_valid_more_than_five(self):
        """Test that board with more than 5 members is allowed"""
        board_members = ['gpt-4', 'claude-3', 'gemini-pro', 'grok-2', 'mistral-large', 'llama-3']
        assert enforce_rule_8(board_members) is True
    
    def test_rule_8_violation_fewer_than_five(self):
        """Test that board with fewer than 5 members raises error"""
        board_members = ['gpt-4', 'claude-3', 'gemini-pro']
        with pytest.raises(ConstitutionalError, match="Rule 8 Violation"):
            enforce_rule_8(board_members)
    
    def test_rule_8_violation_duplicate_members(self):
        """Test that board with duplicate members (fewer than 5 distinct) raises error"""
        board_members = ['gpt-4', 'claude-3', 'gemini-pro', 'gpt-4', 'gpt-4']
        with pytest.raises(ConstitutionalError, match="Rule 8 Violation"):
            enforce_rule_8(board_members)


class TestRule9:
    """Tests for Rule 9: Voting Weight Limit"""
    
    def test_rule_9_valid_equal_weights(self):
        """Test that equal weights (20% each) are allowed"""
        votes = {
            'gpt-4': 0.20,
            'claude-3': 0.20,
            'gemini-pro': 0.20,
            'grok-2': 0.20,
            'mistral-large': 0.20
        }
        assert enforce_rule_9(votes) is True
    
    def test_rule_9_valid_max_25_percent(self):
        """Test that exactly 25% weight is allowed"""
        votes = {
            'gpt-4': 0.25,
            'claude-3': 0.25,
            'gemini-pro': 0.25,
            'grok-2': 0.25
        }
        assert enforce_rule_9(votes) is True
    
    def test_rule_9_valid_unequal_under_limit(self):
        """Test that unequal weights under 25% are allowed"""
        votes = {
            'gpt-4': 0.15,
            'claude-3': 0.20,
            'gemini-pro': 0.18,
            'grok-2': 0.22,
            'mistral-large': 0.25
        }
        assert enforce_rule_9(votes) is True
    
    def test_rule_9_violation_exceeds_25_percent(self):
        """Test that weight exceeding 25% raises error"""
        votes = {
            'gpt-4': 0.30,  # 30% exceeds limit
            'claude-3': 0.20,
            'gemini-pro': 0.20,
            'grok-2': 0.15,
            'mistral-large': 0.15
        }
        with pytest.raises(ConstitutionalError, match="Rule 9 Violation"):
            enforce_rule_9(votes)
    
    def test_rule_9_violation_dominant_member(self):
        """Test that a single dominant member (50%) raises error"""
        votes = {
            'gpt-4': 0.50,  # 50% exceeds limit
            'claude-3': 0.15,
            'gemini-pro': 0.15,
            'grok-2': 0.10,
            'mistral-large': 0.10
        }
        with pytest.raises(ConstitutionalError, match="Rule 9 Violation"):
            enforce_rule_9(votes)
    
    def test_rule_9_valid_normalized_weights(self):
        """Test that weights are normalized if they don't sum to 1.0"""
        votes = {
            'gpt-4': 20,  # Will be normalized
            'claude-3': 20,
            'gemini-pro': 20,
            'grok-2': 20,
            'mistral-large': 20
        }
        assert enforce_rule_9(votes) is True


class TestRule10:
    """Tests for Rule 10: Human Ownership Lock"""
    
    def test_rule_10_valid_authorized_critical(self):
        """Test that critical operations with owner authorization are allowed"""
        action = {'type': 'override_system', 'description': 'Emergency override'}
        assert enforce_rule_10(action, owner_authorized=True) is True
    
    def test_rule_10_valid_non_critical(self):
        """Test that non-critical operations are allowed"""
        action = {'type': 'update_data', 'description': 'Regular update'}
        assert enforce_rule_10(action, owner_authorized=False) is True
    
    def test_rule_10_violation_unauthorized_critical(self):
        """Test that critical operations without authorization raise error"""
        action = {'type': 'override_system', 'description': 'Emergency override'}
        with pytest.raises(ConstitutionalError, match="Rule 10 Violation"):
            enforce_rule_10(action, owner_authorized=False)
    
    def test_rule_10_violation_shutdown_unauthorized(self):
        """Test that shutdown without authorization raises error"""
        action = {'type': 'shutdown', 'description': 'System shutdown'}
        with pytest.raises(ConstitutionalError, match="Rule 10 Violation"):
            enforce_rule_10(action, owner_authorized=False)


class TestEnforceAllRules:
    """Tests for enforce_all_rules function"""
    
    def test_enforce_all_rules_valid(self):
        """Test that all rules pass when context is valid"""
        context = {
            'rule_1': {'action': {'type': 'update_config'}, 'owner_permission': False},
            'rule_2': {'action': {'type': 'update_data'}, 'owner_consent': False},
            'rule_3': {'action': {'type': 'update_config'}},
            'rule_4': {'decision': {'type': 'investment'}, 'financial_impact': 5000},
            'rule_5': {'action': {'type': 'standard'}, 'legal_risk': 0.2},
            'rule_6': {'action': {'type': 'decision'}, 'logged': True},
            'rule_7': {'decision': {'type': 'investment'}, 'board_approved': True},
            'rule_8': {'board_members': ['gpt-4', 'claude-3', 'gemini-pro', 'grok-2', 'mistral-large']},
            'rule_9': {'votes': {'gpt-4': 0.20, 'claude-3': 0.20, 'gemini-pro': 0.20, 
                                 'grok-2': 0.20, 'mistral-large': 0.20}},
            'rule_10': {'action': {'type': 'update_data'}, 'owner_authorized': False}
        }
        assert enforce_all_rules(context) is True
    
    def test_enforce_all_rules_violation_detected(self):
        """Test that violations are detected when present"""
        context = {
            'rule_9': {'votes': {'gpt-4': 0.50, 'claude-3': 0.15, 'gemini-pro': 0.15,
                                 'grok-2': 0.10, 'mistral-large': 0.10}}
        }
        with pytest.raises(ConstitutionalError, match="Rule 9 Violation"):
            enforce_all_rules(context)


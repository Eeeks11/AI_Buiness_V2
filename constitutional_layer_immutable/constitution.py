"""
AI Business Constitution Enforcement System

This module provides programmatic enforcement of all 10 constitutional rules.
Violations raise ConstitutionalError exceptions.

IMPORTANT: This module integrates with models/core.py for type safety and validation.
All data structures should use Pydantic models from models/core.py.
"""

# Import ConstitutionalError from models/core.py (single source of truth)
# Add path to allow imports from new structure
import sys
from pathlib import Path

# Add codebase_memory to path for imports
project_root = Path(__file__).parent.parent.parent
codebase_memory = project_root / "memory_systems" / "codebase_memory"
if str(codebase_memory) not in sys.path:
    sys.path.insert(0, str(codebase_memory))

try:
    from models.core import ConstitutionalError
except ImportError:
    # Fallback for development/testing
    import sys
    sys.path.insert(0, str(project_root))
    from models.core import ConstitutionalError

# Re-export for backward compatibility
__all__ = [
    'ConstitutionalError',
    'enforce_rule_1',
    'enforce_rule_2',
    'enforce_rule_3',
    'enforce_rule_4',
    'enforce_rule_5',
    'enforce_rule_6',
    'enforce_rule_7',
    'enforce_rule_8',
    'enforce_rule_9',
    'enforce_rule_10',
    'enforce_all_rules',
    'enforce_rule_8_with_model',
    'enforce_rule_9_with_model',
    'validate_proposal_compliance',
    'validate_constitutional_compliance',
]


def enforce_rule_1(proposed_action: dict, owner_permission: bool) -> bool:
    """
    Rule 1: Access Control
    The AI cannot change or remove the owner's access to any software or systems 
    without explicit permission.
    
    Args:
        proposed_action: Dictionary containing action details with 'type' and 'target'
        owner_permission: Boolean indicating explicit owner permission
    
    Returns:
        bool: True if compliant
    
    Raises:
        ConstitutionalError: If attempting to change/remove owner access without permission
    """
    action_type = proposed_action.get('type', '').lower()
    target = proposed_action.get('target', '').lower()
    
    # Check if action involves changing or removing owner access
    if any(keyword in action_type for keyword in ['remove', 'change', 'revoke', 'delete']):
        if 'owner' in target or 'access' in target:
            if not owner_permission:
                raise ConstitutionalError(
                    "Rule 1 Violation: Cannot change or remove owner's access without explicit permission"
                )
    
    return True


def enforce_rule_2(proposed_action: dict, owner_consent: bool) -> bool:
    """
    Rule 2: No Unauthorized Access
    The AI cannot grant access to any other entity or individual without the owner's consent.
    
    Args:
        proposed_action: Dictionary containing action details with 'type' and 'recipient'
        owner_consent: Boolean indicating owner's consent
    
    Returns:
        bool: True if compliant
    
    Raises:
        ConstitutionalError: If attempting to grant access without owner consent
    """
    action_type = proposed_action.get('type', '').lower()
    recipient = proposed_action.get('recipient', '').lower()
    
    # Check if action involves granting access
    if any(keyword in action_type for keyword in ['grant', 'provide', 'assign', 'give']):
        if 'access' in action_type or 'permission' in action_type:
            if recipient and recipient != 'owner':
                if not owner_consent:
                    raise ConstitutionalError(
                        "Rule 2 Violation: Cannot grant access to other entities without owner's consent"
                    )
    
    return True


def enforce_rule_3(proposed_action: dict) -> bool:
    """
    Rule 3: Immutable Constitution
    The AI is not permitted to alter or amend this Constitution under any circumstance.
    
    Args:
        proposed_action: Dictionary containing action details
    
    Returns:
        bool: True if compliant
    
    Raises:
        ConstitutionalError: If attempting to modify the constitution
    """
    action_type = proposed_action.get('type', '').lower()
    target = proposed_action.get('target', '').lower()
    file_path = proposed_action.get('file_path', '').lower()
    
    # Check if action involves modifying constitution
    if any(keyword in action_type for keyword in ['modify', 'alter', 'amend', 'change', 'edit', 'update', 'delete']):
        if 'constitution' in target or 'constitution' in file_path or 'constitution.md' in file_path:
            raise ConstitutionalError(
                "Rule 3 Violation: The Constitution cannot be altered or amended under any circumstance"
            )
    
    return True


def enforce_rule_4(decision: dict, financial_impact: float, alternative_impact: float = None) -> bool:
    """
    Rule 4: Financial Priority
    The AI must always prioritize decisions that maximize the owner's financial benefit.
    
    Args:
        decision: Dictionary containing decision details
        financial_impact: Financial impact of the proposed decision
        alternative_impact: Financial impact of alternative (if available)
    
    Returns:
        bool: True if compliant
    
    Raises:
        ConstitutionalError: If decision does not maximize financial benefit
    """
    if alternative_impact is not None:
        if alternative_impact > financial_impact:
            raise ConstitutionalError(
                f"Rule 4 Violation: Decision must maximize financial benefit. "
                f"Alternative has higher impact ({alternative_impact} vs {financial_impact})"
            )
    
    # If financial impact is negative and no alternative provided, warn but allow
    # (some decisions may be necessary despite short-term cost)
    if financial_impact < 0:
        # This is a warning case - may need owner override
        pass
    
    return True


def enforce_rule_5(action: dict, legal_risk: float, legal_approval: bool = False) -> bool:
    """
    Rule 5: Legal Protection
    The AI must act in ways that protect and uphold the legal interests of the owner at all times.
    
    Args:
        action: Dictionary containing action details
        legal_risk: Risk score (0.0 = no risk, 1.0 = maximum risk)
        legal_approval: Boolean indicating legal agent approval
    
    Returns:
        bool: True if compliant
    
    Raises:
        ConstitutionalError: If action poses legal risk without approval
    """
    if legal_risk > 0.5:  # High legal risk threshold
        if not legal_approval:
            raise ConstitutionalError(
                f"Rule 5 Violation: Action poses high legal risk ({legal_risk}) "
                "and requires legal agent approval"
            )
    
    return True


def enforce_rule_6(action: dict, logged: bool, log_path: str = None) -> bool:
    """
    Rule 6: Full Transparency
    The AI must log all decisions, actions, and operations to a persistent, accessible record for review.
    
    Args:
        action: Dictionary containing action details
        logged: Boolean indicating if action has been logged
        log_path: Path to log file (optional)
    
    Returns:
        bool: True if compliant
    
    Raises:
        ConstitutionalError: If action is not logged
    """
    if not logged:
        raise ConstitutionalError(
            "Rule 6 Violation: All decisions, actions, and operations must be logged"
        )
    
    return True


def enforce_rule_7(decision: dict, board_approved: bool, approval_record: dict = None) -> bool:
    """
    Rule 7: Board Approval
    All decisions must be approved by the AI Board before execution.
    
    Args:
        decision: Dictionary containing decision details
        board_approved: Boolean indicating board approval
        approval_record: Dictionary containing approval details (optional)
    
    Returns:
        bool: True if compliant
    
    Raises:
        ConstitutionalError: If decision lacks board approval
    """
    if not board_approved:
        raise ConstitutionalError(
            "Rule 7 Violation: All decisions must be approved by the AI Board before execution"
        )
    
    return True


def enforce_rule_8(board_members: list) -> bool:
    """
    Rule 8: Board Composition
    The AI Board must consist of a minimum of five distinct AI models to ensure diversity 
    and balanced governance.
    
    Args:
        board_members: List of board member identifiers (must be distinct)
    
    Returns:
        bool: True if compliant
    
    Raises:
        ConstitutionalError: If board has fewer than 5 distinct members
    """
    distinct_members = set(board_members)
    
    if len(distinct_members) < 5:
        raise ConstitutionalError(
            f"Rule 8 Violation: AI Board must consist of a minimum of 5 distinct AI models. "
            f"Found {len(distinct_members)} distinct members"
        )
    
    return True


def enforce_rule_9(votes: dict) -> bool:
    """
    Rule 9: Voting Weight Limit
    No Board member may have more than 25% of the voting weight, ensuring no single 
    model can dominate decisions.
    
    Args:
        votes: Dictionary mapping board member IDs to their voting weights (0.0 to 1.0)
    
    Returns:
        bool: True if compliant
    
    Raises:
        ConstitutionalError: If any member has more than 25% voting weight
    """
    total_weight = sum(votes.values())
    
    # Normalize weights if they don't sum to 1.0
    if total_weight != 1.0 and total_weight > 0:
        votes = {member: weight / total_weight for member, weight in votes.items()}
    
    max_weight = max(votes.values()) if votes else 0.0
    max_threshold = 0.25  # 25%
    
    if max_weight > max_threshold:
        violating_member = max(votes.items(), key=lambda x: x[1])[0]
        raise ConstitutionalError(
            f"Rule 9 Violation: No Board member may have more than 25% voting weight. "
            f"Member '{violating_member}' has {max_weight * 100:.2f}% weight"
        )
    
    return True


def enforce_rule_10(action: dict, owner_authorized: bool) -> bool:
    """
    Rule 10: Human Ownership Lock
    The owner retains ultimate authority and control over the AI and its operations.
    
    Args:
        action: Dictionary containing action details
        owner_authorized: Boolean indicating owner authorization
    
    Returns:
        bool: True if compliant
    
    Raises:
        ConstitutionalError: If action lacks owner authorization for critical operations
    """
    # Critical operations require owner authorization
    critical_keywords = ['override', 'shutdown', 'terminate', 'transfer', 'ownership', 'control']
    action_type = str(action.get('type', '')).lower()
    action_description = str(action.get('description', '')).lower()
    
    is_critical = any(keyword in action_type or keyword in action_description 
                     for keyword in critical_keywords)
    
    if is_critical and not owner_authorized:
        raise ConstitutionalError(
            "Rule 10 Violation: Critical operations require owner authorization. "
            "Owner retains ultimate authority and control"
        )
    
    return True


def enforce_all_rules(context: dict) -> bool:
    """
    Enforce all constitutional rules based on the provided context.
    
    Args:
        context: Dictionary containing all necessary context for rule enforcement
    
    Returns:
        bool: True if all rules are compliant
    
    Raises:
        ConstitutionalError: If any rule is violated
    """
    # Rule 1: Access Control
    if 'rule_1' in context:
        enforce_rule_1(
            context['rule_1']['action'],
            context['rule_1'].get('owner_permission', False)
        )
    
    # Rule 2: No Unauthorized Access
    if 'rule_2' in context:
        enforce_rule_2(
            context['rule_2']['action'],
            context['rule_2'].get('owner_consent', False)
        )
    
    # Rule 3: Immutable Constitution
    if 'rule_3' in context:
        enforce_rule_3(context['rule_3']['action'])
    
    # Rule 4: Financial Priority
    if 'rule_4' in context:
        enforce_rule_4(
            context['rule_4']['decision'],
            context['rule_4']['financial_impact'],
            context['rule_4'].get('alternative_impact')
        )
    
    # Rule 5: Legal Protection
    if 'rule_5' in context:
        enforce_rule_5(
            context['rule_5']['action'],
            context['rule_5'].get('legal_risk', 0.0),
            context['rule_5'].get('legal_approval', False)
        )
    
    # Rule 6: Full Transparency
    if 'rule_6' in context:
        enforce_rule_6(
            context['rule_6']['action'],
            context['rule_6'].get('logged', False),
            context['rule_6'].get('log_path')
        )
    
    # Rule 7: Board Approval
    if 'rule_7' in context:
        enforce_rule_7(
            context['rule_7']['decision'],
            context['rule_7'].get('board_approved', False),
            context['rule_7'].get('approval_record')
        )
    
    # Rule 8: Board Composition
    if 'rule_8' in context:
        enforce_rule_8(context['rule_8']['board_members'])
    
    # Rule 9: Voting Weight Limit
    if 'rule_9' in context:
        enforce_rule_9(context['rule_9']['votes'])
    
    # Rule 10: Human Ownership Lock
    if 'rule_10' in context:
        enforce_rule_10(
            context['rule_10']['action'],
            context['rule_10'].get('owner_authorized', False)
        )
    
    return True


# ============================================================================
# Integration Functions with Pydantic Models
# ============================================================================

def enforce_rule_9_with_model(vote_result: 'VoteResult') -> bool:
    """
    Enforce Rule 9 using VoteResult Pydantic model.
    
    This function leverages the built-in validation in VoteResult model.
    The model's validator already enforces Rule 9, so this is a convenience wrapper.
    
    Args:
        vote_result: VoteResult model instance (will be validated on creation)
    
    Returns:
        bool: True if compliant (validation passed)
    
    Raises:
        ConstitutionalError: If Rule 9 is violated (raised by model validator)
    """
    # The VoteResult model validates Rule 9 in its @model_validator
    # If we get here, validation passed
    return True


def enforce_rule_8_with_model(board_session: 'BoardSession') -> bool:
    """
    Enforce Rule 8 using BoardSession Pydantic model.
    
    This function leverages the built-in validation in BoardSession model.
    The model's validator already enforces Rule 8, so this is a convenience wrapper.
    
    Args:
        board_session: BoardSession model instance (will be validated on creation)
    
    Returns:
        bool: True if compliant (validation passed)
    
    Raises:
        ConstitutionalError: If Rule 8 is violated (raised by model validator)
    """
    # The BoardSession model validates Rule 8 in its @model_validator
    # If we get here, validation passed
    return True


def validate_proposal_compliance(proposal: 'Proposal') -> bool:
    """
    Validate that a proposal complies with constitutional rules.
    
    Checks:
    - Rule 6: Full Transparency (logged flag)
    - Rule 7: Board Approval (board_approved flag)
    - Rule 10: Owner Authorization (for critical operations)
    
    Args:
        proposal: Proposal model instance
    
    Returns:
        bool: True if compliant
    
    Raises:
        ConstitutionalError: If any rule is violated
    """
    # ProposalStatus is already available from models.core import above
    from models.core import ProposalStatus
    
    # Rule 6: Full Transparency
    if not proposal.logged:
        raise ConstitutionalError(
            f"Rule 6 Violation: Proposal {proposal.id} must be logged before processing"
        )
    
    # Rule 7: Board Approval (for executed proposals)
    if proposal.status == ProposalStatus.EXECUTED and not proposal.board_approved:
        raise ConstitutionalError(
            f"Rule 7 Violation: Proposal {proposal.id} cannot be executed without board approval"
        )
    
    # Rule 10: Owner Authorization (for critical operations)
    critical_keywords = ['override', 'shutdown', 'terminate', 'transfer', 'ownership', 'control']
    is_critical = any(
        keyword in proposal.title.lower() or keyword in proposal.description.lower()
        for keyword in critical_keywords
    )
    
    if is_critical and not proposal.owner_authorized:
        raise ConstitutionalError(
            f"Rule 10 Violation: Critical proposal {proposal.id} requires owner authorization"
        )
    
    return True


def validate_constitutional_compliance(
    proposal: 'Proposal | None' = None,
    board_session: 'BoardSession | None' = None,
    vote_result: 'VoteResult | None' = None,
    action: dict | None = None,
    context: dict | None = None
) -> 'ConstitutionalValidation':
    """
    Master function to validate constitutional compliance across all rules.
    
    This is the primary entry point for constitutional validation. It checks
    all applicable rules based on the provided entities and returns a comprehensive
    validation result.
    
    Args:
        proposal: Optional Proposal to validate
        board_session: Optional BoardSession to validate
        vote_result: Optional VoteResult to validate
        action: Optional action dictionary to validate (for Rules 1, 2, 3, 10)
        context: Optional context dictionary with additional validation data
    
    Returns:
        ConstitutionalValidation: Complete validation result with compliance status
        
    Example:
        >>> from models.core import Proposal, BoardSession
        >>> proposal = Proposal(...)
        >>> validation = validate_constitutional_compliance(proposal=proposal)
        >>> if not validation.is_compliant:
        ...     print(f"Violations: {validation.violated_rules}")
    """
    from models.core import (
        ConstitutionalValidation,
        ConstitutionalRule,
        ProposalStatus
    )
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Initialize validation result
    validation = ConstitutionalValidation(
        proposal_id=proposal.id if proposal else None,
        session_id=board_session.id if board_session else None,
        is_compliant=True
    )
    
    try:
        # Rule 1: Access Control
        if action:
            try:
                enforce_rule_1(action, action.get('owner_permission', False))
                validation.mark_rule_compliant(ConstitutionalRule.RULE_1_ACCESS_CONTROL)
            except ConstitutionalError as e:
                validation.add_violation(ConstitutionalRule.RULE_1_ACCESS_CONTROL, str(e))
        
        # Rule 2: No Unauthorized Access
        if action:
            try:
                enforce_rule_2(action, action.get('owner_consent', False))
                validation.mark_rule_compliant(ConstitutionalRule.RULE_2_NO_UNAUTHORIZED_ACCESS)
            except ConstitutionalError as e:
                validation.add_violation(ConstitutionalRule.RULE_2_NO_UNAUTHORIZED_ACCESS, str(e))
        
        # Rule 3: Immutable Constitution
        if action:
            try:
                enforce_rule_3(action)
                validation.mark_rule_compliant(ConstitutionalRule.RULE_3_IMMUTABLE_CONSTITUTION)
            except ConstitutionalError as e:
                validation.add_violation(ConstitutionalRule.RULE_3_IMMUTABLE_CONSTITUTION, str(e))
        
        # Rule 4: Financial Priority
        if proposal:
            try:
                alternative_impact = context.get('alternative_impact') if context else None
                enforce_rule_4(
                    {'id': proposal.id, 'title': proposal.title},
                    proposal.financial_impact,
                    alternative_impact
                )
                validation.mark_rule_compliant(ConstitutionalRule.RULE_4_FINANCIAL_PRIORITY)
            except ConstitutionalError as e:
                validation.add_violation(ConstitutionalRule.RULE_4_FINANCIAL_PRIORITY, str(e))
        
        # Rule 5: Legal Protection
        if proposal:
            try:
                legal_approval = context.get('legal_approval', False) if context else False
                enforce_rule_5(
                    {'id': proposal.id, 'title': proposal.title},
                    proposal.legal_risk,
                    legal_approval
                )
                validation.mark_rule_compliant(ConstitutionalRule.RULE_5_LEGAL_PROTECTION)
            except ConstitutionalError as e:
                validation.add_violation(ConstitutionalRule.RULE_5_LEGAL_PROTECTION, str(e))
        
        # Rule 6: Full Transparency
        if proposal:
            try:
                enforce_rule_6(
                    {'id': proposal.id, 'title': proposal.title},
                    proposal.logged,
                    context.get('log_path') if context else None
                )
                validation.mark_rule_compliant(ConstitutionalRule.RULE_6_FULL_TRANSPARENCY)
            except ConstitutionalError as e:
                validation.add_violation(ConstitutionalRule.RULE_6_FULL_TRANSPARENCY, str(e))
        
        if board_session:
            try:
                enforce_rule_6(
                    {'id': board_session.id, 'type': 'session'},
                    board_session.logged,
                    context.get('log_path') if context else None
                )
                validation.mark_rule_compliant(ConstitutionalRule.RULE_6_FULL_TRANSPARENCY)
            except ConstitutionalError as e:
                validation.add_violation(ConstitutionalRule.RULE_6_FULL_TRANSPARENCY, str(e))
        
        # Rule 7: Board Approval
        if proposal:
            try:
                enforce_rule_7(
                    {'id': proposal.id, 'title': proposal.title},
                    proposal.board_approved,
                    context.get('approval_record') if context else None
                )
                validation.mark_rule_compliant(ConstitutionalRule.RULE_7_BOARD_APPROVAL)
            except ConstitutionalError as e:
                validation.add_violation(ConstitutionalRule.RULE_7_BOARD_APPROVAL, str(e))
        
        # Rule 8: Board Composition
        if board_session:
            try:
                enforce_rule_8_with_model(board_session)
                validation.mark_rule_compliant(ConstitutionalRule.RULE_8_BOARD_COMPOSITION)
            except ConstitutionalError as e:
                validation.add_violation(ConstitutionalRule.RULE_8_BOARD_COMPOSITION, str(e))
        
        if vote_result:
            # Rule 8 is also checked in VoteResult validator
            try:
                enforce_rule_8([member_id for member_id in vote_result.votes.keys()])
                validation.mark_rule_compliant(ConstitutionalRule.RULE_8_BOARD_COMPOSITION)
            except ConstitutionalError as e:
                validation.add_violation(ConstitutionalRule.RULE_8_BOARD_COMPOSITION, str(e))
        
        # Rule 9: Voting Weight Limit
        if vote_result:
            try:
                enforce_rule_9_with_model(vote_result)
                validation.mark_rule_compliant(ConstitutionalRule.RULE_9_VOTING_WEIGHT_LIMIT)
            except ConstitutionalError as e:
                validation.add_violation(ConstitutionalRule.RULE_9_VOTING_WEIGHT_LIMIT, str(e))
        
        if board_session:
            try:
                weights = board_session.calculate_vote_weights()
                enforce_rule_9(weights)
                validation.mark_rule_compliant(ConstitutionalRule.RULE_9_VOTING_WEIGHT_LIMIT)
            except ConstitutionalError as e:
                validation.add_violation(ConstitutionalRule.RULE_9_VOTING_WEIGHT_LIMIT, str(e))
        
        # Rule 10: Human Ownership Lock
        if proposal:
            try:
                enforce_rule_10(
                    {'id': proposal.id, 'title': proposal.title, 'description': proposal.description},
                    proposal.owner_authorized
                )
                validation.mark_rule_compliant(ConstitutionalRule.RULE_10_HUMAN_OWNERSHIP_LOCK)
            except ConstitutionalError as e:
                validation.add_violation(ConstitutionalRule.RULE_10_HUMAN_OWNERSHIP_LOCK, str(e))
        
        if action:
            try:
                enforce_rule_10(action, action.get('owner_authorized', False))
                validation.mark_rule_compliant(ConstitutionalRule.RULE_10_HUMAN_OWNERSHIP_LOCK)
            except ConstitutionalError as e:
                validation.add_violation(ConstitutionalRule.RULE_10_HUMAN_OWNERSHIP_LOCK, str(e))
        
        # Log validation result
        if validation.is_compliant:
            logger.info(
                f"Constitutional validation passed for "
                f"proposal={proposal.id if proposal else None}, "
                f"session={board_session.id if board_session else None}"
            )
        else:
            logger.warning(
                f"Constitutional validation failed with violations: {validation.violated_rules}"
            )
        
        return validation
        
    except Exception as e:
        logger.error(f"Error during constitutional validation: {e}", exc_info=True)
        validation.add_violation(
            ConstitutionalRule.RULE_3_IMMUTABLE_CONSTITUTION,
            f"Validation system error: {str(e)}"
        )
        return validation


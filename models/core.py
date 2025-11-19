"""
Core Data Models - Single Source of Truth

All data structures for the AI Business governance system MUST be defined here.
Never create duplicate models in other modules.

This module provides:
- Pydantic models for all governance entities
- Custom exceptions for constitutional violations
- Validators that enforce constitutional rules
"""

from datetime import datetime
from typing import Optional, Literal
from enum import Enum
from pydantic import BaseModel, field_validator, model_validator, Field
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Custom Exceptions
# ============================================================================

class ConstitutionalError(Exception):
    """Raised when a constitutional rule is violated."""
    pass


class ValidationError(Exception):
    """Raised when data validation fails."""
    pass


# ============================================================================
# Enums
# ============================================================================

class VoteType(str, Enum):
    """Types of votes."""
    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"
    VETO = "veto"


class ProposalStatus(str, Enum):
    """Status of a proposal."""
    DRAFT = "draft"
    DELIBERATION = "deliberation"
    VOTING = "voting"
    VOTING_FAILED = "voting_failed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    VETOED = "vetoed"
    EXECUTED = "executed"


class RoleType(str, Enum):
    """Board role types."""
    CEO = "CEO"
    CFO = "CFO"
    COO = "COO"
    CMO = "CMO"
    LEGAL = "LEGAL"
    CISO = "CISO"
    CHAIR = "CHAIR"
    SECRETARY = "SECRETARY"


class ConstitutionalRule(int, Enum):
    """
    Enumeration of the 10 constitutional rules.
    
    Maps to business rules from Section 3.2 of the AI Business Plan.
    """
    RULE_1_ACCESS_CONTROL = 1
    RULE_2_NO_UNAUTHORIZED_ACCESS = 2
    RULE_3_IMMUTABLE_CONSTITUTION = 3
    RULE_4_FINANCIAL_PRIORITY = 4
    RULE_5_LEGAL_PROTECTION = 5
    RULE_6_FULL_TRANSPARENCY = 6
    RULE_7_BOARD_APPROVAL = 7
    RULE_8_BOARD_COMPOSITION = 8
    RULE_9_VOTING_WEIGHT_LIMIT = 9
    RULE_10_HUMAN_OWNERSHIP_LOCK = 10


# ============================================================================
# Core Models
# ============================================================================

class Vote(BaseModel):
    """
    Individual vote from a board member.
    
    Enforces Rule 9: Voting Weight Limit (25% maximum)
    """
    model_config = {"frozen": True}  # Immutable (Rule 3)
    
    member_id: str = Field(..., description="Unique identifier for board member")
    role: RoleType = Field(..., description="Board role of the member")
    vote_type: VoteType = Field(..., description="Type of vote cast")
    weight: float = Field(..., ge=0.0, le=1.0, description="Voting weight (0.0 to 1.0)")
    rationale: Optional[str] = Field(None, description="Reasoning for the vote")
    timestamp: datetime = Field(default_factory=datetime.now, description="When vote was cast")
    
    @field_validator('weight')
    @classmethod
    def validate_weight(cls, v: float) -> float:
        """Validate individual vote weight does not exceed 25%."""
        if v > 0.25:
            logger.error(f"Rule 9 Violation: Individual vote weight {v*100:.2f}% exceeds 25%")
            raise ConstitutionalError(
                f"Rule 9 Violation: Individual vote weight {v*100:.2f}% exceeds 25% maximum"
            )
        return v


class VoteResult(BaseModel):
    """
    Aggregated voting results from a board session.
    
    Enforces Rule 9: No member may have more than 25% voting weight.
    Enforces Rule 8: Minimum 5 distinct board members.
    """
    model_config = {"frozen": True}  # Immutable (Rule 3)
    
    session_id: str = Field(..., description="Board session identifier")
    proposal_id: str = Field(..., description="Proposal being voted on")
    votes: dict[str, float] = Field(..., description="Member ID -> voting weight mapping")
    total_weight: float = Field(..., ge=0.0, le=1.0, description="Sum of all weights")
    timestamp: datetime = Field(default_factory=datetime.now, description="When voting completed")
    
    @model_validator(mode='after')
    def validate_constitutional_rules(self) -> 'VoteResult':
        """
        Validate Rule 8 (minimum 5 members) and Rule 9 (25% weight limit).
        
        Raises:
            ConstitutionalError: If rules are violated
        """
        # Rule 8: Minimum 5 distinct members
        distinct_members = set(self.votes.keys())
        if len(distinct_members) < 5:
            logger.error(f"Rule 8 Violation: Only {len(distinct_members)} distinct members")
            raise ConstitutionalError(
                f"Rule 8 Violation: AI Board must consist of minimum 5 distinct AI models. "
                f"Found {len(distinct_members)} distinct members"
            )
        
        # Rule 9: No member exceeds 25% weight
        if self.total_weight > 0:
            normalized_weights = {
                member: weight / self.total_weight 
                for member, weight in self.votes.items()
            }
            max_weight = max(normalized_weights.values())
            if max_weight > 0.25:
                violating_member = max(normalized_weights.items(), key=lambda x: x[1])[0]
                logger.error(
                    f"Rule 9 Violation: Member {violating_member} has {max_weight*100:.2f}% weight"
                )
                raise ConstitutionalError(
                    f"Rule 9 Violation: No Board member may have more than 25% voting weight. "
                    f"Member '{violating_member}' has {max_weight * 100:.2f}% weight"
                )
        
        return self


class Proposal(BaseModel):
    """
    A proposal submitted for board deliberation and voting.
    
    Enforces Rule 6: Full Transparency (all proposals must be logged)
    Enforces Rule 7: Board Approval (status tracking)
    """
    model_config = {"frozen": False}  # Proposals can be updated during deliberation
    
    id: str = Field(..., description="Unique proposal identifier")
    title: str = Field(..., min_length=1, description="Proposal title")
    description: str = Field(..., min_length=1, description="Detailed proposal description")
    status: ProposalStatus = Field(default=ProposalStatus.DRAFT, description="Current status")
    financial_impact: float = Field(..., description="Expected financial impact")
    legal_risk: float = Field(default=0.0, ge=0.0, le=1.0, description="Legal risk score (0.0-1.0)")
    session_id: Optional[str] = Field(None, description="Board session ID if submitted")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    logged: bool = Field(default=False, description="Whether proposal has been logged (Rule 6)")
    board_approved: bool = Field(default=False, description="Whether board approved (Rule 7)")
    owner_authorized: bool = Field(default=False, description="Owner authorization (Rule 10)")
    
    @field_validator('legal_risk')
    @classmethod
    def validate_legal_risk(cls, v: float) -> float:
        """Validate legal risk is within bounds."""
        if not 0.0 <= v <= 1.0:
            raise ValidationError(f"Legal risk must be between 0.0 and 1.0, got {v}")
        return v
    
    def mark_logged(self) -> 'Proposal':
        """Mark proposal as logged (Rule 6 compliance)."""
        self.logged = True
        self.updated_at = datetime.now()
        logger.info(f"Proposal {self.id} marked as logged")
        return self
    
    def mark_board_approved(self) -> 'Proposal':
        """Mark proposal as board approved (Rule 7 compliance)."""
        self.board_approved = True
        self.status = ProposalStatus.APPROVED
        self.updated_at = datetime.now()
        logger.info(f"Proposal {self.id} marked as board approved")
        return self


class BoardMember(BaseModel):
    """
    Represents a board member (AI model) with their role and configuration.
    
    Enforces Rule 8: Distinct AI models
    """
    model_config = {"frozen": True}  # Immutable (Rule 3)
    
    member_id: str = Field(..., description="Unique identifier for this AI model")
    role: RoleType = Field(..., description="Board role")
    model_name: str = Field(..., description="AI model identifier (e.g., 'gpt-4', 'claude-3')")
    voting_weight: float = Field(..., ge=0.0, le=0.25, description="Voting weight (max 25%)")
    is_active: bool = Field(default=True, description="Whether member is currently active")
    
    @field_validator('voting_weight')
    @classmethod
    def validate_voting_weight(cls, v: float) -> float:
        """Validate voting weight does not exceed 25% (Rule 9)."""
        if v > 0.25:
            logger.error(f"Rule 9 Violation: Voting weight {v*100:.2f}% exceeds 25%")
            raise ConstitutionalError(
                f"Rule 9 Violation: Voting weight {v*100:.2f}% exceeds 25% maximum"
            )
        return v


class BoardSession(BaseModel):
    """
    A board session for deliberation and voting.
    
    Enforces Rule 8: Minimum 5 distinct members
    Enforces Rule 6: Full Transparency (session logging)
    """
    model_config = {"frozen": False}  # Sessions can be updated
    
    id: str = Field(..., description="Unique session identifier")
    members: list[BoardMember] = Field(..., min_length=5, description="Board members (min 5)")
    proposals: list[Proposal] = Field(default_factory=list, description="Proposals in session")
    started_at: datetime = Field(default_factory=datetime.now, description="Session start time")
    ended_at: Optional[datetime] = Field(None, description="Session end time")
    logged: bool = Field(default=False, description="Whether session has been logged (Rule 6)")
    
    @model_validator(mode='after')
    def validate_board_composition(self) -> 'BoardSession':
        """
        Validate Rule 8: Minimum 5 distinct AI models.
        
        Raises:
            ConstitutionalError: If fewer than 5 distinct members
        """
        distinct_member_ids = {member.member_id for member in self.members}
        distinct_model_names = {member.model_name for member in self.members}
        
        # Check distinct member IDs
        if len(distinct_member_ids) < 5:
            logger.error(f"Rule 8 Violation: Only {len(distinct_member_ids)} distinct member IDs")
            raise ConstitutionalError(
                f"Rule 8 Violation: AI Board must consist of minimum 5 distinct AI models. "
                f"Found {len(distinct_member_ids)} distinct members"
            )
        
        # Also check distinct model names (same model shouldn't appear twice)
        if len(distinct_model_names) < len(self.members):
            logger.warning(
                f"Some board members share the same model name. "
                f"Distinct models: {len(distinct_model_names)}, Total members: {len(self.members)}"
            )
        
        return self
    
    def get_active_members(self) -> list[BoardMember]:
        """Get list of active board members."""
        return [member for member in self.members if member.is_active]
    
    def calculate_vote_weights(self) -> dict[str, float]:
        """
        Calculate normalized voting weights for active members.
        
        Returns:
            Dictionary mapping member_id to normalized weight
            
        Raises:
            ConstitutionalError: If any weight exceeds 25% after normalization
        """
        active_members = self.get_active_members()
        if len(active_members) < 5:
            raise ConstitutionalError(
                f"Rule 8 Violation: Only {len(active_members)} active members, need minimum 5"
            )
        
        weights = {member.member_id: member.voting_weight for member in active_members}
        total_weight = sum(weights.values())
        
        if total_weight > 0:
            normalized = {member_id: weight / total_weight for member_id, weight in weights.items()}
            max_weight = max(normalized.values())
            if max_weight > 0.25:
                violating_member = max(normalized.items(), key=lambda x: x[1])[0]
                raise ConstitutionalError(
                    f"Rule 9 Violation: Member '{violating_member}' has {max_weight*100:.2f}% "
                    f"weight after normalization, exceeds 25% limit"
                )
            return normalized
        
        return weights


class ConstitutionalValidation(BaseModel):
    """
    Result of constitutional compliance validation.
    
    Tracks which rules were checked and their compliance status.
    Note: Not frozen to allow building validation results incrementally.
    """
    model_config = {"frozen": False}  # Mutable to allow incremental building
    
    proposal_id: Optional[str] = Field(None, description="Proposal ID if validating proposal")
    session_id: Optional[str] = Field(None, description="Session ID if validating session")
    validated_at: datetime = Field(default_factory=datetime.now, description="Validation timestamp")
    is_compliant: bool = Field(default=True, description="Overall compliance status")
    violated_rules: list[ConstitutionalRule] = Field(
        default_factory=list, 
        description="List of violated rule numbers"
    )
    validation_details: dict[str, bool] = Field(
        default_factory=dict,
        description="Per-rule validation results (rule_name -> compliant)"
    )
    error_messages: list[str] = Field(
        default_factory=list,
        description="Error messages for violations"
    )
    
    def add_violation(self, rule: ConstitutionalRule, message: str) -> None:
        """Add a rule violation."""
        if rule not in self.violated_rules:
            self.violated_rules.append(rule)
        self.error_messages.append(message)
        self.is_compliant = False
        self.validation_details[f"rule_{rule.value}"] = False
    
    def mark_rule_compliant(self, rule: ConstitutionalRule) -> None:
        """Mark a rule as compliant."""
        self.validation_details[f"rule_{rule.value}"] = True


class APIResponse(BaseModel):
    """
    Standard API response model for all endpoints.
    
    Ensures consistent response structure across the system.
    """
    model_config = {"frozen": True}  # Immutable (Rule 3)
    
    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Human-readable message")
    data: Optional[dict] = Field(None, description="Response data payload")
    errors: list[str] = Field(default_factory=list, description="List of error messages")
    timestamp: datetime = Field(default_factory=datetime.now, description="Response timestamp")
    request_id: Optional[str] = Field(None, description="Request identifier for tracing")
    
    @classmethod
    def success_response(
        cls, 
        message: str, 
        data: Optional[dict] = None,
        request_id: Optional[str] = None
    ) -> 'APIResponse':
        """Create a successful API response."""
        return cls(
            success=True,
            message=message,
            data=data,
            request_id=request_id
        )
    
    @classmethod
    def error_response(
        cls,
        message: str,
        errors: list[str],
        request_id: Optional[str] = None
    ) -> 'APIResponse':
        """Create an error API response."""
        return cls(
            success=False,
            message=message,
            errors=errors,
            request_id=request_id
        )


# ============================================================================
# Helper Functions
# ============================================================================

def create_vote_result(session_id: str, proposal_id: str, votes: dict[str, float]) -> VoteResult:
    """
    Create a VoteResult with automatic validation.
    
    Args:
        session_id: Board session identifier
        proposal_id: Proposal identifier
        votes: Dictionary mapping member_id to voting weight
        
    Returns:
        VoteResult with validated weights
        
    Raises:
        ConstitutionalError: If Rule 8 or Rule 9 is violated
    """
    total_weight = sum(votes.values())
    return VoteResult(
        session_id=session_id,
        proposal_id=proposal_id,
        votes=votes,
        total_weight=total_weight
    )


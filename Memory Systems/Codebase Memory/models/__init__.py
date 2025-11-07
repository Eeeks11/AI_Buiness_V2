"""
Models package - Single source of truth for all data structures.

All models MUST be imported from models.core, never defined elsewhere.
"""

from models.core import (
    ConstitutionalError,
    ValidationError,
    Vote,
    VoteResult,
    Proposal,
    BoardSession,
    BoardMember,
    VoteType,
    ProposalStatus,
    RoleType,
    ConstitutionalRule,
    ConstitutionalValidation,
    APIResponse,
    create_vote_result,
)

__all__ = [
    "ConstitutionalError",
    "ValidationError",
    "Vote",
    "VoteResult",
    "Proposal",
    "BoardSession",
    "BoardMember",
    "VoteType",
    "ProposalStatus",
    "RoleType",
    "ConstitutionalRule",
    "ConstitutionalValidation",
    "APIResponse",
    "create_vote_result",
]


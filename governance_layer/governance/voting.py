"""
Voting Utilities

Aggregate and evaluate board votes with constitutional safeguards, including
Rule 9 weight enforcement, veto handling, and Chair tiebreak logic.
"""

# Standard library
import logging
import math
from pathlib import Path
from typing import Any, Dict, List
import sys

# Local - models first (single source of truth)
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from models.core import (
    ConstitutionalError,
    Vote,
    VoteResult,
    VoteType,
    RoleType,
    create_vote_result
)

# Local - constitutional enforcement
sys.path.insert(0, str(project_root / "constitutional_layer_immutable"))
from constitution import validate_constitutional_compliance

# Local - roles
sys.path.insert(0, str(project_root / "governance_layer" / "roles"))
from prompt_templates import load_role_configs

# Local - utilities
from utilities.logger import log_event

logger = logging.getLogger(__name__)


def _validate_role_weight_distribution(role_configs: Dict[str, Dict[str, Any]]) -> None:
    """
    Validate that role weights are Rule 9 compliant.
    
    Validates:
    - No single role exceeds 25% voting weight
    - Only the 4 primary voters (CEO, CFO, COO, CMO) have voting weight
    - The 4 primary voters sum to exactly 100%
    - Non-voting roles (CHAIR, LEGAL, CISO, SECRETARY) have 0% weight
    
    Args:
        role_configs: Role configuration dictionary.
    
    Raises:
        ConstitutionalError: If weight validation fails.
    """
    PRIMARY_VOTERS = {"CEO", "CFO", "COO", "CMO"}
    NON_VOTING_ROLES = {"CHAIR", "LEGAL", "CISO", "SECRETARY"}
    
    primary_voter_weights = []
    non_voting_weights = []
    
    for role, config in role_configs.items():
        weight = config.get("voting_weight", 0.0)
        
        if role in PRIMARY_VOTERS:
            primary_voter_weights.append(weight)
        elif role in NON_VOTING_ROLES:
            non_voting_weights.append(weight)
    
    # Check no single role exceeds 25%
    all_weights = [config.get("voting_weight", 0.0) for config in role_configs.values()]
    if any(weight > 0.25 for weight in all_weights):
        logger.error("Role configuration weight exceeds 25 percent", extra={"weights": all_weights})
        raise ConstitutionalError(
            "Rule 9 Violation: Role configuration assigns more than 25% voting weight"
        )
    
    # Check primary voters sum to 100%
    primary_total = sum(primary_voter_weights)
    if not math.isclose(primary_total, 1.0, rel_tol=1e-9, abs_tol=1e-6):
        logger.error(
            "Primary voter weights do not sum to 1.0",
            extra={"primary_total": primary_total, "primary_voters": PRIMARY_VOTERS}
        )
        raise ConstitutionalError(
            f"Rule 9 Violation: Primary voters (CEO, CFO, COO, CMO) must sum to 1.0, got {primary_total:.6f}"
        )
    
    # Check non-voting roles have 0% weight
    if any(weight != 0.0 for weight in non_voting_weights):
        logger.error(
            "Non-voting roles have non-zero weights",
            extra={"non_voting_weights": non_voting_weights}
        )
        raise ConstitutionalError(
            "Rule 9 Violation: Non-voting roles (CHAIR, LEGAL, CISO, SECRETARY) must have 0% voting weight"
        )


def tally_votes(votes: List[Vote], roles: Dict[str, Dict[str, Any]] | None, proposal_id: str) -> VoteResult:
    """
    Tally board votes with constitutional compliance safeguards.
    
    Voting Logic:
    1. Only CEO, CFO, COO, CMO votes count toward the decision (25% each)
    2. LEGAL and CISO can veto (blocks proposal regardless of votes)
    3. CHAIR only votes to break 2-2 ties between the 4 primary voters
    4. SECRETARY does not vote (documentation only)
    
    Args:
        votes: List of Vote objects submitted by board members.
        roles: Role configuration dictionary (defaults to role_configs.json when None).
        proposal_id: Identifier for the proposal being voted on.
    
    Returns:
        VoteResult containing normalized vote distribution.
    
    Raises:
        ConstitutionalError: If votes breach constitutional requirements.
    """
    logger.info(
        "Tallying board votes",
        extra={"proposal_id": proposal_id, "vote_count": len(votes)}
    )

    PRIMARY_VOTERS = {RoleType.CEO, RoleType.CFO, RoleType.COO, RoleType.CMO}
    VETO_ROLES = {RoleType.LEGAL, RoleType.CISO}

    role_configs = roles if roles else load_role_configs()
    _validate_role_weight_distribution(role_configs)

    session_id = None
    if isinstance(role_configs, dict) and "_session_id" in role_configs:
        session_id = str(role_configs["_session_id"])

    # Track votes from primary voters only
    primary_votes: Dict[RoleType, Vote] = {}
    approve_count = 0
    reject_count = 0
    
    # Track veto votes
    veto_triggered = False
    veto_role: str | None = None
    
    # Track CHAIR vote (for tie-breaking)
    chair_vote: Vote | None = None
    
    # Track all votes for logging
    votes_map: Dict[str, float] = {}
    abstain_weight = 0.0

    # First pass: collect all votes and check for vetoes
    for vote in votes:
        role_key = vote.role.value.upper()
        if role_key not in role_configs:
            logger.error("Vote received from undefined role", extra={"role": role_key})
            raise ConstitutionalError(
                f"Rule 8 Violation: Vote submitted by undefined role '{role_key}'"
            )

        expected_weight = role_configs[role_key].get("voting_weight", 0.0)
        votes_map[vote.member_id] = float(expected_weight)

        # Check for vetoes first (LEGAL or CISO)
        if vote.role in VETO_ROLES and vote.vote_type == VoteType.VETO:
            veto_triggered = True
            veto_role = role_key
            logger.info("Veto detected", extra={"role": role_key, "proposal_id": proposal_id})
            # Veto blocks proposal regardless of other votes, but continue to collect all votes for logging
        
        # Track CHAIR vote (for tie-breaking only)
        if vote.role == RoleType.CHAIR:
            chair_vote = vote
            if vote.vote_type == VoteType.ABSTAIN:
                abstain_weight += float(expected_weight)
        
        # Track primary voter votes (CEO, CFO, COO, CMO)
        if vote.role in PRIMARY_VOTERS:
            primary_votes[vote.role] = vote
            if vote.vote_type == VoteType.APPROVE:
                approve_count += 1
            elif vote.vote_type == VoteType.REJECT:
                reject_count += 1
            elif vote.vote_type == VoteType.ABSTAIN:
                abstain_weight += float(expected_weight)
            elif vote.vote_type == VoteType.VETO:
                # Primary voters should not cast veto (only LEGAL/CISO can)
                logger.warning(
                    "Primary voter attempted to cast veto",
                    extra={"role": role_key, "proposal_id": proposal_id}
                )
                reject_count += 1  # Treat as reject

    # Validate we have votes from all 4 primary voters
    if len(primary_votes) < 4:
        missing_voters = PRIMARY_VOTERS - set(primary_votes.keys())
        logger.error(
            "Missing votes from primary voters",
            extra={"missing": [v.value for v in missing_voters], "proposal_id": proposal_id}
        )
        raise ConstitutionalError(
            f"Rule 8 Violation: All 4 primary voters (CEO, CFO, COO, CMO) must vote. "
            f"Missing: {[v.value for v in missing_voters]}"
        )

    # Decision logic
    decision = "approved"
    decision_reason = "majority"
    chair_tiebreak_used = False

    # Step 1: Check for veto (veto overrides everything)
    if veto_triggered:
        decision = "rejected"
        decision_reason = f"{veto_role} veto"
        logger.info(
            "Veto triggered; proposal rejected",
            extra={"role": veto_role, "proposal_id": proposal_id}
        )
    # Step 2: Check for 2-2 tie (requires CHAIR tie-breaker)
    elif approve_count == 2 and reject_count == 2:
        if chair_vote is None:
            logger.error(
                "2-2 tie without Chair vote available",
                extra={"proposal_id": proposal_id, "approve_count": approve_count, "reject_count": reject_count}
            )
            raise ConstitutionalError(
                "Rule 9 Violation: 2-2 tie requires Chair to cast tie-breaking vote"
            )
        
        if chair_vote.vote_type == VoteType.APPROVE:
            decision = "approved"
        elif chair_vote.vote_type == VoteType.REJECT:
            decision = "rejected"
        else:
            logger.error(
                "Chair abstained during 2-2 tie, violating governance protocol",
                extra={"proposal_id": proposal_id, "chair_vote_type": chair_vote.vote_type.value}
            )
            raise ConstitutionalError(
                "Rule 9 Violation: Chair must cast APPROVE or REJECT vote during 2-2 tie (cannot abstain)"
            )
        
        decision_reason = "chair_tiebreak"
        chair_tiebreak_used = True
        logger.info(
            "2-2 tie resolved by Chair",
            extra={
                "proposal_id": proposal_id,
                "chair_vote": chair_vote.vote_type.value,
                "decision": decision
            }
        )
    # Step 3: Majority decision (3-1 or 4-0)
    else:
        if approve_count > reject_count:
            decision = "approved"
            decision_reason = "majority_approval"
        elif reject_count > approve_count:
            decision = "rejected"
            decision_reason = "majority_rejection"
        else:
            # This should not happen if we have exactly 4 votes
            logger.error(
                "Unexpected vote count",
                extra={"approve_count": approve_count, "reject_count": reject_count, "proposal_id": proposal_id}
            )
            raise ConstitutionalError(
                f"Rule 9 Violation: Unexpected vote distribution. Approve: {approve_count}, Reject: {reject_count}"
            )

    # Calculate weights for logging (only from primary voters)
    approve_weight = approve_count * 0.25
    reject_weight = reject_count * 0.25

    vote_result = create_vote_result(
        session_id=session_id or f"{proposal_id}-session",
        proposal_id=proposal_id,
        votes=votes_map
    )

    validation = validate_constitutional_compliance(
        vote_result=vote_result,
        context={"log_path": str(project_root / "audit_compliance" / "logs" / "events.jsonl")}
    )

    if not validation.is_compliant:
        logger.error(
            "Vote tally failed constitutional validation",
            extra={"proposal_id": proposal_id, "violations": validation.violated_rules}
        )
        raise ConstitutionalError(
            f"Rule 9 Violation: Vote tally invalid. Violations: {validation.violated_rules}"
        )

    logger.info(
        "Votes tallied successfully",
        extra={
            "proposal_id": proposal_id,
            "decision": decision,
            "reason": decision_reason,
            "approve_count": approve_count,
            "reject_count": reject_count,
            "veto_triggered": veto_triggered,
            "chair_tiebreak": chair_tiebreak_used
        }
    )

    # Log the vote tally
    try:
        log_event(
            event_type="board_vote_tallied",
            data={
                "proposal_id": proposal_id,
                "approve_count": approve_count,
                "reject_count": reject_count,
                "approve_weight": approve_weight,
                "reject_weight": reject_weight,
                "abstain_weight": abstain_weight,
                "decision": decision,
                "reason": decision_reason,
                "veto_triggered": veto_triggered,
                "veto_role": veto_role,
                "chair_tiebreak_used": chair_tiebreak_used,
                "chair_vote": chair_vote.vote_type.value if chair_vote else None
            },
            metadata={"function": "tally_votes"}
        )
    except Exception as exc:
        logger.warning("Failed to log vote tally", extra={"error": str(exc)})

    return vote_result


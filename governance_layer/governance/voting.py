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
sys.path.insert(0, str(project_root / "memory_systems" / "codebase_memory"))
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
    Validate that role weights are Rule 9 compliant and sum to 1.0.
    
    Args:
        role_configs: Role configuration dictionary.
    
    Raises:
        ConstitutionalError: If weight validation fails.
    """
    weights = [config.get("voting_weight", 0.0) for config in role_configs.values()]
    total_weight = sum(weights)

    if any(weight > 0.25 for weight in weights):
        logger.error("Role configuration weight exceeds 25 percent", extra={"weights": weights})
        raise ConstitutionalError(
            "Rule 9 Violation: Role configuration assigns more than 25% voting weight"
        )

    if not math.isclose(total_weight, 1.0, rel_tol=1e-9, abs_tol=1e-6):
        logger.error(
            "Role configuration weights do not sum to 1.0",
            extra={"total_weight": total_weight}
        )
        raise ConstitutionalError(
            "Rule 9 Violation: Role voting weights must sum to 1.0"
        )


def tally_votes(votes: List[Vote], roles: Dict[str, Dict[str, Any]] | None, proposal_id: str) -> VoteResult:
    """
    Tally board votes with constitutional compliance safeguards.
    
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

    if len(votes) < 5:
        logger.error("Insufficient votes for compliance", extra={"vote_count": len(votes)})
        raise ConstitutionalError(
            "Rule 8 Violation: Minimum five votes required to ensure board diversity"
        )

    role_configs = roles if roles else load_role_configs()
    _validate_role_weight_distribution(role_configs)

    session_id = None
    if isinstance(role_configs, dict) and "_session_id" in role_configs:
        session_id = str(role_configs["_session_id"])

    approve_weight = 0.0
    reject_weight = 0.0
    abstain_weight = 0.0
    votes_map: Dict[str, float] = {}
    veto_triggered = False
    veto_role: str | None = None
    chair_vote: Vote | None = None
    chair_weight = 0.0

    for vote in votes:
        role_key = vote.role.value.upper()
        if role_key not in role_configs:
            logger.error("Vote received from undefined role", extra={"role": role_key})
            raise ConstitutionalError(
                f"Rule 8 Violation: Vote submitted by undefined role '{role_key}'"
            )

        expected_weight = role_configs[role_key].get("voting_weight")
        if expected_weight is None:
            logger.error("Role configuration missing voting weight", extra={"role": role_key})
            raise ConstitutionalError(
                f"Rule 9 Violation: Role '{role_key}' lacks assigned voting weight"
            )

        if not math.isclose(vote.weight, float(expected_weight), abs_tol=1e-6):
            logger.warning(
                "Vote weight deviates from configuration; normalizing to expected weight",
                extra={"role": role_key, "received": vote.weight, "expected": expected_weight}
            )

        votes_map[vote.member_id] = float(expected_weight)

        if vote.role == RoleType.CHAIR:
            chair_vote = vote
            chair_weight = float(expected_weight)
            if vote.vote_type == VoteType.ABSTAIN:
                abstain_weight += float(expected_weight)
            continue

        if vote.vote_type == VoteType.APPROVE:
            approve_weight += float(expected_weight)
        elif vote.vote_type == VoteType.REJECT:
            reject_weight += float(expected_weight)
        elif vote.vote_type == VoteType.ABSTAIN:
            abstain_weight += float(expected_weight)
        elif vote.vote_type == VoteType.VETO:
            veto_triggered = True
            veto_role = role_key
            reject_weight += float(expected_weight)
        else:
            logger.error("Unsupported vote type detected", extra={"vote_type": vote.vote_type})
            raise ConstitutionalError(
                f"Rule 4 Violation: Unsupported vote type '{vote.vote_type.value}' encountered"
            )

    decision = "approved"
    decision_reason = "majority"

    if veto_triggered:
        decision = "rejected"
        decision_reason = f"{veto_role} veto"
        logger.info("Veto triggered; proposal rejected", extra={"role": veto_role})
    else:
        if math.isclose(approve_weight, reject_weight, abs_tol=1e-6):
            if chair_vote is None:
                logger.error("Tie without Chair vote available", extra={"proposal_id": proposal_id})
                raise ConstitutionalError(
                    "Rule 9 Violation: Chair must participate to resolve voting ties"
                )

            if chair_vote.vote_type == VoteType.APPROVE:
                decision = "approved"
            elif chair_vote.vote_type in {VoteType.REJECT, VoteType.VETO}:
                decision = "rejected"
            else:
                logger.error(
                    "Chair abstained during tie, violating governance protocol",
                    extra={"proposal_id": proposal_id}
                )
                raise ConstitutionalError(
                    "Rule 9 Violation: Chair must cast approving or rejecting vote during tie"
                )
            decision_reason = "chair_tiebreak"
            logger.info(
                "Tie resolved by Chair",
                extra={"proposal_id": proposal_id, "chair_vote": chair_vote.vote_type.value}
            )
        else:
            decision = "approved" if approve_weight > reject_weight else "rejected"
            decision_reason = "weighted_majority"

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
        extra={"proposal_id": proposal_id, "decision": decision}
    )

    log_approve_weight = approve_weight
    log_reject_weight = reject_weight
    if chair_vote and chair_vote.vote_type == VoteType.APPROVE and decision == "approved":
        log_approve_weight += chair_weight
    if chair_vote and chair_vote.vote_type in {VoteType.REJECT, VoteType.VETO} and decision == "rejected":
        log_reject_weight += chair_weight

    try:
        log_event(
            event_type="board_vote_tallied",
            data={
                "proposal_id": proposal_id,
                "approve_weight": log_approve_weight,
                "reject_weight": log_reject_weight,
                "abstain_weight": abstain_weight if chair_vote is None or chair_vote.vote_type != VoteType.ABSTAIN else abstain_weight,
                "decision": decision,
                "reason": decision_reason
            },
            metadata={"function": "tally_votes"}
        )
    except Exception as exc:
        logger.warning("Failed to log vote tally", extra={"error": str(exc)})

    return vote_result


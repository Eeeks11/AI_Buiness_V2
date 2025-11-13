"""
Tests for governance voting logic and constitutional safeguards.

Tests the new governance structure:
- 4 primary voters (CEO, CFO, COO, CMO) with 25% each
- Non-voting advisory roles (CHAIR, LEGAL, CISO, SECRETARY)
- Veto powers for LEGAL and CISO
- CHAIR tie-breaker for 2-2 ties
"""

# Standard library
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

# Third-party
import pytest

# Path setup
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "governance_layer" / "governance"))
sys.path.insert(0, str(PROJECT_ROOT / "governance_layer" / "roles"))

# Local imports
from models.core import ConstitutionalError, RoleType, Vote, VoteType
from prompt_templates import load_role_configs
from voting import tally_votes


def _make_vote(role: str, vote_type: VoteType) -> Vote:
    """Helper to create Vote objects aligned with role configuration."""
    configs = load_role_configs()
    weight = float(configs[role]["voting_weight"])
    return Vote(
        member_id=f"{role.lower()}_agent",
        role=RoleType(role),
        vote_type=vote_type,
        weight=weight,
        rationale=f"{role} vote cast as {vote_type.value}"
    )


def _make_all_votes(
    ceo: VoteType, cfo: VoteType, coo: VoteType, cmo: VoteType,
    legal: VoteType = VoteType.APPROVE,
    ciso: VoteType = VoteType.APPROVE,
    chair: VoteType = VoteType.ABSTAIN,
    secretary: VoteType = VoteType.ABSTAIN
) -> list[Vote]:
    """Helper to create all 8 votes with specified vote types."""
    return [
        _make_vote("CEO", ceo),
        _make_vote("CFO", cfo),
        _make_vote("COO", coo),
        _make_vote("CMO", cmo),
        _make_vote("LEGAL", legal),
        _make_vote("CISO", ciso),
        _make_vote("CHAIR", chair),
        _make_vote("SECRETARY", secretary)
    ]


@patch("voting.validate_constitutional_compliance")
@patch("voting.log_event")
def test_4_0_unanimous_approval(
    mock_log_event: MagicMock,
    mock_validate: MagicMock
) -> None:
    """Test 4-0 unanimous approval from all primary voters."""
    mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])

    votes = _make_all_votes(
        ceo=VoteType.APPROVE,
        cfo=VoteType.APPROVE,
        coo=VoteType.APPROVE,
        cmo=VoteType.APPROVE
    )

    result = tally_votes(votes=votes, roles=load_role_configs(), proposal_id="prop-4-0")
    
    mock_log_event.assert_called_once()
    logged_data = mock_log_event.call_args.kwargs["data"]
    assert logged_data["decision"] == "approved"
    assert logged_data["reason"] == "majority_approval"
    assert logged_data["approve_count"] == 4
    assert logged_data["reject_count"] == 0
    assert logged_data["veto_triggered"] is False
    assert logged_data["chair_tiebreak_used"] is False


@patch("voting.validate_constitutional_compliance")
@patch("voting.log_event")
def test_3_1_majority_approval(
    mock_log_event: MagicMock,
    mock_validate: MagicMock
) -> None:
    """Test 3-1 majority approval passes."""
    mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])

    votes = _make_all_votes(
        ceo=VoteType.APPROVE,
        cfo=VoteType.APPROVE,
        coo=VoteType.APPROVE,
        cmo=VoteType.REJECT
    )

    result = tally_votes(votes=votes, roles=load_role_configs(), proposal_id="prop-3-1")
    
    mock_log_event.assert_called_once()
    logged_data = mock_log_event.call_args.kwargs["data"]
    assert logged_data["decision"] == "approved"
    assert logged_data["reason"] == "majority_approval"
    assert logged_data["approve_count"] == 3
    assert logged_data["reject_count"] == 1
    assert logged_data["veto_triggered"] is False


@patch("voting.validate_constitutional_compliance")
@patch("voting.log_event")
def test_2_2_tie_with_chair_tiebreak(
    mock_log_event: MagicMock,
    mock_validate: MagicMock
) -> None:
    """Test 2-2 tie requires CHAIR tie-breaker vote."""
    mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])

    votes = _make_all_votes(
        ceo=VoteType.APPROVE,
        cfo=VoteType.APPROVE,
        coo=VoteType.REJECT,
        cmo=VoteType.REJECT,
        chair=VoteType.APPROVE  # CHAIR breaks tie
    )

    result = tally_votes(votes=votes, roles=load_role_configs(), proposal_id="prop-2-2-tie")
    
    mock_log_event.assert_called_once()
    logged_data = mock_log_event.call_args.kwargs["data"]
    assert logged_data["decision"] == "approved"
    assert logged_data["reason"] == "chair_tiebreak"
    assert logged_data["approve_count"] == 2
    assert logged_data["reject_count"] == 2
    assert logged_data["chair_tiebreak_used"] is True
    assert logged_data["chair_vote"] == "approve"


@patch("voting.validate_constitutional_compliance")
@patch("voting.log_event")
def test_2_2_tie_chair_rejects(
    mock_log_event: MagicMock,
    mock_validate: MagicMock
) -> None:
    """Test 2-2 tie with CHAIR rejecting."""
    mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])

    votes = _make_all_votes(
        ceo=VoteType.APPROVE,
        cfo=VoteType.APPROVE,
        coo=VoteType.REJECT,
        cmo=VoteType.REJECT,
        chair=VoteType.REJECT  # CHAIR breaks tie by rejecting
    )

    result = tally_votes(votes=votes, roles=load_role_configs(), proposal_id="prop-2-2-tie-reject")
    
    mock_log_event.assert_called_once()
    logged_data = mock_log_event.call_args.kwargs["data"]
    assert logged_data["decision"] == "rejected"
    assert logged_data["reason"] == "chair_tiebreak"
    assert logged_data["chair_tiebreak_used"] is True
    assert logged_data["chair_vote"] == "reject"


@patch("voting.validate_constitutional_compliance")
@patch("voting.log_event")
def test_2_2_tie_missing_chair_raises_error(
    mock_log_event: MagicMock,
    mock_validate: MagicMock
) -> None:
    """Test 2-2 tie without CHAIR vote raises ConstitutionalError."""
    mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])

    votes = [
        _make_vote("CEO", VoteType.APPROVE),
        _make_vote("CFO", VoteType.APPROVE),
        _make_vote("COO", VoteType.REJECT),
        _make_vote("CMO", VoteType.REJECT),
        _make_vote("LEGAL", VoteType.APPROVE),
        _make_vote("CISO", VoteType.APPROVE),
        _make_vote("SECRETARY", VoteType.ABSTAIN)
        # CHAIR vote missing
    ]

    with pytest.raises(ConstitutionalError, match="2-2 tie requires Chair"):
        tally_votes(votes=votes, roles=load_role_configs(), proposal_id="prop-2-2-no-chair")


@patch("voting.validate_constitutional_compliance")
@patch("voting.log_event")
def test_legal_veto_blocks_proposal(
    mock_log_event: MagicMock,
    mock_validate: MagicMock
) -> None:
    """LEGAL veto blocks proposal even with 4-0 approval."""
    mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])

    votes = _make_all_votes(
        ceo=VoteType.APPROVE,
        cfo=VoteType.APPROVE,
        coo=VoteType.APPROVE,
        cmo=VoteType.APPROVE,
        legal=VoteType.VETO  # LEGAL vetoes
    )

    result = tally_votes(votes=votes, roles=load_role_configs(), proposal_id="prop-legal-veto")
    
    mock_log_event.assert_called_once()
    logged_data = mock_log_event.call_args.kwargs["data"]
    assert logged_data["decision"] == "rejected"
    assert "LEGAL veto" in logged_data["reason"] or logged_data["veto_role"] == "LEGAL"
    assert logged_data["veto_triggered"] is True
    assert logged_data["approve_count"] == 4  # Still counted but veto overrides


@patch("voting.validate_constitutional_compliance")
@patch("voting.log_event")
def test_ciso_veto_blocks_proposal(
    mock_log_event: MagicMock,
    mock_validate: MagicMock
) -> None:
    """CISO veto blocks proposal even with 4-0 approval."""
    mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])

    votes = _make_all_votes(
        ceo=VoteType.APPROVE,
        cfo=VoteType.APPROVE,
        coo=VoteType.APPROVE,
        cmo=VoteType.APPROVE,
        ciso=VoteType.VETO  # CISO vetoes
    )

    result = tally_votes(votes=votes, roles=load_role_configs(), proposal_id="prop-ciso-veto")
    
    mock_log_event.assert_called_once()
    logged_data = mock_log_event.call_args.kwargs["data"]
    assert logged_data["decision"] == "rejected"
    assert "CISO veto" in logged_data["reason"] or logged_data["veto_role"] == "CISO"
    assert logged_data["veto_triggered"] is True


@patch("voting.validate_constitutional_compliance")
@patch("voting.log_event")
def test_missing_primary_voter_raises_error(
    mock_log_event: MagicMock,
    mock_validate: MagicMock
) -> None:
    """Missing vote from a primary voter raises ConstitutionalError."""
    mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])

    votes = [
        _make_vote("CEO", VoteType.APPROVE),
        _make_vote("CFO", VoteType.APPROVE),
        _make_vote("COO", VoteType.APPROVE),
        # CMO missing
        _make_vote("LEGAL", VoteType.APPROVE),
        _make_vote("CISO", VoteType.APPROVE),
        _make_vote("CHAIR", VoteType.ABSTAIN),
        _make_vote("SECRETARY", VoteType.ABSTAIN)
    ]

    with pytest.raises(ConstitutionalError, match="All 4 primary voters"):
        tally_votes(votes=votes, roles=load_role_configs(), proposal_id="prop-missing-voter")




@patch("voting.validate_constitutional_compliance")
@patch("voting.log_event")
def test_vote_result_includes_all_roles(
    mock_log_event: MagicMock,
    mock_validate: MagicMock
) -> None:
    """VoteResult should include all 8 roles in votes dict for logging."""
    mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])

    votes = _make_all_votes(
        ceo=VoteType.APPROVE,
        cfo=VoteType.APPROVE,
        coo=VoteType.APPROVE,
        cmo=VoteType.APPROVE
    )

    result = tally_votes(votes=votes, roles=load_role_configs(), proposal_id="prop-all-roles")
    
    # All 8 roles should be in votes dict (for Rule 8 compliance)
    assert len(result.votes) == 8
    assert "ceo_agent" in result.votes
    assert "cfo_agent" in result.votes
    assert "coo_agent" in result.votes
    assert "cmo_agent" in result.votes
    assert "legal_agent" in result.votes
    assert "ciso_agent" in result.votes
    assert "chair_agent" in result.votes
    assert "secretary_agent" in result.votes
    
    # Primary voters should have 0.25 weight
    assert result.votes["ceo_agent"] == 0.25
    assert result.votes["cfo_agent"] == 0.25
    assert result.votes["coo_agent"] == 0.25
    assert result.votes["cmo_agent"] == 0.25
    
    # Non-voting roles should have 0.0 weight
    assert result.votes["legal_agent"] == 0.0
    assert result.votes["ciso_agent"] == 0.0
    assert result.votes["chair_agent"] == 0.0
    assert result.votes["secretary_agent"] == 0.0
    
    mock_log_event.assert_called_once()


"""
Tests for governance voting logic and constitutional safeguards.
"""

# Standard library
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

# Third-party
import pytest

# Path setup
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "Governance Layer" / "governance"))
sys.path.insert(0, str(PROJECT_ROOT / "Governance Layer" / "roles"))
sys.path.insert(0, str(PROJECT_ROOT / "Memory Systems" / "Codebase Memory"))

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


@patch("voting.validate_constitutional_compliance")
@patch("voting.log_event")
def test_rule9_weight_enforcement(
    mock_log_event: MagicMock,
    mock_validate: MagicMock
) -> None:
    """Normalized weights exceeding 25% should raise ConstitutionalError."""
    mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])

    votes = [
        _make_vote("CEO", VoteType.APPROVE),
        _make_vote("CFO", VoteType.REJECT),
        _make_vote("COO", VoteType.REJECT),
        _make_vote("LEGAL", VoteType.REJECT),
        _make_vote("CMO", VoteType.REJECT)
    ]

    with pytest.raises(ConstitutionalError, match="Rule 9"):
        tally_votes(votes=votes, roles=load_role_configs(), proposal_id="prop-rule9")

    mock_log_event.assert_not_called()


@patch("voting.validate_constitutional_compliance")
@patch("voting.log_event")
def test_veto_power_blocks_proposal(
    mock_log_event: MagicMock,
    mock_validate: MagicMock
) -> None:
    """Legal or CISO veto should reject proposal regardless of majority."""
    mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])

    votes = [
        _make_vote("CEO", VoteType.APPROVE),
        _make_vote("CFO", VoteType.APPROVE),
        _make_vote("COO", VoteType.APPROVE),
        _make_vote("CMO", VoteType.APPROVE),
        _make_vote("LEGAL", VoteType.VETO),
        _make_vote("CISO", VoteType.APPROVE),
        _make_vote("CHAIR", VoteType.APPROVE),
        _make_vote("SECRETARY", VoteType.ABSTAIN)
    ]

    tally_votes(votes=votes, roles=load_role_configs(), proposal_id="prop-veto")

    mock_log_event.assert_called_once()
    logged_data = mock_log_event.call_args.kwargs["data"]
    assert logged_data["decision"] == "rejected"
    assert "veto" in logged_data["reason"]


@patch("voting.validate_constitutional_compliance")
@patch("voting.log_event")
def test_chair_tiebreaker(
    mock_log_event: MagicMock,
    mock_validate: MagicMock
) -> None:
    """Chair should resolve ties when approve and reject weights match."""
    mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])

    votes = [
        _make_vote("CEO", VoteType.REJECT),
        _make_vote("LEGAL", VoteType.REJECT),
        _make_vote("CISO", VoteType.REJECT),
        _make_vote("CFO", VoteType.APPROVE),
        _make_vote("COO", VoteType.APPROVE),
        _make_vote("CMO", VoteType.APPROVE),
        _make_vote("SECRETARY", VoteType.ABSTAIN),
        _make_vote("CHAIR", VoteType.APPROVE)
    ]

    tally_votes(votes=votes, roles=load_role_configs(), proposal_id="prop-tie")

    mock_log_event.assert_called_once()
    logged_data = mock_log_event.call_args.kwargs["data"]
    assert logged_data["decision"] == "approved"
    assert logged_data["reason"] == "chair_tiebreak"


@patch("voting.validate_constitutional_compliance")
@patch("voting.log_event")
def test_vote_result_totals(mock_log_event: MagicMock, mock_validate: MagicMock) -> None:
    """Successful tallies should return vote results totaling 1.0 weight."""
    mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])

    votes = [
        _make_vote("CEO", VoteType.APPROVE),
        _make_vote("CFO", VoteType.APPROVE),
        _make_vote("COO", VoteType.APPROVE),
        _make_vote("CMO", VoteType.APPROVE),
        _make_vote("LEGAL", VoteType.REJECT),
        _make_vote("CISO", VoteType.REJECT),
        _make_vote("CHAIR", VoteType.REJECT),
        _make_vote("SECRETARY", VoteType.ABSTAIN)
    ]

    result = tally_votes(votes=votes, roles=load_role_configs(), proposal_id="prop-success")
    assert result.total_weight == pytest.approx(1.0, rel=1e-9)
    assert len(result.votes) == 8
    mock_log_event.assert_called_once()


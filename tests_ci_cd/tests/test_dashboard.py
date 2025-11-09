"""Tests for dashboard components rendering."""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

import pytest
from pytest_mock import MockerFixture

from owner_control.dashboard import components


def _mock_compliance(mocker: MockerFixture) -> SimpleNamespace:
    """Return a mocked compliance result."""
    compliance_result = SimpleNamespace(
        is_compliant=True,
        violated_rules=[],
        error_messages=[],
        validation_details={},
    )
    mocker.patch(
        "owner_control.dashboard.components.validate_constitutional_compliance",
        return_value=compliance_result,
    )
    return compliance_result


def test_proposal_card_renders(mocker: MockerFixture) -> None:
    """Ensure proposal card renders expected elements."""
    _mock_compliance(mocker)
    mocker.patch(
        "owner_control.dashboard.components.st.container",
        return_value=nullcontext(),
    )
    subheader_spy = mocker.patch(
        "owner_control.dashboard.components.st.subheader"
    )
    markdown_spy = mocker.patch(
        "owner_control.dashboard.components.st.markdown"
    )
    columns_spy = mocker.patch(
        "owner_control.dashboard.components.st.columns",
        return_value=(mocker.MagicMock(), mocker.MagicMock()),
    )
    caption_spy = mocker.patch(
        "owner_control.dashboard.components.st.caption"
    )

    proposal: Mapping[str, Any] = {
        "id": "proposal-1",
        "title": "Test Proposal",
        "description": "Detailed description",
        "financial_impact": 1000.0,
        "legal_risk": 0.1,
        "status": "draft",
    }

    components.proposal_card(proposal)

    subheader_spy.assert_called_once_with("Active Proposal")
    assert markdown_spy.call_count >= 2
    columns_spy.assert_called_once()
    caption_spy.assert_called_once()


def test_vote_summary_renders_table(mocker: MockerFixture) -> None:
    """Ensure vote summary renders dataframe."""
    _mock_compliance(mocker)
    mocker.patch(
        "owner_control.dashboard.components.st.container",
        return_value=nullcontext(),
    )
    subheader_spy = mocker.patch(
        "owner_control.dashboard.components.st.subheader"
    )
    dataframe_spy = mocker.patch(
        "owner_control.dashboard.components.st.dataframe"
    )
    info_spy = mocker.patch(
        "owner_control.dashboard.components.st.info"
    )
    caption_spy = mocker.patch(
        "owner_control.dashboard.components.st.caption"
    )

    vote_result: Mapping[str, Any] = {
        "proposal_id": "proposal-1",
        "session_id": "session-1",
        "votes": {
            "member_a": 0.2,
            "member_b": 0.2,
            "member_c": 0.2,
            "member_d": 0.2,
            "member_e": 0.2,
        },
    }

    components.vote_summary(vote_result)

    subheader_spy.assert_called_once_with("Board Vote Summary")
    dataframe_spy.assert_called_once()
    info_spy.assert_not_called()
    caption_spy.assert_called_once()


@pytest.mark.parametrize("is_compliant,expected_call", [(True, "success"), (False, "error")])
def test_constitutional_compliance_indicator(
    mocker: MockerFixture, is_compliant: bool, expected_call: str
) -> None:
    """Ensure compliance indicator reflects status."""
    _mock_compliance(mocker)
    mocker.patch(
        "owner_control.dashboard.components.st.container",
        return_value=nullcontext(),
    )
    success_spy = mocker.patch(
        "owner_control.dashboard.components.st.success"
    )
    error_spy = mocker.patch(
        "owner_control.dashboard.components.st.error"
    )
    json_spy = mocker.patch(
        "owner_control.dashboard.components.st.json"
    )

    details: Mapping[str, Any] = {"violations": []}

    components.constitutional_compliance_indicator(
        is_compliant=is_compliant, details=details
    )

    if expected_call == "success":
        success_spy.assert_called_once()
        error_spy.assert_not_called()
    else:
        error_spy.assert_called_once()
        success_spy.assert_not_called()
    json_spy.assert_called_once_with(details)


def test_execution_log_viewer_with_entries(mocker: MockerFixture) -> None:
    """Ensure execution log viewer renders dataframe when entries exist."""
    _mock_compliance(mocker)
    mocker.patch(
        "owner_control.dashboard.components.st.container",
        return_value=nullcontext(),
    )
    dataframe_spy = mocker.patch(
        "owner_control.dashboard.components.st.dataframe"
    )
    info_spy = mocker.patch(
        "owner_control.dashboard.components.st.info"
    )

    entries: Sequence[Mapping[str, Any]] = [
        {"timestamp": "2025-01-01T00:00:00Z", "type": "event", "data": {}}
    ]

    components.execution_log_viewer(entries)

    dataframe_spy.assert_called_once()
    info_spy.assert_not_called()


def test_execution_log_viewer_no_entries(mocker: MockerFixture) -> None:
    """Ensure execution log viewer shows info when no entries."""
    _mock_compliance(mocker)
    mocker.patch(
        "owner_control.dashboard.components.st.container",
        return_value=nullcontext(),
    )
    dataframe_spy = mocker.patch(
        "owner_control.dashboard.components.st.dataframe"
    )
    info_spy = mocker.patch(
        "owner_control.dashboard.components.st.info"
    )

    components.execution_log_viewer([])

    dataframe_spy.assert_not_called()
    info_spy.assert_called_once_with("No log entries available.")


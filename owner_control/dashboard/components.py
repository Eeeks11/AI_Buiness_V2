"""Streamlit dashboard components for owner oversight."""

from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

import streamlit as st

from constitutional_layer_immutable.constitution import (
    validate_constitutional_compliance,
)
from memory_systems.codebase_memory.models.core import ConstitutionalError

logger = logging.getLogger(__name__)


def _ensure_dashboard_compliance(action_type: str) -> None:
    """Validate constitutional compliance for dashboard rendering."""
    validation = validate_constitutional_compliance(
        action={
            "type": action_type,
            "description": f"Dashboard render action: {action_type}",
            "owner_authorized": True,
            "logged": True,
        }
    )
    if not validation.is_compliant:
        logger.error(
            "Dashboard render failed compliance check",
            extra={
                "event": "dashboard_compliance_violation",
                "action_type": action_type,
                "violations": validation.violated_rules,
            },
        )
        raise ConstitutionalError(
            f"Rule 10 Violation: Dashboard action '{action_type}' blocked {validation.violated_rules}"
        )


def proposal_card(proposal: Mapping[str, Any]) -> None:
    """
    Render a proposal summary card.

    Args:
        proposal: Mapping containing proposal details.
    """
    logger.info(
        "Rendering proposal card",
        extra={
            "event": "dashboard_proposal_rendered",
            "proposal_id": proposal.get("id"),
        },
    )
    _ensure_dashboard_compliance("dashboard_proposal_card")

    with st.container():
        st.subheader("Active Proposal")
        st.markdown(f"**Title:** {proposal.get('title', 'Unknown')}")
        st.markdown(f"**Description:** {proposal.get('description', 'N/A')}")
        col1, col2 = st.columns(2)
        with col1:
            st.metric(
                "Financial Impact",
                f"{proposal.get('financial_impact', 0):,.2f}",
            )
        with col2:
            st.metric("Legal Risk", f"{proposal.get('legal_risk', 0):.2f}")
        st.caption(f"Status: {proposal.get('status', 'N/A')}")


def vote_summary(vote_result: Mapping[str, Any]) -> None:
    """
    Render a summary of voting results.

    Args:
        vote_result: Mapping containing voting information.
    """
    logger.info(
        "Rendering vote summary",
        extra={
            "event": "dashboard_vote_summary_rendered",
            "proposal_id": vote_result.get("proposal_id"),
        },
    )
    _ensure_dashboard_compliance("dashboard_vote_summary")

    with st.container():
        st.subheader("Board Vote Summary")
        votes = vote_result.get("votes", {})
        if votes:
            st.dataframe(
                {"Member": list(votes.keys()), "Weight": list(votes.values())},
                use_container_width=True,
            )
        else:
            st.info("No votes recorded.")
        st.caption(f"Session ID: {vote_result.get('session_id', 'N/A')}")


def constitutional_compliance_indicator(
    is_compliant: bool, details: Mapping[str, Any]
) -> None:
    """
    Render a constitutional compliance indicator.

    Args:
        is_compliant: Flag indicating compliance status.
        details: Mapping with compliance details.
    """
    logger.info(
        "Rendering constitutional compliance indicator",
        extra={
            "event": "dashboard_compliance_indicator_rendered",
            "is_compliant": is_compliant,
        },
    )
    _ensure_dashboard_compliance("dashboard_compliance_indicator")

    with st.container():
        st.subheader("Constitutional Compliance")
        if is_compliant:
            st.success("All constitutional checks passed.")
        else:
            st.error("Constitutional violations detected.")
        st.json(details)


def execution_log_viewer(log_entries: Sequence[Mapping[str, Any]]) -> None:
    """
    Render a viewer for recent execution logs.

    Args:
        log_entries: Sequence of log entry mappings.
    """
    logger.info(
        "Rendering execution log viewer",
        extra={
            "event": "dashboard_log_viewer_rendered",
            "entry_count": len(log_entries),
        },
    )
    _ensure_dashboard_compliance("dashboard_execution_log_viewer")

    with st.container():
        st.subheader("Execution Logs")
        if log_entries:
            st.dataframe(list(log_entries), use_container_width=True)
        else:
            st.info("No log entries available.")



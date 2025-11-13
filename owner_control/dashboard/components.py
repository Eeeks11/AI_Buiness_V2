"""Streamlit dashboard components for owner oversight."""

from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

import streamlit as st

from constitutional_layer_immutable.constitution import (
    validate_constitutional_compliance,
)
from models.core import ConstitutionalError

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
    Render a summary of voting results with voting vs advisory role indicators.

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
        
        # Load role configs to determine voting vs advisory roles
        from pathlib import Path
        import sys
        import json
        
        project_root = Path(__file__).parent.parent.parent
        role_config_path = project_root / "governance_layer" / "roles" / "role_configs.json"
        
        try:
            with open(role_config_path, "r", encoding="utf-8") as f:
                role_configs = json.load(f)
        except Exception:
            role_configs = {}
        
        PRIMARY_VOTERS = {"CEO", "CFO", "COO", "CMO"}
        VETO_ROLES = {"LEGAL", "CISO"}
        
        votes = vote_result.get("votes", {})
        
        if votes:
            # Separate voting members from advisory roles
            voting_members = []
            advisory_members = []
            
            for member_id, weight in votes.items():
                # Extract role from member_id (e.g., "ceo_agent" -> "CEO")
                role = member_id.upper().replace("_AGENT", "")
                
                role_config = role_configs.get(role, {})
                is_voter = role in PRIMARY_VOTERS
                has_veto = role_config.get("veto_power", False)
                role_name = role_config.get("name", role)
                
                member_info = {
                    "Member": member_id,
                    "Role": role_name,
                    "Weight": f"{weight:.1%}" if weight > 0 else "0%",
                    "Type": "Voting Member" if is_voter else ("Veto Authority" if has_veto else "Advisory"),
                    "Veto Power": "🔴 Yes" if has_veto else "⚪ No"
                }
                
                if is_voter:
                    voting_members.append(member_info)
                else:
                    advisory_members.append(member_info)
            
            # Display voting members
            if voting_members:
                st.markdown("### 🗳️ Voting Members (25% each)")
                voting_df = {
                    "Role": [m["Role"] for m in voting_members],
                    "Weight": [m["Weight"] for m in voting_members],
                    "Member ID": [m["Member"] for m in voting_members]
                }
                st.dataframe(voting_df, use_container_width=True)
            
            # Display advisory roles
            if advisory_members:
                st.markdown("### 📋 Advisory Roles")
                advisory_df = {
                    "Role": [m["Role"] for m in advisory_members],
                    "Type": [m["Type"] for m in advisory_members],
                    "Veto Power": [m["Veto Power"] for m in advisory_members],
                    "Member ID": [m["Member"] for m in advisory_members]
                }
                st.dataframe(advisory_df, use_container_width=True)
            
            # Show decision details
            decision = vote_result.get("decision")
            reason = vote_result.get("reason", "")
            veto_triggered = vote_result.get("veto_triggered", False)
            chair_tiebreak = vote_result.get("chair_tiebreak_used", False)
            
            if decision:
                col1, col2 = st.columns(2)
                with col1:
                    if decision == "approved":
                        st.success(f"✅ Decision: **{decision.upper()}**")
                    else:
                        st.error(f"❌ Decision: **{decision.upper()}**")
                
                with col2:
                    if veto_triggered:
                        veto_role = vote_result.get("veto_role", "Unknown")
                        st.warning(f"🚫 Veto by {veto_role}")
                    elif chair_tiebreak:
                        chair_vote = vote_result.get("chair_vote", "Unknown")
                        st.info(f"⚖️ CHAIR tie-breaker: {chair_vote}")
                    else:
                        st.info(f"📊 Reason: {reason}")
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



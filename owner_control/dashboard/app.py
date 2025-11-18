"""Streamlit application for owner oversight and authorization."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Mapping, Optional
from datetime import datetime

import streamlit as st

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config_settings.config import get_settings
from constitutional_layer_immutable.constitution import (
    validate_constitutional_compliance,
)
from models.core import ConstitutionalError, ProposalStatus
from owner_control.dashboard.components import (
    constitutional_compliance_indicator,
    execution_log_viewer,
    proposal_card,
    vote_summary,
    deliberation_viewer,
    role_structure_display,
)
from owner_control.dashboard.data_retrieval import (
    get_all_proposals,
    get_proposal_by_id,
    get_pending_owner_approvals,
    get_governance_events_for_proposal,
)
from owner_control.owner_gate.signature import sign_action
from utilities.logger import get_recent_logs, log_event

# Import governance cycle runner
from governance_layer.orchestrator.langgraph_state_machine import run_governance_cycle

logger = logging.getLogger(__name__)


def _log_dashboard_event(event_type: str, data: Mapping[str, Any]) -> None:
    """Write dashboard events to persistent log."""
    try:
        log_event(event_type=event_type, data=dict(data), metadata={"source": "dashboard"})
    except Exception as exc:
        logger.warning(
            "Failed to persist dashboard event",
            extra={
                "event": "dashboard_log_failure",
                "event_type": event_type,
                "error": str(exc),
            },
        )


def _create_proposal_form() -> Optional[dict]:
    """Render proposal creation form and return proposal dict if submitted."""
    with st.expander("➕ Create New Proposal", expanded=False):
        with st.form("create_proposal_form"):
            proposal_id = st.text_input(
                "Proposal ID",
                value=f"proposal-{uuid.uuid4().hex[:8]}",
                help="Unique identifier for this proposal"
            )
            title = st.text_input("Title", placeholder="Enter proposal title")
            description = st.text_area(
                "Description",
                placeholder="Enter detailed proposal description",
                height=150
            )
            col1, col2 = st.columns(2)
            with col1:
                financial_impact = st.number_input(
                    "Financial Impact ($)",
                    min_value=0.0,
                    value=0.0,
                    step=1000.0,
                    format="%.2f"
                )
            with col2:
                legal_risk = st.slider(
                    "Legal Risk Score",
                    min_value=0.0,
                    max_value=1.0,
                    value=0.0,
                    step=0.01,
                    help="Legal risk assessment (0.0 = no risk, 1.0 = high risk)"
                )
            
            submitted = st.form_submit_button("Submit Proposal", type="primary")
            
            if submitted:
                if not title or not description:
                    st.error("Title and description are required.")
                    return None
                
                proposal = {
                    "id": proposal_id,
                    "title": title,
                    "description": description,
                    "financial_impact": financial_impact,
                    "legal_risk": legal_risk,
                    "status": ProposalStatus.DRAFT.value,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
                
                # Log proposal creation with all fields
                _log_dashboard_event(
                    event_type="proposal_created",
                    data={
                        "proposal_id": proposal["id"],
                        "proposal": proposal,  # Include full proposal in nested structure
                        "title": proposal["title"],
                        "description": proposal["description"],
                        "financial_impact": proposal["financial_impact"],
                        "legal_risk": proposal["legal_risk"],
                        "status": proposal["status"]
                    }
                )
                
                return proposal
    
    return None


def _run_governance_cycle_for_proposal(proposal: dict) -> None:
    """Run governance cycle for a proposal and show progress."""
    try:
        with st.spinner("Running governance cycle..."):
            # Create a status container
            status_container = st.empty()
            
            status_container.info("🔄 Starting governance cycle...")
            
            # Run the governance cycle
            result = run_governance_cycle(
                proposal=proposal,
                owner_signature=None,
                owner_id=get_settings().owner_id
            )
            
            status_container.success("✅ Governance cycle completed!")
            
            # Log the result
            _log_dashboard_event(
                event_type="dashboard_governance_cycle_triggered",
                data={
                    "proposal_id": proposal.get("id"),
                    "status": "completed"
                }
            )
            
            st.balloons()
            st.info("Proposal has been processed through the governance workflow. Check the proposal list to see results.")
            
    except ConstitutionalError as exc:
        st.error(f"Constitutional error: {exc}")
        _log_dashboard_event(
            event_type="dashboard_governance_cycle_error",
            data={
                "proposal_id": proposal.get("id"),
                "error": str(exc)
            }
        )
    except Exception as exc:
        st.error(f"Error running governance cycle: {exc}")
        logger.exception("Governance cycle failed")
        _log_dashboard_event(
            event_type="dashboard_governance_cycle_error",
            data={
                "proposal_id": proposal.get("id"),
                "error": str(exc)
            }
        )


def _build_authorization_payload(
    owner_id: str, proposal: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Build payload used for owner authorization signatures."""
    return {
        "action": "execute_decision",
        "proposal": dict(proposal),
        "owner_id": owner_id,
    }


def main() -> None:
    """Render the Streamlit dashboard for owner oversight."""
    st.set_page_config(page_title="AI Business Owner Dashboard", layout="wide")

    settings = get_settings()
    
    # Initialize session state
    if "selected_proposal_id" not in st.session_state:
        st.session_state["selected_proposal_id"] = None
    if "refresh_trigger" not in st.session_state:
        st.session_state["refresh_trigger"] = 0

    validation = validate_constitutional_compliance(
        action={
            "type": "dashboard_load",
            "description": "Dashboard initialization",
            "owner_authorized": True,
            "logged": True,
        }
    )
    compliance_details = {
        "is_compliant": validation.is_compliant,
        "violated_rules": [rule.value for rule in validation.violated_rules],
        "errors": validation.error_messages,
    }

    logger.info(
        "Dashboard page loaded",
        extra={
            "event": "dashboard_page_load",
            "owner_id": settings.owner_id,
            "owner_auth_mode": settings.owner_auth_mode,
        },
    )
    _log_dashboard_event(
        event_type="dashboard_page_load",
        data={
            "owner_id": settings.owner_id,
            "owner_auth_mode": settings.owner_auth_mode,
        },
    )

    st.title("🏛️ AI Business Governance Dashboard")
    
    # Sidebar
    with st.sidebar:
        st.header("Owner Controls")
        st.metric("Authorization Mode", settings.owner_auth_mode)
        st.metric("Owner ID", settings.owner_id or "Not configured")
        st.write("Active Models")
        st.write(settings.active_models)
        st.toggle(
            "Owner Gate Enabled",
            value=settings.owner_gate_enabled,
            disabled=True,
        )
        
        st.divider()
        
        # Refresh button
        if st.button("🔄 Refresh Data", width="stretch"):
            st.session_state["refresh_trigger"] += 1
            st.rerun()
        
        # Display role structure
        st.header("Board Structure")
        role_structure_display()

    # Main content tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Proposals", "➕ Create Proposal", "⏳ Pending Approvals", "📊 Audit Trail"])

    with tab1:
        st.header("All Proposals")
        
        # Get all proposals
        proposals = get_all_proposals(limit=50)
        
        if not proposals:
            st.info("No proposals found. Create a new proposal to get started.")
        else:
            # Proposal selector
            proposal_options = {f"{p['id']} - {p.get('title', 'Untitled')}": p['id'] for p in proposals}
            selected_label = st.selectbox(
                "Select Proposal",
                options=list(proposal_options.keys()),
                index=0 if proposals else None,
                key="proposal_selector"
            )
            
            if selected_label:
                selected_proposal_id = proposal_options[selected_label]
                st.session_state["selected_proposal_id"] = selected_proposal_id
                
                # Get full proposal data
                proposal = get_proposal_by_id(selected_proposal_id)
                
                if proposal:
                    # Display proposal details
                    proposal_card(proposal)
                    
                    # Display vote summary if available
                    if proposal.get("vote_result"):
                        vote_summary(proposal["vote_result"])
                    
                    # Display deliberations
                    if proposal.get("deliberation_responses"):
                        deliberation_viewer(proposal["deliberation_responses"])
                    
                    # Display constitutional compliance
                    constitutional_compliance_indicator(
                        is_compliant=validation.is_compliant,
                        details=compliance_details
                    )
                    
                    # Owner actions
                    st.divider()
                    st.subheader("Owner Actions")
                    
                    vote_result = proposal.get("vote_result")
                    can_approve = (
                        vote_result and 
                        vote_result.get("decision") == "approved" and
                        not proposal.get("owner_authorized", False)
                    )
                    
                    if can_approve:
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            if st.button("✅ Approve & Sign", type="primary", width="stretch"):
                                try:
                                    authorization_payload = _build_authorization_payload(
                                        owner_id=settings.owner_id or "unknown_owner",
                                        proposal=proposal,
                                    )
                                    signature = sign_action(
                                        owner_id=settings.owner_id or "unknown_owner",
                                        payload=authorization_payload,
                                    )
                                    
                                    # Log owner approval
                                    _log_dashboard_event(
                                        event_type="owner_proposal_approved",
                                        data={
                                            "proposal_id": proposal["id"],
                                            "signature": signature,
                                            "owner_id": settings.owner_id
                                        }
                                    )
                                    
                                    st.success("✅ Proposal approved and signed!")
                                    st.code(signature, language="text")
                                    
                                    # Update proposal status
                                    proposal["owner_authorized"] = True
                                    
                                except ConstitutionalError as exc:
                                    st.error(f"Failed to approve: {exc}")
                        
                        with col2:
                            if st.button("❌ Reject", width="stretch"):
                                _log_dashboard_event(
                                    event_type="owner_proposal_rejected",
                                    data={
                                        "proposal_id": proposal["id"],
                                        "owner_id": settings.owner_id
                                    }
                                )
                                st.warning("Proposal rejected by owner.")
                    else:
                        if proposal.get("owner_authorized"):
                            st.success("✅ This proposal has been approved by the owner.")
                        elif vote_result and vote_result.get("decision") != "approved":
                            st.info(f"Board decision: {vote_result.get('decision', 'unknown')}. Owner approval not required.")
                        else:
                            st.info("⏳ Waiting for board decision...")
                    
                    # Show governance events timeline
                    st.divider()
                    st.subheader("Governance Timeline")
                    events = get_governance_events_for_proposal(selected_proposal_id)
                    if events:
                        for event in events[-10:]:  # Show last 10 events
                            event_type = event.get("type", "unknown")
                            timestamp = event.get("timestamp", "")
                            data = event.get("data", {})
                            
                            with st.expander(f"{event_type} - {timestamp[:19] if timestamp else 'Unknown time'}"):
                                st.json(data)
                    else:
                        st.info("No governance events found for this proposal.")
                else:
                    st.warning(f"Proposal {selected_proposal_id} not found.")

    with tab2:
        st.header("Create New Proposal")
        
        new_proposal = _create_proposal_form()
        
        if new_proposal:
            st.success("Proposal created! Starting governance cycle...")
            
            # Run governance cycle
            _run_governance_cycle_for_proposal(new_proposal)
            
            # Refresh to show new proposal
            st.session_state["refresh_trigger"] += 1
            st.rerun()

    with tab3:
        st.header("Pending Owner Approvals")
        
        pending = get_pending_owner_approvals()
        
        if not pending:
            st.success("✅ No pending approvals. All board-approved proposals have been authorized.")
        else:
            st.info(f"Found {len(pending)} proposal(s) awaiting owner approval.")
            
            for proposal in pending:
                st.divider()
                
                # Display proposal card
                proposal_card(proposal)
                
                # Show vote result if available
                if proposal.get("vote_result"):
                    vote_summary(proposal["vote_result"])
                
                # Approval buttons
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button(f"✅ Approve", key=f"approve_{proposal['id']}", type="primary"):
                        try:
                            from governance_layer.orchestrator.langgraph_state_machine import resume_from_approval
                            
                            authorization_payload = _build_authorization_payload(
                                owner_id=settings.owner_id or "unknown_owner",
                                proposal=proposal,
                            )
                            signature = sign_action(
                                owner_id=settings.owner_id or "unknown_owner",
                                payload=authorization_payload,
                            )
                            
                            # Resume governance cycle with approval
                            result = resume_from_approval(
                                proposal_id=proposal["id"],
                                owner_signature=signature,
                                owner_id=settings.owner_id or "unknown_owner",
                                approved=True
                            )
                            
                            _log_dashboard_event(
                                event_type="owner_proposal_approved",
                                data={
                                    "proposal_id": proposal["id"],
                                    "signature": signature,
                                    "owner_id": settings.owner_id
                                }
                            )
                            
                            st.success("✅ Proposal approved! Execution proceeding...")
                            st.session_state["refresh_trigger"] += 1
                            st.rerun()
                            
                        except Exception as exc:
                            st.error(f"Failed to approve: {exc}")
                            logger.exception("Approval failed")
                
                with col2:
                    if st.button(f"❌ Reject", key=f"reject_{proposal['id']}"):
                        try:
                            from governance_layer.orchestrator.langgraph_state_machine import resume_from_approval
                            
                            authorization_payload = _build_authorization_payload(
                                owner_id=settings.owner_id or "unknown_owner",
                                proposal=proposal,
                            )
                            signature = sign_action(
                                owner_id=settings.owner_id or "unknown_owner",
                                payload=authorization_payload,
                            )
                            
                            # Resume governance cycle with rejection
                            result = resume_from_approval(
                                proposal_id=proposal["id"],
                                owner_signature=signature,
                                owner_id=settings.owner_id or "unknown_owner",
                                approved=False
                            )
                            
                            _log_dashboard_event(
                                event_type="owner_proposal_rejected",
                                data={
                                    "proposal_id": proposal["id"],
                                    "owner_id": settings.owner_id
                                }
                            )
                            
                            st.warning("❌ Proposal rejected by owner.")
                            st.session_state["refresh_trigger"] += 1
                            st.rerun()
                            
                        except Exception as exc:
                            st.error(f"Failed to reject: {exc}")
                            logger.exception("Rejection failed")

    with tab4:
        st.header("Audit Trail")
        
        recent_logs = get_recent_logs(limit=100)
        execution_log_viewer(recent_logs)


if __name__ == "__main__":
    main()

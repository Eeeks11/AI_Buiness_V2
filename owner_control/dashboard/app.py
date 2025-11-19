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
from governance_layer.orchestrator.model_health_check import get_model_health_summary
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
            financial_impact = st.number_input(
                "Financial Impact ($)",
                min_value=0.0,
                value=0.0,
                step=1000.0,
                format="%.2f",
                help="Estimated financial impact of this proposal"
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
                    "legal_risk": 0.0,  # Legal risk will be assessed by Legal role during deliberation
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
                        "legal_risk": proposal["legal_risk"],  # Will be 0.0, assessed later by Legal role
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
        st.toggle(
            "Owner Gate Enabled",
            value=settings.owner_gate_enabled,
            disabled=True,
        )
        
        st.divider()
        
        # Display Roles with Models and Health Status
        st.subheader("Roles")
        try:
            # Get role-to-model mapping
            from governance_layer.governance.board import get_role_provider_map, get_model_assignment
            from governance_layer.roles.prompt_templates import load_role_configs
            from governance_layer.orchestrator.model_health_check import check_model_health
            
            role_configs = load_role_configs()
            role_providers = get_role_provider_map()
            
            # Check health for each role's specific provider (more accurate than matching from summary)
            # Use a cache to avoid checking the same provider multiple times
            provider_health_cache = {}
            
            # Display each role with model and health indicator
            for role in ["CHAIR", "CEO", "CFO", "COO", "CMO", "LEGAL", "CISO", "SECRETARY"]:
                if role not in role_configs:
                    continue
                
                # Get model name for display
                model_assignment = get_model_assignment(role)
                if model_assignment:
                    model_name = model_assignment.get("model", "Unknown")
                    # Format model name nicely - handle common patterns
                    # e.g., "gpt-5.1" -> "GPT-5.1", "gpt-4o" -> "GPT-4o"
                    parts = model_name.split("-")
                    formatted_parts = []
                    for part in parts:
                        if part:
                            # Capitalize common abbreviations (gpt, claude, gemini, etc.)
                            if part.lower() in ["gpt", "claude", "gemini", "grok", "mistral"]:
                                formatted_parts.append(part.upper())
                            else:
                                formatted_parts.append(part.capitalize())
                    display_model = "-".join(formatted_parts)
                else:
                    # Fallback to provider identifier
                    provider = role_providers.get(role, "Unknown")
                    if "/" in provider:
                        model_name = provider.split("/")[1]
                        # Format similarly
                        parts = model_name.split("-")
                        formatted_parts = []
                        for part in parts:
                            if part:
                                if part.lower() in ["gpt", "claude", "gemini", "grok", "mistral"]:
                                    formatted_parts.append(part.upper())
                                else:
                                    formatted_parts.append(part.capitalize())
                        display_model = "-".join(formatted_parts)
                    else:
                        display_model = provider
                
                # Get health status for this role's specific provider
                provider = role_providers.get(role, "")
                if provider:
                    # Check cache first
                    if provider not in provider_health_cache:
                        try:
                            # Quick health check with shorter timeout for sidebar
                            health_status = check_model_health(provider, timeout_seconds=2.0)
                            provider_health_cache[provider] = health_status.is_healthy
                        except Exception as e:
                            logger.debug(f"Health check failed for {role} ({provider}): {e}")
                            provider_health_cache[provider] = False
                    is_healthy = provider_health_cache[provider]
                else:
                    is_healthy = False
                
                health_indicator = "✓" if is_healthy else "✗"
                
                # Display role with model and health
                role_name = role_configs[role].get("name", role)
                st.write(f"{role_name}: {display_model} {health_indicator}")
                
        except Exception as e:
            logger.warning(f"Failed to display roles with models: {e}")
            st.warning("⚠️ Role model information unavailable")
        
        st.divider()
        
        # Refresh button
        if st.button("🔄 Refresh Data", width="stretch"):
            st.session_state["refresh_trigger"] += 1
            st.rerun()
        
        # Display role structure
        st.header("Board Structure")
        role_structure_display()

    # Main content tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 Proposals", "➕ Create Proposal", "⏳ Pending Approvals", "🤖 Model Health", "📊 Audit Trail"])

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
        
        # Check model health before allowing proposal creation
        try:
            health_summary = get_model_health_summary()
            if not health_summary["can_run_governance"]:
                st.error(
                    f"⚠️ **Cannot create proposals**: Only {health_summary['healthy_count']}/5 required models are healthy. "
                    f"Please check the '🤖 Model Health' tab and fix unhealthy models before creating proposals."
                )
                st.info("Go to the '🤖 Model Health' tab to see detailed error messages for each model.")
            else:
                st.success(f"✅ All systems ready: {health_summary['healthy_count']} models healthy")
        except Exception as e:
            st.warning(f"Could not check model health: {e}. Proceeding with caution...")
            logger.exception("Model health check failed before proposal creation")
        
        new_proposal = _create_proposal_form()
        
        if new_proposal:
            # Double-check health before running cycle
            try:
                health_summary = get_model_health_summary()
                if not health_summary["can_run_governance"]:
                    st.error(
                        f"❌ Cannot run governance cycle: Only {health_summary['healthy_count']}/5 models healthy. "
                        f"Proposal created but cycle will fail. Please fix models first."
                    )
                    return
            except Exception as e:
                logger.warning(f"Health check failed before cycle: {e}")
            
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
        st.header("🤖 LLM Model Health Status")
        
        # Refresh button
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("🔄 Refresh Health Check", type="primary"):
                st.rerun()
        
        try:
            # Get model health summary
            health_summary = get_model_health_summary()
            
            # Overall status
            st.divider()
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total Models", health_summary["total_models"])
            
            with col2:
                healthy_count = health_summary["healthy_count"]
                unhealthy_count = health_summary["unhealthy_count"]
                st.metric("Healthy", healthy_count, delta=f"-{unhealthy_count}" if unhealthy_count > 0 else None)
            
            with col3:
                can_run = health_summary["can_run_governance"]
                status_color = "🟢" if can_run else "🔴"
                st.metric("Can Run Governance", f"{status_color} {'Yes' if can_run else 'No'}")
            
            st.divider()
            
            # Detailed model status
            st.subheader("Model Details")
            
            # Map providers to roles for display
            from governance_layer.governance.board import get_role_provider_map, get_model_assignment
            from governance_layer.roles.prompt_templates import load_role_configs
            role_providers = get_role_provider_map()
            role_configs = load_role_configs()
            
            # Build provider -> roles mapping
            provider_to_roles = {}
            for role, provider in role_providers.items():
                if provider not in provider_to_roles:
                    provider_to_roles[provider] = []
                provider_to_roles[provider].append(role)
            
            if health_summary["models"]:
                for model in health_summary["models"]:
                    provider = model.get("provider", "")
                    roles_using = provider_to_roles.get(provider, [])
                    
                    with st.container():
                        col1, col2, col3, col4 = st.columns([2, 1, 1, 2])
                        
                        with col1:
                            status_icon = "✅" if model["is_healthy"] else "❌"
                            st.write(f"{status_icon} **{provider}**")
                            if model.get("model_name") and model["model_name"] != "unknown":
                                st.caption(f"Model: {model['model_name']}")
                            # Show which roles use this provider
                            if roles_using:
                                role_names = [role_configs.get(r, {}).get("name", r) for r in roles_using]
                                st.caption(f"Used by: {', '.join(role_names)}")
                        
                        with col2:
                            if model["is_healthy"]:
                                st.success("Healthy")
                            else:
                                st.error("Unhealthy")
                        
                        with col3:
                            if model.get("response_time_ms"):
                                st.metric("Response Time", f"{model['response_time_ms']:.0f}ms")
                            else:
                                st.write("—")
                        
                        with col4:
                            if not model["is_healthy"]:
                                error_type = model.get("error_type", "unknown")
                                error_msg = model.get("error", "Unknown error")
                                
                                # Color code error types
                                if error_type == "api_key_missing":
                                    st.error(f"🔑 **API Key Issue**: {error_msg}")
                                elif error_type == "network_error":
                                    st.warning(f"🌐 **Network Error**: {error_msg}")
                                elif error_type == "rate_limit":
                                    st.warning(f"⏱️ **Rate Limit**: {error_msg}")
                                elif error_type == "model_not_found":
                                    st.error(f"🔍 **Model Not Found**: {error_msg}")
                                elif error_type == "service_unavailable":
                                    st.warning(f"🔧 **Service Unavailable**: {error_msg}")
                                elif error_type == "billing_error":
                                    st.error(f"💳 **Billing Issue**: {error_msg}")
                                else:
                                    st.error(f"❓ **{error_type}**: {error_msg}")
                            
                            if model.get("checked_at"):
                                st.caption(f"Checked: {model['checked_at'][:19]}")
                        
                        st.divider()
            else:
                st.info("No models configured.")
            
            # Warning if governance cannot run
            if not health_summary["can_run_governance"]:
                st.error(
                    f"⚠️ **Warning**: Governance cycles cannot run. "
                    f"Only {health_summary['healthy_count']}/5 required models are healthy. "
                    f"Please fix the unhealthy models before creating proposals."
                )
            
        except Exception as e:
            st.error(f"Failed to check model health: {e}")
            logger.exception("Model health check failed in dashboard")
    
    with tab5:
        st.header("Audit Trail")
        
        recent_logs = get_recent_logs(limit=100)
        execution_log_viewer(recent_logs)


if __name__ == "__main__":
    main()

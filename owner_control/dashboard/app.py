"""Streamlit application for owner oversight and authorization."""

from __future__ import annotations

import logging
from typing import Any, Mapping

import streamlit as st

from config_settings.config import get_settings
from constitutional_layer_immutable.constitution import (
    validate_constitutional_compliance,
)
from memory_systems.codebase_memory.models.core import ConstitutionalError
from owner_control.dashboard.components import (
    constitutional_compliance_indicator,
    execution_log_viewer,
    proposal_card,
    vote_summary,
)
from owner_control.owner_gate.signature import sign_action
from Utilities.logger import get_recent_logs, log_event

logger = logging.getLogger(__name__)


def _initialize_session_state() -> None:
    """Ensure session state contains baseline data."""
    if "current_proposal" not in st.session_state:
        st.session_state["current_proposal"] = {
            "id": "proposal-001",
            "title": "Launch New AI Service",
            "description": "Deploy AI-driven analytics for enterprise clients.",
            "financial_impact": 150000.0,
            "legal_risk": 0.15,
            "status": "deliberation",
            "board_approved": False,
            "owner_authorized": False,
        }

    if "vote_result" not in st.session_state:
        st.session_state["vote_result"] = {
            "session_id": "session-001",
            "proposal_id": st.session_state["current_proposal"]["id"],
            "votes": {
                "ceo_agent": 0.2,
                "cfo_agent": 0.2,
                "coo_agent": 0.2,
                "cmo_agent": 0.2,
                "legal_agent": 0.2,
            },
        }


def _build_authorization_payload(
    owner_id: str, proposal: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Build payload used for owner authorization signatures."""
    return {
        "action": "execute_decision",
        "proposal": dict(proposal),
        "owner_id": owner_id,
    }


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


def main() -> None:
    """Render the Streamlit dashboard for owner oversight."""
    st.set_page_config(page_title="AI Business Owner Dashboard", layout="wide")

    settings = get_settings()
    _initialize_session_state()

    current_proposal = st.session_state["current_proposal"]
    vote_result_data = st.session_state["vote_result"]

    authorization_payload = _build_authorization_payload(
        owner_id=settings.owner_id or "unknown_owner",
        proposal=current_proposal,
    )

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

    if (
        settings.owner_auth_mode.upper() == "MOCK"
        and "owner_signature" not in st.session_state
    ):
        try:
            mock_signature = sign_action(
                owner_id=settings.owner_id or "unknown_owner",
                payload=authorization_payload,
            )
            st.session_state["owner_signature"] = mock_signature
            logger.info(
                "Mock signature auto-generated",
                extra={
                    "event": "dashboard_mock_signature_generated",
                    "owner_id": settings.owner_id,
                },
            )
        except ConstitutionalError as exc:
            st.error(f"Failed to generate mock signature: {exc}")

    st.title("Owner Oversight Console")

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

    proposal_card(current_proposal)
    vote_summary(vote_result_data)
    constitutional_compliance_indicator(
        is_compliant=validation.is_compliant, details=compliance_details
    )

    signature_placeholder = st.empty()
    signature_actions = st.container()

    with signature_actions:
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("Approve Proposal"):
                logger.info(
                    "Approve proposal clicked",
                    extra={"event": "dashboard_approve_clicked"},
                )
                _log_dashboard_event(
                    event_type="dashboard_approve_clicked",
                    data={"proposal_id": current_proposal.get("id")},
                )
                current_proposal["status"] = "approved"
                st.success("Proposal marked as approved.")

        with col2:
            if st.button("Reject Proposal"):
                logger.info(
                    "Reject proposal clicked",
                    extra={"event": "dashboard_reject_clicked"},
                )
                _log_dashboard_event(
                    event_type="dashboard_reject_clicked",
                    data={"proposal_id": current_proposal.get("id")},
                )
                current_proposal["status"] = "rejected"
                st.warning("Proposal marked as rejected.")

        with col3:
            if st.button("Generate Approval Signature"):
                logger.info(
                    "Generate approval signature clicked",
                    extra={"event": "dashboard_signature_button_clicked"},
                )
                _log_dashboard_event(
                    event_type="dashboard_signature_clicked",
                    data={"proposal_id": current_proposal.get("id")},
                )
                try:
                    signature = sign_action(
                        owner_id=settings.owner_id or "unknown_owner",
                        payload=authorization_payload,
                    )
                    st.session_state["owner_signature"] = signature
                    signature_placeholder.code(signature)
                    st.success("Signature generated. Copy and provide to orchestrator.")
                    logger.info(
                        "Owner signature generated",
                        extra={"event": "dashboard_signature_generated"},
                    )
                except ConstitutionalError as exc:
                    st.error(f"Failed to generate signature: {exc}")
                    logger.error(
                        "Signature generation failed",
                        extra={
                            "event": "dashboard_signature_failed",
                            "error": str(exc),
                        },
                    )

    if "owner_signature" in st.session_state:
        signature_placeholder.code(st.session_state["owner_signature"])

    if settings.owner_auth_mode.upper() == "MOCK":
        if st.button("Execute with Mock Signature"):
            logger.info(
                "Execute with mock signature clicked",
                extra={"event": "dashboard_mock_execute_clicked"},
            )
            _log_dashboard_event(
                event_type="dashboard_mock_execute_clicked",
                data={"proposal_id": current_proposal.get("id")},
            )
            st.info("Execution triggered with mock signature (simulation mode).")

    recent_logs = get_recent_logs(limit=50)
    execution_log_viewer(recent_logs)


if __name__ == "__main__":
    main()



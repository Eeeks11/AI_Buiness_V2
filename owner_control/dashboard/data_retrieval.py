"""
Governance Data Retrieval Module

Queries the immutable log system to retrieve real governance data:
- Proposals and their status
- Deliberation transcripts from all 8 roles
- Vote results from the 4 voting members
- Chair tie-breaker votes
- Legal and CISO vetoes
- Secretary documentation
- Constitutional compliance status
- Owner approval decisions
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.core import Proposal, ProposalStatus, RoleType

# Import logger utilities
sys.path.insert(0, str(PROJECT_ROOT))
from utilities.logger import get_recent_logs, export_logs

logger = logging.getLogger(__name__)


def get_all_proposals(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Retrieve all proposals from log events.
    
    Looks for:
    - governance_state_entry events with proposal_id
    - proposal_created events
    - Any event with proposal data
    
    Returns:
        List of proposal dictionaries sorted by creation time (newest first)
    """
    all_logs = get_recent_logs(limit=limit * 10)  # Get more logs to find all proposals
    proposals_map: Dict[str, Dict[str, Any]] = {}
    
    # Event types that contain proposal data
    proposal_event_types = [
        "governance_state_entry",
        "proposal_created",
        "governance_cycle_complete",
        "board_ideation_conducted",
        "board_deliberation_conducted",
        "board_vote_tallied",
    ]
    
    for log_entry in all_logs:
        event_type = log_entry.get("type", "")
        if event_type not in proposal_event_types:
            continue
            
        data = log_entry.get("data", {})
        proposal_id = data.get("proposal_id")
        
        if not proposal_id:
            continue
        
        # Initialize proposal if not seen before
        if proposal_id not in proposals_map:
            proposals_map[proposal_id] = {
                "id": proposal_id,
                "title": data.get("title", "Unknown Proposal"),
                "description": data.get("description", ""),
                "financial_impact": data.get("financial_impact", 0.0),
                "legal_risk": data.get("legal_risk", 0.0),
                "status": ProposalStatus.DRAFT.value,
                "created_at": log_entry.get("timestamp", ""),
                "updated_at": log_entry.get("timestamp", ""),
                "session_id": data.get("session_id"),
                "board_approved": False,
                "owner_authorized": False,
                "logged": True,
                "phase": None,
                "deliberation_responses": {},
                "vote_result": None,
                "veto_triggered": False,
                "veto_role": None,
                "chair_tiebreak": False,
                "constitutional_compliance": None,
            }
        
        proposal = proposals_map[proposal_id]
        
        # Update proposal data from various event types
        if event_type == "governance_state_entry":
            phase = data.get("phase", "")
            proposal["phase"] = phase
            # Map phase to status
            if phase == "IDEATION":
                proposal["status"] = ProposalStatus.DRAFT.value
            elif phase == "DELIBERATION":
                proposal["status"] = ProposalStatus.DELIBERATION.value
            elif phase == "VOTING":
                proposal["status"] = ProposalStatus.VOTING.value
            elif phase == "EXECUTION":
                proposal["status"] = ProposalStatus.APPROVED.value
        
        # Update from proposal data if present
        if "proposal" in data:
            proposal_data = data["proposal"]
            if isinstance(proposal_data, dict):
                proposal.update({
                    k: v for k, v in proposal_data.items()
                    if k in ["title", "description", "financial_impact", "legal_risk", "status"]
                    and v is not None
                })
        
        # Update timestamp
        if log_entry.get("timestamp"):
            proposal["updated_at"] = log_entry["timestamp"]
    
    # Sort by updated_at (newest first)
    proposals = sorted(
        proposals_map.values(),
        key=lambda p: p.get("updated_at", ""),
        reverse=True
    )
    
    return proposals[:limit]


def get_proposal_deliberations(proposal_id: str) -> Dict[str, Dict[str, Any]]:
    """
    Retrieve deliberation responses from all 8 board roles for a proposal.
    
    Returns:
        Dictionary mapping role names to their deliberation responses
    """
    all_logs = get_recent_logs(limit=1000)
    deliberations: Dict[str, Dict[str, Any]] = {}
    
    for log_entry in all_logs:
        event_type = log_entry.get("type", "")
        data = log_entry.get("data", {})
        
        if event_type == "board_deliberation_response_captured":
            if data.get("proposal_id") == proposal_id:
                role = data.get("role", "")
                if role:
                    deliberations[role] = {
                        "role": role,
                        "provider": data.get("provider", ""),
                        "response_length": data.get("response_length", 0),
                        "captured_at": data.get("captured_at", log_entry.get("timestamp", "")),
                    }
        
        elif event_type == "board_deliberation_conducted":
            if data.get("proposal_id") == proposal_id:
                # Check if there's a stored deliberation file
                responses = data.get("responses", {})
                if isinstance(responses, dict):
                    for role, response_data in responses.items():
                        if isinstance(response_data, dict):
                            deliberations[role] = {
                                "role": role,
                                "provider": response_data.get("provider", ""),
                                "response": response_data.get("response", ""),
                                "captured_at": response_data.get("captured_at", log_entry.get("timestamp", "")),
                            }
    
    # Also check for persisted deliberation files
    deliberation_file = PROJECT_ROOT / "data" / "proposals" / f"{proposal_id}_deliberation.json"
    if deliberation_file.exists():
        try:
            with open(deliberation_file, "r", encoding="utf-8") as f:
                deliberation_data = json.load(f)
                responses = deliberation_data.get("responses", {})
                if isinstance(responses, dict):
                    for role, response_data in responses.items():
                        if isinstance(response_data, dict):
                            deliberations[role] = {
                                "role": role,
                                "provider": response_data.get("provider", ""),
                                "response": response_data.get("response", ""),
                                "captured_at": response_data.get("captured_at", ""),
                            }
        except Exception as exc:
            logger.warning(f"Failed to read deliberation file: {exc}")
    
    return deliberations


def get_proposal_votes(proposal_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve vote results for a proposal.
    
    Returns:
        Dictionary with vote results including:
        - votes: mapping of member_id to weight
        - decision: approved/rejected
        - reason: decision reason
        - veto_triggered: boolean
        - veto_role: role that vetoed (if any)
        - chair_tiebreak_used: boolean
        - chair_vote: chair's tie-breaking vote (if used)
    """
    all_logs = get_recent_logs(limit=500)
    
    for log_entry in all_logs:
        event_type = log_entry.get("type", "")
        data = log_entry.get("data", {})
        
        if event_type == "board_vote_tallied":
            if data.get("proposal_id") == proposal_id:
                return {
                    "proposal_id": proposal_id,
                    "session_id": data.get("session_id", f"{proposal_id}-session"),
                    "votes": data.get("votes", {}),
                    "decision": data.get("decision", "unknown"),
                    "reason": data.get("reason", ""),
                    "approve_count": data.get("approve_count", 0),
                    "reject_count": data.get("reject_count", 0),
                    "approve_weight": data.get("approve_weight", 0.0),
                    "reject_weight": data.get("reject_weight", 0.0),
                    "veto_triggered": data.get("veto_triggered", False),
                    "veto_role": data.get("veto_role"),
                    "chair_tiebreak_used": data.get("chair_tiebreak_used", False),
                    "chair_vote": data.get("chair_vote"),
                    "timestamp": log_entry.get("timestamp", ""),
                }
    
    return None


def get_proposal_by_id(proposal_id: str) -> Optional[Dict[str, Any]]:
    """
    Get complete proposal data including deliberations and votes.
    
    Returns:
        Complete proposal dictionary with all associated data
    """
    proposals = get_all_proposals(limit=1000)
    
    for proposal in proposals:
        if proposal.get("id") == proposal_id:
            # Enrich with deliberations and votes
            proposal["deliberation_responses"] = get_proposal_deliberations(proposal_id)
            proposal["vote_result"] = get_proposal_votes(proposal_id)
            
            # Determine final status
            if proposal.get("vote_result"):
                vote_result = proposal["vote_result"]
                if vote_result.get("veto_triggered"):
                    proposal["status"] = ProposalStatus.VETOED.value
                elif vote_result.get("decision") == "approved":
                    proposal["status"] = ProposalStatus.APPROVED.value
                elif vote_result.get("decision") == "rejected":
                    proposal["status"] = ProposalStatus.REJECTED.value
            
            return proposal
    
    return None


def get_pending_owner_approvals() -> List[Dict[str, Any]]:
    """
    Get proposals that are approved by the board but awaiting owner approval.
    
    Returns:
        List of proposals awaiting owner authorization
    """
    all_proposals = get_all_proposals(limit=100)
    
    pending = []
    for proposal in all_proposals:
        status = proposal.get("status", "")
        vote_result = proposal.get("vote_result")
        
        # Check if board approved but owner hasn't authorized
        if (status == ProposalStatus.APPROVED.value or 
            (vote_result and vote_result.get("decision") == "approved")):
            if not proposal.get("owner_authorized", False):
                pending.append(proposal)
    
    return pending


def get_governance_events_for_proposal(proposal_id: str) -> List[Dict[str, Any]]:
    """
    Get all governance events related to a specific proposal.
    
    Returns:
        List of log entries related to the proposal, sorted chronologically
    """
    all_logs = get_recent_logs(limit=1000)
    
    proposal_events = []
    for log_entry in all_logs:
        data = log_entry.get("data", {})
        if data.get("proposal_id") == proposal_id:
            proposal_events.append(log_entry)
    
    # Sort by timestamp (oldest first for chronological order)
    proposal_events.sort(key=lambda e: e.get("timestamp", ""))
    
    return proposal_events


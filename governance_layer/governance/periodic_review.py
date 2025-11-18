"""
Periodic Review System

Implements Section 8.2: Periodic Review requirements from the business plan.
Conducts comprehensive quarterly reviews of business performance, agent performance,
system integrity, governance efficiency, and role relevance.
"""

from __future__ import annotations

import logging
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from constitutional_layer_immutable.constitution import validate_constitutional_compliance
from memory_systems.business_memory.memory.context_builder import build_agent_context
from models.core import ConstitutionalError
from owner_control.owner_gate.authorization import require_owner_approval
from telemetry.metrics import get_recent_metrics
from utilities.logger import get_recent_logs, log_event

logger = logging.getLogger(__name__)

PERIODIC_REVIEW_EVENT_TYPE = "periodic_review_completed"
PERIODIC_REVIEW_CHECK_EVENT = "periodic_review_schedule_checked"
QUARTERLY_DAYS = 90  # Fiscal quarter = 90 days


def _parse_timestamp(timestamp: str) -> datetime:
    """Parse ISO-formatted timestamps into timezone-aware datetime objects."""
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def _collect_recent_periodic_review_timestamp() -> Optional[datetime]:
    """Return the timestamp of the most recent periodic review or None."""
    logs = get_recent_logs(limit=500)
    for entry in logs:
        if entry.get("type") == PERIODIC_REVIEW_EVENT_TYPE:
            try:
                return _parse_timestamp(str(entry["timestamp"]))
            except (KeyError, ValueError):
                continue
    return None


def should_run_periodic_review() -> bool:
    """
    Check if quarterly review is due.
    
    Implements Section 8.2: Periodic Review must be conducted at least once every fiscal quarter.
    
    Returns:
        bool: True if a periodic review should be executed (90+ days since last review).
    """
    validate_constitutional_compliance()
    
    last_review = _collect_recent_periodic_review_timestamp()
    now = datetime.now(timezone.utc)
    
    if last_review is None:
        # No previous review, so one is due
        due = True
        days_since_last = None
    else:
        days_since_last = (now - last_review).days
        due = days_since_last >= QUARTERLY_DAYS
    
    log_event(
        PERIODIC_REVIEW_CHECK_EVENT,
        {
            "due": due,
            "days_since_last": days_since_last,
            "last_review": last_review.isoformat() if last_review else None,
        },
    )
    
    return due


def _analyze_financial_performance(days: int) -> Dict[str, Any]:
    """
    Analyze financial and operational performance.
    
    Implements Section 8.2: Financial and operational performance analysis.
    
    Args:
        days: Number of days to analyze.
    
    Returns:
        Dictionary containing financial performance metrics.
    """
    logger.info("Analyzing financial performance", extra={"days": days})
    
    events = _filter_events_within_period(days)
    
    # Extract financial metrics from events
    financial_events = [
        event for event in events
        if "financial" in str(event.get("type", "")).lower() or
           "proposal" in str(event.get("type", "")).lower()
    ]
    
    # Calculate financial impact from proposals
    total_financial_impact = 0.0
    proposal_count = 0
    
    for event in financial_events:
        data = event.get("data", {})
        if "financial_impact" in data:
            try:
                total_financial_impact += float(data["financial_impact"])
                proposal_count += 1
            except (ValueError, TypeError):
                continue
    
    avg_financial_impact = total_financial_impact / proposal_count if proposal_count > 0 else 0.0
    
    return {
        "total_financial_impact": total_financial_impact,
        "proposal_count": proposal_count,
        "average_financial_impact": avg_financial_impact,
        "period_days": days,
    }


def _analyze_agent_performance(days: int) -> Dict[str, Any]:
    """
    Assess agent performance and system integrity.
    
    Implements Section 8.2: Assessment of agent performance and system integrity.
    
    Args:
        days: Number of days to analyze.
    
    Returns:
        Dictionary containing agent performance metrics.
    """
    logger.info("Analyzing agent performance", extra={"days": days})
    
    events = _filter_events_within_period(days)
    metrics_summary = _summarize_metrics(days)
    
    # Count decisions by role
    role_decisions: Dict[str, int] = {}
    for event in events:
        role = event.get("data", {}).get("role")
        if role:
            role_decisions[role] = role_decisions.get(role, 0) + 1
    
    # Analyze decision outcomes
    successful_decisions = len([
        e for e in events
        if e.get("type") in {"execution_completed", "proposal_executed"}
    ])
    failed_decisions = len([
        e for e in events
        if e.get("type") in {"execution_failed", "proposal_rejected"}
    ])
    
    return {
        "role_decisions": role_decisions,
        "successful_decisions": successful_decisions,
        "failed_decisions": failed_decisions,
        "success_rate": (
            successful_decisions / (successful_decisions + failed_decisions)
            if (successful_decisions + failed_decisions) > 0 else 0.0
        ),
        "avg_decision_time_seconds": metrics_summary.get("avg_decision_time_seconds", 0.0),
        "vote_consensus_rate": metrics_summary.get("vote_consensus_rate", 0.0),
        "constitutional_compliance_rate": metrics_summary.get("constitutional_compliance_rate", 1.0),
    }


def _evaluate_governance_efficiency(days: int) -> Dict[str, Any]:
    """
    Evaluate governance efficiency and role relevance.
    
    Implements Section 8.2: Evaluation of governance efficiency and role relevance.
    
    Args:
        days: Number of days to analyze.
    
    Returns:
        Dictionary containing governance efficiency metrics.
    """
    logger.info("Evaluating governance efficiency", extra={"days": days})
    
    events = _filter_events_within_period(days)
    metrics_summary = _summarize_metrics(days)
    
    # Count governance cycle completions
    cycle_completions = len([
        e for e in events
        if e.get("type") == "governance_cycle_complete"
    ])
    
    # Calculate average time per phase (simplified)
    avg_decision_time = metrics_summary.get("avg_decision_time_seconds", 0.0)
    
    # Role participation analysis
    role_participation: Dict[str, int] = {}
    for event in events:
        role = event.get("data", {}).get("role")
        if role:
            role_participation[role] = role_participation.get(role, 0) + 1
    
    return {
        "cycle_completions": cycle_completions,
        "avg_decision_time_seconds": avg_decision_time,
        "role_participation": role_participation,
        "governance_efficiency_score": (
            1.0 - (avg_decision_time / 300.0)  # Normalize to 0-1 scale
            if avg_decision_time > 0 else 1.0
        ),
    }


def _identify_potential_amendments(review_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Identify potential amendments or structural optimizations.
    
    Implements Section 8.2: Identification of potential amendments or structural optimizations.
    
    Args:
        review_results: Results from comprehensive review.
    
    Returns:
        List of potential amendments/optimizations.
    """
    logger.info("Identifying potential amendments")
    
    amendments: List[Dict[str, Any]] = []
    
    # Check for performance issues
    agent_perf = review_results.get("agent_performance", {})
    if agent_perf.get("success_rate", 1.0) < 0.8:
        amendments.append({
            "type": "optimization",
            "category": "agent_performance",
            "description": "Agent success rate below 80%. Consider recalibrating decision-making processes.",
            "priority": "high",
        })
    
    # Check for efficiency issues
    gov_efficiency = review_results.get("governance_efficiency", {})
    if gov_efficiency.get("governance_efficiency_score", 1.0) < 0.7:
        amendments.append({
            "type": "optimization",
            "category": "governance_efficiency",
            "description": "Governance efficiency below 70%. Consider streamlining workflows.",
            "priority": "medium",
        })
    
    # Check for role relevance
    role_participation = gov_efficiency.get("role_participation", {})
    if len(role_participation) < 5:
        amendments.append({
            "type": "structural",
            "category": "role_relevance",
            "description": "Some roles may be underutilized. Review role assignments.",
            "priority": "low",
        })
    
    return amendments


def _filter_events_within_period(days: int) -> List[Dict[str, Any]]:
    """Return log events that fall within the review period."""
    period_end = datetime.now(timezone.utc)
    period_start = period_end - timedelta(days=days)
    
    events: List[Dict[str, Any]] = []
    logs = get_recent_logs(limit=5000)
    for entry in logs:
        timestamp_raw = entry.get("timestamp")
        if not isinstance(timestamp_raw, str):
            continue
        try:
            timestamp = _parse_timestamp(timestamp_raw)
        except ValueError:
            continue
        
        if period_start <= timestamp <= period_end:
            events.append(entry)
    
    events.sort(key=lambda entry: entry.get("timestamp", ""))
    return events


def _summarize_metrics(days: int) -> Dict[str, float]:
    """Build a metrics summary dictionary from telemetry measurements."""
    metrics_summary = {
        "avg_decision_time_seconds": 0.0,
        "vote_consensus_rate": 0.0,
        "constitutional_compliance_rate": 1.0,
    }
    
    grouped_metrics = get_recent_metrics(days=days)
    for group in grouped_metrics:
        name = group.get("name")
        aggregates = group.get("aggregates") or {}
        if not isinstance(name, str) or not aggregates:
            continue
        if name == "decision_time_seconds":
            metrics_summary["avg_decision_time_seconds"] = float(aggregates.get("avg", 0.0))
        elif name == "vote_consensus":
            metrics_summary["vote_consensus_rate"] = float(aggregates.get("avg", 0.0))
        elif name == "constitutional_compliance_check":
            metrics_summary["constitutional_compliance_rate"] = float(aggregates.get("avg", 1.0))
    return metrics_summary


@require_owner_approval("conduct_periodic_review")
def conduct_periodic_review(
    days: int = QUARTERLY_DAYS,
    *,
    owner_id: Optional[str] = None,
    owner_signature: Optional[str] = None,
    authorization_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run comprehensive quarterly review.
    
    Implements Section 8.2: Periodic Review requirements.
    Conducts comprehensive review of:
    - Financial and operational performance analysis
    - Assessment of agent performance and system integrity
    - Evaluation of governance efficiency and role relevance
    - Identification of potential amendments or structural optimizations
    
    Args:
        days: Number of days to review (default: 90 for quarterly).
        owner_id: Identifier of the approving owner (Rule 10).
        owner_signature: Signature authorizing the review (Rule 10).
        authorization_payload: Optional payload used to generate the owner signature.
    
    Returns:
        Structured review report with findings.
    
    Raises:
        ConstitutionalError: If invalid inputs are supplied or constitutional validation fails.
    """
    if days < 1:
        raise ConstitutionalError("Rule 1 Violation: Review window must be at least one day.")
    
    validate_constitutional_compliance()
    
    logger.info("Starting periodic review", extra={"days": days, "owner_id": owner_id})
    
    log_event(
        "periodic_review_started",
        {
            "window_days": days,
            "owner_id": owner_id,
            "authorization_payload_present": authorization_payload is not None,
        },
    )
    
    now = datetime.now(timezone.utc)
    period_end = now.isoformat()
    period_start = (now - timedelta(days=days)).isoformat()
    
    # Conduct comprehensive review
    financial_performance = _analyze_financial_performance(days)
    agent_performance = _analyze_agent_performance(days)
    governance_efficiency = _evaluate_governance_efficiency(days)
    
    # System integrity evaluation (simplified)
    system_integrity = {
        "constitutional_compliance_rate": agent_performance.get("constitutional_compliance_rate", 1.0),
        "system_health": "healthy" if agent_performance.get("constitutional_compliance_rate", 1.0) > 0.95 else "degraded",
    }
    
    # Compile review results
    review_results = {
        "financial_performance": financial_performance,
        "agent_performance": agent_performance,
        "governance_efficiency": governance_efficiency,
        "system_integrity": system_integrity,
    }
    
    # Identify potential amendments
    potential_amendments = _identify_potential_amendments(review_results)
    
    # Generate findings
    findings = generate_review_findings(review_results, potential_amendments)
    
    # Create review report
    review_id = f"review-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    
    report: Dict[str, Any] = {
        "review_id": review_id,
        "period_start": period_start,
        "period_end": period_end,
        "review_type": "quarterly",
        "review_results": review_results,
        "potential_amendments": potential_amendments,
        "findings": findings,
        "timestamp": now.isoformat(),
    }
    
    # Log review completion
    log_event(
        PERIODIC_REVIEW_EVENT_TYPE,
        {
            "review_id": review_id,
            "amendments_identified": len(potential_amendments),
            "owner_id": owner_id,
        },
    )
    
    logger.info("Periodic review completed", extra={"review_id": review_id})
    return report


def generate_review_findings(
    review_results: Dict[str, Any],
    potential_amendments: List[Dict[str, Any]]
) -> str:
    """
    Format findings for owner presentation.
    
    Implements Section 8.2: Findings are formally logged by the Secretary
    and presented to the Owner for consideration.
    
    Args:
        review_results: Results from comprehensive review.
        potential_amendments: List of identified amendments/optimizations.
    
    Returns:
        Formatted markdown report string.
    """
    logger.info("Generating review findings")
    
    financial = review_results.get("financial_performance", {})
    agent = review_results.get("agent_performance", {})
    governance = review_results.get("governance_efficiency", {})
    integrity = review_results.get("system_integrity", {})
    
    findings = f"""# Quarterly Periodic Review Findings

## Executive Summary

This report summarizes the comprehensive review conducted for the AI Business Governance System.

## Financial Performance

- **Total Financial Impact**: ${financial.get('total_financial_impact', 0.0):,.2f}
- **Proposals Reviewed**: {financial.get('proposal_count', 0)}
- **Average Financial Impact**: ${financial.get('average_financial_impact', 0.0):,.2f}

## Agent Performance

- **Success Rate**: {agent.get('success_rate', 0.0):.1%}
- **Successful Decisions**: {agent.get('successful_decisions', 0)}
- **Failed Decisions**: {agent.get('failed_decisions', 0)}
- **Average Decision Time**: {agent.get('avg_decision_time_seconds', 0.0):.2f} seconds
- **Vote Consensus Rate**: {agent.get('vote_consensus_rate', 0.0):.1%}
- **Constitutional Compliance Rate**: {agent.get('constitutional_compliance_rate', 1.0):.1%}

## Governance Efficiency

- **Governance Cycles Completed**: {governance.get('cycle_completions', 0)}
- **Efficiency Score**: {governance.get('governance_efficiency_score', 0.0):.1%}
- **Role Participation**: {len(governance.get('role_participation', {}))} roles active

## System Integrity

- **System Health**: {integrity.get('system_health', 'unknown')}
- **Constitutional Compliance**: {integrity.get('constitutional_compliance_rate', 1.0):.1%}

## Potential Amendments and Optimizations

"""
    
    if potential_amendments:
        for idx, amendment in enumerate(potential_amendments, 1):
            findings += f"""
### {idx}. {amendment.get('category', 'Unknown')} - {amendment.get('type', 'optimization').title()}

**Priority**: {amendment.get('priority', 'medium')}

**Description**: {amendment.get('description', 'No description provided')}
"""
    else:
        findings += "\nNo critical amendments or optimizations identified at this time.\n"
    
    findings += f"""

## Recommendations

Based on this review, the following actions are recommended:

1. **Continue Monitoring**: Maintain current governance configuration if all metrics are within acceptable ranges.
2. **Address Identified Issues**: Review and address any high-priority amendments identified above.
3. **Optimize Performance**: Consider implementing optimizations for medium-priority items.

---
*Report generated: {datetime.now(timezone.utc).isoformat()}*
"""
    
    return findings

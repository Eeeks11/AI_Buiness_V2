"""Governance retrospective workflow supporting constitutional self-review."""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from constitutional_layer_immutable.constitution import validate_constitutional_compliance
from memory_systems.business_memory.memory.context_builder import build_agent_context
from models.core import ConstitutionalError
from owner_control.owner_gate.authorization import require_owner_approval
from telemetry.metrics import get_recent_metrics
from utilities.logger import get_recent_logs, log_event

RETROSPECTIVE_EVENT_TYPE = "retrospective_completed"
RETROSPECTIVE_CHECK_EVENT = "retrospective_schedule_checked"


def _parse_timestamp(timestamp: str) -> datetime:
    """Parse ISO-formatted timestamps into timezone-aware datetime objects."""
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def _collect_recent_retrospective_timestamp() -> Optional[datetime]:
    """Return the timestamp of the most recent retrospective or None."""
    logs = get_recent_logs(limit=200)
    for entry in logs:
        if entry.get("type") == RETROSPECTIVE_EVENT_TYPE:
            try:
                return _parse_timestamp(str(entry["timestamp"]))
            except (KeyError, ValueError):
                continue
    return None


def should_run_retrospective() -> bool:
    """Determine whether the weekly retrospective is due.

    Returns:
        bool: True if a retrospective should be executed.
    """
    validate_constitutional_compliance()

    last_run = _collect_recent_retrospective_timestamp()
    now = datetime.now(timezone.utc)
    due = last_run is None or (now - last_run) >= timedelta(days=7)
    days_since_last = (now - last_run).days if last_run else None

    log_event(
        RETROSPECTIVE_CHECK_EVENT,
        {
            "due": due,
            "days_since_last": days_since_last,
        },
    )
    return due


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


def _analyze_outcomes(events: List[Dict[str, Any]]) -> Dict[str, int]:
    """Compute outcome counts from governance events."""
    counts = {"successful": 0, "failed": 0, "pending": 0}
    for event in events:
        event_type = event.get("type", "")
        if event_type in {"execution_completed", "proposal_executed"}:
            counts["successful"] += 1
        elif event_type in {"execution_failed", "proposal_rejected"}:
            counts["failed"] += 1
        elif event_type in {"execution_pending", "proposal_pending"}:
            counts["pending"] += 1
    return counts


def _generate_improvement_points(
    metrics_summary: Dict[str, float], outcomes: Dict[str, int]
) -> List[Dict[str, Any]]:
    """Derive retrospective improvement recommendations."""
    recommendations: List[Dict[str, Any]] = []

    if metrics_summary["avg_decision_time_seconds"] > 60:
        recommendations.append(
            {
                "category": "efficiency",
                "recommendation": "Reduce decision latency by optimizing deliberation prompts.",
                "priority": "high",
                "requires_owner_approval": False,
            }
        )

    if metrics_summary["vote_consensus_rate"] < 0.75:
        recommendations.append(
            {
                "category": "accuracy",
                "recommendation": "Recalibrate board member weighting to improve consensus.",
                "priority": "medium",
                "requires_owner_approval": True,
            }
        )

    if outcomes["failed"] > 0:
        recommendations.append(
            {
                "category": "accuracy",
                "recommendation": "Perform root cause analysis on failed executions.",
                "priority": "high",
                "requires_owner_approval": True,
            }
        )

    if not recommendations:
        recommendations.append(
            {
                "category": "efficiency",
                "recommendation": "Maintain current governance configuration; no critical issues detected.",
                "priority": "low",
                "requires_owner_approval": False,
            }
        )
    return recommendations


def _detect_anomalies(events: List[Dict[str, Any]], outcomes: Dict[str, int]) -> List[Dict[str, str]]:
    """Identify anomalous patterns in governance events."""
    anomalies: List[Dict[str, str]] = []

    if outcomes["failed"] > 0:
        anomalies.append(
            {
                "type": "execution_failure",
                "description": "Detected failed governance execution(s) requiring review.",
                "severity": "critical",
            }
        )

    pending_votes = [
        event
        for event in events
        if event.get("type") == "vote_cast" and event.get("data", {}).get("status") == "pending"
    ]
    if pending_votes:
        anomalies.append(
            {
                "type": "pending_vote",
                "description": f"{len(pending_votes)} vote(s) remain pending approval.",
                "severity": "warning",
            }
        )

    return anomalies


def _filter_events_within_period(days: int) -> List[Dict[str, Any]]:
    """Return log events that fall within the retrospective review window."""
    period_end = datetime.now(timezone.utc)
    period_start = period_end - timedelta(days=days)

    events: List[Dict[str, Any]] = []
    logs = get_recent_logs(limit=2000)
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


@require_owner_approval("conduct_weekly_retrospective")
def conduct_weekly_retrospective(
    days: int = 7,
    *,
    owner_id: Optional[str] = None,
    owner_signature: Optional[str] = None,
    authorization_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Conduct a weekly retrospective across recent governance activity.

    Args:
        days: Number of trailing days to include in the retrospective analysis.
        owner_id: Identifier of the approving owner (Rule 10).
        owner_signature: Signature authorizing the retrospective (Rule 10).
        authorization_payload: Optional payload used to generate the owner signature.

    Returns:
        Structured retrospective report describing review findings.

    Raises:
        ConstitutionalError: If invalid inputs are supplied or constitutional validation fails.
    """
    if days < 1:
        raise ConstitutionalError("Rule 1 Violation: Retrospective window must be at least one day.")

    validate_constitutional_compliance()
    log_event(
        "retrospective_started",
        {
            "window_days": days,
            "owner_id": owner_id,
            "authorization_payload_present": authorization_payload is not None,
        },
    )

    events = _filter_events_within_period(days)
    metrics_summary = _summarize_metrics(days)
    outcomes = _analyze_outcomes(events)
    anomalies = _detect_anomalies(events, outcomes)

    decision_ids = {
        str(event.get("data", {}).get("proposal_id"))
        for event in events
        if event.get("data", {}).get("proposal_id")
    }

    now = datetime.now(timezone.utc)
    period_end = now.isoformat()
    period_start = (now - timedelta(days=days)).isoformat()

    agent_context = build_agent_context(
        role="CHAIR",
        current_proposal={
            "id": "retrospective_review",
            "title": "Governance Retrospective",
            "description": "Weekly governance performance analysis",
            "financial_impact": 0.0,
            "legal_risk": 0.0,
        },
        topic_keywords=["retrospective", "governance", "compliance"],
    )

    report: Dict[str, Any] = {
        "retrospective_id": f"retro-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}",
        "period_start": period_start,
        "period_end": period_end,
        "summary": (
            f"Reviewed {len(events)} governance events across {len(decision_ids)} decision(s). "
            f"Prepared context for board review."
        ),
        "decisions_reviewed": len(decision_ids),
        "outcomes_analyzed": outcomes,
        "improvement_points": _generate_improvement_points(metrics_summary, outcomes),
        "metrics_summary": metrics_summary,
        "anomalies": anomalies,
        "timestamp": now.isoformat(),
    }

    log_event(
        RETROSPECTIVE_EVENT_TYPE,
        {
            "retrospective_id": report["retrospective_id"],
            "decisions_reviewed": len(decision_ids),
            "anomaly_count": len(anomalies),
            "owner_id": owner_id,
        },
    )
    return report


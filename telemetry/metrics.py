"""Telemetry metrics collection and aggregation utilities."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from constitutional_layer_immutable.constitution import (
    validate_constitutional_compliance,
)
from models.core import ConstitutionalError
from utilities.logger import log_event

METRICS_RELATIVE_PATH = Path("audit_compliance") / "logs" / "metrics.jsonl"


def _project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).resolve().parent.parent


def _resolve_metrics_path() -> Path:
    """Resolve the metrics log path and ensure the directory exists."""
    metrics_path = _project_root() / METRICS_RELATIVE_PATH
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    return metrics_path


def _load_metrics() -> List[Dict[str, Any]]:
    """Load all metrics entries from disk."""
    metrics_path = _resolve_metrics_path()
    if not metrics_path.exists():
        return []

    entries: List[Dict[str, Any]] = []
    with open(metrics_path, "r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ConstitutionalError(
                    f"Rule 6 Violation: Metrics log corrupted at line {line_number}: {exc}"
                ) from exc
            entries.append(entry)
    return entries


def _persist_metric(entry: Dict[str, Any]) -> None:
    """Persist a single metric entry to disk."""
    metrics_path = _resolve_metrics_path()
    with open(metrics_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _parse_timestamp(value: str) -> datetime:
    """Parse ISO formatted metric timestamps."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConstitutionalError(
            f"Rule 6 Violation: Invalid metric timestamp detected: {exc}"
        ) from exc


def log_metric(name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
    """Record a metric measurement and log the operation.

    Args:
        name: Name of the metric to record.
        value: Numeric value of the metric.
        tags: Optional tags providing additional classification context.

    Raises:
        ConstitutionalError: If constitutional compliance validation fails or persistence errors occur.
    """
    validate_constitutional_compliance()

    if not isinstance(name, str) or not name:
        raise ConstitutionalError("Rule 1 Violation: Metric name must be a non-empty string.")

    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as exc:
        raise ConstitutionalError(
            f"Rule 1 Violation: Metric value must be numeric: {exc}"
        ) from exc

    metric_entry: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "name": name,
        "value": numeric_value,
        "tags": tags or {},
    }

    _persist_metric(metric_entry)
    log_event(
        "metric_logged",
        {
            "name": name,
            "value": numeric_value,
            "tags": tags or {},
        },
    )


def get_recent_metrics(days: int = 7) -> List[Dict[str, Any]]:
    """Return metrics grouped by name within the requested time window.

    Args:
        days: Number of trailing days to include in the results.

    Returns:
        A list of dictionaries containing metric name, records, and aggregates.
    """
    validate_constitutional_compliance()

    if days < 1:
        raise ConstitutionalError("Rule 1 Violation: `days` must be >= 1.")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    grouped: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"name": "", "records": [], "aggregates": {"avg": 0.0, "min": 0.0, "max": 0.0, "count": 0}}
    )

    all_entries = _load_metrics()

    for entry in all_entries:
        timestamp_raw = entry.get("timestamp")
        name = entry.get("name")
        value = entry.get("value")

        if not isinstance(timestamp_raw, str) or not isinstance(name, str):
            continue

        timestamp = _parse_timestamp(timestamp_raw)
        if timestamp < cutoff:
            continue

        if not isinstance(value, (int, float)):
            continue

        container = grouped[name]
        container["name"] = name
        container["records"].append(entry)

    for container in grouped.values():
        values = [float(record["value"]) for record in container["records"]]
        if not values:
            continue
        container["aggregates"] = {
            "avg": mean(values),
            "min": min(values),
            "max": max(values),
            "count": len(values),
        }

    result = list(grouped.values())
    log_event(
        "metrics_queried",
        {
            "window_days": days,
            "metric_groups": len(result),
        },
    )
    return result


def get_metric_aggregates(metric_name: str, days: int = 7) -> Dict[str, float]:
    """Return aggregated statistics for a specific metric.

    Args:
        metric_name: Target metric name.
        days: Number of trailing days to include in the calculation.

    Returns:
        Dictionary containing aggregate statistics (`avg`, `min`, `max`, `count`).

    Raises:
        ConstitutionalError: If inputs are invalid or no data exists for the metric in the timeframe.
    """
    validate_constitutional_compliance()

    if not metric_name:
        raise ConstitutionalError("Rule 1 Violation: `metric_name` must be provided.")

    grouped_metrics = get_recent_metrics(days=days)
    for container in grouped_metrics:
        if container["name"] == metric_name:
            aggregates = container.get("aggregates", {})
            if not aggregates or not container.get("records"):
                break
            log_event(
                "metric_aggregates_calculated",
                {
                    "metric_name": metric_name,
                    "window_days": days,
                    "count": aggregates.get("count", 0),
                },
            )
            return {
                "avg": float(aggregates.get("avg", 0.0)),
                "min": float(aggregates.get("min", 0.0)),
                "max": float(aggregates.get("max", 0.0)),
                "count": float(aggregates.get("count", 0)),
            }

    raise ConstitutionalError(
        f"Rule 6 Violation: No metrics found for '{metric_name}' within {days} day(s)."
    )


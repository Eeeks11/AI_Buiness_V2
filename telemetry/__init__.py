"""Telemetry package exposing metrics collection utilities."""

from __future__ import annotations

from telemetry.metrics import get_metric_aggregates, get_recent_metrics, log_metric

__all__ = [
    "get_metric_aggregates",
    "get_recent_metrics",
    "log_metric",
]


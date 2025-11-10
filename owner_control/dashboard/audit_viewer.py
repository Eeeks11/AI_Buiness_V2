"""Streamlit audit viewer for immutable logging transparency."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import streamlit as st

# Ensure project packages resolve when launched via `streamlit run`
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.core import ConstitutionalError
from utilities.logger import (
    export_batch_index,
    export_logs,
    log_event,
    validate_log_chain,
)

try:
    import pandas as pd  # type: ignore
except ImportError:  # pragma: no cover - fallback when pandas unavailable
    pd = None


def _parse_timestamp(value: str) -> Optional[datetime]:
    """Parse ISO-formatted timestamps safely."""
    if not value:
        return None
    cleaned = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _filter_logs(
    logs: Iterable[Dict[str, Any]],
    selected_event: str,
    start_date: Optional[date],
    end_date: Optional[date],
    query: str,
    pinned_only: bool,
    pinned_hashes: Set[str],
) -> List[Dict[str, Any]]:
    """Apply event, date, text, and pinned filters to log entries."""
    query_lower = query.strip().lower()
    filtered: List[Dict[str, Any]] = []

    for entry in logs:
        if selected_event and selected_event != "All" and entry.get("type") != selected_event:
            continue

        timestamp = _parse_timestamp(entry.get("timestamp", ""))
        if start_date and (timestamp is None or timestamp.date() < start_date):
            continue
        if end_date and (timestamp is None or timestamp.date() > end_date):
            continue

        if pinned_only and entry.get("chain_hash") not in pinned_hashes:
            continue

        if query_lower:
            serialized = json.dumps(entry, ensure_ascii=False)
            if query_lower not in serialized.lower():
                continue

        filtered.append(entry)

    filtered.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return filtered


def _collect_pinned_hashes(batch_index: Dict[str, Any]) -> Set[str]:
    """Collect chain hashes from pinned batch manifests."""
    pinned: Set[str] = set()
    for batch in batch_index.get("batches", []):
        for manifest_entry in batch.get("manifest_entries", []) or []:
            chain_hash = manifest_entry.get("chain_hash")
            if chain_hash:
                pinned.add(chain_hash)
    return pinned


def _log_dashboard_event(event_type: str, data: Dict[str, Any]) -> None:
    """Safely persist dashboard audit interactions."""
    try:
        log_event(
            event_type=event_type,
            data=data,
            metadata={"source": "audit_dashboard"},
        )
    except ConstitutionalError as exc:
        st.warning(f"Failed to persist audit log event: {exc}")
    except Exception:
        st.warning("Failed to persist audit log event.")


def main() -> None:
    """Render the immutable audit log viewer."""
    st.set_page_config(page_title="Immutable Audit Log")
    _log_dashboard_event("dashboard_audit_accessed", {})

    st.title("Immutable Audit Log")
    st.caption("Review, validate, and export immutable log data for Rule 6 compliance.")

    logs = export_logs()
    batch_index = export_batch_index()
    pinned_hashes = _collect_pinned_hashes(batch_index)

    event_options = sorted({entry.get("type", "") for entry in logs if entry.get("type")})
    event_options.insert(0, "All")

    with st.sidebar:
        st.header("Filter Controls")
        with st.form("audit_filters"):
            selected_event = st.selectbox("Event Type", options=event_options)
            date_range = st.date_input(
                "Date Range",
                value=(),
                min_value=None,
                max_value=None,
                help="Select a start and end date to filter log timestamps.",
            )
            text_query = st.text_input("Search Text", value="")
            pinned_only = st.checkbox("Show only pinned batches", value=False)
            submitted = st.form_submit_button("Apply Filters")

        start_date: Optional[date] = None
        end_date: Optional[date] = None
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
        elif isinstance(date_range, date):
            start_date = date_range
            end_date = date_range

        if submitted:
            _log_dashboard_event(
                "dashboard_audit_filtered",
                {
                    "event_type": selected_event,
                    "start_date": str(start_date) if start_date else None,
                    "end_date": str(end_date) if end_date else None,
                    "query": text_query,
                    "pinned_only": pinned_only,
                },
            )
    filtered_logs = _filter_logs(
        logs=logs,
        selected_event=selected_event if submitted else "All",
        start_date=start_date,
        end_date=end_date,
        query=text_query if submitted else "",
        pinned_only=pinned_only if submitted else False,
        pinned_hashes=pinned_hashes,
    )

    st.subheader("Latest Logs")
    if filtered_logs:
        display_rows = [
            {
                "timestamp": entry.get("timestamp"),
                "event_type": entry.get("type"),
                "chain_hash": entry.get("chain_hash"),
                "last_pin_tx_id": entry.get("last_pin_tx_id"),
            }
            for entry in filtered_logs
        ]
        if pd is not None:
            st.dataframe(pd.DataFrame(display_rows))
        else:
            st.table(display_rows)
    else:
        st.info("No log entries match the selected filters.")

    st.subheader("Manifest Batch Pins")
    if batch_index.get("batches"):
        for batch in batch_index["batches"]:
            st.markdown(
                f"- **Batch ID:** {batch.get('batch_id')}  "
                f"- **Tx ID:** `{batch.get('tx_id')}`  "
                f"- **Entries:** {batch.get('entry_count')}"
            )
    else:
        st.info("No immutable batch pins have been created yet.")

    st.subheader("Actions")
    if st.button("Validate Chain Integrity"):
        _log_dashboard_event("dashboard_audit_validate_clicked", {})
        try:
            valid = validate_log_chain()
            if valid:
                st.success(f"✅ Chain valid. Entries: {len(logs)}")
            else:  # pragma: no cover - safeguard for unexpected false
                st.error("❌ Chain validation reported issues.")
        except ConstitutionalError as exc:
            st.error(f"❌ Chain validation failed: {exc}")

    logs_json = json.dumps(logs, indent=2, ensure_ascii=False)
    if st.download_button(
        "Export Logs (JSON)",
        data=logs_json.encode("utf-8"),
        file_name="immutable_logs.json",
        mime="application/json",
    ):
        _log_dashboard_event(
            "dashboard_audit_exported",
            {"resource": "logs", "entry_count": len(logs)},
        )

    batch_json = json.dumps(batch_index, indent=2, ensure_ascii=False)
    if st.download_button(
        "Export Batch Index (JSON)",
        data=batch_json.encode("utf-8"),
        file_name="immutable_batch_index.json",
        mime="application/json",
    ):
        _log_dashboard_event(
            "dashboard_audit_exported",
            {"resource": "batch_index", "batch_count": len(batch_index.get("batches", []))},
        )


if __name__ == "__main__":
    main()



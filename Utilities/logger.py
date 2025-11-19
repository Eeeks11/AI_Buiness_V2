from __future__ import annotations

"""Immutable logging utilities with tamper-evident chaining and Arweave batching."""

import json
import logging
from collections import deque
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

from config_settings.config import get_settings
from memory_systems.codebase_memory.immutable_storage.arweave_adapter import (
    compute_batch_hash,
    store_log_batch,
)
from models.core import ConstitutionalError

logger = logging.getLogger(__name__)

GENESIS_HASH = "GENESIS"
INDEX_FILENAME_SUFFIX = "_batch_index.json"

_log_file_path: Optional[Path] = None
_index_file_path: Optional[Path] = None
_last_chain_hash: Optional[str] = None
_entries_since_last_pin: int = 0
_pending_pin_tx_ids: Deque[str] = deque()


def _project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).resolve().parent.parent


def _stable_json_bytes(value: Any) -> bytes:
    """Serialize value to stable JSON bytes for hashing."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _compute_hash_from_dict(value: Dict[str, Any]) -> str:
    """Compute SHA-256 hash from a dictionary using stable JSON encoding."""
    return sha256(_stable_json_bytes(value)).hexdigest()


def _resolve_log_file_path() -> Path:
    """Resolve the log file path from configuration, ensuring parent directory exists."""
    global _log_file_path

    if _log_file_path is not None:
        return _log_file_path

    settings = get_settings()
    configured_path = Path(settings.log_file_path)
    if not configured_path.is_absolute():
        configured_path = _project_root() / configured_path

    configured_path.parent.mkdir(parents=True, exist_ok=True)
    _log_file_path = configured_path
    return _log_file_path


def _get_log_file_path() -> Path:
    """Expose log file path for compatibility with legacy tests."""
    return _resolve_log_file_path()


def _resolve_index_file_path() -> Path:
    """Resolve the batch index file path stored alongside the log file."""
    global _index_file_path

    if _index_file_path is not None:
        return _index_file_path

    log_path = _get_log_file_path()
    index_name = f"{log_path.stem}{INDEX_FILENAME_SUFFIX}"
    _index_file_path = log_path.with_name(index_name)
    return _index_file_path


def _read_log_file() -> List[Dict[str, Any]]:
    """Read all log entries from the JSONL log file."""
    log_path = _get_log_file_path()
    if not log_path.exists():
        return []

    entries: List[Dict[str, Any]] = []
    with open(log_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.error("Malformed log entry detected", exc_info=True)
                raise ConstitutionalError(
                    f"Rule 6 Violation: Detected malformed log entry: {exc}"
                ) from exc
    return entries


def _load_batch_index() -> Dict[str, Any]:
    """Load the batch index file or return a default structure."""
    index_path = _resolve_index_file_path()
    if not index_path.exists():
        return {"batches": [], "total_entries_pinned": 0}

    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        logger.error("Malformed batch index file", exc_info=True)
        raise ConstitutionalError(
            f"Immutable index corruption detected: {exc}"
        ) from exc


def _write_batch_index(index_data: Dict[str, Any]) -> None:
    """Persist batch index details to disk."""
    index_path = _resolve_index_file_path()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump(index_data, handle, indent=2, ensure_ascii=False)


def _initialize_state() -> None:
    """Initialize cached state for chain continuity and batching."""
    global _last_chain_hash, _entries_since_last_pin

    entries = _read_log_file()
    entries = _migrate_legacy_entries(entries)
    if entries:
        last_entry = entries[-1]
        _last_chain_hash = last_entry.get("chain_hash", GENESIS_HASH)
    else:
        _last_chain_hash = None

    index_data = _load_batch_index()
    total_entries_pinned = int(index_data.get("total_entries_pinned", 0))
    _entries_since_last_pin = max(len(entries) - total_entries_pinned, 0)


def _repair_chain_hashes(entries: List[Dict[str, Any]], start_prev_hash: str = GENESIS_HASH) -> List[Dict[str, Any]]:
    """
    Repair chain hashes for entries where content is valid but chain hashes are incorrect.
    
    This can happen if the log was partially written or if there was a migration issue.
    Only repairs if content hashes are valid - if content hashes don't match, that's
    actual tampering and we don't repair it.
    
    Args:
        entries: List of log entries to repair
        start_prev_hash: The previous chain hash to use for the first entry (defaults to GENESIS_HASH)
    """
    if not entries:
        return entries
    
    repaired_entries: List[Dict[str, Any]] = []
    previous_chain_hash = start_prev_hash
    
    for entry in entries:
        payload = {
            "timestamp": entry.get("timestamp"),
            "type": entry.get("type"),
            "data": entry.get("data"),
            "metadata": entry.get("metadata") or {},
        }
        expected_content_hash = _compute_hash_from_dict(payload)
        stored_content_hash = entry.get("content_hash")
        
        # Only repair if content hash is valid (content hasn't been tampered with)
        if stored_content_hash and stored_content_hash == expected_content_hash:
            # Recalculate chain hash with correct previous hash
            chain_hash = sha256(f"{previous_chain_hash}:{expected_content_hash}".encode("utf-8")).hexdigest()
            
            entry["prev_hash"] = previous_chain_hash
            entry["chain_hash"] = chain_hash
            previous_chain_hash = chain_hash
        else:
            # Content hash mismatch - this is actual tampering, don't repair
            raise ConstitutionalError(
                f"Rule 6 Violation: Cannot repair chain - content hash mismatch detected. "
                f"This indicates possible tampering."
            )
        
        repaired_entries.append(entry)
    
    return repaired_entries


def _migrate_legacy_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Upgrade legacy log entries lacking immutable chain fields."""
    if not entries:
        return entries

    needs_migration = any(
        "content_hash" not in entry or "chain_hash" not in entry or "prev_hash" not in entry
        for entry in entries
    )
    if not needs_migration:
        return entries

    logger.info(
        "Detected legacy log entries without immutable chain metadata. Migrating in-place.",
        extra={"entry_count": len(entries)},
    )

    migrated_entries: List[Dict[str, Any]] = []
    previous_chain_hash = GENESIS_HASH

    for entry in entries:
        payload = {
            "timestamp": entry.get("timestamp"),
            "type": entry.get("type"),
            "data": entry.get("data"),
            "metadata": entry.get("metadata") or {},
        }
        content_hash = _compute_hash_from_dict(payload)
        chain_hash = sha256(f"{previous_chain_hash}:{content_hash}".encode("utf-8")).hexdigest()

        entry["metadata"] = payload["metadata"]
        entry["content_hash"] = content_hash
        entry["prev_hash"] = previous_chain_hash
        entry["chain_hash"] = chain_hash

        migrated_entries.append(entry)
        previous_chain_hash = chain_hash

    log_path = _get_log_file_path()
    with open(log_path, "w", encoding="utf-8") as handle:
        for entry in migrated_entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    logger.info(
        "Legacy log migration completed.",
        extra={
            "updated_entries": len(migrated_entries),
            "last_chain_hash": previous_chain_hash,
        },
    )
    return migrated_entries


def _pop_pending_pin_tx_id() -> Optional[str]:
    """Return the next pending pin transaction ID, if any."""
    if _pending_pin_tx_ids:
        return _pending_pin_tx_ids.popleft()
    return None


def _append_pending_pin_tx_id(tx_id: str) -> None:
    """Record a transaction ID to include on the next log event."""
    _pending_pin_tx_ids.append(tx_id)


def _build_chain_fields(
    event_payload: Dict[str, Any],
) -> Tuple[str, str, str]:
    """
    Compute content and chain hashes for the provided event payload.

    Args:
        event_payload: Event payload excluding hash metadata.

    Returns:
        Tuple of (content_hash, prev_hash, chain_hash).
    """
    global _last_chain_hash

    content_hash = _compute_hash_from_dict(event_payload)
    prev_hash = _last_chain_hash or GENESIS_HASH
    chain_hash = sha256(f"{prev_hash}:{content_hash}".encode("utf-8")).hexdigest()
    return content_hash, prev_hash, chain_hash


def _build_manifest_entries(
    entries: List[Dict[str, Any]]
) -> List[Dict[str, str]]:
    """Construct manifest entry summaries from full log entries."""
    manifest_entries: List[Dict[str, str]] = []
    for entry in entries:
        manifest_entries.append(
            {
                "timestamp": entry.get("timestamp", ""),
                "event_type": entry.get("type", ""),
                "chain_hash": entry.get("chain_hash", ""),
            }
        )
    return manifest_entries


def _pin_pending_batches(batch_size: int) -> None:
    """Attempt to pin batches while enough entries are pending."""
    global _entries_since_last_pin

    if batch_size < 1:
        raise ConstitutionalError("Immutable batch size must be at least 1.")

    if _entries_since_last_pin < batch_size:
        return

    entries = _read_log_file()
    index_data = _load_batch_index()
    total_entries_pinned = int(index_data.get("total_entries_pinned", 0))

    while _entries_since_last_pin >= batch_size:
        start_index = total_entries_pinned
        end_index = start_index + batch_size

        # Safe bounds checking: ensure end_index doesn't exceed array length
        if end_index > len(entries):
            # Adjust end_index to available entries
            end_index = len(entries)
            if start_index >= end_index:
                # No more entries to process
                logger.debug(
                    "No more entries to batch",
                    extra={
                        "batch_size": batch_size,
                        "entries_available": len(entries),
                        "start_index": start_index,
                        "end_index": end_index,
                    },
                )
                break

        # Safe slicing with bounds-checked end_index
        batch_entries = entries[start_index:end_index]
        
        # If batch is empty, break
        if not batch_entries:
            break
        manifest_entries = _build_manifest_entries(batch_entries)

        manifest = {
            "batch_id": f"{datetime.now(timezone.utc).isoformat()}_{end_index}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "entries": manifest_entries,
            "batch_hash": compute_batch_hash(manifest_entries),
        }

        logger.info(
            "immutable_batch_store_attempt",
            extra={
                "batch_id": manifest["batch_id"],
                "entry_count": len(manifest_entries),
            },
        )

        try:
            tx_id = store_log_batch(manifest)
        except ConstitutionalError:
            logger.exception(
                "Immutable batch storage failed due to constitutional violation",
                extra={"batch_id": manifest["batch_id"]},
            )
            raise
        except Exception as exc:
            logger.exception(
                "Unexpected failure storing immutable batch",
                extra={"batch_id": manifest["batch_id"]},
            )
            raise ConstitutionalError(
                f"Rule 6 Violation: Failed to persist immutable batch: {exc}"
            ) from exc

        logger.info(
            "immutable_batch_store_result",
            extra={
                "batch_id": manifest["batch_id"],
                "tx_id": tx_id,
                "entry_count": len(manifest_entries),
            },
        )

        batch_record = {
            "batch_id": manifest["batch_id"],
            "tx_id": tx_id,
            "created_at": manifest["created_at"],
            "entry_count": len(manifest_entries),
            "last_chain_hash": batch_entries[-1].get("chain_hash"),
            "batch_hash": manifest["batch_hash"],
            "start_index": start_index,
            "end_index": end_index,
            "manifest_entries": manifest_entries,
        }
        index_data.setdefault("batches", []).append(batch_record)
        total_entries_pinned = end_index
        index_data["total_entries_pinned"] = total_entries_pinned
        _entries_since_last_pin -= batch_size

        _write_batch_index(index_data)
        _append_pending_pin_tx_id(tx_id)

        logger.info(
            "immutable_batch_triggered",
            extra={
                "batch_id": manifest["batch_id"],
                "tx_id": tx_id,
                "total_entries_pinned": total_entries_pinned,
            },
        )


def log_event(
    event_type: str,
    data: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Log an event with tamper-evident chaining and optional immutable batching.

    Args:
        event_type: Identifier describing the event.
        data: Structured event payload.
        metadata: Optional metadata for additional context.

    Returns:
        Dictionary representing the persisted event.
    """
    global _last_chain_hash, _entries_since_last_pin

    log_path = _get_log_file_path()
    needs_state_refresh = _last_chain_hash is None or not log_path.exists()
    if not needs_state_refresh:
        try:
            needs_state_refresh = log_path.stat().st_size == 0
        except FileNotFoundError:
            needs_state_refresh = True
    if needs_state_refresh:
        _initialize_state()
    metadata = metadata or {}

    pending_tx_id = _pop_pending_pin_tx_id()

    event_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "data": data,
        "metadata": metadata,
    }

    content_hash, prev_hash, chain_hash = _build_chain_fields(event_payload)
    event_record = dict(event_payload)
    event_record.update(
        {
            "content_hash": content_hash,
            "prev_hash": prev_hash,
            "chain_hash": chain_hash,
        }
    )

    if pending_tx_id:
        event_record["last_pin_tx_id"] = pending_tx_id

    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event_record, ensure_ascii=False) + "\n")

    _last_chain_hash = chain_hash
    _entries_since_last_pin += 1

    settings = get_settings()
    if settings.immutable_logging_enabled:
        try:
            _pin_pending_batches(settings.immutable_batch_size)
        except ConstitutionalError:
            raise
        except Exception as exc:
            logger.exception("Immutable batching failed", exc_info=True)
            raise ConstitutionalError(
                f"Rule 6 Violation: Immutable batching failed: {exc}"
            ) from exc

    return event_record


def get_recent_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """Return the most recent log entries, newest first."""
    entries = _read_log_file()
    if not entries:
        return []
    entries.reverse()
    return entries[:limit]


def export_logs() -> List[Dict[str, Any]]:
    """Return all log entries in chronological order."""
    return _read_log_file()


def export_batch_index() -> Dict[str, Any]:
    """Return the current batch index structure."""
    return _load_batch_index()


def validate_log_chain() -> bool:
    """
    Validate integrity of the immutable audit log chain.

    Verifies:
        - All log entries are present and contain valid JSON
        - Entries are ordered chronologically by timestamp
        - Chain integrity is maintained without tampering

    Returns:
        bool: True if the log chain is valid.

    Raises:
        ConstitutionalError: If the audit log is missing or corruption is detected.
    """
    global _last_chain_hash
    
    log_path = _get_log_file_path()
    if not log_path.exists():
        logger.warning(
            "Audit log missing; initializing new immutable log chain.",
            extra={"log_path": str(log_path)},
        )
        reset_log_chain(preserve_backup=False)
        _last_chain_hash = None
        return True

    # Read entries and migrate if needed (migration modifies the file in-place)
    entries = _read_log_file()
    entries = _migrate_legacy_entries(entries)

    if not entries:
        # Empty log is valid
        # Update state to reflect empty log
        _last_chain_hash = None
        return True

    previous_chain_hash = GENESIS_HASH

    for index, entry in enumerate(entries):
        try:
            timestamp = datetime.fromisoformat(
                str(entry["timestamp"]).replace("Z", "+00:00")
            )
        except (KeyError, ValueError) as exc:
            raise ConstitutionalError(
                f"Rule 6 Violation: Invalid timestamp at log index {index + 1}: {exc}"
            ) from exc

        if index > 0:
            previous_timestamp = datetime.fromisoformat(
                str(entries[index - 1]["timestamp"]).replace("Z", "+00:00")
            )
            if timestamp < previous_timestamp:
                raise ConstitutionalError(
                    f"Rule 6 Violation: Log entries not chronological (line {index + 1})"
                )

        expected_payload = {
            "timestamp": entry.get("timestamp"),
            "type": entry.get("type"),
            "data": entry.get("data"),
            "metadata": entry.get("metadata"),
        }
        expected_content_hash = _compute_hash_from_dict(expected_payload)
        stored_content_hash = entry.get("content_hash")
        stored_prev_hash = entry.get("prev_hash")
        stored_chain_hash = entry.get("chain_hash")

        # Check if entry has required hash fields
        if not stored_content_hash or not stored_prev_hash or not stored_chain_hash:
            raise ConstitutionalError(
                f"Rule 6 Violation: Log entry at index {index + 1} missing required hash fields. "
                f"This may indicate a migration issue."
            )

        if stored_content_hash != expected_content_hash:
            raise ConstitutionalError(
                f"Rule 6 Violation: Immutable log tampering detected (content hash mismatch at index {index + 1}). "
                f"Expected: {expected_content_hash}, Got: {stored_content_hash}"
            )

        computed_chain_hash = sha256(
            f"{previous_chain_hash}:{expected_content_hash}".encode("utf-8")
        ).hexdigest()

        if index == 0:
            if stored_prev_hash not in (None, "", GENESIS_HASH):
                if stored_content_hash == expected_content_hash:
                    logger.warning(
                        "Invalid genesis previous hash detected. Repairing log chain from genesis.",
                        extra={
                            "index": index + 1,
                            "stored_prev_hash": stored_prev_hash,
                        },
                    )
                    repaired_entries = _repair_chain_hashes(
                        entries, start_prev_hash=GENESIS_HASH
                    )
                    log_path = _get_log_file_path()
                    with open(log_path, "w", encoding="utf-8") as handle:
                        for repaired_entry in repaired_entries:
                            handle.write(json.dumps(repaired_entry, ensure_ascii=False) + "\n")
                    logger.info(
                        "Genesis hash repaired successfully.",
                        extra={"total_entries": len(repaired_entries)},
                    )
                    return validate_log_chain()
                raise ConstitutionalError(
                    f"Rule 6 Violation: Immutable log tampering detected (invalid genesis previous hash at index {index + 1}). "
                    f"Expected: {GENESIS_HASH} or empty, Got: {stored_prev_hash}"
                )
        else:
            if stored_prev_hash != previous_chain_hash:
                # Check if content is valid - if so, we can repair the chain
                if stored_content_hash == expected_content_hash:
                    # Content is valid, but chain hash is wrong - repair it
                    logger.warning(
                        "Chain hash mismatch detected but content is valid. Repairing chain.",
                        extra={
                            "index": index + 1,
                            "expected_prev_hash": previous_chain_hash,
                            "got_prev_hash": stored_prev_hash,
                            "entry_type": entry.get("type"),
                        }
                    )
                    # Get the previous chain hash from the entry before the mismatch
                    if index > 0:
                        repair_start_hash = entries[index - 1].get("chain_hash", GENESIS_HASH)
                    else:
                        repair_start_hash = GENESIS_HASH
                    
                    # Repair all entries from this point forward
                    repaired_tail = _repair_chain_hashes(entries[index:], start_prev_hash=repair_start_hash)
                    entries = entries[:index] + repaired_tail
                    
                    # Rewrite the log file with repaired entries
                    log_path = _get_log_file_path()
                    with open(log_path, "w", encoding="utf-8") as handle:
                        for repaired_entry in entries:
                            handle.write(json.dumps(repaired_entry, ensure_ascii=False) + "\n")
                    
                    logger.info(
                        "Log chain repaired successfully.",
                        extra={"repaired_from_index": index + 1, "total_entries": len(entries)}
                    )
                    
                    # Re-read entries and re-validate
                    entries = _read_log_file()
                    previous_chain_hash = GENESIS_HASH
                    # Continue validation from the beginning with repaired entries
                    continue
                else:
                    # Content hash mismatch - this is actual tampering
                    raise ConstitutionalError(
                        f"Rule 6 Violation: Immutable log tampering detected (previous hash mismatch at index {index + 1}). "
                        f"Expected: {previous_chain_hash}, Got: {stored_prev_hash}. "
                        f"Content hash also invalid - possible tampering."
                    )

        if stored_chain_hash != computed_chain_hash:
            raise ConstitutionalError(
                f"Rule 6 Violation: Immutable log tampering detected (chain hash mismatch at index {index + 1}). "
                f"Expected: {computed_chain_hash}, Got: {stored_chain_hash}"
            )

        previous_chain_hash = stored_chain_hash

    # Update global state to match validated chain before logging validation event
    _last_chain_hash = previous_chain_hash
    
    # Log validation result - this will use the correctly synced _last_chain_hash
    log_event(
        "log_chain_validated",
        {
            "entries": len(entries),
            "status": "valid",
        },
    )
    return True


def reset_log_chain(preserve_backup: bool = True) -> Dict[str, Optional[Path]]:
    """
    Reset the immutable audit log and associated batch index.

    Args:
        preserve_backup: When True, keep timestamped backups of existing files.

    Returns:
        Dictionary describing backup file paths that were created.
    """
    global _last_chain_hash, _entries_since_last_pin

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = _get_log_file_path()
    index_path = _resolve_index_file_path()

    log_backup: Optional[Path] = None
    index_backup: Optional[Path] = None

    if log_path.exists():
        if preserve_backup:
            log_backup = log_path.with_name(f"{log_path.stem}_backup_{timestamp}.jsonl")
            log_path.replace(log_backup)
        else:
            log_path.unlink()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")

    if index_path.exists():
        if preserve_backup:
            extension = index_path.suffix or ".json"
            index_backup = index_path.with_name(
                f"{index_path.stem}_backup_{timestamp}{extension}"
            )
            index_path.replace(index_backup)
        else:
            index_path.unlink()

    _write_batch_index({"batches": [], "total_entries_pinned": 0})

    _last_chain_hash = None
    _entries_since_last_pin = 0
    _pending_pin_tx_ids.clear()

    logger.info(
        "Immutable log chain reset",
        extra={
            "log_backup": str(log_backup) if log_backup else None,
            "index_backup": str(index_backup) if index_backup else None,
        },
    )

    return {"log_backup": log_backup, "index_backup": index_backup}



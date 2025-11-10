"""
Arweave adapter for immutable logging.

Provides MOCK (default) storage that returns deterministic transaction IDs
without performing network requests. LIVE mode is not yet implemented and will
raise a ConstitutionalError when selected.
"""

from __future__ import annotations

import json
import logging
from hashlib import sha256
from typing import Any, Dict, List

from config_settings.config import get_settings
from models.core import ConstitutionalError

logger = logging.getLogger(__name__)

MOCK_MODE = "MOCK"
LIVE_MODE = "LIVE"

REQUIRED_MANIFEST_KEYS = {"batch_id", "created_at", "entries", "batch_hash"}


def _stable_json_bytes(value: Any) -> bytes:
    """Serialize any JSON-compatible value with stable ordering for hashing."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def compute_batch_hash(entries: List[Dict[str, Any]]) -> str:
    """
    Compute the SHA-256 hash for the provided manifest entries.

    Args:
        entries: List of manifest entry dictionaries.

    Returns:
        Hex-encoded SHA-256 digest.

    Raises:
        ConstitutionalError: If entries are invalid or non-serializable.
    """
    if not isinstance(entries, list):
        raise ConstitutionalError("Manifest entries must be provided as a list.")

    for entry in entries:
        if not isinstance(entry, dict):
            raise ConstitutionalError("Each manifest entry must be a dictionary.")

    try:
        digest = sha256(_stable_json_bytes(entries)).hexdigest()
    except TypeError as exc:
        raise ConstitutionalError(
            f"Manifest entries are not JSON serializable: {exc}"
        ) from exc

    return digest


def _validate_manifest(manifest: Dict[str, Any]) -> None:
    """Validate manifest schema and content."""
    missing = REQUIRED_MANIFEST_KEYS - manifest.keys()
    if missing:
        raise ConstitutionalError(
            f"Manifest missing required fields: {', '.join(sorted(missing))}"
        )

    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ConstitutionalError("Manifest entries must be a non-empty list.")

    batch_hash = manifest.get("batch_hash")
    expected_hash = compute_batch_hash(entries)
    if batch_hash != expected_hash:
        raise ConstitutionalError(
            "Manifest batch_hash does not match computed entries hash."
        )


def _mock_store(manifest: Dict[str, Any]) -> str:
    """Return deterministic transaction ID for MOCK mode."""
    manifest_bytes = _stable_json_bytes(manifest)
    digest = sha256(manifest_bytes).hexdigest()
    return f"arweave_tx_mock_{digest}"


def store_log_batch(manifest: Dict[str, Any]) -> str:
    """
    Store an immutable log batch on Arweave (MOCK by default).

    Args:
        manifest: Manifest dictionary describing the batch.

    Returns:
        Transaction ID string (deterministic in MOCK mode).

    Raises:
        ConstitutionalError: If configuration or manifest is invalid.
    """
    if not isinstance(manifest, dict):
        raise ConstitutionalError("Manifest must be provided as a dictionary.")

    _validate_manifest(manifest)

    settings = get_settings()
    mode = settings.immutable_logging_mode.upper()

    logger.info(
        "immutable_batch_store_attempt",
        extra={
            "adapter_mode": mode,
            "batch_id": manifest.get("batch_id"),
            "entry_count": len(manifest.get("entries", [])),
        },
    )

    if mode == MOCK_MODE:
        tx_id = _mock_store(manifest)
    elif mode == LIVE_MODE:
        raise ConstitutionalError("Arweave LIVE mode not configured.")
    else:
        raise ConstitutionalError(f"Unknown immutable logging mode: {mode}")

    logger.info(
        "immutable_batch_store_result",
        extra={
            "adapter_mode": mode,
            "batch_id": manifest.get("batch_id"),
            "tx_id": tx_id,
        },
    )
    return tx_id



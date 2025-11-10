"""Owner signature management for Rule 10 compliance."""

from __future__ import annotations

from datetime import datetime, UTC
import hashlib
import hmac
import json
import logging
from typing import Any, Mapping

from config_settings.config import get_settings
from constitutional_layer_immutable.constitution import (
    validate_constitutional_compliance,
)
from models.core import ConstitutionalError

logger = logging.getLogger(__name__)


def _normalize_payload(payload: Mapping[str, Any]) -> str:
    """Normalize payload dictionaries into a deterministic JSON string."""
    try:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        logger.error(
            "Failed to normalize payload for owner signing",
            exc_info=True,
            extra={"event": "owner_signature_payload_error"},
        )
        raise ConstitutionalError(
            "Rule 10 Violation: Unable to normalize payload for owner signature"
        ) from exc
    return normalized


def _get_owner_settings() -> tuple[str, str, bool]:
    """Retrieve owner authorization settings and ensure mandatory fields."""
    settings = get_settings()
    owner_auth_mode = settings.owner_auth_mode.upper()
    owner_id = settings.owner_id
    owner_signature_key = settings.owner_signature_key or ""

    if not owner_id:
        logger.error(
            "Owner ID missing in configuration",
            extra={"event": "owner_signature_configuration_error"},
        )
        raise ConstitutionalError("Rule 10 Violation: OWNER_ID must be configured")

    if owner_auth_mode == "SOFTWARE" and not owner_signature_key:
        logger.error(
            "Owner signature key missing for software mode",
            extra={"event": "owner_signature_configuration_error"},
        )
        raise ConstitutionalError(
            "Rule 10 Violation: OWNER_SIGNATURE_KEY required in SOFTWARE mode"
        )

    return owner_auth_mode, owner_signature_key, settings.owner_gate_enabled


def sign_action(owner_id: str, payload: Mapping[str, Any]) -> str:
    """
    Generate a secure signature for an owner-approved action.

    Args:
        owner_id: Identifier of the owner generating the signature.
        payload: Action payload requiring authorization.

    Returns:
        Owner signature string encoded per authorization mode.

    Raises:
        ConstitutionalError: If signing fails or violates Rule 10 requirements.
    """
    logger.info(
        "Owner sign attempt",
        extra={"event": "owner_sign_attempt", "owner_id": owner_id},
    )

    normalized_payload = _normalize_payload(payload)
    owner_auth_mode, owner_signature_key, _ = _get_owner_settings()

    timestamp = datetime.now(UTC).isoformat(timespec="seconds")

    if owner_auth_mode == "SOFTWARE":
        message = f"{owner_id}:{timestamp}:{normalized_payload}".encode("utf-8")
        digest = hmac.new(
            owner_signature_key.encode("utf-8"), msg=message, digestmod=hashlib.sha256
        ).hexdigest()
        signature = f"software:{timestamp}:{digest}"
    elif owner_auth_mode == "MOCK":
        mock_hash = hashlib.sha256(
            f"{owner_id}:{normalized_payload}".encode("utf-8")
        ).hexdigest()
        signature = f"mock_owner_signature:{mock_hash}"
    elif owner_auth_mode == "HARDWARE":
        logger.error(
            "Hardware signing not configured",
            extra={"event": "owner_sign_result", "owner_id": owner_id},
        )
        raise ConstitutionalError("Hardware signing not configured")
    else:
        logger.error(
            "Unsupported owner authentication mode",
            extra={
                "event": "owner_sign_result",
                "owner_id": owner_id,
                "owner_auth_mode": owner_auth_mode,
            },
        )
        raise ConstitutionalError(
            f"Rule 10 Violation: Unsupported owner authentication mode '{owner_auth_mode}'"
        )

    validation = validate_constitutional_compliance(
        action={
            "type": "owner_signature_generation",
            "description": "Owner sign action",
            "owner_authorized": True,
        }
    )
    if not validation.is_compliant:
        logger.error(
            "Owner signature generation failed compliance check",
            extra={
                "event": "owner_sign_result",
                "owner_id": owner_id,
                "violations": validation.violated_rules,
            },
        )
        raise ConstitutionalError(
            f"Rule 10 Violation: Signature generation blocked {validation.violated_rules}"
        )

    logger.info(
        "Owner sign result",
        extra={
            "event": "owner_sign_result",
            "owner_id": owner_id,
            "owner_auth_mode": owner_auth_mode,
        },
    )
    return signature


def verify_owner_signature(
    owner_id: str, payload: Mapping[str, Any], signature: str
) -> bool:
    """
    Verify an owner signature against a payload.

    Args:
        owner_id: Identifier of the owner expected to have signed.
        payload: Payload data associated with the signature.
        signature: Signature string provided for validation.

    Returns:
        True if signature is valid, False otherwise.
    """
    logger.info(
        "Owner signature verification attempt",
        extra={"event": "owner_verify_attempt", "owner_id": owner_id},
    )

    normalized_payload = _normalize_payload(payload)
    owner_auth_mode, owner_signature_key, _ = _get_owner_settings()

    is_valid = False

    if owner_auth_mode == "SOFTWARE":
        prefix, first_sep, remainder = signature.partition(":")
        if not first_sep:
            logger.warning(
                "Invalid software signature format",
                extra={
                    "event": "owner_verify_result",
                    "owner_id": owner_id,
                    "owner_auth_mode": owner_auth_mode,
                },
            )
            is_valid = False
            is_valid = False
        else:
            timestamp, last_sep, provided_digest = remainder.rpartition(":")
            if prefix != "software" or not last_sep:
                logger.warning(
                    "Software signature prefix mismatch",
                    extra={
                        "event": "owner_verify_result",
                        "owner_id": owner_id,
                        "owner_auth_mode": owner_auth_mode,
                    },
                )
                is_valid = False
            else:
                message = f"{owner_id}:{timestamp}:{normalized_payload}".encode("utf-8")
                expected_digest = hmac.new(
                    owner_signature_key.encode("utf-8"),
                    msg=message,
                    digestmod=hashlib.sha256,
                ).hexdigest()
                is_valid = hmac.compare_digest(expected_digest, provided_digest)
    elif owner_auth_mode == "MOCK":
        expected_hash = hashlib.sha256(
            f"{owner_id}:{normalized_payload}".encode("utf-8")
        ).hexdigest()
        is_valid = hmac.compare_digest(
            signature, f"mock_owner_signature:{expected_hash}"
        )
    elif owner_auth_mode == "HARDWARE":
        logger.warning(
            "Hardware verification stub in use",
            extra={
                "event": "owner_verify_result",
                "owner_id": owner_id,
                "owner_auth_mode": owner_auth_mode,
            },
        )
        is_valid = False
    else:
        logger.error(
            "Unsupported owner authentication mode during verification",
            extra={
                "event": "owner_verify_result",
                "owner_id": owner_id,
                "owner_auth_mode": owner_auth_mode,
            },
        )
        raise ConstitutionalError(
            f"Rule 10 Violation: Unsupported owner authentication mode '{owner_auth_mode}'"
        )

    validation = validate_constitutional_compliance(
        action={
            "type": "owner_signature_verification",
            "description": "Verify owner signature",
            "owner_authorized": is_valid,
        }
    )
    if not validation.is_compliant:
        logger.error(
            "Owner signature verification failed compliance check",
            extra={
                "event": "owner_verify_result",
                "owner_id": owner_id,
                "violations": validation.violated_rules,
            },
        )
        raise ConstitutionalError(
            f"Rule 10 Violation: Signature verification blocked {validation.violated_rules}"
        )

    logger.info(
        "Owner signature verification result",
        extra={
            "event": "owner_verify_result",
            "owner_id": owner_id,
            "owner_auth_mode": owner_auth_mode,
            "is_valid": is_valid,
        },
    )
    return is_valid



"""Owner gate authorization decorator and utilities."""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, Mapping, Optional, TypeVar, cast

from config_settings.config import get_settings
from constitutional_layer_immutable.constitution import (
    validate_constitutional_compliance,
)
from models.core import ConstitutionalError

from owner_control.owner_gate.signature import verify_owner_signature

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def is_owner_gate_enabled() -> bool:
    """Return True unless OWNER_GATE_ENABLED=false (used for testing)."""
    settings = get_settings()
    return bool(settings.owner_gate_enabled)


def _extract_authorization_context(
    args: tuple[Any, ...], kwargs: dict[str, Any]
) -> tuple[str, str, Mapping[str, Any]]:
    """Extract owner authorization context from function arguments."""
    owner_id: Optional[str] = cast(Optional[str], kwargs.get("owner_id"))
    owner_signature: Optional[str] = cast(
        Optional[str], kwargs.get("owner_signature")
    )

    payload: Optional[Mapping[str, Any]] = None

    if "authorization_payload" in kwargs and isinstance(
        kwargs["authorization_payload"], Mapping
    ):
        payload = cast(Mapping[str, Any], kwargs["authorization_payload"])
    elif "owner_payload" in kwargs and isinstance(kwargs["owner_payload"], Mapping):
        payload = cast(Mapping[str, Any], kwargs["owner_payload"])
    elif "payload" in kwargs and isinstance(kwargs["payload"], Mapping):
        payload = cast(Mapping[str, Any], kwargs["payload"])

    if owner_id is None or payload is None:
        if args:
            first_arg = args[0]
            if isinstance(first_arg, Mapping):
                mapping_arg = cast(Mapping[str, Any], first_arg)
                owner_id = owner_id or cast(Optional[str], mapping_arg.get("owner_id"))
                owner_signature = owner_signature or cast(
                    Optional[str], mapping_arg.get("owner_signature")
                )
                if payload is None:
                    if (
                        "authorization_payload" in mapping_arg
                        and isinstance(mapping_arg["authorization_payload"], Mapping)
                    ):
                        payload = cast(
                            Mapping[str, Any], mapping_arg["authorization_payload"]
                        )
                    else:
                        payload = {
                            key: value
                            for key, value in mapping_arg.items()
                            if key != "owner_signature"
                        }

    if owner_id is None or payload is None:
        logger.error(
            "Owner authorization context missing",
            extra={"event": "owner_gate_context_missing"},
        )
        raise ConstitutionalError(
            "Rule 10 Violation: Owner authorization context required"
        )

    return owner_id, owner_signature, payload


def require_owner_approval(action_name: str) -> Callable[[F], F]:
    """
    Decorator enforcing owner authorization for critical operations (Rule 10).

    Args:
        action_name: Human-readable name of the action being protected.

    Returns:
        Decorated function requiring owner signature verification.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.info(
                "Owner gate check initiated",
                extra={"event": "owner_gate_check", "action_name": action_name},
            )

            pre_validation = validate_constitutional_compliance(
                action={
                    "type": f"{action_name}_precheck",
                    "description": f"Owner gate pre-validation for {action_name}",
                    "owner_authorized": False,
                }
            )
            if not pre_validation.is_compliant:
                logger.error(
                    "Owner gate pre-validation failed",
                    extra={
                        "event": "owner_gate_check_failed",
                        "action_name": action_name,
                        "violations": pre_validation.violated_rules,
                    },
                )
                raise ConstitutionalError(
                    f"Rule 10 Violation: Pre-validation failed {pre_validation.violated_rules}"
                )

            if not is_owner_gate_enabled():
                logger.warning(
                    "Owner gate disabled, proceeding without verification",
                    extra={
                        "event": "owner_gate_bypass",
                        "action_name": action_name,
                    },
                )
                result = func(*args, **kwargs)
                post_validation = validate_constitutional_compliance(
                    action={
                        "type": f"{action_name}_postcheck",
                        "description": f"Owner gate post-validation for {action_name}",
                        "owner_authorized": True,
                    }
                )
                if not post_validation.is_compliant:
                    logger.error(
                        "Owner gate post-validation failed",
                        extra={
                            "event": "owner_gate_post_failed",
                            "action_name": action_name,
                            "violations": post_validation.violated_rules,
                        },
                    )
                    raise ConstitutionalError(
                        f"Rule 10 Violation: Post-validation failed {post_validation.violated_rules}"
                    )
                logger.info(
                    "Owner gate completed (disabled)",
                    extra={"event": "owner_gate_completed", "action_name": action_name},
                )
                return result

            owner_id, owner_signature, payload = _extract_authorization_context(
                args, kwargs
            )

            if not owner_signature:
                logger.error(
                    "Owner gate verification failed (no signature provided)",
                    extra={
                        "event": "owner_gate_failed",
                        "action_name": action_name,
                        "owner_id": owner_id,
                    },
                )
                raise ConstitutionalError(
                    f"Rule 10 Violation: {action_name} requires owner approval"
                )

            is_valid = verify_owner_signature(
                owner_id=owner_id, payload=payload, signature=owner_signature
            )

            if not is_valid:
                logger.error(
                    "Owner gate verification failed",
                    extra={
                        "event": "owner_gate_failed",
                        "action_name": action_name,
                        "owner_id": owner_id,
                    },
                )
                raise ConstitutionalError(
                    f"Rule 10 Violation: {action_name} requires owner approval"
                )

            logger.info(
                "Owner gate passed",
                extra={
                    "event": "owner_gate_passed",
                    "action_name": action_name,
                    "owner_id": owner_id,
                },
            )

            result = func(*args, **kwargs)

            post_validation = validate_constitutional_compliance(
                action={
                    "type": f"{action_name}_postcheck",
                    "description": f"Owner gate post-validation for {action_name}",
                    "owner_authorized": True,
                }
            )
            if not post_validation.is_compliant:
                logger.error(
                    "Owner gate post-validation failed",
                    extra={
                        "event": "owner_gate_post_failed",
                        "action_name": action_name,
                        "violations": post_validation.violated_rules,
                    },
                )
                raise ConstitutionalError(
                    f"Rule 10 Violation: Post-validation failed {post_validation.violated_rules}"
                )

            logger.info(
                "Owner gate completed",
                extra={"event": "owner_gate_completed", "action_name": action_name},
            )
            return result

        return cast(F, wrapper)

    return decorator



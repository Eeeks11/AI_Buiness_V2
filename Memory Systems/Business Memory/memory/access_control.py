"""
Access Control for Memory Systems

Manages permissions and access to different memory stores.
Enforces Rule 10: Human Ownership Lock - owner retains ultimate authority.
"""

# Standard library
import logging
from pathlib import Path
from typing import Optional
import sys

# Local - models first (single source of truth)
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "Memory Systems" / "Codebase Memory"))
from models.core import ConstitutionalRule, ConstitutionalError

# Local - constitutional enforcement
sys.path.insert(0, str(project_root / "Constitutional Layer (Immutable)"))
from constitution import validate_constitutional_compliance

# Local - configuration
sys.path.insert(0, str(project_root / "Config & Settings"))
from config import get_settings

logger = logging.getLogger(__name__)


def validate_memory_operation(
    operation: str,
    requester: str,
    owner_signature: Optional[str] = None
) -> bool:
    """
    Validate memory operation permissions (Rule 10 enforcement).
    
    Operations:
    - "read": Always allowed
    - "write": Requires valid owner_signature (Rule 10)
    - "delete": Always forbidden (Rule 6 - transparency)
    - "modify": Requires owner_signature + board approval
    
    Args:
        operation: Type of operation ("read", "write", "delete", "modify")
        requester: Identifier of the entity requesting the operation
        owner_signature: Optional owner signature for authorization
        
    Returns:
        True if operation is allowed
        
    Raises:
        ConstitutionalError: If operation is unauthorized
        
    Example:
        >>> # Read operation (always allowed)
        >>> validate_memory_operation("read", "system")
        True
        
        >>> # Write operation (requires signature)
        >>> validate_memory_operation("write", "system", "valid_signature")
        True
        
        >>> # Delete operation (always forbidden)
        >>> validate_memory_operation("delete", "system")
        Traceback (most recent call last):
        ...
        ConstitutionalError: Rule 6 Violation: Delete operations are forbidden...
    """
    logger.debug(
        f"Validating memory operation: {operation} by {requester}",
        extra={"operation": operation, "requester": requester}
    )
    
    # Normalize operation to lowercase
    operation = operation.lower()
    
    # Rule: "read" - Always allowed
    if operation == "read":
        logger.info(f"Memory read operation allowed for {requester}")
        return True
    
    # Rule: "delete" - Always forbidden (Rule 6 - transparency)
    if operation == "delete":
        logger.error(
            f"Rule 6 Violation: Delete operation attempted by {requester}",
            extra={"operation": operation, "requester": requester}
        )
        raise ConstitutionalError(
            "Rule 6 Violation: Delete operations are forbidden to maintain full transparency. "
            "All memory operations must be logged and immutable."
        )
    
    # Rule: "write" - Requires valid owner_signature (Rule 10)
    if operation == "write":
        if not owner_signature:
            logger.warning(
                f"Rule 10 Violation: Write operation attempted without owner signature by {requester}",
                extra={"operation": operation, "requester": requester}
            )
            raise ConstitutionalError(
                "Rule 10 Violation: Write operations require owner authorization. "
                "Owner retains ultimate authority and control."
            )
        
        # Validate owner signature
        if not check_owner_signature(owner_signature):
            logger.error(
                f"Rule 10 Violation: Invalid owner signature for write operation by {requester}",
                extra={"operation": operation, "requester": requester}
            )
            raise ConstitutionalError(
                "Rule 10 Violation: Invalid owner signature. Write operations require valid owner authorization."
            )
        
        logger.info(f"Memory write operation authorized for {requester}")
        return True
    
    # Rule: "modify" - Requires owner_signature + board approval
    if operation == "modify":
        if not owner_signature:
            logger.warning(
                f"Rule 10 Violation: Modify operation attempted without owner signature by {requester}",
                extra={"operation": operation, "requester": requester}
            )
            raise ConstitutionalError(
                "Rule 10 Violation: Modify operations require owner authorization. "
                "Owner retains ultimate authority and control."
            )
        
        # Validate owner signature
        if not check_owner_signature(owner_signature):
            logger.error(
                f"Rule 10 Violation: Invalid owner signature for modify operation by {requester}",
                extra={"operation": operation, "requester": requester}
            )
            raise ConstitutionalError(
                "Rule 10 Violation: Invalid owner signature. Modify operations require valid owner authorization."
            )
        
        # Note: Board approval check would be done at a higher level
        # For now, owner signature is sufficient for modify operations
        logger.info(f"Memory modify operation authorized for {requester}")
        return True
    
    # Unknown operation
    logger.warning(f"Unknown memory operation: {operation}")
    raise ConstitutionalError(
        f"Unknown memory operation: {operation}. "
        f"Supported operations: read, write, delete, modify"
    )


def check_owner_signature(signature: str) -> bool:
    """
    Check if owner signature is valid.
    
    Placeholder for Week 7-8 YubiKey integration. For now:
    - In DEBUG mode: returns True if signature == "mock_owner_signature"
    - In production: returns False without valid signature
    
    Args:
        signature: Owner signature string to validate
        
    Returns:
        True if signature is valid, False otherwise
        
    Example:
        >>> # In DEBUG mode
        >>> check_owner_signature("mock_owner_signature")
        True
        
        >>> # In production
        >>> check_owner_signature("invalid")
        False
    """
    try:
        settings = get_settings()
        debug_mode = settings.debug
        
        # Log signature check attempt (Rule 6)
        logger.debug(
            f"Checking owner signature (debug_mode={debug_mode})",
            extra={"debug_mode": debug_mode}
        )
        
        # In DEBUG mode, allow mock signature for testing
        if debug_mode:
            if signature == "mock_owner_signature":
                logger.info("Owner signature validated (DEBUG mode - mock signature)")
                return True
            else:
                logger.warning(f"Invalid owner signature in DEBUG mode: {signature[:20]}...")
                return False
        
        # In production, signature validation will be implemented in Week 7-8
        # For now, return False (requires actual YubiKey integration)
        logger.warning(
            "Owner signature validation not yet implemented. "
            "YubiKey integration scheduled for Week 7-8."
        )
        return False
        
    except Exception as e:
        logger.error(f"Error checking owner signature: {e}", exc_info=True)
        return False

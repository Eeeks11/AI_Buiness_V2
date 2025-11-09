"""Compatibility shim maintaining legacy `Utilities` imports while canonical path is `utilities`."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

_package_path = Path(__file__).with_name("Utilities")
if _package_path.exists():
    __path__ = [str(_package_path)]
    logger = import_module("Utilities.logger")
    sys.modules.setdefault(__name__ + ".logger", logger)
    sys.modules.setdefault("Utilities.logger", logger)
else:
    raise ModuleNotFoundError(
        "Legacy Utilities package not found; ensure the project root is on PYTHONPATH."
    )

log_event = logger.log_event
validate_log_chain = logger.validate_log_chain
get_recent_logs = logger.get_recent_logs
export_logs = logger.export_logs
export_batch_index = logger.export_batch_index

__all__ = [
    "log_event",
    "validate_log_chain",
    "get_recent_logs",
    "export_logs",
    "export_batch_index",
]



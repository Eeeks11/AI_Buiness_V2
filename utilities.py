"""Compatibility shim allowing `import utilities` to resolve to `Utilities` package."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

_package_path = Path(__file__).with_name("Utilities")
__path__ = [str(_package_path)]

logger = import_module("Utilities.logger")
sys.modules[__name__ + ".logger"] = logger



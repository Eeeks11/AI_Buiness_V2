"""Utilities package compatibility wrapper."""

import sys

from . import logger as _logger

sys.modules.setdefault("utilities", sys.modules[__name__])
sys.modules.setdefault("utilities.logger", _logger)

"""Test configuration ensuring project packages are importable."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_project_paths_on_sys_path() -> None:
    """Prepend key project directories to sys.path for package imports."""
    project_root = Path(__file__).resolve().parent.parent

    paths_to_add = [
        project_root,
        project_root / "memory_systems" / "codebase_memory",
    ]

    for path in paths_to_add:
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


_ensure_project_paths_on_sys_path()



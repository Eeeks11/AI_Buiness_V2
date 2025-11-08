"""Import smoke test for AI Business Governance System packages.

This script traverses all Python modules in the repository, attempts to
import each one, and reports the result. It is designed to ensure that
package renames and refactors preserve importability across the codebase.
"""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from typing import Iterable, List, Set


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IGNORE_DIRECTORIES: Set[str] = {
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "venv",
    "Lib",
    "Scripts",
    "site-packages",
    "dist-info",
    ".cursor",
}


def discover_modules(root: Path) -> List[str]:
    """Return a sorted list of dotted module paths discoverable under *root*."""
    modules: Set[str] = set()
    for path in root.rglob("*.py"):
        if path == Path(__file__).resolve():
            continue
        if any(part in IGNORE_DIRECTORIES for part in path.parts):
            continue
        relative = path.relative_to(root)
        top_level = relative.parts[0]
        if top_level.startswith("."):
            continue
        if top_level in IGNORE_DIRECTORIES:
            continue
        if relative.name == "__init__.py":
            package_parts = relative.parts[:-1]
            if not package_parts:
                continue
            module_name = ".".join(package_parts)
        else:
            module_name = ".".join(relative.with_suffix("").parts)
        modules.add(module_name)
    return sorted(modules)


def print_results(successes: Iterable[str], failures: Iterable[tuple[str, Exception]]) -> None:
    """Print import results using the required symbols."""
    for module in successes:
        print(f"✅ {module}")
    for module, error in failures:
        print(f"❌ {module}: {error}")


def run_import_smoke_test() -> int:
    """Attempt to import every discovered module and return an exit status."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger("import_smoke_test")

    stdout = getattr(sys, "stdout", None)
    reconfigure = getattr(stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")

    sys.path.insert(0, str(PROJECT_ROOT))

    modules = discover_modules(PROJECT_ROOT)
    successes: List[str] = []
    failures: List[tuple[str, Exception]] = []

    for module in modules:
        try:
            importlib.import_module(module)
            successes.append(module)
        except Exception as error:
            logger.exception("Import failed for module %s", module)
            failures.append((module, error))

    print_results(successes, failures)
    return 1 if failures else 0


def main() -> None:
    """Entry point for the import smoke test."""
    exit_code = run_import_smoke_test()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()


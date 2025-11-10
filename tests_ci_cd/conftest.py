"""Test configuration ensuring project packages are importable."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Dict, Any

import pytest


def _ensure_project_paths_on_sys_path() -> None:
    """Prepend key project directories to sys.path for package imports."""
    project_root = Path(__file__).resolve().parent.parent

    paths_to_add = [
        project_root,
    ]

    for path in paths_to_add:
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


_ensure_project_paths_on_sys_path()


@pytest.fixture()
def isolated_logging_env(tmp_path, monkeypatch) -> Dict[str, Any]:
    """Provide isolated immutable logging environment for tests."""
    project_root = Path(__file__).resolve().parent.parent

    log_dir = tmp_path / "audit_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "events.jsonl"
    metrics_path = log_dir / "metrics.jsonl"

    monkeypatch.setenv("LOG_FILE_PATH", str(log_path))
    monkeypatch.setenv("IMMUTABLE_LOGGING_ENABLED", "false")
    monkeypatch.setenv("IMMUTABLE_BATCH_SIZE", "50")

    # Reload configuration to pick up new environment variables
    import config_settings.config as config_module

    importlib.reload(config_module)
    if hasattr(config_module, "_settings"):
        config_module._settings = None  # type: ignore[attr-defined]
    if hasattr(config_module, "settings"):
        delattr(config_module, "settings")

    config_module._settings = None  # type: ignore[attr-defined]
    config_module_settings = config_module.get_settings()

    # Reload logger modules to use the updated configuration
    for module_name in ("utilities.logger", "Utilities.logger"):
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
        else:
            importlib.import_module(module_name)

    logger_module = sys.modules["utilities.logger"]

    # Ensure telemetry metrics writes to isolated path
    import telemetry.metrics as metrics_module

    importlib.reload(metrics_module)

    def _isolated_metrics_path() -> Path:
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        return metrics_path

    monkeypatch.setattr(metrics_module, "_resolve_metrics_path", _isolated_metrics_path)

    return {
        "log_path": log_path,
        "metrics_path": metrics_path,
        "logger_module": logger_module,
        "metrics_module": metrics_module,
        "settings": config_module_settings,
    }

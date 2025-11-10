from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Dict, List

import pytest


def _reload_module(module_name: str):
    """Reload a module if present, otherwise import it."""
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


@pytest.fixture()
def immutable_logger(tmp_path, monkeypatch):
    """Provide a fresh immutable logger instance with isolated settings."""
    log_file = tmp_path / "events.jsonl"
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))
    monkeypatch.setenv("IMMUTABLE_LOGGING_MODE", "MOCK")
    monkeypatch.setenv("IMMUTABLE_LOGGING_ENABLED", "true")
    monkeypatch.setenv("IMMUTABLE_BATCH_SIZE", "3")

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    config_module = _reload_module("config_settings.config")
    config_module._settings = None  # type: ignore[attr-defined]
    config_module.settings = config_module.get_settings()  # type: ignore[attr-defined]

    for module_name in ["utilities.logger", "Utilities.logger"]:
        if module_name in sys.modules:
            del sys.modules[module_name]

    logger_module = _reload_module("utilities.logger")
    _reload_module("Utilities.logger")
    return logger_module


def test_chain_links_are_correct(immutable_logger):
    logger = immutable_logger

    entries: List[Dict] = []
    for idx in range(3):
        entry = logger.log_event(
            event_type=f"test_event_{idx}",
            data={"value": idx},
            metadata={"test": True},
        )
        entries.append(entry)

    for prev, current in zip(entries, entries[1:]):
        assert current["prev_hash"] == prev["chain_hash"]

    is_valid = logger.validate_log_chain()
    assert is_valid
    assert len(logger.export_logs()) >= 3


def test_batching_triggers_after_threshold(monkeypatch, immutable_logger):
    logger = immutable_logger
    captured_manifests: List[Dict] = []

    def fake_store(manifest: Dict[str, object]) -> str:
        captured_manifests.append(manifest)
        return "arweave_tx_mock_fake"

    monkeypatch.setattr(logger, "store_log_batch", fake_store)

    for idx in range(3):
        logger.log_event(
            event_type="batch_test",
            data={"index": idx},
        )

    assert len(captured_manifests) == 1
    manifest = captured_manifests[0]
    assert manifest["batch_hash"] == logger.compute_batch_hash(manifest["entries"])

    batch_index = logger.export_batch_index()
    assert batch_index["batches"][0]["tx_id"] == "arweave_tx_mock_fake"

    next_entry = logger.log_event(event_type="post_batch", data={})
    assert next_entry.get("last_pin_tx_id") == "arweave_tx_mock_fake"


def test_arweave_adapter_mock_tx_id_is_deterministic(monkeypatch):
    monkeypatch.setenv("IMMUTABLE_LOGGING_MODE", "MOCK")
    adapter = _reload_module("memory_systems.codebase_memory.immutable_storage.arweave_adapter")
    entries = [
        {"timestamp": "2024-01-01T00:00:00Z", "event_type": "alpha", "chain_hash": "abc"},
        {"timestamp": "2024-01-01T00:01:00Z", "event_type": "beta", "chain_hash": "def"},
    ]
    manifest = {
        "batch_id": "batch-1",
        "created_at": "2024-01-01T00:05:00Z",
        "entries": entries,
        "batch_hash": adapter.compute_batch_hash(entries),
    }

    tx_id_one = adapter.store_log_batch(manifest)
    tx_id_two = adapter.store_log_batch(manifest)
    assert tx_id_one == tx_id_two
    assert tx_id_one.startswith("arweave_tx_mock_")


def test_manifest_hash_matches_entries():
    adapter = _reload_module("memory_systems.codebase_memory.immutable_storage.arweave_adapter")
    entries = [
        {"timestamp": "2024-01-01T00:00:00Z", "event_type": "alpha", "chain_hash": "abc"},
        {"timestamp": "2024-01-01T00:01:00Z", "event_type": "beta", "chain_hash": "def"},
    ]
    batch_hash = adapter.compute_batch_hash(entries)
    manifest = {
        "batch_id": "batch-2",
        "created_at": "2024-01-01T00:10:00Z",
        "entries": entries,
        "batch_hash": batch_hash,
    }
    assert batch_hash == adapter.compute_batch_hash(manifest["entries"])


def test_export_functions_produce_valid_json(immutable_logger):
    logger = immutable_logger
    logger.log_event(event_type="export_test", data={"value": 1})
    logger.log_event(event_type="export_test", data={"value": 2})

    logs = logger.export_logs()
    index = logger.export_batch_index()

    serialized_logs = json.dumps(logs)
    serialized_index = json.dumps(index)

    assert isinstance(serialized_logs, str)
    assert isinstance(serialized_index, str)


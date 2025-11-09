from __future__ import annotations

import importlib
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def mock_streamlit(monkeypatch):
    """Provide a minimal Streamlit mock for audit viewer tests."""
    mock = MagicMock()
    sidebar = MagicMock()
    sidebar.__enter__.return_value = sidebar
    sidebar.__exit__.return_value = False
    mock.sidebar = sidebar

    form_ctx = MagicMock()
    form_ctx.__enter__.return_value = form_ctx
    form_ctx.__exit__.return_value = False
    mock.form.return_value = form_ctx

    mock.selectbox.return_value = "All"
    mock.date_input.return_value = ()
    mock.text_input.return_value = ""
    mock.checkbox.return_value = False
    mock.form_submit_button.return_value = False
    mock.button.return_value = False
    mock.download_button.return_value = False

    monkeypatch.setitem(sys.modules, "streamlit", mock)
    return mock


@pytest.fixture()
def audit_viewer_module(mock_streamlit):
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    codebase_path = project_root / "memory_systems" / "codebase_memory"
    if str(codebase_path) not in sys.path:
        sys.path.insert(0, str(codebase_path))
    if "owner_control.dashboard.audit_viewer" in sys.modules:
        del sys.modules["owner_control.dashboard.audit_viewer"]
    return importlib.import_module("owner_control.dashboard.audit_viewer")


def test_audit_viewer_imports(audit_viewer_module):
    assert audit_viewer_module is not None


def test_validate_chain_button_calls_validator(audit_viewer_module, mock_streamlit, monkeypatch):
    mock_streamlit.button.return_value = True
    mock_streamlit.download_button.return_value = False

    sample_logs = [
        {"timestamp": "2024-01-01T00:00:00", "type": "alpha", "chain_hash": "x", "last_pin_tx_id": None}
    ]
    sample_index = {"batches": []}

    monkeypatch.setattr(audit_viewer_module, "export_logs", MagicMock(return_value=sample_logs))
    monkeypatch.setattr(audit_viewer_module, "export_batch_index", MagicMock(return_value=sample_index))
    mock_response = MagicMock(success=True, data={"entry_count": 1})
    validator = MagicMock(return_value=mock_response)
    monkeypatch.setattr(audit_viewer_module, "validate_log_chain", validator)
    monkeypatch.setattr(audit_viewer_module, "_log_dashboard_event", MagicMock())

    audit_viewer_module.main()

    validator.assert_called_once()


def test_filters_do_not_crash(audit_viewer_module, mock_streamlit, monkeypatch):
    mock_streamlit.selectbox.return_value = "alpha"
    mock_streamlit.date_input.return_value = (date(2024, 1, 1), date(2024, 1, 2))
    mock_streamlit.text_input.return_value = "search"
    mock_streamlit.checkbox.return_value = True
    mock_streamlit.form_submit_button.return_value = True

    sample_logs = [
        {"timestamp": "2024-01-01T00:00:00", "type": "alpha", "chain_hash": "x", "last_pin_tx_id": None},
        {"timestamp": "2024-01-03T00:00:00", "type": "beta", "chain_hash": "y", "last_pin_tx_id": None},
    ]
    sample_index = {
        "batches": [
            {
                "batch_id": "batch-1",
                "tx_id": "tx123",
                "entry_count": 2,
                "manifest_entries": [{"chain_hash": "x"}],
            }
        ]
    }

    monkeypatch.setattr(audit_viewer_module, "export_logs", MagicMock(return_value=sample_logs))
    monkeypatch.setattr(audit_viewer_module, "export_batch_index", MagicMock(return_value=sample_index))
    monkeypatch.setattr(audit_viewer_module, "_log_dashboard_event", MagicMock())
    monkeypatch.setattr(audit_viewer_module, "validate_log_chain", MagicMock())

    audit_viewer_module.main()


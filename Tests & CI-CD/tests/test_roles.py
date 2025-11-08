"""
Tests for board role configuration and prompt generation.
"""

# Standard library
import math
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

# Third-party
import pytest

# Path setup
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "Governance Layer" / "roles"))
sys.path.insert(0, str(PROJECT_ROOT / "Memory Systems" / "Codebase Memory"))

# Local imports
from models.core import ConstitutionalError
from prompt_templates import generate_role_prompt, load_role_configs


def test_role_configs_sum_to_one() -> None:
    """Ensure role configurations meet Rule 9 requirements."""
    role_configs = load_role_configs()

    assert len(role_configs) == 8
    total_weight = sum(config["voting_weight"] for config in role_configs.values())
    assert math.isclose(total_weight, 1.0, rel_tol=1e-9)
    assert all(config["voting_weight"] <= 0.25 for config in role_configs.values())


@patch("prompt_templates.log_event")
@patch("prompt_templates.validate_constitutional_compliance")
def test_generate_role_prompt_uses_context(
    mock_validate: MagicMock,
    mock_log_event: MagicMock
) -> None:
    """Role prompts should embed memory context and log generation."""
    mock_validate.return_value = MagicMock(is_compliant=True, violated_rules=[])

    context = {
        "current_proposal": {
            "id": "prop-123",
            "title": "Launch New Product Line",
            "description": "Introduce AI-driven analytics suite.",
            "financial_impact": 1250000.0,
            "legal_risk": 0.2
        },
        "constitutional_rules": {"rule_4": "Financial Priority - maximize owner profit"},
        "recent_activity_summary": "Board approved infrastructure upgrade last cycle.",
        "relevant_precedents": [{"summary": "Approved strategic expansion into EMEA."}],
        "trend_analysis": "Market demand for analytics growing 18% YoY."
    }

    prompt = generate_role_prompt("CEO", context)

    assert "Launch New Product Line" in prompt
    assert "Board approved infrastructure upgrade" in prompt
    assert "Approved strategic expansion into EMEA" in prompt
    assert "Market demand for analytics" in prompt

    mock_log_event.assert_called_once()
    mock_validate.assert_called_once()


@patch("prompt_templates.validate_constitutional_compliance", side_effect=ConstitutionalError("Rule 6 Violation"))
def test_generate_role_prompt_validation_failure(mock_validate: MagicMock) -> None:
    """Prompt generation should propagate constitutional validation errors."""
    context = {
        "current_proposal": {"id": "prop-999"},
        "constitutional_rules": {},
        "recent_activity_summary": "",
        "relevant_precedents": [],
        "trend_analysis": ""
    }

    with pytest.raises(ConstitutionalError):
        generate_role_prompt("LEGAL", context)


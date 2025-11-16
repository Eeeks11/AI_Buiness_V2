"""Automated health check script ensuring operational readiness."""

from __future__ import annotations

import sys
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Set UTF-8 encoding for Windows console compatibility
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from colorama import Fore, Style, init

init(autoreset=True)


def print_check(name: str, passed: bool, details: str = "") -> None:
    """Print color-coded health check result."""
    # Use ASCII-safe characters for Windows compatibility
    status = f"{Fore.GREEN}[PASS]{Style.RESET_ALL}" if passed else f"{Fore.RED}[FAIL]{Style.RESET_ALL}"
    print(f"{status} {name}")
    if details:
        print(f"     {details}")


def generate_health_report(results: List[Dict[str, Any]], overall_passed: bool) -> None:
    """Persist a Markdown report summarizing health check results."""
    report_path = Path("cursor_development_reports") / "HEALTH_CHECK_REPORT.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).isoformat()
    status_label = "PASS" if overall_passed else "FAIL"

    lines = [
        "# Health Check Report",
        "",
        f"- Generated: {timestamp}",
        f"- Overall Status: **{status_label}**",
        "",
        "## Check Results",
    ]

    for result in results:
        status_icon = "✅" if result["passed"] else "❌"
        lines.append(f"- {status_icon} **{result['name']}** — {result.get('details', 'No details provided.')}")

    lines.append("")
    lines.append("## Recommendations")
    if overall_passed:
        lines.append("- All systems operational. Continue standard monitoring cadence.")
    else:
        remediation = [
            "- Investigate failing checks immediately.",
            "- Review immutable logs for anomalies.",
            "- Confirm owner gate configuration matches deployment requirements.",
        ]
        lines.extend(remediation)

    report_path.write_text("\n".join(lines), encoding="utf-8")


def _run_memory_integrity_check(results: List[Dict[str, Any]]) -> bool:
    try:
        from memory_systems.business_memory.memory.semantic import validate_memory_integrity

        passed = validate_memory_integrity()
        detail = "Semantic memory integrity verified." if passed else "Detected semantic memory inconsistencies."
        results.append({"name": "Memory Integrity", "passed": passed, "details": detail})
        print_check("Memory Integrity", passed, detail)
        return passed
    except Exception as exc:
        detail = f"Error: {exc}"
        results.append({"name": "Memory Integrity", "passed": False, "details": detail})
        print_check("Memory Integrity", False, detail)
        return False


def _run_model_availability_check(results: List[Dict[str, Any]]) -> bool:
    try:
        from config_settings.config import get_settings

        settings = get_settings()
        active_models = len(settings.active_models)
        passed = active_models >= 5
        detail = f"{active_models} models active."
        results.append({"name": "Model Availability", "passed": passed, "details": detail})
        print_check("Model Availability", passed, detail)
        return passed
    except Exception as exc:
        detail = f"Error: {exc}"
        results.append({"name": "Model Availability", "passed": False, "details": detail})
        print_check("Model Availability", False, detail)
        return False


def _run_log_chain_check(results: List[Dict[str, Any]]) -> bool:
    try:
        from utilities.logger import validate_log_chain

        passed = validate_log_chain()
        detail = "Immutable log chain validated."
        results.append({"name": "Log Chain Integrity", "passed": passed, "details": detail})
        print_check("Log Chain Integrity", passed, detail)
        return passed
    except Exception as exc:
        detail = f"Error: {str(exc)}"
        results.append({"name": "Log Chain Integrity", "passed": False, "details": detail})
        print_check("Log Chain Integrity", False, detail)
        import traceback
        print(f"     Full traceback: {traceback.format_exc()}")
        return False


def _run_owner_gate_check(results: List[Dict[str, Any]]) -> bool:
    try:
        from owner_control.owner_gate.authorization import is_owner_gate_enabled

        passed = is_owner_gate_enabled()
        detail = "Owner gate enabled." if passed else "Owner gate disabled."
        results.append({"name": "Owner Gate Enabled", "passed": passed, "details": detail})
        print_check("Owner Gate Enabled", passed, detail)
        return passed
    except Exception as exc:
        detail = f"Error: {exc}"
        results.append({"name": "Owner Gate Enabled", "passed": False, "details": detail})
        print_check("Owner Gate Enabled", False, detail)
        return False


def _run_constitutional_check(results: List[Dict[str, Any]]) -> bool:
    try:
        from constitutional_layer_immutable.constitution import validate_constitutional_compliance

        validation = validate_constitutional_compliance()
        passed = validation.is_compliant
        detail = (
            "Constitutional compliance confirmed."
            if passed
            else f"Violations detected: {validation.violated_rules}"
        )
        results.append({"name": "Constitutional Compliance", "passed": passed, "details": detail})
        print_check("Constitutional Compliance", passed, detail)
        return passed
    except Exception as exc:
        detail = f"Error: {exc}"
        results.append({"name": "Constitutional Compliance", "passed": False, "details": detail})
        print_check("Constitutional Compliance", False, detail)
        return False


def run_health_checks() -> bool:
    """Run all health checks and generate report."""
    print("\n" + "=" * 60)
    print("AI BUSINESS HEALTH CHECK")
    print("=" * 60 + "\n")

    results: List[Dict[str, Any]] = []
    all_passed = True

    checks = [
        _run_memory_integrity_check,
        _run_model_availability_check,
        _run_log_chain_check,
        _run_owner_gate_check,
        _run_constitutional_check,
    ]

    for check in checks:
        passed = check(results)
        all_passed = all_passed and passed

    print("\n" + "=" * 60)
    if all_passed:
        print(f"{Fore.GREEN}[PASS] ALL CHECKS PASSED{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}[FAIL] SOME CHECKS FAILED{Style.RESET_ALL}")
    print("=" * 60 + "\n")

    generate_health_report(results, all_passed)
    return all_passed


if __name__ == "__main__":
    import sys

    success = run_health_checks()
    sys.exit(0 if success else 1)


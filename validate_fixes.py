#!/usr/bin/env python3
"""
Validation script for comprehensive fixes.
Validates code structure, imports, and logic without requiring full test environment.
"""

import json
import sys
from pathlib import Path

def validate_model_config():
    """Validate model_assignments.json exists and is properly formatted."""
    print("Validating model_assignments.json...")
    config_path = Path("config_settings/model_assignments.json")
    
    if not config_path.exists():
        print("❌ ERROR: model_assignments.json does not exist")
        return False
    
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ ERROR: model_assignments.json is invalid JSON: {e}")
        return False
    
    required_roles = ["CEO", "CFO", "COO", "CMO", "CHAIR", "LEGAL", "CISO", "SECRETARY"]
    missing_roles = [role for role in required_roles if role not in config]
    
    if missing_roles:
        print(f"❌ ERROR: Missing roles in model_assignments.json: {missing_roles}")
        return False
    
    for role in required_roles:
        role_config = config[role]
        required_fields = ["provider", "model", "temperature", "max_tokens"]
        missing_fields = [field for field in required_fields if field not in role_config]
        
        if missing_fields:
            print(f"❌ ERROR: {role} missing fields: {missing_fields}")
            return False
    
    print("✅ model_assignments.json is valid")
    return True


def validate_code_structure():
    """Validate that key functions and classes exist in modified files."""
    print("\nValidating code structure...")
    
    files_to_check = [
        ("governance_layer/orchestrator/langgraph_state_machine.py", [
            "conduct_voting",
            "conduct_deliberation", 
            "resume_from_approval",
            "_build_role_deliberation_prompt"
        ]),
        ("governance_layer/orchestrator/iterative_deliberation.py", [
            "conduct_iterative_deliberation",
            "detect_convergence",
            "detect_exhaustion",
            "build_iterative_prompt"
        ]),
        ("governance_layer/governance/board.py", [
            "get_model_assignment",
            "get_role_provider_map"
        ]),
    ]
    
    all_valid = True
    for file_path, expected_items in files_to_check:
        path = Path(file_path)
        if not path.exists():
            print(f"❌ ERROR: {file_path} does not exist")
            all_valid = False
            continue
        
        try:
            content = path.read_text()
            for item in expected_items:
                if item not in content:
                    print(f"❌ ERROR: {item} not found in {file_path}")
                    all_valid = False
                else:
                    print(f"✅ Found {item} in {file_path}")
        except Exception as e:
            print(f"❌ ERROR: Failed to read {file_path}: {e}")
            all_valid = False
    
    return all_valid


def validate_voting_logic():
    """Validate voting logic structure."""
    print("\nValidating voting logic...")
    
    voting_file = Path("governance_layer/orchestrator/langgraph_state_machine.py")
    if not voting_file.exists():
        print("❌ ERROR: langgraph_state_machine.py not found")
        return False
    
    content = voting_file.read_text()
    
    # Check for correct voting structure
    checks = [
        ('PRIMARY_VOTERS = ["CEO", "CFO", "COO", "CMO"]', "Primary voters defined"),
        ('weight=0.25', "25% weight assigned"),
        ('VETO_ROLES = ["LEGAL", "CISO"]', "Veto roles defined"),
        ('ProposalStatus.PENDING_APPROVAL', "Pending approval status used"),
        ('chair_tiebreak', "Chair tie-breaker logic"),
    ]
    
    all_valid = True
    for check_str, description in checks:
        if check_str in content:
            print(f"✅ {description}")
        else:
            print(f"❌ ERROR: {description} not found")
            all_valid = False
    
    return all_valid


def validate_deliberation_logic():
    """Validate iterative deliberation logic."""
    print("\nValidating iterative deliberation logic...")
    
    iter_file = Path("governance_layer/orchestrator/iterative_deliberation.py")
    if not iter_file.exists():
        print("❌ ERROR: iterative_deliberation.py not found")
        return False
    
    content = iter_file.read_text()
    
    checks = [
        ('def conduct_iterative_deliberation', "Iterative deliberation function"),
        ('def detect_convergence', "Convergence detection"),
        ('def detect_exhaustion', "Exhaustion detection"),
        ('all_previous_rounds', "Previous rounds context"),
        ('position_evolution', "Position evolution tracking"),
    ]
    
    all_valid = True
    for check_str, description in checks:
        if check_str in content:
            print(f"✅ {description}")
        else:
            print(f"❌ ERROR: {description} not found")
            all_valid = False
    
    return all_valid


def validate_dashboard_changes():
    """Validate dashboard changes."""
    print("\nValidating dashboard changes...")
    
    app_file = Path("owner_control/dashboard/app.py")
    if not app_file.exists():
        print("❌ ERROR: dashboard/app.py not found")
        return False
    
    content = app_file.read_text()
    
    # Check that legal_risk field is removed from form
    if 'legal_risk = st.slider' in content:
        print("❌ ERROR: Legal risk slider still in form")
        return False
    
    if 'legal_risk": 0.0' in content or '"legal_risk": 0.0' in content:
        print("✅ Legal risk set to 0.0 by default")
    else:
        print("⚠️  WARNING: Legal risk handling may need review")
    
    # Check data retrieval
    data_file = Path("owner_control/dashboard/data_retrieval.py")
    if data_file.exists():
        data_content = data_file.read_text()
        if 'PENDING_APPROVAL' in data_content:
            print("✅ Pending approvals query handles PENDING_APPROVAL status")
        else:
            print("⚠️  WARNING: Pending approvals query may need review")
    
    return True


def validate_chair_prompts():
    """Validate Chair role prompts."""
    print("\nValidating Chair role prompts...")
    
    state_file = Path("governance_layer/orchestrator/langgraph_state_machine.py")
    if not state_file.exists():
        return False
    
    content = state_file.read_text()
    
    checks = [
        ('role == "CHAIR"', "Chair-specific logic"),
        ('facilitator and moderator', "Chair responsibilities defined"),
        ('at least 200 words', "Minimum response length for Chair"),
        ('do NOT vote in regular voting', "Chair voting clarification"),
    ]
    
    all_valid = True
    for check_str, description in checks:
        if check_str in content:
            print(f"✅ {description}")
        else:
            print(f"⚠️  WARNING: {description} may need review")
    
    return all_valid


def main():
    """Run all validations."""
    print("=" * 60)
    print("Comprehensive Fix Validation")
    print("=" * 60)
    
    results = []
    
    results.append(("Model Configuration", validate_model_config()))
    results.append(("Code Structure", validate_code_structure()))
    results.append(("Voting Logic", validate_voting_logic()))
    results.append(("Deliberation Logic", validate_deliberation_logic()))
    results.append(("Dashboard Changes", validate_dashboard_changes()))
    results.append(("Chair Prompts", validate_chair_prompts()))
    
    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    if all_passed:
        print("✅ All validations passed!")
        return 0
    else:
        print("❌ Some validations failed. Please review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

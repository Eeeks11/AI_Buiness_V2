# Test Execution Guide

This guide provides instructions for running the comprehensive tests for all 6 critical scenarios.

## Prerequisites

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure all environment variables are set (API keys for LLM providers)

3. Verify model health:
```bash
python scripts/health_check.py
```

## Running Tests

### Option 1: Run All Comprehensive Tests

```bash
cd /workspace
pytest tests_ci_cd/tests/test_comprehensive_fixes.py -v
```

### Option 2: Run Individual Test Scenarios

#### Test 1: Complete Approval Workflow
```bash
pytest tests_ci_cd/tests/test_comprehensive_fixes.py::TestApprovalWorkflow -v
```

#### Test 2: Owner Rejection Flow
```bash
pytest tests_ci_cd/tests/test_comprehensive_fixes.py::TestOwnerRejection -v
```

#### Test 3: Iterative Deliberation Quality
```bash
pytest tests_ci_cd/tests/test_comprehensive_fixes.py::TestIterativeDeliberation -v
```

#### Test 4: Chair Functionality
```bash
pytest tests_ci_cd/tests/test_comprehensive_fixes.py::TestChairFunctionality -v
```

#### Test 5: Veto Powers
```bash
pytest tests_ci_cd/tests/test_comprehensive_fixes.py::TestVetoPowers -v
```

#### Test 6: Model Configuration
```bash
pytest tests_ci_cd/tests/test_comprehensive_fixes.py::TestModelConfiguration -v
```

### Option 3: Run Validation Script (No Dependencies Required)

```bash
python3 validate_fixes.py
```

This validates:
- Model configuration file structure
- Code structure and imports
- Voting logic implementation
- Deliberation logic implementation
- Dashboard changes
- Chair prompt updates

## Manual Testing Checklist

If automated tests cannot run, use this manual checklist:

### Test 1: Complete Approval Workflow
- [ ] Create a new proposal via dashboard
- [ ] Verify it progresses through IDEATION → DELIBERATION → VOTING
- [ ] Verify status becomes "pending_approval" after board vote
- [ ] Verify proposal appears in "Pending Approvals" tab
- [ ] Click "Approve & Sign"
- [ ] Verify status changes to "approved" then "executed"
- [ ] Verify all transitions logged in audit trail

### Test 2: Owner Rejection Flow
- [ ] Create a proposal and let it reach pending_approval
- [ ] Click "Reject" button
- [ ] Verify status changes to "rejected"
- [ ] Verify execution does NOT occur
- [ ] Verify rejection logged in audit trail

### Test 3: Iterative Deliberation Quality
- [ ] Create a debatable proposal
- [ ] Monitor deliberation phase
- [ ] Verify Round 1: All 8 roles provide initial analysis
- [ ] Verify Round 2: Members reference Round 1 inputs
- [ ] Verify at least one member changes position
- [ ] Verify dashboard shows all rounds with position evolution

### Test 4: Chair Functionality
- [ ] Verify Chair provides non-empty responses in deliberation
- [ ] Verify Chair's responses are substantial (>100 chars)
- [ ] Create proposal that results in 2-2 voting tie
- [ ] Verify Chair is asked to cast tie-breaking vote
- [ ] Verify Chair's vote determines outcome

### Test 5: Veto Powers
- [ ] Create proposal with constitutional violation
- [ ] Verify Legal identifies violation during deliberation
- [ ] Verify Legal exercises veto
- [ ] Verify proposal status becomes "vetoed"
- [ ] Verify proposal does NOT proceed to owner approval

### Test 6: Model Configuration
- [ ] Edit config_settings/model_assignments.json
- [ ] Change one role's model
- [ ] Change one role's temperature
- [ ] Create new proposal
- [ ] Verify system uses new model assignments
- [ ] Verify temperature settings are applied

## Expected Test Results

All tests should pass with the following expected outcomes:

1. **Approval Workflow**: ✅ Status transitions correctly, proposals appear in Pending Approvals
2. **Owner Rejection**: ✅ Rejection stops workflow, status set to rejected
3. **Iterative Deliberation**: ✅ Multiple rounds execute, members reference each other
4. **Chair Functionality**: ✅ Chair provides substantial responses, tie-breaking works
5. **Veto Powers**: ✅ Legal/CISO vetoes block proposals correctly
6. **Model Configuration**: ✅ JSON file works, models can be changed easily

## Troubleshooting

### Tests Fail Due to Missing Dependencies
- Install requirements: `pip install -r requirements.txt`
- Verify Python version: `python3 --version` (should be 3.8+)

### Tests Fail Due to API Keys
- Set environment variables for LLM providers
- Check `.env` file has all required keys

### Tests Fail Due to Model Health
- Run health check: `python scripts/health_check.py`
- Ensure at least 5 models are healthy (Rule 8)

### Import Errors
- Verify PYTHONPATH includes project root
- Check all files are in correct locations
- Verify no circular imports

## Validation Results

The validation script (`validate_fixes.py`) has been run and all checks pass:

✅ Model Configuration - PASS
✅ Code Structure - PASS  
✅ Voting Logic - PASS
✅ Deliberation Logic - PASS
✅ Dashboard Changes - PASS
✅ Chair Prompts - PASS

All Python files compile without syntax errors.

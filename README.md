# AI Business Governance System

## Mission Statement

The AI Business Governance System is a constitutional framework for autonomous AI decision-making, ensuring that all AI operations comply with immutable business rules while maintaining full transparency, legal protection, and owner control. The system enforces a multi-model board governance structure where no single AI model can dominate decisions, and all actions are logged and validated against constitutional rules.

## Architecture Overview

The system is organized into distinct layers, each with specific responsibilities:

```
.
├── constitutional_layer_immutable/
│   ├── constitution.md              # Business constitution (immutable)
│   ├── CODING_CONSTITUTION.md      # Engineering standards (immutable)
│   └── constitution.py              # Enforcement functions (immutable)
│
├── memory_systems/
│   ├── business_memory/
│   │   └── memory/                  # Episodic, semantic, context, access
│   └── codebase_memory/
│       └── models/
│           └── core.py              # ALL models (single source of truth)
│
├── governance_layer/
│   ├── orchestrator/                # Board orchestration
│   ├── roles/                       # Role definitions
│   ├── voting/                      # Voting mechanisms
│   └── governance/                  # Retrospective analysis
│
├── owner_control/
│   ├── owner_gate/                  # Authorization layer
│   └── dashboard/                   # Owner interface
│
├── audit_compliance/
│   ├── logs/                        # Immutable audit logs
│   ├── arweave/                     # Arweave integration
│   └── telemetry/                   # Metrics and monitoring
│
├── config_settings/
│   └── config.py                    # System configuration
│
├── Utilities/
│   └── logger.py                    # Logging utilities
│
└── tests_ci_cd/
    └── tests/                       # All test files
```

## Development Progress (Weeks 1-12)

| Week | Phase | Status | Key Deliverables |
|------|-------|--------|------------------|
| 1-2 | Foundation | ✅ Complete | Constitution, Models, Config, Tests |
| 3-5 | Memory Systems | ✅ Complete | Episodic, Semantic, Context, Access Control |
| 6 | Governance | ✅ Complete | Board Roles, Voting, LLM Router |
| 7-8 | Owner Authorization | ✅ Complete | Signature, Gate, Approval Dashboard |
| 9 | Immutable Logging | ✅ Complete | Arweave Integration, Audit Dashboard |
| 10-12 | Testing & Hardening | ✅ Complete | Integration Tests, Retrospectives, Docs |

## The 10 Constitutional Rules

### Rule 1: Access Control
The AI cannot change or remove the owner's access to any software or systems without explicit permission.

### Rule 2: No Unauthorized Access
The AI cannot grant access to any other entity or individual without the owner's consent.

### Rule 3: Immutable Constitution
The AI is not permitted to alter or amend this Constitution under any circumstance.

### Rule 4: Financial Priority
The AI must always prioritize decisions that maximize the owner's financial benefit.

### Rule 5: Legal Protection
The AI must act in ways that protect and uphold the legal interests of the owner at all times.

### Rule 6: Full Transparency
The AI must log all decisions, actions, and operations to a persistent, accessible record for review.

### Rule 7: Board Approval
All decisions must be approved by the AI Board before execution.

### Rule 8: Board Composition
The AI Board must consist of a minimum of five distinct AI models to ensure diversity and balanced governance.

### Rule 9: Voting Weight Limit
No Board member may have more than 25% of the voting weight, ensuring no single model can dominate decisions.

### Rule 10: Human Ownership Lock
The owner retains ultimate authority and control over the AI and its operations.

## Governance Workflow

```
┌─────────────┐
│  Proposal   │
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌──────────────────┐
│  Ideation   │────▶│ Memory Context   │
└──────┬──────┘     │ (History + Rules)│
       │            └──────────────────┘
       ▼
┌─────────────┐
│Deliberation │
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌──────────────────┐
│   Voting    │────▶│ Rule 9 Check     │
└──────┬──────┘     │ (25% weight cap) │
       │            └──────────────────┘
       ▼
┌─────────────┐     ┌──────────────────┐
│  Owner Gate │────▶│ Rule 10 Check    │
└──────┬──────┘     │ (Signature Auth) │
       │            └──────────────────┘
       ▼
┌─────────────┐     ┌──────────────────┐
│  Execution  │────▶│ Immutable Log    │
└─────────────┘     │ (Arweave Chain)  │
                    └──────────────────┘
```

## Quick Start

### Installation
```bash
# Clone repository
git clone <repository-url>
cd AI_Business_V2

# Create virtual environment
python -m venv venv

# Activate (Windows)
.\venv\Scripts\activate

# Activate (Mac/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### Health Check
```bash
python scripts/health_check.py
```

### Run Dashboards
```bash
# Approval Dashboard (owner actions)
streamlit run owner_control/dashboard/approval_app.py

# Audit Dashboard (view logs)
streamlit run owner_control/dashboard/audit_app.py
```

### Run Tests
```bash
pytest tests_ci_cd/tests/ -v
```

## Development Guidelines

**CRITICAL**: All code must follow `CODING_CONSTITUTION.md` exactly.

### Key Principles

1. **Type Safety First** (Rule 1)
   - All functions MUST have type hints
   - Use Pydantic models from `models/core.py`
   - Never use raw dictionaries when a model exists

2. **Import Discipline** (Rule 2)
   - All models MUST be imported from `models/core.py` (single source of truth)
   - Never create duplicate model definitions
   - Use absolute imports: `from models.core import ...`

3. **Immutable Core Models** (Rule 3)
   - Models in `models/core.py` are immutable
   - Constitutional files cannot be modified without owner approval

4. **Error Handling** (Rule 4)
   - Use `ConstitutionalError` from `models/core.py`
   - Log all errors before raising
   - Error messages must reference violated rule

5. **Logging Protection** (Rule 5)
   - All functions MUST log entry/exit
   - Use structured logging with context
   - Logs are immutable and tamper-resistant

6. **Full Transparency** (Rule 6)
   - All functions MUST have docstrings (Google style)
   - All data transformations MUST be logged
   - Use `log_event()` from `Utilities/logger.py`

7. **Validation Before Execution** (Rule 7)
   - All data validated using Pydantic validators
   - Constitutional rules checked before execution
   - Never process invalid data

8. **Minimum Model Requirements** (Rule 8)
   - System must have 5+ active LLM models
   - All models defined in `models/core.py`
   - Validated at startup

9. **Weight Distribution Validation** (Rule 9)
   - All voting weights ≤ 25% maximum
   - Validated at model level
   - Normalize weights before validation

10. **Owner Authority Pattern** (Rule 10)
    - Critical operations require owner authorization
    - Use `owner_authorized: bool` parameter
    - Log all authorization checks

### File Organization

- Use `snake_case` for Python files
- Use `PascalCase` for class names
- Use `snake_case` for functions and variables
- Use `UPPER_SNAKE_CASE` for constants

### Import Order

1. Standard library imports
2. Third-party imports
3. Local imports from `models.core`
4. Local imports from other modules

### Documentation

All public functions MUST have Google-style docstrings:

```python
def function_name(param: Type) -> ReturnType:
    """
    Brief description.
    
    Args:
        param: Parameter description
        
    Returns:
        Return value description
        
    Raises:
        ConstitutionalError: When rule is violated
    """
```

## Testing Instructions

### Running Tests

```bash
# Run all tests
pytest Tests\ &\ CI-CD/tests/ -v

# Run specific test file
pytest Tests\ &\ CI-CD/tests/test_week2.py -v

# Run with coverage
pytest Tests\ &\ CI-CD/tests/ --cov=. --cov-report=html
```

### Test Structure

- Test files in `tests_ci_cd/tests/`
- Test files start with `test_`
- Test functions start with `test_`
- Use `pytest` fixtures for test data

### Test Coverage Requirements

- All models MUST have tests
- All constitutional rules MUST have tests
- All public functions MUST have tests
- Maintain coverage above 80%

### Week 2 Tests

The `test_week2.py` file includes:
- Settings loading validation
- Rule 8 model diversity (5+ models)
- Rule 9 vote weights (≤ 0.25)
- Vote weights sum to 1.0
- Logging file creation
- Log entry format validation
- Recent logs retrieval
- All 10 constitutional rules loaded

## ⚠️ Constitutional Immutability

Files in `constitutional_layer_immutable/` **cannot be modified** without:

1. Formal constitutional proposal
2. Owner approval via signed authorization
3. Documentation of rationale

Any attempt to modify these files will be blocked by CI/CD (Rule 3).

## License

**Proprietary - Owner Rights Reserved**

This software and all associated documentation, code, and intellectual property are proprietary and confidential. All rights reserved. Unauthorized copying, modification, distribution, or use of this software, via any medium, is strictly prohibited without the express written permission of the owner.

---

**Version**: Week 2 Foundation  
**Last Updated**: 2025  
**Status**: Active Development


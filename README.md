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

## Setup Instructions

### Prerequisites

- Python 3.10 or higher
- pip package manager

### Installation

1. **Clone the repository** (if applicable):
   ```bash
   git clone <repository-url>
   cd "AI Business V2"
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   
   # On Windows:
   venv\Scripts\activate
   
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys and configuration
   ```

5. **Verify installation**:
   ```bash
   pytest Tests\ &\ CI-CD/tests/ -v
   ```

### Configuration

The system requires the following environment variables (see `.env.example` for template):

- **LLM API Keys** (Rule 8: Minimum 5 required):
  - `OPENAI_API_KEY`
  - `ANTHROPIC_API_KEY`
  - `GOOGLE_API_KEY`
  - `XAI_API_KEY`
  - `MISTRAL_API_KEY`

- **Owner Authentication** (Rule 10):
  - `OWNER_ID`
  - `OWNER_SIGNATURE_KEY`

- **System Configuration**:
  - `DEBUG` (default: `false`)
  - `LOG_LEVEL` (default: `INFO`)
  - `ARWEAVE_ENABLED` (default: `false`)

- **Database** (for future use):
  - `DATABASE_URL` (default: `sqlite:///./ai_business.db`)

### Running the System

Start the FastAPI application:

```bash
python main.py
```

The system will:
1. Load and validate constitutional rules
2. Verify active models (must be 5+ for Rule 8)
3. Validate vote weights (all ≤ 0.25 for Rule 9)
4. Log system startup event
5. Start the API server on `http://localhost:8000`

**Health Check**:
- `GET /` - System status
- `GET /health` - Health check endpoint

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

## License

**Proprietary - Owner Rights Reserved**

This software and all associated documentation, code, and intellectual property are proprietary and confidential. All rights reserved. Unauthorized copying, modification, distribution, or use of this software, via any medium, is strictly prohibited without the express written permission of the owner.

---

**Version**: Week 2 Foundation  
**Last Updated**: 2025  
**Status**: Active Development


# CODING CONSTITUTION — IMMUTABLE

This document defines the engineering standards and mandatory patterns for all code in the AI Business governance system. These rules are IMMUTABLE once established and must be followed by all AI-generated code.

## The 10 Coding Rules

### Rule 1: Type Safety First
**Inspired by Business Rule 1 (Access Control)**
- All functions MUST have type hints for parameters and return values
- Use Pydantic models from `models/core.py` for all data structures
- Never use raw dictionaries when a model exists
- Type checking must pass with `mypy --strict` or equivalent

**Mandatory Pattern:**
```python
from models.core import Proposal, Vote
from typing import Optional

def process_proposal(proposal: Proposal) -> Optional[Vote]:
    """Function with complete type hints."""
    ...
```

### Rule 2: Import Discipline
**Inspired by Business Rule 2 (No Unauthorized Access)**
- All data models MUST be imported from `models/core.py` (single source of truth)
- Never create duplicate model definitions
- Never import from other modules when a model exists in `models/core.py`
- Use absolute imports: `from models.core import ...`

**Mandatory Pattern:**
```python
# ✅ CORRECT
from models.core import Vote, Proposal, BoardSession

# ❌ WRONG
from typing import TypedDict
class Vote(TypedDict):  # Duplicate definition
    ...
```

### Rule 3: Immutable Core Models
**Inspired by Business Rule 3 (Immutable Constitution)**
- Models in `models/core.py` are the single source of truth and MUST NOT be duplicated
- All Pydantic models MUST use `frozen=True` or `allow_mutation=False` where appropriate
- Constitutional enforcement functions in `constitution.py` are immutable
- Never modify `models/core.py` without architectural review

**Mandatory Pattern:**
```python
from pydantic import BaseModel

class Vote(BaseModel):
    """Immutable vote model."""
    model_config = {"frozen": True}  # Prevents mutation
    ...
```

### Rule 4: Error Handling Priority
**Inspired by Business Rule 4 (Financial Priority)**
- All errors MUST use custom exception classes from `models/core.py`
- Never use generic `Exception` or `ValueError` for constitutional violations
- Error messages MUST be descriptive and reference the violated rule
- Log all errors before raising

**Mandatory Pattern:**
```python
from models.core import ConstitutionalError
import logging

logger = logging.getLogger(__name__)

def enforce_rule(proposal: Proposal) -> None:
    if violates_rule(proposal):
        logger.error(f"Constitutional violation: {proposal.id}")
        raise ConstitutionalError("Rule X Violation: ...")
```

### Rule 5: Logging Protection
**Inspired by Business Rule 5 (Legal Protection)**
- All functions MUST log their entry and exit (or errors)
- Use structured logging with context (proposal IDs, session IDs, etc.)
- Logs MUST be immutable and tamper-resistant
- All decisions, actions, and operations MUST be logged (Rule 6 compliance)

**Mandatory Pattern:**
```python
import logging
from models.core import Proposal

logger = logging.getLogger(__name__)

def process_proposal(proposal: Proposal) -> None:
    logger.info(f"Processing proposal {proposal.id}", extra={
        "proposal_id": proposal.id,
        "session_id": proposal.session_id
    })
    try:
        # ... processing ...
        logger.info(f"Proposal {proposal.id} processed successfully")
    except Exception as e:
        logger.error(f"Error processing proposal {proposal.id}: {e}", exc_info=True)
        raise
```

### Rule 6: Full Transparency
**Inspired by Business Rule 6 (Full Transparency)**
- All functions MUST have docstrings with Args, Returns, and Raises
- All public APIs MUST be documented
- All data transformations MUST be logged
- Code MUST be self-documenting with clear variable names

**Mandatory Pattern:**
```python
def calculate_vote_weights(votes: list[Vote]) -> dict[str, float]:
    """
    Calculate normalized voting weights for board members.
    
    Args:
        votes: List of Vote objects from board members
    
    Returns:
        Dictionary mapping member IDs to normalized weights (0.0-1.0)
    
    Raises:
        ConstitutionalError: If any weight exceeds 25% (Rule 9 violation)
    """
    ...
```

### Rule 7: Validation Before Execution
**Inspired by Business Rule 7 (Board Approval)**
- All data MUST be validated using Pydantic validators before processing
- Constitutional rules MUST be checked before any action execution
- Use `@field_validator` and `@model_validator` from Pydantic
- Never process invalid data

**Mandatory Pattern:**
```python
from pydantic import BaseModel, field_validator, model_validator
from models.core import ConstitutionalError

class Vote(BaseModel):
    weight: float
    
    @field_validator('weight')
    @classmethod
    def validate_weight(cls, v: float) -> float:
        if v > 0.25:
            raise ConstitutionalError("Rule 9 Violation: Weight exceeds 25%")
        return v
```

### Rule 8: Minimum Model Requirements
**Inspired by Business Rule 8 (Board Composition)**
- All core models MUST be defined in `models/core.py`
- Never create models in other modules
- Models MUST have validators for constitutional compliance
- At minimum, these models MUST exist: `Vote`, `VoteResult`, `Proposal`, `BoardSession`

**Mandatory Pattern:**
```python
# ✅ CORRECT - All models in models/core.py
from models.core import Vote, Proposal, BoardSession

# ❌ WRONG - Models scattered across files
# proposal.py
class Proposal: ...
# vote.py  
class Vote: ...
```

### Rule 9: Weight Distribution Validation
**Inspired by Business Rule 9 (Voting Weight Limit)**
- All voting weight calculations MUST enforce the 25% maximum
- Weight validation MUST happen at the model level using Pydantic validators
- Normalize weights before validation
- Raise `ConstitutionalError` on violation

**Mandatory Pattern:**
```python
from pydantic import BaseModel, model_validator
from models.core import ConstitutionalError

class VoteResult(BaseModel):
    votes: dict[str, float]
    
    @model_validator(mode='after')
    def validate_weights(self) -> 'VoteResult':
        total = sum(self.votes.values())
        if total > 0:
            normalized = {k: v/total for k, v in self.votes.items()}
            max_weight = max(normalized.values())
            if max_weight > 0.25:
                raise ConstitutionalError(
                    f"Rule 9 Violation: Max weight {max_weight*100:.2f}% exceeds 25%"
                )
        return self
```

### Rule 10: Owner Authority Pattern
**Inspired by Business Rule 10 (Human Ownership Lock)**
- All critical operations MUST require explicit owner authorization
- Use `owner_authorized: bool` parameter for critical functions
- Owner authorization MUST be checked before execution
- Log all authorization checks

**Mandatory Pattern:**
```python
from models.core import Proposal, ConstitutionalError
import logging

logger = logging.getLogger(__name__)

def execute_critical_action(proposal: Proposal, owner_authorized: bool) -> None:
    """Execute critical action requiring owner authorization."""
    if not owner_authorized:
        logger.warning(f"Critical action blocked: {proposal.id}")
        raise ConstitutionalError(
            "Rule 10 Violation: Critical operations require owner authorization"
        )
    logger.info(f"Executing critical action: {proposal.id}")
    # ... execution ...
```

## File Organization Standards

### Directory Structure
```
.
├── constitutional_layer_immutable/
│   ├── constitution.md
│   ├── CODING_CONSTITUTION.md  # This file (immutable)
│   ├── constitution.py          # Constitutional enforcement (immutable)
│   └── .cursorrules             # Cursor AI instructions
├── memory_systems/
│   └── codebase_memory/
│       └── models/
│           └── core.py          # Single source of truth for all data models
└── tests_ci_cd/
    └── tests/
        ├── test_constitution.py
        └── test_architectural_consistency.py
```

### Import Hierarchy
1. Standard library imports
2. Third-party imports (Pydantic, etc.)
3. Local imports from `models.core`
4. Local imports from `constitution`

**Example:**
```python
# Standard library
import logging
from typing import Optional
from datetime import datetime

# Third-party
from pydantic import BaseModel, field_validator

# Local - models first (single source of truth)
from models.core import Vote, Proposal, ConstitutionalError

# Local - enforcement
from constitution import enforce_rule_9
```

## Error Handling Standards

### Custom Exceptions
All custom exceptions MUST be defined in `models/core.py`:

```python
class ConstitutionalError(Exception):
    """Raised when a constitutional rule is violated."""
    pass

class ValidationError(Exception):
    """Raised when data validation fails."""
    pass
```

### Error Logging
- Log errors with full context (proposal ID, session ID, etc.)
- Include stack traces for debugging
- Never silently catch and ignore errors

## Naming Conventions

### File Naming
- Use `snake_case` for all Python files: `proposal_handler.py`, `vote_processor.py`
- Use `PascalCase` for class names: `ProposalHandler`, `VoteProcessor`
- Use `snake_case` for function and variable names: `process_proposal()`, `calculate_weights()`
- Use `UPPER_SNAKE_CASE` for constants: `MAX_VOTING_WEIGHT = 0.25`
- Use descriptive names that indicate purpose: `validate_constitutional_compliance()` not `validate()`

### Model Naming
- All Pydantic models MUST use `PascalCase`: `Vote`, `Proposal`, `BoardSession`
- Enum classes MUST use `PascalCase` with descriptive names: `VoteType`, `RoleType`, `ConstitutionalRule`
- Enum values MUST use `UPPER_SNAKE_CASE`: `APPROVE`, `REJECT`, `RULE_1_ACCESS_CONTROL`

### Function Naming
- Use verb-noun pattern: `validate_proposal()`, `calculate_weights()`, `enforce_rule_9()`
- Boolean functions MUST start with `is_`, `has_`, or `can_`: `is_compliant()`, `has_permission()`
- Private functions (module-internal) MUST start with `_`: `_internal_helper()`

## Type System Requirements

### Mandatory Type Hints
- **ALL** function parameters MUST have type hints
- **ALL** function return values MUST have type hints
- **ALL** class attributes MUST have type hints
- Use `Optional[Type]` or `Type | None` for nullable values (Python 3.10+)
- Use `list[Type]` or `dict[str, Type]` for collections (Python 3.9+)
- Use `Literal` for fixed string/enum values

### Type Checking Standards
```python
# ✅ CORRECT - Complete type hints
def process_vote(
    vote: Vote,
    session: BoardSession,
    context: dict[str, str] | None = None
) -> VoteResult:
    """Process a vote with full type safety."""
    ...

# ❌ WRONG - Missing type hints
def process_vote(vote, session, context=None):
    """Missing type hints."""
    ...
```

### Pydantic Model Requirements
- All models MUST inherit from `BaseModel`
- All fields MUST have `Field()` with description
- Use `Field(..., description="...")` for required fields
- Use `Field(default=..., description="...")` for optional fields
- Use `Field(default_factory=...)` for mutable defaults (lists, dicts)

## Logging Patterns

### Structured Logging Requirements
- Use `logger = logging.getLogger(__name__)` in every module
- Log at appropriate levels:
  - `DEBUG`: Detailed diagnostic information
  - `INFO`: General informational messages (entry/exit, state changes)
  - `WARNING`: Warning messages (non-critical issues)
  - `ERROR`: Error messages (exceptions, violations)
  - `CRITICAL`: Critical errors (system failures)

### Logging Context
- Always include context in logs: proposal IDs, session IDs, user IDs
- Use `extra` parameter for structured logging:
```python
logger.info(
    f"Processing proposal {proposal.id}",
    extra={
        "proposal_id": proposal.id,
        "session_id": session.id,
        "action": "process_proposal"
    }
)
```

### Logging Before Errors
- **ALWAYS** log before raising `ConstitutionalError`
- Include full context and stack trace:
```python
logger.error(
    f"Rule 9 Violation: Member {member_id} exceeds weight limit",
    extra={"member_id": member_id, "weight": weight, "max_weight": 0.25},
    exc_info=True
)
raise ConstitutionalError(...)
```

## File Organization Standards

### Directory Structure (Detailed)
```
constitutional_layer_immutable/
  ├── constitution.md              # Business constitution (immutable)
  ├── CODING_CONSTITUTION.md      # This file (immutable)
  ├── constitution.py              # Enforcement functions (immutable)
  └── .cursorrules                 # Cursor AI instructions

memory_systems/
  ├── business_memory/
  │   └── memory/                  # Episodic, semantic, context, access
  └── codebase_memory/
      └── models/
          ├── __init__.py          # Package exports
          └── core.py              # ALL models (single source of truth)

governance_layer/
  ├── orchestrator/                # Board orchestration
  ├── roles/                       # Role definitions
  ├── voting/                      # Voting mechanisms
  └── governance/                  # Retrospective analysis

owner_control/
  ├── owner_gate/                  # Authorization layer
  └── dashboard/                   # Owner interface

audit_compliance/
  ├── logs/                        # Immutable audit logs
  ├── arweave/                     # Arweave integration
  └── telemetry/                   # Metrics and monitoring

tests_ci_cd/
  ├── tests/                       # All test files
  └── .github/workflows/           # CI/CD pipelines
```

### Module Organization
- One class per file for large classes (>200 lines)
- Related functions can be grouped in modules
- Use `__init__.py` to expose public API
- Keep modules focused on single responsibility

### Import Order (Strict)
1. Standard library imports (alphabetical)
2. Third-party imports (alphabetical)
3. Local imports from `models.core` (alphabetical)
4. Local imports from other modules (alphabetical)

```python
# Standard library
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

# Third-party
from pydantic import BaseModel, Field
import httpx

# Local - models first (single source of truth)
from models.core import (
    ConstitutionalError,
    Proposal,
    Vote,
    VoteResult
)

# Local - other modules
from constitution import enforce_rule_9
```

## Testing Requirements

### Test File Organization
- Test files MUST be in `tests_ci_cd/tests/`
- Test files MUST start with `test_`: `test_constitution.py`, `test_proposals.py`
- Test classes MUST start with `Test`: `class TestRule9:`
- Test functions MUST start with `test_`: `def test_rule_9_weight_limit():`

### Test Coverage Requirements
- All models MUST have tests
- All constitutional rules MUST have tests
- All public functions MUST have tests
- Test coverage MUST be maintained above 80%
- Use `pytest` for all tests
- Use `pytest.fixture` for test data

### Test Patterns
```python
import pytest
from models.core import Vote, ConstitutionalError

class TestVoteWeight:
    """Tests for vote weight validation."""
    
    def test_valid_weight(self):
        """Test that valid weights pass."""
        vote = Vote(
            member_id="member1",
            role=RoleType.CEO,
            vote_type=VoteType.APPROVE,
            weight=0.20  # 20% - valid
        )
        assert vote.weight == 0.20
    
    def test_invalid_weight_exceeds_limit(self):
        """Test that weights exceeding 25% raise error."""
        with pytest.raises(ConstitutionalError, match="Rule 9 Violation"):
            Vote(
                member_id="member1",
                role=RoleType.CEO,
                vote_type=VoteType.APPROVE,
                weight=0.30  # 30% - exceeds limit
            )
```

## Error Handling Standards

### Exception Hierarchy
```python
# Base exception
ConstitutionalError(Exception)
  ├── RuleViolationError(ConstitutionalError)
  └── ValidationError(Exception)
```

### Error Message Format
- MUST reference the violated rule: "Rule X Violation: ..."
- MUST be descriptive and actionable
- MUST include relevant context (IDs, values, thresholds)

```python
# ✅ CORRECT
raise ConstitutionalError(
    f"Rule 9 Violation: Member '{member_id}' has {weight*100:.2f}% weight, "
    f"exceeds 25% maximum limit"
)

# ❌ WRONG
raise ConstitutionalError("Invalid weight")
```

## Documentation Standards

### Docstring Format
All public functions MUST have docstrings in Google style:

```python
def process_proposal(proposal: Proposal, session: BoardSession) -> VoteResult:
    """
    Process a proposal through the board voting system.
    
    This function validates the proposal, calculates voting weights,
    and returns the aggregated vote result. All constitutional rules
    are enforced during processing.
    
    Args:
        proposal: The proposal to process
        session: The board session context
        
    Returns:
        VoteResult with aggregated votes and validation status
        
    Raises:
        ConstitutionalError: If any constitutional rule is violated
        ValidationError: If proposal data is invalid
        
    Example:
        >>> proposal = Proposal(id="prop1", title="New Feature", ...)
        >>> session = BoardSession(id="sess1", members=[...])
        >>> result = process_proposal(proposal, session)
        >>> assert result.is_compliant
    """
    ...
```

### Code Comments
- Use comments to explain **why**, not **what**
- Complex logic MUST have comments
- Constitutional rule references MUST be commented

## Enforcement

### Automated Checks
- `.cursorrules` enforces these patterns during AI code generation
- `test_architectural_consistency.py` catches violations automatically
- GitHub Actions blocks PRs that violate these rules
- `mypy` type checking MUST pass
- `ruff` linting MUST pass

### Manual Review Checklist
Before submitting code, verify:
- [ ] All functions have type hints
- [ ] All functions have docstrings
- [ ] All imports are from `models/core.py`
- [ ] All errors use `ConstitutionalError`
- [ ] All operations are logged
- [ ] All tests pass
- [ ] No duplicate model definitions

## Immutability Enforcement

### Immutable Files (Rule 3)
These files CANNOT be modified without owner approval:
- `constitutional_layer_immutable/constitution.md`
- `constitutional_layer_immutable/CODING_CONSTITUTION.md`
- `constitutional_layer_immutable/constitution.py`

### Immutable Models
Models with `frozen=True` cannot be modified after creation:
- `Vote` (immutable)
- `VoteResult` (immutable)
- `BoardMember` (immutable)
- `ConstitutionalValidation` (mutable during building, then frozen)
- `APIResponse` (immutable)

### Model Mutation Rules
- Use `model_copy(update={...})` for Pydantic v2 to create modified copies
- Never modify frozen models directly
- Log all model modifications

---

**Remember:** These coding rules ensure consistency, maintainability, and constitutional compliance across all AI-generated code. Follow them religiously. Violations will be caught by automated tests and CI/CD pipelines.


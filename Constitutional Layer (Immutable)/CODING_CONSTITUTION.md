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
├── Constitutional Layer (Immutable)/
│   ├── constitution.md
│   ├── CODING_CONSTITUTION.md  # This file (immutable)
│   ├── constitution.py          # Constitutional enforcement (immutable)
│   └── .cursorrules             # Cursor AI instructions
├── Memory Systems/
│   └── Codebase Memory/
│       └── models/
│           └── core.py          # Single source of truth for all data models
└── Tests & CI-CD/
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

## Testing Requirements

- All models MUST have tests in `tests/`
- All constitutional rules MUST have tests
- Architectural consistency MUST be tested in `test_architectural_consistency.py`
- Test coverage MUST be maintained

## Enforcement

- `.cursorrules` enforces these patterns during AI code generation
- `test_architectural_consistency.py` catches violations automatically
- GitHub Actions blocks PRs that violate these rules
- These rules are IMMUTABLE and cannot be modified without owner approval

---

**Remember:** These coding rules ensure consistency, maintainability, and constitutional compliance across all AI-generated code. Follow them religiously.


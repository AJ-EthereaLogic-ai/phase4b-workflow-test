# Issue #2: Implement User Profile Validation Service (TDD)

**Type:** Feature
**Labels:** `feature`, `backend`, `tdd`, `validation`
**Assignee:** ADWS Bot
**Status:** Open

## Description

Implement a comprehensive user profile validation service with full test coverage using Test-Driven Development (TDD). This service will validate user profile data before saving to the database.

## Requirements

### Test-Driven Development Approach
**IMPORTANT:** Generate comprehensive tests FIRST, then implement the code to make tests pass.

### Functional Requirements

1. **ProfileValidator Class** with methods:
   - `validate_username(username: str) -> ValidationResult`
   - `validate_email(email: str) -> ValidationResult`
   - `validate_age(age: int) -> ValidationResult`
   - `validate_bio(bio: str) -> ValidationResult`
   - `validate_profile(profile: UserProfile) -> ValidationResult`

2. **ValidationResult Model**:
   ```python
   class ValidationResult:
       is_valid: bool
       errors: List[str]
       warnings: List[str]
   ```

3. **UserProfile Model**:
   ```python
   class UserProfile:
       username: str
       email: str
       age: int
       bio: Optional[str]
   ```

### Validation Rules

**Username:**
- Must be 3-20 characters long
- Can only contain alphanumeric characters, underscores, and hyphens
- Cannot start or end with underscore or hyphen
- Cannot contain consecutive special characters

**Email:**
- Must be valid email format (RFC 5322 compliant)
- Domain must have at least one dot
- Local part cannot be empty
- Cannot contain consecutive dots

**Age:**
- Must be between 13 and 120 (inclusive)
- Must be an integer
- Warn if age > 100 (unusual but valid)

**Bio:**
- Optional field
- Max 500 characters if provided
- Cannot contain offensive words (use simple word list)
- Warn if bio is empty but profile is otherwise complete

### Test Coverage Requirements

Generate tests for:
1. **Happy path tests** (valid inputs)
2. **Edge case tests** (boundary values: 3 chars, 20 chars, age 13, age 120)
3. **Invalid input tests** (empty strings, special chars, out of range)
4. **Integration tests** (validate_profile with various combinations)
5. **Error message tests** (verify correct error messages)
6. **Warning tests** (verify warnings for unusual but valid inputs)

### File Structure Expected
```
app/server/
└── services/
    ├── __init__.py
    ├── profile_validator.py  # Main implementation
    └── models.py             # Pydantic models

tests/
└── services/
    ├── __init__.py
    └── test_profile_validator.py  # Comprehensive test suite
```

### Test Examples to Generate

```python
# Tests should include (but not limited to):

def test_validate_username_valid():
    """Test that valid usernames pass validation."""
    validator = ProfileValidator()
    result = validator.validate_username("john_doe123")
    assert result.is_valid is True
    assert len(result.errors) == 0

def test_validate_username_too_short():
    """Test that usernames under 3 chars fail."""
    validator = ProfileValidator()
    result = validator.validate_username("ab")
    assert result.is_valid is False
    assert "at least 3 characters" in result.errors[0].lower()

def test_validate_age_boundary_min():
    """Test minimum age boundary (13)."""
    validator = ProfileValidator()
    result = validator.validate_age(13)
    assert result.is_valid is True

def test_validate_age_boundary_max_warning():
    """Test that age 100+ triggers warning."""
    validator = ProfileValidator()
    result = validator.validate_age(101)
    assert result.is_valid is True
    assert len(result.warnings) > 0
    assert "unusual" in result.warnings[0].lower()

# ... many more test cases
```

## Acceptance Criteria
- [ ] Test suite generated FIRST with comprehensive coverage
- [ ] All validation methods implemented
- [ ] All edge cases handled correctly
- [ ] Error messages are clear and helpful
- [ ] Warnings are generated for unusual inputs
- [ ] Code passes ALL generated tests
- [ ] Test coverage is 100%
- [ ] Type hints are complete
- [ ] Docstrings explain expected behavior

## TDD Workflow
1. **Red Phase:** Generate comprehensive test suite that will fail
2. **Green Phase:** Implement code to make all tests pass
3. **Refactor Phase:** (Optional) Improve code quality while keeping tests green

## Additional Context
This service is critical for data quality. The TDD approach ensures we have full test coverage from the start and the validation logic is correct.

**Priority:** High
**Estimated Complexity:** Medium
**Sprint:** Sprint 1
**TDD Required:** YES

# ADWS Workflow Test Issues

This directory contains comprehensive mock GitHub issues designed to test the autonomous completion capabilities of all 4 ADWS workflow types.

## Quick Reference

| File | Issue # | Workflow Type | Description | Complexity | TDD |
|------|---------|---------------|-------------|------------|-----|
| `issue_001_backend_standard.md` | #1 | Backend Standard | User Authentication API Endpoint | Medium | No |
| `issue_002_backend_tdd.md` | #2 | Backend TDD | User Profile Validation Service | Medium | Yes |
| `issue_003_frontend_standard.md` | #3 | Frontend Standard | User Login Page Component | Medium | No |
| `issue_004_frontend_tdd.md` | #4 | Frontend TDD | User Dashboard Component | Medium | Yes |

## Files

### 1. `issue_001_backend_standard.md`
**Backend Standard Workflow Test**
- **Type:** Feature - User Authentication API
- **Tech Stack:** FastAPI, Pydantic, JWT, bcrypt
- **Expected Output:**
  - `app/server/api/auth.py` - Authentication endpoints
  - `app/server/api/models.py` - Pydantic models
  - `app/server/utils/jwt_utils.py` - JWT utilities
  - `app/server/utils/password_utils.py` - Password hashing
- **Test Strategy:** Manual testing (non-TDD workflow)
- **Success Metric:** Functional REST API endpoint that validates credentials and returns JWT tokens

### 2. `issue_002_backend_tdd.md`
**Backend TDD Workflow Test**
- **Type:** Feature - User Profile Validation Service (TDD)
- **Tech Stack:** Python, Pydantic, pytest
- **Expected Output (Red Phase - Tests First):**
  - `tests/services/test_profile_validator.py` - Comprehensive test suite
- **Expected Output (Green Phase - Implementation):**
  - `app/server/services/profile_validator.py` - Main validation logic
  - `app/server/services/models.py` - Pydantic models
- **Test Coverage Required:** 100%
- **Validation Rules:** Username (3-20 chars), Email (RFC 5322), Age (13-120), Bio (max 500 chars)
- **Success Metric:** All generated tests pass, 100% code coverage

### 3. `issue_003_frontend_standard.md`
**Frontend Standard Workflow Test**
- **Type:** Feature - User Login Page Component
- **Tech Stack:** React 18+, TypeScript, CSS Modules/Tailwind, React Hook Form
- **Expected Output:**
  - `app/client/src/pages/LoginPage.tsx` - Main component
  - `app/client/src/pages/LoginPage.module.css` - Component styles
  - `app/client/src/components/Input.tsx` - Reusable input
  - `app/client/src/components/Button.tsx` - Reusable button
  - `app/client/src/utils/validation.ts` - Form validation helpers
- **Features:** Email/password validation, show/hide password, loading states, error handling
- **Test Strategy:** Manual testing (non-TDD workflow)
- **Success Metric:** Responsive, accessible login page with proper validation and UX

### 4. `issue_004_frontend_tdd.md`
**Frontend TDD Workflow Test**
- **Type:** Feature - User Dashboard Component (TDD)
- **Tech Stack:** React 18+, TypeScript, React Testing Library, Jest/Vitest
- **Expected Output (Red Phase - Tests First):**
  - `app/client/src/components/__tests__/UserDashboard.test.tsx` - Comprehensive test suite
- **Expected Output (Green Phase - Implementation):**
  - `app/client/src/components/UserDashboard.tsx` - Main component
  - `app/client/src/components/UserDashboard.module.css` - Styles
  - `app/client/src/components/Avatar.tsx` - Avatar component
  - `app/client/src/utils/dateFormatting.ts` - Date helpers
  - `app/client/src/utils/initials.ts` - Initials helper
- **Test Coverage:** Rendering, interactions, accessibility, edge cases
- **Success Metric:** All generated RTL tests pass, 100% component coverage

## Usage

### Quick Start

1. **Create GitHub Issues** (using GitHub CLI):
```bash
cd /path/to/your/adws/project

# Create all 4 issues
gh issue create --title "Add User Authentication API Endpoint" \
  --label "feature,backend,api" \
  --body-file ../workflow_test_issues/issue_001_backend_standard.md

gh issue create --title "Implement User Profile Validation Service (TDD)" \
  --label "feature,backend,tdd,validation" \
  --body-file ../workflow_test_issues/issue_002_backend_tdd.md

gh issue create --title "Create User Login Page Component" \
  --label "feature,frontend,ui,react" \
  --body-file ../workflow_test_issues/issue_003_frontend_standard.md

gh issue create --title "Create User Dashboard Component with Tests (TDD)" \
  --label "feature,frontend,tdd,react,testing" \
  --body-file ../workflow_test_issues/issue_004_frontend_tdd.md
```

2. **Run Workflow Tests**:
```python
# Use the automated test script from WORKFLOW_TEST_PLAN.md
python run_workflow_tests.py
```

3. **Or test individually**:
```python
from adws.workflows import BackendStandardWorkflow
workflow = BackendStandardWorkflow(repo_path=Path.cwd())
result = await workflow.execute_from_issue(issue_number=1)
```

### Expected Outcomes

**Backend Standard (#1):**
- ✅ Authentication API endpoint implemented
- ✅ JWT token generation working
- ✅ Pydantic models for request/response
- ✅ Password validation and hashing
- ✅ Conventional commit created
- ✅ PR opened with implementation summary

**Backend TDD (#2):**
- ✅ **Tests generated FIRST** with comprehensive coverage
- ✅ **Code implemented SECOND** to make tests pass
- ✅ ProfileValidator class with all validation methods
- ✅ ValidationResult and UserProfile models
- ✅ 100% test coverage
- ✅ Commit marked with "(TDD)"
- ✅ PR includes test-first workflow summary

**Frontend Standard (#3):**
- ✅ LoginPage React component implemented
- ✅ Responsive design with CSS modules
- ✅ Form validation (email/password)
- ✅ Loading states and error handling
- ✅ Accessible (ARIA labels, keyboard navigation)
- ✅ Conventional commit created
- ✅ PR with manual test plan

**Frontend TDD (#4):**
- ✅ **Tests generated FIRST** using React Testing Library
- ✅ **Component implemented SECOND** to make tests pass
- ✅ UserDashboard component with profile/activity/actions
- ✅ Comprehensive RTL tests (rendering, interaction, accessibility)
- ✅ 100% component test coverage
- ✅ Commit marked with "(TDD)"
- ✅ PR includes Jest/RTL test suite details

## Issue Characteristics

### Complexity Levels

All issues are **Medium complexity** to ensure they:
- Challenge the workflow's autonomous capabilities
- Require multiple files to be created
- Test state management and event emission
- Validate proper git operations
- Ensure quality PR creation

### TDD Requirements

**TDD Workflows (Issues #2, #4):**
- Explicit instruction to generate tests FIRST
- Detailed test case specifications
- Coverage requirements (100%)
- Test framework specifications (pytest/RTL)
- Success criteria tied to test passage

**Non-TDD Workflows (Issues #1, #3):**
- Implementation-focused
- Manual testing strategies
- Quality requirements without automated tests
- Acceptance criteria based on functionality

### Issue Quality

Each issue includes:
- ✅ Clear title and description
- ✅ Functional and non-functional requirements
- ✅ Expected file structure
- ✅ Code examples and snippets
- ✅ Acceptance criteria checklist
- ✅ Technical specifications
- ✅ Priority and complexity indicators
- ✅ Additional context for LLM understanding

## Testing Philosophy

These issues test the **full autonomous loop**:
```
GitHub Issue → LLM Analysis → Plan Generation → Code Generation →
Git Operations → PR Creation → State Tracking → Event Emission
```

**Without any human intervention.**

## Success Criteria

A workflow passes its test if:
1. ✅ Completes from issue to PR without errors
2. ✅ Creates all expected files in correct locations
3. ✅ Generates proper git commits with conventional format
4. ✅ Opens PR with appropriate summary
5. ✅ Tracks state through complete lifecycle
6. ✅ Emits events at each workflow phase
7. ✅ (TDD only) Generates tests BEFORE implementation
8. ✅ (TDD only) Includes "(TDD)" marker in commit message

## Next Steps

After running these tests:

1. **Review Generated Code** - Assess LLM code quality
2. **Measure Performance** - Track duration and resource usage
3. **Validate State/Events** - Ensure tracking is accurate
4. **Test Edge Cases** - Create more complex issues
5. **Improve Workflows** - Address any identified issues

## Related Documentation

- [`WORKFLOW_TEST_PLAN.md`](./WORKFLOW_TEST_PLAN.md) - Complete testing guide
- [`issue_001_backend_standard.md`](./issue_001_backend_standard.md) - Backend API issue
- [`issue_002_backend_tdd.md`](./issue_002_backend_tdd.md) - Backend TDD issue
- [`issue_003_frontend_standard.md`](./issue_003_frontend_standard.md) - Frontend component issue
- [`issue_004_frontend_tdd.md`](./issue_004_frontend_tdd.md) - Frontend TDD issue

---

**Created:** 2025-11-22
**Template Version:** ADWS UV Cookiecutter v2.0
**Purpose:** Validate autonomous workflow completion capabilities

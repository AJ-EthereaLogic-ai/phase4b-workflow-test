# ADWS Workflow Autonomous Completion Test Plan

## Overview

This document outlines the comprehensive testing strategy for validating that all 4 ADWS workflows can complete GitHub issues autonomously without human intervention.

---

## Test Objectives

1. **Validate Autonomous Execution:** Ensure each workflow can complete from GitHub issue to Pull Request without manual intervention
2. **Verify State Management:** Confirm state transitions are tracked correctly through the workflow lifecycle
3. **Validate Event Emissions:** Ensure real-time events are emitted at each workflow phase
4. **Test Error Handling:** Verify graceful handling of errors and edge cases
5. **Measure Success Rates:** Track completion rates and identify failure points

---

## Mock GitHub Issues Created

| Issue # | Type | Workflow | Description | Complexity |
|---------|------|----------|-------------|------------|
| 001 | Feature | `backend_standard` | User Authentication API Endpoint | Medium |
| 002 | Feature | `backend_tdd` | User Profile Validation Service (TDD) | Medium |
| 003 | Feature | `frontend_standard` | User Login Page Component | Medium |
| 004 | Feature | `frontend_tdd` | User Dashboard Component (TDD) | Medium |

---

## Prerequisites

### 1. Generate Test Project
```bash
cd /Users/etherealogic/Dev/ADWS_UV_Cookiecutter_v2.0

# Generate a test project with all features enabled
cookiecutter cookiecutter-adws-uv --no-input \
  project_name="ADWS Workflow Test" \
  enable_devcontainer="yes" \
  enable_docker_deployment="no" \
  enable_monitoring="yes"

cd adws_workflow_test
```

### 2. Configure Environment
```bash
# Copy environment template
cp .env.example .env

# Edit .env and add REAL API keys
nano .env
```

Required API keys in `.env`:
```bash
ANTHROPIC_API_KEY=sk-ant-...  # For Claude (primary provider)
OPENAI_API_KEY=sk-...         # For OpenAI (consensus)
GOOGLE_API_KEY=...            # For Gemini (consensus)
GITHUB_TOKEN=ghp_...          # For GitHub API access
```

### 3. Initialize Repository
```bash
# Initialize git repository (should be done by template)
git init
git add .
git commit -m "Initial commit from ADWS template"

# Create GitHub repository (or use local repo for testing)
gh repo create adws-workflow-test --private --source=. --remote=origin

# Push initial commit
git push -u origin main
```

### 4. Create Mock GitHub Issues

Option A: **Use GitHub CLI** (Recommended for real GitHub integration)
```bash
# Issue #1: Backend Standard
gh issue create \
  --title "Add User Authentication API Endpoint" \
  --label "feature,backend,api" \
  --body-file ../workflow_test_issues/issue_001_backend_standard.md

# Issue #2: Backend TDD
gh issue create \
  --title "Implement User Profile Validation Service (TDD)" \
  --label "feature,backend,tdd,validation" \
  --body-file ../workflow_test_issues/issue_002_backend_tdd.md

# Issue #3: Frontend Standard
gh issue create \
  --title "Create User Login Page Component" \
  --label "feature,frontend,ui,react" \
  --body-file ../workflow_test_issues/issue_003_frontend_standard.md

# Issue #4: Frontend TDD
gh issue create \
  --title "Create User Dashboard Component with Tests (TDD)" \
  --label "feature,frontend,tdd,react,testing" \
  --body-file ../workflow_test_issues/issue_004_frontend_tdd.md
```

Option B: **Mock GitHub API** (For local testing without GitHub)
- Use fixtures from `tests/fixtures/sample_issues.py`
- Modify workflow code to use mocked GitHub client

---

## Test Execution

### Test 1: Backend Standard Workflow

**Issue:** #1 - User Authentication API Endpoint
**Workflow:** `BackendStandardWorkflow`
**Expected Outcome:** Python API endpoint files created, committed, and PR opened

```python
# Run this in Python (e.g., in a Jupyter notebook or script)
import asyncio
from pathlib import Path
from adws.workflows import BackendStandardWorkflow

async def test_backend_standard():
    """Test backend_standard workflow with Issue #1"""

    # Initialize workflow
    workflow = BackendStandardWorkflow(
        repo_path=Path.cwd(),
        working_dir="app/server"
    )

    # Execute from GitHub issue
    result = await workflow.execute_from_issue(
        issue_number=1,
        use_consensus=False  # Start with single provider
    )

    # Validate results
    print(f"✅ Workflow completed: {result.success}")
    print(f"📁 Files created: {len(result.artifacts)}")
    print(f"🔀 Branch: {result.metadata.get('branch_name')}")
    print(f"🔗 PR URL: {result.artifacts[0] if result.artifacts else 'N/A'}")

    # Check state
    if result.metadata.get('workflow_id'):
        from adws.state import StateManager
        sm = StateManager()
        state = await sm.get_workflow(result.metadata['workflow_id'])
        print(f"📊 Final state: {state.current_state}")
        print(f"⏱️  Duration: {state.duration_seconds}s")

# Run test
asyncio.run(test_backend_standard())
```

**Success Criteria:**
- [ ] Workflow completes without errors
- [ ] Files created in `app/server/api/` and `app/server/utils/`
- [ ] Git branch created: `feature/issue-1-feature`
- [ ] Commit created with conventional commit message
- [ ] PR created on GitHub
- [ ] State tracked through lifecycle: `pending → planning → generating → committing → completed`
- [ ] Events emitted at each phase

**Validation Commands:**
```bash
# Check created files
ls -la app/server/api/
ls -la app/server/utils/

# Check git branch
git branch -a | grep issue-1

# Check commits
git log feature/issue-1-feature --oneline

# Check PR
gh pr list

# Check state database
sqlite3 .adws/state/workflows.db "SELECT workflow_id, current_state, change_type FROM workflows;"

# Check events log
tail -20 .adws/events/events.jsonl
```

---

### Test 2: Backend TDD Workflow

**Issue:** #2 - User Profile Validation Service (TDD)
**Workflow:** `BackendTDDWorkflow`
**Expected Outcome:** Tests generated first, then implementation, both committed, PR opened

```python
import asyncio
from pathlib import Path
from adws.workflows import BackendTDDWorkflow

async def test_backend_tdd():
    """Test backend_tdd workflow with Issue #2"""

    # Initialize workflow
    workflow = BackendTDDWorkflow(
        repo_path=Path.cwd(),
        working_dir="app/server",
        test_directories=["tests"]
    )

    # Execute from GitHub issue with TDD
    result = await workflow.execute_from_issue(
        issue_number=2,
        use_consensus=True,  # Use multi-provider for TDD
        validate_tests=False  # Don't run tests yet (optional)
    )

    # Validate results
    print(f"✅ Workflow completed: {result.success}")
    print(f"📝 Test files: {[f for f in result.artifacts if 'test_' in f]}")
    print(f"📁 Code files: {[f for f in result.artifacts if 'test_' not in f]}")
    print(f"🔀 Branch: {result.metadata.get('branch_name')}")
    print(f"🔗 PR URL: {result.artifacts[-1] if result.artifacts else 'N/A'}")

    # Check TDD workflow phases
    print(f"🔴 Red phase completed: {result.metadata.get('red_phase_complete')}")
    print(f"🟢 Green phase completed: {result.metadata.get('green_phase_complete')}")

# Run test
asyncio.run(test_backend_tdd())
```

**Success Criteria:**
- [ ] Workflow completes without errors
- [ ] **Test files created FIRST** in `tests/services/test_profile_validator.py`
- [ ] **Code files created SECOND** in `app/server/services/profile_validator.py`
- [ ] Git branch created: `feature/issue-2-feature-tdd`
- [ ] Commit includes both tests and implementation
- [ ] Commit message includes "(TDD)" marker
- [ ] PR created with TDD-specific summary
- [ ] State includes `red_phase` and `green_phase` metadata
- [ ] Events show both Red and Green phases

**Validation Commands:**
```bash
# Verify test file created first (check git log for order)
git log feature/issue-2-feature-tdd --name-status --oneline

# Check test file exists
cat tests/services/test_profile_validator.py | head -50

# Check implementation file exists
cat app/server/services/profile_validator.py | head -50

# Optionally run tests
pytest tests/services/test_profile_validator.py -v

# Check TDD markers in commit
git log feature/issue-2-feature-tdd --format="%s" | grep TDD
```

---

### Test 3: Frontend Standard Workflow

**Issue:** #3 - User Login Page Component
**Workflow:** `FrontendStandardWorkflow`
**Expected Outcome:** React component files created, committed, and PR opened

```python
import asyncio
from pathlib import Path
from adws.workflows import FrontendStandardWorkflow

async def test_frontend_standard():
    """Test frontend_standard workflow with Issue #3"""

    # Initialize workflow
    workflow = FrontendStandardWorkflow(
        repo_path=Path.cwd(),
        working_dir="app/client"
    )

    # Execute from GitHub issue
    result = await workflow.execute_from_issue(
        issue_number=3,
        use_consensus=False
    )

    # Validate results
    print(f"✅ Workflow completed: {result.success}")
    print(f"📁 Files created: {len(result.artifacts)}")
    print(f"🔀 Branch: {result.metadata.get('branch_name')}")
    print(f"🔗 PR URL: {result.artifacts[0] if result.artifacts else 'N/A'}")

# Run test
asyncio.run(test_frontend_standard())
```

**Success Criteria:**
- [ ] Workflow completes without errors
- [ ] Component files created in `app/client/src/pages/LoginPage.tsx`
- [ ] Style files created in `app/client/src/pages/LoginPage.module.css`
- [ ] Utility files created in `app/client/src/utils/`
- [ ] Git branch created: `feature/issue-3-feature-frontend`
- [ ] Commit created with conventional commit message
- [ ] PR created on GitHub
- [ ] PR includes manual test plan (no automated tests)

**Validation Commands:**
```bash
# Check created files
ls -la app/client/src/pages/
ls -la app/client/src/components/
ls -la app/client/src/utils/

# View component code
cat app/client/src/pages/LoginPage.tsx | head -100

# Check branch
git log feature/issue-3-feature-frontend --oneline
```

---

### Test 4: Frontend TDD Workflow

**Issue:** #4 - User Dashboard Component with Tests (TDD)
**Workflow:** `FrontendTDDWorkflow`
**Expected Outcome:** React Testing Library tests generated first, then component, both committed, PR opened

```python
import asyncio
from pathlib import Path
from adws.workflows import FrontendTDDWorkflow

async def test_frontend_tdd():
    """Test frontend_tdd workflow with Issue #4"""

    # Initialize workflow
    workflow = FrontendTDDWorkflow(
        repo_path=Path.cwd(),
        working_dir="app/client",
        test_directories=["src/__tests__", "src/components/__tests__"]
    )

    # Execute from GitHub issue with TDD
    result = await workflow.execute_from_issue(
        issue_number=4,
        use_consensus=True,  # Use multi-provider for TDD
        validate_tests=False  # Don't run tests yet
    )

    # Validate results
    print(f"✅ Workflow completed: {result.success}")
    print(f"📝 Test files: {[f for f in result.artifacts if '.test.' in f or '.spec.' in f]}")
    print(f"📁 Component files: {[f for f in result.artifacts if '.test.' not in f and '.spec.' not in f]}")
    print(f"🔀 Branch: {result.metadata.get('branch_name')}")
    print(f"🔗 PR URL: {result.artifacts[-1] if result.artifacts else 'N/A'}")

# Run test
asyncio.run(test_frontend_tdd())
```

**Success Criteria:**
- [ ] Workflow completes without errors
- [ ] **Test files created FIRST** in `app/client/src/components/__tests__/UserDashboard.test.tsx`
- [ ] **Component files created SECOND** in `app/client/src/components/UserDashboard.tsx`
- [ ] Utility files created for helpers
- [ ] Git branch created: `feature/issue-4-feature-frontend-tdd`
- [ ] Commit includes both tests and implementation
- [ ] Commit message includes "(TDD)" marker
- [ ] PR created with TDD-specific summary mentioning Jest/RTL
- [ ] Events show both Red and Green phases

**Validation Commands:**
```bash
# Verify test file created first
git log feature/issue-4-feature-frontend-tdd --name-status --oneline

# Check test file
cat app/client/src/components/__tests__/UserDashboard.test.tsx | head -100

# Check component file
cat app/client/src/components/UserDashboard.tsx | head -100

# Optionally run tests (if Jest/Vitest configured)
npm test -- UserDashboard.test.tsx

# Check TDD markers
git log feature/issue-4-feature-frontend-tdd --format="%s" | grep TDD
```

---

## Automated Test Script

Create `run_workflow_tests.py` to automate all 4 workflow tests:

```python
"""
Automated workflow testing script.
Runs all 4 workflows against their corresponding GitHub issues.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from adws.workflows import (
    BackendStandardWorkflow,
    BackendTDDWorkflow,
    FrontendStandardWorkflow,
    FrontendTDDWorkflow
)


class WorkflowTestRunner:
    """Automated test runner for all ADWS workflows."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.results: List[Dict] = []

    async def test_workflow(
        self,
        workflow_class,
        workflow_name: str,
        issue_number: int,
        **kwargs
    ) -> Dict:
        """Test a single workflow and return results."""
        print(f"\n{'=' * 80}")
        print(f"Testing: {workflow_name}")
        print(f"Issue #: {issue_number}")
        print(f"{'=' * 80}\n")

        start_time = datetime.now()

        try:
            # Initialize workflow
            workflow = workflow_class(repo_path=self.repo_path, **kwargs)

            # Execute from issue
            result = await workflow.execute_from_issue(issue_number=issue_number)

            duration = (datetime.now() - start_time).total_seconds()

            test_result = {
                "workflow": workflow_name,
                "issue_number": issue_number,
                "success": result.success,
                "duration_seconds": duration,
                "files_created": len(result.artifacts),
                "branch_name": result.metadata.get("branch_name"),
                "pr_url": result.artifacts[0] if result.artifacts else None,
                "error": None
            }

            print(f"\n✅ {workflow_name} PASSED")
            print(f"   Duration: {duration:.2f}s")
            print(f"   Files: {len(result.artifacts)}")

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            test_result = {
                "workflow": workflow_name,
                "issue_number": issue_number,
                "success": False,
                "duration_seconds": duration,
                "error": str(e)
            }

            print(f"\n❌ {workflow_name} FAILED")
            print(f"   Error: {e}")

        self.results.append(test_result)
        return test_result

    async def run_all_tests(self):
        """Run all workflow tests."""
        print("\n" + "=" * 80)
        print("ADWS WORKFLOW AUTONOMOUS COMPLETION TESTS")
        print("=" * 80)

        # Test 1: Backend Standard
        await self.test_workflow(
            BackendStandardWorkflow,
            "BackendStandardWorkflow",
            issue_number=1,
            working_dir="app/server"
        )

        # Test 2: Backend TDD
        await self.test_workflow(
            BackendTDDWorkflow,
            "BackendTDDWorkflow",
            issue_number=2,
            working_dir="app/server",
            test_directories=["tests"]
        )

        # Test 3: Frontend Standard
        await self.test_workflow(
            FrontendStandardWorkflow,
            "FrontendStandardWorkflow",
            issue_number=3,
            working_dir="app/client"
        )

        # Test 4: Frontend TDD
        await self.test_workflow(
            FrontendTDDWorkflow,
            "FrontendTDDWorkflow",
            issue_number=4,
            working_dir="app/client",
            test_directories=["src/__tests__", "src/components/__tests__"]
        )

        # Generate report
        self.generate_report()

    def generate_report(self):
        """Generate test results report."""
        print("\n" + "=" * 80)
        print("TEST RESULTS SUMMARY")
        print("=" * 80 + "\n")

        passed = sum(1 for r in self.results if r["success"])
        failed = len(self.results) - passed

        print(f"Total Tests: {len(self.results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {passed / len(self.results) * 100:.1f}%\n")

        # Detailed results
        for result in self.results:
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            print(f"{status} | {result['workflow']}")
            print(f"       Issue #{result['issue_number']}")
            print(f"       Duration: {result.get('duration_seconds', 0):.2f}s")
            if result.get("error"):
                print(f"       Error: {result['error']}")
            print()

        # Save report to JSON
        report_path = Path("workflow_test_results.json")
        with open(report_path, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "results": self.results
            }, f, indent=2)

        print(f"📄 Full report saved to: {report_path}")


async def main():
    """Main entry point."""
    repo_path = Path.cwd()
    runner = WorkflowTestRunner(repo_path)
    await runner.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Expected Results

### Success Metrics

| Workflow | Expected Duration | Files Created | Test Coverage |
|----------|------------------|---------------|---------------|
| Backend Standard | 30-60s | 4-6 files | N/A (no tests) |
| Backend TDD | 60-120s | 8-12 files | 100% |
| Frontend Standard | 30-60s | 3-5 files | N/A (no tests) |
| Frontend TDD | 60-120s | 6-10 files | 100% |

### State Lifecycle

All workflows should transition through:
```
pending → planning → generating → committing → pushing → creating_pr → completed
```

TDD workflows have additional states:
```
pending → planning → generating_tests (Red) → generating_code (Green) → ...
```

### Event Types

Expected events for each workflow:
- `workflow_started`
- `workflow_state_changed` (multiple)
- `workflow_phase_completed` (planning, generating, etc.)
- `workflow_completed`
- `workflow_failed` (if errors occur)

---

## Troubleshooting

### Common Issues

**Issue:** GitHub authentication fails
- **Solution:** Verify `GITHUB_TOKEN` in `.env`, ensure token has `repo` scope

**Issue:** LLM API errors
- **Solution:** Check API keys are valid, verify rate limits not exceeded

**Issue:** State database locked
- **Solution:** Close any open connections: `pkill -f workflows.db`

**Issue:** Tests generated but don't run
- **Solution:** This is expected when `validate_tests=False`. Set to `True` to run tests.

**Issue:** Workflow stuck in `generating` state
- **Solution:** Check LLM provider quotas, verify network connectivity

---

## Success Criteria Summary

**All tests pass if:**
- [ ] All 4 workflows complete without errors
- [ ] Pull requests are created for all issues
- [ ] State is tracked correctly through lifecycle
- [ ] Events are emitted at each phase
- [ ] TDD workflows generate tests BEFORE code
- [ ] All files are created in correct locations
- [ ] Commits have proper conventional commit format
- [ ] No manual intervention required

---

## Next Steps After Testing

1. **Review Generated Code** - Check quality of LLM-generated code
2. **Run Tests** - For TDD workflows, verify tests actually pass
3. **Code Review** - Simulate PR review process
4. **Measure Performance** - Track duration and resource usage
5. **Identify Improvements** - Document any workflow issues or enhancements needed

---

Generated: 2025-11-22
Template Version: ADWS UV Cookiecutter v2.0

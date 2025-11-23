# Backend Workflow Test - AI Agent Instructions

## Context

You are testing the BackendStandardWorkflow in the ADWS (AI Developer Workflow System) autonomous workflow testing infrastructure. Previous investigation identified and fixed multiple issues preventing the workflow from executing successfully.

## Project Location
```
/Users/etherealogic/Dev/ADWS_UV_Cookiecutter_v2.0/phase4b_test
```

## Background - Issues Found & Fixed

### Issue 1: ClaudeCodeProvider is CLI-based
**Problem:** The original `ClaudeCodeProvider` wraps the Claude Code CLI tool via subprocess, not direct API calls.
**Solution:** Created `adws/providers/implementations/anthropic_direct.py` - a new provider using the Anthropic Python SDK for direct API calls.

### Issue 2: Invalid Model Name
**Problem:** Config used `claude-3-5-sonnet-20241022` which doesn't exist in Anthropic's API.
**Solution:** Updated to `claude-3-5-sonnet-20240620` (valid model name).

### Issue 3: Missing Dependencies
**Problem:** `anthropic` Python package not installed.
**Solution:** Installed via `uv pip install anthropic`.

## Current State

### ✅ Completed Setup
- GitHub repository created: `https://github.com/AJ-EthereaLogic-ai/phase4b-workflow-test`
- 4 test issues created (#1-#4)
- API keys configured in `.env` (Anthropic, OpenAI, Gemini, GitHub)
- All 3 LLM providers registered successfully
- Dependencies installed: `anthropic`, `python-dotenv`, `google-generativeai`

### 📁 Key Files Created/Modified

**New Files:**
1. `adws/providers/implementations/anthropic_direct.py` - Direct Anthropic API provider
2. `debug_backend_workflow.py` - Diagnostic script for testing
3. `run_workflow_tests_complete.py` - Complete test runner with all providers

**Modified Files:**
1. `adws.toml` - Updated model name to `claude-3-5-sonnet-20240620`
2. Test runners updated to use `AnthropicProvider` instead of `ClaudeCodeProvider`

### 🔧 Environment Details
- Python: 3.12.11 (in `.venv`)
- Virtual environment: `/Users/etherealogic/Dev/ADWS_UV_Cookiecutter_v2.0/phase4b_test/.venv`
- API Keys: Already configured in `.env` file
- GitHub CLI: Authenticated as `AJ-EthereaLogic-ai`

## Your Task

Run the final test of BackendStandardWorkflow with all fixes applied and verify it works correctly.

## Step-by-Step Instructions

### Step 1: Navigate to Project
```bash
cd /Users/etherealogic/Dev/ADWS_UV_Cookiecutter_v2.0/phase4b_test
```

### Step 2: Activate Virtual Environment
```bash
source .venv/bin/activate
```

### Step 3: Run Debug Script
Execute the debug script to test BackendStandardWorkflow with Issue #1:

```bash
python debug_backend_workflow.py 2>&1
```

**Expected Behavior:**
- Duration: 15-45 seconds (actual LLM API call)
- Should see provider registration messages
- Should fetch GitHub issue #1 (2533 chars)
- Should initialize workflow
- Should execute and call Anthropic API
- **Key Success Indicator:** `Success: True` and response text generated

### Step 4: Interpret Results

#### ✅ SUCCESS Indicators:
```
6. RESULTS:
   Success: True                    ← MUST BE TRUE
   Provider: claude
   Response text (XXXX chars):      ← MUST HAVE CONTENT
   Preview: [code generation...]    ← ACTUAL CODE OUTPUT
   Metadata: {
      'duration_seconds': XX.XX,    ← SHOULD BE 15-45 seconds
      'total_tokens': XXXX          ← SHOULD BE > 0
   }
```

#### ❌ FAILURE Indicators:
```
Success: False
❌ No response text generated
total_tokens: 0
❌ Anthropic API Error: ...
```

### Step 5: If Successful, Run Full Test Suite
```bash
python run_workflow_tests_complete.py 2>&1
```

This will test all 4 workflows:
1. BackendStandardWorkflow (Issue #1) - Should now PASS ✅
2. BackendTDDWorkflow (Issue #2) - May still fail (separate issue)
3. FrontendStandardWorkflow (Issue #3) - Already PASSING ✅
4. FrontendTDDWorkflow (Issue #4) - May still fail (separate issue)

**Expected Duration:** 3-8 minutes for all workflows

## Success Criteria

### Minimum Success (BackendStandardWorkflow Only):
- ✅ `Success: True` in debug output
- ✅ Response text generated (actual code from Claude)
- ✅ Total tokens > 0
- ✅ Duration 15-45 seconds
- ✅ No API errors

### Full Success (All Tests):
- ✅ BackendStandardWorkflow: PASS
- ✅ FrontendStandardWorkflow: PASS (already working)
- Note: BackendTDDWorkflow and FrontendTDDWorkflow may still fail (different issues)

## Troubleshooting

### If you see: "Model not found: claude-3-5-sonnet-20240620"
Check if Anthropic changed model names. Try:
- `claude-3-5-sonnet-latest`
- `claude-3-5-sonnet-20241022`
- Check Anthropic docs for current model names

### If you see: "ModuleNotFoundError: No module named 'anthropic'"
```bash
source .venv/bin/activate
uv pip install anthropic
```

### If you see: "Provider not registered: claude"
The `AnthropicProvider` isn't being imported correctly. Check:
```bash
python -c "from adws.providers.implementations.anthropic_direct import AnthropicProvider; print('Import OK')"
```

### If you see: "Authentication error"
Check `.env` file has valid `ANTHROPIC_API_KEY`

## Expected Output Example

### Debug Script Success Output:
```
================================================================================
BACKEND STANDARD WORKFLOW DEBUG
================================================================================

1. Setting up providers...
   ✅ Claude provider registered
   ✅ OpenAI provider registered
   ✅ Gemini provider registered
   Registered providers: ['claude', 'gemini', 'openai']

2. Creating LLM Orchestrator...
   ✅ Orchestrator created
   Backend route: provider=claude, model=claude-3-5-sonnet-20240620

3. Fetching GitHub issue #1...
   ✅ Got requirement (2533 chars)
   Preview: # Issue #1: Add User Authentication API Endpoint...

4. Initializing BackendStandardWorkflow...
   ✅ Workflow initialized
   Config backend_route: provider='claude' model='claude-3-5-sonnet-20240620'

5. Executing workflow...

6. RESULTS:
   Success: True
   Provider: claude
   ADW ID: debug-backend-1
   Workflow: backend_standard

   Response text (4521 chars):
   """
FastAPI authentication endpoint implementation...
from fastapi import APIRouter, Depends, HTTPException
...
   """

   Metadata: {
      'issue_number': '1',
      'debug': 'true',
      'duration_seconds': 23.45,
      'total_tokens': 1234
   }

   ✅ SUCCESS
```

## Deliverables

After successful test, report:

1. **Test Result:** PASS or FAIL
2. **Duration:** How long the API call took
3. **Response Size:** Character count and token count
4. **Generated Code Sample:** First 500 chars of the response
5. **Any Errors:** Full error messages if failure
6. **Full Test Suite Results:** If you ran `run_workflow_tests_complete.py`

## Additional Context

### GitHub Issue #1 Content
The test uses GitHub issue #1 which requests:
- Feature: Add User Authentication API Endpoint
- Requirements: JWT-based auth, password validation, FastAPI
- Expected files: auth.py, models/user.py, schemas/auth.py, utils/security.py

### What the Workflow Should Generate
Claude should generate:
- FastAPI router code for `/api/v1/auth/login`
- User model with Pydantic
- JWT token generation utilities
- Password hashing with bcrypt
- Request/response schemas

### Previous Test Results
- **FrontendStandardWorkflow:** ✅ PASSED (36.5 seconds, generated React login component)
- **BackendStandardWorkflow:** ❌ FAILED (before fixes - 0.25s, no API call)
- **BackendTDDWorkflow:** ❌ FAILED (provider issues)
- **FrontendTDDWorkflow:** ❌ FAILED (consensus validation bug)

## Files You May Need to Reference

### Configuration
- `.env` - API keys (already configured)
- `adws.toml` - Provider configs
- `workflow_test_issues/issue_001_backend_standard.md` - Full issue specification

### Code
- `adws/workflows/backend_standard.py` - Workflow implementation
- `adws/providers/implementations/anthropic_direct.py` - New Anthropic provider
- `debug_backend_workflow.py` - Test script

### Documentation
- `GITHUB_SETUP_GUIDE.md` - Setup documentation
- `workflow_test_results.json` - Previous test results

## Quick Command Summary

```bash
# Navigate and activate
cd /Users/etherealogic/Dev/ADWS_UV_Cookiecutter_v2.0/phase4b_test
source .venv/bin/activate

# Run debug test (focused test)
python debug_backend_workflow.py 2>&1

# Run full test suite (all 4 workflows)
python run_workflow_tests_complete.py 2>&1

# Check test results
cat workflow_test_results.json | python -m json.tool

# Verify provider import
python -c "from adws.providers.implementations.anthropic_direct import AnthropicProvider; print('✅ Provider available')"

# Check GitHub issues
gh issue list

# View repository
gh repo view
```

## Important Notes

1. **The Anthropic API key is already configured** - Don't regenerate it
2. **All dependencies are installed** - Just activate the venv
3. **GitHub issues are already created** - Issue #1 exists
4. **This is a read-only test** - We're just verifying the workflow executes
5. **Focus on BackendStandardWorkflow first** - Other workflows have separate issues

## Success Confirmation

When the test passes, you should be able to confirm:
- ✅ Anthropic API was called successfully
- ✅ Claude generated Python code for authentication
- ✅ Workflow returned `success=True`
- ✅ Token count > 0 (proves API call happened)
- ✅ Duration 15-45s (proves real LLM generation, not cached/failed)

## Next Steps After Success

If the test passes:
1. Commit the fixes to git
2. Update `workflow_test_results.json` with new results
3. Push to GitHub repository
4. Create summary report of what was fixed

---

**Ready to proceed?** Run the debug script and report the results!

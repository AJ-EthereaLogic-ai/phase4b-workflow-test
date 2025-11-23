# GitHub Setup Guide - Quick Start

## Current Status
✅ API Keys Configured (Anthropic, OpenAI, Gemini)
❌ GitHub Token Missing
❌ GitHub Repository Not Created
❌ GitHub Issues Not Created

---

## Step 1: Create GitHub Personal Access Token

### Option A: Using GitHub CLI (Recommended)
```bash
# Login to GitHub
gh auth login

# Follow the prompts:
# - Choose: GitHub.com
# - Choose: HTTPS
# - Authenticate: Login with web browser
# - This will automatically configure your GitHub token
```

### Option B: Manual Token Creation
1. Go to: https://github.com/settings/tokens/new
2. **Note:** "ADWS Workflow Testing"
3. **Expiration:** 90 days (or custom)
4. **Select scopes:**
   - ✅ `repo` (Full control of private repositories)
   - ✅ `workflow` (Update GitHub Actions workflows)
5. Click "Generate token"
6. **Copy the token immediately** (you won't see it again!)

### Add Token to .env File
```bash
# Edit .env and add this line:
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## Step 2: Verify GitHub Authentication

```bash
cd /Users/etherealogic/Dev/ADWS_UV_Cookiecutter_v2.0/phase4b_test

# Test GitHub CLI authentication
gh auth status

# Expected output:
# ✓ Logged in to github.com as YOUR_USERNAME
```

---

## Step 3: Create GitHub Repository

### Option A: Using GitHub CLI (Recommended)
```bash
cd /Users/etherealogic/Dev/ADWS_UV_Cookiecutter_v2.0/phase4b_test

# Create repository and push
gh repo create phase4b-workflow-test \
  --public \
  --source=. \
  --remote=origin \
  --push

# This will:
# 1. Create GitHub repo: github.com/YOUR_USERNAME/phase4b-workflow-test
# 2. Add remote "origin"
# 3. Push current code
```

### Option B: Manual Repository Creation
```bash
# 1. Go to https://github.com/new
# 2. Repository name: phase4b-workflow-test
# 3. Public
# 4. Don't initialize with README
# 5. Create repository

# Then run:
git remote add origin https://github.com/YOUR_USERNAME/phase4b-workflow-test.git
git branch -M main
git push -u origin main
```

---

## Step 4: Create GitHub Issues (Test Data)

```bash
cd /Users/etherealogic/Dev/ADWS_UV_Cookiecutter_v2.0/phase4b_test

# Create all 4 test issues
gh issue create \
  --title "Add User Authentication API Endpoint" \
  --body-file workflow_test_issues/issue_001_backend_standard.md \
  --label feature,backend,api

gh issue create \
  --title "Implement User Profile Validation Service (TDD)" \
  --body-file workflow_test_issues/issue_002_backend_tdd.md \
  --label feature,backend,tdd,validation

gh issue create \
  --title "Create User Login Page Component" \
  --body-file workflow_test_issues/issue_003_frontend_standard.md \
  --label feature,frontend,ui,react

gh issue create \
  --title "Create User Dashboard Component with Tests (TDD)" \
  --body-file workflow_test_issues/issue_004_frontend_tdd.md \
  --label feature,frontend,tdd,react,testing

# Verify issues created
gh issue list
```

**Expected output:**
```
#4  Create User Dashboard Component with Tests (TDD)  feature, frontend, tdd
#3  Create User Login Page Component                  feature, frontend, ui
#2  Implement User Profile Validation Service (TDD)   feature, backend, tdd
#1  Add User Authentication API Endpoint              feature, backend, api
```

---

## Step 5: Run Workflow Tests

```bash
cd /Users/etherealogic/Dev/ADWS_UV_Cookiecutter_v2.0/phase4b_test

# Activate virtual environment
source .venv/bin/activate

# Verify workflows can be imported
python -c "from adws.workflows import BackendStandardWorkflow; print('✅ Workflows ready')"

# Run all 4 workflow tests
python run_workflow_tests.py
```

---

## Quick Commands (Copy-Paste Ready)

```bash
# Navigate to project
cd /Users/etherealogic/Dev/ADWS_UV_Cookiecutter_v2.0/phase4b_test

# 1. Login to GitHub (if not already)
gh auth login

# 2. Create repository and push
gh repo create phase4b-workflow-test --public --source=. --remote=origin --push

# 3. Create test issues
gh issue create --title "Add User Authentication API Endpoint" --body-file workflow_test_issues/issue_001_backend_standard.md --label feature,backend,api
gh issue create --title "Implement User Profile Validation Service (TDD)" --body-file workflow_test_issues/issue_002_backend_tdd.md --label feature,backend,tdd,validation
gh issue create --title "Create User Login Page Component" --body-file workflow_test_issues/issue_003_frontend_standard.md --label feature,frontend,ui,react
gh issue create --title "Create User Dashboard Component with Tests (TDD)" --body-file workflow_test_issues/issue_004_frontend_tdd.md --label feature,frontend,tdd,react,testing

# 4. Verify setup
gh issue list
gh repo view

# 5. Run tests
source .venv/bin/activate
python run_workflow_tests.py
```

---

## Troubleshooting

### "gh: command not found"
Install GitHub CLI:
```bash
brew install gh
```

### "Could not resolve to a Repository"
Repository not created yet. Run:
```bash
gh repo create phase4b-workflow-test --public --source=. --remote=origin --push
```

### "GITHUB_TOKEN not found in environment"
Add to `.env` file:
```bash
echo 'GITHUB_TOKEN=ghp_your_token_here' >> .env
```

### "Resource not accessible by personal access token"
Your token needs `repo` and `workflow` scopes. Create a new token with these scopes.

---

## Expected Test Duration

- Total time: ~5-8 minutes for all 4 workflows
- Backend Standard: 45-60s
- Backend TDD: 90-120s
- Frontend Standard: 40-55s
- Frontend TDD: 95-110s

---

## What Will Happen

Each workflow will:
1. ✅ Read the GitHub issue
2. ✅ Generate implementation plan
3. ✅ Generate code files
4. ✅ Create git branch
5. ✅ Commit with conventional format
6. ✅ Push to GitHub
7. ✅ Create pull request
8. ✅ Report results

After completion:
- **4 feature branches** created
- **4 pull requests** opened
- **13 code files** generated
- **JSON report** saved to `workflow_test_results.json`

---

## Next Step

**If you already have GitHub CLI installed:**
```bash
cd /Users/etherealogic/Dev/ADWS_UV_Cookiecutter_v2.0/phase4b_test
gh auth login
```

**Then let me know and I'll help you with the next steps!**

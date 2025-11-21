# Phase4B Test Project

A brief description of your project

This project was generated using the **ADWS UV Cookiecutter Template** and comes pre-configured with AI-assisted development workflows.

---

## Features

- **AI-Assisted Development Workflows (ADWS)** - Pre-configured TDD, state management, and LLM provider integration
- **Multi-Provider LLM Support** - Claude, OpenAI GPT, and Google Gemini support out-of-the-box
- **Test-Driven Development** - Automated test generation and coverage tracking
- **State Management** - SQLite-based workflow state persistence
- **Event Streaming** - Immutable audit trail for all operations
- **Cost Tracking** - Monitor and budget API costs
- **Frontend Support** - Ready for full-stack development with frontend testing

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- UV package manager (recommended) or pip

### 2. Installation

```bash
# Clone/navigate to the project directory
cd phase4b_test

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .
# Or with UV (recommended):
uv pip install -e .
```

### 3. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your API keys
# ANTHROPIC_API_KEY=sk-ant-...  # For Claude
# OPENAI_API_KEY=sk-...         # For OpenAI
# GOOGLE_API_KEY=...            # For Gemini
```

### 4. Run Tests

```bash
# Run all tests with coverage
pytest

# Run specific test markers
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m "not slow"    # Skip slow tests
```

---

## ADWS Usage Guide

### Basic Workflow

The ADWS system provides AI-assisted development workflows for:
- Test generation
- Code implementation
- State management
- Multi-provider consensus

### Configuration

Create an `adws.toml` file in the project root:

```toml
[providers.claude]
enabled = true
api_key_env = "ANTHROPIC_API_KEY"
model = "claude-3-5-sonnet-20241022"

[state]
db_path = ".adws/state/workflows.db"
enable_persistence = true

[events]
events_path = ".adws/events/events.jsonl"
enable_streaming = true

[tdd]
default_language = "python"
coverage_threshold = 90.0
```

### TDD Workflow Example

```python
from adws.tdd.orchestrator import TDDOrchestrator
from adws.providers.registry import ProviderRegistry

# Initialize ADWS components
registry = ProviderRegistry()
provider = registry.get("claude")
orchestrator = TDDOrchestrator(provider)

# Run TDD workflow
result = await orchestrator.execute_workflow(
    prompt="Create a function to calculate Fibonacci numbers",
    language="python"
)

print(f"Tests generated: {result.tests_generated}")
print(f"Implementation complete: {result.implementation_complete}")
```

### Provider Usage

```python
from adws.providers.registry import ProviderRegistry
from adws.providers.interfaces import PromptRequest, PromptMessage

# Get configured provider
registry = ProviderRegistry()
provider = registry.get("claude")

# Execute prompt
request = PromptRequest(
    prompt="Explain the SOLID principles",
    model="claude-3-5-sonnet-20241022",
    max_tokens=1000,
    temperature=0.7
)

response = await provider.execute_async(request)
print(response.output)
```

---

## Project Structure

```
phase4b_test/
├── app/                    # Your application code
│   ├── __init__.py
│   ├── server/            # Backend skeleton + API package
│   └── client/            # Frontend placeholder
├── adws/                   # ADWS framework (pre-configured)
│   ├── providers/         # Multi-LLM provider abstraction
│   ├── tdd/               # Test-driven development system
│   ├── state/             # Workflow state management
│   ├── routing/           # Request routing engine
│   ├── cost/              # Cost tracking and budgeting
│   ├── consensus/         # Multi-provider consensus
│   ├── events/            # Event streaming system
│   ├── config/            # Configuration management
│   ├── workflows/         # Workflow helpers
│   └── llm/               # Orchestrator + provider re-exports
├── tests/                 # Your test suite
│   ├── conftest.py       # Pytest configuration
│   └── test_app.py       # Example tests
├── docs/                  # Documentation
│   └── reports/          # Test coverage reports
├── .env.example          # Environment template
├── .gitignore            # Git ignore patterns
├── pyproject.toml        # Project metadata and dependencies
├── pytest.ini            # Pytest configuration
└── README.md             # This file
```

---

## Development

### Adding New Features

1. Write tests first (TDD approach):
   ```bash
   # Create test file
   touch tests/test_new_feature.py
   ```

2. Run tests (they should fail):
   ```bash
   pytest tests/test_new_feature.py
   ```

3. Implement the feature in `app/`

4. Run tests again (they should pass):
   ```bash
   pytest tests/test_new_feature.py
   ```

### Using ADWS for Test Generation

```python
# Use ADWS TDD orchestrator to generate tests
from adws.tdd.orchestrator import TDDOrchestrator

orchestrator = TDDOrchestrator(provider)
result = await orchestrator.generate_tests(
    prompt="Feature description here",
    output_path="tests/test_new_feature.py"
)
```

---

## Testing

### Run All Tests
```bash
pytest
```

### Run with Coverage
```bash
pytest --cov=app --cov=adws --cov-report=html
```

### View Coverage Report
```bash
open docs/reports/coverage/htmlcov/index.html
```

### Test Markers
```bash
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m "not slow"    # Skip slow tests
```

---

## Benchmarking & Validation

- Run `python scripts/benchmark_template_generation.py --run-pytest`
  from the repository root to capture generation time and verify that
  the generated project passes its default tests.
- The repository's GitHub Actions workflow `template-validation.yml`
  executes the same benchmark on Ubuntu and macOS runners.

---

## Configuration Reference

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ANTHROPIC_API_KEY` | Claude API key | If using Claude |
| `OPENAI_API_KEY` | OpenAI API key | If using OpenAI |
| `GOOGLE_API_KEY` | Google/Gemini API key | If using Gemini |
| `ADWS_STATE_DB_PATH` | State database path | No (default: `.adws/state/workflows.db`) |
| `ADWS_EVENTS_PATH` | Events log path | No (default: `.adws/events/events.jsonl`) |

### ADWS Configuration (`adws.toml`)

See the configuration example above. The configuration file supports:
- Provider settings (API keys, models, timeouts)
- State management options
- Event streaming configuration
- TDD workflow settings
- Cost tracking and budgets

---

## Troubleshooting

### Tests Failing

1. Ensure virtual environment is activated
2. Verify all dependencies are installed: `pip install -e .`
3. Check Python version: `python --version` (should be 3.11+)

### API Key Errors

1. Verify `.env` file exists and contains valid API keys
2. Ensure the correct provider is configured in `adws.toml`
3. Check API key permissions and quotas

### Import Errors

1. Ensure ADWS is installed: `pip install -e .`
2. Verify you're in the project root directory
3. Check `sys.path` includes the project directory

---

## Resources

- [ADWS Documentation](https://github.com/Org-EthereaLogic/ADWS_UV_Cookiecutter_v2.0)
- [Cookiecutter Template](https://github.com/Org-EthereaLogic/ADWS_UV_Cookiecutter_v2.0)
- [Issue Tracker](https://github.com/Org-EthereaLogic/ADWS_UV_Cookiecutter_v2.0/issues)

---

## License
This project is licensed under the MIT License - see the LICENSE file for details.

---

## Author

**Your Name** <your.email@example.com>

---

Generated with ADWS UV Cookiecutter Template

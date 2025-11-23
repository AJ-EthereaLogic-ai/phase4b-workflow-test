"""
Debug script for BackendStandardWorkflow failure investigation.
"""

import asyncio
import os
import subprocess
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from adws.workflows import BackendStandardWorkflow
from adws.llm import LLMOrchestrator, LLMOrchestratorConfig
from adws.providers import ProviderRegistry
from adws.providers.interfaces import ProviderConfig
from adws.providers.implementations import (
    OpenAIProvider,
    GeminiProvider
)
from adws.providers.implementations.anthropic_direct import AnthropicProvider


def get_github_issue(issue_number: int) -> str:
    """Fetch GitHub issue body."""
    result = subprocess.run(
        ["gh", "issue", "view", str(issue_number), "--json", "body"],
        capture_output=True,
        text=True,
        check=True
    )
    issue_data = json.loads(result.stdout)
    return issue_data["body"]


async def debug_backend_workflow():
    """Debug BackendStandardWorkflow with detailed logging."""

    print("=" * 80)
    print("BACKEND STANDARD WORKFLOW DEBUG")
    print("=" * 80)

    # Setup providers
    print("\n1. Setting up providers...")
    registry = ProviderRegistry()

    if os.getenv("ANTHROPIC_API_KEY"):
        claude_config = ProviderConfig(
            name="claude",
            enabled=True,
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        claude_provider = AnthropicProvider(config=claude_config)
        registry.register("claude", claude_provider, claude_config)
        print("   ✅ Claude provider registered")

    if os.getenv("OPENAI_API_KEY"):
        openai_config = ProviderConfig(
            name="openai",
            enabled=True,
            api_key=os.getenv("OPENAI_API_KEY")
        )
        openai_provider = OpenAIProvider(config=openai_config)
        registry.register("openai", openai_provider, openai_config)
        print("   ✅ OpenAI provider registered")

    if os.getenv("GEMINI_API_KEY"):
        gemini_config = ProviderConfig(
            name="gemini",
            enabled=True,
            api_key=os.getenv("GEMINI_API_KEY")
        )
        gemini_provider = GeminiProvider(config=gemini_config)
        registry.register("gemini", gemini_provider, gemini_config)
        print("   ✅ Gemini provider registered")

    print(f"   Registered providers: {registry.list_providers()}")

    # Create orchestrator
    print("\n2. Creating LLM Orchestrator...")
    config = LLMOrchestratorConfig(
        default_provider="claude",
        default_model="claude-3-5-sonnet-20240620"
    )
    orchestrator = LLMOrchestrator(config=config, registry=registry)
    print(f"   ✅ Orchestrator created")
    print(f"   Backend route: provider={config.backend_route.provider}, model={config.backend_route.model}")

    # Fetch issue
    print("\n3. Fetching GitHub issue #1...")
    requirement = get_github_issue(1)
    print(f"   ✅ Got requirement ({len(requirement)} chars)")
    print(f"   Preview: {requirement[:200]}...")

    # Initialize workflow
    print("\n4. Initializing BackendStandardWorkflow...")
    workflow = BackendStandardWorkflow(
        orchestrator=orchestrator,
        working_dir="app/server"
    )
    print("   ✅ Workflow initialized")
    print(f"   Config backend_route: {workflow.config.backend_route}")

    # Execute workflow
    print("\n5. Executing workflow...")
    try:
        result = await workflow.execute(
            requirement=requirement,
            adw_id="debug-backend-1",
            metadata={"issue_number": "1", "debug": "true"}
        )

        print("\n6. RESULTS:")
        print(f"   Success: {result.success}")
        print(f"   Provider: {result.provider}")
        print(f"   ADW ID: {result.adw_id}")
        print(f"   Workflow: {result.workflow_name}")

        if hasattr(result, 'response_text') and result.response_text:
            print(f"\n   Response text ({len(result.response_text)} chars):")
            print(f"   {result.response_text[:500]}...")
        else:
            print(f"\n   ❌ No response text generated")

        if hasattr(result, 'output') and result.output:
            print(f"\n   Output ({len(result.output)} chars):")
            print(f"   {result.output[:500]}...")

        print(f"\n   Metadata: {result.metadata}")

        if not result.success:
            print(f"\n   ❌ FAILURE - Workflow reported success=False")
            print(f"   This means the LLM provider returned success=False")
        else:
            print(f"\n   ✅ SUCCESS")

    except Exception as e:
        print(f"\n   ❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_backend_workflow())

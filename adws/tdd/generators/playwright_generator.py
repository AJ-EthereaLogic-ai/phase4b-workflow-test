"""
Playwright E2E Test Generator

Generates end-to-end tests for user flows using Playwright.
Leverages LLM providers for intelligent test generation.
"""

from typing import List, Optional
from dataclasses import dataclass, field
from enum import Enum

from adws.providers.interfaces import PromptMessage, PromptRequest
from adws.providers.registry import ProviderRegistry


class FlowActionType(str, Enum):
    """Types of user flow actions"""

    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SELECT = "select"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    ASSERT = "assert"


@dataclass
class FlowStep:
    """A step in a user flow"""

    action: FlowActionType
    selector: Optional[str] = None
    value: Optional[str] = None
    description: str = ""


@dataclass
class UserFlow:
    """Complete user flow specification"""

    name: str
    description: str
    steps: List[FlowStep] = field(default_factory=list)
    assertions: List[str] = field(default_factory=list)


@dataclass
class GeneratedE2ETest:
    """Information about generated E2E tests"""

    test_file_path: str
    test_code: str
    test_count: int
    flow_name: str


class PlaywrightTestGenerator:
    """
    Generates Playwright E2E tests for user flows.

    Uses LLM providers to generate comprehensive end-to-end tests covering:
    - User navigation flows
    - Form interactions
    - Multi-step processes
    - Visual regression (screenshots)
    - Cross-browser compatibility

    Example:
        >>> registry = ProviderRegistry()
        >>> # ... register providers
        >>> generator = PlaywrightTestGenerator(registry)
        >>> flow = UserFlow(name="Login Flow", description="User login process")
        >>> flow.steps = [...]
        >>> test = await generator.generate_e2e_test(flow)
        >>> print(test.test_code)
    """

    def __init__(self, provider_registry: ProviderRegistry):
        """
        Initialize Playwright test generator.

        Args:
            provider_registry: Registry of available LLM providers
        """
        self.provider_registry = provider_registry

    async def generate_e2e_test(self, user_flow: UserFlow) -> GeneratedE2ETest:
        """
        Generate Playwright E2E test for a user flow.

        Args:
            user_flow: User flow specification

        Returns:
            GeneratedE2ETest with test code and metadata

        Raises:
            ValueError: If no provider is available
        """
        provider = self.provider_registry.get("anthropic")
        if not provider:
            raise ValueError("No LLM provider available")

        # Format steps for prompt
        steps_str = "\n".join(
            [
                f"{i + 1}. {step.action}: {step.description}"
                for i, step in enumerate(user_flow.steps)
            ]
        )

        assertions_str = "\n".join(user_flow.assertions)

        prompt = f"""Generate a Playwright E2E test for the following user flow.

User Flow: {user_flow.name}
Description: {user_flow.description}

Steps:
{steps_str}

Assertions:
{assertions_str}

Requirements:
1. Use Playwright test API with async/await
2. Use page.goto(), page.click(), page.fill(), page.locator(), etc.
3. Include all specified assertions
4. Add screenshots for key steps
5. Use descriptive test names
6. Handle waiting for elements and network requests
7. Add proper error handling

Output ONLY the test code (include imports and test.describe block)."""

        request = PromptRequest(
            prompt=prompt,
            model="claude-sonnet-4-5",
            max_tokens=3000,
            temperature=0.3,
            adw_id=f"e2e::playwright::{user_flow.name}",
            slash_command="/generate_e2e_tests",
            working_dir="tests/e2e",
            metadata={
                "generator": "playwright",
                "flow_name": user_flow.name,
                "step_count": len(user_flow.steps),
            },
            messages=self._build_prompt_messages(prompt),
        )

        response = await provider.execute(request)
        test_code = self._extract_test_code(response.output)

        # Wrap in test file structure if not already present
        if "import" not in test_code:
            test_code = self._render_e2e_test_file(user_flow, test_code)

        test_file_path = self._get_test_file_path(user_flow.name)
        test_count = self._count_tests(test_code)

        return GeneratedE2ETest(
            test_file_path=test_file_path,
            test_code=test_code,
            test_count=test_count,
            flow_name=user_flow.name,
        )

    async def generate_from_steps(
        self,
        flow_name: str,
        description: str,
        steps: List[FlowStep],
        assertions: Optional[List[str]] = None,
    ) -> GeneratedE2ETest:
        """
        Generate E2E test from flow steps.

        Args:
            flow_name: Name of the flow
            description: Flow description
            steps: List of flow steps
            assertions: Optional list of assertions

        Returns:
            GeneratedE2ETest with test code and metadata
        """
        user_flow = UserFlow(
            name=flow_name,
            description=description,
            steps=steps,
            assertions=assertions or [],
        )

        return await self.generate_e2e_test(user_flow)

    def _build_prompt_messages(self, user_prompt: str) -> List[PromptMessage]:
        system_content = (
            "You are a senior QA engineer generating reliable Playwright tests "
            "with descriptive assertions and proper waiting."
        )
        return [
            PromptMessage(role="system", content=system_content),
            PromptMessage(role="user", content=user_prompt),
        ]

    def _render_e2e_test_file(self, user_flow: UserFlow, test_code: str) -> str:
        """Render complete E2E test file"""
        return f"""import {{ test, expect }} from '@playwright/test';

test.describe('{user_flow.name}', () => {{
  {test_code}
}});
"""

    def _extract_test_code(self, response: str) -> str:
        """Extract test code from LLM response"""
        code = response

        # Remove code fences if present
        if "```typescript" in code or "```ts" in code:
            code = (
                code.split("```typescript")[1]
                if "```typescript" in code
                else code.split("```ts")[1]
            )
            code = code.split("```")[0]
        elif "```javascript" in code or "```js" in code:
            code = (
                code.split("```javascript")[1]
                if "```javascript" in code
                else code.split("```js")[1]
            )
            code = code.split("```")[0]
        elif "```" in code:
            code = code.split("```")[1].split("```")[0]

        return code.strip()

    def _get_test_file_path(self, flow_name: str) -> str:
        """Generate test file path from flow name"""
        # Convert "Login Flow" -> "login-flow.spec.ts"
        filename = flow_name.lower().replace(" ", "-") + ".spec.ts"
        return f"tests/e2e/{filename}"

    def _count_tests(self, test_code: str) -> int:
        """Count number of test cases in code"""
        return test_code.count("test(") + test_code.count("test.step(")

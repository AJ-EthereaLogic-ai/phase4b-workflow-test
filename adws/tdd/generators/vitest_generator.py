"""
Vitest Test Generator

Generates fast unit tests for React hooks and utility functions using Vitest.
Leverages LLM providers for intelligent test generation.
"""

from pathlib import Path
from typing import List
from dataclasses import dataclass

from adws.providers.interfaces import PromptMessage, PromptRequest
from adws.providers.registry import ProviderRegistry


@dataclass
class GeneratedVitestTest:
    """Information about generated Vitest tests"""

    test_file_path: str
    test_code: str
    test_count: int
    coverage_estimate: float
    quality_score: float


@dataclass
class HookInfo:
    """Information about a React hook"""

    name: str
    file_path: str
    parameters: List[str]
    return_type: str
    dependencies: List[str]


@dataclass
class UtilityInfo:
    """Information about a utility function"""

    name: str
    file_path: str
    parameters: List[str]
    return_type: str


class VitestTestGenerator:
    """
    Generates Vitest tests for React hooks and utility functions.

    Uses LLM providers to generate fast, focused unit tests for:
    - Custom React hooks
    - Utility functions
    - Helper functions
    - Pure functions

    Example:
        >>> registry = ProviderRegistry()
        >>> # ... register providers
        >>> generator = VitestTestGenerator(registry)
        >>> hook_info = HookInfo(name="useCounter", ...)
        >>> test = await generator.generate_hook_tests(hook_info)
        >>> print(test.test_code)
    """

    def __init__(self, provider_registry: ProviderRegistry):
        """
        Initialize Vitest test generator.

        Args:
            provider_registry: Registry of available LLM providers
        """
        self.provider_registry = provider_registry

    async def generate_hook_tests(
        self, hook_info: HookInfo
    ) -> GeneratedVitestTest:
        """
        Generate Vitest tests for a custom React hook.

        Args:
            hook_info: Information about the hook to test

        Returns:
            GeneratedVitestTest with test code and metadata

        Raises:
            ValueError: If no provider is available
        """
        provider = self.provider_registry.get("anthropic")
        if not provider:
            raise ValueError("No LLM provider available")

        prompt = f"""Generate Vitest tests for a custom React hook.

Hook Name: {hook_info.name}
Parameters: {', '.join(hook_info.parameters) if hook_info.parameters else 'none'}
Return Type: {hook_info.return_type}
Dependencies: {', '.join(hook_info.dependencies) if hook_info.dependencies else 'none'}

Requirements:
1. Use @testing-library/react-hooks (renderHook)
2. Test hook initialization
3. Test hook updates and state changes
4. Test edge cases and error conditions
5. Use Vitest API (test, expect, vi)
6. Use descriptive test names

Output ONLY the test code (include imports and describe block)."""

        request = PromptRequest(
            prompt=prompt,
            model="claude-sonnet-4-5",
            max_tokens=2500,
            temperature=0.3,
            adw_id=f"frontend::vitest::hook::{hook_info.name}",
            slash_command="/generate_vitest_tests",
            working_dir=str(Path(hook_info.file_path).parent),
            metadata={
                "generator": "vitest",
                "type": "hook",
                "name": hook_info.name,
                "file_path": hook_info.file_path,
            },
            messages=self._build_prompt_messages(prompt),
        )

        response = await provider.execute(request)
        test_code = self._extract_test_code(response.output)

        test_file_path = self._get_test_file_path(hook_info.file_path)
        test_count = self._count_tests(test_code)
        coverage_estimate = 85.0  # Hooks typically have high coverage
        quality_score = self._calculate_quality_score(test_code)

        return GeneratedVitestTest(
            test_file_path=test_file_path,
            test_code=test_code,
            test_count=test_count,
            coverage_estimate=coverage_estimate,
            quality_score=quality_score,
        )

    async def generate_utility_tests(
        self, utility_info: UtilityInfo
    ) -> GeneratedVitestTest:
        """
        Generate Vitest tests for a utility function.

        Args:
            utility_info: Information about the utility function

        Returns:
            GeneratedVitestTest with test code and metadata

        Raises:
            ValueError: If no provider is available
        """
        provider = self.provider_registry.get("anthropic")
        if not provider:
            raise ValueError("No LLM provider available")

        prompt = f"""Generate Vitest tests for a utility function.

Function Name: {utility_info.name}
Parameters: {', '.join(utility_info.parameters) if utility_info.parameters else 'none'}
Return Type: {utility_info.return_type}

Requirements:
1. Test normal operation with valid inputs
2. Test edge cases (empty, null, undefined, boundary values)
3. Test error conditions
4. Use Vitest API (test, expect, vi)
5. Use descriptive test names
6. Include test cases for type safety

Output ONLY the test code (include imports and describe block)."""

        request = PromptRequest(
            prompt=prompt,
            model="claude-sonnet-4-5",
            max_tokens=2000,
            temperature=0.3,
            adw_id=f"frontend::vitest::utility::{utility_info.name}",
            slash_command="/generate_vitest_tests",
            working_dir=str(Path(utility_info.file_path).parent),
            metadata={
                "generator": "vitest",
                "type": "utility",
                "name": utility_info.name,
                "file_path": utility_info.file_path,
            },
            messages=self._build_prompt_messages(prompt),
        )

        response = await provider.execute(request)
        test_code = self._extract_test_code(response.output)

        test_file_path = self._get_test_file_path(utility_info.file_path)
        test_count = self._count_tests(test_code)
        coverage_estimate = 90.0  # Utilities typically have very high coverage
        quality_score = self._calculate_quality_score(test_code)

        return GeneratedVitestTest(
            test_file_path=test_file_path,
            test_code=test_code,
            test_count=test_count,
            coverage_estimate=coverage_estimate,
            quality_score=quality_score,
        )

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

    def _build_prompt_messages(self, user_prompt: str) -> List[PromptMessage]:
        system_content = (
            "You are a senior frontend engineer who specializes in writing Vitest "
            "unit tests with thorough edge-case coverage."
        )
        return [
            PromptMessage(role="system", content=system_content),
            PromptMessage(role="user", content=user_prompt),
        ]

    def _get_test_file_path(self, source_file_path: str) -> str:
        """Generate test file path from source file path"""
        path = Path(source_file_path)
        test_filename = path.stem + ".test" + path.suffix
        test_dir = path.parent / "__tests__"
        return str(test_dir / test_filename)

    def _count_tests(self, test_code: str) -> int:
        """Count number of test cases in code"""
        # Count 'test(' or 'it(' occurrences
        return test_code.count("test(") + test_code.count("it(")

    def _calculate_quality_score(self, test_code: str) -> float:
        """Calculate quality score for generated tests"""
        score = 0.0

        # Check for assertions
        if "expect(" in test_code:
            score += 0.3

        # Check for edge cases
        if any(
            keyword in test_code.lower()
            for keyword in ["edge case", "boundary", "null", "undefined", "empty"]
        ):
            score += 0.25

        # Check for error handling tests
        if "toThrow" in test_code or "error" in test_code.lower():
            score += 0.2

        # Check for descriptive test names
        if "describe" in test_code or "it(" in test_code or "test(" in test_code:
            score += 0.15

        # Check for mocking
        if "vi.fn" in test_code or "vi.mock" in test_code:
            score += 0.1

        return min(1.0, score)

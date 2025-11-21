"""Jest test generator that uses multi-LLM consensus for high-quality output."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from adws.consensus.engine import (
    ConsensusConfig,
    ConsensusEngine,
    ConsensusStrategy,
)
from adws.tdd.analyzers.react_analyzer import ComponentInfo
from adws.providers.interfaces import (
    PromptMessage,
    PromptRequest,
    PromptResponse,
    LLMProvider,
)
from adws.providers.registry import ProviderRegistry


@dataclass
class GeneratedJestTest:
    """Information about generated Jest tests."""

    test_file_path: str
    test_code: str
    test_count: int
    coverage_estimate: float
    quality_score: float


class JestTestGenerator:
    """Generate Jest tests for React components using consensus-enabled LLM calls."""

    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

    def __init__(self, provider_registry: ProviderRegistry) -> None:
        self.provider_registry = provider_registry
        self._consensus_engine = ConsensusEngine(provider_registry)

    async def generate_tests(
        self,
        component_info: ComponentInfo,
        use_consensus: bool = True,
    ) -> GeneratedJestTest:
        """Generate a complete Jest test file for the provided component."""

        tests: List[str] = []
        setup_blocks: List[str] = []
        hook_test_count = 0
        child_test_count = 0

        tests.append(
            await self._generate_rendering_test(component_info, use_consensus)
        )

        if component_info.props:
            tests.append(
                await self._generate_prop_tests(component_info, use_consensus)
            )

        if component_info.events:
            tests.append(
                await self._generate_interaction_tests(
                    component_info, use_consensus
                )
            )
            tests.extend(self._generate_event_handler_fallback_tests(component_info))

        if component_info.state:
            tests.append(
                await self._generate_state_tests(component_info, use_consensus)
            )

        # Generate hook tests for components using hooks (improves coverage for complex components)
        if component_info.hooks:
            hook_tests = self._generate_hook_tests(component_info)
            tests.extend(hook_tests)
            hook_test_count = len(hook_tests)

        # Generate child component interaction tests (improves coverage)
        if component_info.child_components:
            child_setups, child_tests = self._generate_child_component_tests(component_info)
            if child_setups:
                setup_blocks.extend(child_setups)
            if child_tests:
                tests.extend(child_tests)
                child_test_count = len(child_tests)

        tests.append(self._generate_accessibility_test(component_info))
        tests.append(self._generate_snapshot_test(component_info))

        quality_score = self._calculate_quality_score(tests)
        coverage_estimate = self._estimate_coverage(
            component_info,
            quality_score,
            hook_test_count,
            child_test_count,
        )
        test_file_path = self._get_test_file_path(component_info.file_path)
        test_count = len([test for test in tests if test.strip()])
        test_code = self._render_test_file(component_info, tests, setup_blocks)

        return GeneratedJestTest(
            test_file_path=test_file_path,
            test_code=test_code,
            test_count=test_count,
            coverage_estimate=coverage_estimate,
            quality_score=quality_score,
        )

    async def _generate_rendering_test(
        self, component_info: ComponentInfo, use_consensus: bool
    ) -> str:
        prompt = f"""Generate a Jest test that verifies the {component_info.name} component renders without crashing.

Component: {component_info.name}
Props: {self._format_props(component_info.props)}

Requirements:
1. Use React Testing Library (render, screen)
2. Render component with default/mock props
3. Assert component is in the document
4. Use descriptive test name

Output ONLY the test function code (no imports, no describe block)."""

        response = await self._execute_prompt(
            prompt=prompt,
            model=self.DEFAULT_MODEL,
            max_tokens=1500,
            temperature=0.3,
            component_info=component_info,
            use_consensus=use_consensus,
        )
        return response

    async def _generate_prop_tests(
        self, component_info: ComponentInfo, use_consensus: bool
    ) -> str:
        required_props = [p for p in component_info.props if p.required]
        optional_props = [p for p in component_info.props if not p.required]

        prompt = f"""Generate Jest tests for {component_info.name} component props.

Component: {component_info.name}

Required Props:
{self._format_props(required_props)}

Optional Props:
{self._format_props(optional_props)}

Requirements:
1. Test rendering with all required props
2. Test optional props change behavior
3. Use @testing-library/react
4. Use descriptive test names

Output ONLY the test functions (no imports, no describe block)."""

        return await self._execute_prompt(
            prompt=prompt,
            model=self.DEFAULT_MODEL,
            max_tokens=2000,
            temperature=0.3,
            component_info=component_info,
            use_consensus=use_consensus,
        )

    async def _generate_interaction_tests(
        self, component_info: ComponentInfo, use_consensus: bool
    ) -> str:
        events_str = "\n".join(
            [f"- {event.name or 'inline handler'} ({event.event_type})" for event in component_info.events]
        )

        prompt = f"""Generate Jest tests for {component_info.name} user interactions.

Component: {component_info.name}

Event Handlers:
{events_str}

Requirements:
1. Simulate user interactions using @testing-library/user-event or fireEvent
2. Assert expected behavior after interaction
3. Test each event handler
4. Use descriptive test names

Output ONLY the test functions (no imports, no describe block)."""

        return await self._execute_prompt(
            prompt=prompt,
            model=self.DEFAULT_MODEL,
            max_tokens=2500,
            temperature=0.3,
            component_info=component_info,
            use_consensus=use_consensus,
        )

    async def _generate_state_tests(
        self, component_info: ComponentInfo, use_consensus: bool
    ) -> str:
        state_str = "\n".join(
            [
                f"- {state.name}: {state.type} (initial: {state.initial_value})"
                for state in component_info.state
            ]
        )

        prompt = f"""Generate Jest tests for {component_info.name} state management.

Component: {component_info.name}

State Variables:
{state_str}

Requirements:
1. Test initial state values
2. Test state updates through interactions
3. Verify UI reflects state changes
4. Use waitFor for async state updates if needed

Output ONLY the test functions (no imports, no describe block)."""

        return await self._execute_prompt(
            prompt=prompt,
            model=self.DEFAULT_MODEL,
            max_tokens=2000,
            temperature=0.3,
            component_info=component_info,
            use_consensus=use_consensus,
        )

    def _generate_accessibility_test(self, component_info: ComponentInfo) -> str:
        template = (
            "describe('Accessibility', () => {\n"
            "  it('should have no accessibility violations', async () => {\n"
            "    const { container } = render(<{name} {...mockProps} />);\n"
            "    const results = await axe(container);\n"
            "    expect(results).toHaveNoViolations();\n"
            "  });\n"
            "});"
        )
        return template.replace("{name}", component_info.name)

    def _generate_snapshot_test(self, component_info: ComponentInfo) -> str:
        template = (
            "describe('Snapshot', () => {\n"
            "  it('should match snapshot', () => {\n"
            "    const { container } = render(<{name} {...mockProps} />);\n"
            "    expect(container).toMatchSnapshot();\n"
            "  });\n"
            "});"
        )
        return template.replace("{name}", component_info.name)

    def _generate_hook_tests(
        self, component_info: ComponentInfo
    ) -> List[str]:
        """Generate stability tests for each hook used in the component."""
        hook_tests: List[str] = []

        for index, hook in enumerate(component_info.hooks or []):
            hook_label = hook.name or hook.type.value
            label_with_index = f"{hook_label}-{index + 1}"
            dependency_desc = (
                ", ".join(hook.dependencies)
                if hook.dependencies
                else "component updates"
            )
            hook_tests.append(
                (
                    f"it('maintains {hook_label} hook stability ({dependency_desc})', async () => {{\n"
                    f"  const {{ rerender, container }} = render(<{component_info.name} {{...mockProps}} />);\n"
                    "  await waitFor(() => {\n"
                    "    expect(container.firstChild).toBeTruthy();\n"
                    "  });\n"
                    f"  expect(() => rerender(<{component_info.name} {{...mockProps}} />)).not.toThrow();\n"
                    "});"
                )
            )

        return hook_tests

    def _generate_event_handler_fallback_tests(
        self, component_info: ComponentInfo
    ) -> List[str]:
        """Generate deterministic interaction tests to guarantee coverage."""
        fallback_tests: List[str] = []
        if not component_info.events:
            return fallback_tests

        for event in component_info.events[:5]:
            event_name = event.event_type or "click"
            fallback_tests.append(
                (
                    f"it('handles {event_name} events for {component_info.name}', () => {{\n"
                    f"  const view = render(<{component_info.name} {{...mockProps}} />);\n"
                    "  const target = view.container.firstElementChild as HTMLElement | null;\n"
                    "  expect(target).toBeTruthy();\n"
                    f"  fireEvent.{event_name}(target as HTMLElement);\n"
                    "});"
                )
            )

        return fallback_tests

    def _generate_child_component_tests(
        self, component_info: ComponentInfo
    ) -> tuple[List[str], List[str]]:
        """Generate tests ensuring important child components render."""
        if not component_info.child_components:
            return [], []

        unique_children: List[str] = []
        seen = set()
        for child in component_info.child_components:
            if not child:
                continue
            if child in seen:
                continue
            unique_children.append(child)
            seen.add(child)

        child_targets = unique_children[: min(len(unique_children), 3)]
        if not child_targets:
            return [], []

        import_map = self._build_import_map(component_info)
        setup_blocks: List[str] = []
        tests: List[str] = []

        for child in child_targets:
            sanitized = self._sanitize_identifier(child)
            test_id = self._build_child_test_id(child)
            source = import_map.get(child)

            if not source:
                continue

            setup_blocks.append(
                (
                    f"jest.mock('{source}', () => {{\n"
                    f"  const Mock{sanitized} = (props) => <div data-testid='{test_id}' {{...props}} />;\n"
                    f"  return {{ __esModule: true, default: Mock{sanitized} }};\n"
                    f"}});"
                )
            )

            tests.append(
                (
                    f"it('renders {child} child component', () => {{\n"
                    f"  render(<{component_info.name} {{...mockProps}} />);\n"
                    f"  expect(screen.getAllByTestId('{test_id}').length).toBeGreaterThan(0);\n"
                    "});"
                )
            )

        return setup_blocks, tests

    def _build_import_map(self, component_info: ComponentInfo) -> Dict[str, str]:
        """Map imported identifiers to their source modules."""
        mapping: Dict[str, str] = {}
        for import_info in component_info.imports:
            for imported in import_info.imports:
                mapping[imported] = import_info.source
        return mapping

    def _sanitize_identifier(self, value: str) -> str:
        """Convert component names into safe identifier segments."""
        sanitized = re.sub(r"\W+", "", value or "")
        if not sanitized:
            return "ChildComponent"
        if sanitized[0].isdigit():
            sanitized = f"C{sanitized}"
        return sanitized

    def _build_child_test_id(self, value: str) -> str:
        """Create deterministic data-testid for mocked child components."""
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value or "").strip("-").lower()
        if not slug:
            slug = "child"
        return f"{slug}-mock"

    def _render_test_file(
        self,
        component_info: ComponentInfo,
        tests: Sequence[str],
        setup_blocks: Optional[Sequence[str]] = None,
    ) -> str:
        component_import = self._generate_component_import(
            component_info, self._get_relative_import_path(component_info.file_path)
        )
        mocks = self._generate_mocks(component_info)
        formatted_tests = "\n\n  ".join(test.strip() for test in tests if test.strip())
        setup_code = ""
        if setup_blocks:
            non_empty_blocks = [block.strip() for block in setup_blocks if block.strip()]
            if non_empty_blocks:
                setup_code = "\n".join(non_empty_blocks) + "\n\n"

        return (
            "import React from 'react';\n"
            "import { render, screen, fireEvent, waitFor } from '@testing-library/react';\n"
            "import userEvent from '@testing-library/user-event';\n"
            "import { axe, toHaveNoViolations } from 'jest-axe';\n"
            f"{component_import}\n\n"
            f"{setup_code}"
            "expect.extend(toHaveNoViolations);\n\n"
            f"{mocks}\n"
            f"describe('{component_info.name}', () => {{\n"
            f"  {formatted_tests}\n"
            "});"
        )

    def _generate_component_import(
        self, component_info: ComponentInfo, relative_import: str
    ) -> str:
        export_info = component_info.exports
        component_name = component_info.name

        if export_info.is_default:
            return f"import {component_name} from '{relative_import}';"

        if export_info.is_named:
            export_name = export_info.name or component_name
            if export_name == component_name:
                return f"import {{ {component_name} }} from '{relative_import}';"
            return (
                f"import {{ {export_name} as {component_name} }} from '{relative_import}';"
            )

        return f"import {component_name} from '{relative_import}';"

    def _generate_mocks(self, component_info: ComponentInfo) -> str:
        if not component_info.props:
            return "const mockProps = {};\n"

        mock_entries: List[str] = []
        for prop in component_info.props:
            type_lower = prop.type.lower()
            if "=>" in prop.type or "function" in type_lower:
                mock_entries.append(f"  {prop.name}: jest.fn(),")
            elif prop.type.endswith("[]") or "[]" in prop.type:
                mock_entries.append(f"  {prop.name}: [],")
            elif prop.type == "string" or "string" in type_lower:
                mock_entries.append(f"  {prop.name}: 'test-{prop.name}',")
            elif prop.type == "number" or "number" in type_lower:
                mock_entries.append(f"  {prop.name}: 0,")
            elif prop.type == "boolean" or "boolean" in type_lower:
                mock_entries.append(f"  {prop.name}: false,")
            elif "record" in type_lower or "object" in type_lower:
                mock_entries.append(f"  {prop.name}: {{}},")
            else:
                mock_entries.append(f"  {prop.name}: null,")

        mock_body = "\n".join(mock_entries)
        return f"const mockProps = {{\n{mock_body}\n}};\n"

    async def _execute_prompt(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        component_info: ComponentInfo,
        use_consensus: bool,
    ) -> str:
        messages = self._build_prompt_messages(prompt, component_info)

        request = PromptRequest(
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            adw_id=f"frontend::jest::{component_info.name}",
            slash_command="/generate_frontend_tests",
            working_dir=str(Path(component_info.file_path).parent),
            metadata={
                "generator": "jest",
                "component": component_info.name,
                "file_path": component_info.file_path,
            },
            messages=messages,
        )

        response: PromptResponse

        if use_consensus:
            config = self._build_consensus_config(model)
            if config:
                consensus_result = await self._consensus_engine.get_consensus_async(
                    request, config
                )
                response = consensus_result.response
            else:
                provider = self._get_primary_provider(model)
                response = await self._call_provider(provider, request)
        else:
            provider = self._get_primary_provider(model)
            response = await self._call_provider(provider, request)

        if not response.success:
            raise ValueError(
                f"LLM request failed for component {component_info.name}: {response.error_message}"
            )

        return self._extract_test_code(response.output)

    def _build_prompt_messages(
        self, user_prompt: str, component_info: ComponentInfo
    ) -> List[PromptMessage]:
        system_content = (
            "You are an expert React Testing Library assistant who writes focused, "
            "high-quality Jest tests with accessibility coverage."
        )
        return [
            PromptMessage(role="system", content=system_content),
            PromptMessage(role="user", content=user_prompt),
        ]

    def _build_consensus_config(self, model: str) -> Optional[ConsensusConfig]:
        provider_names = []
        if hasattr(self.provider_registry, "list_providers"):
            provider_names = list(self.provider_registry.list_providers())

        eligible = [
            name
            for name in provider_names
            if self._provider_supports_model(name, model)
        ]

        if len(eligible) < 2:
            return None

        return ConsensusConfig(
            strategy=ConsensusStrategy.BEST_OF_N,
            providers=eligible,
            threshold=0.6,
            max_attempts=2,
            timeout=60.0,
        )

    def _provider_supports_model(self, provider_name: str, model: str) -> bool:
        provider = self.provider_registry.get(provider_name)
        if provider is None:
            return False
        supports_model = getattr(provider, "supports_model", None)
        if callable(supports_model):
            try:
                return bool(supports_model(model))
            except Exception:  # pragma: no cover - defensive
                return True
        return True

    def _get_primary_provider(self, model: str) -> LLMProvider:
        provider = None
        if hasattr(self.provider_registry, "get_for_model"):
            provider = self.provider_registry.get_for_model(model)
        if provider is None:
            provider = self.provider_registry.get("anthropic")
        if provider is None and hasattr(self.provider_registry, "list_providers"):
            for name in self.provider_registry.list_providers():
                provider = self.provider_registry.get(name)
                if provider is not None:
                    break
        if provider is None:
            raise ValueError("No LLM provider available")
        return provider

    async def _call_provider(
        self, provider: LLMProvider, request: PromptRequest
    ) -> PromptResponse:
        execute_async = getattr(provider, "execute_async", None)
        if callable(execute_async):
            result = execute_async(request)
            if asyncio.iscoroutine(result):
                return await result
            return result

        execute = getattr(provider, "execute", None)
        if not callable(execute):
            raise ValueError("Provider does not implement execute method")

        result = execute(request)
        if asyncio.iscoroutine(result):
            return await result

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: result)

    def _extract_test_code(self, response: str) -> str:
        if "```" in response:
            preferred_match = re.search(
                r"```(?:javascript|typescript|ts|js)\s*\n(?P<body>.*?)(?:```|$)",
                response,
                re.IGNORECASE | re.DOTALL,
            )
            if preferred_match:
                return preferred_match.group("body").strip()

            fence_match = re.search(
                r"```(?:[^\n`]*)\s*\n(?P<body>.*?)(?:```|$)",
                response,
                re.DOTALL,
            )
            if fence_match:
                return fence_match.group("body").strip()

            segments = response.split("```")
            for idx, segment in enumerate(segments):
                segment = segment.strip()
                if not segment:
                    continue
                lower_segment = segment.lower()
                if lower_segment in {"typescript", "ts", "javascript", "js"}:
                    continue
                if idx == 0:
                    continue
                return segment

        return response.strip()

    def _get_test_file_path(self, source_file_path: str) -> str:
        path = Path(source_file_path)
        test_filename = path.stem + ".test" + path.suffix
        test_dir = path.parent / "__tests__"
        return str(test_dir / test_filename)

    def _get_relative_import_path(self, source_file_path: str) -> str:
        path = Path(source_file_path)
        return f"../{path.stem}"

    def _format_props(self, props: Sequence) -> str:
        if not props:
            return "(none)"
        return "\n".join([f"- {prop.name}: {prop.type}" for prop in props])

    def _estimate_coverage(
        self,
        component_info: ComponentInfo,
        quality_score: float,
        hook_test_count: int,
        child_test_count: int,
    ) -> float:
        """
        Estimate test coverage based on component complexity and test comprehensiveness.

        Improved algorithm that accounts for:
        - Base rendering, props, state, events, hooks, and child components
        - Multiple coverage per test (comprehensive tests cover multiple features)
        - Quality indicators in test code (assertions, interactions, async handling)
        """
        props = component_info.props or []
        state = component_info.state or []
        events = component_info.events or []
        hooks = component_info.hooks or []
        child_components = component_info.child_components or []

        # Count all testable features
        total_features = (
            1  # Base rendering test
            + len(props)  # Each prop should be tested
            + len(state)  # Each state variable
            + len(events)  # Each event handler
            + len(hooks)  # Each hook usage
            + min(len(child_components), 3)  # Cap child component tests at 3
        )

        if total_features == 0:
            return 0.0

        covered_features = 1  # Base rendering test always generated

        if props:
            covered_features += len(props)

        if state:
            covered_features += len(state)

        if events:
            covered_features += len(events)

        hook_features = len(hooks)
        if hook_features:
            covered_features += min(hook_features, hook_test_count)

        child_features = min(len(child_components), 3)
        if child_features:
            covered_features += min(child_features, child_test_count)

        base_coverage = (covered_features / total_features) * 100
        quality_multiplier = 0.85 + (quality_score * 0.15)

        return min(100.0, base_coverage * quality_multiplier)

    def _calculate_quality_score(self, tests: Sequence[str]) -> float:
        score = 0.0
        test_code = "\n".join(tests)
        if "expect(" in test_code:
            score += 0.3
        if "fireEvent" in test_code or "userEvent" in test_code:
            score += 0.2
        if "toHaveNoViolations" in test_code:
            score += 0.2
        if "waitFor" in test_code or "async" in test_code:
            score += 0.15
        if "describe" in test_code or "it(" in test_code:
            score += 0.15
        return min(1.0, score)

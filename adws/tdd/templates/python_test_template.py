"""Helper templates for generated pytest suites."""

from __future__ import annotations

import json
from textwrap import dedent, indent
from typing import Iterable, Sequence

from adws.tdd.models import ClassInfo, FunctionInfo, ModuleAnalysis, TestScenario


def render_file_header(analysis: ModuleAnalysis, scenarios: Sequence[TestScenario]) -> str:
    """Return file docstring summarizing coverage."""

    scenario_lines = [
        f"- {scenario.summary()}" for scenario in scenarios
    ] or ["- ad-hoc exploration scenario"]

    return dedent(
        f'''"""
Auto-generated pytest suite for ``{analysis.import_path}``.

Scenarios:
{chr(10).join(scenario_lines)}
"""
'''
    ).rstrip()


def render_import_block(analysis: ModuleAnalysis) -> str:
    """Render import statements for target module."""

    targets: list[str] = [func.name for func in analysis.functions]
    targets.extend(cls.name for cls in analysis.classes)

    if targets:
        targets_str = ", ".join(sorted(set(targets)))
        return f"from {analysis.import_path} import {targets_str}"

    return f"import {analysis.import_path}"


def _build_call_expression(function: FunctionInfo) -> str:
    args = []
    for param in function.parameters:
        if param.name == "self":
            continue
        placeholder = "0"
        annotation = (param.annotation or "").lower()
        if "str" in annotation:
            placeholder = f"'{param.name}_value'"
        elif "bool" in annotation:
            placeholder = "False"
        elif "list" in annotation:
            placeholder = "[]"
        elif "dict" in annotation:
            placeholder = "{}"
        args.append(f"{param.name}={placeholder}")

    return f"{function.name}({', '.join(args)})"


def render_function_test(function: FunctionInfo, scenario_hint: str | None = None) -> str:
    """Render skeleton test for a function."""

    call_expression = _build_call_expression(function)
    act_line = f"result = {call_expression}"
    if function.is_async:
        act_line = f"result = await {call_expression}"

    decorator = "@pytest.mark.asyncio\n" if function.is_async else ""
    doc = function.docstring.splitlines()[0] if function.docstring else "Auto-generated"
    hint_comment = f"    # Scenario: {scenario_hint}\n" if scenario_hint else ""

    body = f"""
{decorator}def test_{function.name}_returns_expected_result():
    \"\"\"{doc}.\"\"\"
{hint_comment}    # Arrange
    # Placeholder values below are for template purposes; replace with realistic inputs as needed.
    # Act
    {act_line}
    # Assert
    assert result is not None
""".rstrip()

    return body


def render_edge_case_test(function: FunctionInfo, cases: Sequence[dict]) -> str:
    """Render parametrized edge case test."""

    payload = indent(",\n".join(json.dumps(case, sort_keys=True) for case in cases), " " * 8)
    call_expression = f"{function.name}(**case)"
    if function.is_async:
        call_expression = f"await {call_expression}"

    decorator = "@pytest.mark.asyncio\n" if function.is_async else ""

    return dedent(
        f"""
@pytest.mark.parametrize("case", [
        {payload}
])
{decorator}def test_{function.name}_edge_cases(case):
    \"\"\"Auto-generated edge case coverage.\"\"\"
    result = {call_expression}
    assert result is not None
"""
    ).rstrip()


def render_class_test(cls: ClassInfo) -> str:
    """Render smoke test for a class."""

    method = cls.methods[0] if cls.methods else None
    invocation = "instance"
    if method:
        args = ", ".join(
            f"{param.name}=0" for param in method.parameters if param.name != "self"
        )
        call = f"instance.{method.name}({args})" if args else f"instance.{method.name}()"
        invocation = call

    return dedent(
        f"""
def test_{cls.name.lower()}_basic_flow():
    \"\"\"Automatically generated smoke test for {cls.name}.\"\"\"
    instance = {cls.name}()
    result = {invocation}
    assert hasattr(instance, '__class__')
    assert result is None or result is not NotImplemented
"""
    ).rstrip()


def assemble_test_file(
    analysis: ModuleAnalysis,
    test_blocks: Iterable[str],
    scenarios: Sequence[TestScenario],
) -> str:
    """Assemble full test file contents."""

    header = render_file_header(analysis, scenarios)
    imports = render_import_block(analysis)
    body = "\n\n\n".join(block.strip() for block in test_blocks if block.strip())

    return dedent(
        f"""
{header}

import pytest

{imports}


{body}
"""
    ).strip() + "\n"


__all__ = [
    "assemble_test_file",
    "render_class_test",
    "render_edge_case_test",
    "render_file_header",
    "render_function_test",
    "render_import_block",
]

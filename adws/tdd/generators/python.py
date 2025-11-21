"""AST-driven pytest generation for Python modules."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from adws.tdd.exceptions import TestGenerationError
from adws.tdd.models import (
    ClassInfo,
    FunctionInfo,
    GeneratedPythonTest,
    ModuleAnalysis,
    ParameterInfo,
    TestScenario,
)
from adws.tdd.templates import python_test_template as template


def _safe_unparse(node: ast.AST | None) -> Optional[str]:
    if node is None:
        return None
    try:  # Python 3.11+
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive
        return None


class PythonCodeAnalyzer(ast.NodeVisitor):
    """Extract functions/classes from a Python module."""

    def __init__(self, module_path: Path):
        self.module_path = Path(module_path)
        self._functions: List[FunctionInfo] = []
        self._classes: List[ClassInfo] = []
        self._class_stack: list[ClassInfo] = []

    def analyze(self) -> ModuleAnalysis:
        if not self.module_path.exists():
            raise FileNotFoundError(f"Module not found: {self.module_path}")

        tree = ast.parse(self.module_path.read_text(encoding="utf-8"))
        self.visit(tree)

        return ModuleAnalysis(
            module_path=self.module_path,
            import_path=self._infer_import_path(),
            functions=self._functions,
            classes=self._classes,
        )

    # Visitor overrides -------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record_function(node, is_async=True)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        class_info = ClassInfo(
            name=node.name,
            docstring=ast.get_docstring(node),
        )
        self._class_stack.append(class_info)
        self.generic_visit(node)
        self._class_stack.pop()
        self._classes.append(class_info)

    # Helpers -----------------------------------------------------------

    def _record_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        is_async: bool,
    ) -> None:
        params = self._build_parameters(node.args)
        info = FunctionInfo(
            name=node.name,
            parameters=params,
            return_annotation=_safe_unparse(node.returns),
            docstring=ast.get_docstring(node),
            is_async=is_async,
            parent_class=self._class_stack[-1].name if self._class_stack else None,
        )

        if self._class_stack:
            self._class_stack[-1].methods.append(info)
        else:
            self._functions.append(info)

    def _build_parameters(self, args: ast.arguments) -> List[ParameterInfo]:
        parameters: List[ParameterInfo] = []
        ordered = list(args.posonlyargs) + list(args.args)
        defaults = [None] * (len(ordered) - len(args.defaults)) + list(
            args.defaults
        )

        for node, default in zip(ordered, defaults, strict=False):
            parameters.append(
                ParameterInfo(
                    name=node.arg,
                    annotation=_safe_unparse(node.annotation),
                    default=_safe_unparse(default),
                )
            )

        if args.vararg:
            parameters.append(
                ParameterInfo(name="*" + args.vararg.arg, kind="vararg")
            )
        for kw, default in zip(args.kwonlyargs, args.kw_defaults, strict=False):
            parameters.append(
                ParameterInfo(
                    name=kw.arg,
                    annotation=_safe_unparse(kw.annotation),
                    default=_safe_unparse(default),
                    kind="kwonly",
                )
            )
        if args.kwarg:
            parameters.append(
                ParameterInfo(name="**" + args.kwarg.arg, kind="varkw")
            )
        return parameters

    def _infer_import_path(self) -> str:
        try:
            relative = self.module_path.relative_to(Path.cwd())
            return ".".join(relative.with_suffix("").parts)
        except ValueError:
            return self.module_path.with_suffix("").name


@dataclass
class EdgeCaseDefinition:
    """Edge case metadata used for parametrized tests."""

    description: str
    parameters: Dict[str, str]


class EdgeCaseGenerator:
    """Suggest simple boundary cases based on parameter metadata."""

    NUMERIC_HINTS = {"count", "retries", "limit", "size", "amount"}

    def suggest(self, function: FunctionInfo) -> List[EdgeCaseDefinition]:
        cases: List[EdgeCaseDefinition] = []
        numeric_params = [
            param
            for param in function.parameters
            if self._looks_numeric(param) and not param.name.startswith("*")
        ]
        string_params = [
            param
            for param in function.parameters
            if self._looks_string(param) and not param.name.startswith("*")
        ]

        if numeric_params:
            for boundary in (0, 1, -1):
                params = {param.name: boundary for param in numeric_params}
                cases.append(
                    EdgeCaseDefinition(
                        description=f"numeric boundary {boundary}",
                        parameters=params,
                    )
                )

        if string_params:
            cases.append(
                EdgeCaseDefinition(
                    description="empty string inputs",
                    parameters={param.name: "''" for param in string_params},
                )
            )
            cases.append(
                EdgeCaseDefinition(
                    description="long string inputs",
                    parameters={
                        param.name: "'x' * 1024" for param in string_params
                    },
                )
            )

        return cases

    def _looks_numeric(self, param: ParameterInfo) -> bool:
        annotation = (param.annotation or "").lower()
        return (
            annotation in {"int", "float", "decimal"}
            or param.name.lower() in self.NUMERIC_HINTS
        )

    def _looks_string(self, param: ParameterInfo) -> bool:
        annotation = (param.annotation or "").lower()
        return "str" in annotation or param.name.lower() in {"name", "email"}


class PythonTestGenerator:
    """Generate pytest files for analyzed modules."""

    def __init__(self) -> None:
        self._edge_cases = EdgeCaseGenerator()

    def generate_tests(
        self,
        module_path: Path | str,
        *,
        scenarios: Sequence[TestScenario] | None = None,
        output_path: Path | None = None,
        write_to_file: bool = False,
    ) -> GeneratedPythonTest:
        module_path = Path(module_path)
        analyzer = PythonCodeAnalyzer(module_path)
        analysis = analyzer.analyze()

        if analysis.total_entities == 0:
            raise TestGenerationError(
                f"No functions or classes found in {module_path}"
            )

        scenario_list = list(scenarios or [])
        test_blocks: List[str] = []

        for function in analysis.functions:
            scenario_hint = scenario_list[0].name if scenario_list else None
            test_blocks.append(
                template.render_function_test(function, scenario_hint)
            )
            edge_cases = self._edge_cases.suggest(function)
            if edge_cases:
                serialized = [
                    {
                        **case.parameters,
                        "_description": case.description,
                    }
                    for case in edge_cases
                ]
                test_blocks.append(
                    template.render_edge_case_test(function, serialized)
                )

        for cls in analysis.classes:
            if cls.methods:
                test_blocks.append(template.render_class_test(cls))

        file_contents = template.assemble_test_file(
            analysis=analysis,
            test_blocks=test_blocks,
            scenarios=scenario_list,
        )

        target_path = output_path or Path("tests") / "unit" / f"test_{module_path.stem}.py"
        target_path = Path(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if write_to_file:
            target_path.write_text(file_contents, encoding="utf-8")

        coverage_estimate = min(
            1.0,
            len(test_blocks) / max(1, analysis.total_entities) * 0.9,
        )
        quality_score = min(1.0, 0.5 + 0.05 * len(test_blocks))

        return GeneratedPythonTest(
            test_file_path=str(target_path),
            test_code=file_contents,
            test_count=len(test_blocks),
            coverage_estimate=coverage_estimate,
            quality_score=quality_score,
            scenarios=[scenario.summary() for scenario in scenario_list],
        )


__all__ = ["PythonCodeAnalyzer", "PythonTestGenerator"]

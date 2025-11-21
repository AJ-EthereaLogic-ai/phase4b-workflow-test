"""
Quality Metrics Calculator

Calculates comprehensive quality metrics beyond coverage including test quality,
documentation, type safety, and complexity scores.
"""

from __future__ import annotations

import ast
from pathlib import Path

from adws.tdd.coverage.unified_coverage_tracker import QualityMetrics


class QualityMetricsCalculator:
    """
    Calculates comprehensive quality metrics beyond coverage.

    Metrics:
    - Coverage score (from coverage report)
    - Test quality score (assertions, independence, etc.)
    - Documentation score (docstrings, comments)
    - Type safety score (type hints, annotations)
    - Complexity score (cyclomatic complexity, maintainability)

    Example:
        >>> calculator = QualityMetricsCalculator()
        >>> metrics = calculator.calculate_metrics(
        ...     source_path=Path("adws"),
        ...     test_path=Path("tests"),
        ...     coverage_percentage=92.5
        ... )
        >>> print(f"Overall quality: {metrics.overall_score:.2f}")
    """

    def calculate_metrics(
        self,
        source_path: Path,
        test_path: Path,
        coverage_percentage: float,
    ) -> QualityMetrics:
        """
        Calculate comprehensive quality metrics.

        Args:
            source_path: Path to source code
            test_path: Path to test code
            coverage_percentage: Coverage percentage from report

        Returns:
            Quality metrics
        """
        # Coverage score (0-1)
        coverage_score = coverage_percentage / 100.0

        # Test quality score
        test_quality_score = self._calculate_test_quality(test_path)

        # Documentation score
        documentation_score = self._calculate_documentation_score(source_path)

        # Type safety score
        type_safety_score = self._calculate_type_safety_score(source_path)

        # Complexity score
        complexity_score = self._calculate_complexity_score(source_path)

        # Overall score (weighted average)
        overall_score = (
            coverage_score * 0.35
            + test_quality_score * 0.25
            + documentation_score * 0.15
            + type_safety_score * 0.15
            + complexity_score * 0.10
        )

        return QualityMetrics(
            coverage_score=coverage_score,
            test_quality_score=test_quality_score,
            documentation_score=documentation_score,
            type_safety_score=type_safety_score,
            complexity_score=complexity_score,
            overall_score=overall_score,
        )

    def _calculate_test_quality(self, test_path: Path) -> float:
        """Calculate test quality score."""
        if not test_path.exists():
            return 0.0

        weights = {
            "has_assertions": 0.3,
            "has_docstrings": 0.2,
            "uses_fixtures": 0.2,
            "covers_edge_cases": 0.15,
            "independent_tests": 0.15,
        }

        if test_path.is_file():
            test_files = [test_path]
        else:
            test_files = list(test_path.rglob("test_*.py"))

        if not test_files:
            return 0.0

        total_score = 0.0

        for test_file in test_files:
            try:
                code = test_file.read_text(encoding="utf-8")

                file_score = 0.0

                # Has assertions
                if "assert" in code:
                    file_score += weights["has_assertions"]

                # Has docstrings
                if '"""' in code or "'''" in code:
                    file_score += weights["has_docstrings"]

                # Uses fixtures
                if "@pytest.fixture" in code or "mock" in code.lower():
                    file_score += weights["uses_fixtures"]

                # Covers edge cases
                edge_keywords = ["edge", "boundary", "empty", "none", "null"]
                if any(keyword in code.lower() for keyword in edge_keywords):
                    file_score += weights["covers_edge_cases"]

                # Independent tests (no shared state)
                if "setup" not in code.lower() and "teardown" not in code.lower():
                    file_score += weights["independent_tests"]

                total_score += file_score

            except (OSError, UnicodeDecodeError):
                continue

        return min(1.0, total_score / len(test_files))

    def _calculate_documentation_score(self, source_path: Path) -> float:
        """Calculate documentation score."""
        if not source_path.exists():
            return 0.0

        if source_path.is_file():
            source_files = [source_path]
        else:
            source_files = list(source_path.rglob("*.py"))

        if not source_files:
            return 0.0

        total_score = 0.0
        valid_files = 0

        for source_file in source_files:
            try:
                code = source_file.read_text(encoding="utf-8")
                tree = ast.parse(code)

                total_functions = 0
                documented_functions = 0

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        total_functions += 1
                        if ast.get_docstring(node):
                            documented_functions += 1

                if total_functions > 0:
                    total_score += documented_functions / total_functions
                    valid_files += 1

            except (SyntaxError, OSError, UnicodeDecodeError):
                continue

        return total_score / valid_files if valid_files > 0 else 0.0

    def _calculate_type_safety_score(self, source_path: Path) -> float:
        """Calculate type safety score."""
        if not source_path.exists():
            return 0.0

        if source_path.is_file():
            source_files = [source_path]
        else:
            source_files = list(source_path.rglob("*.py"))

        if not source_files:
            return 0.0

        total_score = 0.0
        valid_files = 0

        for source_file in source_files:
            try:
                code = source_file.read_text(encoding="utf-8")
                tree = ast.parse(code)

                total_functions = 0
                typed_functions = 0

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        total_functions += 1

                        # Check for return type annotation
                        if node.returns:
                            typed_functions += 1
                        # Check for parameter annotations
                        elif any(arg.annotation for arg in node.args.args):
                            typed_functions += 1

                if total_functions > 0:
                    total_score += typed_functions / total_functions
                    valid_files += 1

            except (SyntaxError, OSError, UnicodeDecodeError):
                continue

        return total_score / valid_files if valid_files > 0 else 0.0

    def _calculate_complexity_score(self, source_path: Path) -> float:
        """Calculate complexity score (inverse of complexity)."""
        # Simplified complexity calculation
        # In production, use tools like radon, mccabe, etc.

        if not source_path.exists():
            return 1.0

        if source_path.is_file():
            source_files = [source_path]
        else:
            source_files = list(source_path.rglob("*.py"))

        if not source_files:
            return 1.0

        total_complexity = 0
        total_functions = 0

        for source_file in source_files:
            try:
                code = source_file.read_text(encoding="utf-8")
                tree = ast.parse(code)

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        total_functions += 1

                        # Simple complexity: count branches
                        complexity = 1  # Base complexity
                        for child in ast.walk(node):
                            if isinstance(
                                child, (ast.If, ast.For, ast.While, ast.With)
                            ):
                                complexity += 1

                        total_complexity += complexity

            except (SyntaxError, OSError, UnicodeDecodeError):
                continue

        if total_functions == 0:
            return 1.0

        avg_complexity = total_complexity / total_functions

        # Lower complexity is better, normalize to 0-1 scale
        # Complexity > 20 is considered very high
        normalized_score = max(0.0, 1.0 - (avg_complexity / 20.0))

        return normalized_score

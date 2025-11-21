"""Specification-to-scenario extraction utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from adws.tdd.exceptions import ScenarioExtractionError
from adws.tdd.models import TestPriority, TestScenario, TestType


_SCENARIO_HEADING = re.compile(
    r"^(?:#{2,6}\s*)?(?:scenario|test case|case)\s*[:\-]\s*(?P<title>.+)$",
    re.IGNORECASE,
)


@dataclass
class ExtractedSection:
    """Internal helper to accumulate scenario metadata."""

    title: str
    lines: list[str]


class TestScenarioExtractor:
    """Extract structured test scenarios from Markdown specifications."""

    def extract_scenarios(
        self,
        spec_path: Path | str,
        test_types: Sequence[TestType] | None = None,
    ) -> List[TestScenario]:
        path = Path(spec_path)
        if not path.exists():
            raise FileNotFoundError(f"Specification not found: {path}")

        content = path.read_text(encoding="utf-8")
        sections = self._split_into_sections(content.splitlines())

        scenarios: List[TestScenario] = []
        for section in sections:
            scenario = self._build_scenario_from_section(
                section,
                source_file=path,
                test_types=test_types,
            )
            if scenario:
                scenarios.append(scenario)

        if not scenarios:
            raise ScenarioExtractionError(
                f"No test scenarios could be extracted from {path}"
            )

        return scenarios

    def _split_into_sections(self, lines: Iterable[str]) -> List[ExtractedSection]:
        sections: List[ExtractedSection] = []
        current: ExtractedSection | None = None

        for idx, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line:
                if current:
                    current.lines.append("")
                continue

            heading = _SCENARIO_HEADING.match(line)
            if heading:
                if current:
                    sections.append(current)
                title = heading.group("title").strip()
                current = ExtractedSection(title=title, lines=[f"@line:{idx}"])
                continue

            if current is None:  # opportunistically create scenario only for G/W/T
                lower = line.lower()
                if lower.startswith("given") or lower.startswith("when") or lower.startswith("then"):
                    synthetic_title = line[:60]
                    current = ExtractedSection(title=synthetic_title, lines=[f"@line:{idx}"])
                else:
                    # Ignore non-scenario prose until a valid heading or G/W/T line appears
                    continue

            current.lines.append(line)

        if current:
            sections.append(current)

        return sections

    def _build_scenario_from_section(
        self,
        section: ExtractedSection,
        *,
        source_file: Path,
        test_types: Sequence[TestType] | None,
    ) -> TestScenario | None:
        lines = [line for line in section.lines if not line.startswith("@line:")]
        if not lines:
            return None

        priority = self._infer_priority(lines)
        test_type = self._infer_test_type(lines, requested=test_types)

        steps = [
            self._normalize_bdd_line(line)
            for line in lines
            if self._bdd_line_matches(line, ("given",))
        ]
        steps.extend(
            self._normalize_bdd_line(line)
            for line in lines
            if self._bdd_line_matches(line, ("when",))
        )
        expectations = [
            self._normalize_bdd_line(line)
            for line in lines
            if self._bdd_line_matches(line, ("then",))
        ]

        edge_cases = self._extract_list_block(lines, prefix="edge case")
        errors = self._extract_list_block(lines, prefix="error")

        scenario = TestScenario(
            name=section.title.strip(),
            description=" ".join(lines[:3]),
            test_type=test_type,
            priority=priority,
            steps=steps,
            expected_outputs=expectations,
            edge_cases=edge_cases,
            error_conditions=errors,
            source_file=source_file,
            line_number=self._extract_line_number(section),
            tags=self._extract_tags(lines),
        )

        # Incorporate contextual inference
        if not scenario.edge_cases:
            scenario.edge_cases = self._default_edge_cases(test_type)
        if not scenario.expected_outputs and steps:
            scenario.expected_outputs = [
                "System responds according to specification"
            ]

        # If there are no steps and no expectations, treat as non-scenario
        if not steps and not expectations:
            return None

        return scenario

    def _extract_line_number(self, section: ExtractedSection) -> int | None:
        for token in section.lines:
            if token.startswith("@line:"):
                return int(token.split(":", 1)[1])
        return None

    def _infer_priority(self, lines: Sequence[str]) -> TestPriority:
        priority_line = next(
            (line for line in lines if "priority" in line.lower()),
            "",
        )
        if "high" in priority_line.lower():
            return TestPriority.HIGH
        if "low" in priority_line.lower():
            return TestPriority.LOW
        return TestPriority.MEDIUM

    def _infer_test_type(
        self,
        lines: Sequence[str],
        *,
        requested: Sequence[TestType] | None,
    ) -> TestType:
        if requested:
            return requested[0]

        joined = " ".join(lines).lower()
        if any(keyword in joined for keyword in ("api", "service", "database")):
            return TestType.INTEGRATION
        if any(keyword in joined for keyword in ("browser", "ui", "workflow")):
            return TestType.E2E
        if "unit" in joined:
            return TestType.UNIT
        return TestType.INTEGRATION

    def _extract_list_block(self, lines: Sequence[str], *, prefix: str) -> List[str]:
        results: List[str] = []
        lower_prefix = prefix.lower()
        capture = False
        for line in lines:
            lower = line.lower()
            if lower.startswith(lower_prefix):
                capture = True
                continue
            if capture:
                if lower.startswith(("-", "*")):
                    results.append(line.lstrip("-* ").strip())
                else:
                    capture = False
        return results

    def _extract_tags(self, lines: Sequence[str]) -> List[str]:
        tags_line = next((line for line in lines if "tags:" in line.lower()), "")
        if not tags_line:
            return []
        _, _, tail = tags_line.partition(":")
        return [tag.strip().lower() for tag in tail.split(",") if tag.strip()]

    def _bdd_line_matches(self, line: str, keywords: Sequence[str]) -> bool:
        """
        Return True if the normalized line starts with any of the given keywords.
        Matching is case-insensitive; keywords are normalized to lowercase.
        """
        normalized = self._normalize_bdd_line(line)
        lower = normalized.lower()
        return any(lower.startswith(keyword.lower()) for keyword in keywords)

    def _normalize_bdd_line(self, line: str) -> str:
        """Remove leading list markers to make BDD keyword detection reliable."""

        return re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line)

    def _default_edge_cases(self, test_type: TestType) -> List[str]:
        if test_type == TestType.UNIT:
            return ["null input", "empty input", "boundary values"]
        if test_type == TestType.E2E:
            return ["network interruption", "authentication failure"]
        return ["downstream dependency failure"]


__all__ = ["TestScenarioExtractor"]

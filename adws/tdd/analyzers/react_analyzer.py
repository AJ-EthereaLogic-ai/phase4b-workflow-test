"""React component analyzer using TypeScript and Babel AST traversal."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional


class HookType(str, Enum):
    """Enumeration of supported React hook types."""

    USE_STATE = "useState"
    USE_EFFECT = "useEffect"
    USE_CONTEXT = "useContext"
    USE_REF = "useRef"
    USE_MEMO = "useMemo"
    USE_CALLBACK = "useCallback"
    CUSTOM = "custom"


@dataclass
class PropInfo:
    """Information about a component prop."""

    name: str
    type: str
    required: bool
    default_value: Optional[str] = None
    description: Optional[str] = None


@dataclass
class StateInfo:
    """Information about a useState variable."""

    name: str
    type: str
    initial_value: Optional[str] = None
    setter: Optional[str] = None


@dataclass
class HookUsage:
    """Information about a hook invocation."""

    name: str
    type: HookType
    dependencies: List[str] = field(default_factory=list)


@dataclass
class EventHandler:
    """Information about a JSX event handler."""

    name: Optional[str]
    event_type: str
    element: Optional[str] = None


@dataclass
class ImportInfo:
    """Information about an ES module import."""

    source: str
    imports: List[str]
    is_default: bool


@dataclass
class ExportInfo:
    """Information about component export details."""

    is_default: bool
    is_named: bool
    name: str


@dataclass
class ComponentInfo:
    """Complete analysis result for a React component."""

    name: str
    file_path: str
    props: List[PropInfo] = field(default_factory=list)
    state: List[StateInfo] = field(default_factory=list)
    hooks: List[HookUsage] = field(default_factory=list)
    events: List[EventHandler] = field(default_factory=list)
    child_components: List[str] = field(default_factory=list)
    imports: List[ImportInfo] = field(default_factory=list)
    exports: ExportInfo = field(
        default_factory=lambda: ExportInfo(
            is_default=False,
            is_named=False,
            name="",
        )
    )
    is_class_component: bool = False
    is_functional: bool = False


class ReactComponentAnalyzer:
    """Analyzer that delegates to a Node.js worker for AST-based analysis."""

    def __init__(
        self,
        tsconfig_path: Optional[Path] = None,
        node_executable: str = "node",
        worker_path: Optional[Path] = None,
    ) -> None:
        """Initialize the analyzer.

        Args:
            tsconfig_path: Optional path to a tsconfig.json file.
            node_executable: Name or path of the Node.js executable.
            worker_path: Optional explicit path to the analyzer worker script.
        """

        self._tsconfig_path = Path(tsconfig_path) if tsconfig_path else None
        self._node_executable = node_executable
        self._worker_path = (
            Path(worker_path)
            if worker_path
            else Path(__file__).with_name("react_analyzer_worker.js")
        )

        if not self._worker_path.exists():
            raise FileNotFoundError(
                f"React analyzer worker not found: {self._worker_path}"
            )

    def analyze_component(self, file_path: Path) -> ComponentInfo:
        """Analyze the supplied React component file."""

        if not isinstance(file_path, Path):
            file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Component file not found: {file_path}")

        payload = self._run_worker(file_path)
        return self._parse_component_info(payload)

    def _run_worker(self, file_path: Path) -> dict:
        command = [self._node_executable, str(self._worker_path), str(file_path)]
        if self._tsconfig_path:
            command.append(str(self._tsconfig_path))

        try:
            completed = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,  # Security: prevent command injection
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip()
            message = (
                f"React analyzer worker failed for {file_path}: {stderr or exc}"
            )
            raise ValueError(message) from exc
        except FileNotFoundError as exc:  # pragma: no cover - environment issue
            raise FileNotFoundError(
                "Node.js executable not found. Install Node.js to run the analyzer."
            ) from exc

        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid analyzer output for {file_path}: {completed.stdout!r}"
            ) from exc

    def _parse_component_info(self, payload: dict) -> ComponentInfo:
        component = ComponentInfo(
            name=payload.get("name", "UnknownComponent"),
            file_path=payload.get("filePath", ""),
        )

        component.props = [
            PropInfo(
                name=prop.get("name", ""),
                type=prop.get("type", "any"),
                required=bool(prop.get("required", False)),
                default_value=prop.get("defaultValue"),
                description=prop.get("description"),
            )
            for prop in payload.get("props", [])
        ]

        component.state = [
            StateInfo(
                name=state.get("name", ""),
                type=state.get("type", "unknown"),
                initial_value=state.get("initialValue"),
                setter=state.get("setter"),
            )
            for state in payload.get("state", [])
        ]

        component.hooks = [
            HookUsage(
                name=hook.get("name", ""),
                type=self._hook_type_from_string(hook.get("type", "custom")),
                dependencies=list(hook.get("dependencies", []) or []),
            )
            for hook in payload.get("hooks", [])
        ]

        component.events = [
            EventHandler(
                name=event.get("name"),
                event_type=event.get("eventType", ""),
                element=event.get("element"),
            )
            for event in payload.get("events", [])
        ]

        component.child_components = list(payload.get("childComponents", []))

        component.imports = [
            ImportInfo(
                source=imp.get("source", ""),
                imports=list(imp.get("imports", [])),
                is_default=bool(imp.get("isDefault", False)),
            )
            for imp in payload.get("imports", [])
        ]

        export_payload = payload.get("exports", {})
        component.exports = ExportInfo(
            is_default=bool(export_payload.get("isDefault", False)),
            is_named=bool(export_payload.get("isNamed", False)),
            name=export_payload.get("name", component.name),
        )

        component.is_class_component = bool(payload.get("isClassComponent", False))
        component.is_functional = bool(payload.get("isFunctional", False))

        return component

    @staticmethod
    def _hook_type_from_string(value: str) -> HookType:
        mapping = {
            "useState": HookType.USE_STATE,
            "useEffect": HookType.USE_EFFECT,
            "useContext": HookType.USE_CONTEXT,
            "useRef": HookType.USE_REF,
            "useMemo": HookType.USE_MEMO,
            "useCallback": HookType.USE_CALLBACK,
        }
        return mapping.get(value, HookType.CUSTOM)

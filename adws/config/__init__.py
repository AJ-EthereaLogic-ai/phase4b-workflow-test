"""
Configuration loading for ADWS v2.0.

Implements the shared configuration model described in the integration
architecture design. Configuration values are resolved using the following
precedence:

1. Explicit arguments passed to `load_config`
2. Environment variables (e.g., ADWS_DEFAULT_PROVIDER)
3. `adws.toml` if present in the project root
4. Built-in defaults
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import tomllib
from pydantic import BaseModel, Field, ConfigDict, field_validator

from adws.consensus.engine import ConsensusStrategy
from adws.providers.interfaces import ProviderConfig
from adws.state.cleanup import CleanupPolicy

__all__ = [
    "ADWSConfig",
    "ConfigError",
    "EventConfig",
    "TDDConfig",
    "TUIConfig",
    "load_config",
]


DEFAULT_STATE_DIR = Path(".adws/state")
DEFAULT_SQLITE_DB = DEFAULT_STATE_DIR / "workflows.db"
DEFAULT_EVENT_FILE = Path(".adws/events/events.jsonl")


class ConfigError(RuntimeError):
    """Raised when configuration cannot be loaded or validated."""


class EventConfig(BaseModel):
    """Event streaming configuration."""

    backend: str = Field("file", description="Event backend type")
    file: Path = Field(DEFAULT_EVENT_FILE, description="Path to event log file")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator("file", mode="before")
    @classmethod
    def _coerce_path(cls, value: Any) -> Path:
        return Path(value) if not isinstance(value, Path) else value


class TUIConfig(BaseModel):
    """Configuration for the monitoring TUI."""

    enabled: bool = Field(True, description="Whether the TUI is enabled")
    refresh_ms: int = Field(100, description="Refresh interval for UI updates", ge=16)


class TDDConfig(BaseModel):
    """Configuration for the TDD workflow helpers."""

    enabled: bool = Field(True, description="Whether TDD helpers are enabled")
    coverage_target: float = Field(
        0.80,
        description="Coverage target required by the TDD workflow",
        ge=0.0,
        le=1.0,
    )
    test_framework: str = Field(
        "pytest",
        description="Default test framework",
        min_length=1,
    )


def _default_cleanup_policy() -> CleanupPolicy:
    """Provide a sensible default cleanup policy."""

    return CleanupPolicy(
        policy_name="archive_completed",
        target_state="completed",
        min_age_days=30,
        action="archive",
    )


class ADWSConfig(BaseModel):
    """Top-level configuration object shared across subsystems."""

    providers: Dict[str, ProviderConfig] = Field(
        default_factory=dict, description="Configured LLM providers"
    )
    default_provider: str = Field(
        "claude", description="Default provider name", min_length=1
    )
    consensus_strategy: ConsensusStrategy = Field(
        ConsensusStrategy.MAJORITY_VOTE,
        description="Consensus strategy for multi-provider execution",
    )
    state_dir: Path = Field(DEFAULT_STATE_DIR, description="State directory path")
    sqlite_db: Path = Field(DEFAULT_SQLITE_DB, description="SQLite database path")
    cleanup_policy: CleanupPolicy = Field(
        default_factory=_default_cleanup_policy,
        description="System-wide cleanup policy defaults",
    )
    event_backend: str = Field("file", description="Event backend identifier")
    event_file: Path = Field(DEFAULT_EVENT_FILE, description="Event log path")
    tdd: TDDConfig = Field(default_factory=TDDConfig)
    tui: TUIConfig = Field(default_factory=TUIConfig)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator("state_dir", "sqlite_db", "event_file", mode="before")
    @classmethod
    def _coerce_path(cls, value: Any) -> Path:
        return Path(value) if not isinstance(value, Path) else value

    @property
    def tui_config(self) -> TUIConfig:
        """Return the TUI configuration (design compatibility helper)."""

        return self.tui

    @property
    def tdd_config(self) -> TDDConfig:
        """Return the TDD configuration (design compatibility helper)."""

        return self.tdd

    @property
    def tdd_enabled(self) -> bool:
        """Mirror the design document's `tdd_enabled` flag."""

        return self.tdd.enabled

    @property
    def coverage_target(self) -> float:
        """Expose coverage target at the top level."""

        return self.tdd.coverage_target

    @property
    def test_framework(self) -> str:
        """Expose preferred test framework at the top level."""

        return self.tdd.test_framework


def load_config(config_path: Optional[Path | str] = None) -> ADWSConfig:
    """
    Load ADWS configuration from file/environment/defaults.

    Args:
        config_path: Optional explicit path to an `adws.toml` file.

    Returns:
        ADWSConfig populated with the resolved values.

    Raises:
        ConfigError: if the provided config path does not exist or parsing fails.
    """

    raw_data = _load_toml_data(config_path)
    providers = _load_provider_configs(raw_data.get("providers", {}))

    default_provider = _env_or_value(
        "ADWS_DEFAULT_PROVIDER",
        raw_data.get("default_provider"),
        "claude",
    )

    consensus_strategy = _parse_consensus_strategy(
        _env_or_value(
            "ADWS_CONSENSUS_STRATEGY",
            raw_data.get("consensus_strategy"),
            ConsensusStrategy.MAJORITY_VOTE.value,
        )
    )

    state_dir = Path(
        _env_or_value(
            "ADWS_STATE_DIR",
            raw_data.get("state", {}).get("state_dir") if raw_data.get("state") else None,
            str(DEFAULT_STATE_DIR),
        )
    )
    sqlite_db = Path(
        _env_or_value(
            "ADWS_SQLITE_DB",
            raw_data.get("state", {}).get("sqlite_db") if raw_data.get("state") else None,
            str(DEFAULT_SQLITE_DB),
        )
    )

    event_backend = _env_or_value(
        "ADWS_EVENT_BACKEND",
        raw_data.get("event", {}).get("backend") if raw_data.get("event") else None,
        "file",
    )
    event_file = Path(
        _env_or_value(
            "ADWS_EVENT_FILE",
            raw_data.get("event", {}).get("file") if raw_data.get("event") else None,
            str(DEFAULT_EVENT_FILE),
        )
    )

    tdd_data = raw_data.get("tdd", {})
    tdd_enabled = _env_bool(
        "ADWS_TDD_ENABLED", tdd_data.get("enabled", True)
    )
    tdd_coverage = float(
        _env_or_value(
            "ADWS_TDD_COVERAGE_TARGET",
            tdd_data.get("coverage_target"),
            str(TDDConfig().coverage_target),
        )
    )
    tdd_framework = _env_or_value(
        "ADWS_TEST_FRAMEWORK",
        tdd_data.get("test_framework"),
        TDDConfig().test_framework,
    )

    tui_data = raw_data.get("tui", {})
    tui_enabled = _env_bool(
        "ADWS_TUI_ENABLED", tui_data.get("enabled", True)
    )
    tui_refresh = int(
        _env_or_value(
            "ADWS_TUI_REFRESH_MS",
            tui_data.get("refresh_ms"),
            str(TUIConfig().refresh_ms),
        )
    )

    cleanup_policy = _build_cleanup_policy(raw_data.get("cleanup_policy"))

    return ADWSConfig(
        providers=providers,
        default_provider=default_provider,
        consensus_strategy=consensus_strategy,
        state_dir=state_dir,
        sqlite_db=sqlite_db,
        cleanup_policy=cleanup_policy,
        event_backend=event_backend,
        event_file=event_file,
        tdd=TDDConfig(
            enabled=tdd_enabled,
            coverage_target=tdd_coverage,
            test_framework=tdd_framework,
        ),
        tui=TUIConfig(
            enabled=tui_enabled,
            refresh_ms=tui_refresh,
        ),
    )


def _load_toml_data(config_path: Optional[Path | str]) -> Dict[str, Any]:
    """Load data from a TOML file if one can be resolved."""

    resolved = _resolve_config_path(config_path)
    if resolved is None:
        return {}

    if not resolved.exists():
        raise ConfigError(f"Configuration file not found: {resolved}")

    with resolved.open("rb") as fh:
        return tomllib.load(fh)


def _resolve_config_path(config_path: Optional[Path | str]) -> Optional[Path]:
    """Resolve configuration path with environment fallback."""

    if config_path:
        return Path(config_path)

    env_path = os.getenv("ADWS_CONFIG_FILE")
    if env_path:
        return Path(env_path)

    default_path = Path("adws.toml")
    return default_path if default_path.exists() else None


def _load_provider_configs(raw: Dict[str, Any]) -> Dict[str, ProviderConfig]:
    """Convert provider mapping into ProviderConfig instances."""

    providers: Dict[str, ProviderConfig] = {}
    for name, cfg in raw.items():
        config_data = dict(cfg)
        config_data.setdefault("name", name)
        api_key_env = config_data.pop("api_key_env", None)
        if not config_data.get("api_key") and api_key_env:
            config_data["api_key"] = os.getenv(api_key_env)
        providers[name] = ProviderConfig(**config_data)
    return providers


def _parse_consensus_strategy(raw_value: str) -> ConsensusStrategy:
    """Convert string to ConsensusStrategy, allowing hyphen/underscore aliases."""

    normalized = raw_value.replace("_", "-").lower()
    for strategy in ConsensusStrategy:
        if strategy.value == normalized:
            return strategy
    raise ConfigError(f"Unknown consensus strategy: {raw_value}")


def _env_bool(env_var: str, default: Any) -> bool:
    """Resolve boolean from environment with fallback."""

    value = os.getenv(env_var)
    if value is None:
        return bool(default)
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"Invalid boolean for {env_var}: {value}")


def _env_or_value(env_var: str, value: Any, default: Any) -> str:
    """Return environment variable value if set, otherwise fallback to provided/default values."""

    env_value = os.getenv(env_var)
    if env_value is not None:
        return env_value
    if value is not None:
        return str(value)
    return str(default)


def _build_cleanup_policy(raw: Optional[Dict[str, Any]]) -> CleanupPolicy:
    """Create a cleanup policy from raw dict data if provided."""

    if not raw:
        return _default_cleanup_policy()

    try:
        return CleanupPolicy(
            policy_name=raw["policy_name"],
            target_state=raw["target_state"],
            min_age_days=int(raw["min_age_days"]),
            action=raw["action"],
        )
    except KeyError as exc:  # pragma: no cover - invalid config detection
        raise ConfigError(f"Missing cleanup_policy field: {exc}") from exc

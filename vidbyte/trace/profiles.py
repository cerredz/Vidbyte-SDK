"""Trace profile presets and component filtering."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from vidbyte.lib.errors import ConfigurationError
from vidbyte.trace.schema import SpanSpec, TraceDetail

_DETAIL_ORDER = {
    TraceDetail.MINIMAL: 0,
    TraceDetail.STANDARD: 1,
    TraceDetail.VERBOSE: 2,
    TraceDetail.DIAGNOSTIC: 3,
}
_COMPONENTS = {
    "agents",
    "aggregate",
    "runtimes",
    "actor",
    "search",
    "context",
    "algorithms",
    "middleware",
    "tools",
    "parsers",
    "retrievers",
    "embeddings",
    "sessions",
    "core",
    "pipelines",
    "handoff",
    "sources",
    "evals",
    "mcp",
}
_SETTING_VALUES = {"off", "minimal", "default", "summary", "decisions_only", "inputs_outputs", "verbose", "diagnostic"}


@dataclass(frozen=True, slots=True)
class TraceComponentSettings:
    """Component-level settings used by TraceProfile."""

    components: Mapping[str, str | bool] = field(default_factory=dict)

    def resolve(self, component: str) -> str | bool:
        # Looks up a component setting with a safe default.
        return dict(self.components).get(component, "default")


@dataclass(frozen=True, slots=True)
class TraceProfile:
    """Immutable profile that controls semantic trace detail and redaction."""

    detail: TraceDetail = TraceDetail.STANDARD
    components: Mapping[str, str | bool] = field(default_factory=dict)
    redact: bool = True
    max_chars: int = 12000

    def __post_init__(self) -> None:
        # Validates profile shape after dataclass initialization.
        if self.max_chars <= 0:
            raise ConfigurationError("TraceProfile.max_chars must be greater than zero.")
        for component, setting in dict(self.components).items():
            self._validate_component_setting(component, setting)

    @classmethod
    def minimal(cls) -> TraceProfile:
        # Builds the profile that keeps only agent, llm, and tool call spans.
        return cls(detail=TraceDetail.MINIMAL, components=_base_components("minimal"))

    @classmethod
    def default(cls) -> TraceProfile:
        # Builds the SDK default semantic profile.
        return cls(detail=TraceDetail.STANDARD, components=_base_components("default"))

    @classmethod
    def verbose(cls) -> TraceProfile:
        # Builds a profile with runtime, context, algorithm, aggregate, and middleware decisions.
        return cls(detail=TraceDetail.VERBOSE, components=_base_components("verbose"))

    @classmethod
    def diagnostic(cls) -> TraceProfile:
        # Builds the highest-detail profile for local debugging and diagnostics.
        return cls(detail=TraceDetail.DIAGNOSTIC, components=_base_components("diagnostic"))

    def with_components(self, **components: str | bool) -> TraceProfile:
        # Returns a copy with selected component settings overridden.
        merged = {**dict(self.components)}
        for component, setting in components.items():
            self._validate_component_setting(component, setting)
            merged[component] = setting
        return replace(self, components=merged)

    def allows(self, spec: SpanSpec) -> bool:
        # Returns whether a semantic span is enabled by component and detail threshold.
        setting = dict(self.components).get(spec.component, "default")
        if setting is False or setting == "off":
            return False
        if setting is True:
            return _DETAIL_ORDER[spec.detail] <= _DETAIL_ORDER[self.detail]
        if setting == "minimal":
            return spec.detail is TraceDetail.MINIMAL
        if setting == "decisions_only":
            return spec.name == "middleware.decision" or _DETAIL_ORDER[spec.detail] <= _DETAIL_ORDER[TraceDetail.STANDARD]
        if setting in {"default", "summary", "inputs_outputs"}:
            return _DETAIL_ORDER[spec.detail] <= _DETAIL_ORDER[TraceDetail.STANDARD]
        if setting == "verbose":
            return _DETAIL_ORDER[spec.detail] <= _DETAIL_ORDER[TraceDetail.VERBOSE]
        if setting == "diagnostic":
            return True
        return _DETAIL_ORDER[spec.detail] <= _DETAIL_ORDER[self.detail]

    @staticmethod
    def _validate_component_setting(component: str, setting: str | bool) -> None:
        # Raises for unknown component names or unsupported settings.
        if component not in _COMPONENTS:
            raise ConfigurationError(f"Unknown trace component: {component}.")
        if isinstance(setting, bool):
            return
        if setting not in _SETTING_VALUES:
            raise ConfigurationError(f"Unknown trace setting for {component}: {setting}.")


def _base_components(setting: str) -> dict[str, str | bool]:
    # Builds a complete component settings map for a preset.
    return {component: setting for component in _COMPONENTS}


def safe_trace_value(value: Any, *, max_chars: int = 12000, redact: bool = True) -> Any:
    # Recursively redacts and truncates values before they leave the semantic layer.
    if isinstance(value, Mapping):
        return {
            str(key): safe_trace_value(item, max_chars=max_chars, redact=redact)
            for key, item in dict(value).items()
            if not (redact and _is_secret_key(str(key)))
        }
    if isinstance(value, tuple):
        return tuple(safe_trace_value(item, max_chars=max_chars, redact=redact) for item in value)
    if isinstance(value, list):
        return [safe_trace_value(item, max_chars=max_chars, redact=redact) for item in value]
    if isinstance(value, str) and len(value) > max_chars:
        return f"{value[:max_chars]}...[truncated]"
    return value


def _is_secret_key(key: str) -> bool:
    # Detects credential-like trace payload keys.
    upper = key.upper()
    return upper.startswith("LANGSMITH_") or any(token in upper for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH"))


__all__ = ["TraceComponentSettings", "TraceProfile", "safe_trace_value"]

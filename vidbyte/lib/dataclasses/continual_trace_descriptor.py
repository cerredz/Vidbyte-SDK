"""Context Protocol Header

Description:
    Defines the ContinualTraceAgentDescriptor dataclass — a thin configuration
    wrapper for YAML-loaded continual-trace agent configurations. Holds the
    trace schema, iteration limit, and source provider/model.
Purpose:
    Provides a typed configuration object that the YamlLoader produces from a
    continual-trace-agent YAML document. Validates schema presence, iteration
    bounds, and provider/model pairing.
Architecture:
    - ContinualTraceAgentDescriptor: frozen dataclass holding trace schema and source config.
    - __post_init__ validates schema size, iteration bounds, and provider/model.
Relations:
    - Produced by vidbyte/lib/config/loader.py.
    - Used to construct ContinualTraceAgent instances at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.errors import ConfigurationError

_MAX_SCHEMA_KEYS = 50
_MAX_SCHEMA_DEPTH = 5


@dataclass(frozen=True, slots=True)
class ContinualTraceAgentDescriptor:
    """Typed continual-trace agent configuration loaded from a YAML document."""

    name: str = "continual-trace"
    schema: dict[str, Any] = field(default_factory=dict)
    max_trace_iterations: int = 3
    source_provider: str | None = None
    source_model_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates schema, iteration bounds, and provider/model pairing.
        self._validate_schema()
        self._validate_iterations()
        self._validate_provider_model()

    def to_agent_kwargs(self) -> dict[str, Any]:
        # Returns keyword arguments for ContinualTraceAgent construction.
        return {
            "name": self.name,
            "schema": dict(self.schema),
            "max_trace_iterations": self.max_trace_iterations,
            "source_provider": self.source_provider,
            "source_model_name": self.source_model_name,
        }

    def _validate_schema(self) -> None:
        # Validates the trace schema is non-empty, within key and depth limits.
        if not self.schema:
            raise ConfigurationError(
                "Continual-trace agent schema must be a non-empty mapping.",
                details={"field": "schema", "expected": "non-empty dict"},
            )
        if len(self.schema) > _MAX_SCHEMA_KEYS:
            raise ConfigurationError(
                f"Continual-trace schema must have at most {_MAX_SCHEMA_KEYS} top-level keys.",
                details={"field": "schema", "max_keys": _MAX_SCHEMA_KEYS, "actual_keys": len(self.schema)},
            )
        depth = ContinualTraceAgentDescriptor._max_depth(self.schema)
        if depth > _MAX_SCHEMA_DEPTH:
            raise ConfigurationError(
                f"Continual-trace schema must have at most {_MAX_SCHEMA_DEPTH} nesting levels.",
                details={"field": "schema", "max_depth": _MAX_SCHEMA_DEPTH, "actual_depth": depth},
            )

    @staticmethod
    def _max_depth(value: Any, current: int = 1) -> int:
        # Returns the maximum nesting depth of a JSON-like structure.
        if isinstance(value, dict) and value:
            return max(ContinualTraceAgentDescriptor._max_depth(item, current + 1) for item in value.values())
        return current

    def _validate_iterations(self) -> None:
        # Validates max_trace_iterations is an integer in [1, 3].
        if isinstance(self.max_trace_iterations, bool) or not isinstance(self.max_trace_iterations, int):
            raise ConfigurationError(
                "max_trace_iterations must be an integer.",
                details={"field": "max_trace_iterations", "actual_type": type(self.max_trace_iterations).__name__},
            )
        if self.max_trace_iterations < 1 or self.max_trace_iterations > 3:
            raise ConfigurationError(
                "max_trace_iterations must be between 1 and 3.",
                details={"field": "max_trace_iterations", "actual": self.max_trace_iterations},
            )

    def _validate_provider_model(self) -> None:
        # Validates provider/model are both set or both absent, and provider is recognized.
        if self.source_provider is None and self.source_model_name is None:
            return
        if self.source_provider is None or self.source_model_name is None:
            raise ConfigurationError(
                "source_provider and source_model_name must both be provided or both omitted.",
                details={
                    "field": "source_provider" if self.source_provider is None else "source_model_name",
                    "expected": "both provider and model_name",
                },
            )
        try:
            ModelProvider(self.source_provider)
        except ValueError as exc:
            known = sorted(p.value for p in ModelProvider)
            raise ConfigurationError(
                f"Unrecognized source_provider '{self.source_provider}'. Known providers: {known}.",
                details={"field": "source_provider", "actual": self.source_provider, "expected": known},
            ) from exc


__all__ = ["ContinualTraceAgentDescriptor"]

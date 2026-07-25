"""Context Protocol Header

Description:
    Defines the AgentDescriptor dataclass — the single source of truth for
    YAML-loaded agent configurations. It composes existing runtime settings classes
    (AgentLoopSettings, ToolSettings, AgentMetadata, TraceOption, ToolSpec) rather
    than duplicating their fields.
Purpose:
    Provides a typed configuration object that the YamlLoader produces from an agent
    YAML document. Callers resolve tool/middleware refs to live objects and pass
    the descriptor through to_agent_kwargs() for BaseAgent construction.
Architecture:
    - AgentDescriptor: thin frozen dataclass composing existing settings objects.
    - __post_init__ validates text lengths, provider/model, ref uniqueness, secrets,
      numeric ranges, and runtime compatibility.
    - to_agent_kwargs() maps fields to BaseAgent.__init__ keyword arguments.
Relations:
    - Produced by vidbyte/lib/config/loader.py.
    - Composed by HarnessDescriptor and EnvironmentDescriptor.
    - Used by BaseAgent construction through to_agent_kwargs().
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from vidbyte.agents.settings.loop import AgentLoopSettings
from vidbyte.agents.settings.tool import ToolSettings
from vidbyte.lib.dataclasses.agents import AgentMetadata
from vidbyte.lib.dataclasses.tools import ToolSpec
from vidbyte.lib.dataclasses.trace import TraceOption
from vidbyte.lib.enums.agent_runtime import AgentRuntimeType
from vidbyte.lib.enums.config import AgentType
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.registries.models import ProviderModelRegistry

_MAX_NAME_CHARS = 256
_MAX_SYSTEM_PROMPT_CHARS = 500_000
_MAX_DESCRIPTION_CHARS = 2000
_MAX_REF_CHARS = 128
_MAX_CAPABILITY_CHARS = 200
_REF_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")
_INTERPOLATION_PATTERN = re.compile(r"\$\{[^}]*\}")
_SECRET_KEY_SUFFIXES = (
    "api_key", "token", "password", "secret", "credential",
)
_SECRET_KEY_PREFIXES = (
    "api_key_", "token_", "password_", "secret_", "credential_",
)


def _has_secret_like_keys(mapping: Mapping[str, Any]) -> bool:
    # Returns True if any key in the mapping looks like a secret or credential.
    for key in mapping:
        lower = key.lower().replace("-", "_")
        if lower in _SECRET_KEY_SUFFIXES:
            return True
        if any(lower.startswith(prefix) for prefix in _SECRET_KEY_PREFIXES):
            return True
    return False


def _has_interpolation(value: Any) -> bool:
    # Recursively checks strings for ${...} environment interpolation patterns.
    if isinstance(value, str):
        return bool(_INTERPOLATION_PATTERN.search(value))
    if isinstance(value, dict):
        return any(_has_interpolation(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_interpolation(v) for v in value)
    return False


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    # Rejects secret-like keys and interpolation patterns in metadata.
    if _has_secret_like_keys(metadata):
        raise ConfigurationError(
            "Metadata contains secret-like keys. Secrets must not appear in YAML config.",
            details={"field": "metadata", "expected": "no secret keys"},
        )
    if _has_interpolation(metadata):
        raise ConfigurationError(
            "Metadata contains ${...} environment interpolation patterns.",
            details={"field": "metadata", "expected": "no interpolation"},
        )
    return metadata


@dataclass(frozen=True, slots=True)
class AgentDescriptor:
    """Typed agent configuration loaded from a YAML document.

    Composes existing runtime settings objects. All field validation fires from
    __post_init__ and the composed objects' own validation.
    """

    type: AgentType = AgentType.BASE
    name: str = ""
    system_prompt: str = ""
    description: str = ""
    provider: str | None = None
    model_name: str | None = None
    temperature: float | None = None
    runtime: AgentRuntimeType = AgentRuntimeType.LINEAR
    loop: AgentLoopSettings = field(default_factory=AgentLoopSettings)
    tools: tuple[ToolSpec, ...] = ()
    middleware_refs: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    agent_metadata: AgentMetadata = field(default_factory=AgentMetadata)
    algorithm: str | None = None
    output_schema: dict[str, Any] | None = None
    trace_option: TraceOption | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates all scalar fields, ref uniqueness, secrets, and runtime compatibility.
        self._validate_identity()
        self._validate_provider_model()
        self._validate_temperature()
        self._validate_refs()
        self._validate_capabilities()
        self._validate_algorithm()
        self._validate_output_schema()
        self._validate_metadata()
        self._validate_runtime_compatibility()

    def to_agent_kwargs(self, *, tools: Sequence[object] = (), middleware: Sequence[object] = ()) -> dict[str, Any]:
        # Returns keyword arguments for BaseAgent.__init__ after the caller supplies resolved tools and middleware.
        kwargs: dict[str, Any] = {
            "name": self.name,
            "system_prompt": self.system_prompt,
            "description": self.description,
            "runtime": self.runtime,
            "agent_loop_settings": self.loop,
            "tools": tools,
            "middleware": middleware,
            "capabilities": self.capabilities,
            "agent_metadata": self.agent_metadata,
            "metadata": dict(self.metadata),
        }
        if self.provider is not None:
            kwargs["provider"] = self.provider
        if self.model_name is not None:
            kwargs["model_name"] = self.model_name
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.algorithm is not None:
            kwargs["algorithm"] = self.algorithm
        if self.output_schema is not None:
            kwargs["output_schema"] = dict(self.output_schema)
        if self.trace_option is not None:
            kwargs["trace_option"] = self.trace_option
        return kwargs

    # ── identity validation ──

    def _validate_identity(self) -> None:
        # Validates name and system_prompt are non-empty, within length limits, and free of interpolation.
        if not self.name or not self.name.strip():
            raise ConfigurationError(
                "Agent name must be a non-empty string.",
                details={"field": "name", "expected": "non-empty string"},
            )
        if _INTERPOLATION_PATTERN.search(self.name):
            raise ConfigurationError(
                "Agent name must not contain environment interpolation patterns.",
                details={"field": "name", "expected": "no ${...} patterns"},
            )
        if len(self.name) > _MAX_NAME_CHARS:
            raise ConfigurationError(
                f"Agent name must be at most {_MAX_NAME_CHARS} characters.",
                details={"field": "name", "max_chars": _MAX_NAME_CHARS, "actual_chars": len(self.name)},
            )
        if not self.system_prompt or not self.system_prompt.strip():
            raise ConfigurationError(
                "Agent system_prompt must be a non-empty string.",
                details={"field": "system_prompt", "expected": "non-empty string"},
            )
        if _INTERPOLATION_PATTERN.search(self.system_prompt):
            raise ConfigurationError(
                "Agent system_prompt must not contain environment interpolation patterns.",
                details={"field": "system_prompt", "expected": "no ${...} patterns"},
            )
        if len(self.system_prompt) > _MAX_SYSTEM_PROMPT_CHARS:
            raise ConfigurationError(
                f"Agent system_prompt must be at most {_MAX_SYSTEM_PROMPT_CHARS} characters.",
                details={"field": "system_prompt", "max_chars": _MAX_SYSTEM_PROMPT_CHARS, "actual_chars": len(self.system_prompt)},
            )
        if len(self.description) > _MAX_DESCRIPTION_CHARS:
            raise ConfigurationError(
                f"Agent description must be at most {_MAX_DESCRIPTION_CHARS} characters.",
                details={"field": "description", "max_chars": _MAX_DESCRIPTION_CHARS, "actual_chars": len(self.description)},
            )
        if self.description and _INTERPOLATION_PATTERN.search(self.description):
            raise ConfigurationError(
                "Agent description must not contain environment interpolation patterns.",
                details={"field": "description", "expected": "no ${...} patterns"},
            )

    # ── provider / model validation ──

    def _validate_provider_model(self) -> None:
        # Validates provider is a recognized ModelProvider and model_name is non-empty.
        if self.provider is None and self.model_name is None:
            return
        if self.provider is None or self.model_name is None:
            raise ConfigurationError(
                "provider and model_name must both be provided or both omitted.",
                details={
                    "field": "provider" if self.provider is None else "model_name",
                    "expected": "both provider and model_name",
                },
            )
        try:
            ModelProvider(self.provider)
        except ValueError as exc:
            known = sorted(p.value for p in ModelProvider)
            raise ConfigurationError(
                f"Unrecognized provider '{self.provider}'. Known providers: {known}.",
                details={"field": "provider", "actual": self.provider, "expected": known},
            ) from exc
        try:
            ProviderModelRegistry.validate_model(self.model_name)
        except ConfigurationError as exc:
            raise ConfigurationError(
                f"Invalid model_name: {exc}",
                details={"field": "model_name", "actual": self.model_name},
            ) from exc

    # ── temperature validation ──

    def _validate_temperature(self) -> None:
        # Validates temperature is in the supported range when set.
        if self.temperature is not None and not (0.0 <= self.temperature <= 2.0):
            raise ConfigurationError(
                "temperature must be between 0.0 and 2.0 when provided.",
                details={"field": "temperature", "actual": self.temperature, "expected": "0.0 <= temperature <= 2.0"},
            )

    # ── ref (tool / middleware) validation ──

    def _validate_refs(self) -> None:
        # Validates tool specs and middleware refs for non-empty unique valid identifiers.
        self._validate_tool_specs()
        self._validate_middleware_refs()

    def _validate_tool_specs(self) -> None:
        # Rejects blank, overly long, malformed, or duplicate tool refs and checks for secrets.
        seen: set[str] = set()
        for index, spec in enumerate(self.tools):
            ref = spec.name if spec.name else ""
            if not ref or not ref.strip():
                raise ConfigurationError(
                    f"Tool at index {index} has an empty ref.",
                    details={"field": f"tools[{index}].ref", "expected": "non-empty string"},
                )
            if len(ref) > _MAX_REF_CHARS:
                raise ConfigurationError(
                    f"Tool ref '{ref}' must be at most {_MAX_REF_CHARS} characters.",
                    details={"field": f"tools[{index}].ref", "max_chars": _MAX_REF_CHARS, "actual_chars": len(ref)},
                )
            if not _REF_PATTERN.match(ref):
                raise ConfigurationError(
                    f"Tool ref '{ref}' must match pattern '{_REF_PATTERN.pattern}'.",
                    details={"field": f"tools[{index}].ref", "actual": ref, "expected": "lowercase identifier with dots, hyphens, underscores"},
                )
            if ref in seen:
                raise ConfigurationError(
                    f"Duplicate tool ref '{ref}' at index {index}.",
                    details={"field": f"tools[{index}].ref", "actual": ref},
                )
            seen.add(ref)
            if spec.metadata and (_has_secret_like_keys(spec.metadata) or _has_interpolation(spec.metadata)):
                raise ConfigurationError(
                    f"Tool '{ref}' options contain secrets or interpolation patterns.",
                    details={"field": f"tools[{index}].options", "expected": "no secrets or ${} patterns"},
                )

    def _validate_middleware_refs(self) -> None:
        # Rejects blank, overly long, malformed, or duplicate middleware refs and interpolation patterns.
        seen: set[str] = set()
        for index, ref in enumerate(self.middleware_refs):
            if not ref or not ref.strip():
                raise ConfigurationError(
                    f"Middleware ref at index {index} is empty.",
                    details={"field": f"middleware[{index}]", "expected": "non-empty string"},
                )
            if _INTERPOLATION_PATTERN.search(ref):
                raise ConfigurationError(
                    f"Middleware ref '{ref}' must not contain environment interpolation patterns.",
                    details={"field": f"middleware[{index}]", "expected": "no ${...} patterns"},
                )
            if len(ref) > _MAX_REF_CHARS:
                raise ConfigurationError(
                    f"Middleware ref '{ref}' must be at most {_MAX_REF_CHARS} characters.",
                    details={"field": f"middleware[{index}]", "max_chars": _MAX_REF_CHARS, "actual_chars": len(ref)},
                )
            if not _REF_PATTERN.match(ref):
                raise ConfigurationError(
                    f"Middleware ref '{ref}' must match pattern '{_REF_PATTERN.pattern}'.",
                    details={"field": f"middleware[{index}]", "actual": ref, "expected": "lowercase identifier with dots, hyphens, underscores"},
                )
            if ref in seen:
                raise ConfigurationError(
                    f"Duplicate middleware ref '{ref}' at index {index}.",
                    details={"field": f"middleware[{index}]", "actual": ref},
                )
            seen.add(ref)

    # ── capabilities validation ──

    def _validate_capabilities(self) -> None:
        # Rejects blank, overly long, or duplicate capability strings.
        seen: set[str] = set()
        for index, cap in enumerate(self.capabilities):
            if not cap or not cap.strip():
                raise ConfigurationError(
                    f"Capability at index {index} is empty.",
                    details={"field": f"capabilities[{index}]", "expected": "non-empty string"},
                )
            if len(cap) > _MAX_CAPABILITY_CHARS:
                raise ConfigurationError(
                    f"Capability '{cap}' must be at most {_MAX_CAPABILITY_CHARS} characters.",
                    details={"field": f"capabilities[{index}]", "max_chars": _MAX_CAPABILITY_CHARS, "actual_chars": len(cap)},
                )
            if cap in seen:
                raise ConfigurationError(
                    f"Duplicate capability '{cap}' at index {index}.",
                    details={"field": f"capabilities[{index}]", "actual": cap},
                )
            seen.add(cap)

    # ── algorithm validation ──

    def _validate_algorithm(self) -> None:
        # Rejects empty, overly long, or interpolation-containing algorithm strings.
        if self.algorithm is not None:
            if not self.algorithm.strip():
                raise ConfigurationError(
                    "algorithm must be a non-empty string when provided.",
                    details={"field": "algorithm", "expected": "non-empty string"},
                )
            if _INTERPOLATION_PATTERN.search(self.algorithm):
                raise ConfigurationError(
                    "algorithm must not contain environment interpolation patterns.",
                    details={"field": "algorithm", "expected": "no ${...} patterns"},
                )
            if len(self.algorithm) > _MAX_REF_CHARS:
                raise ConfigurationError(
                    f"algorithm must be at most {_MAX_REF_CHARS} characters.",
                    details={"field": "algorithm", "max_chars": _MAX_REF_CHARS, "actual_chars": len(self.algorithm)},
                )

    # ── output_schema validation ──

    def _validate_output_schema(self) -> None:
        # Rejects non-dict, overly large, or secret-containing output schemas.
        if self.output_schema is None:
            return
        if not isinstance(self.output_schema, dict):
            raise ConfigurationError(
                "output_schema must be a mapping when provided.",
                details={"field": "output_schema", "actual_type": type(self.output_schema).__name__},
            )
        if len(self.output_schema) > 200:
            raise ConfigurationError(
                "output_schema must have at most 200 top-level keys.",
                details={"field": "output_schema", "max_keys": 200, "actual_keys": len(self.output_schema)},
            )
        if _has_secret_like_keys(self.output_schema):
            raise ConfigurationError(
                "output_schema contains secret-like keys.",
                details={"field": "output_schema", "expected": "no secret keys"},
            )

    # ── metadata validation ──

    def _validate_metadata(self) -> None:
        # Sanitizes metadata for secret keys and interpolation patterns.
        object.__setattr__(self, "metadata", _sanitize_metadata(dict(self.metadata)))
        if _has_secret_like_keys(self.metadata) or _has_interpolation(self.metadata):
            pass  # _sanitize_metadata already raised

    # ── runtime compatibility validation ──

    def _validate_runtime_compatibility(self) -> None:
        # Rejects settings that are incompatible with non-linear runtimes.
        if self.runtime == AgentRuntimeType.LINEAR:
            return
        if self.trace_option is not None and self.trace_option.enabled:
            raise ConfigurationError(
                "trace_option is not supported with non-linear runtimes.",
                details={
                    "field": "trace_option",
                    "runtime": self.runtime.value,
                    "expected": "trace_option must be None for non-linear runtimes",
                },
            )
        if self.middleware_refs:
            raise ConfigurationError(
                "middleware is not supported with non-linear runtimes.",
                details={
                    "field": "middleware",
                    "runtime": self.runtime.value,
                    "expected": "middleware must be empty for non-linear runtimes",
                },
            )
        if self.algorithm is not None:
            raise ConfigurationError(
                "algorithm is not supported with non-linear runtimes.",
                details={
                    "field": "algorithm",
                    "runtime": self.runtime.value,
                    "expected": "algorithm must be None for non-linear runtimes",
                },
            )
        loop = self.loop
        has_tool_settings = (
            loop.tool_settings is not None
            and any(getattr(loop.tool_settings, attr) is not None for attr in (
                "max_calls", "max_calls_per_tool", "result_max_chars", "max_calls_per_iteration",
                "max_identical_calls", "max_consecutive_failures", "max_error_calls",
                "tool_timeout_seconds", "sliding_window_max_calls",
            ))
        )
        if has_tool_settings:
            raise ConfigurationError(
                "loop.tool_settings is not supported with non-linear runtimes.",
                details={
                    "field": "loop.tool_settings",
                    "runtime": self.runtime.value,
                    "expected": "loop.tool_settings must be default for non-linear runtimes",
                },
            )
        if loop.output_contracts:
            raise ConfigurationError(
                "loop.output_contracts are not supported with non-linear runtimes.",
                details={
                    "field": "loop.output_contracts",
                    "runtime": self.runtime.value,
                    "expected": "output_contracts must be empty for non-linear runtimes",
                },
            )
        if self.algorithm is not None:
            raise ConfigurationError(
                "algorithm is not supported with non-linear runtimes.",
                details={
                    "field": "algorithm",
                    "runtime": self.runtime.value,
                    "expected": "algorithm must be None for non-linear runtimes",
                },
            )


__all__ = ["AgentDescriptor"]

"""Context Protocol Header

Description:
    Defines typed, declarative configuration objects produced by the YAML loader.
Purpose:
    Separates safe parsing and intrinsic validation from application-owned runtime
    resolution of tools and middleware.
Architecture:
    - AgentSettings: Validated agent construction inputs and declarative references.
    - ToolDefinition: A named tool reference with data-only options.
    - MiddlewareDefinition: A named middleware reference with data-only options.
Relations:
    Constructed by vidbyte.config.loader and consumed by application composition code.
Non-Goals:
    Does not import references, instantiate tools or middleware, or resolve secrets.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.errors import ConfigurationError


@dataclass(slots=True)
class ToolDefinition:
    """A declarative tool reference and its serializable configuration options."""

    ref: str
    options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates the reference and copies options so callers retain no mutable alias.
        self.ref = self._required_text(self.ref, "ToolDefinition.ref")
        self.options = self._mapping_copy(self.options, "ToolDefinition.options")
        self._serializable(self.options, "ToolDefinition.options")

    @staticmethod
    def _required_text(value: object, field_name: str) -> str:
        # Returns a non-blank string or raises the SDK configuration error contract.
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"{field_name} must be a non-blank string.", details={"field": field_name})
        return value.strip()

    @staticmethod
    def _mapping_copy(value: object, field_name: str) -> dict[str, Any]:
        # Validates mapping-shaped options without imposing application-specific option schemas.
        if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
            raise ConfigurationError(f"{field_name} must be a mapping with string keys.", details={"field": field_name})
        return dict(value)

    @staticmethod
    def _serializable(value: object, field_name: str, ancestry: frozenset[int] = frozenset()) -> None:
        # Rejects Python objects that cannot safely be represented as configuration data.
        if value is None or isinstance(value, (bool, int, float)):
            return
        if isinstance(value, str):
            if "${" in value:
                raise ConfigurationError("Configuration does not support environment interpolation.", details={"field": field_name})
            return
        if isinstance(value, list):
            if id(value) in ancestry:
                raise ConfigurationError("Configuration must not contain cyclic aliases.", details={"field": field_name})
            for index, item in enumerate(value):
                ToolDefinition._serializable(item, f"{field_name}[{index}]", ancestry | {id(value)})
            return
        if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
            if id(value) in ancestry:
                raise ConfigurationError("Configuration must not contain cyclic aliases.", details={"field": field_name})
            for key, item in value.items():
                ToolDefinition._serializable(item, f"{field_name}.{key}", ancestry | {id(value)})
            return
        raise ConfigurationError("Configuration values must be scalars, lists, or string-keyed mappings.", details={"field": field_name})


@dataclass(slots=True)
class MiddlewareDefinition:
    """A declarative middleware reference and its serializable configuration options."""

    ref: str
    options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates the reference and copies options so callers retain no mutable alias.
        self.ref = ToolDefinition._required_text(self.ref, "MiddlewareDefinition.ref")
        self.options = ToolDefinition._mapping_copy(self.options, "MiddlewareDefinition.options")


@dataclass(slots=True)
class AgentSettings:
    """Validated declarative inputs for constructing one BaseAgent instance."""

    name: str
    system_prompt: str
    provider: str
    model_name: str
    runtime: AgentRuntimeType | str = AgentRuntimeType.LINEAR
    loop: AgentLoopSettings = field(default_factory=AgentLoopSettings)
    tool_refs: tuple[str, ...] = ()
    middleware_refs: tuple[str, ...] = ()
    description: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalizes intrinsic fields before any agent, tool, or middleware is constructed.
        self.name = ToolDefinition._required_text(self.name, "AgentSettings.name")
        self.system_prompt = ToolDefinition._required_text(self.system_prompt, "AgentSettings.system_prompt")
        self.provider = ToolDefinition._required_text(self.provider, "AgentSettings.provider")
        self.model_name = ToolDefinition._required_text(self.model_name, "AgentSettings.model_name")
        self.runtime = self._runtime_value(self.runtime)
        self.loop = self._loop_settings(self.loop)
        self.tool_refs = self._references(self.tool_refs, "AgentSettings.tool_refs")
        self.middleware_refs = self._references(self.middleware_refs, "AgentSettings.middleware_refs")
        self.description = self._optional_text(self.description, "AgentSettings.description")
        self.capabilities = self._references(self.capabilities, "AgentSettings.capabilities")
        self.metadata = ToolDefinition._mapping_copy(self.metadata, "AgentSettings.metadata")
        ToolDefinition._serializable(self.metadata, "AgentSettings.metadata")

    def to_agent_kwargs(self, *, tools: Sequence[object] = (), middleware: Sequence[object] = ()) -> dict[str, Any]:
        # Returns BaseAgent-compatible kwargs after the application resolves declarative references.
        return {
            "name": self.name,
            "system_prompt": self.system_prompt,
            "provider": self.provider,
            "model_name": self.model_name,
            "runtime": self.runtime,
            "agent_loop_settings": self.loop,
            "tools": tuple(tools),
            "middleware": tuple(middleware),
            "description": self.description,
            "capabilities": self.capabilities,
            "metadata": dict(self.metadata),
        }

    @staticmethod
    def _runtime_value(value: AgentRuntimeType | str) -> AgentRuntimeType:
        # Converts a public runtime string to the canonical runtime enum.
        try:
            return AgentRuntimeType(value)
        except (TypeError, ValueError) as error:
            raise ConfigurationError("AgentSettings.runtime is not a supported runtime.", details={"field": "runtime"}) from error

    @staticmethod
    def _loop_settings(value: object) -> AgentLoopSettings:
        # Requires callers to pass the existing validated loop-settings abstraction.
        if not isinstance(value, AgentLoopSettings):
            raise ConfigurationError("AgentSettings.loop must be an AgentLoopSettings instance.", details={"field": "loop"})
        return value

    @staticmethod
    def _references(value: object, field_name: str) -> tuple[str, ...]:
        # Normalizes unique non-blank references while rejecting a scalar string as a sequence.
        if isinstance(value, str) or not isinstance(value, Sequence):
            raise ConfigurationError(f"{field_name} must be a sequence of non-blank strings.", details={"field": field_name})
        references = tuple(ToolDefinition._required_text(item, field_name) for item in value)
        if len(set(references)) != len(references):
            raise ConfigurationError(f"{field_name} must not contain duplicate references.", details={"field": field_name})
        return references

    @staticmethod
    def _optional_text(value: object, field_name: str) -> str:
        # Accepts an empty description but otherwise applies the public string contract.
        if not isinstance(value, str):
            raise ConfigurationError(f"{field_name} must be a string.", details={"field": field_name})
        return value.strip()

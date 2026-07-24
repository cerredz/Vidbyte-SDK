"""Context Protocol Header

Description:
    Defines the typed, declarative configuration dataclasses produced by the public YAML
    loader: the polymorphic AgentSettings hierarchy plus the nested ToolDefinition and
    MiddlewareDefinition entries an agent document carries.
Purpose:
    Keeps every configuration data contract in the central vidbyte.lib.dataclasses namespace
    and makes each dataclass the single place that validates its own shape, so the loader only
    parses YAML and each class validates its fields against the SDK's canonical sources of
    truth (ProviderModelRegistry, AgentRuntimeType, AgentType, AgentLoopSettings).
Architecture:
    - _ConfigValidation: Shared, minimal validation primitives used by every config dataclass.
    - ToolDefinition / MiddlewareDefinition: A named ref plus data-only options, nested per agent.
    - AgentSettings: Base agent construction inputs; polymorphic on an AgentType discriminator.
    - BaseAgentSettings: The fully-supported ``type: base`` agent (plain BaseAgent).
    - AggregateAgentSettings / ContinualTraceAgentSettings / HandoffAgentSettings /
      MultiAgentSettings / AdversarialAgentSettings: Registered facade/composite types that are
      recognized but not yet loadable from YAML; requesting one raises a specific error.
    - _AGENT_TYPES: Maps each AgentType to its settings class for from_mapping dispatch.
Relations:
    Constructed by vidbyte.config.loader; re-exported through vidbyte.config.types. AgentSettings
    mirrors the YAML-serializable construction inputs of vidbyte.agents.base.BaseAgent; the
    non-serializable inputs (permission_policy, context_manager, tracer, handoff, ...) are out of
    scope for the declarative surface. It stays separate from the frozen in-process AgentSpec.
Non-Goals:
    Does not import references, instantiate tools/middleware/agents, or resolve secrets.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from vidbyte.lib.enums import AgentRuntimeType, AgentType
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.registries.models import ProviderModelRegistry

if TYPE_CHECKING:
    from vidbyte.agents.settings import AgentLoopSettings

_SECRET_KEYS = frozenset({"api_key", "token", "password", "secret"})
_SECRET_SUFFIXES = ("_api_key", "_token", "_password", "_secret")


def _default_loop() -> "AgentLoopSettings":
    # Builds an empty loop-settings object, importing lazily to avoid an agents<->lib cycle.
    from vidbyte.agents.settings import AgentLoopSettings

    return AgentLoopSettings()


class _ConfigValidation:
    """Shared validation primitives so every config dataclass validates its own fields."""

    __slots__ = ()

    @staticmethod
    def _error(message: str, field_name: str, **extra: Any) -> ConfigurationError:
        # Builds the shared configuration error naming the exact offending field.
        return ConfigurationError(message, details={"field": field_name, **extra})

    @classmethod
    def _text(cls, value: object, field_name: str) -> str:
        # Returns a non-blank stripped string or names the field and the type received.
        if not isinstance(value, str) or not value.strip():
            raise cls._error(f"'{field_name}' must be a non-blank string.", field_name, actual_type=type(value).__name__)
        return value.strip()

    @classmethod
    def _optional_text(cls, value: object, field_name: str) -> str:
        # Accepts an empty string but otherwise applies the non-empty string contract.
        if not isinstance(value, str):
            raise cls._error(f"'{field_name}' must be a string.", field_name, actual_type=type(value).__name__)
        return value.strip()

    @classmethod
    def _mapping(cls, value: object, field_name: str) -> dict[str, Any]:
        # Returns a string-keyed shallow copy or reports why the field is not a valid mapping.
        if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
            raise cls._error(f"'{field_name}' must be a mapping with string keys.", field_name, actual_type=type(value).__name__)
        return dict(value)

    @classmethod
    def _refs(cls, value: object, field_name: str) -> tuple[str, ...]:
        # Normalizes a list of unique non-blank string references, rejecting a bare string.
        if isinstance(value, str) or not isinstance(value, Sequence):
            raise cls._error(f"'{field_name}' must be a list of non-blank strings.", field_name, actual_type=type(value).__name__)
        refs = tuple(cls._text(item, f"{field_name}[{index}]") for index, item in enumerate(value))
        duplicates = sorted({ref for ref in refs if refs.count(ref) > 1})
        if duplicates:
            raise cls._error(f"'{field_name}' must not contain duplicate references.", field_name, duplicates=duplicates)
        return refs

    @classmethod
    def _only(cls, payload: Mapping[str, Any], allowed: frozenset[str], field_name: str) -> None:
        # Rejects schema drift instead of silently ignoring unsupported configuration keys.
        unknown = sorted(set(payload).difference(allowed))
        if unknown:
            raise cls._error(f"'{field_name}' contains unsupported field(s): {', '.join(unknown)}.", f"{field_name}.{unknown[0]}", unknown=unknown, allowed=sorted(allowed))

    @classmethod
    def _serializable(cls, value: object, field_name: str, ancestry: frozenset[int] = frozenset()) -> None:
        # Accepts only YAML data values, rejecting secrets, env interpolation, and cyclic aliases.
        if value is None or isinstance(value, (bool, int, float)):
            return
        if isinstance(value, str):
            if "${" in value:
                raise cls._error("Configuration does not support environment interpolation.", field_name)
            return
        if isinstance(value, list):
            cls._guard_cycle(value, field_name, ancestry)
            for index, item in enumerate(value):
                cls._serializable(item, f"{field_name}[{index}]", ancestry | {id(value)})
            return
        if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
            cls._guard_cycle(value, field_name, ancestry)
            for key, item in value.items():
                if key.strip().lower() in _SECRET_KEYS or key.strip().lower().endswith(_SECRET_SUFFIXES):
                    raise cls._error("Configuration must not contain YAML-held secrets.", f"{field_name}.{key}")
                cls._serializable(item, f"{field_name}.{key}", ancestry | {id(value)})
            return
        raise cls._error("Configuration values must be YAML scalars, lists, or string-keyed mappings.", field_name, actual_type=type(value).__name__)

    @classmethod
    def _guard_cycle(cls, value: object, field_name: str, ancestry: frozenset[int]) -> None:
        # Rejects a container that references itself so validation cannot recurse forever.
        if id(value) in ancestry:
            raise cls._error("Configuration must not contain cyclic aliases.", field_name)


@dataclass(slots=True)
class _RefOptionsDefinition(_ConfigValidation):
    """A declarative ``{ref, options}`` reference with serializable, secret-free options."""

    ref: str
    options: dict[str, Any] = field(default_factory=dict)

    _LABEL: ClassVar[str] = "definition"
    _ALLOWED_FIELDS: ClassVar[frozenset[str]] = frozenset({"ref", "options"})

    def __post_init__(self) -> None:
        # Validates the reference and copies options so callers retain no mutable alias.
        self.ref = self._text(self.ref, f"{self._LABEL}.ref")
        self.options = self._mapping(self.options, f"{self._LABEL}.options")
        self._serializable(self.options, f"{self._LABEL}.options")

    @classmethod
    def from_mapping(cls, data: object, field_name: str) -> "_RefOptionsDefinition":
        # Validates a single ``{ref, options}`` declaration and builds the definition.
        item = cls._mapping(data, field_name)
        cls._only(item, cls._ALLOWED_FIELDS, field_name)
        return cls(ref=item.get("ref"), options=item.get("options", {}))

    @staticmethod
    def expected_structure() -> dict[str, Any]:
        # Returns the document shape a developer should follow for one entry.
        return {"ref": "<reference>", "options": {}}


@dataclass(slots=True)
class ToolDefinition(_RefOptionsDefinition):
    """A declarative tool reference nested inside an agent document."""

    _LABEL: ClassVar[str] = "ToolDefinition"

    @staticmethod
    def expected_structure() -> dict[str, Any]:
        # Returns the document shape a developer should follow for one tool entry.
        return {"ref": "<tool-reference>", "options": {}}


@dataclass(slots=True)
class MiddlewareDefinition(_RefOptionsDefinition):
    """A declarative middleware reference nested inside an agent document."""

    _LABEL: ClassVar[str] = "MiddlewareDefinition"

    @staticmethod
    def expected_structure() -> dict[str, Any]:
        # Returns the document shape a developer should follow for one middleware entry.
        return {"ref": "<middleware-reference>", "options": {}}


@dataclass(slots=True)
class AgentSettings(_ConfigValidation):
    """Validated declarative inputs for constructing one agent; polymorphic on ``type``."""

    type: AgentType | str
    name: str
    system_prompt: str
    provider: str | None = None
    model_name: str | None = None
    temperature: float | None = None
    runtime: AgentRuntimeType | str = AgentRuntimeType.LINEAR
    loop: "AgentLoopSettings | Mapping[str, Any]" = field(default_factory=_default_loop)
    algorithm: str | None = None
    tools: tuple[ToolDefinition, ...] = ()
    middleware: tuple[MiddlewareDefinition, ...] = ()
    description: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    _SUPPORTED: ClassVar[bool] = False
    _REQUIRED_FIELDS: ClassVar[tuple[str, ...]] = ("name", "system_prompt")
    _ALLOWED_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"type", "name", "system_prompt", "provider", "model_name", "temperature", "runtime", "loop", "algorithm", "tools", "middleware", "description", "capabilities", "metadata"}
    )

    def __post_init__(self) -> None:
        # Normalizes and validates every field against the SDK's canonical sources of truth.
        self.type = self.type if isinstance(self.type, AgentType) else AgentType(self.type)
        self.name = self._text(self.name, "agent.name")
        self.system_prompt = self._text(self.system_prompt, "agent.system_prompt")
        self.provider = self._validated_provider(self.provider)
        self.model_name = self._validated_model(self.model_name)
        self.temperature = self._optional_number(self.temperature, "agent.temperature")
        self.runtime = self._runtime(self.runtime)
        self.loop = self._loop(self.loop)
        self.algorithm = None if self.algorithm is None else self._optional_text(self.algorithm, "agent.algorithm")
        self.tools = self._definitions(self.tools, ToolDefinition, "agent.tools")
        self.middleware = self._definitions(self.middleware, MiddlewareDefinition, "agent.middleware")
        self.description = self._optional_text(self.description, "agent.description")
        self.capabilities = self._refs(self.capabilities, "agent.capabilities")
        self.metadata = self._mapping(self.metadata, "agent.metadata")
        self._serializable(self.metadata, "agent.metadata")

    @classmethod
    def from_mapping(cls, data: object, field_name: str = "agent") -> "AgentSettings":
        # Validates an agent document body, dispatches on ``type``, and builds validated settings.
        payload = cls._mapping(data, field_name)
        target = cls._resolve_type(payload.get("type", AgentType.BASE.value), field_name)
        cls._only(payload, target._ALLOWED_FIELDS, field_name)
        for required in target._REQUIRED_FIELDS:
            if required not in payload:
                raise cls._error(f"'{field_name}' is missing required field '{required}'.", f"{field_name}.{required}")
        return target(
            type=target._AGENT_TYPE,
            name=payload.get("name"),
            system_prompt=payload.get("system_prompt"),
            provider=payload.get("provider"),
            model_name=payload.get("model_name"),
            temperature=payload.get("temperature"),
            runtime=payload.get("runtime", AgentRuntimeType.LINEAR),
            loop=payload.get("loop", {}),
            algorithm=payload.get("algorithm"),
            tools=payload.get("tools", ()),
            middleware=payload.get("middleware", ()),
            description=payload.get("description", ""),
            capabilities=payload.get("capabilities", ()),
            metadata=payload.get("metadata", {}),
        )

    def to_agent_kwargs(self, *, tools: Sequence[object] = (), middleware: Sequence[object] = ()) -> dict[str, Any]:
        # Returns BaseAgent-compatible kwargs after the application resolves declarative references.
        return {
            "name": self.name,
            "system_prompt": self.system_prompt,
            "provider": self.provider,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "runtime": self.runtime,
            "agent_loop_settings": self.loop,
            "algorithm": self.algorithm,
            "tools": tuple(tools),
            "middleware": tuple(middleware),
            "description": self.description,
            "capabilities": self.capabilities,
            "metadata": dict(self.metadata),
        }

    @staticmethod
    def expected_structure() -> dict[str, Any]:
        # Returns the document shape a developer should follow for a base agent document.
        return {
            "type": AgentType.BASE.value,
            "name": "<agent-name>",
            "system_prompt": "<system-prompt>",
            "provider": "<provider>",
            "model_name": "<model-name>",
            "temperature": "<float|null>",
            "runtime": AgentRuntimeType.LINEAR.value,
            "loop": {"max_iterations": "<int>", "max_tokens": "<int>"},
            "algorithm": "<algorithm-name|null>",
            "tools": [ToolDefinition.expected_structure()],
            "middleware": [MiddlewareDefinition.expected_structure()],
            "description": "",
            "capabilities": ["<capability>"],
            "metadata": {},
        }

    @classmethod
    def _resolve_type(cls, raw_type: object, field_name: str) -> type["AgentSettings"]:
        # Resolves the ``type`` discriminator to a supported settings class or raises a precise error.
        try:
            agent_type = AgentType(raw_type)
        except (TypeError, ValueError) as error:
            raise cls._error(f"'{field_name}.type' must be one of {list(AgentType.values())}.", f"{field_name}.type", found=raw_type) from error
        target = _AGENT_TYPES[agent_type]
        if not target._SUPPORTED:
            raise cls._error(f"agent type '{agent_type.value}' is registered but not yet loadable from YAML; only 'base' is supported.", f"{field_name}.type", found=agent_type.value, supported=["base"])
        return target

    @classmethod
    def _validated_provider(cls, value: object) -> str | None:
        # Validates the provider against the canonical ProviderModelRegistry, or leaves it unset.
        if value is None:
            return None
        provider = cls._text(value, "agent.provider")
        try:
            ProviderModelRegistry.validate_provider(provider)
        except ConfigurationError as error:
            raise cls._error(str(error), "agent.provider", actual_value=provider) from error
        return provider

    @classmethod
    def _validated_model(cls, value: object) -> str | None:
        # Validates the model name against the canonical ProviderModelRegistry, or leaves it unset.
        if value is None:
            return None
        model = cls._text(value, "agent.model_name")
        try:
            ProviderModelRegistry.validate_model(model)
        except ConfigurationError as error:
            raise cls._error(str(error), "agent.model_name", actual_value=model) from error
        return model

    @classmethod
    def _optional_number(cls, value: object, field_name: str) -> float | None:
        # Accepts a real number (not bool) or leaves the field unset.
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise cls._error(f"'{field_name}' must be a number.", field_name, actual_type=type(value).__name__)
        return float(value)

    @classmethod
    def _runtime(cls, value: object) -> AgentRuntimeType:
        # Converts a public runtime string to the canonical runtime enum.
        try:
            return AgentRuntimeType(value)
        except (TypeError, ValueError) as error:
            raise cls._error(f"'agent.runtime' must be one of {sorted(member.value for member in AgentRuntimeType)}.", "agent.runtime", actual_value=value) from error

    @classmethod
    def _loop(cls, value: object) -> "AgentLoopSettings":
        # Accepts an existing loop object or validates and builds one from a document mapping.
        from vidbyte.agents.settings import AgentLoopSettings

        if isinstance(value, AgentLoopSettings):
            return value
        mapping = cls._mapping(value, "agent.loop")
        if "allowed_tools" in mapping:
            allowed = mapping["allowed_tools"]
            if isinstance(allowed, str) or not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
                raise cls._error("'agent.loop.allowed_tools' must be a list of strings.", "agent.loop.allowed_tools", actual_type=type(allowed).__name__)
            mapping["allowed_tools"] = tuple(allowed)
        try:
            return AgentLoopSettings(**mapping)
        except (TypeError, ValueError, ConfigurationError) as error:
            raise cls._error(f"'agent.loop' is invalid: {error}", "agent.loop") from error

    @classmethod
    def _definitions(cls, value: object, definition: type[_RefOptionsDefinition], field_name: str) -> tuple[Any, ...]:
        # Builds nested tool/middleware definitions and rejects duplicate references.
        if isinstance(value, (str, Mapping)) or not isinstance(value, Sequence):
            raise cls._error(f"'{field_name}' must be a list of {{ref, options}} entries.", field_name, actual_type=type(value).__name__)
        items = tuple(item if isinstance(item, definition) else definition.from_mapping(item, f"{field_name}[{index}]") for index, item in enumerate(value))
        refs = [item.ref for item in items]
        duplicates = sorted({ref for ref in refs if refs.count(ref) > 1})
        if duplicates:
            raise cls._error(f"'{field_name}' must not contain duplicate references: {', '.join(duplicates)}.", field_name, duplicates=duplicates)
        return items


@dataclass(slots=True)
class BaseAgentSettings(AgentSettings):
    """``type: base`` — the fully-supported plain BaseAgent settings."""

    _SUPPORTED: ClassVar[bool] = True
    _AGENT_TYPE: ClassVar[AgentType] = AgentType.BASE


@dataclass(slots=True)
class AggregateAgentSettings(AgentSettings):
    """``type: aggregate`` — AggregateAgent; registered but not yet loadable from YAML."""

    _AGENT_TYPE: ClassVar[AgentType] = AgentType.AGGREGATE


@dataclass(slots=True)
class ContinualTraceAgentSettings(AgentSettings):
    """``type: continual_trace`` — ContinualTraceAgent; registered but not yet loadable from YAML."""

    _AGENT_TYPE: ClassVar[AgentType] = AgentType.CONTINUAL_TRACE


@dataclass(slots=True)
class HandoffAgentSettings(AgentSettings):
    """``type: handoff`` — HandoffAgent; registered but not yet loadable from YAML."""

    _AGENT_TYPE: ClassVar[AgentType] = AgentType.HANDOFF


@dataclass(slots=True)
class MultiAgentSettings(AgentSettings):
    """``type: multi`` — MultiAgent; registered but not yet loadable from YAML."""

    _AGENT_TYPE: ClassVar[AgentType] = AgentType.MULTI


@dataclass(slots=True)
class AdversarialAgentSettings(AgentSettings):
    """``type: adversarial`` — AdversarialAgent; registered but not yet loadable from YAML."""

    _AGENT_TYPE: ClassVar[AgentType] = AgentType.ADVERSARIAL


# BASE also carries its own AgentType so a directly-constructed AgentSettings can be resolved.
AgentSettings._AGENT_TYPE = AgentType.BASE  # type: ignore[attr-defined]

_AGENT_TYPES: dict[AgentType, type[AgentSettings]] = {
    AgentType.BASE: BaseAgentSettings,
    AgentType.AGGREGATE: AggregateAgentSettings,
    AgentType.CONTINUAL_TRACE: ContinualTraceAgentSettings,
    AgentType.HANDOFF: HandoffAgentSettings,
    AgentType.MULTI: MultiAgentSettings,
    AgentType.ADVERSARIAL: AdversarialAgentSettings,
}


__all__ = [
    "AdversarialAgentSettings",
    "AggregateAgentSettings",
    "AgentSettings",
    "BaseAgentSettings",
    "ContinualTraceAgentSettings",
    "HandoffAgentSettings",
    "MiddlewareDefinition",
    "MultiAgentSettings",
    "ToolDefinition",
]

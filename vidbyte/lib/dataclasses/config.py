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
    - _ConfigValidation: Shared validation primitives (text, bounds, references, serializability)
      used by every config dataclass.
    - ToolDefinition / MiddlewareDefinition / ContextItemDefinition: A named ref plus data-only
      options, nested per agent, reporting errors at their document position.
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
    Model, provider, modality, and algorithm names are checked against ProviderModelRegistry,
    ModalityDetector, and ContextWindow rather than against a list duplicated here.
Non-Goals:
    Does not import references, instantiate tools/middleware/agents, or resolve secrets. An entry's
    ``options`` are validated as inert data, never against the referenced component's own schema:
    that check belongs to whoever resolves the ref, which is the only layer that can import it.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from vidbyte.lib.agents.modality_detector import ModalityDetector
from vidbyte.lib.dataclasses.agents import AgentMetadata
from vidbyte.lib.enums import AgentRuntimeType, AgentType, ModelModality
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.registries.models import ProviderModelRegistry

if TYPE_CHECKING:
    from vidbyte.agents.settings import AgentLoopSettings

_SECRET_KEYS = frozenset(
    {"api_key", "token", "password", "passwd", "secret", "authorization", "credential", "credentials", "private_key", "access_key", "secret_key", "session_token", "cookie", "bearer"}
)
_SECRET_SUFFIXES = ("_api_key", "_token", "_password", "_secret", "_credential", "_credentials", "_private_key", "_access_key", "_secret_key")

# Bounds that turn a plausible-but-unusable document into a load-time error naming the field.
_MAX_NAME_CHARS = 64
_MAX_SYSTEM_PROMPT_CHARS = 100_000
_MAX_DESCRIPTION_CHARS = 1_024
_MAX_MODEL_NAME_CHARS = 128
_MAX_CAPABILITIES = 64
_MAX_CAPABILITY_CHARS = 128
_MAX_DEFINITIONS = 128
_MAX_NESTING_DEPTH = 32
_MIN_TEMPERATURE = 0.0
_MAX_TEMPERATURE = 2.0

# Agent names become provider tool names once an agent is exposed via agent_metadata.
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_REF_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")

# Providers whose accepted sampling range is narrower than the SDK-wide 0.0-2.0 window.
_PROVIDER_TEMPERATURE_CEILING = {"anthropic": 1.0}

# Runtimes whose executors have no middleware, in-context-learning, or continual-tracing stage.
_NON_LINEAR_RUNTIMES = frozenset({AgentRuntimeType.MCTS_SEARCH, AgentRuntimeType.ACTOR_MODEL, AgentRuntimeType.ACTOR_MODEL_P2P, AgentRuntimeType.ACTOR_MODEL_BROADCAST})

# Mirrors the AgentLoopSettings keyword arguments so an unknown loop key names the valid set
# instead of surfacing a raw "unexpected keyword argument" TypeError from the constructor.
_LOOP_FIELDS = frozenset(
    {
        "max_iterations", "max_tokens", "max_tool_calls", "max_queued_prompts", "max_parallel_tool_calls", "max_retries", "timeout_seconds",
        "context_window_budget", "compaction_trigger_tokens", "compaction_target_tokens", "allowed_tools", "tool_error_policy", "tool_settings",
        "output_contracts", "max_contract_rejections",
    }
)


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
    def _bounded_text(cls, value: str, field_name: str, limit: int, *, reason: str = "") -> str:
        # Applies one character ceiling so an oversized value fails here instead of at the provider.
        if len(value) > limit:
            suffix = f" {reason}" if reason else ""
            raise cls._error(f"'{field_name}' must be {limit} characters or fewer; got {len(value)}.{suffix}", field_name, limit=limit, actual_length=len(value))
        return value

    @classmethod
    def _printable(cls, value: str, field_name: str) -> str:
        # Rejects control characters, which survive a UTF-8 read but corrupt a prompt sent to a model.
        for index, character in enumerate(value):
            if (ord(character) < 32 and character not in "\t\n\r") or ord(character) == 127:
                raise cls._error(f"'{field_name}' must not contain control characters (found U+{ord(character):04X} at offset {index}).", field_name, offset=index, codepoint=f"U+{ord(character):04X}")
        return value

    @classmethod
    def _bounded_count(cls, items: tuple[Any, ...], field_name: str, limit: int) -> tuple[Any, ...]:
        # Applies one entry ceiling so an unbounded list fails here instead of at the provider.
        if len(items) > limit:
            raise cls._error(f"'{field_name}' must contain {limit} entries or fewer; got {len(items)}.", field_name, limit=limit, actual_count=len(items))
        return items

    @classmethod
    def _positive_int(cls, value: object, field_name: str) -> int | None:
        # Accepts a strictly positive integer (not bool) or leaves the field unset.
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise cls._error(f"'{field_name}' must be an integer.", field_name, actual_type=type(value).__name__)
        if value <= 0:
            raise cls._error(f"'{field_name}' must be greater than zero; got {value}.", field_name, actual_value=value)
        return value

    @classmethod
    def _reference(cls, value: str, field_name: str) -> str:
        # Requires a reference to look like a resolvable name so a typo fails at the offending line.
        if not _REF_PATTERN.match(value):
            raise cls._error(f"'{field_name}' must be a valid reference name matching {_REF_PATTERN.pattern}; got {value!r}.", field_name, actual_value=value, pattern=_REF_PATTERN.pattern)
        return value

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
    def _serializable(cls, value: object, field_name: str, ancestry: frozenset[int] = frozenset(), depth: int = 0) -> None:
        # Accepts only YAML data values, rejecting secrets, env interpolation, cycles, and deep nesting.
        if value is None or isinstance(value, (bool, int, float)):
            return
        if isinstance(value, str):
            if "${" in value:
                raise cls._error("Configuration does not support environment interpolation.", field_name)
            return
        if isinstance(value, list):
            cls._guard_cycle(value, field_name, ancestry)
            cls._guard_depth(field_name, depth)
            for index, item in enumerate(value):
                cls._serializable(item, f"{field_name}[{index}]", ancestry | {id(value)}, depth + 1)
            return
        if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
            cls._guard_cycle(value, field_name, ancestry)
            cls._guard_depth(field_name, depth)
            for key, item in value.items():
                if key.strip().lower() in _SECRET_KEYS or key.strip().lower().endswith(_SECRET_SUFFIXES):
                    raise cls._error("Configuration must not contain YAML-held secrets.", f"{field_name}.{key}")
                cls._serializable(item, f"{field_name}.{key}", ancestry | {id(value)}, depth + 1)
            return
        raise cls._error("Configuration values must be YAML scalars, lists, or string-keyed mappings.", field_name, actual_type=type(value).__name__)

    @classmethod
    def _guard_cycle(cls, value: object, field_name: str, ancestry: frozenset[int]) -> None:
        # Rejects a container that references itself so validation cannot recurse forever.
        if id(value) in ancestry:
            raise cls._error("Configuration must not contain cyclic aliases.", field_name)

    @classmethod
    def _guard_depth(cls, field_name: str, depth: int) -> None:
        # @intent bounded-recursion
        # An acyclic but deeply nested document would exhaust the interpreter stack and surface a
        # RecursionError instead of a ConfigurationError, so the depth is capped before recursing.
        if depth >= _MAX_NESTING_DEPTH:
            raise cls._error(f"'{field_name}' exceeds the maximum nesting depth of {_MAX_NESTING_DEPTH}.", field_name, max_depth=_MAX_NESTING_DEPTH)


@dataclass(slots=True)
class _RefOptionsDefinition(_ConfigValidation):
    """A declarative ``{ref, options}`` reference with serializable, secret-free options."""

    ref: str
    options: dict[str, Any] = field(default_factory=dict)
    path: str = ""

    _LABEL: ClassVar[str] = "definition"
    _ALLOWED_FIELDS: ClassVar[frozenset[str]] = frozenset({"ref", "options"})

    def __post_init__(self) -> None:
        # @intent positional-error-paths
        # Errors are reported against the document position the entry came from ("agent.tools[2].ref")
        # rather than the class label, so a reader can find the offending line without counting entries.
        base = self.path or self._LABEL
        self.ref = self._reference(self._text(self.ref, f"{base}.ref"), f"{base}.ref")
        self.options = self._mapping(self.options, f"{base}.options")
        self._serializable(self.options, f"{base}.options")

    @classmethod
    def from_mapping(cls, data: object, field_name: str) -> "_RefOptionsDefinition":
        # Validates a ``ref`` shorthand or a ``{ref, options}`` declaration and builds the definition.
        if isinstance(data, str):
            return cls(ref=data, options={}, path=field_name)
        item = cls._mapping(data, field_name)
        cls._only(item, cls._ALLOWED_FIELDS, field_name)
        return cls(ref=item.get("ref"), options=item.get("options", {}), path=field_name)

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
class ContextItemDefinition(_RefOptionsDefinition):
    """A declarative context-item reference nested inside an agent document."""

    _LABEL: ClassVar[str] = "ContextItemDefinition"

    @staticmethod
    def expected_structure() -> dict[str, Any]:
        # Returns the document shape a developer should follow for one context-item entry.
        return {"ref": "<context-item-reference>", "options": {}}


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
    context_items: tuple[ContextItemDefinition, ...] = ()
    description: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    agent_metadata: "AgentMetadata | Mapping[str, Any] | None" = None
    output_schema: dict[str, Any] | None = None
    trace_option: "Any | None" = None
    max_tool_rounds: int | None = None

    _SUPPORTED: ClassVar[bool] = False
    _AGENT_TYPE: ClassVar[AgentType] = AgentType.BASE
    _REQUIRED_FIELDS: ClassVar[tuple[str, ...]] = ("name", "system_prompt")
    _ALLOWED_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "type", "name", "system_prompt", "provider", "model_name", "temperature", "runtime", "loop", "algorithm", "tools", "middleware",
            "context_items", "description", "capabilities", "metadata", "agent_metadata", "output_schema", "trace_option", "max_tool_rounds",
        }
    )

    def __post_init__(self) -> None:
        # Normalizes and validates every field against the SDK's canonical sources of truth.
        self.type = self.type if isinstance(self.type, AgentType) else AgentType(self.type)
        self.name = self._validated_name(self.name)
        self.system_prompt = self._validated_system_prompt(self.system_prompt)
        self.provider = self._validated_provider(self.provider)
        self.model_name = self._validated_model(self.model_name, self.provider)
        self.temperature = self._validated_temperature(self.temperature, self.provider)
        self.runtime = self._runtime(self.runtime)
        self.loop = self._loop(self.loop)
        self.algorithm = self._validated_algorithm(self.algorithm)
        self.tools = self._definitions(self.tools, ToolDefinition, "agent.tools")
        self.middleware = self._definitions(self.middleware, MiddlewareDefinition, "agent.middleware")
        self.context_items = self._definitions(self.context_items, ContextItemDefinition, "agent.context_items")
        self.description = self._bounded_text(self._optional_text(self.description, "agent.description"), "agent.description", _MAX_DESCRIPTION_CHARS, reason="This text is sent to the model when the agent is used as a tool.")
        self.capabilities = self._validated_capabilities(self.capabilities)
        self.metadata = self._mapping(self.metadata, "agent.metadata")
        self._serializable(self.metadata, "agent.metadata")
        self.agent_metadata = self._validated_agent_metadata(self.agent_metadata)
        self.output_schema = self._validated_output_schema(self.output_schema)
        self.trace_option = self._validated_trace_option(self.trace_option)
        self.max_tool_rounds = self._positive_int(self.max_tool_rounds, "agent.max_tool_rounds")
        self._validate_runtime_compatibility()

    @classmethod
    def from_mapping(cls, data: object, field_name: str = "agent") -> "AgentSettings":
        # Validates an agent document body, dispatches on ``type``, and builds validated settings.
        payload = cls._mapping(data, field_name)
        target = cls._resolve_type(payload.get("type", AgentType.BASE.value), field_name)
        cls._only(payload, target._ALLOWED_FIELDS, field_name)
        for required in target._REQUIRED_FIELDS:
            if required not in payload:
                raise cls._error(f"'{field_name}' is missing required field '{required}'.", f"{field_name}.{required}")
        return target.from_payload(payload)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "AgentSettings":
        # @intent subclass-extensible-construction
        # Construction goes through one overridable hook so a settings subclass that adds a field
        # (a future ``multi`` agent's ``agents:``) extends it here instead of editing the dispatcher.
        return cls(
            type=cls._AGENT_TYPE,
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
            context_items=payload.get("context_items", ()),
            description=payload.get("description", ""),
            capabilities=payload.get("capabilities", ()),
            metadata=payload.get("metadata", {}),
            agent_metadata=payload.get("agent_metadata"),
            output_schema=payload.get("output_schema"),
            trace_option=payload.get("trace_option"),
            max_tool_rounds=payload.get("max_tool_rounds"),
        )

    def to_agent_kwargs(self, *, tools: Sequence[object] = (), middleware: Sequence[object] = (), context_items: Sequence[object] = ()) -> dict[str, Any]:
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
            "context_items": tuple(context_items),
            "description": self.description,
            "capabilities": self.capabilities,
            "metadata": dict(self.metadata),
            "agent_metadata": self.agent_metadata,
            "output_schema": dict(self.output_schema) if self.output_schema is not None else None,
            "trace_option": self.trace_option,
            "max_tool_rounds": self.max_tool_rounds,
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
            "context_items": [ContextItemDefinition.expected_structure()],
            "description": "",
            "capabilities": ["<capability>"],
            "metadata": {},
            "agent_metadata": {"name": "<tool-name>", "description": "<what this agent does>", "use_cases": "<when to call it>"},
            "output_schema": {"type": "object", "properties": {}},
            "trace_option": {"mode": "continual", "schema": {"name": "<schema-name>", "fields": {"<field-name>": {"description": "<what this field records>", "type": "string"}}}, "every_n_iterations": 5, "max_trace_iterations": 3},
            "max_tool_rounds": "<int|null>",
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
    def _validated_name(cls, value: object) -> str:
        # Constrains the name to the character set a provider accepts for a tool name.
        name = cls._bounded_text(cls._text(value, "agent.name"), "agent.name", _MAX_NAME_CHARS)
        if not _NAME_PATTERN.match(name):
            raise cls._error(f"'agent.name' must contain only letters, digits, hyphens, and underscores so the agent can be exposed as a tool; got {name!r}.", "agent.name", actual_value=name, pattern=_NAME_PATTERN.pattern)
        return name

    @classmethod
    def _validated_system_prompt(cls, value: object) -> str:
        # @intent bounded-prompt
        # The prompt may now come from a file, so an accidental multi-megabyte target must fail
        # here with a length, not as an opaque context-length rejection from the provider.
        prompt = cls._text(value, "agent.system_prompt")
        cls._bounded_text(prompt, "agent.system_prompt", _MAX_SYSTEM_PROMPT_CHARS, reason="A prompt this large will not fit most model context windows.")
        return cls._printable(prompt, "agent.system_prompt")

    @classmethod
    def _validated_provider(cls, value: object) -> str | None:
        # Validates the provider against the canonical ProviderModelRegistry, or leaves it unset.
        if value is None:
            return None
        provider = cls._text(value, "agent.provider").lower()
        try:
            ProviderModelRegistry.validate_provider(provider)
        except ConfigurationError as error:
            raise cls._error(str(error), "agent.provider", actual_value=provider) from error
        return provider

    @classmethod
    def _validated_model(cls, value: object, provider: str | None) -> str | None:
        # Validates the model against the catalog, its declared provider, and its execution modality.
        if value is None:
            return None
        model = cls._bounded_text(cls._text(value, "agent.model_name"), "agent.model_name", _MAX_MODEL_NAME_CHARS)
        try:
            if provider is None:
                ProviderModelRegistry.validate_model(model)
            else:
                ProviderModelRegistry.validate_provider_model_pair(provider, model)
        except ConfigurationError as error:
            raise cls._error(str(error), "agent.model_name", actual_value=model, declared_provider=provider) from error
        return cls._text_modality(model)

    @classmethod
    def _text_modality(cls, model: str) -> str:
        # @intent modality-agent-fit
        # A system prompt, tools, and an agentic loop only compose with a text model; an image,
        # video, or audio model is a category error that otherwise fails deep inside runner selection.
        modality = ModalityDetector.detect_modality(model)
        if modality in (ModelModality.TEXT, ModelModality.AUTO):
            return model
        raise cls._error(f"'agent.model_name' {model!r} has {modality.value} modality and cannot drive a conversational agent; agents require a text model.", "agent.model_name", actual_value=model, modality=modality.value)

    @classmethod
    def _validated_temperature(cls, value: object, provider: str | None) -> float | None:
        # Bounds sampling temperature to the SDK window, tightened to the provider's own ceiling.
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise cls._error("'agent.temperature' must be a number.", "agent.temperature", actual_type=type(value).__name__)
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            raise cls._error(f"'agent.temperature' must be a finite number; got {value}.", "agent.temperature", actual_value=str(value))
        ceiling = _PROVIDER_TEMPERATURE_CEILING.get(provider or "", _MAX_TEMPERATURE)
        if not _MIN_TEMPERATURE <= number <= ceiling:
            scope = f" for provider {provider!r}" if ceiling != _MAX_TEMPERATURE else ""
            raise cls._error(f"'agent.temperature' must be between {_MIN_TEMPERATURE} and {ceiling}{scope}; got {number}.", "agent.temperature", actual_value=number, minimum=_MIN_TEMPERATURE, maximum=ceiling)
        return number

    @classmethod
    def _validated_capabilities(cls, value: object) -> tuple[str, ...]:
        # Applies the unique-reference contract plus per-entry and total-count ceilings.
        capabilities = cls._bounded_count(cls._refs(value, "agent.capabilities"), "agent.capabilities", _MAX_CAPABILITIES)
        for index, capability in enumerate(capabilities):
            cls._bounded_text(capability, f"agent.capabilities[{index}]", _MAX_CAPABILITY_CHARS)
        return capabilities

    @classmethod
    def _validated_algorithm(cls, value: object) -> str | None:
        # Resolves the algorithm against the registered presets, rejecting a blank placeholder.
        if value is None:
            return None
        name = cls._text(value, "agent.algorithm")
        from vidbyte.context.window import ContextWindow

        try:
            ContextWindow.resolve_algorithm(name)
        except Exception as error:
            raise cls._error(f"'agent.algorithm' must be a registered context-window preset; got {name!r}.", "agent.algorithm", actual_value=name) from error
        return name

    @classmethod
    def _validated_agent_metadata(cls, value: object) -> AgentMetadata | None:
        # Builds the agent-as-tool metadata from a document mapping, bounding its model-visible text.
        if value is None or isinstance(value, AgentMetadata):
            return value
        payload = cls._mapping(value, "agent.agent_metadata")
        cls._only(payload, frozenset({"name", "description", "use_cases"}), "agent.agent_metadata")
        fields = {key: cls._bounded_text(cls._optional_text(payload.get(key, ""), f"agent.agent_metadata.{key}"), f"agent.agent_metadata.{key}", _MAX_DESCRIPTION_CHARS) for key in ("name", "description", "use_cases")}
        if fields["name"] and not _NAME_PATTERN.match(fields["name"]):
            raise cls._error(f"'agent.agent_metadata.name' must contain only letters, digits, hyphens, and underscores because it becomes the tool name; got {fields['name']!r}.", "agent.agent_metadata.name", actual_value=fields["name"])
        return AgentMetadata(**fields)

    @classmethod
    def _validated_output_schema(cls, value: object) -> dict[str, Any] | None:
        # Accepts only the JSON-Schema mapping form; a Python type is not expressible in a document.
        if value is None:
            return None
        schema = cls._mapping(value, "agent.output_schema")
        cls._serializable(schema, "agent.output_schema")
        if "type" not in schema and "properties" not in schema:
            raise cls._error("'agent.output_schema' must be a JSON Schema object declaring at least 'type' or 'properties'.", "agent.output_schema", keys=sorted(schema))
        return schema

    @classmethod
    def _validated_trace_option(cls, value: object) -> Any | None:
        # Builds a TraceOption from a document mapping, delegating field rules to the trace dataclass.
        from vidbyte.lib.dataclasses.trace import TraceOption

        if value is None or isinstance(value, TraceOption):
            return value
        payload = cls._mapping(value, "agent.trace_option")
        cls._only(payload, frozenset({"mode", "schema", "every_n_iterations", "max_trace_iterations"}), "agent.trace_option")
        if "schema" not in payload:
            raise cls._error("'agent.trace_option' is missing required field 'schema'.", "agent.trace_option.schema")
        payload["schema"] = cls._trace_schema(payload["schema"])
        try:
            return TraceOption(**payload)
        except (TypeError, ValueError, ConfigurationError) as error:
            raise cls._error(f"'agent.trace_option' is invalid: {error}", "agent.trace_option") from error

    @classmethod
    def _trace_schema(cls, value: object) -> Any:
        # @intent explicit-trace-schema-shape
        # TraceSchema.coerce reads any bare mapping as a *fields* map, so a document that names its
        # schema is built explicitly here; otherwise "name" and "fields" silently become trace fields.
        from vidbyte.lib.dataclasses.trace import TraceSchema

        if isinstance(value, TraceSchema):
            return value
        payload = cls._mapping(value, "agent.trace_option.schema")
        cls._only(payload, frozenset({"name", "fields", "description"}), "agent.trace_option.schema")
        for key in ("name", "fields"):
            if key not in payload:
                raise cls._error(f"'agent.trace_option.schema' is missing required field '{key}'.", f"agent.trace_option.schema.{key}")
        fields = cls._mapping(payload["fields"], "agent.trace_option.schema.fields")
        for name, spec in fields.items():
            entry = cls._mapping(spec, f"agent.trace_option.schema.fields.{name}")
            if not entry.get("description"):
                raise cls._error(f"'agent.trace_option.schema.fields.{name}' must declare a non-blank 'description'.", f"agent.trace_option.schema.fields.{name}.description")
        try:
            return TraceSchema(name=cls._text(payload["name"], "agent.trace_option.schema.name"), fields=fields, description=cls._optional_text(payload.get("description", ""), "agent.trace_option.schema.description"))
        except (TypeError, ValueError) as error:
            raise cls._error(f"'agent.trace_option.schema' is invalid: {error}", "agent.trace_option.schema") from error

    def _validate_runtime_compatibility(self) -> None:
        # @intent early-runtime-conflict
        # BaseAgent rejects these combinations at construction; repeating the check here lets the
        # error name the document and field the author must change instead of an agent internal.
        if self.runtime not in _NON_LINEAR_RUNTIMES:
            return
        runtime = self.runtime.value
        if self.middleware:
            raise self._error(f"'agent.middleware' is not supported by runtime {runtime!r}; remove it or use runtime 'linear'.", "agent.middleware", runtime=runtime)
        if self.algorithm is not None and self.algorithm != "default":
            raise self._error(f"'agent.algorithm' is not supported by runtime {runtime!r}; remove it or use runtime 'linear'.", "agent.algorithm", runtime=runtime, actual_value=self.algorithm)
        if self.trace_option is not None and getattr(self.trace_option, "enabled", False):
            raise self._error(f"'agent.trace_option' is not supported by runtime {runtime!r}; remove it or use runtime 'linear'.", "agent.trace_option", runtime=runtime)

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
        cls._only(mapping, _LOOP_FIELDS, "agent.loop")
        if "allowed_tools" in mapping:
            allowed = mapping["allowed_tools"]
            if isinstance(allowed, str) or not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
                raise cls._error("'agent.loop.allowed_tools' must be a list of strings.", "agent.loop.allowed_tools", actual_type=type(allowed).__name__)
            mapping["allowed_tools"] = tuple(allowed)
        cls._coerce_loop_members(mapping)
        try:
            return AgentLoopSettings(**mapping)
        except (TypeError, ValueError, ConfigurationError) as error:
            raise cls._error(f"'agent.loop' is invalid: {error}", "agent.loop") from error

    @classmethod
    def _coerce_loop_members(cls, mapping: dict[str, Any]) -> None:
        # @intent reachable-nested-loop-settings
        # AgentLoopSettings requires real nested objects, so a YAML mapping for these fields would
        # otherwise be rejected outright and leave three documented loop settings unusable from a file.
        from vidbyte.agents.contracts import OutputContract
        from vidbyte.agents.settings import ToolErrorPolicy, ToolSettings

        for key, builder in (("tool_error_policy", ToolErrorPolicy), ("tool_settings", ToolSettings)):
            if isinstance(mapping.get(key), Mapping):
                payload = cls._mapping(mapping[key], f"agent.loop.{key}")
                try:
                    mapping[key] = builder(**payload)
                except (TypeError, ValueError, ConfigurationError) as error:
                    raise cls._error(f"'agent.loop.{key}' is invalid: {error}", f"agent.loop.{key}") from error
        contracts = mapping.get("output_contracts")
        if isinstance(contracts, list):
            mapping["output_contracts"] = tuple(cls._coerce_contract(OutputContract, item, index) for index, item in enumerate(contracts))

    @classmethod
    def _coerce_contract(cls, builder: type, item: object, index: int) -> Any:
        # Builds one output contract from a document mapping, naming its position on failure.
        if not isinstance(item, Mapping):
            return item
        payload = cls._mapping(item, f"agent.loop.output_contracts[{index}]")
        try:
            return builder(**payload)
        except (TypeError, ValueError, ConfigurationError) as error:
            raise cls._error(f"'agent.loop.output_contracts[{index}]' is invalid: {error}", f"agent.loop.output_contracts[{index}]") from error

    @classmethod
    def _definitions(cls, value: object, definition: type[_RefOptionsDefinition], field_name: str) -> tuple[Any, ...]:
        # Builds nested tool/middleware/context definitions and rejects duplicate references.
        if isinstance(value, (str, Mapping)) or not isinstance(value, Sequence):
            raise cls._error(f"'{field_name}' must be a list of {{ref, options}} entries.", field_name, actual_type=type(value).__name__)
        items = cls._bounded_count(tuple(value), field_name, _MAX_DEFINITIONS)
        built = tuple(item if isinstance(item, definition) else definition.from_mapping(item, f"{field_name}[{index}]") for index, item in enumerate(items))
        refs = [item.ref for item in built]
        duplicates = sorted({ref for ref in refs if refs.count(ref) > 1})
        if duplicates:
            raise cls._error(f"'{field_name}' must not contain duplicate references: {', '.join(duplicates)}.", field_name, duplicates=duplicates)
        return built


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
    "ContextItemDefinition",
    "ContinualTraceAgentSettings",
    "HandoffAgentSettings",
    "MiddlewareDefinition",
    "MultiAgentSettings",
    "ToolDefinition",
]

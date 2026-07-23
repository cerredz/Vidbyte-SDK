"""Context Protocol Header

Description:
    Defines the typed, declarative configuration dataclasses produced by the public
    YAML loader: AgentSettings, ToolDefinition, and MiddlewareDefinition.
Purpose:
    Keeps every configuration data contract in the central vidbyte.lib.dataclasses
    namespace and makes each dataclass the single place that validates its own shape,
    so the loader parses YAML and delegates all field validation here instead of
    performing ad-hoc string and isinstance checks.
Architecture:
    - ToolDefinition / MiddlewareDefinition: A named ref with data-only options.
    - AgentSettings: Validated agent construction inputs and declarative references.
    - Each type exposes ``from_mapping`` (validate + build from a parsed document) and
      ``expected_structure`` (the document shape the loader surfaces to developers).
Relations:
    Constructed by vidbyte.config.loader; re-exported through vidbyte.config.types.
    AgentSettings mirrors the construction fields of vidbyte.lib.dataclasses.agents
    AgentSpec but adds the provider/model/runtime/loop and declarative-reference inputs
    a YAML agent document needs; the two stay separate because AgentSpec is a frozen
    in-process construction record while AgentSettings is a mutable parse result.
Non-Goals:
    Does not import references, instantiate tools or middleware, or resolve secrets.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vidbyte.lib.enums import AgentLoopField, AgentRuntimeType
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.settings import AgentLoopSettings

_SECRET_KEYS = frozenset({"api_key", "token", "password", "secret"})
_SECRET_SUFFIXES = ("_api_key", "_token", "_password", "_secret")


def _default_loop() -> "AgentLoopSettings":
    # Builds an empty loop-settings object, importing lazily to avoid an agents<->lib cycle.
    from vidbyte.agents.settings import AgentLoopSettings

    return AgentLoopSettings()


def _config_error(message: str, field_name: str, **extra: Any) -> ConfigurationError:
    # Builds the shared configuration error with the exact offending field and safe context.
    details: dict[str, Any] = {"field": field_name}
    details.update(extra)
    return ConfigurationError(message, details=details)


def _is_secret_key(key: str) -> bool:
    # Identifies common credential field names without treating budget-oriented names as secrets.
    normalized = key.strip().lower()
    return normalized in _SECRET_KEYS or normalized.endswith(_SECRET_SUFFIXES)


def _required_text(value: object, field_name: str) -> str:
    # Returns a non-blank, stripped string or names the field and the type actually received.
    if not isinstance(value, str) or not value.strip():
        raise _config_error(
            f"'{field_name}' must be a non-blank string.",
            field_name,
            actual_type=type(value).__name__,
        )
    return value.strip()


def _mapping_copy(value: object, field_name: str) -> dict[str, Any]:
    # Returns a string-keyed shallow copy or reports why the field is not a valid mapping.
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _config_error(
            f"'{field_name}' must be a mapping with string keys.",
            field_name,
            actual_type=type(value).__name__,
        )
    return dict(value)


def _validate_serializable(value: object, field_name: str, ancestry: frozenset[int] = frozenset()) -> None:
    # Recursively accepts only data values that can be represented without Python object construction.
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        if "${" in value:
            raise _config_error("Configuration does not support environment interpolation.", field_name)
        return
    if isinstance(value, list):
        if id(value) in ancestry:
            raise _config_error("Configuration must not contain cyclic aliases.", field_name)
        for index, item in enumerate(value):
            _validate_serializable(item, f"{field_name}[{index}]", ancestry | {id(value)})
        return
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        if id(value) in ancestry:
            raise _config_error("Configuration must not contain cyclic aliases.", field_name)
        for key, item in value.items():
            if _is_secret_key(key):
                raise _config_error("Configuration must not contain YAML-held secrets.", f"{field_name}.{key}")
            _validate_serializable(item, f"{field_name}.{key}", ancestry | {id(value)})
        return
    raise _config_error(
        "Configuration values must be YAML scalars, lists, or string-keyed mappings.",
        field_name,
        actual_type=type(value).__name__,
    )


def _validate_references(value: object, field_name: str) -> tuple[str, ...]:
    # Normalizes unique non-blank references while rejecting a scalar string as a sequence.
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise _config_error(
            f"'{field_name}' must be a list of non-blank strings.",
            field_name,
            actual_type=type(value).__name__,
        )
    references = tuple(_required_text(item, f"{field_name}[{index}]") for index, item in enumerate(value))
    duplicates = sorted({ref for ref in references if references.count(ref) > 1})
    if duplicates:
        raise _config_error(f"'{field_name}' must not contain duplicate references.", field_name, duplicates=duplicates)
    return references


def _only_fields(payload: Mapping[str, Any], allowed: frozenset[str], field_name: str) -> None:
    # Rejects schema drift instead of silently ignoring unsupported configuration keys.
    unknown = sorted(set(payload).difference(allowed))
    if unknown:
        raise _config_error(
            f"'{field_name}' contains unsupported field(s): {', '.join(unknown)}.",
            f"{field_name}.{unknown[0]}",
            unknown=unknown,
            allowed=sorted(allowed),
        )


@dataclass(slots=True)
class ToolDefinition:
    """A declarative tool reference and its serializable configuration options."""

    ref: str
    options: dict[str, Any] = field(default_factory=dict)

    _ALLOWED_FIELDS = frozenset({"ref", "options"})

    def __post_init__(self) -> None:
        # Validates the reference and copies options so callers retain no mutable alias.
        self.ref = _required_text(self.ref, "ToolDefinition.ref")
        self.options = _mapping_copy(self.options, "ToolDefinition.options")
        _validate_serializable(self.options, "ToolDefinition.options")

    @classmethod
    def from_mapping(cls, data: object, field_name: str) -> "ToolDefinition":
        # Validates a single ``{ref, options}`` declaration and builds the dataclass.
        item = _mapping_copy(data, field_name)
        _only_fields(item, cls._ALLOWED_FIELDS, field_name)
        return cls(ref=item.get("ref"), options=item.get("options", {}))

    @staticmethod
    def expected_structure() -> dict[str, Any]:
        # Returns the document shape a developer should follow for one tool entry.
        return {"ref": "<tool-reference>", "options": {}}


@dataclass(slots=True)
class MiddlewareDefinition:
    """A declarative middleware reference and its serializable configuration options."""

    ref: str
    options: dict[str, Any] = field(default_factory=dict)

    _ALLOWED_FIELDS = frozenset({"ref", "options"})

    def __post_init__(self) -> None:
        # Validates the reference and copies options so callers retain no mutable alias.
        self.ref = _required_text(self.ref, "MiddlewareDefinition.ref")
        self.options = _mapping_copy(self.options, "MiddlewareDefinition.options")
        _validate_serializable(self.options, "MiddlewareDefinition.options")

    @classmethod
    def from_mapping(cls, data: object, field_name: str) -> "MiddlewareDefinition":
        # Validates a single ``{ref, options}`` declaration and builds the dataclass.
        item = _mapping_copy(data, field_name)
        _only_fields(item, cls._ALLOWED_FIELDS, field_name)
        return cls(ref=item.get("ref"), options=item.get("options", {}))

    @staticmethod
    def expected_structure() -> dict[str, Any]:
        # Returns the document shape a developer should follow for one middleware entry.
        return {"ref": "<middleware-reference>", "options": {}}


@dataclass(slots=True)
class AgentSettings:
    """Validated declarative inputs for constructing one BaseAgent instance."""

    name: str
    system_prompt: str
    provider: str
    model_name: str
    runtime: AgentRuntimeType | str = AgentRuntimeType.LINEAR
    loop: "AgentLoopSettings | Mapping[str, Any]" = field(default_factory=_default_loop)
    tool_refs: tuple[str, ...] = ()
    middleware_refs: tuple[str, ...] = ()
    description: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    _REQUIRED_FIELDS = ("name", "system_prompt", "provider", "model_name")
    _ALLOWED_FIELDS = frozenset(
        {
            "name",
            "system_prompt",
            "provider",
            "model_name",
            "runtime",
            "loop",
            "tools",
            "middleware",
            "description",
            "capabilities",
            "metadata",
        }
    )

    def __post_init__(self) -> None:
        # Normalizes intrinsic fields before any agent, tool, or middleware is constructed.
        self.name = _required_text(self.name, "AgentSettings.name")
        self.system_prompt = _required_text(self.system_prompt, "AgentSettings.system_prompt")
        self.provider = _required_text(self.provider, "AgentSettings.provider")
        self.model_name = _required_text(self.model_name, "AgentSettings.model_name")
        self.runtime = self._runtime_value(self.runtime)
        self.loop = self._loop_settings(self.loop)
        self.tool_refs = _validate_references(self.tool_refs, "AgentSettings.tool_refs")
        self.middleware_refs = _validate_references(self.middleware_refs, "AgentSettings.middleware_refs")
        self.description = self._optional_text(self.description, "AgentSettings.description")
        self.capabilities = _validate_references(self.capabilities, "AgentSettings.capabilities")
        self.metadata = _mapping_copy(self.metadata, "AgentSettings.metadata")
        _validate_serializable(self.metadata, "AgentSettings.metadata")

    @classmethod
    def from_mapping(cls, data: object, field_name: str = "agent") -> "AgentSettings":
        # Validates an ``agent`` document body and builds fully validated settings.
        payload = _mapping_copy(data, field_name)
        _only_fields(payload, cls._ALLOWED_FIELDS, field_name)
        for required in cls._REQUIRED_FIELDS:
            if required not in payload:
                raise _config_error(f"'{field_name}' is missing required field '{required}'.", f"{field_name}.{required}")
        return cls(
            name=payload.get("name"),
            system_prompt=payload.get("system_prompt"),
            provider=payload.get("provider"),
            model_name=payload.get("model_name"),
            runtime=payload.get("runtime", AgentRuntimeType.LINEAR),
            loop=payload.get("loop", {}),
            tool_refs=payload.get("tools", ()),
            middleware_refs=payload.get("middleware", ()),
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
            "runtime": self.runtime,
            "agent_loop_settings": self.loop,
            "tools": tuple(tools),
            "middleware": tuple(middleware),
            "description": self.description,
            "capabilities": self.capabilities,
            "metadata": dict(self.metadata),
        }

    @staticmethod
    def expected_structure() -> dict[str, Any]:
        # Returns the document shape a developer should follow for an agent document.
        return {
            "version": 1,
            "kind": "agent",
            "agent": {
                "name": "<agent-name>",
                "system_prompt": "<system-prompt>",
                "provider": "<provider>",
                "model_name": "<model-name>",
                "runtime": AgentRuntimeType.LINEAR.value,
                "loop": {field_name.value: "<int|float|list>" for field_name in AgentLoopField},
                "tools": ["<tool-reference>"],
                "middleware": ["<middleware-reference>"],
                "description": "",
                "capabilities": ["<capability>"],
                "metadata": {},
            },
        }

    @staticmethod
    def _runtime_value(value: AgentRuntimeType | str) -> AgentRuntimeType:
        # Converts a public runtime string to the canonical runtime enum.
        try:
            return AgentRuntimeType(value)
        except (TypeError, ValueError) as error:
            supported = sorted(member.value for member in AgentRuntimeType)
            raise _config_error(
                f"'agent.runtime' is not a supported runtime; expected one of {supported}.",
                "agent.runtime",
                actual_value=value,
            ) from error

    @staticmethod
    def _loop_settings(value: object) -> "AgentLoopSettings":
        # Accepts an existing loop object or validates and builds one from a document mapping.
        from vidbyte.agents.settings import AgentLoopSettings

        if isinstance(value, AgentLoopSettings):
            return value
        loop = _mapping_copy(value, "agent.loop")
        _only_fields(loop, AgentLoopField.names(), "agent.loop")
        if "allowed_tools" in loop:
            allowed_tools = loop["allowed_tools"]
            if isinstance(allowed_tools, str) or not isinstance(allowed_tools, list) or not all(isinstance(item, str) for item in allowed_tools):
                raise _config_error(
                    "'agent.loop.allowed_tools' must be a list of strings.",
                    "agent.loop.allowed_tools",
                    actual_type=type(allowed_tools).__name__,
                )
            loop["allowed_tools"] = tuple(allowed_tools)
        try:
            return AgentLoopSettings(**loop)
        except (TypeError, ValueError, ConfigurationError) as error:
            raise _config_error(f"'agent.loop' is invalid: {error}", "agent.loop") from error

    @staticmethod
    def _optional_text(value: object, field_name: str) -> str:
        # Accepts an empty description but otherwise applies the public string contract.
        if not isinstance(value, str):
            raise _config_error(f"'{field_name}' must be a string.", field_name, actual_type=type(value).__name__)
        return value.strip()


__all__ = ["AgentSettings", "MiddlewareDefinition", "ToolDefinition"]

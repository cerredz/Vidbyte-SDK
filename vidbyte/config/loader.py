"""Context Protocol Header

Description:
    Provides the public class-first YAML configuration loader.
Purpose:
    Safely parses versioned YAML documents into validated declarative settings.
Architecture:
    - ConfigurationLoader: Stateless public interface for agent, tool, and middleware documents.
    - _DuplicateKeySafeLoader: SafeLoader variant that rejects ambiguous mappings.
Relations:
    Uses vidbyte.config.types and the existing ConfigurationError contract.
Non-Goals:
    Never resolves refs, imports code, interpolates secrets, or creates runtime objects.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from yaml.nodes import MappingNode

from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.config.types import AgentSettings, MiddlewareDefinition, ToolDefinition
from vidbyte.lib.errors import ConfigurationError

_SUPPORTED_SUFFIXES = frozenset({".yaml", ".yml"})
_LOOP_FIELDS = frozenset(
    {
        "max_iterations",
        "max_tokens",
        "max_tool_calls",
        "max_queued_prompts",
        "max_parallel_tool_calls",
        "max_retries",
        "timeout_seconds",
        "context_window_budget",
        "compaction_trigger_tokens",
        "compaction_target_tokens",
        "allowed_tools",
        "max_contract_rejections",
    }
)


class _DuplicateKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate keys instead of silently overwriting them."""

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Any, Any]:
        # @intent configuration-ambiguity-guard
        # Rejecting duplicates prevents an untrusted file from hiding an earlier value behind YAML's last-key-wins behavior.
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in mapping
            except TypeError as error:
                raise yaml.constructor.ConstructorError("while constructing a mapping", node.start_mark, "found an unhashable mapping key", key_node.start_mark) from error
            if duplicate:
                raise yaml.constructor.ConstructorError("while constructing a mapping", node.start_mark, f"found duplicate key {key!r}", key_node.start_mark)
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


class ConfigurationLoader:
    """Stateless loader for versioned agent, tool, and middleware YAML documents."""

    def load_agent_settings(self, path: str | Path) -> AgentSettings:
        # Loads one agent document into intrinsic settings without resolving referenced components.
        try:
            document_path, document = self._document(path, "agent")
            payload = self._mapping(document.get("agent"), document_path, "agent")
            self._only_fields(payload, {"name", "system_prompt", "provider", "model_name", "runtime", "loop", "tools", "middleware", "description", "capabilities", "metadata"}, document_path, "agent")
            values = self._required_agent_fields(payload, document_path)
            loop = self._loop_settings(payload.get("loop", {}), document_path)
            return self._agent_settings(values, payload, loop, document_path)
        except ConfigurationError as error:
            error.details.setdefault("expected_kind", "agent")
            raise

    def load_tools(self, path: str | Path) -> tuple[ToolDefinition, ...]:
        # Loads a tool-definition document without resolving any tool reference into executable code.
        try:
            document_path, document = self._document(path, "tools")
            definitions = self._definition_list(document.get("tools"), "tools", document_path)
            return tuple(ToolDefinition(**definition) for definition in definitions)
        except ConfigurationError as error:
            error.details.setdefault("expected_kind", "tools")
            raise

    def load_middleware_settings(self, path: str | Path) -> tuple[MiddlewareDefinition, ...]:
        # Loads middleware declarations without constructing middleware or importing their references.
        try:
            document_path, document = self._document(path, "middleware")
            definitions = self._definition_list(document.get("middleware"), "middleware", document_path)
            return tuple(MiddlewareDefinition(**definition) for definition in definitions)
        except ConfigurationError as error:
            error.details.setdefault("expected_kind", "middleware")
            raise

    def _document(self, path: str | Path, expected_kind: str) -> tuple[Path, dict[str, Any]]:
        # Reads one YAML file and validates its shared versioned document envelope.
        document_path = self._path(path)
        try:
            loaded = yaml.load(document_path.read_text(encoding="utf-8"), Loader=_DuplicateKeySafeLoader)
        except (OSError, UnicodeError, yaml.YAMLError) as error:
            self._error("Unable to read a valid YAML configuration document.", document_path, "document", error)
        payload = self._mapping(loaded, document_path, "document")
        self._only_fields(payload, {"version", "kind", expected_kind}, document_path, "document")
        self._version(payload.get("version"), document_path)
        self._kind(payload.get("kind"), expected_kind, document_path)
        return document_path, payload

    def _path(self, value: str | Path) -> Path:
        # Validates the public path type and extension before attempting file access.
        if not isinstance(value, (str, Path)):
            raise ConfigurationError("Configuration path must be a string or pathlib.Path.", details={"field": "path"})
        path = Path(value)
        if path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            raise ConfigurationError("Configuration files must use a .yaml or .yml extension.", details={"path": str(path), "field": "path"})
        return path

    def _required_agent_fields(self, payload: Mapping[str, Any], path: Path) -> dict[str, str]:
        # Extracts the required agent identity and provider/model fields from a document payload.
        required = ("name", "system_prompt", "provider", "model_name")
        values: dict[str, str] = {}
        for field_name in required:
            value = payload.get(field_name)
            if not isinstance(value, str) or not value.strip():
                self._error("Agent configuration requires a non-blank string.", path, f"agent.{field_name}")
            values[field_name] = value
        return values

    def _loop_settings(self, value: object, path: Path) -> AgentLoopSettings:
        # Converts the YAML-compatible loop subset to the SDK's existing validated settings object.
        loop = self._mapping(value, path, "agent.loop")
        self._only_fields(loop, _LOOP_FIELDS, path, "agent.loop")
        if "allowed_tools" in loop:
            allowed_tools = loop["allowed_tools"]
            if isinstance(allowed_tools, str) or not isinstance(allowed_tools, list) or not all(isinstance(item, str) for item in allowed_tools):
                self._error("agent.loop.allowed_tools must be a list of strings.", path, "agent.loop.allowed_tools")
            loop["allowed_tools"] = tuple(allowed_tools)
        try:
            return AgentLoopSettings(**loop)
        except (TypeError, ValueError, ConfigurationError) as error:
            self._error("Agent loop settings are invalid.", path, "agent.loop", error)

    def _agent_settings(self, values: Mapping[str, str], payload: Mapping[str, Any], loop: AgentLoopSettings, path: Path) -> AgentSettings:
        # Builds AgentSettings after all YAML-specific shape validation is complete.
        try:
            return AgentSettings(
                **values,
                runtime=payload.get("runtime", "linear"),
                loop=loop,
                tool_refs=self._references(payload.get("tools", []), path, "agent.tools"),
                middleware_refs=self._references(payload.get("middleware", []), path, "agent.middleware"),
                description=payload.get("description", ""),
                capabilities=self._references(payload.get("capabilities", []), path, "agent.capabilities"),
                metadata=self._mapping(payload.get("metadata", {}), path, "agent.metadata"),
            )
        except ConfigurationError as error:
            self._error("Agent settings are invalid.", path, "agent", error)

    def _definition_list(self, value: object, kind: str, path: Path) -> list[dict[str, Any]]:
        # Validates a declaration list with one ref and optional data-only options per item.
        if not isinstance(value, list):
            self._error(f"{kind} configuration must be a list.", path, kind)
        result: list[dict[str, Any]] = []
        for index, definition in enumerate(value):
            field = f"{kind}[{index}]"
            item = self._mapping(definition, path, field)
            self._only_fields(item, {"ref", "options"}, path, field)
            if not isinstance(item.get("ref"), str) or not item["ref"].strip():
                self._error(f"{field}.ref must be a non-blank string.", path, f"{field}.ref")
            options = self._mapping(item.get("options", {}), path, f"{field}.options")
            self._serializable(options, path, f"{field}.options")
            result.append({"ref": item["ref"], "options": options})
        references = [definition["ref"].strip() for definition in result]
        if len(set(references)) != len(references):
            self._error(f"{kind} configuration must not contain duplicate references.", path, kind)
        return result

    def _references(self, value: object, path: Path, field: str) -> tuple[str, ...]:
        # Validates an ordered list of unique declarative reference names.
        if isinstance(value, str) or not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
            self._error(f"{field} must be a list of non-blank strings.", path, field)
        references = tuple(value)
        if len(set(references)) != len(references):
            self._error(f"{field} must not contain duplicate references.", path, field)
        return references

    def _mapping(self, value: object, path: Path, field: str) -> dict[str, Any]:
        # Returns a string-keyed mapping or reports the exact document field that violated the shape contract.
        if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
            self._error(f"{field} must be a mapping with string keys.", path, field)
        return dict(value)

    def _only_fields(self, payload: Mapping[str, Any], allowed: set[str] | frozenset[str], path: Path, field: str) -> None:
        # Rejects schema drift instead of silently ignoring unsupported configuration keys.
        unknown = sorted(set(payload).difference(allowed))
        if unknown:
            self._error("Configuration contains an unsupported field.", path, f"{field}.{unknown[0]}")

    def _version(self, value: object, path: Path) -> None:
        # Requires the first documented schema version and excludes bool despite bool being an int subclass.
        if isinstance(value, bool) or not isinstance(value, int) or value != 1:
            self._error("Configuration version must be the supported integer value 1.", path, "version")

    def _kind(self, value: object, expected_kind: str, path: Path) -> None:
        # Requires each loader method to receive its matching document kind.
        if value != expected_kind:
            self._error(f"Configuration kind must be {expected_kind!r}.", path, "kind")

    def _serializable(self, value: object, path: Path, field: str, ancestry: frozenset[int] = frozenset()) -> None:
        # Recursively accepts only data values that can be represented without Python object construction.
        if value is None or isinstance(value, (bool, int, float)):
            return
        if isinstance(value, str):
            if "${" in value:
                self._error("Configuration does not support environment interpolation.", path, field)
            return
        if isinstance(value, list):
            if id(value) in ancestry:
                self._error("Configuration must not contain cyclic aliases.", path, field)
            for index, item in enumerate(value):
                self._serializable(item, path, f"{field}[{index}]", ancestry | {id(value)})
            return
        if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
            if id(value) in ancestry:
                self._error("Configuration must not contain cyclic aliases.", path, field)
            for key, item in value.items():
                if ToolDefinition._secret_key(key):
                    self._error("Configuration must not contain YAML-held secrets.", path, f"{field}.{key}")
                self._serializable(item, path, f"{field}.{key}", ancestry | {id(value)})
            return
        self._error("Configuration values must be YAML scalars, lists, or string-keyed mappings.", path, field)

    @staticmethod
    def _error(message: str, path: Path, field: str, cause: Exception | None = None) -> None:
        # Raises the shared error with actionable safe context and preserves a source exception when present.
        error = ConfigurationError(message, details={"path": str(path), "field": field})
        if cause is not None:
            raise error from cause
        raise error

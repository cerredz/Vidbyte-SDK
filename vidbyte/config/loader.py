"""Context Protocol Header

Description:
    Provides the public class-first YAML configuration loader.
Purpose:
    Safely parses versioned YAML documents into validated declarative settings and offers
    one central entry point that loads either an agent document or a harness document.
Architecture:
    - YamlLoader: Stateless public interface with a central load() plus typed loaders.
    - load()/load_agent()/load_harness()/load_tools()/load_middleware(): parse a document.
    - view_*(): return the expected document structure without touching the filesystem.
    - _DuplicateKeySafeLoader: SafeLoader variant that rejects ambiguous mappings.
Relations:
    Builds the dataclasses in vidbyte.lib.dataclasses.config, uses vidbyte.lib.enums for
    document kinds and loop fields, and delegates harness documents to HarnessConfigLoader.
Non-Goals:
    Never resolves refs, imports code, interpolates secrets, or creates runtime objects.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from yaml.nodes import MappingNode

from vidbyte.harnesses.config import HarnessConfigLoader
from vidbyte.harnesses.contracts import HARNESS_SCHEMA_VERSION, HarnessSpec
from vidbyte.lib.dataclasses.config import AgentSettings, MiddlewareDefinition, ToolDefinition
from vidbyte.lib.enums import ConfigKind
from vidbyte.lib.errors import ConfigurationError

_SUPPORTED_SUFFIXES = frozenset({".yaml", ".yml"})
_SUPPORTED_VERSION = 1


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


class YamlLoader:
    """Stateless loader for versioned agent, harness, tool, and middleware YAML documents."""

    def load(self, path: str | Path) -> AgentSettings | HarnessSpec | tuple[ToolDefinition, ...] | tuple[MiddlewareDefinition, ...]:
        # Central entry point: reads one document and dispatches on its declared kind.
        document_path = self._path(path)
        document = self._read(document_path)
        kind = self._detect_kind(document, document_path)
        if kind is ConfigKind.HARNESS:
            return self.load_harness(document_path)
        if kind is ConfigKind.AGENT:
            return self._load_agent_document(document_path, document)
        if kind is ConfigKind.TOOLS:
            return self._load_definitions(document_path, document, ConfigKind.TOOLS, ToolDefinition)
        return self._load_definitions(document_path, document, ConfigKind.MIDDLEWARE, MiddlewareDefinition)

    def load_agent(self, path: str | Path) -> AgentSettings:
        # Loads one agent document into intrinsic settings without resolving referenced components.
        document_path = self._path(path)
        return self._load_agent_document(document_path, self._read(document_path))

    def load_harness(self, path: str | Path) -> HarnessSpec:
        # Loads one harness document into a validated, content-addressed HarnessSpec.
        document_path = self._path(path)
        try:
            return HarnessConfigLoader().load(document_path)
        except ConfigurationError as error:
            error.details.setdefault("path", str(document_path))
            error.details.setdefault("expected_kind", ConfigKind.HARNESS.value)
            raise

    def load_tools(self, path: str | Path) -> tuple[ToolDefinition, ...]:
        # Loads a tool-definition document without resolving any tool reference into executable code.
        document_path = self._path(path)
        return self._load_definitions(document_path, self._read(document_path), ConfigKind.TOOLS, ToolDefinition)

    def load_middleware(self, path: str | Path) -> tuple[MiddlewareDefinition, ...]:
        # Loads middleware declarations without constructing middleware or importing their references.
        document_path = self._path(path)
        return self._load_definitions(document_path, self._read(document_path), ConfigKind.MIDDLEWARE, MiddlewareDefinition)

    def view_agent(self) -> dict[str, Any]:
        # Returns the document structure an agent .yaml file must follow.
        return AgentSettings.expected_structure()

    def view_harness(self) -> dict[str, Any]:
        # Returns the document structure a harness .yaml file must follow.
        return {
            "schema_version": HARNESS_SCHEMA_VERSION,
            "harness": {"type": "<harness-type>"},
            "agents": [{"name": "<agent-name>", "provider": "<provider>", "model": "<model>", "system_prompt": "<prompt-or-$file>", "params": {}, "tools": []}],
            "orchestration": {},
            "metadata": {},
        }

    def view_tools(self) -> dict[str, Any]:
        # Returns the document structure a tools .yaml file must follow.
        return {"version": _SUPPORTED_VERSION, "kind": ConfigKind.TOOLS.value, "tools": [ToolDefinition.expected_structure()]}

    def view_middleware(self) -> dict[str, Any]:
        # Returns the document structure a middleware .yaml file must follow.
        return {"version": _SUPPORTED_VERSION, "kind": ConfigKind.MIDDLEWARE.value, "middleware": [MiddlewareDefinition.expected_structure()]}

    def _load_agent_document(self, path: Path, document: dict[str, Any]) -> AgentSettings:
        # Validates the agent envelope and delegates field validation to AgentSettings.
        try:
            body = self._envelope(document, ConfigKind.AGENT, path)
            return AgentSettings.from_mapping(body, "agent")
        except ConfigurationError as error:
            self._enrich(error, path, ConfigKind.AGENT)
            raise

    def _load_definitions(self, path: Path, document: dict[str, Any], kind: ConfigKind, definition: type[ToolDefinition | MiddlewareDefinition]) -> tuple[Any, ...]:
        # Validates a definition-list envelope and builds each entry through its dataclass.
        try:
            body = self._envelope(document, kind, path)
            if not isinstance(body, list):
                raise ConfigurationError(f"'{kind.value}' must be a list.", details={"field": kind.value, "actual_type": type(body).__name__})
            items = tuple(definition.from_mapping(entry, f"{kind.value}[{index}]") for index, entry in enumerate(body))
            self._reject_duplicate_refs(items, kind)
            return items
        except ConfigurationError as error:
            self._enrich(error, path, kind)
            raise

    def _envelope(self, document: Mapping[str, Any], kind: ConfigKind, path: Path) -> Any:
        # Validates the shared ``version``/``kind`` envelope and returns the typed body.
        allowed = {"version", "kind", kind.value}
        unknown = sorted(set(document).difference(allowed))
        if unknown:
            raise ConfigurationError(f"Document contains unsupported top-level field(s): {', '.join(unknown)}.", details={"field": unknown[0], "allowed": sorted(allowed)})
        version = document.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version != _SUPPORTED_VERSION:
            raise ConfigurationError(f"Document 'version' must be the supported integer {_SUPPORTED_VERSION}.", details={"field": "version", "found": version})
        if document.get("kind") != kind.value:
            raise ConfigurationError(f"Document 'kind' must be {kind.value!r}.", details={"field": "kind", "found": document.get("kind"), "expected": kind.value})
        if kind.value not in document:
            raise ConfigurationError(f"Document is missing its '{kind.value}' body.", details={"field": kind.value})
        return document[kind.value]

    def _detect_kind(self, document: Mapping[str, Any], path: Path) -> ConfigKind:
        # Chooses the document kind from its declared envelope for the central load() dispatch.
        if "kind" in document:
            raw = document.get("kind")
            try:
                return ConfigKind(raw)
            except (TypeError, ValueError) as error:
                supported = sorted(member.value for member in ConfigKind)
                raise ConfigurationError(f"Document 'kind' must be one of {supported}.", details={"path": str(path), "field": "kind", "found": raw}) from error
        if "schema_version" in document or "harness" in document:
            return ConfigKind.HARNESS
        raise ConfigurationError(
            "Document does not declare a configuration kind; expected an agent/tools/middleware document with a 'kind' field or a harness document with a 'schema_version' field.",
            details={"path": str(path), "field": "kind"},
        )

    def _read(self, path: Path) -> dict[str, Any]:
        # Reads one YAML file into a validated top-level mapping with duplicate keys rejected.
        try:
            loaded = yaml.load(path.read_text(encoding="utf-8"), Loader=_DuplicateKeySafeLoader)
        except (OSError, UnicodeError, yaml.YAMLError) as error:
            raise ConfigurationError(f"Unable to read a valid YAML document: {error}", details={"path": str(path), "field": "document"}) from error
        if not isinstance(loaded, Mapping) or not all(isinstance(key, str) for key in loaded):
            raise ConfigurationError("Document root must be a mapping with string keys.", details={"path": str(path), "field": "document", "actual_type": type(loaded).__name__})
        return dict(loaded)

    def _path(self, value: str | Path) -> Path:
        # Validates the public path type and extension before attempting file access.
        if not isinstance(value, (str, Path)):
            raise ConfigurationError("Configuration path must be a string or pathlib.Path.", details={"field": "path", "actual_type": type(value).__name__})
        path = Path(value)
        if path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            raise ConfigurationError("Configuration files must use a .yaml or .yml extension.", details={"path": str(path), "field": "path", "suffix": path.suffix})
        return path

    @staticmethod
    def _reject_duplicate_refs(items: tuple[Any, ...], kind: ConfigKind) -> None:
        # Rejects two entries that declare the same reference in one definition document.
        references = [item.ref for item in items]
        duplicates = sorted({ref for ref in references if references.count(ref) > 1})
        if duplicates:
            raise ConfigurationError(f"'{kind.value}' must not contain duplicate references: {', '.join(duplicates)}.", details={"field": kind.value, "duplicates": duplicates})

    @staticmethod
    def _enrich(error: ConfigurationError, path: Path, kind: ConfigKind) -> None:
        # Attaches the offending file and expected kind so diagnostics name the exact document.
        error.details.setdefault("path", str(path))
        error.details.setdefault("expected_kind", kind.value)


__all__ = ["YamlLoader"]

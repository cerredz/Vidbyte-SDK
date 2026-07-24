"""Context Protocol Header

Description:
    Provides the public class-first YAML configuration loader.
Purpose:
    Safely parses one YAML document into either validated agent settings or a harness
    specification, with no ``kind`` field: agent documents are distinguished from harness
    documents by the harness envelope and all field validation lives on the dataclasses.
Architecture:
    - YamlLoader: Stateless public interface with a central load() plus typed loaders.
    - load(): reads one document and returns an AgentSettings subclass or a HarnessSpec.
    - load_agent()/load_harness(): parse one document of a known family.
    - view_agent(): returns the expected agent-document structure without touching the disk.
    - _DuplicateKeySafeLoader: SafeLoader variant that rejects ambiguous mappings.
Relations:
    Builds the dataclasses in vidbyte.lib.dataclasses.config and delegates harness documents
    to vidbyte.harnesses.HarnessConfigLoader.
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
from vidbyte.harnesses.contracts import HarnessSpec
from vidbyte.lib.dataclasses.config import AgentSettings
from vidbyte.lib.errors import ConfigurationError

_SUPPORTED_SUFFIXES = frozenset({".yaml", ".yml"})
_HARNESS_ENVELOPE_KEYS = frozenset({"schema_version", "harness"})


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
    """Stateless loader for agent and harness YAML documents."""

    def load(self, path: str | Path) -> AgentSettings | HarnessSpec:
        # Reads one document and returns a harness spec or an agent settings object by envelope.
        document_path = self._path(path)
        document = self._read(document_path)
        if self._is_harness(document):
            return self.load_harness(document_path)
        return self._build_agent(document_path, document)

    def load_agent(self, path: str | Path) -> AgentSettings:
        # Loads one agent document into validated settings without resolving referenced components.
        document_path = self._path(path)
        return self._build_agent(document_path, self._read(document_path))

    def load_harness(self, path: str | Path) -> HarnessSpec:
        # Loads one harness document into a validated, content-addressed HarnessSpec.
        document_path = self._path(path)
        try:
            return HarnessConfigLoader().load(document_path)
        except ConfigurationError as error:
            error.details.setdefault("path", str(document_path))
            raise

    def view_agent(self) -> dict[str, Any]:
        # Returns the document structure a base agent .yaml file must follow.
        return AgentSettings.expected_structure()

    def _build_agent(self, path: Path, document: Mapping[str, Any]) -> AgentSettings:
        # Delegates all field validation to AgentSettings and names the offending file on failure.
        try:
            return AgentSettings.from_mapping(document, "agent")
        except ConfigurationError as error:
            error.details.setdefault("path", str(path))
            raise

    def _is_harness(self, document: Mapping[str, Any]) -> bool:
        # Recognizes a harness document by its own envelope so agents need no ``kind`` field.
        return any(key in document for key in _HARNESS_ENVELOPE_KEYS)

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


__all__ = ["YamlLoader"]

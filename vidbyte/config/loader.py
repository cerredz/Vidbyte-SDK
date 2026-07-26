"""Context Protocol Header

Description:
    Provides the public class-first YAML configuration loader and agent builder.
Purpose:
    Safely parses one YAML document into either validated agent settings or a harness
    specification, with no ``kind`` field: agent documents are distinguished from harness
    documents by the harness envelope and all field validation lives on the dataclasses.
    build_agent() then turns those settings into a live agent, so the SDK owns construction
    instead of every application repeating it.
Architecture:
    - YamlLoader: Stateless public interface with a central load() plus typed loaders.
    - load(): reads one document and returns an AgentSettings subclass or a HarnessSpec.
    - load_agent()/load_harness(): parse one document of a known family.
    - build_agent(): builds one BaseAgent from exactly the settings load() returned, resolving
      every declared ref through the SDK's own ComponentRegistry.
    - view_agent(): returns the expected agent-document structure without touching the disk.
    - _DuplicateKeySafeLoader: SafeLoader variant that rejects ambiguous mappings.
Relations:
    Builds the dataclasses in vidbyte.lib.dataclasses.config and delegates harness documents
    to vidbyte.harnesses.HarnessConfigLoader. Tool, middleware, and context-item references
    resolve through vidbyte.lib.registries.ComponentRegistry; BaseAgent is imported inside the
    construction method so this package's dependency on vidbyte.agents stays reversible.
Non-Goals:
    Never imports code named by a document or interpolates secrets. A ref selects a class the
    SDK already registers; a document cannot name application-defined tools or middleware, which
    stay the caller's job to attach to the built agent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from yaml.nodes import MappingNode

from vidbyte.harnesses.config import HarnessConfigLoader
from vidbyte.harnesses.contracts import HarnessSpec
from vidbyte.lib.dataclasses.config import AgentSettings
from vidbyte.lib.enums import AgentType
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.registries.components import ComponentRegistry
from vidbyte.tools.catalog import Tools

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent
    from vidbyte.agents.settings import AgentLoopSettings

_SUPPORTED_SUFFIXES = frozenset({".yaml", ".yml"})
_HARNESS_ENVELOPE_KEYS = frozenset({"schema_version", "harness"})
_TEXT_FILE_SUFFIXES = frozenset({".md", ".markdown", ".txt", ".text", ".rst"})


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
        return self._parse_agent_settings(document_path, document)

    def load_agent(self, path: str | Path) -> AgentSettings:
        # Loads one agent document into validated settings without resolving referenced components.
        document_path = self._path(path)
        return self._parse_agent_settings(document_path, self._read(document_path))

    def load_harness(self, path: str | Path) -> HarnessSpec:
        # Loads one harness document into a validated, content-addressed HarnessSpec.
        document_path = self._path(path)
        try:
            return HarnessConfigLoader().load(document_path)
        except ConfigurationError as error:
            error.details.setdefault("path", str(document_path))
            raise

    def build_agent(self, settings: AgentSettings, *, name: str | None = None) -> "BaseAgent":
        # Builds one live agent from exactly the settings load_agent() returned, resolving every declared ref through the SDK's component registry.
        buildable = self._buildable_settings(settings, name)
        tools = ComponentRegistry.build_tools(buildable.tools)
        self._assert_contract_tools_resolve(buildable, tools)
        return self._construct_agent(buildable, tools, ComponentRegistry.build_middleware(buildable.middleware), ComponentRegistry.build_context_items(buildable.context_items))

    def view_agent(self) -> dict[str, Any]:
        # Returns the document structure a base agent .yaml file must follow.
        return AgentSettings.expected_structure()

    def _parse_agent_settings(self, path: Path, document: Mapping[str, Any]) -> AgentSettings:
        # Resolves a system_prompt text-file reference, then delegates all validation to AgentSettings.
        prompt = document.get("system_prompt")
        if isinstance(prompt, str) and Path(prompt.strip()).suffix.lower() in _TEXT_FILE_SUFFIXES:
            document = {**document, "system_prompt": self._load_file(self._contained(path, prompt.strip()))}
        try:
            return AgentSettings.from_mapping(document, "agent")
        except ConfigurationError as error:
            error.details.setdefault("path", str(path))
            raise

    def _contained(self, document_path: Path, reference: str) -> Path:
        # @intent prompt-file-containment
        # The prompt reference comes from the same untrusted document as every other field, so it may
        # only name a file beside the document; without this, '../../../etc/passwd' becomes the prompt.
        base = document_path.parent.resolve()
        target = (base / reference).resolve()
        if base != target and base not in target.parents:
            raise ConfigurationError(
                "A system_prompt file reference must stay inside the configuration file's directory.",
                details={"field": "agent.system_prompt", "path": str(document_path), "reference": reference, "resolved": str(target), "base": str(base)},
            )
        return target

    def _load_file(self, target: Path) -> str:
        # Loads one supported text-based file's contents as UTF-8, dispatching on its extension.
        match target.suffix.lower():
            case ".md" | ".markdown" | ".txt" | ".text" | ".rst":
                return target.read_text(encoding="utf-8")
            case other:
                raise ConfigurationError(f"Unsupported system_prompt file type '{other}'.", details={"field": "agent.system_prompt", "suffix": other})

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

    def _buildable_settings(self, settings: object, name: str | None) -> AgentSettings:
        # Accepts only base-agent settings and applies the optional name override before anything is resolved.
        if isinstance(settings, HarnessSpec):
            raise ConfigurationError("A harness document is not buildable into one agent; load the agent document with load_agent() instead.", details={"field": "build_agent.settings", "harness_type": settings.harness_type, "agents": [str(agent.get("name", "")) for agent in settings.agents]})
        if not isinstance(settings, AgentSettings):
            raise ConfigurationError("build_agent() requires the AgentSettings returned by load() or load_agent().", details={"field": "build_agent.settings", "actual_type": type(settings).__name__})
        if settings.type is not AgentType.BASE:
            raise ConfigurationError(f"Only '{AgentType.BASE.value}' agent settings can be built today; got '{settings.type.value}'.", details={"field": "build_agent.settings", "agent_type": settings.type.value, "buildable": [AgentType.BASE.value]})
        return settings if name is None else self._renamed(settings, name)

    def _renamed(self, settings: AgentSettings, name: str) -> AgentSettings:
        # @intent revalidated-name-override
        # replace() re-runs __post_init__, so an override goes through the same name rules the document
        # did; without it a caller could hand BaseAgent a name no provider accepts as a tool name.
        try:
            return replace(settings, name=name)
        except ConfigurationError as error:
            error.details["field"] = "build_agent.name"
            raise

    def _assert_contract_tools_resolve(self, settings: AgentSettings, tools: Tools) -> None:
        # @intent unsatisfiable-floors-fail-at-build
        # An output-contract floor naming a tool the agent will not have can never be met, so the run would
        # spend its whole rejection budget and fail late. Ceilings are not checked: an unmatched
        # max_calls_per_tool or allowed_tools entry is inert, and both may legitimately name a tool attached
        # after construction. A floor on such a tool must declare it so it arrives in the catalog.
        if not settings.tools:
            return
        available = set(tools.names())
        missing = sorted({name for name in self._contract_tool_names(settings.loop) if name not in available})
        if missing:
            raise ConfigurationError(f"'agent.loop.output_contracts' requires calls to tool(s) the agent will not have: {', '.join(missing)}.", details={"field": "agent.loop.output_contracts", "missing": missing, "available": sorted(available)})

    def _contract_tool_names(self, loop: "AgentLoopSettings") -> tuple[str, ...]:
        # Collects the tool identity of every output contract that targets one named tool.
        return tuple(str(getattr(contract, "tool_name")) for contract in loop.output_contracts if getattr(contract, "tool_name", None))

    def _construct_agent(self, settings: AgentSettings, tools: Tools, middleware: tuple[object, ...], context_items: tuple[object, ...]) -> "BaseAgent":
        # Maps validated settings and the components built from them onto BaseAgent keyword arguments.
        from vidbyte.agents.base import BaseAgent

        try:
            return BaseAgent(**settings.to_agent_kwargs(tools=tools, middleware=middleware, context_items=context_items))
        except (TypeError, ValueError) as error:
            raise ConfigurationError(f"Settings for agent '{settings.name}' did not construct a BaseAgent: {error}", details={"field": "agent", "agent": settings.name}) from error


__all__ = ["YamlLoader"]

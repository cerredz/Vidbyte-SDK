"""Context Protocol Header

Description:
    Defines YamlLoader — the single entry point for reading Vidbyte SDK YAML
    configuration files. Produces AgentDescriptor, HarnessDescriptor, or
    EnvironmentDescriptor objects depending on the document type discriminator.
Purpose:
    Provides a thin I/O-and-dispatch layer. All field validation lives on the
    descriptor dataclasses and the existing runtime settings objects they compose.
Architecture:
    - YamlLoader: three typed public methods (load_agent, load_harness, load_environment)
      that share a private _read_yaml helper.
    - _read_yaml: validates extension, reads text, parses with a duplicate-key-aware
      SafeLoader, requires a mapping root.
    - _build_*: construct the appropriate descriptor, enrich errors with file path.
Relations:
    Lives in vidbyte/lib/config/ so every SDK sub-package can import without cycles.
    Composes AgentDescriptor, HarnessDescriptor, EnvironmentDescriptor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from vidbyte.agents.settings.loop import AgentLoopSettings
from vidbyte.agents.settings.tool import ToolSettings
from vidbyte.agents.settings import ToolErrorPolicy
from vidbyte.lib.dataclasses.adversarial_agent_descriptor import AdversarialAgentDescriptor
from vidbyte.lib.dataclasses.aggregate_agent_descriptor import AggregateAgentDescriptor
from vidbyte.lib.dataclasses.agent_descriptor import AgentDescriptor
from vidbyte.lib.dataclasses.agents import AgentMetadata
from vidbyte.lib.dataclasses.continual_trace_descriptor import ContinualTraceAgentDescriptor
from vidbyte.lib.dataclasses.environment_descriptor import EnvironmentDescriptor
from vidbyte.lib.dataclasses.harness_descriptor import HarnessDescriptor
from vidbyte.lib.dataclasses.multi_agent_descriptor import MultiAgentDescriptor
from vidbyte.lib.dataclasses.tools import ToolSpec
from vidbyte.lib.dataclasses.trace import TraceOption
from vidbyte.lib.dataclasses.handoff_agent_descriptor import HandoffAgentDescriptor
from vidbyte.lib.enums.agent_runtime import AgentRuntimeType
from vidbyte.lib.enums.config import AgentType, DocumentType
from vidbyte.lib.errors import ConfigurationError

_MAX_FILE_BYTES = 10 * 1024 * 1024
_SUPPORTED_EXTENSIONS = frozenset({".yaml", ".yml"})


class _DuplicateKeySafeLoader(yaml.SafeLoader):
    """SafeLoader variant that rejects duplicate mapping keys."""

    def __init__(self, stream: Any) -> None:
        # Starts each load with no recorded own-pair counts; yaml nodes hash by identity.
        super().__init__(stream)
        self._own_pair_counts: dict[yaml.nodes.MappingNode, int] = {}

    def flatten_mapping(self, node: yaml.nodes.MappingNode) -> None:
        # Records how many pairs the mapping wrote itself before its merge keys are flattened away.
        self._own_pair_counts.setdefault(node, sum(1 for key_node, _ in node.value if key_node.tag != "tag:yaml.org,2002:merge"))
        super().flatten_mapping(node)

    def construct_mapping(self, node: yaml.nodes.MappingNode, deep: bool = False) -> dict[Any, Any]:
        # Builds a mapping while detecting and rejecting duplicate keys.
        # @intent yaml-merge-keys-are-resolved
        # `<<` pairs are flattened in front of the mapping's own pairs, as SafeLoader does, so an own key may override a
        # merged one; own counts are recorded at first flatten because a parent's merge can flatten an anchored child
        # before the child itself is constructed.
        self.flatten_mapping(node)
        merged_count = len(node.value) - self._own_pair_counts[node]
        mapping: dict[Any, Any] = {}
        own_keys: set[Any] = set()
        for index, (key_node, value_node) in enumerate(node.value):
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, (str, int, float, bool, type(None))):
                key = str(key)
            if index >= merged_count:
                if key in own_keys:
                    raise yaml.constructor.ConstructorError(
                        None, None,
                        f"Duplicate key {key!r} is not allowed",
                        key_node.start_mark,
                    )
                own_keys.add(key)
            mapping[key] = value_node
        result: dict[Any, Any] = {}
        for key, value_node in mapping.items():
            result[key] = self.construct_object(value_node, deep=deep)
        return result


class YamlLoader:
    """Loads Vidbyte SDK YAML configuration files into typed descriptor objects.

    All field validation lives on the descriptor dataclasses and composed
    settings objects. This class performs only I/O and document-type dispatch.
    """

    def load_agent(self, path: str | Path) -> AgentDescriptor:
        # Reads and validates an agent YAML document, returning an AgentDescriptor.
        raw = self._read_yaml(path)
        return self._build_agent(raw, path)

    def load_harness(self, path: str | Path) -> HarnessDescriptor:
        # Reads and validates a harness YAML document, returning a HarnessDescriptor.
        raw = self._read_yaml(path)
        return self._build_harness(raw, path)

    def load_environment(self, path: str | Path) -> EnvironmentDescriptor:
        # Reads and validates an environment YAML document, returning an EnvironmentDescriptor.
        raw = self._read_yaml(path)
        return self._build_environment(raw, path)

    @staticmethod
    def _read_yaml(path: str | Path) -> dict[str, Any]:
        # Validates the file extension, reads the file, and parses YAML safely.
        file_path = Path(path)
        if file_path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            raise ConfigurationError(
                f"Unsupported file extension '{file_path.suffix}'. Expected .yaml or .yml.",
                details={"path": str(file_path), "expected": sorted(_SUPPORTED_EXTENSIONS)},
            )
        if not file_path.is_file():
            raise ConfigurationError(
                f"YAML file not found: {file_path}",
                details={"path": str(file_path)},
            )
        if file_path.stat().st_size > _MAX_FILE_BYTES:
            raise ConfigurationError(
                f"YAML file exceeds maximum size of {_MAX_FILE_BYTES} bytes.",
                details={"path": str(file_path), "max_bytes": _MAX_FILE_BYTES},
            )
        # @intent unreadable-yaml-is-a-configuration-error
        # A file that is not UTF-8 text, or cannot be read, is reported like every other loader failure, as vidbyte.config.YamlLoader and the harness config loader already do.
        try:
            text = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ConfigurationError(
                f"Unable to read YAML file as UTF-8 text ({type(exc).__name__}): {exc}",
                details={"path": str(file_path)},
            ) from exc
        try:
            raw = yaml.load(text, Loader=_DuplicateKeySafeLoader)
        except yaml.YAMLError as exc:
            raise ConfigurationError(
                f"Failed to parse YAML: {exc}",
                details={"path": str(file_path)},
            ) from exc
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ConfigurationError(
                "YAML root must be a mapping, not a scalar or list.",
                details={"path": str(file_path), "actual_type": type(raw).__name__},
            )
        return dict(raw)

    @staticmethod
    def _text(mapping: dict[str, Any], key: str, default: str = "") -> str:
        # Reads one text field, treating a blank value exactly like an omitted key.
        # @intent yaml-blank-value-is-not-the-text-none
        # YAML parses `key:`, `key: ~` and `key: null` as None, and str(None) is the text "None", which would slip past the descriptors' non-empty checks.
        value = mapping.get(key)
        return default if value is None else str(value)

    @staticmethod
    def _build_agent(raw: dict[str, Any], path: str | Path) -> AgentDescriptor:
        # Constructs an AgentDescriptor from raw YAML, validating via __post_init__.
        return YamlLoader._build_agent_from_raw(raw, path, top_level=True)

    @staticmethod
    def _build_agent_from_raw(raw: dict[str, Any], path: str | Path, *, top_level: bool = False) -> AgentDescriptor:
        # Builds an AgentDescriptor from a raw mapping, used for both top-level and nested agents.
        agent_type_raw = raw.get("agent_type", "base")
        try:
            agent_type = AgentType(agent_type_raw)
        except ValueError as exc:
            raise ConfigurationError(
                f"Unknown agent_type '{agent_type_raw}'. Known types: {AgentType.values()}.",
                details={"path": str(path), "field": "agent_type", "expected": list(AgentType.values())},
            ) from exc
        if agent_type == AgentType.BASE:
            return YamlLoader._construct_base_agent(raw, path)
        if agent_type == AgentType.MULTI:
            return YamlLoader._build_multi_agent(raw, path)
        if agent_type == AgentType.AGGREGATE:
            return YamlLoader._build_aggregate_agent(raw, path)
        if agent_type == AgentType.ADVERSARIAL:
            return YamlLoader._build_adversarial_agent(raw, path)
        if agent_type == AgentType.HANDOFF:
            return YamlLoader._build_handoff_agent(raw, path)
        if agent_type == AgentType.CONTINUAL_TRACE:
            return YamlLoader._build_continual_trace_agent(raw, path)

    @staticmethod
    def _construct_base_agent(raw: dict[str, Any], path: str | Path) -> AgentDescriptor:
        # Builds an AgentDescriptor for a base agent, composing existing settings classes.
        loop_raw = dict(raw.get("loop", {}))
        tool_settings_raw = loop_raw.pop("tool_settings", None)
        output_contracts_raw = loop_raw.pop("output_contracts", None)
        tool_settings = ToolSettings(**tool_settings_raw) if tool_settings_raw else None
        # @intent lib-loader-builds-tool-error-policy
        # YAML only yields a plain mapping for the retry/abort policy, so build the real policy the loop settings require.
        tool_error_policy = loop_raw.pop("tool_error_policy", None)
        if isinstance(tool_error_policy, dict):
            tool_error_policy = ToolErrorPolicy(**tool_error_policy)
        # @intent lib-loader-builds-output-contracts
        # YAML only yields plain mappings, so each contract is built into its floor before the loop settings read it.
        output_contracts = YamlLoader._build_output_contracts(output_contracts_raw, path)
        loop = AgentLoopSettings(
            **loop_raw,
            tool_settings=tool_settings,
            tool_error_policy=tool_error_policy,
            output_contracts=output_contracts,
        )
        tools_raw = raw.get("tools", [])
        tools = tuple(
            ToolSpec(
                name=t.get("ref", ""),
                description=t.get("ref", ""),
                metadata=dict(t.get("options", {})),
            )
            for t in tools_raw
        ) if tools_raw else ()
        middleware_refs = tuple(
            str(ref) for ref in raw.get("middleware", [])
        )
        capabilities = tuple(
            str(cap) for cap in raw.get("capabilities", [])
        )
        agent_metadata_raw = raw.get("agent_metadata", {})
        agent_metadata = AgentMetadata(
            name=YamlLoader._text(agent_metadata_raw, "name"),
            description=YamlLoader._text(agent_metadata_raw, "description"),
            use_cases=YamlLoader._text(agent_metadata_raw, "use_cases"),
        ) if agent_metadata_raw else AgentMetadata()
        trace_option = None
        if "trace_option" in raw:
            trace_raw = dict(raw["trace_option"])
            trace_option = TraceOption(
                mode=trace_raw.get("mode", "continual"),
                schema=trace_raw.get("schema", {}),
                every_n_iterations=trace_raw.get("every_n_iterations", 5),
                max_trace_iterations=trace_raw.get("max_trace_iterations", 3),
            )
        descriptor = AgentDescriptor(
            type=AgentType.BASE,
            name=YamlLoader._text(raw, "name"),
            system_prompt=YamlLoader._text(raw, "system_prompt"),
            description=YamlLoader._text(raw, "description"),
            provider=raw.get("provider"),
            model_name=raw.get("model_name"),
            temperature=raw.get("temperature"),
            runtime=AgentRuntimeType(raw.get("runtime", "linear")),
            loop=loop,
            tools=tools,
            middleware_refs=middleware_refs,
            capabilities=capabilities,
            agent_metadata=agent_metadata,
            algorithm=raw.get("algorithm"),
            output_schema=raw.get("output_schema"),
            trace_option=trace_option,
            metadata=dict(raw.get("metadata", {})),
        )
        return descriptor

    @staticmethod
    def _build_output_contracts(raw_contracts: Any, path: str | Path) -> tuple[Any, ...]:
        # Builds each `{type: <FloorName>, ...}` mapping into its concrete floor, naming the file and position on failure.
        from vidbyte.agents import contracts

        # The abstract base is never satisfiable and SchemaConformance comes from output_schema, so neither is nameable here.
        floors = {name: getattr(contracts, name) for name in contracts.__all__ if name not in {"OutputContract", "SchemaConformance"}}
        if raw_contracts and not isinstance(raw_contracts, (list, tuple)):
            raise ConfigurationError("'loop.output_contracts' must be a list of contract mappings.", details={"path": str(path), "field": "loop.output_contracts", "actual_type": type(raw_contracts).__name__})
        built: list[Any] = []
        for index, item in enumerate(raw_contracts or ()):
            field = f"loop.output_contracts[{index}]"
            if isinstance(item, contracts.OutputContract):
                built.append(item)
                continue
            payload = dict(item) if isinstance(item, dict) else {}
            name = payload.pop("type", None)
            builder = floors.get(name) if isinstance(name, str) else None
            if builder is None:
                raise ConfigurationError(f"'{field}' must be a mapping whose 'type' is one of {sorted(floors)}.", details={"path": str(path), "field": field, "actual_value": repr(name), "expected": sorted(floors)})
            try:
                built.append(builder(**payload))
            except (TypeError, ValueError, ConfigurationError) as exc:
                raise ConfigurationError(f"'{field}' is invalid: {exc}", details={"path": str(path), "field": field}) from exc
        return tuple(built)

    @staticmethod
    def _build_harness(raw: dict[str, Any], path: str | Path) -> HarnessDescriptor:
        # Constructs a HarnessDescriptor from raw YAML, validating via __post_init__.
        try:
            params = dict(raw.get("params", {}))
            agent_raw = raw.get("agent")
            agent = YamlLoader._build_agent_from_raw(agent_raw, path) if agent_raw else None
            return HarnessDescriptor(
                name=YamlLoader._text(raw, "name"),
                description=YamlLoader._text(raw, "description"),
                params=params,
                agent=agent,
            )
        except ConfigurationError:
            raise
        except Exception as exc:
            raise ConfigurationError(
                f"Failed to build harness descriptor: {exc}",
                details={"path": str(path)},
            ) from exc

    @staticmethod
    def _build_environment(raw: dict[str, Any], path: str | Path) -> EnvironmentDescriptor:
        # Constructs an EnvironmentDescriptor from raw YAML, validating via __post_init__.
        try:
            context = YamlLoader._build_agent_from_raw(raw["context"], path) if "context" in raw else None
            splitter = YamlLoader._build_agent_from_raw(raw["splitter"], path) if "splitter" in raw else None
            adversarial = YamlLoader._build_agent_from_raw(raw["adversarial"], path) if "adversarial" in raw else None
            implementation = YamlLoader._build_agent_from_raw(raw["implementation"], path) if "implementation" in raw else None
            settings_raw = raw.get("settings")
            settings = None
            if settings_raw:
                from vidbyte.paradigms.context_minimal_fanout.types import ContextMinimalFanoutSettings
                settings = ContextMinimalFanoutSettings(**settings_raw)
            return EnvironmentDescriptor(
                name=YamlLoader._text(raw, "name"),
                context=context,
                splitter=splitter,
                adversarial=adversarial,
                implementation=implementation,
                settings=settings,
            )
        except ConfigurationError:
            raise
        except Exception as exc:
            raise ConfigurationError(
                f"Failed to build environment descriptor: {exc}",
                details={"path": str(path)},
            ) from exc

    @staticmethod
    def _build_multi_agent(raw: dict[str, Any], path: str | Path) -> MultiAgentDescriptor:
        # Builds a MultiAgentDescriptor from raw YAML, composing nested AgentDescriptors.
        orchestrator_raw = raw.get("orchestrator")
        orchestrator = YamlLoader._build_agent_from_raw(orchestrator_raw, path) if orchestrator_raw else None
        agents_raw = raw.get("agents", [])
        agents = tuple(YamlLoader._build_agent_from_raw(a, path) for a in agents_raw) if agents_raw else ()
        settings_raw = raw.get("settings", {})
        from vidbyte.lib.dataclasses.multi_agent import MultiAgentSettings
        settings = MultiAgentSettings(**settings_raw) if settings_raw else MultiAgentSettings()
        return MultiAgentDescriptor(
            name=YamlLoader._text(raw, "name"),
            system_prompt=YamlLoader._text(raw, "system_prompt"),
            description=YamlLoader._text(raw, "description"),
            orchestrator=orchestrator,
            agents=agents,
            settings=settings,
            capabilities=tuple(str(c) for c in raw.get("capabilities", [])),
            metadata=dict(raw.get("metadata", {})),
        )

    @staticmethod
    def _build_aggregate_agent(raw: dict[str, Any], path: str | Path) -> AggregateAgentDescriptor:
        # Builds an AggregateAgentDescriptor from raw YAML, composing ProposerSpecs.
        from vidbyte.lib.dataclasses.multi_agent import AggregateConfig, ProposerSpec
        proposers_raw = raw.get("proposers", [])
        proposers = tuple(
            ProposerSpec(provider=p.get("provider", ""), model=p.get("model", ""), label=p.get("label"), system_prompt=p.get("system_prompt"))
            for p in proposers_raw
        ) if proposers_raw else ()
        aggregator_raw = raw.get("aggregator")
        aggregator = ProposerSpec(provider=aggregator_raw.get("provider", ""), model=aggregator_raw.get("model", ""), label=aggregator_raw.get("label"), system_prompt=aggregator_raw.get("system_prompt")) if aggregator_raw else None
        config_raw = raw.get("config", {})
        config = AggregateConfig(**config_raw) if config_raw else AggregateConfig()
        return AggregateAgentDescriptor(
            name=YamlLoader._text(raw, "name"),
            system_prompt=YamlLoader._text(raw, "system_prompt"),
            description=YamlLoader._text(raw, "description"),
            proposers=proposers,
            aggregator=aggregator,
            config=config,
            metadata=dict(raw.get("metadata", {})),
        )

    @staticmethod
    def _build_adversarial_agent(raw: dict[str, Any], path: str | Path) -> AdversarialAgentDescriptor:
        # Builds an AdversarialAgentDescriptor from raw YAML, composing nested AgentDescriptors.
        from vidbyte.lib.dataclasses.adversarial_agent_descriptor import AdversarialSettings
        worker_raw = raw.get("worker")
        worker = YamlLoader._build_agent_from_raw(worker_raw, path) if worker_raw else None
        adversary_raw = raw.get("adversary")
        adversary = YamlLoader._build_agent_from_raw(adversary_raw, path) if adversary_raw else None
        settings_raw = raw.get("settings", {})
        settings = AdversarialSettings(**settings_raw) if settings_raw else AdversarialSettings()
        return AdversarialAgentDescriptor(
            name=YamlLoader._text(raw, "name"),
            system_prompt=YamlLoader._text(raw, "system_prompt"),
            description=YamlLoader._text(raw, "description"),
            worker=worker,
            adversary=adversary,
            settings=settings,
            capabilities=tuple(str(c) for c in raw.get("capabilities", [])),
            metadata=dict(raw.get("metadata", {})),
        )

    @staticmethod
    def _build_handoff_agent(raw: dict[str, Any], path: str | Path) -> HandoffAgentDescriptor:
        # Builds a HandoffAgentDescriptor from raw YAML.
        handoff_raw = raw.get("handoff", {})
        sections_raw = handoff_raw.get("sections", {})
        sections = tuple(sections_raw.keys()) if isinstance(sections_raw, dict) else tuple(str(s) for s in sections_raw) if sections_raw else ()
        source = raw.get("source", {})
        return HandoffAgentDescriptor(
            name=YamlLoader._text(raw, "name", "handoff"),
            handoff_title=YamlLoader._text(handoff_raw, "title", "Handoff"),
            handoff_instructions=YamlLoader._text(handoff_raw, "instructions"),
            sections=sections,
            source_provider=source.get("provider") if source else None,
            source_model_name=source.get("model_name") if source else None,
            metadata=dict(raw.get("metadata", {})),
        )

    @staticmethod
    def _build_continual_trace_agent(raw: dict[str, Any], path: str | Path) -> ContinualTraceAgentDescriptor:
        # Builds a ContinualTraceAgentDescriptor from raw YAML.
        schema = dict(raw.get("schema", {}))
        source = raw.get("source", {})
        return ContinualTraceAgentDescriptor(
            name=YamlLoader._text(raw, "name", "continual-trace"),
            schema=schema,
            max_trace_iterations=int(raw.get("max_trace_iterations", 3)),
            source_provider=source.get("provider") if source else None,
            source_model_name=source.get("model_name") if source else None,
            metadata=dict(raw.get("metadata", {})),
        )


__all__ = ["YamlLoader"]

"""Context Protocol Header

Description:
    Implements ForkConversationTool, Vidbyte's agent-bound builtin for self-forking.
Purpose:
    Lets an agent fork its current Vidbyte run with SDK-native parts swapped,
    run that child branch, and receive the child answer as a normal tool result.
Architecture:
    - ForkConversationTool: Validates model-facing Vidbyte fork parameters,
      enforces non-escalation, calls BaseAgent.fork(), and awaits the child reply.
Relations:
    Bound by BaseAgent._bind_agent_tool_context. Uses BaseAgent.fork and Tools.
Similar Files:
    - vidbyte/tools/builtins/handoff/create.py: Canonical agent-bound builtin.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.agents.runtimes.configs import ActorRuntime
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.context.handoff import EngineeringHandoff, Handoff, MinimalHandoff, ResearchHandoff
from vidbyte.context.window import ContextWindow
from vidbyte.lib.dataclasses.agents import AgentForkSettings
from vidbyte.lib.enums import AgentRuntimeType, ModelModality, ModelProvider
from vidbyte.tools.base import BaseTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

_TOOL_NAME = "fork_conversation"
_HISTORY_MODES = {"full", "none", "last_n"}
_CONTEXT_ALGORITHM_PRESETS = (
    "default",
    "raw_tool_outputs",
    "compact_tool_outputs",
    "hide_tool_outputs",
    "no_raw_tool_outputs",
    "reflexion",
    "multi_provider_agentic_grader",
    "trajectory_checkpoints",
    "problem_space_search",
    "error_correction",
)
_HANDOFF_PRESETS = {
    "minimal": MinimalHandoff,
    "engineering": EngineeringHandoff,
    "research": ResearchHandoff,
}
_LOOP_SETTING_FIELDS = (
    "max_iterations",
    "max_tokens",
    "max_tool_calls",
    "max_parallel_tool_calls",
    "max_retries",
    "timeout_seconds",
    "context_window_budget",
    "compaction_trigger_tokens",
    "compaction_target_tokens",
    "allowed_tools",
)
_STATIC_DESCRIPTION = """\
Fork the current Vidbyte agent run into a child branch with interchangeable SDK-native parts, run the \
child on a focused prompt, and return the child answer here. Use this when the next step should be \
isolated from the parent run, or when a different combination of Vidbyte agent parts is better for \
the branch: system prompt, model/provider, modality, tools, runtime, context-window algorithm, context \
budget/compaction settings, handoff spec, output schema, runner options, MCP carry, history slice, or \
run-state carry.

This is a Vidbyte-native fork, not a generic subprocess or delegation wrapper. Inputs use the SDK names \
that BaseAgent.fork understands: runtime values like "linear" and "mcts_search", context algorithms like \
"compact_tool_outputs" and "reflexion", and handoff presets like "minimal", "engineering", and "research".

You cannot grant yourself new permissions with this tool. Tool choices must come from the parent catalog \
or developer-configured extra toolsets, model changes must be allow-listed by the developer, max_iterations \
cannot exceed the parent's configured cap, and permission policy and credentials are always inherited.
"""


class ForkConversationTool(BaseTool):
    """Agent-bound builtin that runs one synchronous child fork and returns its answer."""

    def __init__(self, *, allowed_models: Sequence[str] = (), extra_toolsets: Mapping[str, Tools | Sequence[object]] | None = None, max_fork_depth: int = 2) -> None:
        # Stores developer-controlled allow-lists and starts unbound until BaseAgent attaches an agent.
        self._agent: Any = None
        self._allowed_models = tuple(str(model) for model in allowed_models)
        self._extra_toolsets = self._normalize_extra_toolsets(extra_toolsets)
        self._max_fork_depth = max_fork_depth

    def bind_agent(self, agent: Any) -> None:
        # Attaches the live parent agent whose state will be forked at execution time.
        self._agent = agent

    def clone_for_fork(self) -> ForkConversationTool:
        # Returns an unbound copy preserving developer allow-lists for forked child agents.
        return ForkConversationTool(allowed_models=self._allowed_models, extra_toolsets=self._extra_toolsets, max_fork_depth=self._max_fork_depth)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration and JSON Schema for self-forking.
        return ToolSpec(
            name=_TOOL_NAME,
            description=_STATIC_DESCRIPTION,
            permission=ToolPermission.SAFE,
            binds_to_primitive="fork",
            input_schema=self._input_schema(),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Validates arguments, creates a constrained child fork, and returns the child reply.
        if self._agent is None:
            return ToolResult.error(_TOOL_NAME, "fork_conversation is not bound to an agent.")
        try:
            request = self._build_request(dict(call.arguments))
            self._enforce_depth_cap()
            child = self._build_child(request)
            reply = await child.generate_reply(request["prompt"])
            return self._build_success(child, getattr(reply, "content", str(reply)))
        except Exception as exc:
            return ToolResult.error(_TOOL_NAME, str(exc), metadata={"error_type": type(exc).__name__})

    def _build_request(self, args: Mapping[str, Any]) -> dict[str, Any]:
        # Validates JSON-like tool arguments and returns normalized fork request values.
        prompt = str(args.get("prompt", "")).strip()
        if not prompt:
            raise ValueError("fork_conversation requires a non-empty 'prompt'.")
        context_window = self._optional_mapping(args.get("context_window"), "context_window")
        history_mode = str(args.get("history_mode", context_window.get("history_mode", "full"))).strip() or "full"
        if history_mode not in _HISTORY_MODES:
            raise ValueError("history_mode must be one of: full, none, last_n.")
        request = {
            "prompt": prompt,
            "system_prompt": self._optional_string(args.get("system_prompt")),
            "tools": self._resolve_tools(args.get("tool_names"), args.get("extra_toolset_names"), args.get("drop_tool_names")),
            "history": self._resolve_history(history_mode, args.get("last_n", context_window.get("last_n"))),
            "model": self._resolve_model(args.get("model")),
            "provider": self._resolve_provider(args.get("provider")),
            "modality": self._resolve_modality(args.get("modality")),
            "temperature": self._resolve_temperature(args.get("temperature")),
            "agent_loop_settings": self._resolve_loop_settings(args.get("loop_settings"), args.get("max_iterations"), context_window),
            "name": self._optional_string(args.get("name")),
            "purpose": self._optional_string(args.get("purpose")),
            "metadata": self._resolve_metadata(args.get("metadata")),
            "runtime": self._resolve_runtime(args.get("runtime"), args.get("actor_runtime")),
            "algorithm": self._resolve_context_algorithm(args.get("context_algorithm", context_window.get("algorithm"))),
            "handoff": self._resolve_handoff(args.get("handoff")),
            "output_schema": self._resolve_json_object(args.get("output_schema"), "output_schema"),
            "runner_options": self._resolve_json_object(args.get("runner_options"), "runner_options"),
            "include_run_state": self._resolve_bool(args.get("include_run_state"), default=False, field_name="include_run_state"),
            "mcp": self._resolve_bool(args.get("mcp"), default=True, field_name="mcp"),
            "run_id": self._optional_string(args.get("run_id")),
        }
        return request

    def _build_child(self, request: Mapping[str, Any]) -> Any:
        # Translates normalized request values into a single BaseAgent.fork call.
        metadata = dict(request.get("metadata") or {})
        if request.get("purpose"):
            metadata["fork_purpose"] = request["purpose"]
        settings = AgentForkSettings(
            name=request.get("name"),
            system_prompt=request.get("system_prompt"),
            tools=request.get("tools"),
            history=request.get("history"),
            model_name=request.get("model"),
            provider=request.get("provider"),
            modality=request.get("modality"),
            temperature=request.get("temperature"),
            agent_loop_settings=request.get("agent_loop_settings"),
            metadata=metadata or None,
            runtime=request.get("runtime"),
            algorithm=request.get("algorithm"),
            handoff=request.get("handoff"),
            output_schema=request.get("output_schema"),
            runner_options=request.get("runner_options"),
            include_run_state=bool(request.get("include_run_state")),
            mcp=bool(request.get("mcp")),
            run_id=request.get("run_id"),
        )
        return self._agent.fork(settings)

    def _build_success(self, child: Any, output: str) -> ToolResult:
        # Builds the successful tool result with child lineage metadata.
        metadata = {
            "child_run_id": child.runner_config.run_id,
            "forked_from": child.metadata.get("forked_from"),
            "fork_depth": child.metadata.get("fork_depth"),
            "name": child.name,
        }
        return ToolResult.success(_TOOL_NAME, output, metadata=metadata)

    def _resolve_tools(self, raw_names: Any, raw_extra_toolsets: Any, raw_drop_names: Any) -> Tools | None:
        # Resolves tool set requests against parent tools plus developer-configured extra toolsets.
        extra_names = self._coerce_string_tuple(raw_extra_toolsets, "extra_toolset_names")
        drop_names = self._coerce_string_tuple(raw_drop_names, "drop_tool_names")
        if raw_names is None and not extra_names and not drop_names:
            return None
        catalog = self._available_tools(extra_names)
        if raw_names is None:
            selected = catalog
        else:
            names = self._coerce_string_tuple(raw_names, "tool_names")
            selected = catalog.subset(names)
        if not drop_names:
            return selected
        unknown_drops = tuple(name for name in drop_names if name not in selected)
        if unknown_drops:
            raise ValueError(f"drop_tool_names includes tool(s) not available in the child set: {', '.join(repr(name) for name in unknown_drops)}")
        return Tools(tool for tool in selected if tool.name not in set(drop_names))

    def _available_tools(self, extra_names: tuple[str, ...] = ()) -> Tools:
        # Builds the non-escalating selectable catalog from parent tools and configured extras.
        unknown_extra = tuple(name for name in extra_names if name not in self._extra_toolsets)
        if unknown_extra:
            raise ValueError(f"Unknown extra_toolset_names: {', '.join(repr(name) for name in unknown_extra)}")
        selected_extra_names = extra_names or tuple(self._extra_toolsets)
        catalog = self._agent.tools
        for name in selected_extra_names:
            catalog = catalog.extend(self._extra_toolsets[name].all(), replace=True)
        return catalog

    def _coerce_string_tuple(self, value: Any, field_name: str) -> tuple[str, ...]:
        # Converts an optional array of strings into a tuple.
        if value is None:
            return ()
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise ValueError(f"{field_name} must be an array of strings when provided.")
        return tuple(str(name) for name in value)

    def _resolve_history(self, mode: str, raw_last_n: Any) -> list[Any]:
        # Resolves the requested parent transcript slice for the child fork.
        if mode == "none":
            return []
        if mode == "full":
            return list(self._agent.history)
        last_n = self._coerce_positive_int(raw_last_n, "last_n")
        return list(self._agent.history[-last_n:])

    def _resolve_model(self, raw_model: Any) -> str | None:
        # Enforces the developer model allow-list; empty allow-list disables model swapping.
        model = self._optional_string(raw_model)
        if model is None:
            return None
        if not self._allowed_models:
            raise ValueError("model cannot be changed because no allowed_models were configured.")
        if model not in self._allowed_models:
            raise ValueError(f"model {model!r} is not in the allowed_models list.")
        return model

    def _resolve_provider(self, raw_provider: Any) -> str | None:
        # Validates provider swaps against Vidbyte's provider enum.
        provider = self._optional_string(raw_provider)
        if provider is None:
            return None
        try:
            return ModelProvider(provider).value
        except ValueError as exc:
            allowed = ", ".join(provider.value for provider in ModelProvider)
            raise ValueError(f"provider must be one of: {allowed}.") from exc

    def _resolve_modality(self, raw_modality: Any) -> str | None:
        # Validates modality swaps against Vidbyte's modality enum.
        modality = self._optional_string(raw_modality)
        if modality is None:
            return None
        try:
            return ModelModality(modality).value
        except ValueError as exc:
            allowed = ", ".join(modality.value for modality in ModelModality)
            raise ValueError(f"modality must be one of: {allowed}.") from exc

    def _resolve_temperature(self, raw_temperature: Any) -> float | None:
        # Validates the optional child temperature override.
        if raw_temperature is None:
            return None
        try:
            temperature = float(raw_temperature)
        except (TypeError, ValueError) as exc:
            raise ValueError("temperature must be a number between 0 and 2.") from exc
        if temperature < 0 or temperature > 2:
            raise ValueError("temperature must be between 0 and 2.")
        return temperature

    def _resolve_loop_settings(self, raw_settings: Any, raw_max_iterations: Any, context_window: Mapping[str, Any]) -> AgentLoopSettings | None:
        # Resolves optional loop and context-window budget settings as a merged AgentLoopSettings object.
        settings = self._optional_mapping(raw_settings, "loop_settings")
        if raw_max_iterations is not None:
            settings["max_iterations"] = raw_max_iterations
        if "budget_tokens" in context_window:
            settings["context_window_budget"] = context_window["budget_tokens"]
        if "context_window_budget" in context_window:
            settings["context_window_budget"] = context_window["context_window_budget"]
        if "compaction_trigger_tokens" in context_window:
            settings["compaction_trigger_tokens"] = context_window["compaction_trigger_tokens"]
        if "compaction_target_tokens" in context_window:
            settings["compaction_target_tokens"] = context_window["compaction_target_tokens"]
        if not settings:
            return None
        values = {field: getattr(self._agent.agent_loop_settings, field, None) for field in _LOOP_SETTING_FIELDS}
        for field, value in settings.items():
            if field not in _LOOP_SETTING_FIELDS:
                raise ValueError(f"loop_settings does not support field {field!r}.")
            if field == "timeout_seconds":
                values[field] = self._coerce_positive_float(value, field)
            elif field == "allowed_tools":
                values[field] = self._resolve_allowed_tools(value)
            else:
                values[field] = self._coerce_positive_int(value, field)
        requested = values.get("max_iterations")
        parent_limit = self._agent.agent_loop_settings.max_iterations
        if requested is not None and parent_limit is not None and requested > parent_limit:
            raise ValueError(f"max_iterations cannot exceed the parent cap of {parent_limit}.")
        return AgentLoopSettings(**values)

    def _resolve_allowed_tools(self, raw_allowed_tools: Any) -> tuple[str, ...]:
        # Validates the optional runtime allowed_tools gate against the selectable tool catalog.
        names = self._coerce_string_tuple(raw_allowed_tools, "allowed_tools")
        self._available_tools().subset(names)
        return names

    def _resolve_runtime(self, raw_runtime: Any, raw_actor_runtime: Any) -> str | ActorRuntime | None:
        # Resolves Vidbyte runtime swaps, including structured actor runtime settings.
        actor_settings = self._optional_mapping(raw_actor_runtime, "actor_runtime")
        runtime = self._optional_string(raw_runtime)
        if not actor_settings:
            if runtime is None:
                return None
            try:
                return AgentRuntimeType(runtime).value
            except ValueError as exc:
                allowed = ", ".join(item.value for item in AgentRuntimeType)
                raise ValueError(f"runtime must be one of: {allowed}.") from exc
        topology = self._optional_string(actor_settings.get("topology")) or runtime or AgentRuntimeType.ACTOR_MODEL_P2P.value
        try:
            runtime_type = AgentRuntimeType(topology)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in AgentRuntimeType)
            raise ValueError(f"actor_runtime.topology must be one of: {allowed}.") from exc
        if runtime_type not in (AgentRuntimeType.ACTOR_MODEL, AgentRuntimeType.ACTOR_MODEL_P2P, AgentRuntimeType.ACTOR_MODEL_BROADCAST):
            raise ValueError("actor_runtime can only be used with actor runtime topologies.")
        return ActorRuntime(
            topology=runtime_type,
            dynamic_actors=self._resolve_bool(actor_settings.get("dynamic_actors"), default=False, field_name="actor_runtime.dynamic_actors"),
            max_loop=self._coerce_positive_int(actor_settings.get("max_loop", 20), "actor_runtime.max_loop"),
            termination_mode=self._optional_string(actor_settings.get("termination_mode")) or "coordinator",
            worker_model=self._optional_string(actor_settings.get("worker_model")),
        )

    def _resolve_context_algorithm(self, raw_algorithm: Any) -> str | None:
        # Validates context-window algorithm presets through Vidbyte's resolver.
        algorithm = self._optional_string(raw_algorithm)
        if algorithm is None:
            return None
        try:
            ContextWindow.resolve_algorithm(algorithm)
        except ValueError as exc:
            raise ValueError(f"context_algorithm must be one of: {', '.join(_CONTEXT_ALGORITHM_PRESETS)}.") from exc
        return algorithm

    def _resolve_handoff(self, raw_handoff: Any) -> Handoff | None:
        # Resolves optional Vidbyte handoff presets or a custom sectioned handoff spec.
        if raw_handoff is None:
            return None
        if isinstance(raw_handoff, str):
            raw_handoff = {"preset": raw_handoff}
        if not isinstance(raw_handoff, Mapping):
            raise ValueError("handoff must be an object or preset string when provided.")
        preset = self._optional_string(raw_handoff.get("preset")) or "custom"
        title = self._optional_string(raw_handoff.get("title"))
        instructions = self._optional_string(raw_handoff.get("instructions"))
        metadata = self._resolve_metadata(raw_handoff.get("metadata"))
        if preset == "custom":
            sections = raw_handoff.get("sections")
            if not isinstance(sections, Mapping) or not sections:
                raise ValueError("custom handoff requires a non-empty sections object.")
            return Handoff(
                title=title,
                instructions=instructions,
                sections={str(key): str(value) for key, value in sections.items()},
                metadata=metadata,
            )
        handoff_cls = _HANDOFF_PRESETS.get(preset)
        if handoff_cls is None:
            raise ValueError("handoff.preset must be one of: minimal, engineering, research, custom.")
        kwargs: dict[str, Any] = {"metadata": metadata}
        if title is not None:
            kwargs["title"] = title
        if instructions is not None:
            kwargs["instructions"] = instructions
        if isinstance(raw_handoff.get("sections"), Mapping):
            kwargs["sections"] = {str(key): str(value) for key, value in raw_handoff["sections"].items()}
        return handoff_cls(**kwargs)

    def _enforce_depth_cap(self) -> None:
        # Refuses recursive forks once the inherited fork depth reaches the configured limit.
        depth = int(self._agent.metadata.get("fork_depth", 0) or 0)
        if depth >= self._max_fork_depth:
            raise ValueError(f"fork depth cap reached: {depth} >= {self._max_fork_depth}.")

    def _input_schema(self) -> dict[str, Any]:
        # Returns the JSON Schema for the model-facing fork parameters.
        return {
            "type": "object",
            "required": ["prompt"],
            "additionalProperties": False,
            "properties": {
                "prompt": {"type": "string", "description": "Seed user message for the forked child agent. This is the child branch's task, not a new parent message."},
                "system_prompt": {"type": "string", "description": "Replacement BaseAgent.system_prompt for the child. Omit to inherit the parent's system prompt exactly."},
                "tool_names": {"type": "array", "items": {"type": "string"}, "description": "Exact child tool catalog by model-facing tool name, selected from the parent catalog plus allowed extra toolsets."},
                "extra_toolset_names": {"type": "array", "items": {"type": "string"}, "description": "Named developer-configured extra toolsets to make available to this fork. Omit to allow any configured extra toolset by explicit tool_names."},
                "drop_tool_names": {"type": "array", "items": {"type": "string"}, "description": "Tool names to remove from the selected child catalog after tool_names/extra_toolset_names resolution."},
                "history_mode": {"type": "string", "enum": sorted(_HISTORY_MODES), "default": "full", "description": "Conversation transcript carry mode: full keeps parent history, none starts clean, last_n keeps only the latest N messages."},
                "last_n": {"type": "integer", "minimum": 1, "description": "Number of latest history messages to carry when history_mode is last_n."},
                "context_window": {
                    "type": "object",
                    "additionalProperties": False,
                    "description": "Vidbyte context-window controls for this fork: history slice, algorithm preset, context budget, and compaction thresholds.",
                    "properties": {
                        "history_mode": {"type": "string", "enum": sorted(_HISTORY_MODES), "description": "Same as top-level history_mode, scoped under context_window for SDK-native context edits."},
                        "last_n": {"type": "integer", "minimum": 1, "description": "Same as top-level last_n, scoped under context_window."},
                        "algorithm": {"type": "string", "enum": list(_CONTEXT_ALGORITHM_PRESETS), "description": "ContextWindow preset for the child, such as compact_tool_outputs, reflexion, or trajectory_checkpoints."},
                        "budget_tokens": {"type": "integer", "minimum": 1, "description": "Alias for AgentLoopSettings.context_window_budget."},
                        "context_window_budget": {"type": "integer", "minimum": 1, "description": "Maximum context-window token budget for the child runtime."},
                        "compaction_trigger_tokens": {"type": "integer", "minimum": 1, "description": "Token threshold that triggers context compaction in the child."},
                        "compaction_target_tokens": {"type": "integer", "minimum": 1, "description": "Target token count after compaction; must be below the trigger when both are set."},
                    },
                },
                "context_algorithm": {"type": "string", "enum": list(_CONTEXT_ALGORITHM_PRESETS), "description": "Direct ContextWindow preset override for the child. Prefer context_window.algorithm when grouping context edits."},
                "model": {"type": "string", "description": "Optional model_name override. The value must appear in the developer-configured allowed_models list."},
                "provider": {"type": "string", "enum": [provider.value for provider in ModelProvider], "description": "Optional Vidbyte ModelProvider override. API keys and credentials are still inherited and are never model-controlled."},
                "modality": {"type": "string", "enum": [modality.value for modality in ModelModality], "description": "Optional ModelModality override for the child, such as text, image, video, audio, or embedding."},
                "temperature": {"type": "number", "minimum": 0, "maximum": 2, "description": "Optional child runner temperature override."},
                "runtime": {"type": "string", "enum": [runtime.value for runtime in AgentRuntimeType], "description": "Optional AgentRuntimeType override, such as linear, mcts_search, actor_model_p2p, or actor_model_broadcast."},
                "actor_runtime": {
                    "type": "object",
                    "additionalProperties": False,
                    "description": "Structured ActorRuntime settings for actor_model, actor_model_p2p, or actor_model_broadcast child forks.",
                    "properties": {
                        "topology": {"type": "string", "enum": [AgentRuntimeType.ACTOR_MODEL.value, AgentRuntimeType.ACTOR_MODEL_P2P.value, AgentRuntimeType.ACTOR_MODEL_BROADCAST.value]},
                        "dynamic_actors": {"type": "boolean"},
                        "max_loop": {"type": "integer", "minimum": 1},
                        "termination_mode": {"type": "string", "enum": ["coordinator", "quiescence"]},
                        "worker_model": {"type": "string"},
                    },
                },
                "loop_settings": {
                    "type": "object",
                    "additionalProperties": False,
                    "description": "Complete AgentLoopSettings override surface. Values inherit from the parent unless supplied here.",
                    "properties": {
                        "max_iterations": {"type": "integer", "minimum": 1, "description": "Child loop cap; cannot exceed the parent's configured cap."},
                        "max_tokens": {"type": "integer", "minimum": 1, "description": "Maximum generated/runtime tokens for the child loop."},
                        "max_tool_calls": {"type": "integer", "minimum": 1, "description": "Total child tool-call budget."},
                        "max_parallel_tool_calls": {"type": "integer", "minimum": 1, "description": "Parallel tool-call fanout cap for child loop iterations."},
                        "max_retries": {"type": "integer", "minimum": 1, "description": "Retry budget for recoverable child runtime failures."},
                        "timeout_seconds": {"type": "number", "exclusiveMinimum": 0, "description": "Wall-clock timeout for child loop execution."},
                        "context_window_budget": {"type": "integer", "minimum": 1, "description": "Maximum context-window token budget for the child."},
                        "compaction_trigger_tokens": {"type": "integer", "minimum": 1, "description": "Token threshold that triggers child context compaction."},
                        "compaction_target_tokens": {"type": "integer", "minimum": 1, "description": "Target token count after child context compaction."},
                        "allowed_tools": {"type": "array", "items": {"type": "string"}, "description": "Runtime-level allowed_tools gate for the child; each name must be in the selectable child tool catalog."},
                    },
                },
                "max_iterations": {"type": "integer", "minimum": 1, "description": "Convenience alias for loop_settings.max_iterations; cannot exceed the parent cap."},
                "handoff": {
                    "type": ["object", "string"],
                    "description": "Optional Vidbyte handoff spec for the child. Use preset minimal, engineering, research, or custom sections.",
                    "properties": {
                        "preset": {"type": "string", "enum": ["minimal", "engineering", "research", "custom"]},
                        "title": {"type": "string"},
                        "instructions": {"type": "string"},
                        "sections": {"type": "object", "additionalProperties": {"type": "string"}},
                        "metadata": {"type": "object"},
                    },
                },
                "output_schema": {"type": "object", "description": "Optional structured output schema mapping for the child runtime."},
                "runner_options": {"type": "object", "description": "Optional JSON-serializable runner options for the child runner config."},
                "include_run_state": {"type": "boolean", "default": False, "description": "When true, carry handoffs and prior tool-call contexts into the child lifecycle state."},
                "mcp": {"type": "boolean", "default": True, "description": "Whether to carry MCP server configs as pending child attachments without sharing live parent handles."},
                "metadata": {"type": "object", "description": "Additional child metadata merged with fork lineage metadata."},
                "run_id": {"type": "string", "description": "Optional explicit child run_id. Omit to let Vidbyte create a fresh fork run_id."},
                "name": {"type": "string", "description": "Optional child BaseAgent.name label."},
                "purpose": {"type": "string", "description": "Optional reason stored as fork_purpose in child metadata for trace observability."},
            },
        }

    @staticmethod
    def _optional_mapping(value: Any, field_name: str) -> dict[str, Any]:
        # Converts optional JSON objects into mutable dictionaries.
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ValueError(f"{field_name} must be an object when provided.")
        return dict(value)

    def _resolve_json_object(self, value: Any, field_name: str) -> dict[str, Any] | None:
        # Validates an optional JSON-like object field.
        if value is None:
            return None
        return self._optional_mapping(value, field_name)

    def _resolve_metadata(self, value: Any) -> dict[str, Any]:
        # Validates optional metadata payloads.
        return self._optional_mapping(value, "metadata")

    @staticmethod
    def _resolve_bool(value: Any, *, default: bool, field_name: str) -> bool:
        # Validates optional boolean fields without accepting stringly truthiness.
        if value is None:
            return default
        if not isinstance(value, bool):
            raise ValueError(f"{field_name} must be a boolean when provided.")
        return value

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        # Converts optional JSON values into stripped strings, treating blanks as absent.
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _coerce_positive_int(value: Any, field_name: str) -> int:
        # Converts a JSON value to a strictly positive integer for bounded fork settings.
        try:
            integer = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be a positive integer.") from exc
        if integer <= 0:
            raise ValueError(f"{field_name} must be a positive integer.")
        return integer

    @staticmethod
    def _coerce_positive_float(value: Any, field_name: str) -> float:
        # Converts a JSON value to a strictly positive float for timeout settings.
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be a positive number.") from exc
        if number <= 0:
            raise ValueError(f"{field_name} must be a positive number.")
        return number

    @staticmethod
    def _normalize_extra_toolsets(extra_toolsets: Mapping[str, Tools | Sequence[object]] | None) -> dict[str, Tools]:
        # Normalizes developer-supplied extra toolsets into immutable Tools catalogs.
        return {str(name): toolset if isinstance(toolset, Tools) else Tools(toolset) for name, toolset in dict(extra_toolsets or {}).items()}


__all__ = ["ForkConversationTool"]

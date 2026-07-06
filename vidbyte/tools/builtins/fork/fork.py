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
        def describe(prop_name: str, is_text: str, does_text: str) -> str:
            return f"{prop_name} is {is_text}. {prop_name} does {does_text}."

        return {
            "type": "object",
            "required": ["prompt"],
            "additionalProperties": False,
            "properties": {
                "prompt": {"type": "string", "description": describe("prompt", "the required task message for the forked child agent", "seed the child branch with a focused instruction while leaving the parent conversation untouched")},
                "system_prompt": {"type": "string", "description": describe("system_prompt", "an optional replacement for the child agent's BaseAgent.system_prompt", "change the child's role, constraints, or operating instructions without changing the parent agent")},
                "tool_names": {"type": "array", "items": {"type": "string"}, "description": describe("tool_names", "an optional exact list of model-facing tool names for the child", "select the child's tool catalog from the parent tools plus any allowed extra toolsets")},
                "extra_toolset_names": {"type": "array", "items": {"type": "string"}, "description": describe("extra_toolset_names", "an optional list of developer-configured toolset names", "make those extra toolsets available to the child fork without letting the model create new permissions")},
                "drop_tool_names": {"type": "array", "items": {"type": "string"}, "description": describe("drop_tool_names", "an optional list of selected child tools to remove by name", "subtract tools after tool_names and extra_toolset_names are resolved so the child can run with a narrower catalog")},
                "history_mode": {"type": "string", "enum": sorted(_HISTORY_MODES), "default": "full", "description": describe("history_mode", "the transcript carry mode for the child fork", "choose whether the child receives the full parent history, no parent history, or only the latest last_n messages")},
                "last_n": {"type": "integer", "minimum": 1, "description": describe("last_n", "the number of most recent parent messages to carry when history_mode is last_n", "bound the child context to a small recent slice instead of the full transcript")},
                "context_window": {
                    "type": "object",
                    "additionalProperties": False,
                    "description": describe("context_window", "the Vidbyte SDK control group for the child agent's working context", "set how much parent history the child sees, which context-window algorithm it uses, and when token-budget compaction should run"),
                    "properties": {
                        "history_mode": {"type": "string", "enum": sorted(_HISTORY_MODES), "description": describe("context_window.history_mode", "the context_window-scoped transcript carry mode", "mirror history_mode inside the context_window object when grouping history and budget decisions together")},
                        "last_n": {"type": "integer", "minimum": 1, "description": describe("context_window.last_n", "the context_window-scoped count of recent parent messages to carry", "limit the child to the latest N messages when context_window.history_mode is last_n")},
                        "algorithm": {"type": "string", "enum": list(_CONTEXT_ALGORITHM_PRESETS), "description": describe("context_window.algorithm", "a Vidbyte SDK context-window algorithm preset for preparing the child's prompt context", "choose how the child keeps, compacts, hides, grades, checkpoints, or corrects prior context before it reasons")},
                        "budget_tokens": {"type": "integer", "minimum": 1, "description": describe("context_window.budget_tokens", "a short alias for AgentLoopSettings.context_window_budget", "set the maximum child context budget in tokens without writing the longer field name")},
                        "context_window_budget": {"type": "integer", "minimum": 1, "description": describe("context_window.context_window_budget", "the maximum token budget for the child agent's working context", "cap how much conversation, tool output, and supporting context the child may keep active")},
                        "compaction_trigger_tokens": {"type": "integer", "minimum": 1, "description": describe("context_window.compaction_trigger_tokens", "the token threshold where the child should compact its context", "start context reduction before the child exceeds its available context window")},
                        "compaction_target_tokens": {"type": "integer", "minimum": 1, "description": describe("context_window.compaction_target_tokens", "the target token count after child context compaction", "tell the compactor how small the working context should become after compaction runs")},
                    },
                },
                "context_algorithm": {"type": "string", "enum": list(_CONTEXT_ALGORITHM_PRESETS), "description": describe("context_algorithm", "a direct Vidbyte SDK ContextWindow preset override for the child", "choose the child's context preparation behavior without wrapping it in the context_window object")},
                "model": {"type": "string", "description": describe("model", "an optional child model_name override from the developer-configured allow-list", "switch the child to an approved model while preserving inherited credentials and permission policy")},
                "provider": {"type": "string", "enum": [provider.value for provider in ModelProvider], "description": describe("provider", "an optional Vidbyte ModelProvider override for the child runner", "route the child through a different approved provider while still inheriting credentials from the parent environment")},
                "modality": {"type": "string", "enum": [modality.value for modality in ModelModality], "description": describe("modality", "an optional ModelModality override such as text, image, video, audio, or embedding", "tell the child which kind of model runner should handle its task")},
                "temperature": {"type": "number", "minimum": 0, "maximum": 2, "description": describe("temperature", "an optional child runner sampling temperature between 0 and 2", "make the child more deterministic at lower values or more exploratory at higher values")},
                "runtime": {"type": "string", "enum": [runtime.value for runtime in AgentRuntimeType], "description": describe("runtime", "an optional Vidbyte AgentRuntimeType override such as linear, mcts_search, actor_model_p2p, or actor_model_broadcast", "choose the execution strategy the child uses to plan, call tools, coordinate actors, or search")},
                "actor_runtime": {
                    "type": "object",
                    "additionalProperties": False,
                    "description": describe("actor_runtime", "the structured configuration object for Vidbyte actor-model child runtimes", "configure actor topology, worker behavior, loop limits, and termination when runtime selects an actor mode"),
                    "properties": {
                        "topology": {"type": "string", "enum": [AgentRuntimeType.ACTOR_MODEL.value, AgentRuntimeType.ACTOR_MODEL_P2P.value, AgentRuntimeType.ACTOR_MODEL_BROADCAST.value], "description": describe("actor_runtime.topology", "the actor runtime communication pattern for the child", "choose whether child actors are coordinated centrally, peer-to-peer, or through broadcast coordination")},
                        "dynamic_actors": {"type": "boolean", "description": describe("actor_runtime.dynamic_actors", "a boolean switch for allowing the child actor runtime to create actors dynamically", "let the child expand its actor set during execution when the selected actor runtime supports it")},
                        "max_loop": {"type": "integer", "minimum": 1, "description": describe("actor_runtime.max_loop", "the maximum number of actor coordination loops for the child", "bound how many rounds the child actor runtime may run before stopping")},
                        "termination_mode": {"type": "string", "enum": ["coordinator", "quiescence"], "description": describe("actor_runtime.termination_mode", "the stopping policy for the child actor runtime", "decide whether a coordinator ends the run or the run ends after actors become idle")},
                        "worker_model": {"type": "string", "description": describe("actor_runtime.worker_model", "an optional model name for child actor workers", "let worker actors use a separate approved model from the coordinator when the runtime supports that split")},
                    },
                },
                "loop_settings": {
                    "type": "object",
                    "additionalProperties": False,
                    "description": describe("loop_settings", "the AgentLoopSettings override object for the child fork", "set child loop limits, retry limits, tool-call limits, timeouts, and context budgets while inheriting omitted values from the parent"),
                    "properties": {
                        "max_iterations": {"type": "integer", "minimum": 1, "description": describe("loop_settings.max_iterations", "the maximum number of agent loop iterations for the child", "cap child reasoning and tool-use rounds without allowing a value above the parent cap")},
                        "max_tokens": {"type": "integer", "minimum": 1, "description": describe("loop_settings.max_tokens", "the maximum token budget for child generation or runtime output", "limit how many tokens the child can spend while answering the fork prompt")},
                        "max_tool_calls": {"type": "integer", "minimum": 1, "description": describe("loop_settings.max_tool_calls", "the total tool-call budget for the child loop", "stop the child from using more tools than the requested limit")},
                        "max_parallel_tool_calls": {"type": "integer", "minimum": 1, "description": describe("loop_settings.max_parallel_tool_calls", "the maximum number of tool calls the child can launch in one parallel batch", "control child tool fanout during a single loop iteration")},
                        "max_retries": {"type": "integer", "minimum": 1, "description": describe("loop_settings.max_retries", "the retry budget for recoverable child runtime failures", "bound how many times the child may retry failed model or tool operations")},
                        "timeout_seconds": {"type": "number", "exclusiveMinimum": 0, "description": describe("loop_settings.timeout_seconds", "the wall-clock timeout for child loop execution", "stop the child run if it takes longer than the configured number of seconds")},
                        "context_window_budget": {"type": "integer", "minimum": 1, "description": describe("loop_settings.context_window_budget", "the maximum token budget for the child agent's active context window", "limit how much history, tool output, and support material the child can keep available")},
                        "compaction_trigger_tokens": {"type": "integer", "minimum": 1, "description": describe("loop_settings.compaction_trigger_tokens", "the active-context token count that triggers child compaction", "start reducing the child context before it exceeds the configured window budget")},
                        "compaction_target_tokens": {"type": "integer", "minimum": 1, "description": describe("loop_settings.compaction_target_tokens", "the desired token count after child context compaction", "give the compaction algorithm a target size for the reduced child context")},
                        "allowed_tools": {"type": "array", "items": {"type": "string"}, "description": describe("loop_settings.allowed_tools", "a runtime-level allow-list of tool names for the child", "enforce a final tool-use gate after the child tool catalog has been selected")},
                    },
                },
                "max_iterations": {"type": "integer", "minimum": 1, "description": describe("max_iterations", "a convenience alias for loop_settings.max_iterations", "cap child loop iterations without requiring a full loop_settings object")},
                "handoff": {
                    "type": ["object", "string"],
                    "description": describe("handoff", "an optional Vidbyte handoff preset name or custom sectioned handoff object for the child", "shape what context the child returns or organizes when handing work back to the parent"),
                    "properties": {
                        "preset": {"type": "string", "enum": ["minimal", "engineering", "research", "custom"], "description": describe("handoff.preset", "the named Vidbyte handoff template for the child", "choose minimal, engineering, research, or custom return structure")},
                        "title": {"type": "string", "description": describe("handoff.title", "an optional title for the child handoff", "label the returned handoff so the parent can identify the child branch's deliverable")},
                        "instructions": {"type": "string", "description": describe("handoff.instructions", "optional child-specific handoff instructions", "tell the child how to organize or phrase the handoff it returns")},
                        "sections": {"type": "object", "additionalProperties": {"type": "string"}, "description": describe("handoff.sections", "the custom named sections for a custom child handoff", "define the exact fields the child should fill when it returns structured context")},
                        "metadata": {"type": "object", "description": describe("handoff.metadata", "optional metadata attached to the child handoff object", "carry non-secret labels or routing details alongside the handoff")},
                    },
                },
                "output_schema": {"type": "object", "description": describe("output_schema", "an optional structured-output schema object for the child runtime", "ask the child to return data in a specific JSON-compatible shape when the runtime supports structured output")},
                "runner_options": {"type": "object", "description": describe("runner_options", "an optional JSON-serializable options object for the child runner config", "pass runner-specific settings to the child without changing parent runner options")},
                "include_run_state": {"type": "boolean", "default": False, "description": describe("include_run_state", "a boolean switch for carrying parent lifecycle state into the child", "include prior handoffs and tool-call contexts when the child needs continuity beyond transcript history")},
                "mcp": {"type": "boolean", "default": True, "description": describe("mcp", "a boolean switch for carrying parent MCP server configs into the child", "attach MCP configs as pending child attachments without sharing live parent handles")},
                "metadata": {"type": "object", "description": describe("metadata", "an optional object of child metadata fields", "merge caller-provided labels with fork lineage metadata for trace and debugging use")},
                "run_id": {"type": "string", "description": describe("run_id", "an optional explicit run identifier for the child", "override the fresh fork run_id when the developer needs a known trace identifier")},
                "name": {"type": "string", "description": describe("name", "an optional BaseAgent.name label for the child", "make the forked child identifiable in traces, logs, and returned metadata")},
                "purpose": {"type": "string", "description": describe("purpose", "an optional plain-language reason for creating the child fork", "store the reason as fork_purpose metadata so trace readers can understand why the branch exists")},
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

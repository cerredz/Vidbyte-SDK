"""Context Protocol Header

Description:
    Implements ForkConversationTool, an agent-bound builtin for self-forking.
Purpose:
    Lets an agent run a modified child copy of its current conversation and
    receive the child answer as a normal tool result.
Architecture:
    - ForkConversationTool: Validates model-facing fork parameters, enforces
      non-escalation, calls BaseAgent.fork(), and awaits the child reply.
Relations:
    Bound by BaseAgent._bind_agent_tool_context. Uses BaseAgent.fork and Tools.
Similar Files:
    - vidbyte/tools/builtins/handoff/create.py: Canonical agent-bound builtin.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.tools.base import BaseTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

_TOOL_NAME = "fork_conversation"
_HISTORY_MODES = {"full", "none", "last_n"}
_STATIC_DESCRIPTION = """\
Fork the current conversation into a modified child agent, run that child on a focused prompt, and return \
the child answer here. Use this when you need to isolate a subtask, compare an alternate system prompt, \
try a smaller allowed model, or restrict the child to a narrower tool set without polluting the parent run.

You cannot grant yourself new privileges with this tool. Tool choices must be selected from the parent \
tool catalog or developer-configured extra toolsets, model changes must be allow-listed by the developer, \
max_iterations cannot exceed the parent's configured cap, and permission policy and credentials are \
always inherited.
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
        history_mode = str(args.get("history_mode", "full")).strip() or "full"
        if history_mode not in _HISTORY_MODES:
            raise ValueError("history_mode must be one of: full, none, last_n.")
        request = {
            "prompt": prompt,
            "system_prompt": self._optional_string(args.get("system_prompt")),
            "tools": self._resolve_tools(args.get("tool_names")),
            "history": self._resolve_history(history_mode, args.get("last_n")),
            "model": self._resolve_model(args.get("model")),
            "temperature": self._resolve_temperature(args.get("temperature")),
            "max_iterations": self._resolve_max_iterations(args.get("max_iterations")),
            "name": self._optional_string(args.get("name")),
            "purpose": self._optional_string(args.get("purpose")),
        }
        return request

    def _build_child(self, request: Mapping[str, Any]) -> Any:
        # Translates normalized request values into a single BaseAgent.fork call.
        metadata = {"fork_purpose": request["purpose"]} if request.get("purpose") else {}
        return self._agent.fork(
            name=request.get("name"),
            system_prompt=request.get("system_prompt"),
            tools=request.get("tools"),
            history=request.get("history"),
            model_name=request.get("model"),
            temperature=request.get("temperature"),
            max_iterations=request.get("max_iterations"),
            metadata=metadata,
        )

    def _build_success(self, child: Any, output: str) -> ToolResult:
        # Builds the successful tool result with child lineage metadata.
        metadata = {
            "child_run_id": child.runner_config.run_id,
            "forked_from": child.metadata.get("forked_from"),
            "fork_depth": child.metadata.get("fork_depth"),
            "name": child.name,
        }
        return ToolResult.success(_TOOL_NAME, output, metadata=metadata)

    def _resolve_tools(self, raw_names: Any) -> Tools | None:
        # Resolves optional tool_names against parent tools plus developer-configured extra toolsets.
        if raw_names is None:
            return None
        if not isinstance(raw_names, Sequence) or isinstance(raw_names, (str, bytes)):
            raise ValueError("tool_names must be an array of strings when provided.")
        names = tuple(str(name) for name in raw_names)
        return self._available_tools().subset(names)

    def _available_tools(self) -> Tools:
        # Builds the non-escalating selectable catalog from parent tools and configured extras.
        catalog = self._agent.tools
        for toolset in self._extra_toolsets.values():
            catalog = catalog.extend(toolset.all(), replace=True)
        return catalog

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

    def _resolve_max_iterations(self, raw_max_iterations: Any) -> int | None:
        # Caps optional child loop iterations at the parent's configured limit when present.
        if raw_max_iterations is None:
            return None
        requested = self._coerce_positive_int(raw_max_iterations, "max_iterations")
        parent_limit = self._agent.agent_loop_settings.max_iterations
        if parent_limit is not None and requested > parent_limit:
            raise ValueError(f"max_iterations cannot exceed the parent cap of {parent_limit}.")
        return requested

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
                "prompt": {"type": "string", "description": "Seed user message for the forked child agent."},
                "system_prompt": {"type": "string", "description": "Optional replacement system prompt for the child."},
                "tool_names": {"type": "array", "items": {"type": "string"}, "description": "Optional exact child tool subset by name."},
                "history_mode": {"type": "string", "enum": sorted(_HISTORY_MODES), "default": "full", "description": "Transcript carry mode."},
                "last_n": {"type": "integer", "description": "Required when history_mode is last_n."},
                "model": {"type": "string", "description": "Optional model override from the developer allow-list."},
                "temperature": {"type": "number", "minimum": 0, "maximum": 2, "description": "Optional child temperature override."},
                "max_iterations": {"type": "integer", "minimum": 1, "description": "Optional child loop cap no greater than the parent cap."},
                "name": {"type": "string", "description": "Optional child agent label."},
                "purpose": {"type": "string", "description": "Optional reason stored in child metadata for trace observability."},
            },
        }

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
    def _normalize_extra_toolsets(extra_toolsets: Mapping[str, Tools | Sequence[object]] | None) -> dict[str, Tools]:
        # Normalizes developer-supplied extra toolsets into immutable Tools catalogs.
        return {str(name): toolset if isinstance(toolset, Tools) else Tools(toolset) for name, toolset in dict(extra_toolsets or {}).items()}


__all__ = ["ForkConversationTool"]

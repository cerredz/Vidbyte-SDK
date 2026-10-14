"""FILE: vidbyte/tools/builtins/codex/threads.py

PURPOSE: The five CodexHost tools about threads: spawn_codex_thread, continue_codex_thread and fork_codex_thread, which start or change paid Codex work, and list_codex_threads and read_codex_thread, which only read.
ROLE IN CODEBASE: Part of vidbyte/tools/builtins/codex/; CodexHostTools lists these after the readiness tools, in the order of the CodexHost functions.
ARCHITECTURE NOTE: The posture of every thread and turn, its sandbox, approvals, folder, configuration, instructions and dynamic tools, comes only from the developer's spawn_defaults; the model sets only the six values the spawn and continue schemas expose (INV-34). Spawn and continue hold a cap slot while the host starts the turn.
COMMON MODIFICATION PATTERNS: A new model-settable value is one schema property, one resolve_ call and one field replaced on the request; anything else belongs in spawn_defaults.
KNOWN EDGE CASES: JSON null means omitted, so a null value keeps the developer's default (EC-53). Continue clears every field continue cannot apply from the defaults, so a posture built for spawn still works for continue.
RELATED DOCS: docs/spec/codex-host/spec.md (section 9.2 tool table, rows 4 to 8, and the per-operation field rules)
TESTS: tests/features/codex_host/test_codex_host_tools.py
"""

from __future__ import annotations

from dataclasses import replace

from vidbyte.lib.constants.codex import (
    CODEX_HOST_MIN_EXCLUSIVE_SECONDS,
    CODEX_HOST_MIN_TOKEN_LIMIT,
)
from vidbyte.lib.dataclasses.codex_host import CodexGoal, CodexSpawnRequest
from vidbyte.lib.enums.codex import (
    CodexHostOperation,
    CodexReasoningEffort,
    CodexSortDirection,
    CodexThreadSortKey,
    CodexThreadSource,
    CodexThreadSourceKind,
    CodexThreadStartSource,
)
from vidbyte.lib.errors import ToolExecutionError
from vidbyte.tools.builtins.codex._base import _CodexHostTool
from vidbyte.tools.builtins.codex.descriptions import (
    ARCHIVED_DESCRIPTION,
    CONTINUE_CODEX_THREAD_DESCRIPTION,
    CONTINUE_MODEL_DESCRIPTION,
    CONTINUE_PROMPT_DESCRIPTION,
    CURSOR_DESCRIPTION,
    CWD_DESCRIPTION,
    EFFORT_DESCRIPTION,
    EXCLUDE_TURNS_DESCRIPTION,
    FORK_CODEX_THREAD_DESCRIPTION,
    FROM_TURN_ID_DESCRIPTION,
    GOAL_OBJECTIVE_DESCRIPTION,
    INCLUDE_TURNS_DESCRIPTION,
    LIST_CODEX_THREADS_DESCRIPTION,
    MAX_OUTPUT_TOKENS_DESCRIPTION,
    OUTPUT_SCHEMA_DESCRIPTION,
    READ_CODEX_THREAD_DESCRIPTION,
    SEARCH_DESCRIPTION,
    SORT_DESCRIPTION,
    SORT_DIRECTION_DESCRIPTION,
    SOURCE_KINDS_DESCRIPTION,
    SPAWN_CODEX_THREAD_DESCRIPTION,
    SPAWN_GOAL_BUDGET_DESCRIPTION,
    SPAWN_MODEL_DESCRIPTION,
    SPAWN_PROMPT_DESCRIPTION,
    THREAD_ID_DESCRIPTION,
    THREAD_NAME_DESCRIPTION,
    TURN_TIMEOUT_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

SPAWN = CodexHostOperation.SPAWN_CODEX_THREAD
CONTINUE = CodexHostOperation.CONTINUE_CODEX_THREAD
FORK = CodexHostOperation.FORK_CODEX_THREAD
LIST = CodexHostOperation.LIST_CODEX_THREADS
READ = CodexHostOperation.READ_CODEX_THREAD
ONE_TURN = 1
EFFORTS = [member.value for member in CodexReasoningEffort if member.value]
SOURCE_KINDS = [member.value for member in CodexThreadSourceKind]
SORT_KEYS = [member.value for member in CodexThreadSortKey if member.value]
SORT_DIRECTIONS = [member.value for member in CodexSortDirection if member.value]
EXACTLY_ONE_MESSAGE = "Pass exactly one of 'prompt' and 'goal_objective'."
BUDGET_WITHOUT_GOAL_MESSAGE = "'goal_token_budget' applies only together with 'goal_objective'."


class SpawnCodexThreadTool(_CodexHostTool):
    """Starts a new Codex thread with its first turn or goal run, under the developer's posture."""

    def spec(self) -> ToolSpec:
        # Only the prompt or goal and six turn values are the model's.
        return ToolSpec(
            name=SPAWN.value,
            description=SPAWN_CODEX_THREAD_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "prompt": {"type": "string", "description": SPAWN_PROMPT_DESCRIPTION},
                    "goal_objective": {"type": "string", "description": GOAL_OBJECTIVE_DESCRIPTION},
                    "goal_token_budget": {"type": "integer", "minimum": CODEX_HOST_MIN_TOKEN_LIMIT, "description": SPAWN_GOAL_BUDGET_DESCRIPTION},
                    "model": {"type": "string", "description": SPAWN_MODEL_DESCRIPTION},
                    "effort": {"type": "string", "enum": EFFORTS, "description": EFFORT_DESCRIPTION},
                    "name": {"type": "string", "description": THREAD_NAME_DESCRIPTION},
                    "max_output_tokens": {"type": "integer", "minimum": CODEX_HOST_MIN_TOKEN_LIMIT, "description": MAX_OUTPUT_TOKENS_DESCRIPTION},
                    "timeout_seconds": {"type": "number", "exclusiveMinimum": CODEX_HOST_MIN_EXCLUSIVE_SECONDS, "description": TURN_TIMEOUT_DESCRIPTION},
                    "output_schema": {"type": "object", "description": OUTPUT_SCHEMA_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the new turn's handle as JSON.
        return await self._run(SPAWN.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # @intent one-instruction-per-spawn
        # Read the model's values: exactly one of a prompt and a goal
        # objective, because a goal replaces the prompt, and a goal
        # budget only with an objective.
        prompt = self._resolve_text(call, "prompt")
        objective = self._resolve_text(call, "goal_objective")
        budget = self._resolve_count(call, "goal_token_budget")
        if bool(prompt) == bool(objective):
            raise ToolExecutionError(EXACTLY_ONE_MESSAGE, details={"parameter": "prompt"})
        if budget is not None and not objective:
            raise ToolExecutionError(BUDGET_WITHOUT_GOAL_MESSAGE, details={"parameter": "goal_token_budget"})
        model = self._resolve_text(call, "model")
        effort = self._resolve_choice(call, "effort", CodexReasoningEffort)
        name = self._resolve_text(call, "name")
        max_output_tokens = self._resolve_count(call, "max_output_tokens")
        timeout_seconds = self._resolve_seconds(call, "timeout_seconds")
        output_schema = self._resolve_schema(call, "output_schema")
        # Lay the model's values over the developer's posture; an omitted
        # value keeps the developer's default.
        defaults = self._scope.spawn_defaults
        request = replace(
            defaults,
            prompt=prompt,
            goal=CodexGoal(objective=objective, token_budget=budget) if objective else None,
            thread=replace(defaults.thread, model=model) if model else defaults.thread,
            turn=replace(defaults.turn, effort=effort) if effort is not None else defaults.turn,
            name=name or defaults.name,
            max_output_tokens=max_output_tokens if max_output_tokens is not None else defaults.max_output_tokens,
            timeout_seconds=timeout_seconds if timeout_seconds is not None else defaults.timeout_seconds,
            output_schema=output_schema if output_schema is not None else defaults.output_schema,
        )
        # Hold one cap slot while the host starts the turn.
        await self._scope.reserve(self._host, ONE_TURN, SPAWN)
        try:
            handle = await self._host.spawn_codex_thread(request)
        finally:
            self._scope.release(ONE_TURN)
        self._scope.own((handle,))
        return self._json(handle)


class ContinueCodexThreadTool(_CodexHostTool):
    """Starts one more turn on any existing Codex thread, under the developer's posture."""

    def spec(self) -> ToolSpec:
        # The thread, the prompt, and four turn values are the model's.
        return ToolSpec(
            name=CONTINUE.value,
            description=CONTINUE_CODEX_THREAD_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["thread_id", "prompt"],
                "properties": {
                    "thread_id": {"type": "string", "description": THREAD_ID_DESCRIPTION},
                    "prompt": {"type": "string", "description": CONTINUE_PROMPT_DESCRIPTION},
                    "model": {"type": "string", "description": CONTINUE_MODEL_DESCRIPTION},
                    "effort": {"type": "string", "enum": EFFORTS, "description": EFFORT_DESCRIPTION},
                    "max_output_tokens": {"type": "integer", "minimum": CODEX_HOST_MIN_TOKEN_LIMIT, "description": MAX_OUTPUT_TOKENS_DESCRIPTION},
                    "timeout_seconds": {"type": "number", "exclusiveMinimum": CODEX_HOST_MIN_EXCLUSIVE_SECONDS, "description": TURN_TIMEOUT_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the new turn's handle as JSON.
        return await self._run(CONTINUE.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Read the model's values.
        thread_id = self._resolve_text(call, "thread_id", required=True)
        prompt = self._resolve_text(call, "prompt", required=True)
        model = self._resolve_text(call, "model")
        effort = self._resolve_choice(call, "effort", CodexReasoningEffort)
        max_output_tokens = self._resolve_count(call, "max_output_tokens")
        timeout_seconds = self._resolve_seconds(call, "timeout_seconds")
        # The overrides are the developer's posture with every field
        # continue cannot apply cleared, plus the model's turn values.
        base = self._continue_defaults(self._scope.spawn_defaults)
        overrides = replace(
            base,
            turn=replace(base.turn, model=model or base.turn.model, effort=effort if effort is not None else base.turn.effort),
            max_output_tokens=max_output_tokens if max_output_tokens is not None else base.max_output_tokens,
            timeout_seconds=timeout_seconds if timeout_seconds is not None else base.timeout_seconds,
        )
        # Hold one cap slot while the host starts the turn.
        await self._scope.reserve(self._host, ONE_TURN, CONTINUE)
        try:
            handle = await self._host.continue_codex_thread(thread_id, prompt, overrides=overrides)
        finally:
            self._scope.release(ONE_TURN)
        self._scope.own((handle,))
        return self._json(handle)

    @staticmethod
    def _continue_defaults(defaults: CodexSpawnRequest) -> CodexSpawnRequest:
        # @intent continue-drops-new-thread-fields
        # Continue rejects a prompt, a goal, tools, a name, and the
        # thread fields only a new thread takes (section 9.2 field
        # rules), so the developer's spawn defaults are cleared of them.
        thread = replace(
            defaults.thread,
            ephemeral=False,
            thread_source=CodexThreadSource.PROVIDER_DEFAULT,
            service_name="",
            session_start_source=CodexThreadStartSource.PROVIDER_DEFAULT,
        )
        return replace(defaults, prompt="", goal=None, tools=(), name="", thread=thread)


class ForkCodexThreadTool(_CodexHostTool):
    """Copies a Codex thread into a new thread through one of its completed turns."""

    def spec(self) -> ToolSpec:
        # The thread, the fork point and the answer's shape; no overrides.
        return ToolSpec(
            name=FORK.value,
            description=FORK_CODEX_THREAD_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["thread_id"],
                "properties": {
                    "thread_id": {"type": "string", "description": THREAD_ID_DESCRIPTION},
                    "from_turn_id": {"type": "string", "description": FROM_TURN_ID_DESCRIPTION},
                    "exclude_turns": {"type": "boolean", "description": EXCLUDE_TURNS_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the new thread as JSON.
        return await self._run(FORK.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # The fork inherits everything from its parent, so no overrides.
        thread_id = self._resolve_text(call, "thread_id", required=True)
        from_turn_id = self._resolve_text(call, "from_turn_id")
        exclude_turns = self._resolve_bool_argument(call, "exclude_turns", default=False)
        info = await self._host.fork_codex_thread(thread_id, from_turn_id=from_turn_id, exclude_turns=exclude_turns, overrides=None)
        return self._json(info)


class ListCodexThreadsTool(_CodexHostTool):
    """Lists one page of the stored Codex threads of the account."""

    def spec(self) -> ToolSpec:
        # Every filter is optional; empty ones are left out.
        return ToolSpec(
            name=LIST.value,
            description=LIST_CODEX_THREADS_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "cwd": {"type": "string", "description": CWD_DESCRIPTION},
                    "search": {"type": "string", "description": SEARCH_DESCRIPTION},
                    "archived": {"type": "boolean", "description": ARCHIVED_DESCRIPTION},
                    "source_kinds": {"type": "array", "items": {"type": "string", "enum": SOURCE_KINDS}, "description": SOURCE_KINDS_DESCRIPTION},
                    "sort": {"type": "string", "enum": SORT_KEYS, "description": SORT_DESCRIPTION},
                    "sort_direction": {"type": "string", "enum": SORT_DIRECTIONS, "description": SORT_DIRECTION_DESCRIPTION},
                    "cursor": {"type": "string", "description": CURSOR_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the page as JSON.
        return await self._run(LIST.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # @intent omitted-filters-keep-codex-defaults
        # Read each filter, then list one page; a filter the model left
        # out keeps Codex's own default.
        page = await self._host.list_codex_threads(
            cwd=self._resolve_text(call, "cwd"),
            search=self._resolve_text(call, "search"),
            archived=self._resolve_bool_argument(call, "archived", default=False),
            source_kinds=self._resolve_choices(call, "source_kinds", CodexThreadSourceKind),
            sort=self._resolve_choice(call, "sort", CodexThreadSortKey) or CodexThreadSortKey.PROVIDER_DEFAULT,
            sort_direction=self._resolve_choice(call, "sort_direction", CodexSortDirection) or CodexSortDirection.PROVIDER_DEFAULT,
            cursor=self._resolve_text(call, "cursor"),
        )
        return self._json(page)


class ReadCodexThreadTool(_CodexHostTool):
    """Reads one stored Codex thread, with its turn summaries when asked."""

    def spec(self) -> ToolSpec:
        # Any thread id, and an optional switch for the turns.
        return ToolSpec(
            name=READ.value,
            description=READ_CODEX_THREAD_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["thread_id"],
                "properties": {
                    "thread_id": {"type": "string", "description": THREAD_ID_DESCRIPTION},
                    "include_turns": {"type": "boolean", "description": INCLUDE_TURNS_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the thread as JSON.
        return await self._run(READ.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Read the arguments, then the thread.
        thread_id = self._resolve_text(call, "thread_id", required=True)
        include_turns = self._resolve_bool_argument(call, "include_turns", default=False)
        return self._json(await self._host.read_codex_thread(thread_id, include_turns=include_turns))


__all__ = [
    "ContinueCodexThreadTool",
    "ForkCodexThreadTool",
    "ListCodexThreadsTool",
    "ReadCodexThreadTool",
    "SpawnCodexThreadTool",
]

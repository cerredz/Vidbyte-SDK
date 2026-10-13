"""FILE: vidbyte/tools/builtins/claude/sessions.py

PURPOSE: Defines the four WRITE tools that start Claude Code work: SpawnClaudeSessionTool, ContinueClaudeSessionTool, ForkClaudeSessionTool and LaunchClaudeSubagentsTool.
ROLE IN CODEBASE: Built by ClaudeTools (vidbyte/tools/toolsets/claude.py) and exported by vidbyte/tools/builtins/claude/__init__.py. Each tool calls one ClaudeHost method: spawn_claude_session, continue_claude_session, fork_claude_session or launch_claude_subagents.
ARCHITECTURE NOTE: The model supplies only prompts, session ids, a fork's message id and title, and a launch limit. Every other spawn setting comes from the developer's base request the tool holds (D-13): spawn and launch replace only its prompt, and continue passes it whole for the host to clear its session fields.
COMMON MODIFICATION PATTERNS: A new model-facing argument needs a decision in the spec first (D-13 keeps permissions, sandbox, budgets and paths out of the model's reach); then it adds one schema property and one argument read.
KNOWN EDGE CASES: The prompts argument arrives as a JSON array, which the tool turns into the tuple the host takes; any other value goes on unchanged, so the host refuses it with configuration.invalid_argument.
RELATED DOCS: vidbyte/tools/README.md; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

from dataclasses import asdict, replace

from vidbyte.lib.errors import ClaudeOperationError
from vidbyte.tools.builtins.claude._base import _ClaudeBuiltinTool
from vidbyte.tools.builtins.claude.descriptions import (
    CONTINUE_CLAUDE_SESSION_DESCRIPTION,
    FORK_CLAUDE_SESSION_DESCRIPTION,
    LAUNCH_CLAUDE_SUBAGENTS_DESCRIPTION,
    LAUNCH_LIMIT_DESCRIPTION,
    PROMPT_DESCRIPTION,
    PROMPTS_DESCRIPTION,
    SESSION_ID_DESCRIPTION,
    SPAWN_CLAUDE_SESSION_DESCRIPTION,
    TITLE_DESCRIPTION,
    UP_TO_MESSAGE_ID_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec


class SpawnClaudeSessionTool(_ClaudeBuiltinTool):
    """Starts a new Claude Code session on the model's prompt and returns its handle at once."""

    def spec(self) -> ToolSpec:
        properties = {"prompt": {"type": "string", "description": PROMPT_DESCRIPTION}}
        return self._spec("spawn_claude_session", SPAWN_CLAUDE_SESSION_DESCRIPTION, ToolPermission.WRITE, properties, ("prompt",))

    async def execute(self, call: ToolCall) -> ToolResult:
        # @intent the-model-sets-only-the-prompt
        # The model's prompt replaces only the prompt of the developer's base
        # request; a wrong JSON type for it fails the request's own check and
        # comes back as configuration.invalid_argument.
        prompt = self._optional_argument(call, "prompt", default=None)
        try:
            handle = await self._host.spawn_claude_session(replace(self._request, prompt=prompt))
        except ClaudeOperationError as error:
            return self._failed(self.name, error)
        return self._rendered(self.name, asdict(handle))


class ContinueClaudeSessionTool(_ClaudeBuiltinTool):
    """Sends a new prompt to an existing session as a new turn and returns its handle at once."""

    def spec(self) -> ToolSpec:
        properties = {
            "session_id": {"type": "string", "description": SESSION_ID_DESCRIPTION},
            "prompt": {"type": "string", "description": PROMPT_DESCRIPTION},
        }
        return self._spec("continue_claude_session", CONTINUE_CLAUDE_SESSION_DESCRIPTION, ToolPermission.WRITE, properties, ("session_id", "prompt"))

    async def execute(self, call: ToolCall) -> ToolResult:
        # @intent continue-keeps-the-developer-settings
        # The developer's base request goes along whole, so the continued turn
        # runs with the same settings as a spawned one; the host clears only
        # its session fields and resumes the named session.
        session_id = self._optional_argument(call, "session_id", default=None)
        prompt = self._optional_argument(call, "prompt", default=None)
        try:
            handle = await self._host.continue_claude_session(session_id, prompt, request=self._request)
        except ClaudeOperationError as error:
            return self._failed(self.name, error)
        return self._rendered(self.name, asdict(handle))


class ForkClaudeSessionTool(_ClaudeBuiltinTool):
    """Copies a session into a new one, offline, and returns the new session id."""

    def spec(self) -> ToolSpec:
        properties = {
            "session_id": {"type": "string", "description": SESSION_ID_DESCRIPTION},
            "up_to_message_id": {"type": "string", "description": UP_TO_MESSAGE_ID_DESCRIPTION},
            "title": {"type": "string", "description": TITLE_DESCRIPTION},
        }
        return self._spec("fork_claude_session", FORK_CLAUDE_SESSION_DESCRIPTION, ToolPermission.WRITE, properties, ("session_id",))

    async def execute(self, call: ToolCall) -> ToolResult:
        session_id = self._optional_argument(call, "session_id", default=None)
        up_to_message_id = self._optional_argument(call, "up_to_message_id", default="")
        title = self._optional_argument(call, "title", default="")
        try:
            forked = await self._host.fork_claude_session(session_id, up_to_message_id, title)
        except ClaudeOperationError as error:
            return self._failed(self.name, error)
        return self._rendered(self.name, {"session_id": forked})


class LaunchClaudeSubagentsTool(_ClaudeBuiltinTool):
    """Starts one new session per prompt, at most limit at a time, and returns their handles at once."""

    def spec(self) -> ToolSpec:
        properties = {
            "prompts": {"type": "array", "items": {"type": "string"}, "description": PROMPTS_DESCRIPTION},
            "limit": {"type": "integer", "description": LAUNCH_LIMIT_DESCRIPTION},
        }
        return self._spec("launch_claude_subagents", LAUNCH_CLAUDE_SUBAGENTS_DESCRIPTION, ToolPermission.WRITE, properties, ("prompts", "limit"))

    async def execute(self, call: ToolCall) -> ToolResult:
        # @intent the-model-sets-only-the-prompts
        # Every launched session is the developer's base request with one of
        # the model's prompts; a JSON array becomes the tuple the host takes,
        # and any other value goes on for the host to refuse.
        prompts = self._optional_argument(call, "prompts", default=None)
        if isinstance(prompts, list):
            prompts = tuple(prompts)
        limit = self._optional_argument(call, "limit", default=None)
        try:
            handles = await self._host.launch_claude_subagents(prompts, self._request, limit)
        except ClaudeOperationError as error:
            return self._failed(self.name, error)
        return self._rendered(self.name, [asdict(handle) for handle in handles])


__all__ = ["ContinueClaudeSessionTool", "ForkClaudeSessionTool", "LaunchClaudeSubagentsTool", "SpawnClaudeSessionTool"]

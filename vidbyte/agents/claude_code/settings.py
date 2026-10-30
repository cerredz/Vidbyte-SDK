"""FILE: vidbyte/agents/claude_code/settings.py

PURPOSE: Defines ClaudeCodeHarnessAgentSettings, the whole configuration of one ClaudeCodeHarnessAgent: its name, its instructions (the system prompt), the model, the structured-output schema, the effort level, the built-in tools it may use, its working folder, the claude executable, the time bound of one run and an optional saved session to resume.
ROLE IN CODEBASE: Taken by ClaudeCodeHarnessAgent (agent.py) and read by ClaudeCodeCommand, ClaudeCodeLauncher and ClaudeCodeWorkspace. Re-exported from vidbyte.agents.claude_code, vidbyte.agents and the root vidbyte package. An agent settings object lives in the agent's own settings.py (AGENTS.md placement exception 1); its records live in vidbyte/lib/dataclasses/claude_code.py.
ARCHITECTURE NOTE: Frozen, slotted and validated in __post_init__ through the shared RecordFieldValidator and RecordFieldConverter, so a bad value raises ConfigurationError at construction and never after a process started. Strings are accepted where the contract shows them (effort as "high", paths as text) and stored converted (ClaudeCodeEffort, a resolved Path). The output schema is copied through JSON, so a later change to the caller's dict cannot change the agent.
COMMON MODIFICATION PATTERNS: A new Claude Code option is a field with a default appended at the end (the contract pins the existing names), its check here, its ClaudeCodeFlag member and its CliOption in ClaudeCodeCommand.argv.
KNOWN EDGE CASES: model None leaves Claude Code's built-in default for the account (the user's own default model setting is not read, because the run loads no user settings). output_schema must be an object schema, because Claude Code returns structured output through a tool whose input is an object. session_id resumes a saved conversation, which Claude Code finds only from the folder it ran in, so it requires workspace. A claude_bin without a folder part is looked up on PATH like the default.
RELATED DOCS: docs/design/claude-code-harness-agent.md; vidbyte/agents/claude_code/README.md
TESTS: tests/features/claude_code_agent/test_claude_code_records.py
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from vidbyte.lib.constants.claude_code import (
    CLAUDE_CODE_DEFAULT_TIMEOUT_SECONDS,
    CLAUDE_CODE_JSON_SEPARATORS,
    CLAUDE_CODE_MAX_TIMEOUT_SECONDS,
    CLAUDE_CODE_MAX_TOOLS,
    CLAUDE_CODE_MODEL_MAX_CHARS,
    CLAUDE_CODE_MODEL_PATTERN,
    CLAUDE_CODE_NAME_MAX_CHARS,
    CLAUDE_CODE_OBJECT_SCHEMA_TYPE,
    CLAUDE_CODE_SCHEMA_TYPE_KEY,
    CLAUDE_CODE_SESSION_ID_PATTERN,
    CLAUDE_CODE_TOOL_NAME_PATTERN,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.claude_code import ClaudeCodeEffort
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class ClaudeCodeHarnessAgentSettings:
    """The configuration of one ClaudeCodeHarnessAgent, which is one Claude Code conversation."""

    name: str
    instructions: str = field(repr=False)
    model: str | None = None
    output_schema: Mapping[str, Any] | None = None
    effort: ClaudeCodeEffort | None = None
    allowed_tools: tuple[str, ...] = ()
    workspace: Path | None = None
    claude_bin: Path | None = None
    timeout_seconds: float = CLAUDE_CODE_DEFAULT_TIMEOUT_SECONDS
    session_id: str | None = None

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.name, "ClaudeCodeHarnessAgentSettings.name", max_chars=CLAUDE_CODE_NAME_MAX_CHARS, one_line=True)
        RecordFieldValidator.require_text(self.instructions, "ClaudeCodeHarnessAgentSettings.instructions")
        RecordFieldValidator.require_optional_text(self.model, "ClaudeCodeHarnessAgentSettings.model", max_chars=CLAUDE_CODE_MODEL_MAX_CHARS, pattern=CLAUDE_CODE_MODEL_PATTERN, one_line=True)
        object.__setattr__(self, "output_schema", self._schema_copy(self.output_schema))
        if self.effort is not None:
            object.__setattr__(self, "effort", RecordFieldConverter.to_enum(self.effort, ClaudeCodeEffort, "ClaudeCodeHarnessAgentSettings.effort"))
        tools = RecordFieldConverter.to_tuple(self.allowed_tools, "ClaudeCodeHarnessAgentSettings.allowed_tools", item_type=str, max_items=CLAUDE_CODE_MAX_TOOLS)
        object.__setattr__(self, "allowed_tools", RecordFieldValidator.require_text_items(tuple(dict.fromkeys(tools)), "ClaudeCodeHarnessAgentSettings.allowed_tools", pattern=CLAUDE_CODE_TOOL_NAME_PATTERN))
        if self.workspace is not None:
            object.__setattr__(self, "workspace", RecordFieldConverter.to_folder(self.workspace, "ClaudeCodeHarnessAgentSettings.workspace", must_exist=True))
        if self.claude_bin is not None:
            object.__setattr__(self, "claude_bin", RecordFieldConverter.to_path(self.claude_bin, "ClaudeCodeHarnessAgentSettings.claude_bin").expanduser())
        RecordFieldValidator.require_number(self.timeout_seconds, "ClaudeCodeHarnessAgentSettings.timeout_seconds", maximum=CLAUDE_CODE_MAX_TIMEOUT_SECONDS)
        RecordFieldValidator.require_optional_text(self.session_id, "ClaudeCodeHarnessAgentSettings.session_id", pattern=CLAUDE_CODE_SESSION_ID_PATTERN)
        # @intent a-saved-session-resumes-only-from-its-own-folder
        # Claude Code keys its transcripts by the working folder, so a saved
        # session id is found only from the folder it ran in; a fresh temp
        # folder would make every resume fail with "No conversation found".
        if self.session_id is not None and self.workspace is None:
            raise ConfigurationError("ClaudeCodeHarnessAgentSettings.session_id needs workspace set to the folder that session ran in, because Claude Code finds a session only from its own working folder.", details={"field": "ClaudeCodeHarnessAgentSettings.workspace"})

    @staticmethod
    def _schema_copy(schema: Any) -> Mapping[str, Any] | None:
        # @intent schema-is-a-json-object-copied-once
        # Claude Code takes the schema as JSON text and returns structured
        # output through a tool whose input must be an object, so the schema
        # must serialize (no NaN, no non-JSON values) and describe an object.
        # A read-only JSON copy keeps a later edit of the caller's dict out.
        if schema is None:
            return None
        if not isinstance(schema, Mapping):
            raise ConfigurationError(f"ClaudeCodeHarnessAgentSettings.output_schema must be a JSON Schema mapping or None; got a value of type {type(schema).__name__}.", details={"field": "ClaudeCodeHarnessAgentSettings.output_schema"})
        try:
            copied = json.loads(json.dumps(schema, allow_nan=False))
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("ClaudeCodeHarnessAgentSettings.output_schema must hold only JSON values (text keys, no NaN or infinity).", details={"field": "ClaudeCodeHarnessAgentSettings.output_schema"}) from exc
        if copied.get(CLAUDE_CODE_SCHEMA_TYPE_KEY) != CLAUDE_CODE_OBJECT_SCHEMA_TYPE:
            raise ConfigurationError('ClaudeCodeHarnessAgentSettings.output_schema must be an object schema ("type": "object"), because Claude Code returns structured output as a tool input object.', details={"field": "ClaudeCodeHarnessAgentSettings.output_schema"})
        return MappingProxyType(copied)

    @property
    def output_schema_json(self) -> str | None:
        """The output schema as one line of compact JSON, as --json-schema takes it."""
        if self.output_schema is None:
            return None
        return json.dumps(dict(self.output_schema), separators=CLAUDE_CODE_JSON_SEPARATORS, allow_nan=False)


__all__ = ["ClaudeCodeHarnessAgentSettings"]

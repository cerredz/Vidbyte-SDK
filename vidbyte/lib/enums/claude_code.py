"""FILE: vidbyte/lib/enums/claude_code.py

PURPOSE: Defines the closed sets of the Claude Code harness agent: ClaudeCodeFailureKind (why a ClaudeCodeAgentError was raised), ClaudeCodeEffort (the --effort levels Claude Code accepts) and ClaudeCodeFlag (every command-line flag the agent passes to `claude`).
ROLE IN CODEBASE: ClaudeCodeFailureKind is carried by ClaudeCodeAgentError (vidbyte/lib/errors/base.py) and chosen by ClaudeCodeFailures and ClaudeCodeWire (vidbyte/agents/claude_code/); ClaudeCodeEffort types ClaudeCodeHarnessAgentSettings.effort; ClaudeCodeFlag is the flag of every CliOption ClaudeCodeCommand builds. All three are exported from vidbyte/lib/enums/__init__.py, and the first two from the root vidbyte package.
ARCHITECTURE NOTE: StrEnums, so a member reads as its value in messages and on argv (CliArgv turns each flag into plain text). The failure kinds are the vocabulary pinned by the cross-repo suggest-BYOK contract (section 2); vidbyte-cli matches on them, so a member is never renamed.
COMMON MODIFICATION PATTERNS: A new Claude Code option adds a ClaudeCodeFlag member and its CliOption in ClaudeCodeCommand.argv. A new failure kind adds a member here, its likely cause and next step in vidbyte/lib/constants/claude_code.py, and the condition that selects it in ClaudeCodeWire or the agent, in one change.
KNOWN EDGE CASES: ClaudeCodeEffort lists Claude Code 2.1's levels; a model that does not support effort makes Claude Code itself fail the run (EXIT_NONZERO), which the SDK does not predict. --setting-sources and --tools are passed with an empty joined value, which commander reads exactly as an empty separate argument.
RELATED DOCS: docs/design/claude-code-harness-agent.md; vidbyte/agents/claude_code/README.md
TESTS: tests/features/claude_code_agent/
"""

from __future__ import annotations

from enum import StrEnum


class ClaudeCodeFailureKind(StrEnum):
    """Why a Claude Code run failed; every ClaudeCodeAgentError carries exactly one."""

    NOT_INSTALLED = "not_installed"
    NOT_AUTHENTICATED = "not_authenticated"
    TIMEOUT = "timeout"
    EXIT_NONZERO = "exit_nonzero"
    SCHEMA_VIOLATION = "schema_violation"
    UNSUPPORTED_INPUT = "unsupported_input"
    MALFORMED_OUTPUT = "malformed_output"


class ClaudeCodeEffort(StrEnum):
    """The effort levels Claude Code's --effort flag accepts."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


class ClaudeCodeFlag(StrEnum):
    """Every command-line flag the Claude Code harness agent passes to `claude`."""

    PRINT = "--print"
    INPUT_FORMAT = "--input-format"
    OUTPUT_FORMAT = "--output-format"
    VERBOSE = "--verbose"
    SAFE_MODE = "--safe-mode"
    SETTING_SOURCES = "--setting-sources"
    STRICT_MCP_CONFIG = "--strict-mcp-config"
    DISABLE_SLASH_COMMANDS = "--disable-slash-commands"
    SYSTEM_PROMPT_FILE = "--system-prompt-file"
    TOOLS = "--tools"
    ALLOWED_TOOLS = "--allowed-tools"
    MODEL = "--model"
    EFFORT = "--effort"
    JSON_SCHEMA = "--json-schema"
    SESSION_ID = "--session-id"
    RESUME = "--resume"


__all__ = ["ClaudeCodeEffort", "ClaudeCodeFailureKind", "ClaudeCodeFlag"]

"""FILE: vidbyte/agents/claude_code/command.py

PURPOSE: Defines ClaudeCodeCommand, which turns one run into what `claude` receives: the argv (print mode, stream-json in and out, the isolation flags, the private instructions file, the tools, model, effort, schema and session flags), the single stream-json user message written to stdin (the images, then the prompt text), the media types Claude Code cannot take, and the length of the command line as Windows counts it.
ROLE IN CODEBASE: Called by ClaudeCodeHarnessAgent.arun (agent.py), which passes the argv and stdin to CliRunner (vidbyte/lib/process/runner.py) and refuses a run whose input or command line Claude Code cannot take. Options are built by the canonical CliArgv (vidbyte/lib/process/argv.py) in the joined style.
ARCHITECTURE NOTE: Pure and synchronous: no I/O and no environment reads. Every option is one --flag=value element, so a model name or schema text can never be read as another flag, and no element is empty (CliInvocation refuses empty elements; commander reads --tools= exactly as --tools ""). The isolation flags are always sent, whatever the settings: --safe-mode and --setting-sources= load none of the user's hooks, plugins, CLAUDE.md files, auto-memory or settings; --strict-mcp-config loads no MCP server; --disable-slash-commands loads no skill or command (docs/design/claude-code-harness-agent.md section 4.5 records the live check).
COMMON MODIFICATION PATTERNS: A new Claude Code option is a ClaudeCodeFlag member, a ClaudeCodeHarnessAgentSettings field, a ClaudeCodeCommandRequest field and one CliOption appended in argv(). Keep the session flag last.
WHAT NOT TO DO IN THIS FILE: 1. Do not put the prompt or the instructions on argv; they go through stdin and the instructions file. 2. Do not drop an isolation flag when tools are allowed; tools never need the user's hooks or settings. 3. Do not pass --bare: it ignores the Claude login (section 4.4).
KNOWN EDGE CASES: With no allowed tools --tools= disables every built-in tool and --allowed-tools is not sent; --json-schema still works, through the StructuredOutput tool Claude Code adds. With tools, --allowed-tools names the same tools so they run without a permission prompt nobody could answer in print mode. The stdin message is one line of JSON ended by a newline; CliRunner closes the pipe after it, which ends the run's input.
RELATED DOCS: docs/design/claude-code-harness-agent.md sections 6.2 and 6.3; vidbyte/agents/claude_code/README.md
TESTS: tests/features/claude_code_agent/test_claude_code_agent.py
"""

from __future__ import annotations

import json
import subprocess

from vidbyte.lib.constants.claude_code import (
    CLAUDE_CODE_BASE64_SOURCE,
    CLAUDE_CODE_CONTENT_KEY,
    CLAUDE_CODE_DATA_KEY,
    CLAUDE_CODE_IMAGE_BLOCK,
    CLAUDE_CODE_IMAGE_MEDIA_TYPES,
    CLAUDE_CODE_MEDIA_TYPE_KEY,
    CLAUDE_CODE_MESSAGE_KEY,
    CLAUDE_CODE_NO_SETTING_SOURCES,
    CLAUDE_CODE_NO_TOOLS,
    CLAUDE_CODE_ROLE_KEY,
    CLAUDE_CODE_SOURCE_KEY,
    CLAUDE_CODE_STDIN_LINE_END,
    CLAUDE_CODE_STREAM_JSON,
    CLAUDE_CODE_TEXT_BLOCK,
    CLAUDE_CODE_TOOL_SEPARATOR,
    CLAUDE_CODE_TYPE_KEY,
    CLAUDE_CODE_USER_ROLE,
)
from vidbyte.lib.constants.native_threads import (
    NATIVE_UTF16_UNIT_BYTES,
    NATIVE_WINDOWS_COMMAND_LINE_ENCODING,
)
from vidbyte.lib.dataclasses.claude_code import (
    ClaudeCodeCommandRequest,
    ClaudeCodeRunInput,
)
from vidbyte.lib.dataclasses.process import CliOption
from vidbyte.lib.enums.claude_code import ClaudeCodeFlag
from vidbyte.lib.enums.process import CliOptionStyle
from vidbyte.lib.process import CliArgv


class ClaudeCodeCommand:
    """Builds the argv and the stdin message of one Claude Code run."""

    @staticmethod
    def argv(request: ClaudeCodeCommandRequest) -> tuple[str, ...]:
        # @intent every-run-is-isolated-print-mode-stream-json
        # Print mode with stream-json both ways is the one shape that carries
        # images and reports this run's own cost and model; the isolation
        # flags are unconditional so no hook, plugin, MCP server, skill or
        # CLAUDE.md of the user runs inside the thread.
        options = [
            CliOption(ClaudeCodeFlag.PRINT),
            CliOption(ClaudeCodeFlag.INPUT_FORMAT, CLAUDE_CODE_STREAM_JSON),
            CliOption(ClaudeCodeFlag.OUTPUT_FORMAT, CLAUDE_CODE_STREAM_JSON),
            CliOption(ClaudeCodeFlag.VERBOSE),
            CliOption(ClaudeCodeFlag.SAFE_MODE),
            CliOption(ClaudeCodeFlag.SETTING_SOURCES, CLAUDE_CODE_NO_SETTING_SOURCES),
            CliOption(ClaudeCodeFlag.STRICT_MCP_CONFIG),
            CliOption(ClaudeCodeFlag.DISABLE_SLASH_COMMANDS),
            CliOption(ClaudeCodeFlag.SYSTEM_PROMPT_FILE, str(request.instructions_file)),
        ]

        # No tools means every built-in tool is off; named tools are both made
        # available and pre-approved, since print mode cannot ask anyone.
        tools = CLAUDE_CODE_TOOL_SEPARATOR.join(request.allowed_tools)
        options.append(CliOption(ClaudeCodeFlag.TOOLS, tools or CLAUDE_CODE_NO_TOOLS))
        if tools:
            options.append(CliOption(ClaudeCodeFlag.ALLOWED_TOOLS, tools))

        # The model, the effort and the schema are sent only when chosen, so
        # Claude Code's own defaults apply otherwise.
        if request.model is not None:
            options.append(CliOption(ClaudeCodeFlag.MODEL, request.model))
        if request.effort is not None:
            options.append(CliOption(ClaudeCodeFlag.EFFORT, request.effort.value))
        if request.output_schema_json is not None:
            options.append(CliOption(ClaudeCodeFlag.JSON_SCHEMA, request.output_schema_json))

        # The session goes last: a new id the SDK minted, or the id to resume.
        session_flag = ClaudeCodeFlag.RESUME if request.resume else ClaudeCodeFlag.SESSION_ID
        options.append(CliOption(session_flag, request.session_id))
        return CliArgv.build(request.launcher, options=tuple(options), style=CliOptionStyle.JOINED)

    @staticmethod
    def stdin(run_input: ClaudeCodeRunInput) -> str:
        # One stream-json user message: each image as a base64 block, in the
        # caller's order, then the prompt text, which Anthropic recommends
        # placing after the images it refers to.
        content: list[dict[str, object]] = [
            {
                CLAUDE_CODE_TYPE_KEY: CLAUDE_CODE_IMAGE_BLOCK,
                CLAUDE_CODE_SOURCE_KEY: {CLAUDE_CODE_TYPE_KEY: CLAUDE_CODE_BASE64_SOURCE, CLAUDE_CODE_MEDIA_TYPE_KEY: image.media_type.lower(), CLAUDE_CODE_DATA_KEY: image.data_base64},
            }
            for image in run_input.images
        ]
        content.append({CLAUDE_CODE_TYPE_KEY: CLAUDE_CODE_TEXT_BLOCK, CLAUDE_CODE_TEXT_BLOCK: run_input.prompt})
        message = {CLAUDE_CODE_TYPE_KEY: CLAUDE_CODE_USER_ROLE, CLAUDE_CODE_MESSAGE_KEY: {CLAUDE_CODE_ROLE_KEY: CLAUDE_CODE_USER_ROLE, CLAUDE_CODE_CONTENT_KEY: content}}
        return json.dumps(message, ensure_ascii=False) + CLAUDE_CODE_STDIN_LINE_END

    @staticmethod
    def unsupported_media_types(run_input: ClaudeCodeRunInput) -> tuple[str, ...]:
        """The media types of the run's attachments that Claude Code cannot take, each once, in order."""
        unsupported = (image.media_type for image in run_input.images if image.media_type.lower() not in CLAUDE_CODE_IMAGE_MEDIA_TYPES)
        return tuple(dict.fromkeys(unsupported))

    @staticmethod
    def windows_command_line_units(argv: tuple[str, ...]) -> int:
        """The UTF-16 length of argv once quoted the way CreateProcess receives it."""
        line = subprocess.list2cmdline(argv)
        return len(line.encode(NATIVE_WINDOWS_COMMAND_LINE_ENCODING)) // NATIVE_UTF16_UNIT_BYTES


__all__ = ["ClaudeCodeCommand"]

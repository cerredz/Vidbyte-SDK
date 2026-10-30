"""FILE: vidbyte/lib/constants/claude_code.py

PURPOSE: Holds every fixed value of the Claude Code harness agent: the program name, its time and output bounds, the stream-json wire literals Claude Code 2.1 prints (observed live, docs/design/claude-code-harness-agent.md section 4), the image media types the Messages API accepts, the environment variables a parent Claude Code session sets for its children, the credential variables and token shape scrubbed from vendor text, the markers that identify a login failure, and the likely cause and next step written for each ClaudeCodeFailureKind.
ROLE IN CODEBASE: Read by the records in vidbyte/lib/dataclasses/claude_code.py, by ClaudeCodeAgentError's callers and by every module of vidbyte/agents/claude_code/ (settings, command, launcher, workspace, wire, failures, agent).
ARCHITECTURE NOTE: Bottom layer: it imports only the shared native-thread bounds (vidbyte/lib/constants/native_threads.py), which this agent shares with the harness thread functions because it runs through the same CliRunner. The agent modules hold no literals of their own, so a reviewer finds each Claude Code fact here.
COMMON MODIFICATION PATTERNS: When Claude Code changes a wire key, change it here and add the new shape to the fake in tests/features/claude_code_agent/fake_claude.py. A new failure kind adds its entry to CLAUDE_CODE_FAILURE_TEXTS. A new auth failure text Claude Code prints joins CLAUDE_CODE_AUTH_MARKERS (lower case).
KNOWN EDGE CASES: A login failure exits 1 with is_error true while subtype still reads "success", so only is_error is trusted. total_cost_usd and modelUsage are cumulative over a resumed session; model_usage_since_last_result is this run alone. The Windows CreateProcess limit is 32,767 UTF-16 units including the terminating null.
RELATED DOCS: docs/design/claude-code-harness-agent.md; vidbyte/agents/claude_code/README.md
TESTS: tests/features/claude_code_agent/
"""

from __future__ import annotations

from vidbyte.lib.constants.native_threads import (
    NATIVE_PROCESS_MAX_OUTPUT_BYTES,
    NATIVE_THREAD_MAX_SECONDS,
)
from vidbyte.lib.enums.claude_code import ClaudeCodeFailureKind

# The executable looked up on PATH when the settings name none.
CLAUDE_CODE_PROGRAM = "claude"
# Default and largest time bound of one run, in seconds.
CLAUDE_CODE_DEFAULT_TIMEOUT_SECONDS = 600.0
CLAUDE_CODE_MAX_TIMEOUT_SECONDS = NATIVE_THREAD_MAX_SECONDS
# The stream-json output of one run is capped at the shared native cap.
CLAUDE_CODE_MAX_OUTPUT_BYTES = NATIVE_PROCESS_MAX_OUTPUT_BYTES
# CreateProcess takes at most 32,767 UTF-16 units, the terminating null included.
CLAUDE_CODE_WINDOWS_COMMAND_LINE_MAX_UNITS = 32766
CLAUDE_CODE_WINDOWS_PLATFORM = "win32"

# Text bounds of the records.
CLAUDE_CODE_NAME_MAX_CHARS = 200
CLAUDE_CODE_MODEL_MAX_CHARS = 200
CLAUDE_CODE_MODEL_PATTERN = r"\S+"
CLAUDE_CODE_TOOL_NAME_PATTERN = r"[A-Za-z][A-Za-z0-9_]*"
CLAUDE_CODE_MAX_TOOLS = 64
CLAUDE_CODE_SESSION_ID_PATTERN = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
CLAUDE_CODE_MEDIA_TYPE_PATTERN = r"[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+"
CLAUDE_CODE_MEDIA_TYPE_MAX_CHARS = 100
# The image types the Anthropic Messages API accepts as base64 image blocks.
CLAUDE_CODE_IMAGE_MEDIA_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")

# Values of the command line and of the stdin message (observed on Claude Code 2.1.314).
CLAUDE_CODE_STREAM_JSON = "stream-json"
CLAUDE_CODE_NO_SETTING_SOURCES = ""
CLAUDE_CODE_NO_TOOLS = ""
CLAUDE_CODE_TOOL_SEPARATOR = ","
CLAUDE_CODE_JSON_SEPARATORS = (",", ":")
CLAUDE_CODE_STDIN_LINE_END = "\n"
CLAUDE_CODE_TEXT_ENCODING = "utf-8"
CLAUDE_CODE_USER_ROLE = "user"
CLAUDE_CODE_TEXT_BLOCK = "text"
CLAUDE_CODE_IMAGE_BLOCK = "image"
CLAUDE_CODE_BASE64_SOURCE = "base64"
CLAUDE_CODE_ROLE_KEY = "role"
CLAUDE_CODE_CONTENT_KEY = "content"
CLAUDE_CODE_SOURCE_KEY = "source"
CLAUDE_CODE_MEDIA_TYPE_KEY = "media_type"
CLAUDE_CODE_DATA_KEY = "data"
# The tool Claude Code adds for --json-schema; the only tool allowed beyond the caller's.
CLAUDE_CODE_STRUCTURED_OUTPUT_TOOL = "StructuredOutput"
# --json-schema must describe an object, because the answer is that tool's input.
CLAUDE_CODE_SCHEMA_TYPE_KEY = "type"
CLAUDE_CODE_OBJECT_SCHEMA_TYPE = "object"

# Keys and values of the stream-json events Claude Code prints.
CLAUDE_CODE_TYPE_KEY = "type"
CLAUDE_CODE_SUBTYPE_KEY = "subtype"
CLAUDE_CODE_SYSTEM_EVENT = "system"
CLAUDE_CODE_INIT_SUBTYPE = "init"
CLAUDE_CODE_ASSISTANT_EVENT = "assistant"
CLAUDE_CODE_RESULT_EVENT = "result"
CLAUDE_CODE_MESSAGE_KEY = "message"
CLAUDE_CODE_MODEL_KEY = "model"
CLAUDE_CODE_TOOLS_KEY = "tools"
CLAUDE_CODE_MCP_SERVERS_KEY = "mcp_servers"
CLAUDE_CODE_SESSION_ID_KEY = "session_id"
CLAUDE_CODE_IS_ERROR_KEY = "is_error"
CLAUDE_CODE_RESULT_KEY = "result"
CLAUDE_CODE_STRUCTURED_OUTPUT_KEY = "structured_output"
CLAUDE_CODE_USAGE_KEY = "usage"
CLAUDE_CODE_TOTAL_COST_KEY = "total_cost_usd"
CLAUDE_CODE_RUN_MODEL_USAGE_KEY = "model_usage_since_last_result"
CLAUDE_CODE_COST_KEY = "costUSD"
CLAUDE_CODE_OUTPUT_TOKENS_KEY = "outputTokens"
CLAUDE_CODE_NUM_TURNS_KEY = "num_turns"
CLAUDE_CODE_DURATION_KEY = "duration_ms"
CLAUDE_CODE_API_ERROR_STATUS_KEY = "api_error_status"
CLAUDE_CODE_TERMINAL_REASON_KEY = "terminal_reason"
CLAUDE_CODE_INPUT_TOKENS_FIELD = "input_tokens"
CLAUDE_CODE_OUTPUT_TOKENS_FIELD = "output_tokens"
CLAUDE_CODE_CACHE_READ_FIELD = "cache_read_input_tokens"
CLAUDE_CODE_CACHE_CREATION_FIELD = "cache_creation_input_tokens"

# Variables a running Claude Code session sets for its own children. A thread started
# from inside one would otherwise join the parent's messaging socket and run at its effort.
CLAUDE_CODE_PARENT_SESSION_VARIABLES = (
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_CHILD_SESSION",
    "CLAUDE_CODE_MESSAGING_SOCKET",
    "CLAUDE_CODE_MESSAGING_TOKEN",
    "CLAUDE_CODE_SESSION_ATTENDED",
    "CLAUDE_CODE_EXECPATH",
    "CLAUDE_EFFORT",
    "CLAUDE_PID",
)
# Credential variables whose values are replaced wherever Claude Code's own text is quoted.
CLAUDE_CODE_CREDENTIAL_VARIABLES = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CODE_MESSAGING_TOKEN",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_BEARER_TOKEN_BEDROCK",
    "ANTHROPIC_VERTEX_API_KEY",
)
# Anthropic API keys and OAuth tokens start with sk-ant-; any such run is masked.
CLAUDE_CODE_TOKEN_PATTERN = r"sk-ant-[A-Za-z0-9_\-]{8,}"
CLAUDE_CODE_REDACTED = "<redacted>"
# At most this many characters of Claude Code's own text appear in an error message.
CLAUDE_CODE_VENDOR_TEXT_MAX_CHARS = 500

# A failed run whose text holds one of these (compared in lower case) is a login problem.
CLAUDE_CODE_AUTH_MARKERS = (
    "not logged in",
    "/login",
    "invalid api key",
    "invalid x-api-key",
    "authentication_error",
    "oauth token",
    "authentication failed",
)
CLAUDE_CODE_AUTH_STATUS_CODES = (401, 403)
# Commander's message for a flag this Claude Code does not know.
CLAUDE_CODE_UNKNOWN_OPTION_MARKER = "unknown option"
CLAUDE_CODE_SUCCESS_EXIT_CODE = 0

# Folders and files the agent creates outside the caller's workspace.
CLAUDE_CODE_WORKSPACE_PREFIX = "vidbyte-claude-code-"
CLAUDE_CODE_INSTRUCTIONS_PREFIX = "vidbyte-claude-instructions-"
CLAUDE_CODE_INSTRUCTIONS_FILE_NAME = "instructions.md"
# One run at a time on one agent object, because the agent is one conversation.
CLAUDE_CODE_MAX_CONCURRENT_RUNS = 1

# The likely cause and the next step of each failure kind, in that order.
CLAUDE_CODE_FAILURE_TEXTS: dict[ClaudeCodeFailureKind, tuple[str, str]] = {
    ClaudeCodeFailureKind.NOT_INSTALLED: (
        "Claude Code's `claude` executable is not on PATH, the claude_bin path does not exist or cannot run, or it is a Windows .cmd/.bat launcher this SDK refuses to run because cmd.exe would re-read its arguments.",
        "Install Claude Code (https://claude.com/claude-code; on Windows the native installer gives claude.exe), make sure `claude --version` works in this terminal, or pass ClaudeCodeHarnessAgentSettings(claude_bin=<path to the claude executable>).",
    ),
    ClaudeCodeFailureKind.NOT_AUTHENTICATED: (
        "Claude Code is not signed in, or the API key or OAuth token it found was rejected.",
        "Run `claude auth login` (or start `claude` once and run /login), or set a valid ANTHROPIC_API_KEY in this environment, then try again.",
    ),
    ClaudeCodeFailureKind.TIMEOUT: (
        "The run took longer than timeout_seconds, so the whole Claude Code process tree was stopped.",
        "Raise ClaudeCodeHarnessAgentSettings.timeout_seconds, choose a faster model or lower effort, or shorten the prompt; the conversation keeps every turn that finished before this one.",
    ),
    ClaudeCodeFailureKind.EXIT_NONZERO: (
        "Claude Code reported a failure of its own: an API error, an overloaded or rate-limited account, a session it could not find in this workspace, or a flag this Claude Code version does not know.",
        "Read Claude Code's own message quoted above; run `claude update` if it names an unknown option, keep the same workspace to resume a session, and retry later if the API was overloaded or rate-limited.",
    ),
    ClaudeCodeFailureKind.SCHEMA_VIOLATION: (
        "The model ended its turn without returning an object that matches output_schema, so Claude Code reported no structured output.",
        "Check that output_schema can be satisfied (types, required fields, bounds) and that the instructions ask for it, then run again; a larger model satisfies strict schemas more reliably.",
    ),
    ClaudeCodeFailureKind.UNSUPPORTED_INPUT: (
        "The run input holds something Claude Code cannot take: an attachment type other than png, jpeg, gif or webp images, or settings too long for the Windows command line.",
        "Send images as image/png, image/jpeg, image/gif or image/webp, inline text files into the prompt yourself, and keep output_schema small enough for the command line.",
    ),
    ClaudeCodeFailureKind.MALFORMED_OUTPUT: (
        "Claude Code's output did not have the shape this SDK reads: no final result event, a missing or different session id, more output than the cap, or a session that started with tools or MCP servers the settings did not allow.",
        "Run `claude update` so the installed Claude Code matches the version this SDK was checked against (2.1.314), then retry; report the quoted output if it persists.",
    ),
}


__all__ = [
    "CLAUDE_CODE_SOURCE_KEY",
    "CLAUDE_CODE_ROLE_KEY",
    "CLAUDE_CODE_MEDIA_TYPE_KEY",
    "CLAUDE_CODE_DATA_KEY",
    "CLAUDE_CODE_CONTENT_KEY",
    "CLAUDE_CODE_API_ERROR_STATUS_KEY",
    "CLAUDE_CODE_ASSISTANT_EVENT",
    "CLAUDE_CODE_AUTH_MARKERS",
    "CLAUDE_CODE_AUTH_STATUS_CODES",
    "CLAUDE_CODE_BASE64_SOURCE",
    "CLAUDE_CODE_CACHE_CREATION_FIELD",
    "CLAUDE_CODE_CACHE_READ_FIELD",
    "CLAUDE_CODE_COST_KEY",
    "CLAUDE_CODE_CREDENTIAL_VARIABLES",
    "CLAUDE_CODE_DEFAULT_TIMEOUT_SECONDS",
    "CLAUDE_CODE_DURATION_KEY",
    "CLAUDE_CODE_FAILURE_TEXTS",
    "CLAUDE_CODE_IMAGE_BLOCK",
    "CLAUDE_CODE_IMAGE_MEDIA_TYPES",
    "CLAUDE_CODE_INIT_SUBTYPE",
    "CLAUDE_CODE_INPUT_TOKENS_FIELD",
    "CLAUDE_CODE_INSTRUCTIONS_FILE_NAME",
    "CLAUDE_CODE_INSTRUCTIONS_PREFIX",
    "CLAUDE_CODE_IS_ERROR_KEY",
    "CLAUDE_CODE_JSON_SEPARATORS",
    "CLAUDE_CODE_MAX_CONCURRENT_RUNS",
    "CLAUDE_CODE_MAX_OUTPUT_BYTES",
    "CLAUDE_CODE_MAX_TIMEOUT_SECONDS",
    "CLAUDE_CODE_MAX_TOOLS",
    "CLAUDE_CODE_MCP_SERVERS_KEY",
    "CLAUDE_CODE_MEDIA_TYPE_MAX_CHARS",
    "CLAUDE_CODE_MEDIA_TYPE_PATTERN",
    "CLAUDE_CODE_MESSAGE_KEY",
    "CLAUDE_CODE_MODEL_KEY",
    "CLAUDE_CODE_MODEL_MAX_CHARS",
    "CLAUDE_CODE_MODEL_PATTERN",
    "CLAUDE_CODE_NAME_MAX_CHARS",
    "CLAUDE_CODE_NO_SETTING_SOURCES",
    "CLAUDE_CODE_NO_TOOLS",
    "CLAUDE_CODE_NUM_TURNS_KEY",
    "CLAUDE_CODE_OBJECT_SCHEMA_TYPE",
    "CLAUDE_CODE_OUTPUT_TOKENS_FIELD",
    "CLAUDE_CODE_OUTPUT_TOKENS_KEY",
    "CLAUDE_CODE_PARENT_SESSION_VARIABLES",
    "CLAUDE_CODE_PROGRAM",
    "CLAUDE_CODE_REDACTED",
    "CLAUDE_CODE_RESULT_EVENT",
    "CLAUDE_CODE_RESULT_KEY",
    "CLAUDE_CODE_RUN_MODEL_USAGE_KEY",
    "CLAUDE_CODE_SCHEMA_TYPE_KEY",
    "CLAUDE_CODE_SESSION_ID_KEY",
    "CLAUDE_CODE_SESSION_ID_PATTERN",
    "CLAUDE_CODE_STDIN_LINE_END",
    "CLAUDE_CODE_STREAM_JSON",
    "CLAUDE_CODE_STRUCTURED_OUTPUT_KEY",
    "CLAUDE_CODE_STRUCTURED_OUTPUT_TOOL",
    "CLAUDE_CODE_SUBTYPE_KEY",
    "CLAUDE_CODE_SUCCESS_EXIT_CODE",
    "CLAUDE_CODE_SYSTEM_EVENT",
    "CLAUDE_CODE_TERMINAL_REASON_KEY",
    "CLAUDE_CODE_TEXT_BLOCK",
    "CLAUDE_CODE_TEXT_ENCODING",
    "CLAUDE_CODE_TOKEN_PATTERN",
    "CLAUDE_CODE_TOOLS_KEY",
    "CLAUDE_CODE_TOOL_NAME_PATTERN",
    "CLAUDE_CODE_TOOL_SEPARATOR",
    "CLAUDE_CODE_TOTAL_COST_KEY",
    "CLAUDE_CODE_TYPE_KEY",
    "CLAUDE_CODE_UNKNOWN_OPTION_MARKER",
    "CLAUDE_CODE_USAGE_KEY",
    "CLAUDE_CODE_USER_ROLE",
    "CLAUDE_CODE_VENDOR_TEXT_MAX_CHARS",
    "CLAUDE_CODE_WINDOWS_COMMAND_LINE_MAX_UNITS",
    "CLAUDE_CODE_WINDOWS_PLATFORM",
    "CLAUDE_CODE_WORKSPACE_PREFIX",
]

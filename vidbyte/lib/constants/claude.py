"""FILE: vidbyte/lib/constants/claude.py

PURPOSE: Defines the shared constants of the ClaudeHost harness: names, bounds, CLI lookup paths, account fields and every next-step text.
ROLE IN CODEBASE: Supplies the literals that the Claude records, the host package and the Claude tools share, so each lives in one place.
ARCHITECTURE NOTE: Constants live below the host and tools layers, so every collaborator can import them without importing claude_agent_sdk.
COMMON MODIFICATION PATTERNS: Add a CLAUDE-prefixed value when the host needs a shared literal; add a next step whenever a claude.* failure code is added.
KNOWN EDGE CASES: CLAUDE_FAILURE_NEXT_STEPS must cover exactly the claude.* FailureCode values; no constant name may contain TOKEN, PASSWORD, PASS, PWD or SECRET as a whole word, because ruff S105 flags string values bound to such names.
RELATED DOCS: https://platform.claude.com/docs/en/agent-sdk/python; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

from collections.abc import Mapping

from vidbyte.lib.enums.failure import FailureCode

# The optional extra that installs claude-agent-sdk.
CLAUDE_SDK_EXTRA = "vidbyte-sdk[claude]"
# The executable name Claude Code installs on every platform.
CLAUDE_CLI_NAME = "claude"
# The oldest Claude Code release whose flags and messages the host relies on.
CLAUDE_MIN_CLI_VERSION = "2.1.296"
# The name of the in-process MCP server that carries a request's own tools.
CLAUDE_TOOL_SERVER_NAME = "vidbyte"
# Claude Code names an MCP tool mcp__<server>__<tool>.
CLAUDE_MCP_TOOL_PREFIX = "mcp__"
# The SDK's name for Claude Code's own system prompt.
CLAUDE_SYSTEM_PROMPT_PRESET = "claude_code"
# A plugin entry containing a scheme is a URL rather than a local folder.
CLAUDE_PLUGIN_URL_MARKER = "://"
# The CLI accepts one --file flag per run through extra_args.
CLAUDE_MAX_FILE_SPECS = 1
# The CLI accepts one --plugin-url flag per run through extra_args.
CLAUDE_MAX_PLUGIN_URLS = 1
# The smallest autocompact threshold Claude Code accepts.
CLAUDE_MIN_AUTOCOMPACT_TOKENS = 100_000
# The largest autocompact threshold Claude Code accepts.
CLAUDE_MAX_AUTOCOMPACT_TOKENS = 1_000_000
# The environment variable Claude Code reads for its output cap.
CLAUDE_MAX_OUTPUT_TOKENS_ENV = "CLAUDE_CODE_MAX_OUTPUT_TOKENS"
# Counts such as turns, limits and budgets start at one.
CLAUDE_MIN_COUNT = 1
# Amounts such as dollars and seconds must be above zero.
CLAUDE_MIN_EXCLUSIVE_AMOUNT = 0.0
# How long a turn waits for Claude Code to answer an interrupt before closing it.
CLAUDE_INTERRUPT_GRACE_SECONDS = 30.0
# Sent when the developer's live-session cap refuses a new turn.
CLAUDE_LIVE_CAP_NEXT_STEP = "Wait for a running session to finish, or interrupt one, then spawn again."
# Sent when Claude Code fails to start, because a respawn would fail the same way.
CLAUDE_START_FAILURE_NEXT_STEP = "Run check_claude_ready to see why Claude Code did not start; if that check fails the same way, reinstall Claude Code or pass cli_path to ClaudeHost."
# Sent when a session file cannot be read, because listing sessions would fail the same way.
CLAUDE_HISTORY_READ_NEXT_STEP = "Check that this process can read Claude Code's session files, then call again."
# Sent with configuration.invalid_argument.
CLAUDE_INVALID_ARGUMENT_NEXT_STEP = "Correct the argument the reason names, then call again."
# Sent with configuration.unsupported_combination.
CLAUDE_UNSUPPORTED_COMBINATION_NEXT_STEP = "Change one of the settings the reason names so that they no longer conflict, then call again."
# Sent with input.empty.
CLAUDE_EMPTY_INPUT_NEXT_STEP = "Pass non-empty text, then call again."
# Sent with action.precondition_failed.
CLAUDE_PRECONDITION_NEXT_STEP = "Use the host only inside its async with block on the event loop that entered it (await agent.arun(), not agent.run()), and steer only a RUNNING turn with no steer pending."
# The next step each claude.* failure code carries.
CLAUDE_FAILURE_NEXT_STEPS: Mapping[str, str] = {
    FailureCode.CLAUDE_SDK_UNAVAILABLE.value: f'Install the extra: pip install "{CLAUDE_SDK_EXTRA}".',
    FailureCode.CLAUDE_NOT_INSTALLED.value: "Install Claude Code (the native claude.exe on Windows), or pass cli_path to ClaudeHost.",
    FailureCode.CLAUDE_VERSION_UNSUPPORTED.value: "Run claude update.",
    FailureCode.CLAUDE_NOT_SIGNED_IN.value: "Run claude auth login.",
    FailureCode.CLAUDE_AUTH_MODE_UNSUPPORTED.value: "Switch login type: betas and bare need an API key login.",
    FailureCode.CLAUDE_USAGE_LIMITED.value: "Wait until the reset time, or use an API key.",
    FailureCode.CLAUDE_BILLING_ERROR.value: "Add credits.",
    FailureCode.CLAUDE_MODEL_UNKNOWN.value: "Pick a model from list_claude_models.",
    FailureCode.CLAUDE_SESSION_NOT_FOUND.value: "Find the session with list_claude_sessions.",
    FailureCode.CLAUDE_SESSION_BUSY.value: "Steer it, or fork it.",
    FailureCode.CLAUDE_BUDGET_EXHAUSTED.value: "Raise the budget, or split the work.",
    FailureCode.CLAUDE_API_ERROR.value: "Retry with backoff.",
    FailureCode.CLAUDE_PERMISSION_DENIED.value: "Allow the tool, or change the permission mode.",
    FailureCode.CLAUDE_SCHEMA_VIOLATION.value: "Run a repair turn using the raw text.",
    FailureCode.CLAUDE_PROCESS_EXITED.value: "Respawn, then resume by id.",
    FailureCode.CLAUDE_PROTOCOL_MISMATCH.value: "Align the SDK and CLI versions.",
}
# The platform name sys.platform reports on Windows.
CLAUDE_WINDOWS_PLATFORM = "win32"
# The native Windows executable, which is the only form the SDK can start there.
CLAUDE_CLI_EXE_NAME = "claude.exe"
# Windows suffixes of a file that starts without a shell.
CLAUDE_WINDOWS_NATIVE_SUFFIXES = (".exe", ".com")
# Windows suffixes of a shim the SDK cannot start, so a lookup hit with one is skipped.
CLAUDE_WINDOWS_BATCH_SUFFIXES = (".bat", ".cmd")
# Where the native installer puts claude.exe under the home folder on Windows.
CLAUDE_HOME_CLI_PARTS = (".local", "bin", "claude.exe")
# The places the SDK itself searches on other platforms, in its order, relative to the home folder.
CLAUDE_POSIX_CLI_LOCATIONS = (".npm-global/bin/claude", "/usr/local/bin/claude", ".local/bin/claude", "node_modules/.bin/claude", ".yarn/bin/claude", ".claude/local/claude")
# Account fields whose value names where the signed-in credential came from.
CLAUDE_CREDENTIAL_SOURCE_FIELDS = ("tokenSource", "apiKeySource")
# The account field that is set when the session runs on an API key.
CLAUDE_API_KEY_SOURCE_FIELD = "apiKeySource"
# The value Claude Code reports for a credential source that is not in use.
CLAUDE_ABSENT_SOURCE = "none"
# The account field that names the API provider.
CLAUDE_PROVIDER_FIELD = "apiProvider"
# The provider value for Anthropic's own API, the only one that needs a sign-in.
CLAUDE_FIRST_PARTY_PROVIDER = "firstParty"

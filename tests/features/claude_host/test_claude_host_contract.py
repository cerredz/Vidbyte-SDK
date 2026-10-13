"""FILE: tests/features/claude_host/test_claude_host_contract.py

PURPOSE: Pins the static contract of the ClaudeHost feature: the import boundary that keeps the optional extra optional, the byte-exact shared marker, the failure-code block and its next steps, the constants, the 17 enums and their wire values, the record shapes, the public ClaudeHost surface, the pyproject extra, and the two documentation insertions.
ROLE IN CODEBASE: Contract layer of tests/features/claude_host/ (spec INV-1, INV-21, INV-22, AC-19, AC-23, AC-27, AC-32, AC-33, AC-35, rows 1-2, 11-15, 22-31 of section 12.3). Reads vidbyte/harnesses/native/, vidbyte/lib/{enums,constants,dataclasses,errors}/, vidbyte/tools/{builtins,toolsets}/, pyproject.toml, REPO_MAP.md and vidbyte/harnesses/README.md.
ARCHITECTURE NOTE: Every expected value is spelled out from the spec (sections 8.5, 9.2 and 12.3, and request.md section C for the shared texts), never read back from production constants, so a drifting constant fails here. The import-boundary test runs a clean interpreter so that modules other tests already imported cannot hide a vendor import.
COMMON MODIFICATION PATTERNS: When the spec adds a request field, enum member, constant or record, add it to the matching expected table here in spec order. When request.md changes a shared text, the orchestrator changes both host PRs together; copy the new text verbatim.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level; the module must collect before the feature exists. 2. Do not hash the checked-out marker bytes without replacing CRLF with LF (core.autocrlf=true on this machine). 3. Do not compute expected values from production code.
KNOWN EDGE CASES: The marker contains its own triple-quoted docstring, so its lines are stored one literal each and joined with LF. The REPO_MAP paragraph contains apostrophes, so it is a double-quoted literal. AC-33's "dev is unchanged" is checked as "dev does not gain claude-agent-sdk", because pinning today's whole dev list would break on unrelated PRs.
RELATED DOCS: tests/features/claude_host/FEATURE.md; docs/spec/claude-host/spec.md sections 6.1, 6.2, 8.5, 9.2 and 12.3; docs/spec/claude-host/request.md section C.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/claude_host/test_claude_host_contract.py
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import inspect
import json
import os
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

from tests.features.claude_host.claude_host_fixtures import (
    CLAUDE_NEXT_STEPS,
    EMPTY_INPUT_NEXT_STEP,
    INVALID_ARGUMENT_NEXT_STEP,
    LIVE_CAP_NEXT_STEP,
    PRECONDITION_NEXT_STEP,
    START_FAILURE_NEXT_STEP,
    UNSUPPORTED_COMBINATION_NEXT_STEP,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

# request.md section C: the shared marker module, byte for byte (LF endings and a final newline).
MARKER_SHA256 = "0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a"
MARKER_LINES = (
    '"""FILE: vidbyte/harnesses/native/__init__.py',
    "",
    "PURPOSE: Marks vidbyte/harnesses/native as the package of native coding-harness hosts: one subpackage per coding harness, each wrapping that harness's official SDK in small, atomic functions on a host class.",
    "ROLE IN CODEBASE: A parent package only. Callers import a host from its own subpackage, never from this module, so this module imports nothing and names no harness.",
    "ARCHITECTURE NOTE: Each harness subpackage owns its host class, its vendor SDK import, and its errors. Nothing here imports a vendor SDK, so importing this package never requires an optional extra.",
    "COMMON MODIFICATION PATTERNS: A new harness adds its own subpackage beside the existing ones and leaves this module unchanged.",
    "KNOWN EDGE CASES: None; the module defines no names.",
    "RELATED DOCS: vidbyte/harnesses/README.md",
    "TESTS: None of its own; each harness subpackage has its own tests.",
    '"""',
)
MARKER_TEXT = "\n".join(MARKER_LINES) + "\n"

# request.md section C: the REPO_MAP entry and the harnesses README bullet, verbatim.
NATIVE_MAP_HEADING = "##### `vidbyte/harnesses/native/`"
NATIVE_MAP_PARAGRAPH = "Hosts for the coding agents that vendors ship as their own executables, kept apart from the trajectory envelope above even though both use the word harness. Each coding harness gets its own host class, which owns the live processes it starts and wraps the vendor's official SDK in small, atomic functions such as starting, continuing, forking, steering and waiting on a session. Every failure comes back as a semantic error code that names the problem and the next step to take, so an agent that calls these functions as tools can recover without reading a stack trace. Importing the package never requires a vendor SDK: each host loads its SDK only when it is first used, and that SDK comes from the harness's own optional extra."
NATIVE_README_BULLET = "- `native/`: hosts for native coding-harness executables, one subpackage per harness, each wrapping that harness's official SDK in small, atomic functions on a host class; unrelated to the `Harness` envelope above."

# INV-1: modules whose import must never import claude_agent_sdk. The first group is the tools chain,
# which must not load the host module either (the tools package imports ClaudeHost only under TYPE_CHECKING).
TOOLS_CHAIN_MODULES = (
    "vidbyte",
    "vidbyte.tools.builtins",
    "vidbyte.tools.toolsets",
    "vidbyte.tools.toolsets.claude",
    "vidbyte.tools.builtins.claude",
)
HOST_CHAIN_MODULES = (
    "vidbyte.harnesses.native",
    "vidbyte.harnesses.native.claude",
    "vidbyte.harnesses.native.claude.host",
    "vidbyte.harnesses.native.claude.sdk",
    "vidbyte.harnesses.native.claude.options",
    "vidbyte.harnesses.native.claude.failures",
    "vidbyte.harnesses.native.claude.session",
    "vidbyte.harnesses.native.claude.history",
    "vidbyte.harnesses.native.claude.probe",
    "vidbyte.harnesses.native.claude.tool_server",
    "vidbyte.lib.dataclasses.claude",
    "vidbyte.lib.dataclasses.claude_host",
    "vidbyte.lib.enums.claude",
    "vidbyte.lib.constants.claude",
)

# A clean interpreter records every attempt to import claude_agent_sdk while the modules above load.
IMPORT_PROBE_SCRIPT = "\n".join(
    (
        "import importlib, json, sys",
        "class Recorder:",
        "    def __init__(self):",
        "        self.names = []",
        "    def find_spec(self, name, path=None, target=None):",
        "        if name.split('.')[0] == 'claude_agent_sdk':",
        "            self.names.append(name)",
        "        return None",
        "recorder = Recorder()",
        "sys.meta_path.insert(0, recorder)",
        "for name in json.loads(sys.argv[1]):",
        "    importlib.import_module(name)",
        "host_loaded_by_tools = 'vidbyte.harnesses.native.claude.host' in sys.modules",
        "for name in json.loads(sys.argv[2]):",
        "    importlib.import_module(name)",
        "loaded = sorted(name for name in sys.modules if name.split('.')[0] == 'claude_agent_sdk')",
        "print(json.dumps({'attempts': recorder.names, 'loaded': loaded, 'host_loaded_by_tools': host_loaded_by_tools}))",
    )
)

# Section 9.2: the 16 claude.* member names, in the order of the failure-code table.
CLAUDE_MEMBER_NAMES = (
    "CLAUDE_SDK_UNAVAILABLE",
    "CLAUDE_NOT_INSTALLED",
    "CLAUDE_VERSION_UNSUPPORTED",
    "CLAUDE_NOT_SIGNED_IN",
    "CLAUDE_AUTH_MODE_UNSUPPORTED",
    "CLAUDE_USAGE_LIMITED",
    "CLAUDE_BILLING_ERROR",
    "CLAUDE_MODEL_UNKNOWN",
    "CLAUDE_SESSION_NOT_FOUND",
    "CLAUDE_SESSION_BUSY",
    "CLAUDE_BUDGET_EXHAUSTED",
    "CLAUDE_API_ERROR",
    "CLAUDE_PERMISSION_DENIED",
    "CLAUDE_SCHEMA_VIOLATION",
    "CLAUDE_PROCESS_EXITED",
    "CLAUDE_PROTOCOL_MISMATCH",
)

# Section 12.3 row 14: every named constant and its value.
EXPECTED_CONSTANTS = {
    "CLAUDE_SDK_EXTRA": "vidbyte-sdk[claude]",
    "CLAUDE_CLI_NAME": "claude",
    "CLAUDE_MIN_CLI_VERSION": "2.1.296",
    "CLAUDE_TOOL_SERVER_NAME": "vidbyte",
    "CLAUDE_MCP_TOOL_PREFIX": "mcp__",
    "CLAUDE_SYSTEM_PROMPT_PRESET": "claude_code",
    "CLAUDE_PLUGIN_URL_MARKER": "://",
    "CLAUDE_MAX_FILE_SPECS": 1,
    "CLAUDE_MAX_PLUGIN_URLS": 1,
    "CLAUDE_MIN_AUTOCOMPACT_TOKENS": 100_000,
    "CLAUDE_MAX_AUTOCOMPACT_TOKENS": 1_000_000,
    "CLAUDE_MAX_OUTPUT_TOKENS_ENV": "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
    "CLAUDE_MIN_COUNT": 1,
    "CLAUDE_MIN_EXCLUSIVE_AMOUNT": 0.0,
    "CLAUDE_INTERRUPT_GRACE_SECONDS": 30.0,
    "CLAUDE_LIVE_CAP_NEXT_STEP": LIVE_CAP_NEXT_STEP,
    "CLAUDE_START_FAILURE_NEXT_STEP": START_FAILURE_NEXT_STEP,
    "CLAUDE_INVALID_ARGUMENT_NEXT_STEP": INVALID_ARGUMENT_NEXT_STEP,
    "CLAUDE_UNSUPPORTED_COMBINATION_NEXT_STEP": UNSUPPORTED_COMBINATION_NEXT_STEP,
    "CLAUDE_EMPTY_INPUT_NEXT_STEP": EMPTY_INPUT_NEXT_STEP,
    "CLAUDE_PRECONDITION_NEXT_STEP": PRECONDITION_NEXT_STEP,
    "CLAUDE_WINDOWS_PLATFORM": "win32",
    "CLAUDE_CLI_EXE_NAME": "claude.exe",
    "CLAUDE_WINDOWS_NATIVE_SUFFIXES": (".exe", ".com"),
    "CLAUDE_WINDOWS_BATCH_SUFFIXES": (".bat", ".cmd"),
    "CLAUDE_HOME_CLI_PARTS": (".local", "bin", "claude.exe"),
    "CLAUDE_POSIX_CLI_LOCATIONS": (".npm-global/bin/claude", "/usr/local/bin/claude", ".local/bin/claude", "node_modules/.bin/claude", ".yarn/bin/claude", ".claude/local/claude"),
    "CLAUDE_CREDENTIAL_SOURCE_FIELDS": ("tokenSource", "apiKeySource"),
    "CLAUDE_API_KEY_SOURCE_FIELD": "apiKeySource",
    "CLAUDE_ABSENT_SOURCE": "none",
    "CLAUDE_PROVIDER_FIELD": "apiProvider",
    "CLAUDE_FIRST_PARTY_PROVIDER": "firstParty",
}

# Section 8.5: the 17 enums, each member's name and wire value in declaration order.
EXPECTED_ENUMS = {
    "ClaudePermissionMode": (("PROVIDER_DEFAULT", ""), ("DEFAULT", "default"), ("ACCEPT_EDITS", "acceptEdits"), ("PLAN", "plan"), ("BYPASS_PERMISSIONS", "bypassPermissions"), ("DONT_ASK", "dontAsk"), ("AUTO", "auto")),
    "ClaudeEffort": (("PROVIDER_DEFAULT", ""), ("LOW", "low"), ("MEDIUM", "medium"), ("HIGH", "high"), ("XHIGH", "xhigh"), ("MAX", "max")),
    "ClaudeThinkingMode": (("ADAPTIVE", "adaptive"), ("ENABLED", "enabled"), ("DISABLED", "disabled")),
    "ClaudeThinkingDisplay": (("PROVIDER_DEFAULT", ""), ("SUMMARIZED", "summarized"), ("OMITTED", "omitted")),
    "ClaudeSystemPromptMode": (("PRESET", "preset"), ("REPLACE", "replace"), ("FILE", "file")),
    "ClaudeSettingSource": (("USER", "user"), ("PROJECT", "project"), ("LOCAL", "local")),
    "ClaudePermissionPrompts": (("HOST", "host"), ("NONE", "none")),
    "ClaudeBeta": (("CONTEXT_1M", "context-1m-2025-08-07"),),
    "ClaudeHookEvent": (
        ("PRE_TOOL_USE", "PreToolUse"),
        ("POST_TOOL_USE", "PostToolUse"),
        ("POST_TOOL_USE_FAILURE", "PostToolUseFailure"),
        ("USER_PROMPT_SUBMIT", "UserPromptSubmit"),
        ("STOP", "Stop"),
        ("SUBAGENT_STOP", "SubagentStop"),
        ("PRE_COMPACT", "PreCompact"),
        ("NOTIFICATION", "Notification"),
        ("SUBAGENT_START", "SubagentStart"),
        ("PERMISSION_REQUEST", "PermissionRequest"),
    ),
    "ClaudeMemoryScope": (("USER", "user"), ("PROJECT", "project"), ("LOCAL", "local")),
    "ClaudeMcpTransport": (("STDIO", "stdio"), ("SSE", "sse"), ("HTTP", "http")),
    "ClaudeImageMediaType": (("JPEG", "image/jpeg"), ("PNG", "image/png"), ("GIF", "image/gif"), ("WEBP", "image/webp")),
    "ClaudeTurnStatus": (("QUEUED", "queued"), ("RUNNING", "running"), ("COMPLETED", "completed"), ("FAILED", "failed"), ("INTERRUPTED", "interrupted")),
    "ClaudeRateLimitStatus": (("ALLOWED", "allowed"), ("ALLOWED_WARNING", "allowed_warning"), ("REJECTED", "rejected")),
    "ClaudeRateLimitType": (("FIVE_HOUR", "five_hour"), ("SEVEN_DAY", "seven_day"), ("SEVEN_DAY_OPUS", "seven_day_opus"), ("SEVEN_DAY_SONNET", "seven_day_sonnet"), ("SEVEN_DAY_OVERAGE_INCLUDED", "seven_day_overage_included"), ("OVERAGE", "overage")),
    "ClaudeMessageKind": (("USER", "user"), ("ASSISTANT", "assistant")),
    "ClaudeCliFlag": (
        ("FILE", "file"),
        ("RESTRICTED", "restricted"),
        ("AUTOCOMPACT", "autocompact"),
        ("NAME", "name"),
        ("AGENT", "agent"),
        ("BARE", "bare"),
        ("SAFE_MODE", "safe-mode"),
        ("NO_SESSION_PERSISTENCE", "no-session-persistence"),
        ("WORKTREE", "worktree"),
        ("PLUGIN_URL", "plugin-url"),
        ("PERMISSION_PROMPTS", "permission-prompts"),
    ),
}

# Section 9.2 "Field mapping": the 58 ClaudeSpawnRequest fields in declaration order.
SPAWN_REQUEST_FIELDS = (
    "prompt",
    "images",
    "files",
    "cwd",
    "add_dirs",
    "model",
    "fallback_model",
    "effort",
    "thinking",
    "betas",
    "system_prompt",
    "exclude_dynamic_system_prompt_sections",
    "system_prompt_snapshot",
    "builtin_tools",
    "allowed_tools",
    "disallowed_tools",
    "permission_mode",
    "permission_prompts",
    "restricted",
    "sandbox",
    "can_use_tool",
    "hooks",
    "tools",
    "mcp_servers",
    "strict_mcp_config",
    "skills",
    "plugins",
    "agents",
    "main_agent",
    "setting_sources",
    "settings",
    "bare",
    "safe_mode",
    "max_turns",
    "max_budget_usd",
    "task_budget",
    "autocompact",
    "max_output_tokens",
    "session_id",
    "name",
    "resume",
    "continue_conversation",
    "fork_session",
    "resume_session_at",
    "resume_drops_turn",
    "persist_session",
    "enable_file_checkpointing",
    "session_store",
    "worktree",
    "output_schema",
    "include_partial_messages",
    "include_hook_events",
    "forward_subagent_text",
    "cli_path",
    "env",
    "user",
    "load_timeout_ms",
    "timeout_seconds",
)

# Section 8.5: the field order of every other record.
REQUEST_RECORD_FIELDS = {
    "ClaudeImage": ("media_type", "data"),
    "ClaudeThinking": ("mode", "budget_tokens", "display"),
    "ClaudeSystemPrompt": ("mode", "text"),
    "ClaudeSandbox": ("enabled", "auto_allow_bash", "excluded_commands", "allowed_domains", "denied_domains"),
    "ClaudeHookMatcher": ("event", "callbacks", "matcher", "timeout_seconds"),
    "ClaudeMcpServer": ("name", "transport", "command", "args", "env", "url", "headers"),
    "ClaudeAgentDefinition": ("name", "description", "prompt", "tools", "disallowed_tools", "model", "skills", "memory", "mcp_servers", "initial_prompt", "max_turns", "background", "effort", "permission_mode"),
}
HOST_RECORD_FIELDS = {
    "ClaudeHostSettings": ("cli_path", "max_live_sessions"),
    "ClaudeSessionHandle": ("handle_id", "session_id"),
    "ClaudeFailure": ("code", "reason", "next_step"),
    "ClaudePermissionDenial": ("tool_name", "tool_use_id"),
    "ClaudeTurnResult": ("handle_id", "session_id", "status", "result_text", "structured_output", "failure", "num_turns", "duration_ms", "total_cost_usd", "stop_reason", "terminal_reason", "permission_denials", "hooks_applied"),
    "ClaudeModelUsage": ("model", "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "web_search_requests", "cost_usd"),
    "ClaudeTaskUsage": ("task_id", "description", "total_tokens", "tool_uses", "duration_ms"),
    "ClaudeUsageSnapshot": ("handle_id", "session_id", "total_cost_usd", "models", "tasks"),
    "ClaudeRateLimitWindow": ("rate_limit_type", "status", "resets_at", "utilization", "overage_status", "overage_resets_at", "overage_disabled_reason"),
    "ClaudeReadiness": ("cli_path", "cli_version", "signed_in", "failure"),
    "ClaudeModelInfo": ("value", "display_name", "description", "resolved_model", "supports_effort", "supported_effort_levels", "supports_adaptive_thinking", "supports_fast_mode", "supports_auto_mode"),
    "ClaudeSessionSummary": ("session_id", "summary", "last_modified", "file_size", "custom_title", "first_prompt", "git_branch", "cwd", "tag", "created_at"),
    "ClaudeSessionMessage": ("uuid", "session_id", "kind", "text"),
    "ClaudeTurnOutcome": ("result_seen", "is_error", "subtype", "terminal_reason", "api_error_status", "structured_output_missing", "permission_denials", "assistant_errors", "rate_limit_rejected", "interrupted", "budget_expired", "precondition_failure", "stream_failure"),
}
# Section 9.1: the ClaudeSdkTypes fields (classes, functions, message classes, error classes).
SDK_TYPES_FIELDS = frozenset(
    {
        "client_class",
        "options_class",
        "agent_definition_class",
        "hook_matcher_class",
        "create_sdk_mcp_server",
        "tool",
        "list_sessions",
        "get_session_info",
        "get_session_messages",
        "fork_session",
        "assistant_message",
        "result_message",
        "rate_limit_event",
        "task_progress_message",
        "task_notification_message",
        "sdk_error",
        "cli_not_found_error",
        "cli_connection_error",
        "process_error",
        "result_error",
        "cli_json_decode_error",
    }
)

# Section 9.2 tool table: the 15 tool classes and their tool names, in ClaudeTools order.
TOOL_CLASSES = (
    ("CheckClaudeReadyTool", "check_claude_ready"),
    ("ListClaudeModelsTool", "list_claude_models"),
    ("GetClaudeRateLimitsTool", "get_claude_rate_limits"),
    ("SpawnClaudeSessionTool", "spawn_claude_session"),
    ("ContinueClaudeSessionTool", "continue_claude_session"),
    ("ForkClaudeSessionTool", "fork_claude_session"),
    ("LaunchClaudeSubagentsTool", "launch_claude_subagents"),
    ("ListClaudeSessionsTool", "list_claude_sessions"),
    ("GetClaudeSessionInfoTool", "get_claude_session_info"),
    ("GetClaudeSessionMessagesTool", "get_claude_session_messages"),
    ("WaitClaudeTurnTool", "wait_claude_turn"),
    ("GetClaudeTurnResultTool", "get_claude_turn_result"),
    ("SteerClaudeSessionTool", "steer_claude_session"),
    ("InterruptClaudeTurnTool", "interrupt_claude_turn"),
    ("TrackClaudeSessionUsageTool", "track_claude_session_usage"),
)

REQUIRED = inspect.Parameter.empty
POSITIONAL = inspect.Parameter.POSITIONAL_OR_KEYWORD
KEYWORD = inspect.Parameter.KEYWORD_ONLY
# Section 8.5: every public ClaudeHost method's parameters after self, as (name, kind, default).
HOST_SIGNATURES = {
    "check_claude_ready": (),
    "list_claude_models": (),
    "get_claude_rate_limits": (),
    "spawn_claude_session": (("request", POSITIONAL, REQUIRED),),
    "continue_claude_session": (("session_id", POSITIONAL, REQUIRED), ("prompt", POSITIONAL, REQUIRED), ("request", KEYWORD, None)),
    "fork_claude_session": (("session_id", POSITIONAL, REQUIRED), ("up_to_message_id", POSITIONAL, ""), ("title", POSITIONAL, "")),
    "list_claude_sessions": (("directory", POSITIONAL, ""), ("limit", POSITIONAL, None), ("offset", POSITIONAL, 0), ("include_worktrees", POSITIONAL, True)),
    "get_claude_session_info": (("session_id", POSITIONAL, REQUIRED),),
    "get_claude_session_messages": (("session_id", POSITIONAL, REQUIRED), ("limit", POSITIONAL, None), ("offset", POSITIONAL, 0)),
    "wait_claude_turn": (("handle", POSITIONAL, REQUIRED), ("timeout_seconds", KEYWORD, REQUIRED)),
    "get_claude_turn_result": (("handle", POSITIONAL, REQUIRED),),
    "steer_claude_session": (("handle", POSITIONAL, REQUIRED), ("message", POSITIONAL, REQUIRED)),
    "interrupt_claude_turn": (("handle", POSITIONAL, REQUIRED),),
    "track_claude_session_usage": (("handle", POSITIONAL, REQUIRED),),
    "launch_claude_subagents": (("prompts", POSITIONAL, REQUIRED), ("request", POSITIONAL, REQUIRED), ("limit", POSITIONAL, REQUIRED)),
    "aclose": (),
    "get_handle": (("handle_id", POSITIONAL, REQUIRED),),
}
STAR_FUNCTIONS = frozenset(HOST_SIGNATURES) - {"aclose", "get_handle"}


def _parameters(function: object) -> tuple[tuple[str, object, object], ...]:
    # The (name, kind, default) of every parameter after self.
    parameters = list(inspect.signature(function).parameters.values())[1:]
    return tuple((parameter.name, parameter.kind, parameter.default) for parameter in parameters)


def _lf_text(path: Path) -> str:
    # Read a checked-out text file the way its committed blob reads (CRLF becomes LF).
    return path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")


class ImportBoundaryTests(unittest.TestCase):
    """INV-1 and NFR-1: importing the public packages never imports the vendor SDK or, from the tools, the host."""

    def test_public_imports_never_touch_claude_agent_sdk(self) -> None:
        # Import every INV-1 module in a fresh interpreter that records vendor import attempts.
        env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
        completed = subprocess.run(
            [sys.executable, "-c", IMPORT_PROBE_SCRIPT, json.dumps(TOOLS_CHAIN_MODULES), json.dumps(HOST_CHAIN_MODULES)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-3000:])
        report = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual(report["attempts"], [], "a public import tried to import claude_agent_sdk")
        self.assertEqual(report["loaded"], [])
        self.assertFalse(report["host_loaded_by_tools"], "the tools chain imported the ClaudeHost module at run time")


class MarkerContractTests(unittest.TestCase):
    """AC-19 and INV-21: the shared native marker is byte-identical to the request.md contract."""

    def test_marker_bytes_match_the_contract_in_lf_and_crlf_checkouts(self) -> None:
        # Guard the embedded contract first, so a mistyped constant cannot make this test pass or fail falsely.
        self.assertEqual(hashlib.sha256(MARKER_TEXT.encode("utf-8")).hexdigest(), MARKER_SHA256)
        self.assertEqual(len(MARKER_TEXT.encode("utf-8")), 911)
        raw = (REPO_ROOT / "vidbyte" / "harnesses" / "native" / "__init__.py").read_bytes()
        normalized = raw.replace(b"\r\n", b"\n")
        self.assertEqual(normalized.decode("utf-8"), MARKER_TEXT)
        self.assertEqual(hashlib.sha256(normalized).hexdigest(), MARKER_SHA256)
        # A CRLF checkout of the same bytes normalizes to the same hash.
        crlf = normalized.replace(b"\n", b"\r\n")
        self.assertEqual(hashlib.sha256(crlf.replace(b"\r\n", b"\n")).hexdigest(), MARKER_SHA256)


class FailureCodeContractTests(unittest.TestCase):
    """AC-23 and INV-22: 16 contiguous claude.* codes before CODEX_SDK_UNAVAILABLE, each with its next step."""

    def test_claude_codes_form_one_block_before_the_codex_codes(self) -> None:
        from vidbyte.lib.enums.failure import FailureCode

        names = [member.name for member in FailureCode]
        start = names.index("CONFIGURATION_INVALID_ARGUMENT") + 1
        self.assertCountEqual(names[start : start + 16], CLAUDE_MEMBER_NAMES)
        self.assertEqual(names[start + 16], "CODEX_SDK_UNAVAILABLE")
        claude_members = [member for member in FailureCode if member.value.startswith("claude.")]
        self.assertEqual([member.name for member in claude_members], names[start : start + 16])
        for member in claude_members:
            self.assertEqual(member.value, "claude." + member.name.removeprefix("CLAUDE_").lower())

    def test_next_step_mapping_covers_exactly_the_sixteen_codes_verbatim(self) -> None:
        from vidbyte.lib.constants.claude import CLAUDE_FAILURE_NEXT_STEPS

        self.assertEqual(dict(CLAUDE_FAILURE_NEXT_STEPS), dict(CLAUDE_NEXT_STEPS))


class ConstantsContractTests(unittest.TestCase):
    """Section 12.3 row 14: each constant has the value the spec names."""

    def test_every_named_constant_has_its_spec_value(self) -> None:
        constants = importlib.import_module("vidbyte.lib.constants.claude")
        for name, expected in EXPECTED_CONSTANTS.items():
            with self.subTest(constant=name):
                self.assertTrue(hasattr(constants, name), f"missing constant {name}")
                actual = getattr(constants, name)
                self.assertEqual(tuple(actual) if isinstance(expected, tuple) else actual, expected)


class EnumContractTests(unittest.TestCase):
    """AC-27 and FR-23: the 17 enums carry the wire values and are exported from vidbyte.lib.enums."""

    def test_each_enum_has_its_members_and_wire_values_in_order(self) -> None:
        enums_module = importlib.import_module("vidbyte.lib.enums.claude")
        for enum_name, members in EXPECTED_ENUMS.items():
            with self.subTest(enum=enum_name):
                enum_class = getattr(enums_module, enum_name)
                self.assertTrue(issubclass(enum_class, str), f"{enum_name} must be a str enum")
                self.assertEqual(tuple((member.name, member.value) for member in enum_class), members)

    def test_each_enum_is_exported_from_the_enums_package(self) -> None:
        package = importlib.import_module("vidbyte.lib.enums")
        claude_module = importlib.import_module("vidbyte.lib.enums.claude")
        self.assertEqual(set(claude_module.__all__), set(EXPECTED_ENUMS))
        for enum_name in EXPECTED_ENUMS:
            with self.subTest(enum=enum_name):
                self.assertIn(enum_name, package.__all__)
                self.assertIs(getattr(package, enum_name), getattr(claude_module, enum_name))


class RecordContractTests(unittest.TestCase):
    """Sections 8.5, 9.1 and 9.2: the 23 records are frozen, slotted, ordered as specified, and hide env and headers from repr."""

    def test_spawn_request_has_the_58_fields_in_mapping_order(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest

        self.assertEqual(tuple(field.name for field in dataclasses.fields(ClaudeSpawnRequest)), SPAWN_REQUEST_FIELDS)

    def test_spawn_request_defaults_match_the_mapping_table(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest, ClaudeSystemPrompt
        from vidbyte.lib.enums.claude import ClaudeEffort, ClaudePermissionMode, ClaudePermissionPrompts, ClaudeSystemPromptMode

        request = ClaudeSpawnRequest()
        expected = {
            "prompt": "",
            "images": (),
            "files": (),
            "cwd": "",
            "add_dirs": (),
            "model": "",
            "fallback_model": (),
            "effort": ClaudeEffort.PROVIDER_DEFAULT,
            "thinking": None,
            "betas": (),
            "exclude_dynamic_system_prompt_sections": False,
            "system_prompt_snapshot": None,
            "builtin_tools": None,
            "allowed_tools": (),
            "disallowed_tools": (),
            "permission_mode": ClaudePermissionMode.PROVIDER_DEFAULT,
            "permission_prompts": ClaudePermissionPrompts.NONE,
            "restricted": False,
            "sandbox": None,
            "can_use_tool": None,
            "hooks": (),
            "tools": (),
            "mcp_servers": (),
            "strict_mcp_config": False,
            "skills": None,
            "plugins": (),
            "agents": (),
            "main_agent": "",
            "setting_sources": None,
            "settings": "",
            "bare": False,
            "safe_mode": False,
            "max_turns": None,
            "max_budget_usd": None,
            "task_budget": None,
            "autocompact": None,
            "max_output_tokens": None,
            "session_id": "",
            "name": "",
            "resume": "",
            "continue_conversation": False,
            "fork_session": False,
            "resume_session_at": "",
            "resume_drops_turn": "",
            "persist_session": True,
            "enable_file_checkpointing": False,
            "session_store": None,
            "worktree": None,
            "output_schema": None,
            "include_partial_messages": False,
            "include_hook_events": False,
            "forward_subagent_text": False,
            "cli_path": "",
            "user": "",
            "load_timeout_ms": None,
            "timeout_seconds": None,
        }
        for name, value in expected.items():
            with self.subTest(field=name):
                self.assertEqual(getattr(request, name), value)
        self.assertEqual(dict(request.env), {})
        self.assertEqual(request.system_prompt, ClaudeSystemPrompt())
        self.assertEqual(request.system_prompt.mode, ClaudeSystemPromptMode.PRESET)
        self.assertEqual(request.system_prompt.text, "")

    def test_other_records_have_the_specified_field_order(self) -> None:
        request_module = importlib.import_module("vidbyte.lib.dataclasses.claude")
        host_module = importlib.import_module("vidbyte.lib.dataclasses.claude_host")
        tables = ((request_module, REQUEST_RECORD_FIELDS), (host_module, HOST_RECORD_FIELDS))
        for module, table in tables:
            for record_name, field_names in table.items():
                with self.subTest(record=record_name):
                    record = getattr(module, record_name)
                    self.assertEqual(tuple(field.name for field in dataclasses.fields(record)), field_names)
        self.assertEqual({field.name for field in dataclasses.fields(host_module.ClaudeSdkTypes)}, SDK_TYPES_FIELDS)

    def test_every_record_is_a_frozen_slotted_dataclass(self) -> None:
        request_module = importlib.import_module("vidbyte.lib.dataclasses.claude")
        host_module = importlib.import_module("vidbyte.lib.dataclasses.claude_host")
        records = [getattr(request_module, name) for name in ("ClaudeSpawnRequest", *REQUEST_RECORD_FIELDS)]
        records += [getattr(host_module, name) for name in (*HOST_RECORD_FIELDS, "ClaudeSdkTypes")]
        self.assertEqual(len(records), 23)
        for record in records:
            with self.subTest(record=record.__name__):
                self.assertTrue(dataclasses.is_dataclass(record))
                self.assertTrue(record.__dataclass_params__.frozen)
                self.assertIn("__slots__", vars(record))

    def test_env_and_headers_are_hidden_from_repr(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeMcpServer, ClaudeSpawnRequest

        request_fields = {field.name: field for field in dataclasses.fields(ClaudeSpawnRequest)}
        server_fields = {field.name: field for field in dataclasses.fields(ClaudeMcpServer)}
        self.assertFalse(request_fields["env"].repr)
        self.assertFalse(server_fields["env"].repr)
        self.assertFalse(server_fields["headers"].repr)

    def test_record_modules_export_exactly_their_public_records(self) -> None:
        request_module = importlib.import_module("vidbyte.lib.dataclasses.claude")
        host_module = importlib.import_module("vidbyte.lib.dataclasses.claude_host")
        self.assertEqual(set(request_module.__all__), {"ClaudeSpawnRequest", *REQUEST_RECORD_FIELDS})
        self.assertEqual(set(host_module.__all__), {*HOST_RECORD_FIELDS, "ClaudeSdkTypes"})

    def test_operation_error_carries_the_a003_packet(self) -> None:
        from vidbyte.lib.errors import ClaudeOperationError, VidbyteSdkError

        errors_package = importlib.import_module("vidbyte.lib.errors")
        self.assertIn("ClaudeOperationError", errors_package.__all__)
        self.assertTrue(issubclass(ClaudeOperationError, VidbyteSdkError))
        self.assertEqual(
            ClaudeOperationError.DIAGNOSTIC_FIELDS,
            ("error_kind", "expected", "actual", "safe_runtime_details", "likely_causes", "repair_approaches", "related_docs", "relevant_tests"),
        )
        error = ClaudeOperationError("The session is live in this host.", failure_code="claude.session_busy", operation="spawn_claude_session", next_step="Steer it, or fork it.")
        self.assertEqual(error.failure_code, "claude.session_busy")
        self.assertEqual(error.operation, "spawn_claude_session")
        self.assertEqual(error.reason, "The session is live in this host.")
        self.assertEqual(error.next_step, "Steer it, or fork it.")
        self.assertEqual(error.error_kind, "claude.session_busy")
        self.assertEqual(error.actual, "The session is live in this host.")
        self.assertEqual(error.safe_runtime_details, {"operation": "spawn_claude_session"})
        self.assertEqual(tuple(error.repair_approaches), ("Steer it, or fork it.",))
        self.assertEqual(tuple(error.relevant_tests), ("python scripts/run_ci.py",))
        for field_name in ClaudeOperationError.DIAGNOSTIC_FIELDS:
            with self.subTest(field=field_name):
                self.assertTrue(getattr(error, field_name), f"{field_name} must be set")


class HostSurfaceTests(unittest.TestCase):
    """AC-35 and FR-1: ClaudeHost exposes exactly the 15 starred functions plus aclose and get_handle, with the section 8.5 signatures."""

    def test_package_exports_only_the_host(self) -> None:
        package = importlib.import_module("vidbyte.harnesses.native.claude")
        self.assertEqual(list(package.__all__), ["ClaudeHost"])

    def test_public_methods_are_exactly_the_specified_surface(self) -> None:
        from vidbyte.harnesses.native.claude import ClaudeHost

        public = {name for name in dir(ClaudeHost) if not name.startswith("_") and callable(getattr(ClaudeHost, name))}
        self.assertEqual(public, set(HOST_SIGNATURES))
        self.assertEqual(len(STAR_FUNCTIONS), 15)

    def test_each_method_has_its_signature_and_calling_convention(self) -> None:
        from vidbyte.harnesses.native.claude import ClaudeHost

        for name, parameters in HOST_SIGNATURES.items():
            with self.subTest(method=name):
                method = getattr(ClaudeHost, name)
                self.assertEqual(_parameters(method), parameters)
                # D-25: every starred function is a coroutine, and so is aclose; get_handle is synchronous.
                self.assertEqual(inspect.iscoroutinefunction(method), name != "get_handle")
        self.assertEqual(_parameters(ClaudeHost.__init__), (("cli_path", KEYWORD, ""), ("max_live_sessions", KEYWORD, None)))
        self.assertTrue(inspect.iscoroutinefunction(ClaudeHost.__aenter__))
        self.assertTrue(inspect.iscoroutinefunction(ClaudeHost.__aexit__))


class ToolExportTests(unittest.TestCase):
    """Section 12.3 rows 15, 22, 27 and 28: the tool classes and the toolset are exported where the spec puts them."""

    def test_builtins_export_the_fifteen_tool_classes(self) -> None:
        claude_tools = importlib.import_module("vidbyte.tools.builtins.claude")
        builtins_package = importlib.import_module("vidbyte.tools.builtins")
        class_names = [class_name for class_name, _ in TOOL_CLASSES]
        self.assertEqual(list(claude_tools.__all__), sorted(class_names))
        for class_name in class_names:
            with self.subTest(tool=class_name):
                self.assertIn(class_name, builtins_package.__all__)
                self.assertIs(getattr(builtins_package, class_name), getattr(claude_tools, class_name))

    def test_toolsets_export_claude_tools_first(self) -> None:
        toolset_module = importlib.import_module("vidbyte.tools.toolsets.claude")
        toolsets_package = importlib.import_module("vidbyte.tools.toolsets")
        self.assertEqual(list(toolset_module.__all__), ["ClaudeTools"])
        self.assertEqual(toolsets_package.__all__[0], "ClaudeTools")
        self.assertIs(toolsets_package.ClaudeTools, toolset_module.ClaudeTools)


class PackageMetadataTests(unittest.TestCase):
    """AC-33 and FR-21: the claude extra pins claude-agent-sdk and sits directly before codex."""

    def test_claude_extra_is_declared_before_codex(self) -> None:
        data = tomllib.loads(_lf_text(REPO_ROOT / "pyproject.toml"))
        extras = data["project"]["optional-dependencies"]
        self.assertEqual(extras.get("claude"), ["claude-agent-sdk>=0.2.165,<0.3.0"])
        names = list(extras)
        self.assertEqual(names.index("claude") + 1, names.index("codex"))
        self.assertFalse(any("claude-agent-sdk" in requirement for requirement in extras["dev"]), "the dev extra must not gain claude-agent-sdk")


class DocumentationInsertTests(unittest.TestCase):
    """AC-32 and FR-24: REPO_MAP and the harnesses README carry the request.md texts at the specified spots."""

    def test_repo_map_has_the_native_entry_between_harnesses_and_stores(self) -> None:
        lines = _lf_text(REPO_ROOT / "REPO_MAP.md").split("\n")
        start = lines.index("#### `vidbyte/harnesses/`")
        self.assertEqual(lines[start + 1], "")
        self.assertTrue(lines[start + 2].startswith("The base abstraction for wrapping an existing agent workflow"))
        self.assertEqual(lines[start + 3 : start + 9], ["", NATIVE_MAP_HEADING, "", NATIVE_MAP_PARAGRAPH, "", "##### `vidbyte/harnesses/stores/`"])
        self.assertEqual(lines.count(NATIVE_MAP_HEADING), 1)

    def test_harnesses_readme_ends_key_modules_with_the_native_bullet(self) -> None:
        lines = _lf_text(REPO_ROOT / "vidbyte" / "harnesses" / "README.md").split("\n")
        key_modules = lines.index("## Key modules")
        serialization = next(index for index in range(key_modules, len(lines)) if lines[index].startswith("- `serialization.py`:"))
        self.assertEqual(lines[serialization + 1], NATIVE_README_BULLET)
        self.assertEqual(lines[serialization + 2], "")
        self.assertEqual(lines.count(NATIVE_README_BULLET), 1)


if __name__ == "__main__":
    unittest.main()

"""FILE: tests/features/claude_host/claude_host_fixtures.py

PURPOSE: Offline stand-ins for claude-agent-sdk 0.2.165 and the helpers every claude_host test module shares, so the pack runs with no optional extra, no claude binary and no network.
ROLE IN CODEBASE: Imported by every test module in tests/features/claude_host/. It replaces only the vendor SDK, through the one seam the spec names (ClaudeSdkLoader.load returning a ClaudeSdkTypes built from fakes). ClaudeHost, ClaudeLiveSession, ClaudeOptionsTranslator, ClaudeFailureMapper, the records, ToolExecutor and asyncio.to_thread all run for real (spec section 13, "Real seams").
ARCHITECTURE NOTE: FakeClaudeSdk is created per test and builds a client subclass bound to itself, so every client the host constructs records its options and its connect, get_server_info, query, interrupt and disconnect calls on that one state. A client's stream is an asyncio.Queue: query() queues the scripted reply for that prompt, emit() and finish() let a test queue messages by hand, interrupt() answers the open prompt with an interrupted result unless the test arranged otherwise, and disconnect() ends the stream first and then waits on an optional test-held gate, the way the real SDK sends its end-of-stream marker before its terminate and kill escalation. The message, error, agent-definition and hook-matcher fakes carry the 0.2.165 class names, fields and defaults; ClaudeAgentOptions is a dataclass with exactly the real fields, so an unknown keyword fails here as it would against the real SDK.
FUNCTION INVENTORY: FakeClaudeSdk (types, patched, hold, reply, reply_for, release_gates, client_for_session, turn_clients, all_queries); FakeClaudeClient (connect, get_server_info, query, receive_messages, interrupt, disconnect, emit, finish, end_stream, fail_stream); FakeHistory (list_sessions, get_session_info, get_session_messages, fork_session, add_session, add_messages); factories (result_message, interrupted_result, assistant_message, init_message, rate_limit_event, task_progress, task_notification, model_usage_entry, initialize_response, signed_in_account, api_key_account, session_message); TicketTool; ClaudeHostCase (open_host, close_host, spawn, finished, snapshot, client_for, raises); star_calls; eventually; eventually_async; settle; passed_options; is_sdk_default; prompt_text; answer_for.
COMMON MODIFICATION PATTERNS: When the pinned claude-agent-sdk version moves, re-read its types.py and _errors.py and update SDK_OPTION_DEFAULTS and the fake classes together. Add a client behaviour as a FakeClaudeSdk attribute that a test sets before the host constructs the client, and read it inside the client method at call time.
WHAT NOT TO DO IN THIS FILE: 1. Do not import claude-host symbols (ClaudeHost, ClaudeSdkLoader, ClaudeSdkTypes, the records, enums, constants or errors) at module level; import them inside functions, or every test module becomes a collection error until the feature exists. 2. Do not import claude_agent_sdk, start a process or open a socket. 3. Do not put numeric range guards in a fake's __init__ (lint C006 scans tests). 4. Do not reuse one exception instance across clients; the error attributes hold factories that build a fresh exception per raise.
KNOWN EDGE CASES: A held prompt queues only the init message, so its turn stays RUNNING until the test calls finish(). interrupt() answers only a prompt that has no result yet, which models the CLI ignoring an interrupt that arrives after the result (EC-19). A client whose connect() failed still counts its disconnect() calls, because the host must disconnect every client it constructs (INV-8). Messages queued after the stream ended are never yielded.
RELATED DOCS: tests/features/claude_host/FEATURE.md; docs/spec/claude-host/spec.md sections 6.2, 9.1, 9.2 and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/claude_host
"""

from __future__ import annotations

import asyncio
import copy
import dataclasses
import threading
import unittest
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from unittest import mock

from vidbyte.lib.dataclasses.tools import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec
from vidbyte.tools.base import BaseTool

# A CLI path the host keeps as given on every OS: it does not end in .cmd or .bat (spec section 13).
FAKE_CLI_PATH = "C:/fake/claude/bin/claude.exe"
OTHER_CLI_PATH = "C:/other/claude/bin/claude.exe"
# The version the fake initialize reports by default: exactly the minimum the spec requires (D-6).
FAKE_CLI_VERSION = "2.1.296"
WORK_DIR = "C:/work/repo"
OTHER_DIR = "C:/work/other"
DEFAULT_PROMPT = "Summarize the repository layout."

# Upper bound for awaits that finish at once when the implementation is right; it turns a hang into a failure.
HANG_GUARD_SECONDS = 10.0
# A wait or time budget that must run out because the fake never answers in time.
SHORT_TIMEOUT_SECONDS = 0.05
# The patched interrupt grace for AC-37 and AC-40; the real constant is 30 s.
SMALL_GRACE_SECONDS = 0.05
GRACE_TARGET = "vidbyte.harnesses.native.claude.session.CLAUDE_INTERRUPT_GRACE_SECONDS"
WHICH_TARGET = "vidbyte.harnesses.native.claude.probe.shutil.which"

# Rate-limit reset times compared with time.time(): 2100-01-01 and 2000-01-01 (spec section 13, "Time").
FAR_FUTURE_RESET = 4_102_444_800
FAR_PAST_RESET = 946_684_800

# Dummy markers for the secret and error-text checks (AC-24); none of them is a real credential.
ERROR_MARKER = "sdk-error-marker-41c7"
ENV_MARKER = "env-marker-value-8d2e"
HEADER_MARKER = "header-marker-value-3a9f"
PROMPT_MARKER = "prompt-marker-text-6b1d"

# The 8-byte PNG signature, base64-encoded: valid base64 for an image block.
TINY_PNG_BASE64 = "iVBORw0KGgo="

TERMINAL_STATUSES = frozenset({"completed", "failed", "interrupted"})
LIVE_STATUSES = frozenset({"queued", "running"})

# The 16 claude.* failure codes and their next steps, verbatim from spec section 9.2.
CLAUDE_NEXT_STEPS: Mapping[str, str] = {
    "claude.sdk_unavailable": 'Install the extra: pip install "vidbyte-sdk[claude]".',
    "claude.not_installed": "Install Claude Code (the native claude.exe on Windows), or pass cli_path to ClaudeHost.",
    "claude.version_unsupported": "Run claude update.",
    "claude.not_signed_in": "Run claude auth login.",
    "claude.auth_mode_unsupported": "Switch login type: betas and bare need an API key login.",
    "claude.usage_limited": "Wait until the reset time, or use an API key.",
    "claude.billing_error": "Add credits.",
    "claude.model_unknown": "Pick a model from list_claude_models.",
    "claude.session_not_found": "Find the session with list_claude_sessions.",
    "claude.session_busy": "Steer it, or fork it.",
    "claude.budget_exhausted": "Raise the budget, or split the work.",
    "claude.api_error": "Retry with backoff.",
    "claude.permission_denied": "Allow the tool, or change the permission mode.",
    "claude.schema_violation": "Run a repair turn using the raw text.",
    "claude.process_exited": "Respawn, then resume by id.",
    "claude.protocol_mismatch": "Align the SDK and CLI versions.",
}
LIVE_CAP_NEXT_STEP = "Wait for a running session to finish, or interrupt one, then spawn again."
START_FAILURE_NEXT_STEP = "Run check_claude_ready to see why Claude Code did not start; if that check fails the same way, reinstall Claude Code or pass cli_path to ClaudeHost."
INVALID_ARGUMENT_NEXT_STEP = "Correct the argument the reason names, then call again."
UNSUPPORTED_COMBINATION_NEXT_STEP = "Change one of the settings the reason names so that they no longer conflict, then call again."
EMPTY_INPUT_NEXT_STEP = "Pass non-empty text, then call again."
PRECONDITION_NEXT_STEP = "Use the host only inside its async with block on the event loop that entered it (await agent.arun(), not agent.run()), and steer only a RUNNING turn with no steer pending."

INVALID_ARGUMENT = "configuration.invalid_argument"
UNSUPPORTED_COMBINATION = "configuration.unsupported_combination"
INPUT_EMPTY = "input.empty"
PRECONDITION_FAILED = "action.precondition_failed"
CONFIGURATION_CODES = frozenset({INVALID_ARGUMENT, UNSUPPORTED_COMBINATION})

# The 0.2.165 ClaudeAgentOptions fields and their defaults (types.py), in declaration order.
# debug_stderr defaults to sys.stderr in the SDK; None stands in, because no translator should set it.
SDK_OPTION_DEFAULTS: Mapping[str, Any] = {
    "tools": None,
    "allowed_tools": [],
    "system_prompt": None,
    "mcp_servers": {},
    "strict_mcp_config": False,
    "permission_mode": None,
    "continue_conversation": False,
    "resume": None,
    "session_id": None,
    "max_turns": None,
    "max_budget_usd": None,
    "disallowed_tools": [],
    "model": None,
    "fallback_model": None,
    "betas": [],
    "permission_prompt_tool_name": None,
    "cwd": None,
    "cli_path": None,
    "settings": None,
    "add_dirs": [],
    "env": {},
    "extra_args": {},
    "max_buffer_size": None,
    "debug_stderr": None,
    "stderr": None,
    "can_use_tool": None,
    "hooks": None,
    "user": None,
    "include_partial_messages": False,
    "include_hook_events": False,
    "forward_subagent_text": False,
    "verbatim_prompts": False,
    "fork_session": False,
    "resume_session_at": None,
    "resume_drops_turn": None,
    "agents": None,
    "setting_sources": None,
    "skills": None,
    "sandbox": None,
    "plugins": [],
    "max_thinking_tokens": None,
    "thinking": None,
    "effort": None,
    "output_format": None,
    "enable_file_checkpointing": False,
    "session_store": None,
    "session_store_flush": "batched",
    "load_timeout_ms": 60_000,
    "task_budget": None,
}

ANSWER_BEFORE_GATE = "before_gate"
ANSWER_AFTER_GATE = "after_gate"
ANSWER_NEVER = "never"


def _option_field(name: str, default: Any) -> tuple[str, Any, Any]:
    # Lists and dicts get a factory, as the real dataclass declares them.
    if isinstance(default, (list, dict)):
        return (name, Any, field(default_factory=type(default)))
    return (name, Any, field(default=default))


# The options fake: a dataclass with exactly the real fields, so an unknown keyword raises TypeError.
ClaudeAgentOptions = dataclasses.make_dataclass(
    "ClaudeAgentOptions",
    [_option_field(name, default) for name, default in SDK_OPTION_DEFAULTS.items()],
)


def is_sdk_default(name: str, value: Any) -> bool:
    """Return whether an options value is the 0.2.165 default, so the field counts as omitted (spec 9.2 "Omitted")."""
    default = SDK_OPTION_DEFAULTS[name]
    if isinstance(default, list):
        return isinstance(value, (list, tuple)) and len(value) == 0
    if isinstance(default, dict):
        return isinstance(value, Mapping) and len(value) == 0
    if default is None or isinstance(default, bool):
        return value is default
    return bool(value == default)


def passed_options(options: Any) -> dict[str, Any]:
    """Return the options a translator actually set: every field whose value is not the SDK default."""
    return {item.name: getattr(options, item.name) for item in dataclasses.fields(options) if not is_sdk_default(item.name, getattr(options, item.name))}


# ---------------------------------------------------------------------------
# Errors: the 0.2.165 names and constructors (claude_agent_sdk/_errors.py).
# ---------------------------------------------------------------------------


class ClaudeSDKError(Exception):
    """Fake of the SDK's base error."""


class CLIConnectionError(ClaudeSDKError):
    """Fake of the error the SDK raises when the CLI cannot be started or reached."""


class CLINotFoundError(CLIConnectionError):
    """Fake of CLINotFoundError(message, cli_path)."""

    def __init__(self, message: str = "Claude Code not found", cli_path: str | None = None) -> None:
        # The real class appends the path it looked for to the message.
        self.cli_path = cli_path
        super().__init__(f"{message}: {cli_path}" if cli_path else message)


class ProcessError(ClaudeSDKError):
    """Fake of ProcessError(message, exit_code, stderr); like the real one, its text carries the exit code and stderr."""

    def __init__(self, message: str, exit_code: int | None = None, stderr: str | None = None) -> None:
        self.exit_code = exit_code
        self.stderr = stderr
        text = message
        if exit_code is not None:
            text = f"{text} (exit code: {exit_code})"
        if stderr:
            text = f"{text}\nError output: {stderr}"
        super().__init__(text)


class ResultError(ProcessError):
    """Fake of ResultError(message, data, exit_code), which exposes the error result's fields."""

    def __init__(self, message: str, data: dict[str, Any] | None = None, exit_code: int | None = None) -> None:
        payload = data if isinstance(data, dict) else {}
        self.data = payload
        self.subtype = payload.get("subtype") if isinstance(payload.get("subtype"), str) else None
        self.errors = [str(item) for item in payload.get("errors") or []]
        self.result = payload.get("result") if isinstance(payload.get("result"), str) else None
        self.api_error_status = payload.get("api_error_status") if isinstance(payload.get("api_error_status"), int) else None
        self.terminal_reason = payload.get("terminal_reason") if isinstance(payload.get("terminal_reason"), str) else None
        self.session_id = payload.get("session_id") if isinstance(payload.get("session_id"), str) else None
        super().__init__(message, exit_code=exit_code)


class CLIJSONDecodeError(ClaudeSDKError):
    """Fake of CLIJSONDecodeError(line, original_error); its text quotes the start of the bad line."""

    def __init__(self, line: str, original_error: Exception) -> None:
        self.line = line
        self.original_error = original_error
        super().__init__(f"Failed to decode JSON: {line[:100]}...")


class MessageParseError(ClaudeSDKError):
    """Fake of the unexported MessageParseError; it never appears in ClaudeSdkTypes."""

    def __init__(self, message: str, data: dict[str, Any] | None = None) -> None:
        self.data = data
        super().__init__(message)


# ---------------------------------------------------------------------------
# Messages: the 0.2.165 dataclasses the pump dispatches on (types.py).
# ---------------------------------------------------------------------------


@dataclass
class TextBlock:
    """Fake of the assistant text content block."""

    text: str


@dataclass
class AssistantMessage:
    """Fake of AssistantMessage; `error` carries the CLI's error kind as a raw string."""

    content: list[Any]
    model: str
    parent_tool_use_id: str | None = None
    error: str | None = None
    usage: dict[str, Any] | None = None
    message_id: str | None = None
    stop_reason: str | None = None
    session_id: str | None = None
    uuid: str | None = None


@dataclass
class SystemMessage:
    """Fake of SystemMessage(subtype, data)."""

    subtype: str
    data: dict[str, Any]


@dataclass
class TaskProgressMessage(SystemMessage):
    """Fake of TaskProgressMessage; `usage` is the TaskUsage dict (total_tokens, tool_uses, duration_ms)."""

    task_id: str
    description: str
    usage: dict[str, Any]
    uuid: str
    session_id: str
    tool_use_id: str | None = None
    last_tool_name: str | None = None


@dataclass
class TaskNotificationMessage(SystemMessage):
    """Fake of TaskNotificationMessage; it carries a summary instead of a description, and usage may be absent."""

    task_id: str
    status: str
    output_file: str
    summary: str
    uuid: str
    session_id: str
    tool_use_id: str | None = None
    usage: dict[str, Any] | None = None


@dataclass
class ResultMessage:
    """Fake of ResultMessage with every 0.2.165 field; `origin` is None for the prompt's own result."""

    subtype: str
    duration_ms: int
    duration_api_ms: int
    is_error: bool
    num_turns: int
    session_id: str
    stop_reason: str | None = None
    total_cost_usd: float | None = None
    usage: dict[str, Any] | None = None
    result: str | None = None
    structured_output: Any = None
    model_usage: dict[str, Any] | None = None
    permission_denials: list[Any] | None = None
    deferred_tool_use: Any = None
    errors: list[str] | None = None
    api_error_status: int | None = None
    uuid: str | None = None
    terminal_reason: str | None = None
    origin: dict[str, Any] | None = None


@dataclass
class RateLimitInfo:
    """Fake of RateLimitInfo; `raw` keeps the CLI's camelCase payload."""

    status: str
    resets_at: int | None = None
    rate_limit_type: str | None = None
    utilization: float | None = None
    overage_status: str | None = None
    overage_resets_at: int | None = None
    overage_disabled_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class RateLimitEvent:
    """Fake of RateLimitEvent(rate_limit_info, uuid, session_id)."""

    rate_limit_info: RateLimitInfo
    uuid: str
    session_id: str


@dataclass
class SDKSessionInfo:
    """Fake of SDKSessionInfo, the session metadata list_sessions and get_session_info return."""

    session_id: str
    summary: str
    last_modified: int
    file_size: int | None = None
    custom_title: str | None = None
    first_prompt: str | None = None
    git_branch: str | None = None
    cwd: str | None = None
    tag: str | None = None
    created_at: int | None = None


@dataclass
class SessionMessage:
    """Fake of SessionMessage; `message` is the raw API message dict (role and content)."""

    type: str
    uuid: str
    session_id: str
    message: Any
    parent_tool_use_id: str | None = None
    parent_agent_id: str | None = None


@dataclass
class ForkSessionResult:
    """Fake of the result fork_session returns."""

    session_id: str


@dataclass
class AgentDefinition:
    """Fake of AgentDefinition with its camelCase field names."""

    description: str
    prompt: str
    tools: list[str] | None = None
    disallowedTools: list[str] | None = None  # noqa: N815 - the SDK's own field name
    model: str | None = None
    skills: list[str] | None = None
    memory: str | None = None
    mcpServers: list[Any] | None = None  # noqa: N815 - the SDK's own field name
    initialPrompt: str | None = None  # noqa: N815 - the SDK's own field name
    maxTurns: int | None = None  # noqa: N815 - the SDK's own field name
    background: bool | None = None
    effort: Any = None
    permissionMode: str | None = None  # noqa: N815 - the SDK's own field name


@dataclass
class HookMatcher:
    """Fake of HookMatcher(matcher, hooks, timeout)."""

    matcher: str | None = None
    hooks: list[Any] = field(default_factory=list)
    timeout: float | None = None


@dataclass
class SdkMcpTool:
    """Fake of the SdkMcpTool that the SDK's tool() decorator returns."""

    name: str
    description: str
    input_schema: Any
    handler: Callable[[Any], Awaitable[dict[str, Any]]]
    annotations: Any = None


@dataclass
class FakeMcpServer:
    """The in-process server instance a fake create_sdk_mcp_server builds."""

    name: str
    version: str
    tools: list[SdkMcpTool]


def tool(name: str, description: str, input_schema: Any, annotations: Any = None) -> Callable[[Any], SdkMcpTool]:
    """Fake of the SDK's tool() decorator factory: decorating a handler returns an SdkMcpTool."""

    def decorator(handler: Any) -> SdkMcpTool:
        return SdkMcpTool(name=name, description=description, input_schema=input_schema, handler=handler, annotations=annotations)

    return decorator


# ---------------------------------------------------------------------------
# Message factories with realistic defaults.
# ---------------------------------------------------------------------------


def answer_for(prompt: str) -> str:
    """Return the result text the fake CLI answers a prompt with by default."""
    return f"Answer: {prompt}"


def model_usage_entry(*, input_tokens: int = 1200, output_tokens: int = 340, cache_read: int = 800, cache_creation: int = 0, web_search: int = 0, cost_usd: float = 0.0123) -> dict[str, Any]:
    """Build one model's cumulative usage in the CLI's camelCase ModelUsage shape."""
    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "cacheReadInputTokens": cache_read,
        "cacheCreationInputTokens": cache_creation,
        "webSearchRequests": web_search,
        "costUSD": cost_usd,
        "contextWindow": 200_000,
        "maxOutputTokens": 64_000,
    }


def result_message(
    *,
    result: str | None = "Done.",
    subtype: str = "success",
    is_error: bool = False,
    total_cost_usd: float | None = 0.0123,
    num_turns: int = 1,
    duration_ms: int = 4200,
    session_id: str = "",
    structured_output: Any = None,
    model_usage: dict[str, Any] | None = None,
    permission_denials: list[Any] | None = None,
    api_error_status: int | None = None,
    terminal_reason: str | None = "completed",
    stop_reason: str | None = "end_turn",
    origin: dict[str, Any] | None = None,
    errors: list[str] | None = None,
) -> ResultMessage:
    """Build a result message; session_id "" is replaced with the client's session when emitted."""
    return ResultMessage(
        subtype=subtype,
        duration_ms=duration_ms,
        duration_api_ms=3100,
        is_error=is_error,
        num_turns=num_turns,
        session_id=session_id,
        stop_reason=stop_reason,
        total_cost_usd=total_cost_usd,
        usage={"input_tokens": 1200, "output_tokens": 340, "cache_read_input_tokens": 800, "cache_creation_input_tokens": 0},
        result=result,
        structured_output=structured_output,
        model_usage=model_usage if model_usage is not None else {"claude-sonnet-4-5": model_usage_entry(cost_usd=total_cost_usd or 0.0)},
        permission_denials=permission_denials if permission_denials is not None else [],
        errors=errors,
        api_error_status=api_error_status,
        uuid=str(uuid.uuid4()),
        terminal_reason=terminal_reason,
        origin=origin,
    )


def interrupted_result(*, total_cost_usd: float | None = 0.008) -> ResultMessage:
    """Build the result the CLI sends for a prompt an interrupt stopped (terminal_reason aborted_streaming)."""
    return result_message(result=None, subtype="error_during_execution", is_error=True, total_cost_usd=total_cost_usd, terminal_reason="aborted_streaming", stop_reason=None, errors=[])


def assistant_message(text: str = "Working on it.", *, error: str | None = None, model: str = "claude-sonnet-4-5") -> AssistantMessage:
    """Build an assistant message; `error` is the CLI's error kind, such as "rate_limit" or "model_not_found"."""
    return AssistantMessage(content=[TextBlock(text=text)], model=model, error=error, usage={"input_tokens": 10, "output_tokens": 5}, message_id=f"msg_{uuid.uuid4().hex[:12]}", session_id="", uuid=str(uuid.uuid4()))


def init_message() -> SystemMessage:
    """Build the system init message the CLI sends at the start of each prompt; the pump must skip it."""
    return SystemMessage(subtype="init", data={"type": "system", "subtype": "init", "model": "claude-sonnet-4-5", "tools": ["Read", "Grep"], "claude_code_version": FAKE_CLI_VERSION})


def rate_limit_event(
    rate_limit_type: str | None,
    status: str,
    *,
    resets_at: int | None = None,
    utilization: float | None = None,
    overage_status: str | None = None,
    overage_resets_at: int | None = None,
    overage_disabled_reason: str | None = None,
) -> RateLimitEvent:
    """Build a rate-limit event with the parsed info fields and the raw camelCase payload the SDK keeps."""
    raw = {"status": status, "resetsAt": resets_at, "rateLimitType": rate_limit_type, "utilization": utilization, "overageStatus": overage_status, "overageResetsAt": overage_resets_at, "overageDisabledReason": overage_disabled_reason}
    info = RateLimitInfo(
        status=status,
        resets_at=resets_at,
        rate_limit_type=rate_limit_type,
        utilization=utilization,
        overage_status=overage_status,
        overage_resets_at=overage_resets_at,
        overage_disabled_reason=overage_disabled_reason,
        raw={key: value for key, value in raw.items() if value is not None},
    )
    return RateLimitEvent(rate_limit_info=info, uuid=str(uuid.uuid4()), session_id="")


def task_progress(task_id: str, description: str, *, total_tokens: int, tool_uses: int, duration_ms: int) -> TaskProgressMessage:
    """Build a background-task progress message with its TaskUsage figures."""
    usage = {"total_tokens": total_tokens, "tool_uses": tool_uses, "duration_ms": duration_ms}
    return TaskProgressMessage(subtype="task_progress", data={"task_id": task_id, "description": description, "usage": usage}, task_id=task_id, description=description, usage=usage, uuid=str(uuid.uuid4()), session_id="", tool_use_id="toolu_task", last_tool_name="Grep")


def task_notification(task_id: str, summary: str, *, status: str = "completed", usage: dict[str, Any] | None = None) -> TaskNotificationMessage:
    """Build a background-task notification; usage may be absent, as in the SDK."""
    return TaskNotificationMessage(subtype="task_notification", data={"task_id": task_id, "status": status, "summary": summary}, task_id=task_id, status=status, output_file=f"tasks/{task_id}.output", summary=summary, uuid=str(uuid.uuid4()), session_id="", usage=usage)


def signed_in_account() -> dict[str, Any]:
    """Return an initialize account for a subscription login: a token source and no API key (A-7)."""
    return {"email": "developer@example.test", "organization": "Example Org", "subscriptionType": "max", "tokenSource": "claude.ai", "apiKeySource": "none", "apiProvider": "firstParty"}


def api_key_account() -> dict[str, Any]:
    """Return an initialize account for an API-key login."""
    return {"apiKeySource": "ANTHROPIC_API_KEY", "apiProvider": "firstParty"}


def default_models() -> list[dict[str, Any]]:
    """Return the initialize model list the fake reports unless a test replaces it."""
    return [
        {"value": "default", "displayName": "Default (recommended)", "description": "Opus with 1M context", "resolvedModel": "claude-opus-4-7", "supportsEffort": True, "supportedEffortLevels": ["low", "medium", "high"], "supportsAdaptiveThinking": True, "supportsFastMode": True, "supportsAutoMode": True},
        {"value": "sonnet", "displayName": "Sonnet", "description": "Everyday tasks", "supportsEffort": False},
    ]


def initialize_response(*, version: str | None = FAKE_CLI_VERSION, account: dict[str, Any] | None = None, models: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build the initialize response get_server_info returns; version None omits claude_code_version."""
    info: dict[str, Any] = {
        "commands": [],
        "agents": [],
        "output_style": "default",
        "available_output_styles": ["default"],
        "models": models if models is not None else default_models(),
        "account": account if account is not None else signed_in_account(),
    }
    if version is not None:
        info["claude_code_version"] = version
    return info


def default_reply(prompt: str) -> list[Any]:
    """Return what the fake CLI sends for a prompt nobody scripted: init, one assistant message, a success result."""
    return [init_message(), assistant_message(f"Looking at: {prompt}"), result_message(result=answer_for(prompt))]


def session_message(kind: str, content: Any, *, session_id: str) -> SessionMessage:
    """Build one transcript entry as get_session_messages returns it."""
    return SessionMessage(type=kind, uuid=str(uuid.uuid4()), session_id=session_id, message={"role": kind, "content": content})


def prompt_text(prompt: Any) -> str:
    """Return the text of a recorded prompt: the string itself, or the text block of an image message."""
    if isinstance(prompt, str):
        return prompt
    for message in prompt:
        for block in message.get("message", {}).get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                return str(block.get("text", ""))
    return ""


def _is_own_result(message: ResultMessage) -> bool:
    # D-28: only a result whose origin is absent or human answers the prompt.
    return message.origin is None or (isinstance(message.origin, dict) and message.origin.get("kind") == "human")


def _cli_session_id(options: Any) -> str:
    # The id the CLI would run under: the chosen one, else the resumed one unless forking, else a fresh one.
    chosen = getattr(options, "session_id", None)
    if chosen:
        return str(chosen)
    resumed = getattr(options, "resume", None)
    if resumed and not getattr(options, "fork_session", False):
        return str(resumed)
    return str(uuid.uuid4())


END_OF_STREAM = object()


# ---------------------------------------------------------------------------
# The client and the per-test SDK state.
# ---------------------------------------------------------------------------


class FakeClaudeClient:
    """Fake of ClaudeSDKClient(options=None, transport=None); each instance records what the host did with it."""

    sdk: FakeClaudeSdk

    def __init__(self, options: Any = None, transport: Any = None) -> None:
        # Record the constructor as the host called it; the stream starts empty and open.
        self.options = options
        self.transport = transport
        self.calls: list[str] = []
        self.queries: list[Any] = []
        self.stream: asyncio.Queue[Any] = asyncio.Queue()
        self.session = _cli_session_id(options)
        self.connected = False
        self.ended = False
        self.answered = 0
        self.interrupt_calls = 0
        self.disconnect_calls = 0
        self.disconnect_finished = False
        self.disconnect_cancelled = False
        self.sdk.clients.append(self)

    async def connect(self, prompt: Any = None) -> None:
        """Connect, unless the test holds the connect open or makes it fail."""
        self.calls.append("connect")
        if self.sdk.connect_gate is not None:
            await self.sdk.connect_gate.wait()
        if self.sdk.connect_error is not None:
            raise self.sdk.connect_error()
        self.connected = True
        self.sdk.connected_now += 1
        self.sdk.max_connected = max(self.sdk.max_connected, self.sdk.connected_now)

    async def get_server_info(self) -> dict[str, Any] | None:
        """Return the initialize response; hooks_applied is reported only when the options registered hooks."""
        self.calls.append("get_server_info")
        info = copy.deepcopy(self.sdk.server_info)
        if getattr(self.options, "hooks", None):
            info.setdefault("hooks_applied", True)
        return info

    async def query(self, prompt: Any, session_id: str = "default") -> None:
        """Record the prompt (draining an image message stream), then queue the scripted reply for it."""
        self.calls.append("query")
        if not isinstance(prompt, str):
            prompt = [message async for message in prompt]
        self.queries.append(prompt)
        for message in self.sdk.reply_for(prompt_text(prompt)):
            self.emit(message)

    async def receive_messages(self) -> AsyncIterator[Any]:
        """Yield queued messages until the stream ends; a queued exception is raised from the read, like a broken stream."""
        self.calls.append("receive_messages")
        while not self.ended:
            item = await self.stream.get()
            if item is END_OF_STREAM:
                self.ended = True
                return
            if isinstance(item, BaseException):
                raise item
            yield item

    async def interrupt(self) -> None:
        """Record the interrupt; then raise, answer, hold or stay silent, as the test arranged."""
        self.calls.append("interrupt")
        self.interrupt_calls += 1
        if self.sdk.interrupt_error is not None:
            raise self.sdk.interrupt_error()
        if self.sdk.interrupt_answer == ANSWER_BEFORE_GATE:
            self._answer_interrupt()
        if self.sdk.interrupt_gate is not None:
            await self.sdk.interrupt_gate.wait()
        if self.sdk.interrupt_answer == ANSWER_AFTER_GATE:
            self._answer_interrupt()

    async def disconnect(self) -> None:
        """End the stream first, then wait on the test's gate; record whether the disconnect finished or was cancelled."""
        self.calls.append("disconnect")
        self.disconnect_calls += 1
        self.stream.put_nowait(END_OF_STREAM)
        try:
            if self.sdk.disconnect_gate is not None:
                await self.sdk.disconnect_gate.wait()
        except asyncio.CancelledError:
            self.disconnect_cancelled = True
            raise
        if self.connected:
            self.connected = False
            self.sdk.connected_now -= 1
        self.disconnect_finished = True
        if self.sdk.disconnect_error is not None:
            raise self.sdk.disconnect_error()

    def emit(self, message: Any) -> None:
        """Queue one message on the stream, stamping this client's session id where the message left it empty."""
        if dataclasses.is_dataclass(message) and not isinstance(message, type) and getattr(message, "session_id", None) == "":
            message = dataclasses.replace(message, session_id=self.session)
        if isinstance(message, ResultMessage) and _is_own_result(message):
            self.answered += 1
        self.stream.put_nowait(message)

    def finish(self, text: str = "Done.", **fields: Any) -> None:
        """Answer the open prompt with a result, as the CLI does when a held turn ends."""
        self.emit(result_message(result=text, **fields))

    def end_stream(self) -> None:
        """End the stream without a result, as a process that exits mid-turn does."""
        self.stream.put_nowait(END_OF_STREAM)

    def fail_stream(self, error: BaseException) -> None:
        """Make the next read raise this error, as a broken stream does."""
        self.stream.put_nowait(error)

    def _answer_interrupt(self) -> None:
        # The CLI ends an open prompt when interrupted, and ignores an interrupt once that prompt has its result.
        if self.answered < len(self.queries) and not self.ended:
            self.emit(self.sdk.interrupt_reply())


@dataclass
class HistoryCall:
    """One call into a fake history function: its name, the thread it ran on and its arguments."""

    function: str
    thread_id: int
    arguments: dict[str, Any]


class FakeHistory:
    """Synchronous fakes of list_sessions, get_session_info, get_session_messages and fork_session that record their thread."""

    def __init__(self) -> None:
        # Session files keyed by id, the calls made, and the errors a test wants raised.
        self.infos: dict[str, SDKSessionInfo] = {}
        self.transcripts: dict[str, list[SessionMessage]] = {}
        self.calls: list[HistoryCall] = []
        self.read_error: Callable[[], BaseException] | None = None
        self.fork_error: Callable[[], BaseException] | None = None
        self.forks: list[str] = []

    def list_sessions(self, directory: str | None = None, limit: int | None = None, offset: int = 0, include_worktrees: bool = True) -> list[SDKSessionInfo]:
        """Return the known sessions, most recent first, as the SDK sorts them."""
        self._record("list_sessions", directory=directory, limit=limit, offset=offset, include_worktrees=include_worktrees)
        ordered = sorted(self.infos.values(), key=lambda info: info.last_modified, reverse=True)[offset:]
        return ordered if limit is None else ordered[:limit]

    def get_session_info(self, session_id: str, directory: str | None = None) -> SDKSessionInfo | None:
        """Return one session's metadata, or None for an unknown id, as the SDK does."""
        self._record("get_session_info", session_id=session_id, directory=directory)
        return self.infos.get(session_id)

    def get_session_messages(self, session_id: str, directory: str | None = None, limit: int | None = None, offset: int = 0) -> list[SessionMessage]:
        """Return one session's transcript, or [] for an unknown id, as the SDK does."""
        self._record("get_session_messages", session_id=session_id, directory=directory, limit=limit, offset=offset)
        messages = self.transcripts.get(session_id, [])[offset:]
        return messages if limit is None else messages[:limit]

    def fork_session(self, session_id: str, directory: str | None = None, up_to_message_id: str | None = None, title: str | None = None) -> ForkSessionResult:
        """Copy a session offline and return the new id, or raise what the test arranged."""
        self._record("fork_session", session_id=session_id, directory=directory, up_to_message_id=up_to_message_id, title=title)
        if self.fork_error is not None:
            raise self.fork_error()
        forked = str(uuid.uuid4())
        self.forks.append(forked)
        return ForkSessionResult(session_id=forked)

    def add_session(self, session_id: str | None = None, *, cwd: str | None = WORK_DIR, summary: str = "Fix the parser bug", last_modified: int = 1_760_000_000_000, **extra: Any) -> str:
        """Register a session file and return its id."""
        chosen = session_id or str(uuid.uuid4())
        self.infos[chosen] = SDKSessionInfo(session_id=chosen, summary=summary, last_modified=last_modified, cwd=cwd, **extra)
        return chosen

    def add_messages(self, session_id: str, *messages: SessionMessage) -> None:
        """Register a session's transcript entries."""
        self.transcripts.setdefault(session_id, []).extend(messages)

    def calls_to(self, function: str) -> list[HistoryCall]:
        """Return the recorded calls to one history function, in order."""
        return [call for call in self.calls if call.function == function]

    def _record(self, function: str, **arguments: Any) -> None:
        # Record the call and its thread first, so a test can check the thread even when the call fails.
        self.calls.append(HistoryCall(function=function, thread_id=threading.get_ident(), arguments=arguments))
        if function != "fork_session" and self.read_error is not None:
            raise self.read_error()


class FakeClaudeSdk:
    """One test's fake claude-agent-sdk: the bound client class, the scripted replies, the client behaviours and the history files."""

    def __init__(self) -> None:
        # Every client the host constructs, and the replies and behaviours they read at call time.
        self.clients: list[FakeClaudeClient] = []
        self.server_info: dict[str, Any] = initialize_response()
        self.replies: dict[str, list[Any]] = {}
        self.held: set[str] = set()
        self.connect_gate: asyncio.Event | None = None
        self.connect_error: Callable[[], BaseException] | None = None
        self.interrupt_error: Callable[[], BaseException] | None = None
        self.interrupt_gate: asyncio.Event | None = None
        self.interrupt_answer = ANSWER_AFTER_GATE
        self.interrupt_reply: Callable[[], Any] = interrupted_result
        self.disconnect_gate: asyncio.Event | None = None
        self.disconnect_error: Callable[[], BaseException] | None = None
        self.connected_now = 0
        self.max_connected = 0
        self.history = FakeHistory()
        self.mcp_servers: list[dict[str, Any]] = []
        self.client_class = type("ClaudeSDKClient", (FakeClaudeClient,), {"sdk": self})

    def types(self) -> Any:
        """Build the real ClaudeSdkTypes record from these fakes (imported here, because the feature may not exist yet)."""
        from vidbyte.lib.dataclasses.claude_host import ClaudeSdkTypes

        return ClaudeSdkTypes(
            client_class=self.client_class,
            options_class=ClaudeAgentOptions,
            agent_definition_class=AgentDefinition,
            hook_matcher_class=HookMatcher,
            create_sdk_mcp_server=self.create_sdk_mcp_server,
            tool=tool,
            list_sessions=self.history.list_sessions,
            get_session_info=self.history.get_session_info,
            get_session_messages=self.history.get_session_messages,
            fork_session=self.history.fork_session,
            assistant_message=AssistantMessage,
            result_message=ResultMessage,
            rate_limit_event=RateLimitEvent,
            task_progress_message=TaskProgressMessage,
            task_notification_message=TaskNotificationMessage,
            sdk_error=ClaudeSDKError,
            cli_not_found_error=CLINotFoundError,
            cli_connection_error=CLIConnectionError,
            process_error=ProcessError,
            result_error=ResultError,
            cli_json_decode_error=CLIJSONDecodeError,
        )

    def patched(self) -> Any:
        """Patch the one seam, ClaudeSdkLoader.load, to return these fakes for as long as the patch is active."""
        from vidbyte.harnesses.native.claude.sdk import ClaudeSdkLoader

        return mock.patch.object(ClaudeSdkLoader, "load", return_value=self.types())

    def create_sdk_mcp_server(self, name: str, version: str = "1.0.0", tools: list[Any] | None = None) -> dict[str, Any]:
        """Fake of create_sdk_mcp_server: the McpSdkServerConfig dict around an in-process server."""
        config = {"type": "sdk", "name": name, "instance": FakeMcpServer(name=name, version=version, tools=list(tools or []))}
        self.mcp_servers.append(config)
        return config

    def hold(self, *prompts: str) -> None:
        """Keep these prompts open: query() queues only the init message, so the turn stays RUNNING until the test answers."""
        self.held.update(prompts)

    def reply(self, prompt: str, *messages: Any) -> None:
        """Script exactly what the CLI sends after this prompt (messages, exceptions or END_OF_STREAM)."""
        self.replies[prompt] = list(messages)

    def reply_for(self, text: str) -> list[Any]:
        """Return what the CLI sends after a prompt: held, scripted, or the default success reply."""
        if text in self.held:
            return [init_message()]
        if text in self.replies:
            return list(self.replies[text])
        return default_reply(text)

    def release_gates(self) -> None:
        """Open every gate a test may still hold, so cleanup never waits on a held connect, interrupt or disconnect."""
        for gate in (self.connect_gate, self.interrupt_gate, self.disconnect_gate):
            if gate is not None:
                gate.set()

    def client_for_session(self, session_id: str) -> FakeClaudeClient | None:
        """Return the latest client running this session id, or None."""
        matches = [client for client in self.clients if client.session == session_id]
        return matches[-1] if matches else None

    def turn_clients(self) -> list[FakeClaudeClient]:
        """Return the clients that sent at least one prompt, in construction order."""
        return [client for client in self.clients if client.queries]

    def all_queries(self) -> list[str]:
        """Return the text of every prompt any client sent."""
        return [prompt_text(query) for client in self.clients for query in client.queries]


# ---------------------------------------------------------------------------
# A custom BaseTool for request.tools (AC-20).
# ---------------------------------------------------------------------------


class TicketTool(BaseTool):
    """A small custom tool a developer hands to Claude through request.tools; outcome is "ok", "error" or "raise"."""

    def __init__(self, name: str, permission: ToolPermission, *, outcome: str = "ok") -> None:
        self._name = name
        self._permission = permission
        self._outcome = outcome
        self.calls: list[dict[str, Any]] = []

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self._name,
            description=f"Read or change one ticket in the tracker ({self._name}).",
            parameters=(ToolParameter(name="ticket", type="string", description="The ticket id, such as T-7."),),
            permission=self._permission,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Record the call, then answer the way the test asked.
        self.calls.append(dict(call.arguments))
        if self._outcome == "raise":
            raise RuntimeError("ticket backend unavailable")
        if self._outcome == "error":
            return ToolResult.error(self._name, "ticket not found")
        return ToolResult.success(self._name, f"ticket {call.arguments.get('ticket')} is open")


# ---------------------------------------------------------------------------
# Loop helpers and the host test base.
# ---------------------------------------------------------------------------


async def eventually(predicate: Callable[[], bool], what: str) -> None:
    """Yield to the loop until predicate() holds; fail after HANG_GUARD_SECONDS so a broken implementation fails instead of hanging."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + HANG_GUARD_SECONDS
    spins = 0
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError(f"Timed out waiting for: {what}")
        spins += 1
        await asyncio.sleep(0 if spins < 200 else 0.002)


async def settle(rounds: int = 100) -> None:
    """Let every ready callback run; used before asserting that something did not happen."""
    for _ in range(rounds):
        await asyncio.sleep(0)


async def eventually_async(fetch: Callable[[], Awaitable[Any]], check: Callable[[Any], bool], what: str) -> Any:
    """Await fetch() until check() accepts its value, and return that value; fail after HANG_GUARD_SECONDS."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + HANG_GUARD_SECONDS
    while True:
        value = await fetch()
        if check(value):
            return value
        if loop.time() > deadline:
            raise AssertionError(f"Timed out waiting for: {what} (last value {value!r})")
        await asyncio.sleep(0.002)


def star_calls(host: Any, handle: Any) -> list[tuple[str, Callable[[], Awaitable[Any]]]]:
    """Return one call per star function, each with valid arguments, so a test can try all fifteen in the section 8.5 order."""
    from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest

    session_id = str(uuid.uuid4())
    request = ClaudeSpawnRequest(prompt=DEFAULT_PROMPT, cwd=WORK_DIR)
    return [
        ("check_claude_ready", lambda: host.check_claude_ready()),
        ("list_claude_models", lambda: host.list_claude_models()),
        ("get_claude_rate_limits", lambda: host.get_claude_rate_limits()),
        ("spawn_claude_session", lambda: host.spawn_claude_session(request)),
        ("continue_claude_session", lambda: host.continue_claude_session(session_id, "next")),
        ("fork_claude_session", lambda: host.fork_claude_session(session_id)),
        ("list_claude_sessions", lambda: host.list_claude_sessions()),
        ("get_claude_session_info", lambda: host.get_claude_session_info(session_id)),
        ("get_claude_session_messages", lambda: host.get_claude_session_messages(session_id)),
        ("wait_claude_turn", lambda: host.wait_claude_turn(handle, timeout_seconds=SHORT_TIMEOUT_SECONDS)),
        ("get_claude_turn_result", lambda: host.get_claude_turn_result(handle)),
        ("steer_claude_session", lambda: host.steer_claude_session(handle, "focus on tests")),
        ("interrupt_claude_turn", lambda: host.interrupt_claude_turn(handle)),
        ("track_claude_session_usage", lambda: host.track_claude_session_usage(handle)),
        ("launch_claude_subagents", lambda: host.launch_claude_subagents(("Review src/.",), request, 1)),
    ]


class ClaudeHostCase(unittest.IsolatedAsyncioTestCase):
    """Base for tests that drive an entered ClaudeHost over one FakeClaudeSdk; only the vendor SDK is faked."""

    patch_sdk = True

    async def asyncSetUp(self) -> None:
        # Each test gets its own fake SDK, patched in through the one seam the spec names.
        self.fake = FakeClaudeSdk()
        self.closed_hosts: list[Any] = []
        if self.patch_sdk:
            self.enterContext(self.fake.patched())

    async def open_host(self, **settings: Any) -> Any:
        """Enter a ClaudeHost (with FAKE_CLI_PATH unless the test passes cli_path) and close it at cleanup."""
        from vidbyte.harnesses.native.claude import ClaudeHost

        settings.setdefault("cli_path", FAKE_CLI_PATH)
        host = ClaudeHost(**settings)
        await asyncio.wait_for(host.__aenter__(), HANG_GUARD_SECONDS)
        self.addAsyncCleanup(self._cleanup_host, host)
        return host

    async def close_host(self, host: Any) -> None:
        """Close the host now, opening any held gate first so the close cannot wait forever."""
        self.fake.release_gates()
        self.closed_hosts.append(host)
        await asyncio.wait_for(host.aclose(), HANG_GUARD_SECONDS)

    async def spawn(self, host: Any, prompt: str = DEFAULT_PROMPT, **fields: Any) -> Any:
        """Spawn a turn for a request in WORK_DIR, built from the given fields."""
        from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest

        fields.setdefault("cwd", WORK_DIR)
        return await asyncio.wait_for(host.spawn_claude_session(ClaudeSpawnRequest(prompt=prompt, **fields)), HANG_GUARD_SECONDS)

    async def finished(self, host: Any, handle: Any) -> Any:
        """Wait for the turn to end and return its terminal snapshot."""
        result = await asyncio.wait_for(host.wait_claude_turn(handle, timeout_seconds=HANG_GUARD_SECONDS), HANG_GUARD_SECONDS + 1)
        self.assertIn(result.status.value, TERMINAL_STATUSES, "the turn never reached a terminal status")
        return result

    async def snapshot(self, host: Any, handle: Any) -> Any:
        """Return the turn's current snapshot."""
        return await asyncio.wait_for(host.get_claude_turn_result(handle), HANG_GUARD_SECONDS)

    async def client_for(self, handle: Any) -> FakeClaudeClient:
        """Return the fake client running this handle's turn, once the host has constructed it."""
        await eventually(lambda: self.fake.client_for_session(handle.session_id) is not None, f"a client for session {handle.session_id}")
        client = self.fake.client_for_session(handle.session_id)
        assert client is not None
        return client

    async def raises(self, awaitable: Awaitable[Any], code: str) -> Any:
        """Await a host call that must raise ClaudeOperationError with this failure code, and return the error."""
        from vidbyte.lib.errors import ClaudeOperationError

        with self.assertRaises(ClaudeOperationError) as caught:
            await asyncio.wait_for(awaitable, HANG_GUARD_SECONDS)
        self.assertEqual(caught.exception.failure_code, code, caught.exception.reason)
        return caught.exception

    async def _cleanup_host(self, host: Any) -> None:
        # A test that already closed its host has nothing left to clean up.
        if any(host is closed for closed in self.closed_hosts):
            return
        await self.close_host(host)

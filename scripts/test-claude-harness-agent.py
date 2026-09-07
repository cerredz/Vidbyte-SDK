"""FILE: scripts/test-claude-harness-agent.py

PURPOSE: Verifies every Claude harness agent test case from its design doc offline.
ROLE IN CODEBASE: Executable gate for docs/design/claude-harness-agent.md section 10.
ARCHITECTURE NOTE: A fake claude_agent_sdk module is injected; no CLI or API key is used.
COMMON MODIFICATION PATTERNS: Add a check function and register it in the suite list.
KNOWN EDGE CASES: The fake stream must reproduce the SDK's raise-after-error-result behavior.
RELATED DOCS: docs/design/claude-harness-agent.md.
TESTS: python scripts/test-claude-harness-agent.py
"""

from __future__ import annotations

import asyncio
import sys
import types
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# Fake claude_agent_sdk
# ---------------------------------------------------------------------------


class ClaudeSDKError(Exception):
    """Base fake SDK error."""


class CLINotFoundError(ClaudeSDKError):
    """Fake missing-CLI error."""


class CLIConnectionError(ClaudeSDKError):
    """Fake unreachable-CLI error."""


class ProcessError(ClaudeSDKError):
    """Fake CLI subprocess failure."""


class CLIJSONDecodeError(ClaudeSDKError):
    """Fake unparsable CLI output error."""


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ThinkingBlock:
    thinking: str
    type: str = "thinking"

    def __getattribute__(self, name: str) -> Any:
        # Records any read of the private thinking text so a test can assert exclusion.
        if name == "thinking":
            THINKING_READS.append(1)
        return object.__getattribute__(self, name)


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: str = "tool_use"


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: list[Any] = field(default_factory=list)
    is_error: bool = False
    type: str = "tool_result"


@dataclass
class AssistantMessage:
    content: list[Any]
    type: str = "assistant"


@dataclass
class SystemMessage:
    data: dict[str, Any] = field(default_factory=dict)
    type: str = "system"


@dataclass
class ResultMessage:
    subtype: str = "success"
    terminal_reason: str = "stop"
    session_id: str = ""
    result: str | None = None
    total_cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    duration_ms: int | None = None
    duration_api_ms: int | None = None
    num_turns: int | None = None
    structured_output: dict[str, Any] | None = None
    type: str = "result"


class ClaudeAgentOptions:
    """Records the option kwargs the adapter emitted for one query."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


THINKING_READS: list[int] = []
CAPTURED_OPTIONS: list[ClaudeAgentOptions] = []
CLOSED_STREAMS: list[str] = []
SCRIPTED_TURNS: list[Any] = []


class _FakeStream:
    """Async iterator over one scripted turn; records whether aclose ran."""

    def __init__(self, plan: Any) -> None:
        self._messages = list(plan.get("messages", ()))
        self._raise = plan.get("raise")
        self._supports_close = plan.get("supports_close", True)
        self._index = 0
        if self._supports_close:
            self.aclose = self._aclose  # type: ignore[method-assign]

    def __aiter__(self) -> _FakeStream:
        return self

    async def __anext__(self) -> Any:
        if self._index < len(self._messages):
            message = self._messages[self._index]
            self._index += 1
            return message
        if self._raise is not None:
            raise self._raise
        raise StopAsyncIteration

    async def _aclose(self) -> None:
        CLOSED_STREAMS.append("closed")


def query(*, prompt: str, options: ClaudeAgentOptions) -> _FakeStream:
    # Returns the next scripted turn and records the options it was called with.
    CAPTURED_OPTIONS.append(options)
    plan = SCRIPTED_TURNS.pop(0) if SCRIPTED_TURNS else {"messages": ()}
    plan.setdefault("prompt", prompt)
    LAST_PROMPTS.append(prompt)
    return _FakeStream(plan)


LAST_PROMPTS: list[str] = []


def install_fake_sdk() -> None:
    # Injects the fake module so the adapter's lazy import resolves to this file.
    module = types.ModuleType("claude_agent_sdk")
    for name in (
        "AssistantMessage", "ClaudeAgentOptions", "ClaudeSDKError",
        "CLIConnectionError", "CLIJSONDecodeError", "CLINotFoundError",
        "ProcessError", "ResultMessage", "SystemMessage", "TextBlock",
        "ThinkingBlock", "ToolResultBlock", "ToolUseBlock", "query",
    ):
        setattr(module, name, globals()[name])
    sys.modules["claude_agent_sdk"] = module


def uninstall_fake_sdk() -> None:
    # Removes the fake module so a test can exercise the missing-extra path.
    sys.modules.pop("claude_agent_sdk", None)


def reset_fake() -> None:
    # Clears every recorded interaction between checks.
    THINKING_READS.clear()
    CAPTURED_OPTIONS.clear()
    CLOSED_STREAMS.clear()
    SCRIPTED_TURNS.clear()
    LAST_PROMPTS.clear()


def script(**overrides: Any) -> dict[str, Any]:
    # Builds one scripted turn producing a successful text answer by default.
    result = ResultMessage(
        subtype=overrides.pop("subtype", "success"),
        session_id=overrides.pop("session_id", "sess-1"),
        result=overrides.pop("result", "done"),
        total_cost_usd=overrides.pop("total_cost_usd", 0.25),
        input_tokens=overrides.pop("input_tokens", 100),
        output_tokens=overrides.pop("output_tokens", 20),
        num_turns=overrides.pop("num_turns", 3),
        duration_ms=overrides.pop("duration_ms", 1500),
        structured_output=overrides.pop("structured_output", None),
    )
    blocks = overrides.pop("blocks", [TextBlock("done")])
    messages: list[Any] = [SystemMessage(data={"session_id": result.session_id})]
    if blocks:
        messages.append(AssistantMessage(content=blocks))
    messages.append(result)
    plan: dict[str, Any] = {"messages": messages}
    plan.update(overrides)
    return plan


# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

install_fake_sdk()

from pydantic import BaseModel

from vidbyte.agents.claude import (
    ClaudeAgentDefinition,
    ClaudeAgentSettings,
    ClaudeEffortLevel,
    ClaudeForkSettings,
    ClaudeHarnessAgent,
    ClaudeHarnessAgentSettings,
    ClaudeModelSettings,
    ClaudePermissionMode,
    ClaudeProcessSettings,
    ClaudeRunInput,
    ClaudeSandboxSettings,
    ClaudeSessionSettings,
    ClaudeSettingSource,
    ClaudeSubagentSettings,
    ClaudeSystemPromptKind,
    ClaudeSystemPromptSettings,
    ClaudeThinkingMode,
    ClaudeToolSettings,
)
from vidbyte.agents.claude.config import (
    ClaudeContentTranslator,
    ClaudeVidbyteTranslator,
)
from vidbyte.agents.claude.context import ClaudeContextTranslator
from vidbyte.agents.claude.fork import ClaudeFork
from vidbyte.agents.claude.result import (
    ClaudeResultSerializer,
    ClaudeResultTranslator,
    ClaudeStreamAccumulator,
)
from vidbyte.agents.claude.transport import ClaudeTransport
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import DocumentContextItem
from vidbyte.lib.dataclasses.claude import (
    ClaudeContextTranslationRequest,
    ClaudeForkRequest,
    ClaudeResultTranslationRequest,
    ClaudeSdkTypes,
    ClaudeTransportRunRequest,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import (
    ClaudeAgentError,
    ConfigurationError,
    OutputSchemaViolationError,
)


class Findings(BaseModel):
    """Structured-output schema used by the schema round-trip checks."""

    summary: str
    count: int


def primitive(text: str, name: str = "rule") -> DocumentContextItem:
    # Builds one managed context primitive with a stable id the tests can remove.
    return DocumentContextItem(source=name, content=text, primitive_id=name)


def sdk_types() -> ClaudeSdkTypes:
    # Builds the SDK type record the result collaborators expect.
    return ClaudeTransport._load_sdk()


def agent(**overrides: Any) -> ClaudeHarnessAgent:
    # Constructs an agent with test defaults and the given setting overrides.
    settings = ClaudeHarnessAgentSettings(
        name=overrides.pop("name", "tester"),
        system_prompt=overrides.pop("system_prompt", "You test things."),
        **overrides,
    )
    return ClaudeHarnessAgent(settings)


def expect_config_error(build: Any) -> None:
    # Asserts a settings constructor rejects its input with ConfigurationError.
    try:
        build()
    except ConfigurationError:
        return
    raise AssertionError("expected ConfigurationError")


def expect_failure_code(run: Any, code: FailureCode) -> None:
    # Asserts an adapter operation fails with one specific failure code.
    try:
        run()
    except ClaudeAgentError as exc:
        assert exc.failure_code == code.value, f"{exc.failure_code} != {code.value}"
        assert "Traceback" not in str(exc), "provider text leaked into the message"
        return
    raise AssertionError(f"expected {code.value}")


# ---------------------------------------------------------------------------
# Settings validation
# ---------------------------------------------------------------------------


def check_session_rejects_continue_with_resume() -> None:
    expect_config_error(
        lambda: ClaudeSessionSettings(resume="s1", continue_conversation=True)
    )


def check_session_rejects_fork_without_parent() -> None:
    expect_config_error(lambda: ClaudeSessionSettings(fork_session=True))


def check_session_rejects_resume_at_without_resume() -> None:
    expect_config_error(lambda: ClaudeSessionSettings(resume_session_at="uuid"))


def check_tools_reject_allow_deny_conflict() -> None:
    expect_config_error(
        lambda: ClaudeToolSettings(allowed_tools=("Read",), disallowed_tools=("Read",))
    )


def check_tools_reject_skills_with_all_skills() -> None:
    expect_config_error(lambda: ClaudeToolSettings(skills=("a",), all_skills=True))


def check_model_rejects_low_thinking_budget() -> None:
    expect_config_error(
        lambda: ClaudeModelSettings(
            thinking_mode=ClaudeThinkingMode.ENABLED, thinking_budget_tokens=10
        )
    )


def check_model_rejects_budget_without_enabled_mode() -> None:
    expect_config_error(
        lambda: ClaudeModelSettings(
            thinking_mode=ClaudeThinkingMode.DISABLED, thinking_budget_tokens=2048
        )
    )


def check_subagents_reject_reserved_name() -> None:
    expect_config_error(
        lambda: ClaudeSubagentSettings(
            roles={"Task": ClaudeAgentDefinition(description="d", prompt="p")}
        )
    )


def check_system_prompt_file_requires_path() -> None:
    expect_config_error(
        lambda: ClaudeSystemPromptSettings(kind=ClaudeSystemPromptKind.FILE)
    )
    expect_config_error(
        lambda: ClaudeSystemPromptSettings(kind=ClaudeSystemPromptKind.TEXT, path="p")
    )


def check_sandbox_rejects_detail_without_enabled() -> None:
    expect_config_error(lambda: ClaudeSandboxSettings(allow_network=True))
    expect_config_error(
        lambda: ClaudeSandboxSettings(enabled=True, allowed_domains=("a.com",))
    )


def check_process_rejects_duplicate_setting_sources() -> None:
    expect_config_error(
        lambda: ClaudeProcessSettings(
            setting_sources=(ClaudeSettingSource.USER, ClaudeSettingSource.USER)
        )
    )


def check_fork_rejects_clear_with_replacement() -> None:
    expect_config_error(
        lambda: ClaudeForkSettings(
            clear_context_manager=True, context_manager=ContextManager()
        )
    )
    expect_config_error(
        lambda: ClaudeForkSettings(clear_output_schema=True, output_schema=Findings)
    )


def check_agent_settings_reject_blank_name() -> None:
    expect_config_error(
        lambda: ClaudeHarnessAgentSettings(name="   ", system_prompt="p")
    )


def check_run_input_rejects_empty_prompt() -> None:
    expect_config_error(lambda: ClaudeRunInput(prompt=""))
    expect_config_error(lambda: ClaudeRunInput(prompt="   "))


# ---------------------------------------------------------------------------
# Option translation
# ---------------------------------------------------------------------------


def check_translator_omits_provider_defaults() -> None:
    kwargs = ClaudeContentTranslator.option_kwargs("p", "", ClaudeAgentSettings(), {})
    for key in ("model", "effort", "permission_mode", "thinking", "max_turns", "resume"):
        assert key not in kwargs, f"{key} should be omitted when unset"


def check_translator_emits_explicit_empty_setting_sources() -> None:
    kwargs = ClaudeContentTranslator.option_kwargs("p", "", ClaudeAgentSettings(), {})
    assert kwargs["setting_sources"] == [], kwargs.get("setting_sources")


def check_translator_prefers_agent_session_id() -> None:
    settings = ClaudeAgentSettings(session=ClaudeSessionSettings(resume="stale"))
    kwargs = ClaudeContentTranslator.option_kwargs("p", "live", settings, {})
    assert kwargs["resume"] == "live", kwargs["resume"]


def check_translator_emits_claude_code_preset() -> None:
    kwargs = ClaudeContentTranslator.option_kwargs("p", "", ClaudeAgentSettings(), {})
    assert kwargs["tools"] == {"type": "preset", "preset": "claude_code"}, kwargs["tools"]
    explicit = ClaudeAgentSettings(tools=ClaudeToolSettings(tools=("Read",)))
    assert ClaudeContentTranslator.option_kwargs("p", "", explicit, {})["tools"] == ["Read"]


def check_translator_emits_all_skills_sentinel() -> None:
    settings = ClaudeAgentSettings(tools=ClaudeToolSettings(all_skills=True))
    assert ClaudeContentTranslator.option_kwargs("p", "", settings, {})["skills"] == "all"


def check_translator_emits_camel_case_subagents() -> None:
    role = ClaudeAgentDefinition(
        description="d",
        prompt="p",
        disallowed_tools=("Bash",),
        max_turns=4,
        permission_mode=ClaudePermissionMode.PLAN,
        effort=ClaudeEffortLevel.HIGH,
    )
    settings = ClaudeAgentSettings(subagents=ClaudeSubagentSettings(roles={"auditor": role}))
    emitted = ClaudeContentTranslator.option_kwargs("p", "", settings, {})["agents"]["auditor"]
    assert emitted["disallowedTools"] == ["Bash"], emitted
    assert emitted["maxTurns"] == 4, emitted
    assert emitted["permissionMode"] == "plan", emitted
    assert emitted["effort"] == "high", emitted
    assert "disallowed_tools" not in emitted, emitted


def check_translator_emits_thinking_config() -> None:
    enabled = ClaudeModelSettings(
        thinking_mode=ClaudeThinkingMode.ENABLED, thinking_budget_tokens=4096
    )
    config = ClaudeContentTranslator.thinking_config(enabled)
    assert config == {"type": "enabled", "budget_tokens": 4096}, config
    assert ClaudeContentTranslator.thinking_config(ClaudeModelSettings()) is None


def check_translator_rewrites_schema_draft() -> None:
    resolved = ClaudeVidbyteTranslator().output_schema(Findings)
    assert resolved["$schema"] == "http://json-schema.org/draft-07/schema#", resolved.get("$schema")
    raw = Findings.model_json_schema()
    assert raw.get("$schema", "") != resolved["$schema"] or "$schema" not in raw


def check_translator_strips_whitespace() -> None:
    translated = ClaudeVidbyteTranslator().translate_agent(
        ClaudeHarnessAgentSettings(
            name="  n  ", system_prompt="  p  ", session_id="  s  "
        )
    ).settings
    assert (translated.name, translated.system_prompt, translated.session_id) == ("n", "p", "s")


def check_translator_rejects_conflicting_session_identity() -> None:
    expect_failure_code(
        lambda: ClaudeHarnessAgent(
            ClaudeHarnessAgentSettings(
                name="n",
                system_prompt="p",
                session_id="a",
                claude=ClaudeAgentSettings(session=ClaudeSessionSettings(resume="b")),
            )
        ),
        FailureCode.CLAUDE_VIDBYTE_TRANSLATION_FAILED,
    )


# ---------------------------------------------------------------------------
# Context translation
# ---------------------------------------------------------------------------


def translate_context(**overrides: Any) -> Any:
    # Renders one context translation request with test defaults.
    request = ClaudeRunInput(
        prompt=overrides.pop("prompt", "ask"),
        context_manager=overrides.pop("run_manager", None),
        context_items=overrides.pop("context_items", ()),
    )
    return ClaudeContextTranslator.translate(
        ClaudeContextTranslationRequest(
            input=request,
            static_context=overrides.pop("static_context", ""),
            context_manager=overrides.pop("agent_manager", None),
        )
    )


def check_context_empty_sources() -> None:
    prompt = translate_context()
    assert prompt.user_prompt == "ask", prompt.user_prompt
    assert prompt.developer_context == "", prompt.developer_context


def check_context_same_manager_renders_once() -> None:
    manager = ContextManager()
    manager.upsert(primitive("ONE"))
    prompt = translate_context(agent_manager=manager, run_manager=manager)
    assert prompt.developer_context.count("ONE") == 1, prompt.developer_context


def check_context_two_managers_render_in_order() -> None:
    first, second = ContextManager(), ContextManager()
    first.upsert(primitive("FIRST", "a"))
    second.upsert(primitive("SECOND", "b"))
    prompt = translate_context(agent_manager=first, run_manager=second)
    assert prompt.developer_context.index("FIRST") < prompt.developer_context.index("SECOND")


def check_context_preserves_identical_blocks() -> None:
    prompt = translate_context(
        static_context="SAME", context_items=(primitive("SAME", "x"),)
    )
    assert prompt.user_prompt.count("SAME") == 2, prompt.user_prompt


def check_context_reflects_live_removal() -> None:
    manager = ContextManager()
    item = primitive("GONE", "temp")
    manager.upsert(item)
    assert "GONE" in translate_context(agent_manager=manager).developer_context
    manager.remove_by_id(item.primitive_id)
    assert "GONE" not in translate_context(agent_manager=manager).developer_context


def check_context_does_not_mutate_caller_manager() -> None:
    manager = ContextManager()
    manager.upsert(primitive("KEEP", "keep"))
    before = [primitive_id for primitive_id, _ in manager.registry_items()]
    translate_context(agent_manager=manager)
    after = [primitive_id for primitive_id, _ in manager.registry_items()]
    assert before == after, (before, after)


def check_context_drops_blank_blocks_only() -> None:
    prompt = translate_context(static_context="", prompt="  keep me  ")
    assert prompt.user_prompt == "  keep me  ", repr(prompt.user_prompt)


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


def run_transport(**overrides: Any) -> Any:
    # Executes one transport run against the currently scripted fake stream.
    request = ClaudeTransportRunRequest(
        session_id=overrides.pop("session_id", ""),
        system_prompt="p",
        prompt=translate_context(),
        settings=ClaudeAgentSettings(),
        output_schema={},
    )
    return asyncio.run(ClaudeTransport().run(request))


def check_transport_missing_sdk() -> None:
    uninstall_fake_sdk()
    try:
        expect_failure_code(run_transport, FailureCode.CLAUDE_SDK_UNAVAILABLE)
    finally:
        install_fake_sdk()


def check_transport_maps_cli_not_found() -> None:
    reset_fake()
    SCRIPTED_TURNS.append({"messages": (), "raise": CLINotFoundError("missing")})
    expect_failure_code(run_transport, FailureCode.CLAUDE_CLI_NOT_FOUND)


def check_transport_maps_process_error() -> None:
    reset_fake()
    SCRIPTED_TURNS.append({"messages": (), "raise": ProcessError("exit 1")})
    expect_failure_code(run_transport, FailureCode.CLAUDE_PROCESS_FAILED)


def check_transport_maps_connection_error() -> None:
    reset_fake()
    SCRIPTED_TURNS.append({"messages": (), "raise": CLIConnectionError("gone")})
    expect_failure_code(run_transport, FailureCode.CLAUDE_CONNECTION_FAILED)


def check_transport_maps_resume_failure() -> None:
    reset_fake()
    SCRIPTED_TURNS.append({"messages": (), "raise": RuntimeError("stale id")})
    expect_failure_code(
        lambda: run_transport(session_id="old"), FailureCode.CLAUDE_SESSION_RESUME_FAILED
    )


def check_transport_returns_result_after_raise() -> None:
    reset_fake()
    plan = script(subtype="error_max_turns", session_id="sess-keep", result="partial")
    plan["raise"] = ProcessError("query raised after error result")
    SCRIPTED_TURNS.append(plan)
    result = run_transport()
    assert result.session_id == "sess-keep", result.session_id
    assert result.subtype == "error_max_turns", result.subtype


def check_transport_requires_terminal_result() -> None:
    reset_fake()
    SCRIPTED_TURNS.append({"messages": [SystemMessage(data={"session_id": "s"})]})
    expect_failure_code(run_transport, FailureCode.CLAUDE_RESPONSE_INVALID)


def check_transport_closes_stream_on_success() -> None:
    reset_fake()
    SCRIPTED_TURNS.append(script())
    run_transport()
    assert CLOSED_STREAMS == ["closed"], CLOSED_STREAMS


def check_transport_closes_stream_on_failure() -> None:
    reset_fake()
    SCRIPTED_TURNS.append({"messages": (), "raise": ProcessError("boom")})
    try:
        run_transport()
    except ClaudeAgentError:
        pass
    assert CLOSED_STREAMS == ["closed"], CLOSED_STREAMS


def check_transport_tolerates_missing_aclose() -> None:
    reset_fake()
    plan = script()
    plan["supports_close"] = False
    SCRIPTED_TURNS.append(plan)
    assert run_transport().subtype == "success"
    assert CLOSED_STREAMS == [], CLOSED_STREAMS


def check_transport_propagates_cancellation() -> None:
    reset_fake()
    SCRIPTED_TURNS.append({"messages": (), "raise": asyncio.CancelledError()})
    try:
        run_transport()
    except asyncio.CancelledError:
        return
    except ClaudeAgentError as exc:
        raise AssertionError(f"cancellation became {exc.failure_code}") from exc
    raise AssertionError("expected CancelledError")


def check_transport_rejects_bad_options() -> None:
    reset_fake()

    class Rejecting:
        def __init__(self, **kwargs: Any) -> None:
            raise TypeError("unexpected keyword")

    original = ClaudeTransport._load_sdk

    def patched() -> ClaudeSdkTypes:
        return replace(original(), options=Rejecting)

    ClaudeTransport._load_sdk = staticmethod(patched)  # type: ignore[method-assign]
    try:
        expect_failure_code(run_transport, FailureCode.CLAUDE_CONTENT_TRANSLATION_FAILED)
    finally:
        ClaudeTransport._load_sdk = staticmethod(original)  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Result normalization
# ---------------------------------------------------------------------------


def accumulate(messages: list[Any]) -> ClaudeStreamAccumulator:
    # Feeds a message list through one accumulator and returns it.
    accumulator = ClaudeStreamAccumulator()
    sdk = sdk_types()
    for message in messages:
        accumulator.consume(message, sdk)
    return accumulator


def check_serializer_excludes_thinking_blocks() -> None:
    reset_fake()
    plan = script(blocks=[ThinkingBlock("secret"), TextBlock("visible")])
    result = ClaudeResultSerializer.from_stream(accumulate(plan["messages"]))
    assert [item.type for item in result.items] == ["text"], result.items
    assert THINKING_READS == [], "thinking text was read during serialization"


def check_serializer_copies_supported_blocks() -> None:
    blocks = [
        TextBlock("hi"),
        ToolUseBlock(id="tu1", name="Read", input={"path": "a.py"}),
        ToolResultBlock(tool_use_id="tu1", content=[TextBlock("body")]),
    ]
    result = ClaudeResultSerializer.from_stream(accumulate(script(blocks=blocks)["messages"]))
    assert [item.type for item in result.items] == ["text", "tool_use", "tool_result"]
    assert result.items[1].fields["input"] == {"path": "a.py"}
    assert result.items[2].fields["content_block_count"] == 1


def check_serializer_marks_absent_usage() -> None:
    messages = [ResultMessage(session_id="s", result="ok", total_cost_usd=None)]
    result = ClaudeResultSerializer.from_stream(accumulate(messages))
    assert result.usage_available is False, result.usage_available
    assert result.usage.total_cost_usd == 0.0


def check_serializer_distinguishes_zero_from_absent() -> None:
    messages = [ResultMessage(session_id="s", result="ok", input_tokens=0, total_cost_usd=None)]
    result = ClaudeResultSerializer.from_stream(accumulate(messages))
    assert result.usage_available is True, "an explicit zero is a present value"
    assert result.usage.input_tokens == 0


def check_serializer_handles_empty_assistant_content() -> None:
    messages = [AssistantMessage(content=[]), ResultMessage(session_id="s", result="ok")]
    assert ClaudeResultSerializer.from_stream(accumulate(messages)).items == ()


def check_serializer_handles_result_only_stream() -> None:
    messages = [ResultMessage(session_id="s", result="ok")]
    assert ClaudeResultSerializer.from_stream(accumulate(messages)).session_id == "s"


def check_serializer_rejects_empty_success() -> None:
    messages = [ResultMessage(session_id="s", result=None, structured_output=None)]
    expect_failure_code(
        lambda: ClaudeResultSerializer.from_stream(accumulate(messages)),
        FailureCode.CLAUDE_RESPONSE_INVALID,
    )


def translate_result(result: Any, schema: Any = None) -> Any:
    # Builds an AgentMessage from one run result under the given output schema.
    settings = ClaudeVidbyteTranslator().translate_agent(
        ClaudeHarnessAgentSettings(name="n", system_prompt="p", output_schema=schema)
    ).settings
    return ClaudeResultTranslator().translate(
        ClaudeResultTranslationRequest(
            result=result, agent=settings, input_metadata={}, recipient="user"
        )
    )


def check_translator_skips_validation_on_failure() -> None:
    plan = script(subtype="error_max_turns", result="partial")
    result = ClaudeResultSerializer.from_stream(accumulate(plan["messages"]))
    assert translate_result(result, Findings).structured is None


def check_translator_rejects_success_without_structured_output() -> None:
    result = ClaudeResultSerializer.from_stream(accumulate(script()["messages"]))
    try:
        translate_result(result, Findings)
    except OutputSchemaViolationError:
        return
    raise AssertionError("expected OutputSchemaViolationError")


def check_translator_rejects_schema_violation() -> None:
    plan = script(structured_output={"summary": "s"})
    result = ClaudeResultSerializer.from_stream(accumulate(plan["messages"]))
    try:
        translate_result(result, Findings)
    except OutputSchemaViolationError:
        return
    raise AssertionError("expected OutputSchemaViolationError")


def check_translator_returns_model_instance() -> None:
    plan = script(structured_output={"summary": "s", "count": 2})
    result = ClaudeResultSerializer.from_stream(accumulate(plan["messages"]))
    structured = translate_result(result, Findings).structured
    assert isinstance(structured, Findings), type(structured)
    assert structured.count == 2


def check_translator_accepts_falsey_structured_values() -> None:
    class Flag(BaseModel):
        enabled: bool

    plan = script(structured_output={"enabled": False})
    result = ClaudeResultSerializer.from_stream(accumulate(plan["messages"]))
    assert translate_result(result, Flag).structured.enabled is False


def check_translator_filters_subagent_items() -> None:
    blocks = [
        ToolUseBlock(id="a", name="Task", input={}),
        ToolUseBlock(id="b", name="Read", input={}),
    ]
    result = ClaudeResultSerializer.from_stream(accumulate(script(blocks=blocks)["messages"]))
    message = translate_result(result)
    assert [item.id for item in message.claude.subagents] == ["a"], message.claude.subagents


def check_translator_sets_provider_metadata() -> None:
    result = ClaudeResultSerializer.from_stream(accumulate(script()["messages"]))
    message = translate_result(result)
    assert message.metadata["provider"] == "claude"
    assert message.metadata["provider_item_count"] == 1
    assert message.claude.usage.total_cost_usd == 0.25


# ---------------------------------------------------------------------------
# Fork
# ---------------------------------------------------------------------------


def fork_child(parent_session_id: str = "parent-1", **overrides: Any) -> Any:
    # Prepares one fork child from a validated parent and the given overrides.
    parent = ClaudeVidbyteTranslator().translate_agent(
        ClaudeHarnessAgentSettings(
            name="parent",
            system_prompt="parent prompt",
            output_schema=overrides.pop("parent_schema", Findings),
            context_manager=overrides.pop("parent_manager", None),
            metadata=overrides.pop("parent_metadata", {}),
        )
    ).settings
    return ClaudeFork().fork(
        ClaudeForkRequest(
            parent=parent,
            parent_session_id=parent_session_id,
            overrides=ClaudeForkSettings(**overrides),
        )
    ).settings


def check_fork_requires_parent_session() -> None:
    expect_failure_code(lambda: fork_child(""), FailureCode.CLAUDE_FORK_FAILED)


def check_fork_sets_resume_and_fork_flag() -> None:
    session = fork_child().claude.session
    assert session.resume == "parent-1", session.resume
    assert session.fork_session is True


def check_fork_leaves_child_session_empty() -> None:
    assert fork_child().session_id == ""


def check_fork_clears_parent_continuation() -> None:
    session = fork_child().claude.session
    assert session.continue_conversation is False
    assert session.resume_session_at == ""


def check_fork_deep_copies_context_manager() -> None:
    manager = ContextManager()
    manager.upsert(primitive("PARENT", "shared"))
    child = fork_child(parent_manager=manager)
    child.context_manager.upsert(primitive("CHILD", "childonly"))
    assert "CHILD" not in manager.render_primitives_zone()
    assert child.context_manager is not manager


def check_fork_increments_depth() -> None:
    child = fork_child(parent_metadata={"fork_depth": 2})
    assert child.metadata["fork_depth"] == 3, child.metadata["fork_depth"]
    assert child.metadata["forked_from_session_id"] == "parent-1"


def check_fork_defaults_root_depth() -> None:
    assert fork_child().metadata["fork_depth"] == 1


def check_fork_distinguishes_inherit_from_replace() -> None:
    assert fork_child().capabilities == ()
    inherited = fork_child(capabilities=None)
    assert inherited.capabilities == ()
    replaced = fork_child(capabilities=("audit",))
    assert replaced.capabilities == ("audit",)
    assert fork_child(additional_context="").additional_context == ""


def check_fork_clears_output_schema() -> None:
    assert fork_child(clear_output_schema=True).output_schema is None
    assert fork_child().output_schema is Findings


def check_fork_afork_matches_fork() -> None:
    parent = ClaudeVidbyteTranslator().translate_agent(
        ClaudeHarnessAgentSettings(name="p", system_prompt="p")
    ).settings
    request = ClaudeForkRequest(
        parent=parent, parent_session_id="s1", overrides=ClaudeForkSettings()
    )
    assert asyncio.run(ClaudeFork().afork(request)).settings == ClaudeFork().fork(request).settings


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------


def check_agent_rejects_invalid_settings() -> None:
    expect_failure_code(
        lambda: ClaudeHarnessAgent(
            ClaudeHarnessAgentSettings(
                name="n",
                system_prompt="p",
                session_id="x",
                claude=ClaudeAgentSettings(
                    session=ClaudeSessionSettings(continue_conversation=True)
                ),
            )
        ),
        FailureCode.CLAUDE_VIDBYTE_TRANSLATION_FAILED,
    )


def check_agent_adopts_session_id() -> None:
    reset_fake()
    SCRIPTED_TURNS.append(script(session_id="sess-new"))
    live = agent()
    reply = live.run(ClaudeRunInput.text("hello"))
    assert live.session_id == "sess-new", live.session_id
    assert reply.claude.session_id == "sess-new"
    assert reply.content == "done"


def check_agent_resumes_on_second_turn() -> None:
    reset_fake()
    SCRIPTED_TURNS.extend([script(session_id="sess-a"), script(session_id="sess-a")])
    live = agent()
    live.run(ClaudeRunInput.text("first"))
    live.run(ClaudeRunInput.text("second"))
    assert "resume" not in CAPTURED_OPTIONS[0].kwargs, CAPTURED_OPTIONS[0].kwargs
    assert CAPTURED_OPTIONS[1].kwargs["resume"] == "sess-a", CAPTURED_OPTIONS[1].kwargs


def check_agent_appends_developer_context() -> None:
    reset_fake()
    SCRIPTED_TURNS.append(script())
    manager = ContextManager()
    manager.upsert(primitive("ALWAYS TEST"))
    live = agent(context_manager=manager)
    live.run(ClaudeRunInput.text("go"))
    emitted = CAPTURED_OPTIONS[0].kwargs["system_prompt"]
    assert emitted.startswith("You test things."), emitted
    assert "ALWAYS TEST" in emitted, emitted
    assert "\n\n" in emitted, emitted


def check_agent_sync_guard_inside_loop() -> None:
    reset_fake()
    SCRIPTED_TURNS.append(script())
    live = agent()

    async def call() -> None:
        live.run(ClaudeRunInput.text("go"))

    expect_failure_code(lambda: asyncio.run(call()), FailureCode.CLAUDE_QUERY_FAILED)


def check_agent_history_grows() -> None:
    reset_fake()
    SCRIPTED_TURNS.extend([script(), script()])
    live = agent()
    live.run(ClaudeRunInput.text("one"))
    live.run(ClaudeRunInput.text("two"))
    assert len(live.history) == 2, len(live.history)
    assert live.last_reply is live.history[-1]


def check_package_imports_without_sdk() -> None:
    uninstall_fake_sdk()
    try:
        import importlib

        module = importlib.import_module("vidbyte.agents.claude")
        assert module.ClaudeHarnessAgent is ClaudeHarnessAgent
        live = agent()
        expect_failure_code(
            lambda: live.run(ClaudeRunInput.text("go")),
            FailureCode.CLAUDE_SDK_UNAVAILABLE,
        )
    finally:
        install_fake_sdk()


# ---------------------------------------------------------------------------
# Errors and exports
# ---------------------------------------------------------------------------


def check_error_carries_diagnostic_packet() -> None:
    error = ClaudeAgentError("m", failure_code="claude.query_failed", operation="op")
    for name in ClaudeAgentError.DIAGNOSTIC_FIELDS:
        assert getattr(error, name, None), f"missing {name}"
        assert name in error.details, f"missing {name} in details"


def check_failure_codes_present_and_unique() -> None:
    codes = [code for code in FailureCode if code.value.startswith("claude.")]
    assert len(codes) == 10, [code.value for code in codes]
    assert len({code.value for code in codes}) == 10


def check_root_exports_complete() -> None:
    import vidbyte
    from vidbyte.agents.claude import __all__ as names

    missing = [name for name in names if not hasattr(vidbyte, name)]
    assert missing == [], missing


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------


def check_integration_fork_divergence() -> None:
    reset_fake()
    SCRIPTED_TURNS.extend(
        [script(session_id="parent-s"), script(session_id="child-s"), script(session_id="child-s")]
    )
    parent = agent()
    parent.run(ClaudeRunInput.text("parent turn"))
    child = parent.fork(ClaudeForkSettings(system_prompt="Child prompt."))
    assert child.session_id == ""
    child.run(ClaudeRunInput.text("child turn one"))
    child.run(ClaudeRunInput.text("child turn two"))
    first, second = CAPTURED_OPTIONS[1].kwargs, CAPTURED_OPTIONS[2].kwargs
    assert first["resume"] == "parent-s" and first["fork_session"] is True, first
    assert second["resume"] == "child-s", second
    assert "fork_session" not in second, second


def check_integration_structured_round_trip() -> None:
    reset_fake()
    SCRIPTED_TURNS.append(script(structured_output={"summary": "ok", "count": 7}))
    live = agent(output_schema=Findings)
    reply = live.run(ClaudeRunInput.text("summarize"))
    emitted = CAPTURED_OPTIONS[0].kwargs["output_format"]
    assert emitted["type"] == "json_schema", emitted
    assert emitted["schema"]["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert isinstance(reply.structured, Findings) and reply.structured.count == 7
    assert reply.claude.usage.total_cost_usd == 0.25, reply.claude.usage


def check_integration_recovery_after_max_turns() -> None:
    reset_fake()
    failing = script(subtype="error_max_turns", session_id="sess-recover", result="partial")
    failing["raise"] = ProcessError("raised after error result")
    SCRIPTED_TURNS.extend([failing, script(session_id="sess-recover")])
    live = agent()
    live.run(ClaudeRunInput.text("long task"))
    assert live.session_id == "sess-recover", live.session_id
    live.run(ClaudeRunInput.text("continue"))
    assert CAPTURED_OPTIONS[1].kwargs["resume"] == "sess-recover"


def check_integration_context_mutation_between_turns() -> None:
    reset_fake()
    SCRIPTED_TURNS.extend([script(), script()])
    manager = ContextManager()
    item = primitive("TEMPORARY RULE", "temp")
    manager.upsert(item)
    live = agent(context_manager=manager)
    live.run(ClaudeRunInput.text("one"))
    assert "TEMPORARY RULE" in CAPTURED_OPTIONS[0].kwargs["system_prompt"]
    manager.remove_by_id(item.primitive_id)
    live.run(ClaudeRunInput.text("two"))
    assert "TEMPORARY RULE" not in CAPTURED_OPTIONS[1].kwargs["system_prompt"]


SUITE = [
    ("session rejects continue_conversation with resume [Hidden Assumption]", check_session_rejects_continue_with_resume),
    ("session rejects fork_session without a parent [Hidden Assumption]", check_session_rejects_fork_without_parent),
    ("session rejects resume_session_at without resume [Edge Case]", check_session_rejects_resume_at_without_resume),
    ("tools reject an allow/deny conflict [Silent Failure]", check_tools_reject_allow_deny_conflict),
    ("tools reject skills with all_skills [Edge Case]", check_tools_reject_skills_with_all_skills),
    ("model rejects a thinking budget below the minimum [Edge Case]", check_model_rejects_low_thinking_budget),
    ("model rejects a budget outside ENABLED mode [Silent Failure]", check_model_rejects_budget_without_enabled_mode),
    ("subagents reject a reserved role name [Hidden Assumption]", check_subagents_reject_reserved_name),
    ("system prompt FILE requires a path and TEXT forbids one [Edge Case]", check_system_prompt_file_requires_path),
    ("sandbox rejects detail without enabled [Hidden Assumption]", check_sandbox_rejects_detail_without_enabled),
    ("process rejects duplicate setting sources [Edge Case]", check_process_rejects_duplicate_setting_sources),
    ("fork rejects clear with a replacement [Hidden Assumption]", check_fork_rejects_clear_with_replacement),
    ("agent settings reject a whitespace-only name [Edge Case]", check_agent_settings_reject_blank_name),
    ("run input rejects an empty prompt [Edge Case]", check_run_input_rejects_empty_prompt),
    ("translator omits PROVIDER_DEFAULT sentinels [Silent Failure]", check_translator_omits_provider_defaults),
    ("translator emits an explicit empty setting_sources [Silent Failure]", check_translator_emits_explicit_empty_setting_sources),
    ("translator prefers the adopted session id over settings resume [Silent Failure]", check_translator_prefers_agent_session_id),
    ("translator emits the claude_code tools preset [Edge Case]", check_translator_emits_claude_code_preset),
    ("translator emits the all-skills sentinel [Edge Case]", check_translator_emits_all_skills_sentinel),
    ("translator emits camelCase subagent keys [Silent Failure]", check_translator_emits_camel_case_subagents),
    ("translator emits thinking config only when configured [Edge Case]", check_translator_emits_thinking_config),
    ("translator rewrites the schema draft to draft-07 [Silent Failure]", check_translator_rewrites_schema_draft),
    ("translator strips surrounding whitespace [Edge Case]", check_translator_strips_whitespace),
    ("translator rejects conflicting session identity [Hidden Assumption]", check_translator_rejects_conflicting_session_identity),
    ("context renders an empty prompt body for no sources [Edge Case]", check_context_empty_sources),
    ("context renders one shared manager once [Silent Failure]", check_context_same_manager_renders_once),
    ("context renders two managers in construction-then-run order [Edge Case]", check_context_two_managers_render_in_order),
    ("context preserves identical blocks without deduplicating [Silent Failure]", check_context_preserves_identical_blocks),
    ("context reflects a primitive removed between turns [Hidden Failure]", check_context_reflects_live_removal),
    ("context does not mutate the caller's manager [Hidden Failure]", check_context_does_not_mutate_caller_manager),
    ("context drops blank blocks but keeps interior whitespace [Edge Case]", check_context_drops_blank_blocks_only),
    ("transport raises sdk_unavailable without the extra [Hidden Assumption]", check_transport_missing_sdk),
    ("transport maps CLINotFoundError to cli_not_found [Hidden Failure]", check_transport_maps_cli_not_found),
    ("transport maps ProcessError to process_failed [Hidden Failure]", check_transport_maps_process_error),
    ("transport maps CLIConnectionError to connection_failed [Hidden Failure]", check_transport_maps_connection_error),
    ("transport maps a resumed-run failure to session_resume_failed [Silent Failure]", check_transport_maps_resume_failure),
    ("transport returns the result when the SDK raises after it [Silent Failure]", check_transport_returns_result_after_raise),
    ("transport rejects a stream with no terminal result [Hidden Failure]", check_transport_requires_terminal_result),
    ("transport closes the stream on success [Hidden Failure]", check_transport_closes_stream_on_success),
    ("transport closes the stream on failure [Hidden Failure]", check_transport_closes_stream_on_failure),
    ("transport tolerates an iterator with no aclose [Edge Case]", check_transport_tolerates_missing_aclose),
    ("transport propagates CancelledError unwrapped [Hidden Failure]", check_transport_propagates_cancellation),
    ("transport reports content_translation_failed for bad options [Hidden Failure]", check_transport_rejects_bad_options),
    ("serializer never emits or reads a thinking block [Silent Failure]", check_serializer_excludes_thinking_blocks),
    ("serializer copies text, tool_use, and tool_result blocks [Edge Case]", check_serializer_copies_supported_blocks),
    ("serializer marks absent usage unavailable [Silent Failure]", check_serializer_marks_absent_usage),
    ("serializer distinguishes an explicit zero from absent [Silent Failure]", check_serializer_distinguishes_zero_from_absent),
    ("serializer handles empty assistant content [Edge Case]", check_serializer_handles_empty_assistant_content),
    ("serializer handles a result-only stream [Edge Case]", check_serializer_handles_result_only_stream),
    ("serializer rejects a success with no text or structured output [Silent Failure]", check_serializer_rejects_empty_success),
    ("result translator skips validation on a failed subtype [Hidden Assumption]", check_translator_skips_validation_on_failure),
    ("result translator rejects success with no structured output [Silent Failure]", check_translator_rejects_success_without_structured_output),
    ("result translator rejects a schema violation [Edge Case]", check_translator_rejects_schema_violation),
    ("result translator returns a Pydantic instance [Silent Failure]", check_translator_returns_model_instance),
    ("result translator accepts a falsey structured value [Silent Failure]", check_translator_accepts_falsey_structured_values),
    ("result translator filters subagent items [Edge Case]", check_translator_filters_subagent_items),
    ("result translator sets provider metadata and cost [Edge Case]", check_translator_sets_provider_metadata),
    ("fork requires a parent session id [Hidden Assumption]", check_fork_requires_parent_session),
    ("fork sets child resume and fork_session [Edge Case]", check_fork_sets_resume_and_fork_flag),
    ("fork leaves the child session id empty [Silent Failure]", check_fork_leaves_child_session_empty),
    ("fork clears parent continuation fields [Silent Failure]", check_fork_clears_parent_continuation),
    ("fork deep-copies the context manager [Hidden Failure]", check_fork_deep_copies_context_manager),
    ("fork increments fork depth from parent metadata [Edge Case]", check_fork_increments_depth),
    ("fork defaults to root depth with no parent metadata [Edge Case]", check_fork_defaults_root_depth),
    ("fork distinguishes inherit from replace [Silent Failure]", check_fork_distinguishes_inherit_from_replace),
    ("fork clears the output schema on request [Edge Case]", check_fork_clears_output_schema),
    ("fork afork matches fork [Edge Case]", check_fork_afork_matches_fork),
    ("agent rejects invalid construction settings [Hidden Assumption]", check_agent_rejects_invalid_settings),
    ("agent adopts the provider session id [Edge Case]", check_agent_adopts_session_id),
    ("agent resumes on its second turn [Silent Failure]", check_agent_resumes_on_second_turn),
    ("agent appends developer context to the system prompt [Edge Case]", check_agent_appends_developer_context),
    ("agent run guards a nested event loop [Hidden Failure]", check_agent_sync_guard_inside_loop),
    ("agent records history and last reply [Edge Case]", check_agent_history_grows),
    ("package imports and fails cleanly without the SDK [Hidden Assumption]", check_package_imports_without_sdk),
    ("error carries the full diagnostic packet [Hidden Assumption]", check_error_carries_diagnostic_packet),
    ("failure vocabulary has ten unique claude codes [Edge Case]", check_failure_codes_present_and_unique),
    ("root package exports every adapter name [Silent Failure]", check_root_exports_complete),
    ("integration: fork diverges then resumes its own session [Silent Failure]", check_integration_fork_divergence),
    ("integration: structured output round trip [Silent Failure]", check_integration_structured_round_trip),
    ("integration: recovery after error_max_turns [Hidden Failure]", check_integration_recovery_after_max_turns),
    ("integration: context mutation between turns [Hidden Failure]", check_integration_context_mutation_between_turns),
]


def main() -> int:
    # Runs every registered check and reports a PASS or FAIL line for each.
    passed = 0
    failures: list[str] = []
    for name, check in SUITE:
        reset_fake()
        install_fake_sdk()
        try:
            check()
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"FAIL  {name}")
            continue
        passed += 1
        print(f"PASS  {name}")
    print(f"\n{passed}/{len(SUITE)} tests passed")
    for failure in failures:
        print(f"  - {failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

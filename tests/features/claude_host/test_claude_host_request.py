"""FILE: tests/features/claude_host/test_claude_host_request.py

PURPOSE: Proves that a ClaudeSpawnRequest validates itself and reaches claude-agent-sdk exactly as the field-mapping table says: every field lands on its ClaudeAgentOptions field, extra_args flag or child env variable, unset fields stay at the SDK default, image prompts become one streamed user message, and custom BaseTools reach Claude through one in-process MCP server named vidbyte.
ROLE IN CODEBASE: Request layer of tests/features/claude_host/ (spec AC-17, AC-18, AC-20, INV-17, D-9 to D-12, EC-35 to EC-42). Exercises vidbyte/lib/dataclasses/claude.py, vidbyte/lib/dataclasses/claude_host.py (ClaudeHostSettings), vidbyte/harnesses/native/claude/options.py and vidbyte/harnesses/native/claude/tool_server.py.
ARCHITECTURE NOTE: The translator runs for real against the fake ClaudeAgentOptions, which has exactly the 0.2.165 fields and defaults, so an unknown keyword fails and any field left away from its SDK default counts as "passed". Each mapping case compares only what the request changed relative to a default request, so a stray option fails the case that leaked it.
COMMON MODIFICATION PATTERNS: When the spec maps a new request field, add one row to mapping_cases() with the options delta it must produce. When a validation rule is added, add one row to the rejected or accepted table.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not compare extra_args or env values loosely: the SDK formats them with str(), so an enum member would reach the command line as "ClaudeX.MEMBER". 3. Do not use real secrets; the markers in the fixtures are dummies.
KNOWN EDGE CASES: The sandbox "network" key is only checked when a domain is set, because the spec does not say whether an empty network object is sent. Combination rules that the spec words as "requires" accept either configuration code. A request path is compared through pathlib so that str and Path both pass.
RELATED DOCS: tests/features/claude_host/FEATURE.md; docs/spec/claude-host/spec.md sections 8.5, 9.1 and 9.2 ("Field mapping").
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/claude_host/test_claude_host_request.py
"""

from __future__ import annotations

import dataclasses
import enum
import math
import unittest
from collections.abc import Mapping
from pathlib import Path, PurePath
from typing import Any

from tests.features.claude_host.claude_host_fixtures import (
    ENV_MARKER,
    ERROR_MARKER,
    FAKE_CLI_PATH,
    INVALID_ARGUMENT,
    INVALID_ARGUMENT_NEXT_STEP,
    TINY_PNG_BASE64,
    UNSUPPORTED_COMBINATION,
    UNSUPPORTED_COMBINATION_NEXT_STEP,
    WORK_DIR,
    AgentDefinition,
    ClaudeHostCase,
    FakeClaudeSdk,
    HookMatcher,
    TicketTool,
    passed_options,
)
from vidbyte.lib.dataclasses.security import PermissionPolicy
from vidbyte.lib.dataclasses.tools import ToolCall, ToolPermission
from vidbyte.lib.tools.formatter import ToolsFormatter
from vidbyte.tools.catalog import Tools
from vidbyte.tools.executor import ToolExecutor

SESSION_ID = "6f1c2b8e-3d4a-4f5b-9c6d-7e8f9a0b1c2d"
RESUMED_ID = "0d5a3c4e-8b1f-4a2e-9c3d-5e6f7a8b9c0d"
ANCHOR_ID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
DROP_ID = "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e"
FILE_SPEC = "file_011CNha8iCJcU1wXNR6q4V8w:docs/spec.md"
# The first bytes of a JPEG file, base64-encoded.
TINY_JPEG_BASE64 = "/9j/4AAQ"
PRESET = {"type": "preset", "preset": "claude_code"}
HEADLESS_FLAGS = {"permission-prompts": "none"}
SUMMARY_SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}
SINGLE = (INVALID_ARGUMENT,)
EITHER = (INVALID_ARGUMENT, UNSUPPORTED_COMBINATION)


async def decide_permission(tool_name: str, tool_input: dict[str, Any], context: Any) -> dict[str, Any]:
    """A can_use_tool callback in the SDK's own shape (D-24)."""
    return {"behavior": "allow", "updated_input": tool_input}


async def audit_hook(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
    """A hook callback in the SDK's own shape."""
    return {}


async def block_hook(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
    """A second hook callback, so the mapping keeps callback order."""
    return {"decision": "block"}


class MemorySessionStore:
    """A session_store with the append and load methods the SDK calls."""

    async def append(self, key: Any, entries: list[Any]) -> None:
        return None

    async def load(self, key: Any) -> list[Any] | None:
        return None


class BrokenValidationTool(TicketTool):
    """A tool whose validation itself raises, which ToolExecutor does not catch."""

    def validate_call(self, call: ToolCall) -> str | None:
        raise RuntimeError(ERROR_MARKER)


def plain(value: Any) -> Any:
    """Return a value in comparable form: enums as wire values, paths in POSIX form, tuples as lists, mappings as dicts, fake SDK records as field dicts."""
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, PurePath):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {plain(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {"record": type(value).__name__, **{item.name: plain(getattr(value, item.name)) for item in dataclasses.fields(value)}}
    return value


def translate(request: Any, *, tool_server: Any = None, auto_allowed: tuple[str, ...] = ()) -> Any:
    """Run the real translator against the fake SDK types, as the host does for a new session."""
    from vidbyte.harnesses.native.claude.options import ClaudeOptionsTranslator

    return ClaudeOptionsTranslator.to_options(request, cli_path=FAKE_CLI_PATH, session_id=SESSION_ID, tool_server=tool_server, auto_allowed=auto_allowed, sdk=FakeClaudeSdk().types())


def changes(options: Any) -> dict[str, Any]:
    """Return the options a request set beyond what every default request sets."""
    baseline = {"cli_path": FAKE_CLI_PATH, "session_id": SESSION_ID, "system_prompt": PRESET}
    delta: dict[str, Any] = {}
    for name, value in passed_options(options).items():
        comparable = plain(value)
        if name == "extra_args":
            flags = {key: item for key, item in comparable.items() if (key, item) != ("permission-prompts", "none")}
            if flags:
                delta[name] = flags
        elif baseline.get(name) != comparable:
            delta[name] = comparable
    return delta


def mapping_cases() -> tuple[tuple[str, dict[str, Any], dict[str, Any]], ...]:
    """Return (label, request fields, expected options delta) for every row of the field-mapping table."""
    from vidbyte.lib.dataclasses.claude import ClaudeImage, ClaudeSandbox, ClaudeSystemPrompt, ClaudeThinking
    from vidbyte.lib.enums.claude import (
        ClaudeBeta,
        ClaudeEffort,
        ClaudeImageMediaType,
        ClaudePermissionMode,
        ClaudeSettingSource,
        ClaudeSystemPromptMode,
        ClaudeThinkingDisplay,
        ClaudeThinkingMode,
    )

    sandbox = ClaudeSandbox(auto_allow_bash=True, excluded_commands=("git push",), allowed_domains=("api.example.test",), denied_domains=("evil.example.test",))
    sandbox_options = {"enabled": True, "autoAllowBashIfSandboxed": True, "excludedCommands": ["git push"], "network": {"allowedDomains": ["api.example.test"], "deniedDomains": ["evil.example.test"]}}
    replace_prompt = ClaudeSystemPrompt(mode=ClaudeSystemPromptMode.REPLACE, text="You review diffs.")
    return (
        ("files", {"files": (FILE_SPEC,)}, {"extra_args": {"file": FILE_SPEC}}),
        ("cwd", {"cwd": WORK_DIR}, {"cwd": WORK_DIR}),
        ("add_dirs", {"add_dirs": ("C:/work/shared",)}, {"add_dirs": ["C:/work/shared"]}),
        ("model", {"model": "claude-sonnet-4-5"}, {"model": "claude-sonnet-4-5"}),
        ("fallback_model", {"fallback_model": ("claude-opus-4-7", "claude-sonnet-4-5")}, {"fallback_model": "claude-opus-4-7,claude-sonnet-4-5"}),
        ("effort", {"effort": ClaudeEffort.HIGH}, {"effort": "high"}),
        ("thinking adaptive", {"thinking": ClaudeThinking(mode=ClaudeThinkingMode.ADAPTIVE)}, {"thinking": {"type": "adaptive"}}),
        ("thinking enabled", {"thinking": ClaudeThinking(mode=ClaudeThinkingMode.ENABLED, budget_tokens=8000, display=ClaudeThinkingDisplay.SUMMARIZED)}, {"thinking": {"type": "enabled", "budget_tokens": 8000, "display": "summarized"}}),
        ("thinking disabled", {"thinking": ClaudeThinking(mode=ClaudeThinkingMode.DISABLED)}, {"thinking": {"type": "disabled"}}),
        ("betas", {"betas": (ClaudeBeta.CONTEXT_1M,)}, {"betas": ["context-1m-2025-08-07"]}),
        ("system prompt append", {"system_prompt": ClaudeSystemPrompt(text="Prefer small diffs.")}, {"system_prompt": {**PRESET, "append": "Prefer small diffs."}}),
        ("system prompt replace", {"system_prompt": replace_prompt}, {"system_prompt": {"type": "custom", "prompt": "You review diffs."}}),
        ("system prompt file", {"system_prompt": ClaudeSystemPrompt(mode=ClaudeSystemPromptMode.FILE, text="C:/work/prompts/system.md")}, {"system_prompt": {"type": "file", "path": "C:/work/prompts/system.md"}}),
        ("exclude dynamic sections", {"exclude_dynamic_system_prompt_sections": True}, {"system_prompt": {**PRESET, "exclude_dynamic_sections": True}}),
        ("preset snapshot", {"system_prompt_snapshot": True}, {"system_prompt": {**PRESET, "snapshot": True}}),
        ("custom snapshot", {"system_prompt": replace_prompt, "system_prompt_snapshot": False}, {"system_prompt": {"type": "custom", "prompt": "You review diffs.", "snapshot": False}}),
        ("no builtin tools", {"builtin_tools": ()}, {"tools": []}),
        ("some builtin tools", {"builtin_tools": ("Read", "Grep")}, {"tools": ["Read", "Grep"]}),
        ("allowed tools", {"allowed_tools": ("Read",)}, {"allowed_tools": ["Read"]}),
        ("disallowed tools", {"disallowed_tools": ("Bash",)}, {"disallowed_tools": ["Bash"]}),
        ("permission mode", {"permission_mode": ClaudePermissionMode.PLAN}, {"permission_mode": "plan"}),
        ("restricted", {"restricted": True}, {"extra_args": {"restricted": None}}),
        ("sandbox", {"sandbox": sandbox}, {"sandbox": sandbox_options}),
        ("strict mcp config", {"strict_mcp_config": True}, {"strict_mcp_config": True}),
        ("skills", {"skills": ("pdf", "xlsx")}, {"skills": ["pdf", "xlsx"]}),
        ("no skills", {"skills": ()}, {"skills": []}),
        ("plugin folder", {"plugins": ("C:/work/plugins/review",)}, {"plugins": [{"type": "local", "path": "C:/work/plugins/review"}]}),
        ("plugin url", {"plugins": ("https://plugins.example.test/review.zip",)}, {"extra_args": {"plugin-url": "https://plugins.example.test/review.zip"}}),
        ("main agent", {"main_agent": "reviewer"}, {"extra_args": {"agent": "reviewer"}}),
        ("setting sources", {"setting_sources": (ClaudeSettingSource.PROJECT,)}, {"setting_sources": ["project"]}),
        ("no setting sources", {"setting_sources": ()}, {"setting_sources": []}),
        ("settings", {"settings": "C:/work/settings.json"}, {"settings": "C:/work/settings.json"}),
        ("bare", {"bare": True}, {"extra_args": {"bare": None}}),
        ("safe mode", {"safe_mode": True}, {"extra_args": {"safe-mode": None}}),
        ("max turns", {"max_turns": 12}, {"max_turns": 12}),
        ("max budget", {"max_budget_usd": 2.5}, {"max_budget_usd": 2.5}),
        ("task budget", {"task_budget": 50_000}, {"task_budget": {"total": 50_000}}),
        ("autocompact", {"autocompact": 200_000}, {"extra_args": {"autocompact": "200000"}}),
        ("max output tokens", {"max_output_tokens": 32_000}, {"env": {"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "32000"}}),
        ("name", {"name": "nightly-review"}, {"extra_args": {"name": "nightly-review"}}),
        ("fork a resumed session", {"resume": RESUMED_ID, "fork_session": True}, {"resume": RESUMED_ID, "fork_session": True}),
        ("fork at a message", {"resume": RESUMED_ID, "fork_session": True, "resume_session_at": ANCHOR_ID, "resume_drops_turn": DROP_ID}, {"resume": RESUMED_ID, "fork_session": True, "resume_session_at": ANCHOR_ID, "resume_drops_turn": DROP_ID}),
        ("fork the latest conversation", {"continue_conversation": True, "fork_session": True}, {"continue_conversation": True, "fork_session": True}),
        ("no persistence", {"persist_session": False}, {"extra_args": {"no-session-persistence": None}}),
        ("checkpointing", {"enable_file_checkpointing": True}, {"enable_file_checkpointing": True}),
        ("auto-named worktree", {"worktree": ""}, {"extra_args": {"worktree": None}}),
        ("named worktree", {"worktree": "feature-x"}, {"extra_args": {"worktree": "feature-x"}}),
        ("output schema", {"output_schema": SUMMARY_SCHEMA}, {"output_format": {"type": "json_schema", "schema": SUMMARY_SCHEMA}}),
        ("partial messages", {"include_partial_messages": True}, {"include_partial_messages": True}),
        ("hook events", {"include_hook_events": True}, {"include_hook_events": True}),
        ("subagent text", {"forward_subagent_text": True}, {"forward_subagent_text": True}),
        ("env", {"env": {"FEATURE_FLAG": "on"}}, {"env": {"FEATURE_FLAG": "on"}}),
        ("env and max output tokens", {"env": {"FEATURE_FLAG": "on"}, "max_output_tokens": 32_000}, {"env": {"FEATURE_FLAG": "on", "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "32000"}}),
        ("user", {"user": "builder"}, {"user": "builder"}),
        ("load timeout", {"load_timeout_ms": 90_000}, {"load_timeout_ms": 90_000}),
        ("time budget is the host's watchdog", {"timeout_seconds": 120.0}, {}),
        ("images travel in the prompt", {"prompt": "Describe the chart.", "images": (ClaudeImage(media_type=ClaudeImageMediaType.PNG, data=TINY_PNG_BASE64),)}, {}),
        ("no worktree", {"worktree": None}, {}),
    )


class OptionsMappingTests(unittest.TestCase):
    """AC-17, INV-17 and D-9 to D-11: each request field maps to the SDK surface its row names, and nothing else moves."""

    def test_default_request_sends_the_preset_and_the_headless_flag_only(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest

        options = translate(ClaudeSpawnRequest())
        passed = passed_options(options)
        self.assertEqual(set(passed), {"cli_path", "session_id", "system_prompt", "extra_args"})
        self.assertEqual(Path(passed["cli_path"]), Path(FAKE_CLI_PATH))
        self.assertEqual(passed["session_id"], SESSION_ID)
        self.assertEqual(plain(passed["system_prompt"]), PRESET)
        self.assertEqual(plain(passed["extra_args"]), HEADLESS_FLAGS)
        self.assertIs(type(options.extra_args["permission-prompts"]), str)
        self.assertIsNone(options.can_use_tool)
        self.assertIsNone(options.max_thinking_tokens)

    def test_each_mapping_row_changes_only_its_own_option(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest

        for label, fields, expected in mapping_cases():
            with self.subTest(row=label):
                options = translate(ClaudeSpawnRequest(**fields))
                self.assertEqual(changes(options), expected)
                self.assertIsInstance(options.system_prompt, dict, "the system prompt is always sent (INV-17)")
                # The SDK passes extra_args and env through str(), so they must already be plain text.
                for flag, value in dict(options.extra_args or {}).items():
                    self.assertTrue(value is None or type(value) is str, f"extra_args[{flag!r}] is {value!r}")
                for name, value in dict(options.env or {}).items():
                    self.assertIs(type(value), str, f"env[{name!r}] is {value!r}")

    def test_list_options_are_real_lists(self) -> None:
        # The SDK treats a non-list tools value as the preset and rejects a non-list skills value at connect.
        from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest

        options = translate(ClaudeSpawnRequest(builtin_tools=(), skills=("pdf",)))
        self.assertIs(type(options.tools), list)
        self.assertEqual(options.tools, [])
        self.assertIs(type(options.skills), list)

    def test_host_permission_prompts_pass_the_callback_and_no_flag(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest
        from vidbyte.lib.enums.claude import ClaudePermissionPrompts

        options = translate(ClaudeSpawnRequest(permission_prompts=ClaudePermissionPrompts.HOST, can_use_tool=decide_permission))
        self.assertIs(options.can_use_tool, decide_permission)
        self.assertNotIn("permission-prompts", dict(options.extra_args or {}))
        self.assertEqual(changes(options), {"can_use_tool": decide_permission})

    def test_hooks_become_hook_matchers_grouped_by_event(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeHookMatcher, ClaudeSpawnRequest
        from vidbyte.lib.enums.claude import ClaudeHookEvent

        request = ClaudeSpawnRequest(
            hooks=(
                ClaudeHookMatcher(event=ClaudeHookEvent.PRE_TOOL_USE, callbacks=(audit_hook, block_hook), matcher="Bash", timeout_seconds=30.0),
                ClaudeHookMatcher(event=ClaudeHookEvent.PRE_TOOL_USE, callbacks=(audit_hook,)),
                ClaudeHookMatcher(event=ClaudeHookEvent.STOP, callbacks=(block_hook,)),
            )
        )
        options = translate(request)
        expected = {
            "PreToolUse": [HookMatcher(matcher="Bash", hooks=[audit_hook, block_hook], timeout=30.0), HookMatcher(matcher=None, hooks=[audit_hook], timeout=None)],
            "Stop": [HookMatcher(matcher=None, hooks=[block_hook], timeout=None)],
        }
        self.assertEqual(changes(options), {"hooks": plain(expected)})
        for matchers in options.hooks.values():
            for matcher in matchers:
                self.assertIs(type(matcher), HookMatcher)

    def test_agents_become_camel_case_agent_definitions(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeAgentDefinition, ClaudeSpawnRequest
        from vidbyte.lib.enums.claude import ClaudeEffort, ClaudeMemoryScope, ClaudePermissionMode

        reviewer = ClaudeAgentDefinition(
            name="reviewer",
            description="Reviews diffs for bugs.",
            prompt="You review diffs.",
            tools=("Read", "Grep"),
            disallowed_tools=("Bash",),
            model="sonnet",
            skills=("pdf",),
            memory=ClaudeMemoryScope.PROJECT,
            mcp_servers=("files",),
            initial_prompt="Start with the tests.",
            max_turns=5,
            background=False,
            effort=ClaudeEffort.HIGH,
            permission_mode=ClaudePermissionMode.PLAN,
        )
        helper = ClaudeAgentDefinition(name="helper", description="Answers questions.", prompt="You answer questions.")
        options = translate(ClaudeSpawnRequest(agents=(reviewer, helper)))
        self.assertEqual(set(options.agents), {"reviewer", "helper"})
        self.assertIs(type(options.agents["reviewer"]), AgentDefinition)
        expected = AgentDefinition(
            description="Reviews diffs for bugs.",
            prompt="You review diffs.",
            tools=["Read", "Grep"],
            disallowedTools=["Bash"],
            model="sonnet",
            skills=["pdf"],
            memory="project",
            mcpServers=["files"],
            initialPrompt="Start with the tests.",
            maxTurns=5,
            background=False,
            effort="high",
            permissionMode="plan",
        )
        self.assertEqual(plain(options.agents["reviewer"]), plain(expected))
        minimal = options.agents["helper"]
        self.assertEqual((minimal.description, minimal.prompt), ("Answers questions.", "You answer questions."))
        for name in ("tools", "model", "skills", "memory", "initialPrompt", "maxTurns", "background", "effort", "permissionMode"):
            with self.subTest(unset=name):
                self.assertIsNone(getattr(minimal, name))
        self.assertFalse(minimal.disallowedTools)
        self.assertFalse(minimal.mcpServers)

    def test_external_mcp_servers_become_transport_dicts(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeMcpServer, ClaudeSpawnRequest
        from vidbyte.lib.enums.claude import ClaudeMcpTransport

        request = ClaudeSpawnRequest(
            mcp_servers=(
                ClaudeMcpServer(name="files", transport=ClaudeMcpTransport.STDIO, command="npx", args=("-y", "@example/files-server"), env={"FILES_ROOT": WORK_DIR}),
                ClaudeMcpServer(name="docs", transport=ClaudeMcpTransport.HTTP, url="https://mcp.example.test/docs", headers={"X-Team": "core"}),
                ClaudeMcpServer(name="events", transport=ClaudeMcpTransport.SSE, url="https://mcp.example.test/events", headers={"X-Team": "core"}),
            )
        )
        expected = {
            "files": {"type": "stdio", "command": "npx", "args": ["-y", "@example/files-server"], "env": {"FILES_ROOT": WORK_DIR}},
            "docs": {"type": "http", "url": "https://mcp.example.test/docs", "headers": {"X-Team": "core"}},
            "events": {"type": "sse", "url": "https://mcp.example.test/events", "headers": {"X-Team": "core"}},
        }
        self.assertEqual(changes(translate(request)), {"mcp_servers": expected})

    def test_tool_server_and_auto_allowed_names_join_the_options(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeMcpServer, ClaudeSpawnRequest
        from vidbyte.lib.enums.claude import ClaudeMcpTransport

        server = {"type": "sdk", "name": "vidbyte", "instance": object()}
        request = ClaudeSpawnRequest(
            tools=(TicketTool("lookup_ticket", ToolPermission.READ),),
            allowed_tools=("Read",),
            mcp_servers=(ClaudeMcpServer(name="files", transport=ClaudeMcpTransport.STDIO, command="npx"),),
        )
        options = translate(request, tool_server=server, auto_allowed=("mcp__vidbyte__lookup_ticket",))
        self.assertEqual(set(options.mcp_servers), {"files", "vidbyte"})
        self.assertIs(options.mcp_servers["vidbyte"], server)
        self.assertCountEqual(options.allowed_tools, ["Read", "mcp__vidbyte__lookup_ticket"])


class PromptTranslationTests(unittest.IsolatedAsyncioTestCase):
    """The images row and A-1: text alone is sent as a string, and images as one streamed user message of content blocks."""

    async def test_text_prompt_is_sent_as_a_string(self) -> None:
        from vidbyte.harnesses.native.claude.options import ClaudeOptionsTranslator
        from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest

        self.assertEqual(ClaudeOptionsTranslator.to_prompt(ClaudeSpawnRequest(prompt="Explain the build.")), "Explain the build.")

    async def test_images_become_one_user_message_of_blocks(self) -> None:
        from vidbyte.harnesses.native.claude.options import ClaudeOptionsTranslator
        from vidbyte.lib.dataclasses.claude import ClaudeImage, ClaudeSpawnRequest
        from vidbyte.lib.enums.claude import ClaudeImageMediaType

        request = ClaudeSpawnRequest(
            prompt="Describe both charts.",
            images=(ClaudeImage(media_type=ClaudeImageMediaType.PNG, data=TINY_PNG_BASE64), ClaudeImage(media_type=ClaudeImageMediaType.JPEG, data=TINY_JPEG_BASE64)),
        )
        messages = [message async for message in ClaudeOptionsTranslator.to_prompt(request)]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["type"], "user")
        expected = {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe both charts."},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": TINY_PNG_BASE64}},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": TINY_JPEG_BASE64}},
            ],
        }
        self.assertEqual(plain(messages[0]["message"]), expected)


class RequestValidationTests(unittest.TestCase):
    """AC-18, EC-35 to EC-40 and section 9.1: every invalid record raises ClaudeOperationError from validate_request, naming the field."""

    def assert_rejected(self, build: Any, codes: tuple[str, ...], fields: tuple[str, ...]) -> None:
        from vidbyte.lib.errors import ClaudeOperationError

        with self.assertRaises(ClaudeOperationError) as caught:
            build()
        error = caught.exception
        self.assertIn(error.failure_code, codes)
        self.assertEqual(error.operation, "validate_request")
        self.assertTrue(any(field in error.reason for field in fields), f"the reason {error.reason!r} names none of {fields}")
        expected_step = INVALID_ARGUMENT_NEXT_STEP if error.failure_code == INVALID_ARGUMENT else UNSUPPORTED_COMBINATION_NEXT_STEP
        self.assertEqual(error.next_step, expected_step)

    def test_invalid_values_and_combinations_are_rejected(self) -> None:
        from vidbyte.lib.dataclasses.claude import (
            ClaudeAgentDefinition,
            ClaudeHookMatcher,
            ClaudeImage,
            ClaudeMcpServer,
            ClaudeSpawnRequest,
            ClaudeSystemPrompt,
            ClaudeThinking,
        )
        from vidbyte.lib.dataclasses.claude_host import ClaudeHostSettings
        from vidbyte.lib.enums.claude import (
            ClaudeHookEvent,
            ClaudeImageMediaType,
            ClaudeMcpTransport,
            ClaudePermissionPrompts,
            ClaudeSystemPromptMode,
            ClaudeThinkingDisplay,
            ClaudeThinkingMode,
        )

        request = ClaudeSpawnRequest
        png = ClaudeImage(media_type=ClaudeImageMediaType.PNG, data=TINY_PNG_BASE64)
        files_server = ClaudeMcpServer(name="files", transport=ClaudeMcpTransport.STDIO, command="npx")
        reviewer = ClaudeAgentDefinition(name="reviewer", description="Reviews diffs.", prompt="You review diffs.")
        replace_prompt = ClaudeSystemPrompt(mode=ClaudeSystemPromptMode.REPLACE, text="You review diffs.")
        file_prompt = ClaudeSystemPrompt(mode=ClaudeSystemPromptMode.FILE, text="C:/work/prompts/system.md")
        cases = (
            ("bool count", lambda: request(max_turns=True), SINGLE, ("max_turns",)),
            ("zero count", lambda: request(max_turns=0), SINGLE, ("max_turns",)),
            ("float count", lambda: request(max_turns=2.0), SINGLE, ("max_turns",)),
            ("nan amount", lambda: request(max_budget_usd=math.nan), SINGLE, ("max_budget_usd",)),
            ("infinite amount", lambda: request(max_budget_usd=math.inf), SINGLE, ("max_budget_usd",)),
            ("zero amount", lambda: request(max_budget_usd=0.0), SINGLE, ("max_budget_usd",)),
            ("bool amount", lambda: request(max_budget_usd=True), SINGLE, ("max_budget_usd",)),
            ("negative time budget", lambda: request(timeout_seconds=-1.0), SINGLE, ("timeout_seconds",)),
            ("zero task budget", lambda: request(task_budget=0), SINGLE, ("task_budget",)),
            ("bool output cap", lambda: request(max_output_tokens=False), SINGLE, ("max_output_tokens",)),
            ("zero load timeout", lambda: request(load_timeout_ms=0), SINGLE, ("load_timeout_ms",)),
            ("autocompact below range", lambda: request(autocompact=99_999), SINGLE, ("autocompact",)),
            ("autocompact above range", lambda: request(autocompact=1_000_001), SINGLE, ("autocompact",)),
            ("non-UUID session id", lambda: request(session_id="session-7"), SINGLE, ("session_id",)),
            ("non-UUID resume", lambda: request(resume="last-session"), SINGLE, ("resume",)),
            ("non-UUID resume point", lambda: request(resume=RESUMED_ID, resume_session_at="message-12"), SINGLE, ("resume_session_at",)),
            ("session id with resume but no fork", lambda: request(session_id=SESSION_ID, resume=RESUMED_ID), EITHER, ("session_id", "fork_session")),
            ("session id with continue but no fork", lambda: request(session_id=SESSION_ID, continue_conversation=True), EITHER, ("session_id", "fork_session")),
            ("resume and continue together", lambda: request(resume=RESUMED_ID, continue_conversation=True), EITHER, ("resume", "continue_conversation")),
            ("fork with nothing to fork", lambda: request(fork_session=True), EITHER, ("fork_session",)),
            ("resume point without resume", lambda: request(resume_session_at=ANCHOR_ID), EITHER, ("resume_session_at",)),
            ("dropped turn without resume point", lambda: request(resume=RESUMED_ID, resume_drops_turn=DROP_ID), EITHER, ("resume_drops_turn",)),
            ("two files", lambda: request(files=("file_a:docs/a.md", "file_b:docs/b.md")), SINGLE, ("files",)),
            ("file without an id", lambda: request(files=("docs/a.md",)), SINGLE, ("files",)),
            ("two plugin URLs", lambda: request(plugins=("https://plugins.example.test/a.zip", "https://plugins.example.test/b.zip")), SINGLE, ("plugins",)),
            ("comma in a fallback model", lambda: request(fallback_model=("claude-opus-4-7,claude-sonnet-4-5",)), SINGLE, ("fallback_model",)),
            ("output cap set twice", lambda: request(max_output_tokens=32_000, env={"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "16000"}), (UNSUPPORTED_COMBINATION,), ("max_output_tokens", "env")),
            ("reserved server name", lambda: request(tools=(TicketTool("lookup_ticket", ToolPermission.READ),), mcp_servers=(ClaudeMcpServer(name="vidbyte", transport=ClaudeMcpTransport.STDIO, command="npx"),)), SINGLE, ("mcp_servers", "vidbyte")),
            ("duplicate tool names", lambda: request(tools=(TicketTool("lookup_ticket", ToolPermission.READ), TicketTool("lookup_ticket", ToolPermission.WRITE))), SINGLE, ("tools",)),
            ("not a tool", lambda: request(tools=(object(),)), SINGLE, ("tools",)),
            ("duplicate server names", lambda: request(mcp_servers=(files_server, files_server)), SINGLE, ("mcp_servers",)),
            ("stdio server without a command", lambda: ClaudeMcpServer(name="files", transport=ClaudeMcpTransport.STDIO), EITHER, ("command",)),
            ("http server without a URL", lambda: ClaudeMcpServer(name="docs", transport=ClaudeMcpTransport.HTTP), EITHER, ("url",)),
            ("duplicate agent names", lambda: request(agents=(reviewer, reviewer)), SINGLE, ("agents",)),
            ("agent with zero turns", lambda: ClaudeAgentDefinition(name="reviewer", description="Reviews diffs.", prompt="You review diffs.", max_turns=0), SINGLE, ("max_turns",)),
            ("unknown effort", lambda: request(effort="extreme"), SINGLE, ("effort",)),
            ("unknown permission mode", lambda: request(permission_mode="root"), SINGLE, ("permission_mode",)),
            ("unknown image type", lambda: ClaudeImage(media_type="image/bmp", data=TINY_PNG_BASE64), SINGLE, ("media_type",)),
            ("empty image data", lambda: ClaudeImage(media_type=ClaudeImageMediaType.PNG, data=""), SINGLE, ("data",)),
            ("image data that is not base64", lambda: ClaudeImage(media_type=ClaudeImageMediaType.PNG, data="not base64!"), SINGLE, ("data",)),
            ("images without a prompt", lambda: request(images=(png,)), EITHER, ("images", "prompt")),
            ("enabled thinking without a budget", lambda: ClaudeThinking(mode=ClaudeThinkingMode.ENABLED), EITHER, ("budget_tokens",)),
            ("adaptive thinking with a budget", lambda: ClaudeThinking(mode=ClaudeThinkingMode.ADAPTIVE, budget_tokens=8000), EITHER, ("budget_tokens",)),
            ("disabled thinking with a display", lambda: ClaudeThinking(mode=ClaudeThinkingMode.DISABLED, display=ClaudeThinkingDisplay.SUMMARIZED), EITHER, ("display",)),
            ("replacement prompt without text", lambda: ClaudeSystemPrompt(mode=ClaudeSystemPromptMode.REPLACE), EITHER, ("text",)),
            ("file prompt without a path", lambda: ClaudeSystemPrompt(mode=ClaudeSystemPromptMode.FILE), EITHER, ("text",)),
            ("dynamic sections outside the preset", lambda: request(system_prompt=replace_prompt, exclude_dynamic_system_prompt_sections=True), EITHER, ("exclude_dynamic_system_prompt_sections",)),
            ("snapshot of a file prompt", lambda: request(system_prompt=file_prompt, system_prompt_snapshot=True), EITHER, ("system_prompt_snapshot",)),
            ("host prompts without a callback", lambda: request(permission_prompts=ClaudePermissionPrompts.HOST), EITHER, ("can_use_tool", "permission_prompts")),
            ("headless prompts with a callback", lambda: request(can_use_tool=decide_permission), EITHER, ("can_use_tool", "permission_prompts")),
            ("store without load and append", lambda: request(session_store=object()), SINGLE, ("session_store",)),
            ("empty extra directory", lambda: request(add_dirs=("",)), SINGLE, ("add_dirs",)),
            ("non-text env value", lambda: request(env={"FEATURE_FLAG": 1}), SINGLE, ("env",)),
            ("zero hook timeout", lambda: ClaudeHookMatcher(event=ClaudeHookEvent.PRE_TOOL_USE, callbacks=(audit_hook,), timeout_seconds=0.0), SINGLE, ("timeout_seconds",)),
            ("non-text prompt", lambda: request(prompt=5), SINGLE, ("prompt",)),
            ("zero live cap", lambda: ClaudeHostSettings(max_live_sessions=0), SINGLE, ("max_live_sessions",)),
            ("bool live cap", lambda: ClaudeHostSettings(max_live_sessions=True), SINGLE, ("max_live_sessions",)),
        )
        for label, build, codes, fields in cases:
            with self.subTest(case=label):
                self.assert_rejected(build, codes, fields)

    def test_boundary_values_and_raw_enum_values_are_accepted(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeImage, ClaudeSpawnRequest, ClaudeThinking
        from vidbyte.lib.dataclasses.claude_host import ClaudeHostSettings
        from vidbyte.lib.enums.claude import ClaudeEffort, ClaudeImageMediaType, ClaudePermissionMode, ClaudePermissionPrompts, ClaudeThinkingMode

        png = ClaudeImage(media_type=ClaudeImageMediaType.PNG, data=TINY_PNG_BASE64)
        accepted = (
            dict(max_turns=1, max_budget_usd=0.01, task_budget=1, max_output_tokens=1, load_timeout_ms=1, timeout_seconds=0.5, autocompact=100_000),
            dict(autocompact=1_000_000),
            dict(session_id=SESSION_ID),
            dict(session_id=SESSION_ID, resume=RESUMED_ID, fork_session=True),
            dict(continue_conversation=True),
            dict(resume=RESUMED_ID, resume_session_at=ANCHOR_ID, resume_drops_turn=DROP_ID),
            dict(prompt="Describe the chart.", images=(png,)),
            dict(files=(FILE_SPEC,)),
            dict(plugins=("C:/work/plugins/review", "https://plugins.example.test/review.zip")),
            dict(permission_prompts=ClaudePermissionPrompts.HOST, can_use_tool=decide_permission),
            dict(session_store=MemorySessionStore()),
            dict(env={"FEATURE_FLAG": "on"}, max_output_tokens=32_000),
        )
        for fields in accepted:
            with self.subTest(fields=sorted(fields)):
                ClaudeSpawnRequest(**fields)
        self.assertIs(ClaudeSpawnRequest(effort="high").effort, ClaudeEffort.HIGH)
        self.assertIs(ClaudeSpawnRequest(permission_mode="plan").permission_mode, ClaudePermissionMode.PLAN)
        self.assertIs(ClaudeThinking(mode="enabled", budget_tokens=1024).mode, ClaudeThinkingMode.ENABLED)
        self.assertEqual(ClaudeHostSettings(max_live_sessions=1).max_live_sessions, 1)
        self.assertIsNone(ClaudeHostSettings().max_live_sessions)


class CustomToolServerTests(ClaudeHostCase):
    """AC-20, D-12 and EC-41: request.tools reach Claude through one in-process server named vidbyte, and its handlers never raise."""

    async def test_two_tools_share_one_vidbyte_server_and_only_read_is_auto_allowed(self) -> None:
        lookup = TicketTool("lookup_ticket", ToolPermission.READ)
        close = TicketTool("close_ticket", ToolPermission.WRITE)
        host = await self.open_host()
        handle = await self.spawn(host, tools=(lookup, close), allowed_tools=("Read",))
        result = await self.finished(host, handle)
        self.assertEqual(result.status.value, "completed")
        client = await self.client_for(handle)
        self.assertEqual(len(self.fake.mcp_servers), 1)
        config = self.fake.mcp_servers[0]
        self.assertEqual(config["name"], "vidbyte")
        self.assertEqual(set(client.options.mcp_servers), {"vidbyte"})
        self.assertEqual(client.options.mcp_servers["vidbyte"], config)
        sdk_tools = config["instance"].tools
        self.assertEqual([sdk_tool.name for sdk_tool in sdk_tools], ["lookup_ticket", "close_ticket"])
        for sdk_tool, tool in zip(sdk_tools, (lookup, close)):
            with self.subTest(tool=tool.spec().name):
                self.assertEqual(sdk_tool.description, tool.spec().description)
                self.assertEqual(sdk_tool.input_schema, ToolsFormatter.to_anthropic_tool(tool.spec())["input_schema"])
        self.assertCountEqual(client.options.allowed_tools, ["Read", "mcp__vidbyte__lookup_ticket"])
        # Claude calls each tool through its handler, which runs it through ToolExecutor.
        self.assertEqual(await sdk_tools[0].handler({"ticket": "T-7"}), {"content": [{"type": "text", "text": "ticket T-7 is open"}], "is_error": False})
        self.assertEqual(await sdk_tools[1].handler({"ticket": "T-8"}), {"content": [{"type": "text", "text": "ticket T-8 is open"}], "is_error": False})
        self.assertEqual(lookup.calls, [{"ticket": "T-7"}])
        self.assertEqual(close.calls, [{"ticket": "T-8"}])

    async def test_failing_tools_return_error_content_instead_of_raising(self) -> None:
        raising = TicketTool("lookup_ticket", ToolPermission.READ, outcome="raise")
        erroring = TicketTool("close_ticket", ToolPermission.WRITE, outcome="error")
        host = await self.open_host()
        handle = await self.spawn(host, tools=(raising, erroring))
        await self.finished(host, handle)
        raising_tool, erroring_tool = self.fake.mcp_servers[0]["instance"].tools
        # The executor's own message is passed through unchanged (EC-41).
        reference = await ToolExecutor(Tools([TicketTool("lookup_ticket", ToolPermission.READ, outcome="raise")]), permission_policy=PermissionPolicy.allow_all()).execute_call(ToolCall(tool_name="lookup_ticket", arguments={"ticket": "T-7"}))
        self.assertEqual(await raising_tool.handler({"ticket": "T-7"}), {"content": [{"type": "text", "text": reference.output}], "is_error": True})
        self.assertEqual(await erroring_tool.handler({"ticket": "T-9"}), {"content": [{"type": "text", "text": "ticket not found"}], "is_error": True})
        missing_argument = await raising_tool.handler({})
        self.assertTrue(missing_argument["is_error"])

    async def test_a_request_without_tools_builds_no_server(self) -> None:
        host = await self.open_host()
        handle = await self.spawn(host)
        await self.finished(host, handle)
        client = await self.client_for(handle)
        self.assertEqual(self.fake.mcp_servers, [])
        self.assertNotIn("vidbyte", dict(client.options.mcp_servers or {}))

    async def test_image_prompts_reach_the_client_as_one_user_message(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeImage
        from vidbyte.lib.enums.claude import ClaudeImageMediaType

        host = await self.open_host()
        handle = await self.spawn(host, "Describe the chart.", images=(ClaudeImage(media_type=ClaudeImageMediaType.PNG, data=TINY_PNG_BASE64),))
        result = await self.finished(host, handle)
        self.assertEqual(result.status.value, "completed")
        client = await self.client_for(handle)
        self.assertEqual(len(client.queries), 1)
        sent = client.queries[0]
        self.assertIsInstance(sent, list)
        self.assertEqual(len(sent), 1)
        self.assertEqual([block["type"] for block in sent[0]["message"]["content"]], ["text", "image"])


class ToolServerUnitTests(unittest.IsolatedAsyncioTestCase):
    """D-12 and section 12.3 row 10: the auto-allowed names and the never-raising handler."""

    async def test_auto_allowed_names_cover_only_safe_and_read_tools(self) -> None:
        from vidbyte.harnesses.native.claude.tool_server import ClaudeToolServer

        tools = (
            TicketTool("lookup_ticket", ToolPermission.READ),
            TicketTool("ping_tracker", ToolPermission.SAFE),
            TicketTool("close_ticket", ToolPermission.WRITE),
            TicketTool("run_migration", ToolPermission.EXECUTE),
        )
        self.assertEqual(tuple(ClaudeToolServer.auto_allowed(tools)), ("mcp__vidbyte__lookup_ticket", "mcp__vidbyte__ping_tracker"))

    async def test_handler_returns_text_for_success_unknown_tools_and_crashes(self) -> None:
        from vidbyte.harnesses.native.claude.tool_server import ClaudeToolHandler

        executor = ToolExecutor(Tools([TicketTool("lookup_ticket", ToolPermission.READ)]), permission_policy=PermissionPolicy.allow_all())
        self.assertEqual(await ClaudeToolHandler(executor, "lookup_ticket")({"ticket": "T-3"}), {"content": [{"type": "text", "text": "ticket T-3 is open"}], "is_error": False})
        unknown = await ClaudeToolHandler(executor, "missing_tool")({"ticket": "T-3"})
        self.assertTrue(unknown["is_error"])
        # A failure the executor itself does not catch still comes back as error text, without the raw exception text.
        broken = ToolExecutor(Tools([BrokenValidationTool("lookup_ticket", ToolPermission.READ)]), permission_policy=PermissionPolicy.allow_all())
        crashed = await ClaudeToolHandler(broken, "lookup_ticket")({"ticket": "T-3"})
        self.assertTrue(crashed["is_error"])
        text = crashed["content"][0]["text"]
        self.assertTrue(text)
        self.assertNotIn(ERROR_MARKER, text)
        self.assertNotIn(ENV_MARKER, text)


if __name__ == "__main__":
    unittest.main()

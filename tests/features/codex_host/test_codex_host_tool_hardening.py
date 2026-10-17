"""FILE: tests/features/codex_host/test_codex_host_tool_hardening.py

PURPOSE: Proves the agent-tool half of the hardening slice: a host method that raises something other than a Codex or configuration error becomes a codex.api_error result naming only the tool and the exception type, with one WARNING, while cancellation still propagates; the toolset still holds exactly 26 tools and gives the model no handle on the reviewer, approval policy, sandbox, network access, writable roots, service tier, handler or the new fork and skill arguments; the spawn and continue tools offer the max and ultra efforts; a goal objective with an effort is refused when the request is built; and a USER reviewer in spawn_defaults is refused before any request on a host without a handler.
ROLE IN CODEBASE: Tool layer of the hardening tests in tests/features/codex_host/ (docs/spec/codex-host-hardening/spec.md AC-17, AC-30 schema half, AC-36, INV-23, INV-44, EC-33, EC-43, EC-46; EC-32 is pinned in test_codex_host_tools.py). The stub-host classes run on CI without openai-codex; the spawn_defaults class drives a real host, so CI skips it.
ARCHITECTURE NOTE: The tools are executed directly over StubCodexHost, whose raises table makes one host method raise, so the tool's own _run is what turns it into a result; the WARNING is read from a recorder on the tools' logger. The negative schema check reads every tool's input_schema properties, so a new parameter of any tool is seen.
COMMON MODIFICATION PATTERNS: A parameter that may never reach the model joins FORBIDDEN_PARAMETERS; a tool that should be covered by the local-failure rows joins NO_HANDLE_ARGUMENTS with arguments it accepts.
KNOWN EDGE CASES: The stub raises from its _enter helper, so the logged origin names codex_host_support.py, which is what proves the origin is the innermost frame and not the tool's own. The negative rows are green before the slice lands and stay as guards (S2 test plan, AC-36).
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-hardening/spec.md sections 6.1 (INV-23, INV-44) and 6.3.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_tool_hardening.py
"""

from __future__ import annotations

import asyncio
import logging
import unittest
from typing import Any

from tests.features.codex_host.codex_host_support import (
    GOAL_FIELD_MESSAGE,
    GOAL_SPAWN_OWNER,
    NEXT_STEPS,
    TOOL_NAMES,
    TOOLS_LOGGER,
    USER_REVIEWER_TEXT,
    WAIT_SECONDS,
    HostTestCase,
    LogRecorder,
    StubCodexHost,
    log_events,
    log_fields,
    requires_sdk,
)
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult, ToolStatus

TOOL_CANARY = "tool-canary-e83a"
# Tools that need no turn handle, with arguments each accepts.
NO_HANDLE_ARGUMENTS: dict[str, dict[str, Any]] = {
    "check_codex_ready": {},
    "get_codex_rate_limits": {},
    "list_codex_models": {},
    "list_codex_threads": {},
    "read_codex_thread": {"thread_id": "thr-elsewhere"},
    "track_codex_thread_usage": {"thread_id": "thr-elsewhere"},
    "spawn_codex_thread": {"prompt": "Fix the failing test."},
    "list_codex_skills": {},
    "get_codex_goal": {"thread_id": "thr-elsewhere"},
    # docs/spec/codex-host-first-class/spec.md section 13: one row per new tool that needs no turn handle.
    "update_codex_thread_settings": {"thread_id": "thr-elsewhere", "effort": "high"},
    "list_codex_collaboration_modes": {},
    "run_codex_plan": {"prompt": "Plan a fix for the failing test."},
    "list_codex_mcp_servers": {},
    "get_codex_memory_status": {},
    "start_codex_side_chat": {"thread_id": "thr-elsewhere", "prompt": "Which step of the plan is riskiest?"},
    "pause_codex_goal": {"thread_id": "thr-elsewhere"},
    "resume_codex_goal": {"thread_id": "thr-elsewhere"},
    "archive_codex_thread": {"thread_id": "thr-elsewhere"},
    "unarchive_codex_thread": {"thread_id": "thr-elsewhere"},
    "rename_codex_thread": {"thread_id": "thr-elsewhere", "name": "Login fix"},
    "list_codex_background_terminals": {"thread_id": "thr-elsewhere"},
    "search_codex_thread_content": {"query": "login"},
    "list_codex_child_threads": {"thread_id": "thr-elsewhere"},
}
# INV-44 and AC-36: parameter names no tool may offer the model.
FORBIDDEN_PARAMETERS = frozenset(
    {
        "approvals_reviewer",
        "approval_policy",
        "approval_mode",
        "sandbox",
        "network_access",
        "writable_roots",
        "turn_service_tier",
        "service_tier",
        "approval_handler",
        "handler",
        "before_turn_id",
        "defer_goal_continuation",
        "force_reload",
    }
)


def _toolset(host: Any, spawn_defaults: Any = None) -> Any:
    from vidbyte.tools.toolsets import CodexHostTools

    return CodexHostTools(host, max_live_turns=5, spawn_defaults=spawn_defaults)


async def _call(tools: Any, name: str, arguments: dict[str, Any]) -> ToolResult:
    tool = next(tool for tool in tools if tool.spec().name == name)
    return await asyncio.wait_for(tool.execute(ToolCall(tool_name=name, arguments=dict(arguments))), WAIT_SECONDS)


class CodexToolLocalFailureTests(unittest.IsolatedAsyncioTestCase):
    """AC-17, INV-23 and EC-43: an unexpected exception under a tool is a result and one WARNING, never a raise."""

    def setUp(self) -> None:
        self.recorder = LogRecorder()
        logger = logging.getLogger(TOOLS_LOGGER)
        self.addCleanup(logger.setLevel, logger.level)
        self.addCleanup(logger.removeHandler, self.recorder)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(self.recorder)

    async def test_a_runtime_or_key_error_becomes_an_api_error_result_naming_only_the_tool_and_type(self) -> None:
        api_next_step = NEXT_STEPS["codex.api_error"]
        for error_type in (RuntimeError, KeyError):
            for name, arguments in NO_HANDLE_ARGUMENTS.items():
                with self.subTest(tool=name, error=error_type.__name__):
                    host = StubCodexHost()
                    host.raises[name] = error_type(TOOL_CANARY)
                    before = len(log_events(self.recorder.records, "codex_host_tool_failed"))
                    result = await _call(_toolset(host), name, arguments)
                    self.assertEqual(result.status, ToolStatus.ERROR, result.output)
                    self.assertEqual(result.output, f"codex.api_error: {name} failed with {error_type.__name__}. Next step: {api_next_step}")
                    self.assertEqual(result.output.count("Next step:"), 1)
                    self.assertEqual(result.metadata, {"code": "codex.api_error", "next_step": api_next_step})
                    logged = log_events(self.recorder.records, "codex_host_tool_failed")[before:]
                    self.assertEqual(len(logged), 1)
                    self.assertEqual(logged[0].levelno, logging.WARNING)
                    fields = log_fields(logged[0])
                    self.assertEqual((fields["tool"], fields["error_type"]), (name, error_type.__name__))
                    self.assertTrue(fields["origin"].startswith("codex_host_support.py:_enter:"), fields)
        for record in self.recorder.records:
            self.assertNotIn(TOOL_CANARY, record.getMessage())
            self.assertIsNone(record.exc_info)

    async def test_cancellation_still_propagates_and_logs_nothing(self) -> None:
        host = StubCodexHost()
        host.raises["read_codex_thread"] = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await _call(_toolset(host), "read_codex_thread", {"thread_id": "thr-elsewhere"})
        self.assertEqual(log_events(self.recorder.records, "codex_host_tool_failed"), [])


class CodexToolSurfaceGuardTests(unittest.TestCase):
    """AC-36, AC-30 schema half, INV-44 and D-29: the toolset's surface after the slice."""

    def test_the_toolset_holds_26_tools_and_offers_no_forbidden_parameter(self) -> None:
        tools = _toolset(StubCodexHost())
        # docs/spec/codex-host-first-class/spec.md section 13: 42 tools (INV-41).
        self.assertEqual(len(tools), 42)
        self.assertEqual(tuple(tools.names()), TOOL_NAMES)
        for tool in tools:
            spec = tool.spec()
            with self.subTest(tool=spec.name):
                properties = set(spec.input_schema.get("properties", {}))
                self.assertEqual(properties & FORBIDDEN_PARAMETERS, set())
                if spec.name == "fork_codex_thread":
                    self.assertNotIn("limit", properties)

    def test_the_spawn_and_continue_tools_offer_max_and_ultra(self) -> None:
        tools = _toolset(StubCodexHost())
        for name in ("spawn_codex_thread", "continue_codex_thread"):
            with self.subTest(tool=name):
                spec = next(tool for tool in tools if tool.spec().name == name).spec()
                efforts = spec.input_schema["properties"]["effort"]["enum"]
                self.assertEqual(efforts[-2:], ["max", "ultra"])
                self.assertEqual(efforts[:-2], ["none", "minimal", "low", "medium", "high", "xhigh"])


class CodexToolGoalEffortTests(unittest.IsolatedAsyncioTestCase):
    """EC-33 and INV-34: a goal objective with an effort is refused when the request is built, before the host."""

    async def test_a_goal_spawn_with_an_effort_is_an_invalid_argument_naming_turn(self) -> None:
        host = StubCodexHost()
        result = await _call(_toolset(host), "spawn_codex_thread", {"goal_objective": "Ship the fix.", "effort": "high"})
        self.assertEqual(result.status, ToolStatus.ERROR, result.output)
        self.assertEqual(result.metadata["code"], "configuration.invalid_argument")
        self.assertIn(GOAL_FIELD_MESSAGE.format(owner=GOAL_SPAWN_OWNER, name="turn"), result.output)
        self.assertNotIn("spawn_codex_thread", host.names())


@requires_sdk
class CodexToolUserReviewerTests(HostTestCase):
    """EC-46 and INV-20: a USER reviewer in spawn_defaults is refused by every spawn on a host without a handler."""

    async def test_spawn_and_launch_tools_return_unsupported_combination_and_send_nothing(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.lib.enums.codex import CodexApprovalsReviewer

        host = await self.open_host()
        tools = _toolset(host, spawn_defaults=CodexSpawnRequest(approvals_reviewer=CodexApprovalsReviewer.USER))
        sent = len(self.server.requests)
        for name, arguments in (("spawn_codex_thread", {"prompt": "Fix the failing test."}), ("launch_codex_subagents", {"prompts": ["Review module A."]})):
            with self.subTest(tool=name):
                result = await _call(tools, name, arguments)
                self.assertEqual(result.status, ToolStatus.ERROR, result.output)
                self.assertEqual(result.metadata, {"code": "configuration.unsupported_combination", "next_step": USER_REVIEWER_TEXT})
        self.assertEqual(len(self.server.requests), sent)


if __name__ == "__main__":
    unittest.main()

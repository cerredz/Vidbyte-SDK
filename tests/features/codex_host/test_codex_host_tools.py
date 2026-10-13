"""FILE: tests/features/codex_host/test_codex_host_tools.py

PURPOSE: Proves the fifteen CodexHost agent tools and CodexHostTools: their names, classes, permissions and parameters; error results instead of exceptions; the live-turn cap and per-scope handle ownership, including under concurrency; spawn_defaults as the posture with model values replacing only the six allowed fields and JSON null as omitted; argument checks before the host; the wait clamp; record JSON outputs; and reachability through McpStudioServer.
ROLE IN CODEBASE: Tool layer of tests/features/codex_host/ (spec AC-23 to AC-27, INV-10, INV-31 to INV-35, EC-53 to EC-57, EC-64, D-10 to D-12, D-31). It runs the tools over StubCodexHost, which spec section 13 allows because the tools import CodexHost only under TYPE_CHECKING, so CI runs it without openai-codex.
ARCHITECTURE NOTE: Tools are executed directly, the way McpStudioServer runs them, so the checks prove each tool validates its own arguments; the permission checks go through the real ToolExecutor and PermissionPolicy. StubCodexHost records each call and reports a handle RUNNING until the test finishes it, which is how the cap sees running turns.
COMMON MODIFICATION PATTERNS: Add a tool row to TOOL_TABLE in codex_host_support.py, then an argument set to VALID_ARGUMENTS here. Assert on the request the stub received, never on how the tool built it.
KNOWN EDGE CASES: A cap check may read a handle's status through get_codex_turn_result, a local read that sends nothing to Codex, so "no host call" assertions name the refused method rather than requiring an empty call log. JSON null must behave exactly like an omitted argument.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host/spec.md section 9.2 (Tools, Scope rules, MCP).
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_tools.py
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import math
import os
import unittest
from typing import Any

from tests.features.codex_host.codex_host_support import (
    NEXT_STEPS,
    TOOL_NAMES,
    TOOL_TABLE,
    WAIT_SECONDS,
    StubCodexHost,
    make_echo_tool,
)
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult, ToolStatus
from vidbyte.lib.errors import CodexAgentError, ConfigurationError, ToolExecutionError
from vidbyte.tools.executor import ToolExecutor

WORKSPACE = os.path.abspath(os.path.join(os.sep, "agent-workspace"))
WRITE_TOOLS = tuple(row[0] for row in TOOL_TABLE if row[2] == "write")
TURN_STARTING_TOOLS = ("spawn_codex_thread", "continue_codex_thread", "launch_codex_subagents", "start_codex_review")
HANDLE_TOOLS = ("wait_codex_turn", "get_codex_turn_result", "steer_codex_turn", "interrupt_codex_turn")


def _valid_arguments(handle: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Arguments each tool accepts; the handle must belong to the scope under test."""
    return {
        "check_codex_ready": {},
        "get_codex_rate_limits": {},
        "list_codex_models": {"include_hidden": True},
        "spawn_codex_thread": {"prompt": "Fix the failing test."},
        "continue_codex_thread": {"thread_id": "thr-elsewhere", "prompt": "Carry on."},
        "fork_codex_thread": {"thread_id": "thr-elsewhere"},
        "list_codex_threads": {},
        "read_codex_thread": {"thread_id": "thr-elsewhere"},
        "wait_codex_turn": dict(handle),
        "get_codex_turn_result": dict(handle),
        "steer_codex_turn": {**handle, "prompt": "Also update the changelog."},
        "interrupt_codex_turn": dict(handle),
        "track_codex_thread_usage": {"thread_id": "thr-elsewhere"},
        "launch_codex_subagents": {"prompts": ["Review module A."]},
        "start_codex_review": {"thread_id": "thr-elsewhere", "target_kind": "uncommittedChanges"},
    }


def _toolset(host: Any, *, max_live_turns: int = 5, spawn_defaults: Any = None) -> Any:
    from vidbyte.tools.toolsets import CodexHostTools

    return CodexHostTools(host, max_live_turns=max_live_turns, spawn_defaults=spawn_defaults)


def _tool(tools: Any, name: str) -> Any:
    for tool in tools:
        if tool.spec().name == name:
            return tool
    raise AssertionError(f"the toolset has no tool named {name}")


async def _call(tools: Any, name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
    tool = _tool(tools, name)
    return await asyncio.wait_for(tool.execute(ToolCall(tool_name=name, arguments=dict(arguments or {}))), WAIT_SECONDS)


def _handle_of(result: ToolResult) -> dict[str, str]:
    payload = json.loads(result.output)
    return {"thread_id": payload["thread_id"], "turn_id": payload["turn_id"]}


def _finish(host: StubCodexHost, handle: dict[str, str]) -> None:
    """Mark a stub turn finished, so the cap and the snapshots see it as terminal."""
    from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle

    host.finish(CodexTurnHandle(**handle))


async def _until(condition: Any, what: str) -> None:
    """Yield to the loop until the condition holds; a bounded count keeps a broken tool from hanging the test."""
    for _ in range(10_000):
        if condition():
            return
        await asyncio.sleep(0)
    raise AssertionError(f"timed out waiting for {what}")


def _defaults(**changes: Any) -> Any:
    """A developer posture: sandbox, approvals, cwd, tools and instructions, plus model-replaceable values."""
    from vidbyte.lib.dataclasses.codex import CodexThreadSettings, CodexTurnSettings
    from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
    from vidbyte.lib.enums.codex import CodexApprovalPolicy, CodexApprovalsReviewer, CodexReasoningEffort, CodexReasoningSummary, CodexSandbox

    fields: dict[str, Any] = {
        "thread": CodexThreadSettings(sandbox=CodexSandbox.READ_ONLY, cwd=WORKSPACE, model="gpt-5.4-mini"),
        "turn": CodexTurnSettings(effort=CodexReasoningEffort.LOW, summary=CodexReasoningSummary.CONCISE),
        "approval_policy": CodexApprovalPolicy.ON_REQUEST,
        "approvals_reviewer": CodexApprovalsReviewer.AUTO_REVIEW,
        "tools": (make_echo_tool(),),
        "developer_instructions": "Never push to the main branch.",
        "max_output_tokens": 4000,
        "timeout_seconds": 600.0,
    }
    fields.update(changes)
    return CodexSpawnRequest(**fields)


class _ToolCase(unittest.IsolatedAsyncioTestCase):
    def assert_error_result(self, result: ToolResult, code: str) -> None:
        """INV-10: an error result carries "<code>: <message> Next step: <next_step>" and the two metadata keys."""
        self.assertEqual(result.status, ToolStatus.ERROR, result.output)
        self.assertEqual(result.metadata, {"code": code, "next_step": NEXT_STEPS[code]}, result.output)
        self.assertTrue(result.output.startswith(f"{code}: "), result.output)
        self.assertTrue(result.output.endswith(f" Next step: {NEXT_STEPS[code]}"), result.output)

    async def spawn_handle(self, tools: Any) -> dict[str, str]:
        result = await _call(tools, "spawn_codex_thread", {"prompt": "Fix the failing test."})
        self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
        return _handle_of(result)


class CodexHostToolsShapeTests(_ToolCase):
    """AC-23 and INV-31: fifteen tools, R3 order, the section 9.2 names, classes, permissions and parameters."""

    def test_toolset_holds_the_fifteen_tools_with_their_spec_schemas(self) -> None:
        import vidbyte.tools.builtins.codex as builtin_codex

        tools = _toolset(StubCodexHost(), max_live_turns=2)
        self.assertEqual(len(tools), 15)
        self.assertEqual(tuple(tools.names()), TOOL_NAMES)
        for tool, (name, class_name, permission, parameters, required) in zip(tools, TOOL_TABLE):
            with self.subTest(tool=name):
                spec = tool.spec()
                self.assertIs(type(tool), getattr(builtin_codex, class_name))
                self.assertEqual(spec.permission.value, permission)
                self.assertEqual(set(spec.input_schema.get("properties", {})), set(parameters))
                self.assertEqual(set(spec.input_schema.get("required", ())), set(required))

    async def test_default_policy_allows_the_read_tools_and_denies_the_write_tools(self) -> None:
        host = StubCodexHost()
        tools = _toolset(host, max_live_turns=2)
        handle = await self.spawn_handle(tools)
        before = len(host.calls)
        executor = ToolExecutor(tools)
        for name, arguments in _valid_arguments(handle).items():
            with self.subTest(tool=name):
                result = await asyncio.wait_for(executor.execute_call(ToolCall(tool_name=name, arguments=arguments)), WAIT_SECONDS)
                if name in WRITE_TOOLS:
                    self.assertEqual(result.metadata, {"error": "permission_denied", "permission": "write"})
                else:
                    self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
        self.assertFalse(set(WRITE_TOOLS) & set(host.names()[before:]))


class CodexHostToolErrorTests(_ToolCase):
    """AC-24 and INV-10: host errors become error results; only cancellation propagates."""

    async def test_every_tool_turns_host_errors_into_error_results(self) -> None:
        errors = (
            ("codex.api_error", lambda name: CodexAgentError("Codex rejected the call.", failure_code="codex.api_error", operation=name, next_step=NEXT_STEPS["codex.api_error"]), "Codex rejected the call."),
            ("configuration.invalid_argument", lambda name: ConfigurationError("CodexHost is not open."), "CodexHost is not open."),
            ("configuration.invalid_argument", lambda name: ToolExecutionError("The tool pipeline failed."), "The tool pipeline failed."),
        )
        for name in TOOL_NAMES:
            for code, build, message in errors:
                with self.subTest(tool=name, error=message):
                    host = StubCodexHost()
                    tools = _toolset(host)
                    handle = await self.spawn_handle(tools)
                    host.raises[name] = build(name)
                    result = await _call(tools, name, _valid_arguments(handle)[name])
                    self.assert_error_result(result, code)
                    self.assertEqual(result.output, f"{code}: {message} Next step: {NEXT_STEPS[code]}")

    async def test_cancellation_propagates_and_frees_the_reserved_slot(self) -> None:
        host = StubCodexHost()
        tools = _toolset(host, max_live_turns=1)
        host.gates["spawn_codex_thread"] = asyncio.Event()
        task = asyncio.ensure_future(_call(tools, "spawn_codex_thread", {"prompt": "Fix the failing test."}))
        await _until(lambda: "spawn_codex_thread" in host.names(), "the spawn to reach the host")
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        del host.gates["spawn_codex_thread"]
        # The cancelled call held the only slot; it must be free again.
        await self.spawn_handle(tools)


class CodexHostToolScopeTests(_ToolCase):
    """AC-25, INV-32, INV-33 and D-12: the cap, slot reservation, and per-scope handle ownership."""

    async def test_cap_refuses_turn_starting_tools_without_reaching_the_host(self) -> None:
        host = StubCodexHost()
        tools = _toolset(host, max_live_turns=1)
        running = await self.spawn_handle(tools)
        refused = _valid_arguments(running)
        for name in TURN_STARTING_TOOLS:
            with self.subTest(tool=name):
                self.assert_error_result(await _call(tools, name, refused[name]), "codex.session_busy")
        self.assertEqual(host.names().count("spawn_codex_thread"), 1)
        self.assertFalse({"continue_codex_thread", "launch_codex_subagents", "start_codex_review"} & set(host.names()))
        # A finished turn frees its slot.
        _finish(host, running)
        await self.spawn_handle(tools)

    async def test_launch_counts_every_new_turn_against_the_cap(self) -> None:
        host = StubCodexHost()
        tools = _toolset(host, max_live_turns=2)
        await self.spawn_handle(tools)
        result = await _call(tools, "launch_codex_subagents", {"prompts": ["Review module A.", "Review module B."]})
        self.assert_error_result(result, "codex.session_busy")
        self.assertNotIn("launch_codex_subagents", host.names())
        self.assertEqual(len(json.loads((await _call(tools, "launch_codex_subagents", {"prompts": ["Review module A."]})).output)), 1)

    async def test_two_concurrent_spawns_never_exceed_the_cap(self) -> None:
        host = StubCodexHost()
        tools = _toolset(host, max_live_turns=1)
        gate = host.gates["spawn_codex_thread"] = asyncio.Event()
        first = asyncio.ensure_future(_call(tools, "spawn_codex_thread", {"prompt": "First task."}))
        await _until(lambda: "spawn_codex_thread" in host.names(), "the first spawn to reach the host")
        second = await _call(tools, "spawn_codex_thread", {"prompt": "Second task."})
        self.assert_error_result(second, "codex.session_busy")
        gate.set()
        self.assertEqual((await first).status, ToolStatus.SUCCESS)
        self.assertEqual(host.names().count("spawn_codex_thread"), 1)

    async def test_a_failed_start_releases_its_slot(self) -> None:
        host = StubCodexHost()
        tools = _toolset(host, max_live_turns=1)
        host.raises["spawn_codex_thread"] = CodexAgentError("Codex is overloaded.", failure_code="codex.api_error", operation="spawn_codex_thread", next_step=NEXT_STEPS["codex.api_error"])
        self.assert_error_result(await _call(tools, "spawn_codex_thread", {"prompt": "Fix it."}), "codex.api_error")
        del host.raises["spawn_codex_thread"]
        await self.spawn_handle(tools)

    async def test_handle_tools_accept_only_their_own_scope_while_thread_tools_accept_any_thread(self) -> None:
        host = StubCodexHost()
        mine, other = _toolset(host), _toolset(host)
        foreign = await self.spawn_handle(other)
        unknown = {"thread_id": "thr-never", "turn_id": "turn-never"}
        for handle in (foreign, unknown):
            arguments = _valid_arguments(handle)
            for name in HANDLE_TOOLS:
                with self.subTest(tool=name, handle=handle["thread_id"]):
                    self.assert_error_result(await _call(mine, name, arguments[name]), "codex.session_not_found")
        self.assertFalse({"wait_codex_turn", "steer_codex_turn", "interrupt_codex_turn"} & set(host.names()))
        # Tools 5, 6, 8, 13 and 15 take any thread id, including one another scope started.
        for name in ("continue_codex_thread", "fork_codex_thread", "read_codex_thread", "track_codex_thread_usage", "start_codex_review"):
            with self.subTest(tool=name):
                arguments = {**_valid_arguments(foreign)[name], "thread_id": foreign["thread_id"]}
                self.assertEqual((await _call(mine, name, arguments)).status, ToolStatus.SUCCESS)
        own = await self.spawn_handle(mine)
        self.assertEqual((await _call(mine, "get_codex_turn_result", own)).status, ToolStatus.SUCCESS)


class CodexHostToolArgumentTests(_ToolCase):
    """AC-26, INV-34, EC-53 to EC-55: the posture comes from spawn_defaults; arguments are checked by the tool."""

    async def test_spawn_takes_the_posture_from_defaults_and_six_values_from_the_model(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexGoal
        from vidbyte.lib.enums.codex import CodexReasoningEffort

        defaults = _defaults()
        host = StubCodexHost()
        tools = _toolset(host, spawn_defaults=defaults)
        schema = {"type": "object", "properties": {"title": {"type": "string"}}}
        model_values = {"prompt": "Fix the failing test.", "model": "gpt-5.5", "effort": "high", "name": "fix-test", "max_output_tokens": 100, "timeout_seconds": 30, "output_schema": schema, "goal_objective": None, "goal_token_budget": None}
        await _call(tools, "spawn_codex_thread", model_values)
        sent = host.last("spawn_codex_thread")[0][0]
        expected = dataclasses.replace(
            defaults,
            prompt="Fix the failing test.",
            thread=dataclasses.replace(defaults.thread, model="gpt-5.5"),
            turn=dataclasses.replace(defaults.turn, effort=CodexReasoningEffort.HIGH),
            name="fix-test",
            max_output_tokens=100,
            timeout_seconds=30.0,
            output_schema=schema,
        )
        self.assertEqual(sent, expected)

        # EC-53: JSON null means omitted, so every default stays.
        nulls = {key: None for key in model_values}
        await _call(tools, "spawn_codex_thread", {**nulls, "prompt": "Fix the failing test."})
        self.assertEqual(host.last("spawn_codex_thread")[0][0], dataclasses.replace(defaults, prompt="Fix the failing test."))

        await _call(tools, "spawn_codex_thread", {"goal_objective": "Ship the fix.", "goal_token_budget": 500, "prompt": None})
        goal_request = host.last("spawn_codex_thread")[0][0]
        self.assertEqual((goal_request.prompt, goal_request.goal), ("", CodexGoal(objective="Ship the fix.", token_budget=500)))

    async def test_spawn_needs_exactly_one_of_prompt_and_goal_objective(self) -> None:
        host = StubCodexHost()
        tools = _toolset(host)
        for arguments in ({}, {"prompt": None, "goal_objective": None}, {"prompt": "Fix it.", "goal_objective": "Ship it."}, {"prompt": "Fix it.", "goal_token_budget": 500}):
            with self.subTest(arguments=arguments):
                self.assert_error_result(await _call(tools, "spawn_codex_thread", arguments), "configuration.invalid_argument")
        self.assertNotIn("spawn_codex_thread", host.names())

    async def test_continue_fork_and_launch_carry_only_what_their_operation_applies(self) -> None:
        from vidbyte.lib.enums.codex import CodexApprovalsReviewer, CodexReasoningEffort, CodexSandbox, CodexThreadSource, CodexThreadStartSource

        defaults = _defaults(
            thread=dataclasses.replace(
                _defaults().thread,
                ephemeral=True,
                service_name="vidbyte-agents",
                thread_source=CodexThreadSource.SUBAGENT,
                session_start_source=CodexThreadStartSource.STARTUP,
            ),
            name="worker",
        )
        host = StubCodexHost()
        tools = _toolset(host, spawn_defaults=defaults)
        await _call(tools, "continue_codex_thread", {"thread_id": "thr-7", "prompt": "Carry on.", "model": "gpt-5.5", "effort": "high", "max_output_tokens": 100, "timeout_seconds": 30})
        args, kwargs = host.last("continue_codex_thread")
        overrides = kwargs["overrides"]
        self.assertEqual((args[0], args[1]), ("thr-7", "Carry on."))
        # Every continue-rejected field is cleared; the posture stays.
        self.assertEqual((overrides.prompt, overrides.goal, overrides.tools, overrides.name), ("", None, (), ""))
        self.assertFalse(overrides.thread.ephemeral)
        self.assertEqual(overrides.thread.service_name, "")
        self.assertEqual(overrides.thread.thread_source, CodexThreadSource.PROVIDER_DEFAULT)
        self.assertEqual(overrides.thread.session_start_source, CodexThreadStartSource.PROVIDER_DEFAULT)
        self.assertEqual((overrides.thread.sandbox, overrides.thread.cwd, overrides.thread.model), (CodexSandbox.READ_ONLY, WORKSPACE, "gpt-5.4-mini"))
        self.assertEqual((overrides.turn.model, overrides.turn.effort), ("gpt-5.5", CodexReasoningEffort.HIGH))
        self.assertEqual(overrides.approvals_reviewer, CodexApprovalsReviewer.AUTO_REVIEW)
        self.assertEqual((overrides.max_output_tokens, overrides.timeout_seconds), (100, 30.0))

        await _call(tools, "fork_codex_thread", {"thread_id": "thr-7", "from_turn_id": "turn-2", "exclude_turns": True})
        self.assertEqual(host.last("fork_codex_thread"), (("thr-7",), {"from_turn_id": "turn-2", "exclude_turns": True, "overrides": None}))

        await _call(tools, "launch_codex_subagents", {"prompts": ["Review module A.", "Review module B."]})
        args, kwargs = host.last("launch_codex_subagents")
        self.assertEqual(args[0], ("Review module A.", "Review module B."))
        self.assertEqual((kwargs["request"], kwargs["limit"]), (defaults, None))

    async def test_list_review_and_wait_tools_translate_their_arguments(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget
        from vidbyte.lib.enums.codex import CodexReviewDelivery, CodexReviewTargetKind, CodexSortDirection, CodexThreadSortKey, CodexThreadSourceKind

        host = StubCodexHost()
        tools = _toolset(host)
        await _call(tools, "list_codex_threads", {"cwd": WORKSPACE, "search": "readme", "archived": True, "source_kinds": ["appServer", "cli"], "sort": "updated_at", "sort_direction": "desc", "cursor": "c-1"})
        self.assertEqual(
            host.last("list_codex_threads")[1],
            {
                "cwd": WORKSPACE,
                "search": "readme",
                "archived": True,
                "source_kinds": (CodexThreadSourceKind.APP_SERVER, CodexThreadSourceKind.CLI),
                "sort": CodexThreadSortKey.UPDATED_AT,
                "sort_direction": CodexSortDirection.DESC,
                "cursor": "c-1",
            },
        )
        await _call(tools, "start_codex_review", {"thread_id": "thr-7", "target_kind": "commit", "sha": "abc1234", "title": "Fix the parser", "branch": None})
        args, kwargs = host.last("start_codex_review")
        self.assertEqual(args, ("thr-7", CodexReviewTarget(kind=CodexReviewTargetKind.COMMIT, sha="abc1234", title="Fix the parser")))
        self.assertEqual(kwargs["delivery"], CodexReviewDelivery.INLINE)
        await _call(tools, "start_codex_review", {"thread_id": "thr-7", "target_kind": "uncommittedChanges", "delivery": "detached"})
        self.assertEqual(host.last("start_codex_review")[1]["delivery"], CodexReviewDelivery.DETACHED)

        # D-31, EC-55: the wait tool defaults to 240 s and never waits longer.
        handle = await self.spawn_handle(tools)
        for given, expected in ((None, 240.0), (1000, 240.0), (240.5, 240.0), (5, 5.0)):
            with self.subTest(timeout_seconds=given):
                await _call(tools, "wait_codex_turn", {**handle, "timeout_seconds": given})
                self.assertEqual(host.last("wait_codex_turn")[1]["timeout_seconds"], expected)

    async def test_wrong_argument_types_are_refused_before_the_host(self) -> None:
        host = StubCodexHost()
        tools = _toolset(host)
        handle = await self.spawn_handle(tools)
        before = len(host.calls)
        rows = (
            ("spawn_codex_thread", {"prompt": "Fix it.", "max_output_tokens": "5"}),
            ("spawn_codex_thread", {"prompt": "Fix it.", "max_output_tokens": True}),
            ("spawn_codex_thread", {"prompt": "Fix it.", "max_output_tokens": 0}),
            ("spawn_codex_thread", {"prompt": "Fix it.", "max_output_tokens": 1.5}),
            ("spawn_codex_thread", {"prompt": "Fix it.", "timeout_seconds": 0}),
            ("spawn_codex_thread", {"prompt": "Fix it.", "timeout_seconds": -1}),
            ("spawn_codex_thread", {"prompt": "Fix it.", "timeout_seconds": math.nan}),
            ("spawn_codex_thread", {"prompt": "Fix it.", "timeout_seconds": "soon"}),
            ("spawn_codex_thread", {"prompt": "Fix it.", "timeout_seconds": True}),
            ("spawn_codex_thread", {"prompt": "Fix it.", "effort": "extreme"}),
            ("spawn_codex_thread", {"prompt": 7}),
            ("spawn_codex_thread", {"goal_objective": "Ship it.", "goal_token_budget": 0}),
            ("continue_codex_thread", {"prompt": "Carry on."}),
            ("continue_codex_thread", {"thread_id": 5, "prompt": "Carry on."}),
            ("list_codex_models", {"include_hidden": "yes"}),
            ("list_codex_threads", {"source_kinds": ["nowhere"]}),
            ("list_codex_threads", {"sort": "random"}),
            ("list_codex_threads", {"sort_direction": "up"}),
            ("wait_codex_turn", {**handle, "timeout_seconds": 0}),
            ("launch_codex_subagents", {"prompts": []}),
            ("launch_codex_subagents", {"prompts": "Review module A."}),
            ("launch_codex_subagents", {"prompts": ["Review module A.", 3]}),
            ("start_codex_review", {"thread_id": "thr-7", "target_kind": "everything"}),
            ("start_codex_review", {"thread_id": "thr-7", "target_kind": "commit", "sha": "abc", "delivery": "later"}),
        )
        for name, arguments in rows:
            with self.subTest(tool=name, arguments=arguments):
                self.assert_error_result(await _call(tools, name, arguments), "configuration.invalid_argument")
        # Only a local status read, which sends nothing to Codex, may have happened.
        self.assertLessEqual(set(host.names()[before:]), {"get_codex_turn_result"})


class CodexHostToolOutputTests(_ToolCase):
    """INV-35: record JSON with enum values and nested objects; wait and get leave out result.items."""

    async def test_outputs_are_the_returned_records_as_json(self) -> None:
        host = StubCodexHost()
        tools = _toolset(host)
        readiness = json.loads((await _call(tools, "check_codex_ready")).output)
        self.assertEqual(readiness, {"ready": True, "version": "0.162.1", "minimum_version": "0.151.0", "signed_in": True, "account": "chatgpt", "plan_type": "plus", "sandbox": "ready", "problems": []})
        limits = json.loads((await _call(tools, "get_codex_rate_limits")).output)
        self.assertEqual(limits, {"ordinary_usage_allowed": True, "plan_type": "plus", "limit_reached": "", "primary": {"used_percent": 12, "resets_at": 1_760_000_000, "window_minutes": 300}, "secondary": None})
        models = json.loads((await _call(tools, "list_codex_models")).output)
        self.assertEqual([(model["model_id"], model["efforts"]) for model in models], [("gpt-5.5", ["low", "medium"])])

        handle = await self.spawn_handle(tools)
        running = json.loads((await _call(tools, "get_codex_turn_result", handle)).output)
        self.assertEqual(running, {"handle": handle, "status": "inProgress", "result": None, "problem": None, "goal_status": ""})
        _finish(host, handle)
        done = json.loads((await _call(tools, "wait_codex_turn", handle)).output)
        self.assertEqual((done["status"], done["result"]["final_response"], done["result"]["usage"]["total_tokens"]), ("completed", "Stub final answer.", 15))
        self.assertNotIn("items", done["result"])
        interrupted = await _call(tools, "interrupt_codex_turn", handle)
        self.assertEqual(interrupted.output, f"Interrupt requested for turn {handle['turn_id']}; call wait_codex_turn to collect its result.")

        usage = json.loads((await _call(tools, "track_codex_thread_usage", {"thread_id": "thr-7"})).output)
        self.assertEqual((usage["cost_usd"], usage["cost_complete"], usage["turns"][0]["status"], usage["total"]["output_tokens"]), (0.001, True, "completed", 5))
        page = json.loads((await _call(tools, "list_codex_threads")).output)
        self.assertEqual((page["next_cursor"], page["threads"][0]["status"], page["threads"][0]["turns"]), ("stub-cursor", "idle", []))
        launched = json.loads((await _call(tools, "launch_codex_subagents", {"prompts": ["Review module A.", "Review module B."]})).output)
        self.assertEqual([sorted(item) for item in launched], [["thread_id", "turn_id"], ["thread_id", "turn_id"]])


class CodexHostToolsetConstructionTests(unittest.TestCase):
    """EC-57 and D-11: the cap is required and validated; spawn_defaults cannot carry a prompt or a goal."""

    def test_bad_caps_and_defaults_are_refused_at_construction(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexGoal, CodexSpawnRequest
        from vidbyte.tools.builtins.codex import CodexToolScope

        for cap in (0, -1, True, 1.5, "2", None):
            with self.subTest(max_live_turns=cap):
                with self.assertRaises(ConfigurationError):
                    _toolset(StubCodexHost(), max_live_turns=cap)
                with self.assertRaises(ConfigurationError):
                    CodexToolScope(max_live_turns=cap)
        for defaults in (CodexSpawnRequest(prompt="Fix it."), CodexSpawnRequest(goal=CodexGoal(objective="Ship it.")), "read-only"):
            with self.subTest(spawn_defaults=defaults):
                with self.assertRaises(ConfigurationError):
                    _toolset(StubCodexHost(), max_live_turns=1, spawn_defaults=defaults)


class CodexHostToolsMcpTests(unittest.IsolatedAsyncioTestCase):
    """AC-27 and EC-64: McpStudioServer serves the toolset unchanged; the cap still applies there."""

    async def test_mcp_server_lists_and_runs_the_toolset(self) -> None:
        from vidbyte.mcp_server import McpStudioServer

        host = StubCodexHost()
        server = McpStudioServer(tools=_toolset(host, max_live_turns=1))
        listed = await server._dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertTrue(set(TOOL_NAMES) <= {tool["name"] for tool in listed["result"]["tools"]})

        called = await server._dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "check_codex_ready", "arguments": {}}})
        self.assertTrue(json.loads(called["result"]["content"][0]["text"])["ready"])
        self.assertEqual(host.names(), ["check_codex_ready"])

        spawn = {"name": "spawn_codex_thread", "arguments": {"prompt": "Fix the failing test."}}
        first = await server._dispatch({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": spawn})
        self.assertNotIn("isError", first["result"])
        second = await server._dispatch({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": spawn})
        self.assertTrue(second["result"]["isError"])
        self.assertTrue(second["result"]["content"][0]["text"].startswith("codex.session_busy: "))
        self.assertEqual(host.names().count("spawn_codex_thread"), 1)


if __name__ == "__main__":
    unittest.main()

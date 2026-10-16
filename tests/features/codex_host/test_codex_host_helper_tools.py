"""FILE: tests/features/codex_host/test_codex_host_helper_tools.py

PURPOSE: Proves the eleven thread-helper tools and their place in CodexHostTools: twenty-six tools in section 9.2 order with no tool for delete_codex_thread, each new schema in section 9.2 parameter order, the arguments each tool passes to the host (the default listing limit, the list_codex_turns default page of three, the since timestamp, the scope's spawn_defaults for the run tools), argument checks before the host, the live-turn cap and handle ownership for the three run tools, error results with the new codes' next steps, and the JSON or text each tool returns.
ROLE IN CODEBASE: Tool layer of the thread-helpers additions to tests/features/codex_host/ (docs/spec/codex-host-thread-helpers/spec.md AC-21, AC-33, AC-41, INV-2, INV-27, INV-28, EC-38, EC-39, EC-47). It runs the tools over StubCodexHost, as spec section 13 allows, so CI runs it without openai-codex.
ARCHITECTURE NOTE: Tools are executed directly, the way McpStudioServer runs them. StubCodexHost records every new method's arguments by name, however the tool passed them, so a test compares one normalized mapping with what the spec says the tool sends; a handle stays RUNNING until the test finishes it, which is how the cap sees a live run.
COMMON MODIFICATION PATTERNS: When section 9.2 adds a tool, add its row to TOOL_TABLE in codex_host_support.py, its argument set to VALID_ARGUMENTS here and to _valid_arguments in test_codex_host_tools.py, and a StubCodexHost method.
KNOWN EDGE CASES: The limit upper bound (1000) is the host's check, not the tool's, so it is proven over the fake app-server in test_codex_host_thread_helpers.py; here a stub host would accept it. JSON null must behave exactly like an omitted argument.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-thread-helpers/spec.md sections 6.1 (INV-2, INV-27, INV-28) and 9.2 (tool table).
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_helper_tools.py
"""

from __future__ import annotations

import asyncio
import json
import os
import unittest
from typing import Any

from tests.features.codex_host.codex_host_support import (
    COMPACT_STARTED_TEXT,
    NEXT_STEPS,
    NO_GOAL_TEXT,
    TOOL_NAMES,
    TOOL_TABLE,
    WAIT_SECONDS,
    StubCodexHost,
)
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult, ToolStatus
from vidbyte.lib.errors import CodexAgentError

WORKSPACE = os.path.abspath(os.path.join(os.sep, "agent-workspace"))
NEW_ROWS = TOOL_TABLE[15:]
NEW_TOOLS = tuple(row[0] for row in NEW_ROWS)
RUN_TOOLS = ("run_codex_goal", "run_codex_skill", "run_codex_openai_docs")
# Spec section 9.2 tool table: the JSON type of each new parameter.
INTEGER_PARAMETERS = frozenset({"limit", "since", "token_budget"})
# Spec section 9.3: CODEX_HOST_THREAD_LIST_DEFAULT_LIMIT and CODEX_HOST_TURNS_TOOL_DEFAULT_LIMIT.
DEFAULT_LIMIT = 20
TURNS_TOOL_DEFAULT_LIMIT = 3

# One argument set each new tool accepts.
VALID_ARGUMENTS: dict[str, dict[str, Any]] = {
    "list_recent_codex_threads": {},
    "list_codex_threads_since": {"since": 1_760_000_000},
    "search_codex_threads": {"query": "readme"},
    "get_codex_thread_lineage": {"thread_id": "thr-7"},
    "list_codex_turns": {"thread_id": "thr-7"},
    "compact_codex_thread": {"thread_id": "thr-7"},
    "get_codex_goal": {"thread_id": "thr-7"},
    "run_codex_goal": {"objective": "Ship the fix."},
    "list_codex_skills": {},
    "run_codex_skill": {"skill": "openai-docs", "prompt": "Find the event that streams text."},
    "run_codex_openai_docs": {"question": "Which event streams text deltas?"},
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
    from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle

    host.finish(CodexTurnHandle(**handle))


async def _until(condition: Any, what: str) -> None:
    """Yield to the loop until the condition holds; a bounded count keeps a broken tool from hanging the test."""
    for _ in range(10_000):
        if condition():
            return
        await asyncio.sleep(0)
    raise AssertionError(f"timed out waiting for {what}")


def _defaults() -> Any:
    """A developer posture the run tools must pass on unchanged."""
    from vidbyte.lib.dataclasses.codex import CodexThreadSettings
    from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
    from vidbyte.lib.enums.codex import CodexApprovalPolicy, CodexApprovalsReviewer, CodexSandbox

    return CodexSpawnRequest(
        thread=CodexThreadSettings(sandbox=CodexSandbox.READ_ONLY, cwd=WORKSPACE),
        approval_policy=CodexApprovalPolicy.ON_REQUEST,
        approvals_reviewer=CodexApprovalsReviewer.AUTO_REVIEW,
        developer_instructions="Never push to the main branch.",
        max_output_tokens=4000,
    )


class _ToolCase(unittest.IsolatedAsyncioTestCase):
    def assert_error_result(self, result: ToolResult, code: str) -> None:
        """codex-host INV-10: "<code>: <message> Next step: <next_step>" plus the two metadata keys."""
        self.assertEqual(result.status, ToolStatus.ERROR, result.output)
        self.assertEqual(result.metadata, {"code": code, "next_step": NEXT_STEPS[code]}, result.output)
        self.assertTrue(result.output.startswith(f"{code}: "), result.output)
        self.assertTrue(result.output.endswith(f" Next step: {NEXT_STEPS[code]}"), result.output)

    def assert_success(self, result: ToolResult) -> Any:
        self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
        return result


class CodexHelperToolShapeTests(_ToolCase):
    """AC-33, INV-2 and EC-39: twenty-six tools, the new schemas, and no way to delete a thread."""

    def test_the_toolset_appends_eleven_tools_and_none_is_delete(self) -> None:
        import vidbyte.tools.builtins as builtins
        import vidbyte.tools.builtins.codex as builtin_codex

        tools = _toolset(StubCodexHost(), max_live_turns=1)
        self.assertEqual(tuple(tools.names()), TOOL_NAMES)
        self.assertEqual(len(tools), 26)
        self.assertNotIn("delete_codex_thread", tools.names())
        for tool, (name, class_name, permission, parameters, required) in zip(list(tools)[15:], NEW_ROWS):
            with self.subTest(tool=name):
                spec = tool.spec()
                self.assertEqual(spec.name, name)
                self.assertIs(type(tool), getattr(builtin_codex, class_name))
                self.assertIs(getattr(builtins, class_name), getattr(builtin_codex, class_name))
                self.assertEqual(spec.permission.value, permission)
                schema = spec.input_schema
                self.assertEqual((schema.get("type"), schema.get("additionalProperties")), ("object", False))
                # Section 9.2: parameters are listed in schema order.
                self.assertEqual(tuple(schema.get("properties", {})), parameters)
                self.assertEqual(set(schema.get("required", ())), set(required))
                for parameter, body in schema.get("properties", {}).items():
                    self.assertEqual(body.get("type"), "integer" if parameter in INTEGER_PARAMETERS else "string", parameter)
                self.assertTrue(spec.description.strip())

    async def test_no_tool_reaches_delete_codex_thread(self) -> None:
        # AC-21, T-2: every new tool runs once, and the host's delete is never called.
        host = StubCodexHost()
        tools = _toolset(host, max_live_turns=5)
        for name in NEW_TOOLS:
            with self.subTest(tool=name):
                self.assert_success(await _call(tools, name, VALID_ARGUMENTS[name]))
        self.assertEqual([name for name in host.names() if name in NEW_TOOLS], list(NEW_TOOLS))
        self.assertNotIn("delete_codex_thread", host.names())


class CodexHelperToolArgumentTests(_ToolCase):
    """INV-27, INV-28, AC-41 and section 9.2 "Calls": what each tool passes to the host."""

    async def test_listing_tools_pass_their_arguments_and_the_default_limit(self) -> None:
        host = StubCodexHost()
        tools = _toolset(host)
        rows = (
            ("list_recent_codex_threads", {}, {"cwd": "", "limit": DEFAULT_LIMIT}),
            ("list_recent_codex_threads", {"cwd": None, "limit": None}, {"cwd": "", "limit": DEFAULT_LIMIT}),
            ("list_recent_codex_threads", {"cwd": WORKSPACE, "limit": 5}, {"cwd": WORKSPACE, "limit": 5}),
            ("list_codex_threads_since", {"since": 0}, {"cwd": "", "since": 0, "limit": DEFAULT_LIMIT}),
            ("list_codex_threads_since", {"since": 1_760_000_000, "cwd": WORKSPACE, "limit": 3}, {"cwd": WORKSPACE, "since": 1_760_000_000, "limit": 3}),
            ("search_codex_threads", {"query": "fix"}, {"cwd": "", "query": "fix", "limit": DEFAULT_LIMIT}),
            ("search_codex_threads", {"query": "fix", "cwd": WORKSPACE, "limit": 1}, {"cwd": WORKSPACE, "query": "fix", "limit": 1}),
            ("get_codex_thread_lineage", {"thread_id": "thr-7"}, {"thread_id": "thr-7"}),
            ("compact_codex_thread", {"thread_id": "thr-7"}, {"thread_id": "thr-7"}),
            ("get_codex_goal", {"thread_id": "thr-7"}, {"thread_id": "thr-7"}),
            ("list_codex_skills", {}, {"cwd": ""}),
            ("list_codex_skills", {"cwd": WORKSPACE}, {"cwd": WORKSPACE}),
        )
        for name, arguments, expected in rows:
            with self.subTest(tool=name, arguments=arguments):
                self.assert_success(await _call(tools, name, arguments))
                self.assertEqual(host.last(name), ((), expected))

    async def test_the_turns_tool_asks_for_a_small_page_unless_given_a_limit(self) -> None:
        # AC-41, D-25, EC-47: the tool sends CODEX_HOST_TURNS_TOOL_DEFAULT_LIMIT when the model leaves limit out.
        host = StubCodexHost()
        tools = _toolset(host, max_live_turns=1)
        rows = (
            ({"thread_id": "thr-7"}, {"thread_id": "thr-7", "cursor": "", "limit": TURNS_TOOL_DEFAULT_LIMIT}),
            ({"thread_id": "thr-7", "limit": None, "cursor": None}, {"thread_id": "thr-7", "cursor": "", "limit": TURNS_TOOL_DEFAULT_LIMIT}),
            ({"thread_id": "thr-7", "limit": 7}, {"thread_id": "thr-7", "cursor": "", "limit": 7}),
            ({"thread_id": "thr-7", "cursor": "turns-after-3"}, {"thread_id": "thr-7", "cursor": "turns-after-3", "limit": TURNS_TOOL_DEFAULT_LIMIT}),
        )
        for arguments, expected in rows:
            with self.subTest(arguments=arguments):
                self.assert_success(await _call(tools, "list_codex_turns", arguments))
                self.assertEqual(host.last("list_codex_turns"), ((), expected))

    async def test_run_tools_pass_the_scope_posture_and_their_own_input(self) -> None:
        # INV-27: the run tools send request=scope.spawn_defaults and set nothing else.
        defaults = _defaults()
        host = StubCodexHost()
        tools = _toolset(host, max_live_turns=5, spawn_defaults=defaults)
        rows = (
            ("run_codex_goal", {"objective": "Ship the fix.", "token_budget": 500}, {"objective": "Ship the fix.", "token_budget": 500, "request": defaults}),
            ("run_codex_goal", {"objective": "Ship the fix.", "token_budget": None}, {"objective": "Ship the fix.", "token_budget": None, "request": defaults}),
            ("run_codex_skill", {"skill": "openai-docs", "prompt": "Find it."}, {"skill": "openai-docs", "prompt": "Find it.", "request": defaults}),
            ("run_codex_openai_docs", {"question": "Which event?"}, {"question": "Which event?", "request": defaults}),
        )
        for name, arguments, expected in rows:
            with self.subTest(tool=name, arguments=arguments):
                handle = _handle_of(self.assert_success(await _call(tools, name, arguments)))
                self.assertEqual(host.last(name), ((), expected))
                self.assertEqual(sorted(handle), ["thread_id", "turn_id"])

    async def test_bad_arguments_are_refused_before_the_host(self) -> None:
        host = StubCodexHost()
        tools = _toolset(host)
        rows = (
            ("list_recent_codex_threads", {"limit": 0}),
            ("list_recent_codex_threads", {"limit": True}),
            ("list_recent_codex_threads", {"limit": 2.5}),
            ("list_recent_codex_threads", {"limit": "5"}),
            ("list_recent_codex_threads", {"cwd": 5}),
            # Section 9.2: since is a required whole number of Unix seconds of at least 0, bool refused.
            ("list_codex_threads_since", {}),
            ("list_codex_threads_since", {"since": None}),
            ("list_codex_threads_since", {"since": -1}),
            ("list_codex_threads_since", {"since": True}),
            ("list_codex_threads_since", {"since": 1.5}),
            ("list_codex_threads_since", {"since": "1760000000"}),
            ("search_codex_threads", {}),
            ("search_codex_threads", {"query": 5}),
            ("get_codex_thread_lineage", {}),
            ("list_codex_turns", {}),
            ("list_codex_turns", {"thread_id": "thr-7", "limit": 0}),
            ("list_codex_turns", {"thread_id": "thr-7", "cursor": 5}),
            ("compact_codex_thread", {}),
            ("get_codex_goal", {"thread_id": 7}),
            ("run_codex_goal", {}),
            ("run_codex_goal", {"objective": "Ship it.", "token_budget": 0}),
            ("run_codex_goal", {"objective": "Ship it.", "token_budget": True}),
            ("list_codex_skills", {"cwd": 5}),
            ("run_codex_skill", {"skill": "openai-docs"}),
            ("run_codex_skill", {"prompt": "Find it."}),
            ("run_codex_skill", {"skill": 5, "prompt": "Find it."}),
            ("run_codex_openai_docs", {}),
            ("run_codex_openai_docs", {"question": 5}),
        )
        for name, arguments in rows:
            with self.subTest(tool=name, arguments=arguments):
                self.assert_error_result(await _call(tools, name, arguments), "configuration.invalid_argument")
        self.assertEqual(host.names(), [])


class CodexHelperToolScopeTests(_ToolCase):
    """INV-27, AC-33 and EC-38: the run tools hold one cap slot and own the handle they return."""

    async def test_a_full_cap_refuses_every_run_tool_without_reaching_the_host(self) -> None:
        host = StubCodexHost()
        tools = _toolset(host, max_live_turns=1)
        running = _handle_of(self.assert_success(await _call(tools, "run_codex_goal", {"objective": "Ship the fix."})))
        for name in (*RUN_TOOLS, "spawn_codex_thread"):
            arguments = VALID_ARGUMENTS.get(name, {"prompt": "Fix the failing test."})
            with self.subTest(tool=name):
                self.assert_error_result(await _call(tools, name, arguments), "codex.session_busy")
        self.assertEqual([name for name in host.names() if name in (*RUN_TOOLS, "spawn_codex_thread")], ["run_codex_goal"])
        # The run's handle belongs to this scope, and finishing it frees the slot.
        self.assert_success(await _call(tools, "get_codex_turn_result", running))
        self.assert_error_result(await _call(_toolset(host), "get_codex_turn_result", running), "codex.session_not_found")
        _finish(host, running)
        for name in ("run_codex_skill", "run_codex_openai_docs"):
            with self.subTest(after_finish=name):
                handle = _handle_of(self.assert_success(await _call(tools, name, VALID_ARGUMENTS[name])))
                self.assert_success(await _call(tools, "wait_codex_turn", handle))
                _finish(host, handle)

    async def test_a_failed_or_cancelled_run_releases_its_slot(self) -> None:
        host = StubCodexHost()
        tools = _toolset(host, max_live_turns=1)
        host.raises["run_codex_skill"] = CodexAgentError(
            "Codex lists no skill named 'zz' for the app-server's working folder. Enabled skills: none.",
            failure_code="codex.skill_not_found",
            operation="run_codex_skill",
            next_step=NEXT_STEPS["codex.skill_not_found"],
        )
        self.assert_error_result(await _call(tools, "run_codex_skill", {"skill": "zz", "prompt": "Find it."}), "codex.skill_not_found")
        del host.raises["run_codex_skill"]

        host.gates["run_codex_openai_docs"] = asyncio.Event()
        task = asyncio.ensure_future(_call(tools, "run_codex_openai_docs", {"question": "Which event?"}))
        await _until(lambda: "run_codex_openai_docs" in host.names(), "the docs run to reach the host")
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        del host.gates["run_codex_openai_docs"]
        # Both calls held the only slot; it must be free again.
        self.assert_success(await _call(tools, "run_codex_goal", {"objective": "Ship the fix."}))

    async def test_new_codes_become_error_results_with_their_next_steps(self) -> None:
        # FR-15: the four new codes reach the model as "<code>: <message> Next step: <next_step>".
        rows = (
            ("run_codex_goal", "codex.command_not_run"),
            ("run_codex_skill", "codex.skill_disabled"),
            ("compact_codex_thread", "codex.goal_unfinished"),
        )
        for name, code in rows:
            with self.subTest(tool=name, code=code):
                host = StubCodexHost()
                tools = _toolset(host)
                host.raises[name] = CodexAgentError("Codex refused the call. Thread: thr-7.", failure_code=code, operation=name, next_step=NEXT_STEPS[code])
                result = await _call(tools, name, VALID_ARGUMENTS[name])
                self.assertEqual(result.output, f"{code}: Codex refused the call. Thread: thr-7. Next step: {NEXT_STEPS[code]}")
                self.assert_error_result(result, code)


class CodexHelperToolOutputTests(_ToolCase):
    """INV-28: record JSON with enum values and nested records as objects; compact and a missing goal as text."""

    async def test_outputs_are_the_returned_records_as_json_or_the_spec_texts(self) -> None:
        host = StubCodexHost()
        tools = _toolset(host)
        summary = {"harness": "codex", "thread_id": "thr-stub-recent", "title": "Stub thread", "created_at": 1, "updated_at": 2, "parent_thread_id": None, "model": "gpt-5.5"}
        self.assertEqual(json.loads((await _call(tools, "list_recent_codex_threads")).output), [summary])
        lineage = json.loads((await _call(tools, "get_codex_thread_lineage", {"thread_id": "thr-7"})).output)
        self.assertEqual([(entry["thread_id"], entry["parent_thread_id"]) for entry in lineage], [("thr-7", "thr-stub-parent"), ("thr-stub-parent", None)])

        page = json.loads((await _call(tools, "list_codex_turns", {"thread_id": "thr-7"})).output)
        self.assertEqual(page["next_cursor"], "stub-turn-cursor")
        turn = page["turns"][0]
        self.assertEqual((turn["turn_id"], turn["status"], turn["final_response"], turn["error_message"], turn["started_at"], turn["completed_at"]), ("turn-stub-1", "completed", "Stub final answer.", "", 1, 2))
        self.assertEqual([(item["id"], item["type"]) for item in turn["items"]], [("item-stub-user", "userMessage"), ("item-stub-final", "agentMessage")])
        self.assertEqual(turn["items"][1]["fields"], {"text": "Stub final answer.", "phase": "final_answer"})

        compacted = self.assert_success(await _call(tools, "compact_codex_thread", {"thread_id": "thr-7"}))
        self.assertEqual(compacted.output, COMPACT_STARTED_TEXT.format(thread_id="thr-7"))
        goal = json.loads((await _call(tools, "get_codex_goal", {"thread_id": "thr-7"})).output)
        expected_goal = {"thread_id": "thr-7", "objective": "Ship the fix.", "status": "active", "token_budget": 500, "tokens_used": 120, "time_used_seconds": 30, "created_at": 1, "updated_at": 2}
        self.assertEqual(goal, expected_goal)
        host.goal_missing = True
        missing = self.assert_success(await _call(tools, "get_codex_goal", {"thread_id": "thr-7"}))
        self.assertEqual(missing.output, NO_GOAL_TEXT.format(thread_id="thr-7"))

        skills = json.loads((await _call(tools, "list_codex_skills")).output)
        path = os.path.abspath(os.path.join(os.sep, "stub-skills", "openai-docs", "SKILL.md"))
        self.assertEqual(skills, [{"name": "openai-docs", "description": "Stub skill.", "path": path, "scope": "system", "enabled": True}])


if __name__ == "__main__":
    unittest.main()

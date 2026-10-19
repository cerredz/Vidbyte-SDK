"""FILE: tests/features/codex_host/test_codex_host_feature_tools.py

PURPOSE: Proves the sixteen first-class agent tools beyond their table shape: no tool for the nine INV-42 functions, no posture parameter in any new schema, a paid-work sentence in every new WRITE description, the arguments each tool passes to its host method, the side-chat tool's narrowed read-only, never-ask posture on a stub host and on the wire, with the fields a side chat refuses reset first, the plan, side-chat and resume tools' cap slots and owned handles, handle ownership for the wait and turn-settings tools, the turn-settings status text, the multi-wait JSON without items, and host refusals (a mode in the defaults, the experimental gate) returned as error results.
ROLE IN CODEBASE: Tool layer of the slice-2 tests in tests/features/codex_host/ (docs/spec/codex-host-first-class/spec.md AC-35 to AC-37, INV-41 to INV-44, D-21, D-22, EC-52 to EC-54, EC-59, T-2). The stub-host classes run on CI without openai-codex; the real-host class needs the optional extra, so CI skips it.
ARCHITECTURE NOTE: Tools are executed directly, the way McpStudioServer runs them. StubCodexHost records each host method's arguments by keyword (FeatureStubMethods in codex_host_feature_support.py), and a handle stays RUNNING until the test finishes it, which is how the cap sees a live run. The pinned tests in test_codex_host_tools.py, test_codex_host_helper_tools.py and test_codex_host_tool_hardening.py already check the 42-tool table, FORBIDDEN_PARAMETERS and the error results for every tool; this module does not repeat them.
COMMON MODIFICATION PATTERNS: A new tool adds one row to the arguments table here, besides its rows in TOOL_TABLE, _valid_arguments and NO_HANDLE_ARGUMENTS. A field that the side-chat tool narrows adds one replace() term to _side_chat_view.
KNOWN EDGE CASES: The stub's own parameter defaults are None, not the host's, so an argument a tool may leave to the host's default (detail, summary, approvals_reviewer) is checked as either None or the host's default. require_owned refuses with the existing NOT_OWNED text, which does not repeat the handle (reported in test-plan.md against EC-52's wording).
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-first-class/spec.md sections 6.1 (INV-41 to INV-44) and 9.2 (the sixteen tools); tests/features/codex_host/test_codex_host_helper_tools.py.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_feature_tools.py
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import re
import unittest
from typing import Any

from tests.features.codex_host.codex_host_feature_support import FEATURE_METHODS, NO_TOOL_FUNCTIONS, OLDER_NO_TOOL_FUNCTIONS, SIDE_CHAT_REJECTED_FIELDS, TURN_SETTINGS_STATUS_TEXT
from tests.features.codex_host.codex_host_support import NEXT_STEPS, TOOL_TABLE, WAIT_SECONDS, FeatureHostCase, StubCodexHost, make_echo_tool, requires_sdk
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult, ToolStatus

WORKSPACE = os.path.abspath(os.path.join(os.sep, "agent-workspace"))
EXTRA_ROOT = os.path.abspath(os.path.join(os.sep, "agent-workspace", "generated"))
NEW_ROWS = TOOL_TABLE[26:]
NEW_TOOLS = tuple(row[0] for row in NEW_ROWS)
CAP_TOOLS = ("run_codex_plan", "start_codex_side_chat", "resume_codex_goal")
# Section 9.2 tool rules: no schema offers a collaboration mode, a memory mode, a folder, plugins, a tier, a sandbox or approvals.
POSTURE_PARAMETERS = frozenset({"collaboration_mode", "mode", "memory_mode", "cwd", "disabled_plugin_ids", "service_tier", "turn_service_tier", "sandbox", "approval_policy", "approvals_reviewer", "approval_mode", "network_access", "writable_roots"})
NOT_OWNED_TEXT = "This toolset did not start the turn with that handle, so it cannot wait on, read, steer or interrupt it."
MAX_WAIT_SECONDS = 240.0
CONTINUE_REFUSED = ("prompt", "goal", "thread.ephemeral", "thread.thread_source", "thread.service_name", "thread.session_start_source", "tools", "name")
GOAL_REFUSED = ("turn", "output_schema", "disabled_plugin_ids", "turn_service_tier", "network_access", "writable_roots", "collaboration_mode")
EXPERIMENTAL_HEAD = "configuration.invalid_argument: list_codex_collaboration_modes needs Codex's experimental API for "


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


def _writable_defaults(*, cwd: str = WORKSPACE) -> Any:
    """A developer posture that writes, reaches the network and asks a reviewer: the side-chat tool must narrow all of it."""
    from vidbyte.lib.dataclasses.codex import CodexThreadSettings, CodexTurnSettings
    from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
    from vidbyte.lib.enums.codex import CodexApprovalPolicy, CodexApprovalsReviewer, CodexSandbox

    return CodexSpawnRequest(
        thread=CodexThreadSettings(sandbox=CodexSandbox.WORKSPACE_WRITE, cwd=cwd),
        turn=CodexTurnSettings(sandbox=CodexSandbox.WORKSPACE_WRITE),
        writable_roots=(EXTRA_ROOT,),
        network_access=True,
        approval_policy=CodexApprovalPolicy.ON_REQUEST,
        approvals_reviewer=CodexApprovalsReviewer.AUTO_REVIEW,
        developer_instructions="Never push to the main branch.",
        max_output_tokens=4000,
    )


def _refused_field_defaults(*, cwd: str = WORKSPACE) -> Any:
    """AC-36 extended (spec r6): the writable posture plus one Vidbyte tool, a name and a personality, which a side chat refuses."""
    from vidbyte.lib.enums.codex import CodexPersonality

    defaults = _writable_defaults(cwd=cwd)
    return dataclasses.replace(defaults, tools=(make_echo_tool(),), name="Fixer", thread=dataclasses.replace(defaults.thread, personality=CodexPersonality.NONE))


def _side_chat_view(defaults: Any) -> Any:
    """INV-43 (spec r6): every path of the side chat's rejected-fields row back at a fresh request's value, then the
    sandboxes, roots, network and approvals narrowed; every other field of spawn_defaults is kept."""
    from vidbyte.lib.enums.codex import CodexApprovalMode, CodexApprovalPolicy, CodexApprovalsReviewer, CodexSandbox

    reset = _reset(defaults, SIDE_CHAT_REJECTED_FIELDS)
    return dataclasses.replace(
        reset,
        thread=dataclasses.replace(reset.thread, sandbox=CodexSandbox.READ_ONLY, approval_mode=CodexApprovalMode.DENY_ALL),
        turn=dataclasses.replace(reset.turn, sandbox=CodexSandbox.READ_ONLY, approval_mode=CodexApprovalMode.DENY_ALL),
        writable_roots=(),
        network_access=None,
        approval_policy=CodexApprovalPolicy.PROVIDER_DEFAULT,
        approvals_reviewer=CodexApprovalsReviewer.PROVIDER_DEFAULT,
    )


def _reset(request: Any, paths: tuple[str, ...]) -> Any:
    """The request with each named field, or thread.<field>, back at its default (the resume tool's view)."""
    from vidbyte.lib.dataclasses.codex import CodexThreadSettings
    from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

    fresh, fresh_thread = CodexSpawnRequest(), CodexThreadSettings()
    thread_fields = {path.split(".", 1)[1]: getattr(fresh_thread, path.split(".", 1)[1]) for path in paths if path.startswith("thread.")}
    top_fields = {path: getattr(fresh, path) for path in paths if "." not in path}
    return dataclasses.replace(request, thread=dataclasses.replace(request.thread, **thread_fields), **top_fields)


class _ToolCase(unittest.IsolatedAsyncioTestCase):
    def assert_error_result(self, result: ToolResult, code: str) -> None:
        self.assertEqual(result.status, ToolStatus.ERROR, result.output)
        self.assertEqual(result.metadata, {"code": code, "next_step": NEXT_STEPS[code]}, result.output)
        self.assertTrue(result.output.startswith(f"{code}: "), result.output)

    def assert_success(self, result: ToolResult) -> ToolResult:
        self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
        return result

    async def owned_handle(self, tools: Any, host: StubCodexHost) -> dict[str, str]:
        """A running handle this scope owns, from the plan tool."""
        return _handle_of(self.assert_success(await _call(tools, "run_codex_plan", {"prompt": "Plan a fix."})))


class CodexFeatureToolCatalogTests(_ToolCase):
    """AC-35, INV-41, INV-42 and D-21: what the sixteen tools are, and what no tool may reach."""

    def test_the_sixteen_tools_follow_the_old_ones_in_function_order_and_none_is_a_no_tool_function(self) -> None:
        tools = _toolset(StubCodexHost())
        names = tuple(tools.names())
        self.assertEqual(names[26:], tuple(name for name in FEATURE_METHODS if name not in NO_TOOL_FUNCTIONS))
        self.assertEqual(names[26:], NEW_TOOLS)
        self.assertEqual(set(names) & {*NO_TOOL_FUNCTIONS, *OLDER_NO_TOOL_FUNCTIONS}, set())

    def test_no_new_schema_offers_a_posture_parameter(self) -> None:
        # Section 9.2: the model can never widen the sandbox, approvals, tier, folder, plugins, mode or memory mode.
        tools = _toolset(StubCodexHost())
        for name in NEW_TOOLS:
            with self.subTest(tool=name):
                schema = _tool(tools, name).spec().input_schema
                self.assertEqual(set(schema.get("properties", {})) & POSTURE_PARAMETERS, set())
                for body in schema.get("properties", {}).values():
                    self.assertEqual(set(body.get("properties", {})) & POSTURE_PARAMETERS, set())

    def test_every_new_description_has_four_or_five_sentences_and_each_write_one_names_paid_codex_work(self) -> None:
        # INV-41, section 9.2: "every WRITE description says it starts or changes paid Codex work".
        tools = _toolset(StubCodexHost())
        for name, _class_name, permission, _parameters, _required in NEW_ROWS:
            with self.subTest(tool=name):
                description = _tool(tools, name).spec().description
                sentences = re.findall(r"[.!?](?=\s|$)", description.strip())
                self.assertIn(len(sentences), (4, 5), description)
                if permission == "write":
                    self.assertIn("paid Codex", description)

    def test_the_side_chat_description_says_its_commands_are_read_only_and_the_parents_vidbyte_tools_stay_callable(self) -> None:
        # D-22, AC-36: the posture covers Codex's own commands only.
        description = _tool(_toolset(StubCodexHost()), "start_codex_side_chat").spec().description.casefold()
        for words in ("read-only", "approval", "vidbyte tool", "parent"):
            with self.subTest(words=words):
                self.assertIn(words, description)

    async def test_running_every_new_tool_never_reaches_a_function_that_has_no_tool(self) -> None:
        # T-2: StubCodexHost has none of the nine INV-42 methods, so a tool that called one would fail as codex.api_error.
        host = StubCodexHost()
        tools = _toolset(host, max_live_turns=20)
        handle = await self.owned_handle(tools, host)
        arguments = {
            "update_codex_thread_settings": {"thread_id": "thr-7", "effort": "high"},
            "wait_codex_turns": {"turns": [handle], "timeout_seconds": 1},
            "update_codex_turn_settings": {**handle, "effort": "low"},
            "start_codex_side_chat": {"thread_id": "thr-7", "prompt": "Why?"},
            "pause_codex_goal": {"thread_id": "thr-7"},
            "resume_codex_goal": {"thread_id": "thr-7"},
            "archive_codex_thread": {"thread_id": "thr-7"},
            "unarchive_codex_thread": {"thread_id": "thr-7"},
            "rename_codex_thread": {"thread_id": "thr-7", "name": "Login fix"},
            "list_codex_background_terminals": {"thread_id": "thr-7"},
            "search_codex_thread_content": {"query": "login"},
            "list_codex_child_threads": {"thread_id": "thr-7"},
            "run_codex_plan": {"prompt": "Plan a fix."},
        }
        for name in NEW_TOOLS:
            with self.subTest(tool=name):
                self.assert_success(await _call(tools, name, arguments.get(name, {})))
        self.assertEqual(set(host.names()) & {*NO_TOOL_FUNCTIONS, *OLDER_NO_TOOL_FUNCTIONS}, set())
        self.assertEqual({name for name in host.names() if name in NEW_TOOLS}, set(NEW_TOOLS))


class CodexFeatureToolArgumentTests(_ToolCase):
    """Section 9.2 "Host call and scope rule": what each tool passes to its host method, and the side chat's posture."""

    async def test_the_settings_listing_and_memory_tools_pass_only_their_own_arguments(self) -> None:
        from vidbyte.lib.dataclasses.codex_host_features import CodexThreadSettingsUpdate
        from vidbyte.lib.enums.codex import CodexMcpServerDetail, CodexReasoningEffort

        host = StubCodexHost()
        tools = _toolset(host)
        await _call(tools, "update_codex_thread_settings", {"thread_id": "thr-7", "model": "gpt-5.5", "effort": "high"})
        self.assertEqual(host.last("update_codex_thread_settings")[1], {"thread_id": "thr-7", "settings": CodexThreadSettingsUpdate(model="gpt-5.5", effort=CodexReasoningEffort.HIGH)})
        await _call(tools, "list_codex_mcp_servers", {"thread_id": "thr-7", "server_name": "docs", "cursor": "c-1"})
        listing = host.last("list_codex_mcp_servers")[1]
        self.assertEqual((listing["thread_id"], listing["server_name"], listing["cursor"]), ("thr-7", "docs", "c-1"))
        self.assertIn(listing["detail"], (None, CodexMcpServerDetail.FULL))
        await _call(tools, "get_codex_memory_status")
        self.assertIsNone(host.last("get_codex_memory_status")[1]["min_consolidated_threads"])
        await _call(tools, "search_codex_thread_content", {"query": "login", "archived": True, "cursor": "c-2", "limit": 5})
        self.assertEqual(host.last("search_codex_thread_content")[1], {"query": "login", "archived": True, "cursor": "c-2", "limit": 5})
        await _call(tools, "list_codex_child_threads", {"thread_id": "thr-7", "descendants": True})
        self.assertEqual(host.last("list_codex_child_threads")[1], {"thread_id": "thr-7", "descendants": True, "cursor": "", "limit": None})
        await _call(tools, "list_codex_background_terminals", {"thread_id": "thr-7", "limit": 3})
        self.assertEqual(host.last("list_codex_background_terminals")[1], {"thread_id": "thr-7", "cursor": "", "limit": 3})
        await _call(tools, "rename_codex_thread", {"thread_id": "thr-7", "name": "Login fix"})
        self.assertEqual(host.last("rename_codex_thread")[1], {"thread_id": "thr-7", "name": "Login fix"})

    async def test_the_side_chat_tool_narrows_the_scope_posture_to_read_only_and_never_asking(self) -> None:
        # AC-36 stub half, INV-43, D-22: only the sandboxes, roots, network and approvals change.
        from vidbyte.lib.enums.codex import CodexApprovalMode, CodexApprovalPolicy, CodexApprovalsReviewer, CodexSandbox

        defaults = _writable_defaults()
        host = StubCodexHost()
        tools = _toolset(host, spawn_defaults=defaults)
        handle = _handle_of(self.assert_success(await _call(tools, "start_codex_side_chat", {"thread_id": "thr-7", "prompt": "Which step is riskiest?"})))
        kwargs = host.last("start_codex_side_chat")[1]
        self.assertEqual((kwargs["thread_id"], kwargs["prompt"]), ("thr-7", "Which step is riskiest?"))
        request = kwargs["request"]
        self.assertEqual((request.thread.sandbox, request.turn.sandbox), (CodexSandbox.READ_ONLY, CodexSandbox.READ_ONLY))
        self.assertEqual((request.thread.approval_mode, request.turn.approval_mode), (CodexApprovalMode.DENY_ALL, CodexApprovalMode.DENY_ALL))
        self.assertEqual((request.approval_policy, request.approvals_reviewer), (CodexApprovalPolicy.PROVIDER_DEFAULT, CodexApprovalsReviewer.PROVIDER_DEFAULT))
        self.assertEqual((request.writable_roots, request.network_access), ((), None))
        self.assertEqual(request, _side_chat_view(defaults))
        # The scope owns the side chat's handle.
        self.assert_success(await _call(tools, "get_codex_turn_result", handle))

    async def test_the_side_chat_tool_resets_the_fields_a_side_chat_refuses_before_it_narrows(self) -> None:
        # AC-36 extended, INV-43, D-22 (spec r6, review R-5): tools, name and personality go back to a fresh request's
        # values, so the host can accept the request, and the read-only, never-asking posture still holds.
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.lib.enums.codex import CodexApprovalMode, CodexSandbox

        defaults = _refused_field_defaults()
        host = StubCodexHost()
        tools = _toolset(host, spawn_defaults=defaults)
        self.assert_success(await _call(tools, "start_codex_side_chat", {"thread_id": "thr-7", "prompt": "Why?"}))
        request = host.last("start_codex_side_chat")[1]["request"]
        fresh, fresh_thread = CodexSpawnRequest(), CodexThreadSettings()
        self.assertEqual((request.tools, request.name, request.thread.personality), (fresh.tools, fresh.name, fresh_thread.personality))
        self.assertEqual((request.thread.sandbox, request.turn.sandbox), (CodexSandbox.READ_ONLY, CodexSandbox.READ_ONLY))
        self.assertEqual((request.thread.approval_mode, request.turn.approval_mode), (CodexApprovalMode.DENY_ALL, CodexApprovalMode.DENY_ALL))
        self.assertEqual(request, _side_chat_view(defaults))
        self.assertEqual(request.developer_instructions, defaults.developer_instructions)

    async def test_the_plan_tool_passes_the_scope_posture_and_the_resume_tool_drops_the_fields_resume_refuses(self) -> None:
        # INV-43: the plan's request is spawn_defaults; resume's is spawn_defaults with its continue- and goal-refused fields reset.
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings

        defaults = dataclasses.replace(_writable_defaults(), name="Fixer", thread=CodexThreadSettings(cwd=WORKSPACE, ephemeral=True))
        host = StubCodexHost()
        tools = _toolset(host, spawn_defaults=defaults)
        await _call(tools, "run_codex_plan", {"prompt": "Plan a fix."})
        self.assertEqual(host.last("run_codex_plan")[1], {"prompt": "Plan a fix.", "request": defaults})
        handle = _handle_of(self.assert_success(await _call(tools, "resume_codex_goal", {"thread_id": "thr-7"})))
        kwargs = host.last("resume_codex_goal")[1]
        self.assertEqual(kwargs["thread_id"], "thr-7")
        self.assertEqual(kwargs["request"], _reset(defaults, CONTINUE_REFUSED + GOAL_REFUSED))
        self.assertEqual(handle["thread_id"], "thr-7")


class CodexFeatureToolScopeTests(_ToolCase):
    """AC-37, INV-43, INV-44 and EC-52: cap slots, owned handles, the turn-settings text and the multi-wait JSON."""

    async def test_a_full_cap_refuses_the_plan_side_chat_and_resume_tools_before_the_host(self) -> None:
        host = StubCodexHost()
        tools = _toolset(host, max_live_turns=1)
        running = await self.owned_handle(tools, host)
        arguments = {"run_codex_plan": {"prompt": "Plan again."}, "start_codex_side_chat": {"thread_id": "thr-7", "prompt": "Why?"}, "resume_codex_goal": {"thread_id": "thr-7"}}
        for name in CAP_TOOLS:
            with self.subTest(tool=name):
                self.assert_error_result(await _call(tools, name, arguments[name]), "codex.session_busy")
        self.assertEqual([name for name in host.names() if name in CAP_TOOLS], ["run_codex_plan"])
        _finish(host, running)
        # With the slot free again, each one starts, and its handle belongs to this scope only.
        for name in CAP_TOOLS:
            with self.subTest(after_finish=name):
                handle = _handle_of(self.assert_success(await _call(tools, name, arguments[name])))
                self.assert_success(await _call(tools, "get_codex_turn_result", handle))
                self.assert_error_result(await _call(_toolset(host), "get_codex_turn_result", handle), "codex.session_not_found")
                _finish(host, handle)

    async def test_a_cancelled_side_chat_or_resume_gives_its_slot_back(self) -> None:
        host = StubCodexHost()
        tools = _toolset(host, max_live_turns=1)
        for name, arguments in (("start_codex_side_chat", {"thread_id": "thr-7", "prompt": "Why?"}), ("resume_codex_goal", {"thread_id": "thr-7"})):
            with self.subTest(tool=name):
                host.gates[name] = asyncio.Event()
                calls = host.names().count(name)
                task = asyncio.ensure_future(_call(tools, name, arguments))
                for _ in range(10_000):
                    if host.names().count(name) > calls:
                        break
                    await asyncio.sleep(0)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                del host.gates[name]
                probe = await self.owned_handle(tools, host)
                _finish(host, probe)

    async def test_the_wait_and_turn_settings_tools_refuse_a_handle_this_scope_does_not_own(self) -> None:
        # EC-52: scope.require_owned refuses before the host is called.
        host = StubCodexHost()
        tools = _toolset(host)
        foreign = {"thread_id": "thr-other", "turn_id": "turn-other"}
        rows = (("wait_codex_turns", {"turns": [foreign]}), ("update_codex_turn_settings", {**foreign, "effort": "low"}))
        for name, arguments in rows:
            with self.subTest(tool=name):
                result = await _call(tools, name, arguments)
                self.assert_error_result(result, "codex.session_not_found")
                self.assertIn(NOT_OWNED_TEXT, result.output)
                self.assertNotIn(name, host.names())

    async def test_the_turn_settings_tool_answers_the_status_text_and_sends_no_tier_or_reviewer(self) -> None:
        # AC-37, INV-25: APPLIED is a normal result; the tool reaches only model and effort.
        from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle
        from vidbyte.lib.enums.codex import CodexApprovalsReviewer, CodexReasoningEffort, CodexReasoningSummary

        host = StubCodexHost()
        tools = _toolset(host)
        handle = await self.owned_handle(tools, host)
        result = self.assert_success(await _call(tools, "update_codex_turn_settings", {**handle, "model": "gpt-5.5", "effort": "low"}))
        self.assertEqual(result.output, TURN_SETTINGS_STATUS_TEXT.format(status="applied", turn_id=handle["turn_id"], thread_id=handle["thread_id"]))
        kwargs = host.last("update_codex_turn_settings")[1]
        self.assertEqual((kwargs["handle"], kwargs["model"], kwargs["effort"]), (CodexTurnHandle(**handle), "gpt-5.5", CodexReasoningEffort.LOW))
        self.assertEqual((kwargs["service_tier"], kwargs["clear_service_tier"]), ("", False))
        self.assertIn(kwargs["approvals_reviewer"], (None, CodexApprovalsReviewer.PROVIDER_DEFAULT))
        self.assertIn(kwargs["summary"], (None, CodexReasoningSummary.PROVIDER_DEFAULT))

    async def test_the_multi_wait_returns_one_json_snapshot_per_handle_without_items_and_caps_its_wait(self) -> None:
        # AC-37, INV-43: wait_codex_turns(handles) with the tool's 240-second cap, and _json(..., without_items=True).
        from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle
        from vidbyte.lib.enums.codex import CodexTurnWaitMode

        host = StubCodexHost()
        tools = _toolset(host)
        first, second = await self.owned_handle(tools, host), await self.owned_handle(tools, host)
        _finish(host, first)
        _finish(host, second)
        result = self.assert_success(await _call(tools, "wait_codex_turns", {"turns": [first, second], "return_when": "ALL_COMPLETED"}))
        snapshots = json.loads(result.output)
        self.assertIsInstance(snapshots, list)
        self.assertEqual([snapshot["handle"] for snapshot in snapshots], [first, second])
        for snapshot in snapshots:
            self.assertEqual(snapshot["status"], "completed")
            self.assertNotIn("items", snapshot["result"])
        kwargs = host.last("wait_codex_turns")[1]
        self.assertEqual(kwargs["handles"], (CodexTurnHandle(**first), CodexTurnHandle(**second)))
        self.assertEqual(kwargs["return_when"], CodexTurnWaitMode.ALL_COMPLETED)
        for given, expected in ((None, MAX_WAIT_SECONDS), (1000, MAX_WAIT_SECONDS), (5, 5.0)):
            with self.subTest(timeout_seconds=given):
                await _call(tools, "wait_codex_turns", {"turns": [first], "timeout_seconds": given})
                self.assertEqual(host.last("wait_codex_turns")[1]["timeout_seconds"], expected)


@requires_sdk
class CodexFeatureToolHostTests(FeatureHostCase):
    """AC-36 wire half, EC-53, EC-54 and EC-59: the tools over a real host and the fake app-server."""

    async def test_the_side_chat_tool_sends_never_and_no_reviewer_on_the_fork_and_the_turn(self) -> None:
        # AC-36: DENY_ALL maps to approvalPolicy "never" with no reviewer, from the thread mode on thread/fork and the turn mode on turn/start.
        parent = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        tools = _toolset(host, spawn_defaults=_writable_defaults(cwd=self.fakes.DEFAULT_CWD))
        result = await _call(tools, "start_codex_side_chat", {"thread_id": parent.thread_id, "prompt": "Which step is riskiest?"})
        self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
        fork = self.server.matching("thread/fork")[-1].params
        start = self.server.matching("turn/start")[-1].params
        for label, params in (("thread/fork", fork), ("turn/start", start)):
            with self.subTest(request=label):
                self.assertEqual(params.get("approvalPolicy"), "never")
                self.assertNotIn("approvalsReviewer", params)
        self.assertEqual(fork.get("sandbox"), "read-only")
        self.assertEqual(start["sandboxPolicy"]["type"], "readOnly")
        self.assertIn(start["sandboxPolicy"].get("networkAccess"), (None, False))

    async def test_the_side_chat_tool_starts_on_a_user_reviewer_parent_because_its_fork_never_asks(self) -> None:
        # EC-59: the tool's fork policy is never, so routes_to_user is false and the D-36 refusal cannot happen.
        parent = self.server.seed_thread(completed_turns=1, reviewer="user", policy="on-request")
        host = await self.opened()
        tools = _toolset(host, spawn_defaults=_writable_defaults(cwd=self.fakes.DEFAULT_CWD))
        result = await _call(tools, "start_codex_side_chat", {"thread_id": parent.thread_id, "prompt": "Why?"})
        self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
        self.assertEqual(self.count("thread/inject_items"), 1)

    async def test_the_side_chat_tool_starts_under_defaults_that_set_tools_a_name_and_a_personality(self) -> None:
        # AC-36 extended (spec r6, review R-5): the reset fields are ones the method refuses for a side chat, so it starts,
        # and both the fork and the turn still carry approvalPolicy "never" with no reviewer and a read-only sandbox.
        parent = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        tools = _toolset(host, spawn_defaults=_refused_field_defaults(cwd=self.fakes.DEFAULT_CWD))
        result = await _call(tools, "start_codex_side_chat", {"thread_id": parent.thread_id, "prompt": "Why?"})
        self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
        fork = self.server.matching("thread/fork")[-1].params
        start = self.server.matching("turn/start")[-1].params
        for label, params in (("thread/fork", fork), ("turn/start", start)):
            with self.subTest(request=label):
                self.assertEqual(params.get("approvalPolicy"), "never")
                self.assertNotIn("approvalsReviewer", params)
        self.assertEqual(fork.get("sandbox"), "read-only")
        self.assertEqual(start["sandboxPolicy"]["type"], "readOnly")

    async def test_a_mode_in_the_scope_defaults_makes_the_plan_tool_return_an_error_naming_it(self) -> None:
        # EC-53: run_codex_plan's record refuses collaboration_mode, so the tool answers configuration.invalid_argument.
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.lib.dataclasses.codex_host_modes import CodexCollaborationMode
        from vidbyte.lib.enums.codex import CodexCollaborationModeKind

        host = await self.opened()
        defaults = CodexSpawnRequest(collaboration_mode=CodexCollaborationMode(mode=CodexCollaborationModeKind.PLAN))
        result = await _call(_toolset(host, spawn_defaults=defaults), "run_codex_plan", {"prompt": "Plan a fix."})
        self.assertEqual(result.status, ToolStatus.ERROR, result.output)
        self.assertEqual(result.metadata["code"], "configuration.invalid_argument")
        self.assertIn("collaboration_mode", result.output)
        self.assertEqual(self.sent_methods(), [])

    async def test_a_tool_over_a_host_without_the_experimental_api_returns_the_gate_as_an_error_result(self) -> None:
        # EC-54, INV-44: the host's ConfigurationError becomes configuration.invalid_argument naming the operation.
        from vidbyte.lib.dataclasses.codex import CodexClientSettings

        host = await self.opened(CodexClientSettings(experimental_api=False))
        result = await _call(_toolset(host), "list_codex_collaboration_modes")
        self.assertEqual(result.status, ToolStatus.ERROR, result.output)
        self.assertEqual(result.metadata["code"], "configuration.invalid_argument")
        self.assertTrue(result.output.startswith(EXPERIMENTAL_HEAD), result.output)
        self.assertEqual(self.sent_methods(), [])


if __name__ == "__main__":
    unittest.main()

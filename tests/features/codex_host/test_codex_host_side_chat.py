"""FILE: tests/features/codex_host/test_codex_host_side_chat.py

PURPOSE: Proves start_codex_side_chat over the in-memory app-server: it follows Codex's own /side flow (an ephemeral fork through the parent's latest completed turn with the side-chat developer instructions appended, one injected boundary message, then the turn on the fork), never touches the parent, shares the parent's Vidbyte tools, prices the turn as the fork's model, refuses the fields its row names, refuses a fork whose approvals Codex routes to a person on a host without an approval_handler, and leaves no tool handler and no turn behind when it fails.
ROLE IN CODEBASE: Side-chat layer of the slice-2 tests in tests/features/codex_host/ (docs/spec/codex-host-first-class/spec.md AC-22, AC-23, AC-42, INV-27, INV-28, D-18, D-22, D-36, EC-30 to EC-33, EC-59, NFR-7). Every class needs the optional openai-codex extra, so CI skips them; the docstring half of D-22 and EC-61 is in test_codex_host_feature_docs.py.
ARCHITECTURE NOTE: A real CodexHost talks to FakeAppServer through FeatureHostCase on a patched Linux platform, so the preflight sends only account/read and account/rateLimits/read. The fake's thread/fork copies the parent's reviewer, policy and model unless the params name them (spec section 13), so a parent seeded with reviewer user exercises AC-42 without changing the request, and a parent seeded with another model shows the fork's resolved model on the turn's price. The router check asks the real SDK reader thread an item/tool/call for the fork and reads the host's own answer.
COMMON MODIFICATION PATTERNS: Keep SIDE_CHAT_SEQUENCE whole; section 9.2 calls the request order normative. A new failure step adds one test that checks the error names the fork and that assert_nothing_left holds.
KNOWN EDGE CASES: The fake copies the parent's turns into the fork even with excludeTurns, so the late-turn test counts the fork's turns before Codex accepts the new one. The late-turn test lowers the host to one worker thread, so a thread read is a barrier behind any queued stop.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-first-class/spec.md sections 6.1 (INV-27, INV-28), 6.2, 6.3 and 9.2; docs/spec/codex-host-first-class/test-plan.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_side_chat.py
"""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import Callable
from typing import Any

from tests.features.codex_host.codex_host_feature_support import PROMPT_CANARY, SIDE_CHAT_BOUNDARY_ITEM, SIDE_CHAT_INSTRUCTIONS, priced_cost
from tests.features.codex_host.codex_host_support import (
    HOST_LOGGER,
    REVIEWER_MESSAGE,
    UNREGISTERED_TOOL_TEXT,
    WAIT_SECONDS,
    FeatureHostCase,
    assert_no_canary,
    input_texts,
    make_echo_tool,
    mapped_summary,
    requires_sdk,
    thread_suffix,
)

OPERATION = "start_codex_side_chat"
PREFLIGHT = ["account/read", "account/rateLimits/read"]
# Section 9.2: preflight; thread/read; thread/turns/list (pages until the fork point); thread/fork; thread/inject_items; turn/start.
SIDE_CHAT_SEQUENCE = [*PREFLIGHT, "thread/read", "thread/turns/list", "thread/fork", "thread/inject_items", "turn/start"]
PARENT_METHODS = ["thread/read", "thread/turns/list", "thread/fork"]
RPC_ERROR_TEXT = "Codex answered {method} with JSON-RPC error {code}: '{message}'."
MINI = "gpt-5.4-mini"
QUESTION = "Which step of the plan is riskiest?"


def _on(thread_id: str) -> Callable[[dict[str, Any]], bool]:
    return lambda params: params.get("threadId") == thread_id


async def _decline(request: Any) -> Any:
    """An approval handler that declines everything; these tests only need a host that has one."""
    from vidbyte.lib.dataclasses.codex_host import CodexServerAnswer
    from vidbyte.lib.enums.codex import CodexApprovalDecision

    return CodexServerAnswer(decision=CodexApprovalDecision.DECLINE)


class _SideChatCase(FeatureHostCase):
    """Shared steps: the methods sent on one thread, a parent with Vidbyte tools, and the nothing-left check of INV-28."""

    def methods_on(self, thread_id: str) -> list[str]:
        return [request.method for request in self.sent() if request.params.get("threadId") == thread_id]

    def newest_thread(self) -> str:
        return list(self.server.threads)[-1]

    async def parent_with_tools(self) -> tuple[Any, Any]:
        """A host and a finished parent spawned with the echo tool, so the parent's handler is registered."""
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        host = await self.opened()
        parent = await self.call(host.spawn_codex_thread(CodexSpawnRequest(prompt="Use the tool.", tools=(make_echo_tool(),))))
        self.server.complete_turn(parent.thread_id, parent.turn_id, final="Done.")
        await self.wait_done(host, parent)
        self.remark()
        return host, parent

    async def tool_answer(self, thread_id: str, turn_id: str, call_id: str) -> Any:
        call = {"threadId": thread_id, "turnId": turn_id, "callId": call_id, "tool": "echo_text", "arguments": {"text": "from the side"}}
        return await self.ask("item/tool/call", call)

    async def assert_nothing_left(self, host: Any, fork_id: str, parent_id: str) -> None:
        """INV-28: the router holds no handler for the fork and the registry no turn on it; the parent keeps its handler."""
        unregistered = {"success": False, "contentItems": [{"type": "inputText", "text": UNREGISTERED_TOOL_TEXT}]}
        self.assertEqual(await self.tool_answer(fork_id, "turn-x", "call-fork"), unregistered)
        self.assertIs((await self.tool_answer(parent_id, "turn-x", "call-parent"))["success"], True)
        self.assertEqual([turn for turn in host._registry.running() if turn.handle.thread_id == fork_id], [])
        self.assertIsNone(host._registry.usage(fork_id))
        self.assertFalse(host._registry.busy(fork_id))


@requires_sdk
class CodexSideChatFlowTests(_SideChatCase):
    """AC-22, INV-27, D-18, D-22 and EC-30: the /side flow, the untouched parent, the shared tools and the fork's price."""

    async def test_a_side_chat_forks_the_last_completed_turn_injects_the_boundary_and_starts_its_turn_on_the_fork(self) -> None:
        # AC-22: the parent is mid-turn, so the fork point is its latest completed turn; the handle names the fork.
        parent = self.server.seed_thread(completed_turns=1, running_turn=True)
        completed = parent.turns[0].turn_id
        host = await self.opened()
        handle = await self.call(host.start_codex_side_chat(parent.thread_id, QUESTION))
        fork_id = self.newest_thread()
        self.assertNotEqual(fork_id, parent.thread_id)
        self.assertEqual(self.sent_methods(), SIDE_CHAT_SEQUENCE)
        # The parent is never reserved, resumed, changed, renamed or given a turn.
        self.assertEqual(self.methods_on(parent.thread_id), PARENT_METHODS)
        self.assertEqual(self.methods_on(fork_id), ["thread/inject_items", "turn/start"])
        fork = self.server.matching("thread/fork")[-1].params
        self.assertEqual(fork["threadId"], parent.thread_id)
        self.assertIs(fork.get("ephemeral"), True)
        self.assertEqual(fork.get("developerInstructions"), SIDE_CHAT_INSTRUCTIONS)
        self.assertEqual(fork.get("lastTurnId"), completed)
        self.assertIs(fork.get("excludeTurns"), True)
        self.assertNotIn("beforeTurnId", fork)
        self.assertEqual(self.server.matching("thread/inject_items")[-1].params, {"threadId": fork_id, "items": [SIDE_CHAT_BOUNDARY_ITEM]})
        start = self.server.matching("turn/start")[-1].params
        self.assertEqual(start["threadId"], fork_id)
        self.assertIn(QUESTION, [text for _, text in input_texts(start)])
        self.assertEqual((handle.thread_id, handle.turn_id), (fork_id, self.server.threads[fork_id].turns[-1].turn_id))
        self.assertEqual(self.count("thread/name/set"), 0)
        # EC-30: the side chat runs to its end on the fork; nothing unloads the fork.
        self.server.complete_turn(fork_id, handle.turn_id, final="Step three.")
        self.assert_problem(await self.wait_done(host, handle), "completed", None)
        self.assertEqual(self.count("thread/unsubscribe"), 0)

    async def test_the_requests_own_developer_instructions_come_first_then_a_blank_line_then_the_side_chat_text(self) -> None:
        # INV-27 step 4: "the request's own, then a blank line, then CODEX_HOST_SIDE_CHAT_INSTRUCTIONS".
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        parent = self.server.seed_thread(completed_turns=2)
        host = await self.opened()
        await self.call(host.start_codex_side_chat(parent.thread_id, QUESTION, CodexSpawnRequest(developer_instructions="Answer in one short paragraph.")))
        fork = self.server.matching("thread/fork")[-1].params
        self.assertEqual(fork.get("developerInstructions"), "Answer in one short paragraph.\n\n" + SIDE_CHAT_INSTRUCTIONS)
        self.assertEqual(fork.get("lastTurnId"), parent.turns[-1].turn_id)

    async def test_the_parents_vidbyte_tools_stay_callable_from_the_side_chat(self) -> None:
        # INV-27 step 4 "The tools", D-22: the fork shares the parent's tool handler.
        host, parent = await self.parent_with_tools()
        side = await self.call(host.start_codex_side_chat(parent.thread_id, "Echo from the side."))
        self.assertNotEqual(side.thread_id, parent.thread_id)
        answer = await self.tool_answer(side.thread_id, side.turn_id, "call-side")
        self.assertEqual(answer, {"success": True, "contentItems": [{"type": "inputText", "text": "echo: from the side"}]})

    async def test_the_side_chat_is_priced_as_the_forks_model_and_a_mode_takes_that_model(self) -> None:
        # INV-27 step 6 and INV-13: the fork reports the parent's model; NFR-10: no mode sends no collaborationMode key.
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.lib.dataclasses.codex_host_modes import CodexCollaborationMode
        from vidbyte.lib.enums.codex import CodexCollaborationModeKind

        parent = self.server.seed_thread(completed_turns=1)
        parent.model = MINI
        self.server.model_pages[0].append(self.fakes._model(MINI, MINI))
        host = await self.opened()
        handle = await self.call(host.start_codex_side_chat(parent.thread_id, QUESTION))
        self.assertNotIn("collaborationMode", self.server.matching("turn/start")[-1].params)
        expected = priced_cost(MINI, ((1000, 200),))
        self.assertGreater(expected, 0)
        self.assertNotAlmostEqual(expected, priced_cost("gpt-5.5", ((1000, 200),)), places=9)
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="Step two.", usage=self.fakes.token_usage((1000, 200), (1000, 200)))
        await self.wait_done(host, handle)
        usage = await self.call(host.track_codex_thread_usage(handle.thread_id))
        self.assertAlmostEqual(float(usage.cost_usd), expected, places=12)

        planned = CodexSpawnRequest(collaboration_mode=CodexCollaborationMode(mode=CodexCollaborationModeKind.PLAN))
        await self.call(host.start_codex_side_chat(parent.thread_id, QUESTION, planned))
        self.assertEqual(self.server.matching("turn/start")[-1].params["collaborationMode"], {"mode": "plan", "settings": {"model": MINI}})

    async def test_the_side_chats_prompt_reaches_no_log_record(self) -> None:
        # NFR-7: a prompt is never logged; ids are.
        records = self.capture_logs(HOST_LOGGER)
        parent = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        handle = await self.call(host.start_codex_side_chat(parent.thread_id, f"Why is {PROMPT_CANARY} slow?"))
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="Because.")
        await self.wait_done(host, handle)
        self.assertTrue(records)
        assert_no_canary(self, [record.getMessage() for record in records], (PROMPT_CANARY,))


@requires_sdk
class CodexSideChatRefusalTests(_SideChatCase):
    """AC-23, AC-42, INV-28, D-36, EC-31, EC-32 and EC-59: what a side chat refuses and what a failed one leaves."""

    async def test_a_failed_inject_names_the_fork_releases_its_tools_and_registers_no_turn(self) -> None:
        # AC-23: the inject failure comes after the handler was shared, so release_tools must undo it.
        host, parent = await self.parent_with_tools()
        self.server.fail("thread/inject_items", self.fakes.FakeRpcError(-32603, "inject store failed"), times=1)
        error = await self.assert_codex_error(host.start_codex_side_chat(parent.thread_id, QUESTION), "codex.api_error")
        fork_id = self.newest_thread()
        self.assertNotEqual(fork_id, parent.thread_id)
        self.assertEqual((error.operation, error.thread_id), (OPERATION, fork_id))
        self.assertEqual(mapped_summary(self, error), RPC_ERROR_TEXT.format(method="thread/inject_items", code=-32603, message="inject store failed") + thread_suffix(fork_id))
        self.assertEqual(self.count("turn/start", _on(fork_id)), 0)
        await self.assert_nothing_left(host, fork_id, parent.thread_id)

    async def test_a_failed_turn_start_names_the_fork_releases_its_tools_and_registers_no_turn(self) -> None:
        # INV-28: "A later failure (inject, or turn start) releases the fork's tool handler".
        host, parent = await self.parent_with_tools()
        self.server.fail("turn/start", self.fakes.FakeRpcError(-32603, "turn store failed"), times=1, predicate=lambda params: params.get("threadId") != parent.thread_id)
        error = await self.assert_codex_error(host.start_codex_side_chat(parent.thread_id, QUESTION), "codex.api_error")
        fork_id = self.newest_thread()
        self.assertEqual((error.operation, error.thread_id), (OPERATION, fork_id))
        self.assertEqual(self.methods_on(fork_id), ["thread/inject_items", "turn/start"])
        await self.assert_nothing_left(host, fork_id, parent.thread_id)

    async def test_a_fork_codex_routes_to_a_user_reviewer_is_refused_before_the_inject_on_a_host_without_a_handler(self) -> None:
        # AC-42, EC-59, D-36: the request names no reviewer, so the fork sends none and Codex copies the parent's user reviewer.
        parent = self.server.seed_thread(completed_turns=1, reviewer="user", policy="on-request")
        host = await self.opened()
        error = await self.assert_codex_error(host.start_codex_side_chat(parent.thread_id, QUESTION), "configuration.unsupported_combination")
        fork_id = self.newest_thread()
        self.assertNotEqual(fork_id, parent.thread_id)
        self.assertEqual((error.operation, error.thread_id), (OPERATION, fork_id))
        self.assertEqual(mapped_summary(self, error), REVIEWER_MESSAGE + thread_suffix(fork_id))
        self.assertEqual(self.sent_methods(), [*PREFLIGHT, *PARENT_METHODS])
        self.assertNotIn("approvalsReviewer", self.server.matching("thread/fork")[-1].params)
        # The refusal comes before the handler is shared, so the fork has none; the fork stays loaded (EC-30).
        unregistered = {"success": False, "contentItems": [{"type": "inputText", "text": UNREGISTERED_TOOL_TEXT}]}
        self.assertEqual(await self.tool_answer(fork_id, "turn-x", "call-fork"), unregistered)
        self.assertEqual([turn for turn in host._registry.running() if turn.handle.thread_id == fork_id], [])
        self.assertIsNone(host._registry.usage(fork_id))
        self.assertEqual(self.count("thread/unsubscribe"), 0)

    async def test_a_user_reviewer_with_policy_never_or_a_host_with_a_handler_starts_the_side_chat(self) -> None:
        # INV-27 step 4: routes_to_user is false for policy never, and a host with an approval_handler answers a person's requests.
        never = self.server.seed_thread(completed_turns=1, reviewer="user", policy="never")
        host = await self.opened()
        handle = await self.call(host.start_codex_side_chat(never.thread_id, QUESTION))
        self.assertEqual(self.server.matching("turn/start")[-1].params["threadId"], handle.thread_id)

        human = self.server.seed_thread(completed_turns=1, reviewer="user", policy="on-request")
        answered = await self.opened(approval_handler=_decline)
        side = await self.call(answered.start_codex_side_chat(human.thread_id, QUESTION))
        self.assertEqual(self.sent_methods(), SIDE_CHAT_SEQUENCE)
        self.assertNotEqual(side.thread_id, human.thread_id)

    async def test_a_parent_with_no_completed_turn_is_refused_before_the_fork_with_the_side_chats_operation(self) -> None:
        # EC-31: the fork-point walk finds none (hardening INV-28 step 5), so nothing is forked.
        empty = self.server.seed_thread(completed_turns=0)
        running = self.server.seed_thread(completed_turns=0, running_turn=True)
        host = await self.opened()
        for parent in (empty, running):
            with self.subTest(turns=len(parent.turns)):
                self.remark()
                error = await self.assert_codex_error(host.start_codex_side_chat(parent.thread_id, QUESTION), "codex.fork_failed")
                self.assertEqual(error.operation, OPERATION)
                self.assertNotIn("thread/fork", self.sent_methods())

    async def test_an_unknown_parent_an_unknown_model_or_a_user_reviewer_request_sends_no_fork(self) -> None:
        # INV-28: "A failure before the fork sends no fork."
        from vidbyte.lib.dataclasses.codex import CodexTurnSettings
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.lib.enums.codex import CodexApprovalsReviewer

        parent = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        rows = (
            ("thr-unknown", None, "codex.session_not_found"),
            (parent.thread_id, CodexSpawnRequest(turn=CodexTurnSettings(model="gpt-unknown-9")), "codex.model_unknown"),
            (parent.thread_id, CodexSpawnRequest(approvals_reviewer=CodexApprovalsReviewer.USER), "configuration.unsupported_combination"),
        )
        for thread_id, request, code in rows:
            with self.subTest(code=code):
                error = await self.assert_codex_error(host.start_codex_side_chat(thread_id, QUESTION, request), code)
                self.assertEqual(error.operation, OPERATION)
        self.assertEqual(self.count("thread/fork"), 0)
        self.assertEqual(self.count("thread/inject_items"), 0)

    async def test_a_name_tools_an_ephemeral_setting_a_prompt_or_a_goal_in_the_request_is_refused_before_any_request(self) -> None:
        # EC-32 and the START_CODEX_SIDE_CHAT row: side chats are never renamed, share the parent's tools, and are always ephemeral.
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings
        from vidbyte.lib.dataclasses.codex_host import CodexGoal, CodexSpawnRequest

        parent = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        rows = (
            ("name", CodexSpawnRequest(name="Side question")),
            ("tools", CodexSpawnRequest(tools=(make_echo_tool(),))),
            ("thread.ephemeral", CodexSpawnRequest(thread=CodexThreadSettings(ephemeral=True))),
            ("prompt", CodexSpawnRequest(prompt="Another prompt.")),
            ("goal", CodexSpawnRequest(goal=CodexGoal(objective="Ship it."))),
        )
        for field_name, request in rows:
            with self.subTest(field=field_name):
                await self.refused_locally(host.start_codex_side_chat(parent.thread_id, QUESTION, request), field_name)

    async def test_a_side_chat_cancelled_after_codex_accepted_its_turn_has_that_turn_interrupted_once(self) -> None:
        # EC-33, D-2: connection.start's hand-over adopts the late turn and stops it once, with no problem.
        from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle

        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        parent = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        turn_start = self.server.hold("turn/start")
        task = asyncio.ensure_future(host.start_codex_side_chat(parent.thread_id, QUESTION))
        fork_id = (await asyncio.to_thread(turn_start.wait_arrived)).params["threadId"]
        copied = len(self.server.threads[fork_id].turns)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, WAIT_SECONDS)
        turn_start.release()
        await self.wait_until(lambda: len(self.server.threads[fork_id].turns) > copied, "Codex to accept the late side-chat turn")
        turn_id = self.server.threads[fork_id].turns[-1].turn_id
        await self.wait_for_request("turn/interrupt", lambda params: params["turnId"] == turn_id)
        await self.call(host.read_codex_thread(fork_id))
        self.assertEqual(self.count("turn/interrupt", lambda params: params["turnId"] == turn_id), 1)
        snapshot = await self.wait_done(host, CodexTurnHandle(thread_id=fork_id, turn_id=turn_id))
        self.assert_problem(snapshot, "interrupted", None)
        self.assertEqual(self.count("turn/start", _on(parent.thread_id)), 0)


if __name__ == "__main__":
    unittest.main()

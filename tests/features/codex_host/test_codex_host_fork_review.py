"""FILE: tests/features/codex_host/test_codex_host_fork_review.py

PURPOSE: Proves the hardened fork and review paths: fork runs its checks in the spec's fixed order, sends beforeTurnId with no lastTurnId and deferGoalContinuation when asked, refuses both fork points and, on a host without the experimental API, either experimental field before any request, refuses an unknown override model before thread/fork, and unregisters the fork's tools when its name cannot be set; a review takes a request whose time cap stops it once and refuses any other field; and no host path but read_codex_thread asks Codex for a thread's full history.
ROLE IN CODEBASE: Fork and review layer of the hardening tests in tests/features/codex_host/ (docs/spec/codex-host-hardening/spec.md AC-22, AC-25, AC-33, INV-28, INV-30, INV-38, EC-25, EC-54, EC-56, D-18, D-19, D-21). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: The fake app-server ignores beforeTurnId and deferGoalContinuation and does not model Codex's experimental-API capability (spec section 13), so these tests assert the params the host sent and test the experimental gate as a local refusal that sends nothing.
COMMON MODIFICATION PATTERNS: A new fork step adds one row to the order test with the request it sends or refuses before.
KNOWN EDGE CASES: openai-codex always sends includeTurns on thread/read, as false unless asked, so "no full-history read" means no thread/read whose includeTurns is true. The review time cap uses 0.2 seconds rather than the spec's 1.0, so the run stays fast; the rule is the same.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-hardening/spec.md section 6.1 (INV-28, INV-30, INV-38).
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_fork_review.py
"""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import Callable
from typing import Any

from tests.features.codex_host.codex_host_support import (
    FORK_EXPERIMENTAL_MESSAGE,
    FORK_POINTS_MESSAGE,
    UNREGISTERED_TOOL_TEXT,
    WAIT_SECONDS,
    HostTestCase,
    is_review_read_back,
    make_echo_tool,
    requires_sdk,
    thread_suffix,
)
from vidbyte.lib.errors import ConfigurationError

REVIEW_TIMEOUT_SECONDS = 0.2


def _on(thread_id: str) -> Callable[[dict[str, Any]], bool]:
    return lambda params: params.get("threadId") == thread_id


class ForkReviewTestCase(HostTestCase):
    """HostTestCase plus the full-history check every test here ends with."""

    def assert_no_full_history_read(self) -> None:
        """INV-38: no thread/read with includeTurns true; openai-codex sends the key as false otherwise."""
        self.assertEqual([request.params for request in self.server.matching("thread/read") if request.params.get("includeTurns")], [])

    async def refused_locally(self, call: Any, field_name: str) -> ConfigurationError:
        sent = len(self.server.requests)
        with self.assertRaises(ConfigurationError) as caught:
            await asyncio.wait_for(call, WAIT_SECONDS)
        self.assertEqual(caught.exception.details.get("field"), field_name)
        self.assertEqual(len(self.server.requests), sent)
        return caught.exception


@requires_sdk
class CodexForkHardeningTests(ForkReviewTestCase):
    """AC-22, INV-28, D-19, D-21, EC-25, EC-54 and EC-56: the fork points, the deferred goal and the fixed check order."""

    async def test_before_turn_id_is_sent_alone_and_defer_goal_continuation_is_sent_when_asked(self) -> None:
        host = await self.open_host()
        parent = self.server.seed_thread(completed_turns=2)
        before = parent.turns[1].turn_id
        since = len(self.server.requests)
        await asyncio.wait_for(host.fork_codex_thread(parent.thread_id, before_turn_id=before), WAIT_SECONDS)
        on_parent = [request for request in list(self.server.requests)[since:] if request.params.get("threadId") == parent.thread_id]
        self.assertEqual([request.method for request in on_parent], ["thread/read", "thread/fork"])
        fork_params = on_parent[-1].params
        self.assertEqual(fork_params.get("beforeTurnId"), before)
        self.assertNotIn("lastTurnId", fork_params)
        self.assertNotIn("deferGoalContinuation", fork_params)

        await asyncio.wait_for(host.fork_codex_thread(parent.thread_id, defer_goal_continuation=True), WAIT_SECONDS)
        deferred = self.server.matching("thread/fork")[-1].params
        self.assertIs(deferred.get("deferGoalContinuation"), True)
        self.assertEqual(deferred.get("lastTurnId"), parent.turns[1].turn_id)
        self.assertNotIn("beforeTurnId", deferred)
        self.assert_no_full_history_read()

    async def test_both_fork_points_and_an_unknown_override_model_are_refused_before_the_fork(self) -> None:
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        host = await self.open_host()
        parent = self.server.seed_thread(completed_turns=2)
        error = await self.refused_locally(host.fork_codex_thread(parent.thread_id, from_turn_id=parent.turns[0].turn_id, before_turn_id=parent.turns[1].turn_id), "before_turn_id")
        self.assertEqual(str(error), FORK_POINTS_MESSAGE)
        unknown = CodexSpawnRequest(thread=CodexThreadSettings(model="gpt-unknown-9"))
        await self.assert_codex_error(host.fork_codex_thread(parent.thread_id, overrides=unknown), "codex.model_unknown")
        self.assertEqual(self.count("thread/fork"), 0)
        self.assert_no_full_history_read()

    async def test_a_fork_whose_name_cannot_be_set_names_the_fork_and_unregisters_its_tools(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        host = await self.open_host()
        parent = await asyncio.wait_for(host.spawn_codex_thread(CodexSpawnRequest(prompt="Use the tool.", tools=(make_echo_tool(),))), WAIT_SECONDS)
        self.server.complete_turn(parent.thread_id, parent.turn_id, final="Done.")
        await self.wait_done(host, parent)
        self.server.fail("thread/name/set", self.fakes.FakeRpcError(-32603, "name store failed"), times=1)
        error = await self.assert_codex_error(host.fork_codex_thread(parent.thread_id, overrides=CodexSpawnRequest(name="Forked run")), "codex.api_error")
        fork_id = list(self.server.threads)[-1]
        self.assertNotEqual(fork_id, parent.thread_id)
        self.assertEqual(error.thread_id, fork_id)
        self.assertIn(thread_suffix(fork_id), error.message)
        call = {"threadId": fork_id, "turnId": "turn-x", "callId": "call-1", "tool": "echo_text", "arguments": {"text": "hi"}}
        self.assertEqual(await self.ask("item/tool/call", call), {"success": False, "contentItems": [{"type": "inputText", "text": UNREGISTERED_TOOL_TEXT}]})
        # The parent keeps its own registration.
        self.assertIs((await self.ask("item/tool/call", {**call, "threadId": parent.thread_id, "callId": "call-2"}))["success"], True)

    async def test_without_the_experimental_api_each_experimental_field_is_refused_before_any_request(self) -> None:
        from vidbyte.lib.dataclasses.codex import CodexClientSettings

        host = await self.open_host(CodexClientSettings(experimental_api=False))
        parent = self.server.seed_thread(completed_turns=2)
        rows = (
            ("before_turn_id", {"before_turn_id": parent.turns[1].turn_id}),
            ("defer_goal_continuation", {"defer_goal_continuation": True}),
            ("before_turn_id", {"before_turn_id": parent.turns[1].turn_id, "defer_goal_continuation": True}),
        )
        for field_name, fields in rows:
            with self.subTest(fields=sorted(fields)):
                error = await self.refused_locally(host.fork_codex_thread(parent.thread_id, **fields), field_name)
                self.assertEqual(str(error), FORK_EXPERIMENTAL_MESSAGE.format(field=field_name))
        # A plain fork still works on that host.
        await asyncio.wait_for(host.fork_codex_thread(parent.thread_id), WAIT_SECONDS)


@requires_sdk
class CodexReviewRequestTests(ForkReviewTestCase):
    """AC-25, AC-33, INV-30, INV-38 and D-18: a capped review, a refused field, and one-page read-backs."""

    async def test_a_review_with_a_time_cap_is_interrupted_once_and_labelled_timed_out(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget, CodexSpawnRequest
        from vidbyte.lib.enums.codex import CodexReviewTargetKind

        host = await self.open_host()
        stored = self.server.seed_thread()
        target = CodexReviewTarget(kind=CodexReviewTargetKind.UNCOMMITTED_CHANGES)
        handle = await asyncio.wait_for(host.start_codex_review(stored.thread_id, target, request=CodexSpawnRequest(timeout_seconds=REVIEW_TIMEOUT_SECONDS)), WAIT_SECONDS)
        snapshot = await self.wait_done(host, handle)
        self.assert_problem(snapshot, "interrupted", "codex.turn_timed_out")
        self.assertEqual(self.count("turn/interrupt", _on(handle.thread_id)), 1)
        self.assert_no_full_history_read()

    async def test_a_review_request_with_a_turn_is_refused_before_any_request(self) -> None:
        from vidbyte.lib.dataclasses.codex import CodexTurnSettings
        from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget, CodexSpawnRequest
        from vidbyte.lib.enums.codex import CodexReviewTargetKind

        host = await self.open_host()
        stored = self.server.seed_thread()
        target = CodexReviewTarget(kind=CodexReviewTargetKind.UNCOMMITTED_CHANGES)
        error = await self.refused_locally(host.start_codex_review(stored.thread_id, target, request=CodexSpawnRequest(turn=CodexTurnSettings(model="x"))), "turn")
        self.assertIn("start_codex_review does not use the CodexSpawnRequest field turn", str(error))
        # request=None keeps the uncapped review of today.
        handle = await asyncio.wait_for(host.start_codex_review(stored.thread_id, target, request=None), WAIT_SECONDS)
        self.assertEqual(handle.thread_id, stored.thread_id)

    async def test_a_completed_inline_review_is_read_back_by_two_one_item_pages_and_never_by_full_history(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget
        from vidbyte.lib.enums.codex import CodexReviewTargetKind

        host = await self.open_host()
        stored = self.server.seed_thread()
        handle = await asyncio.wait_for(host.start_codex_review(stored.thread_id, CodexReviewTarget(kind=CodexReviewTargetKind.UNCOMMITTED_CHANGES)), WAIT_SECONDS)
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="Reviewed.")
        snapshot = await self.wait_done(host, handle)
        self.assert_problem(snapshot, "completed", None)
        self.assertEqual(snapshot.result.final_response, "Reviewed.")
        pages = self.server.matching("thread/turns/list", _on(handle.thread_id))
        self.assertEqual(len(pages), 2)
        self.assertTrue(all(is_review_read_back(request.params) for request in pages), [request.params for request in pages])
        self.assert_no_full_history_read()


if __name__ == "__main__":
    unittest.main()

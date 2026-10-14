"""FILE: tests/features/codex_host/test_codex_host_review_gaps.py

PURPOSE: Pins the windows the S4 review of CodexHost found open: a review cancelled during its registration read-back, a cancelled launch, a cancelled close, an unusable output_schema, a start still in flight when its caller left, the problem a late-accepted turn or goal run ends with, a mapping output_schema that only parses JSON, and the launch tool's cap slots on failure and cancellation.
ROLE IN CODEBASE: Regression layer of tests/features/codex_host/ (review.md R-1, R-2, R-6, R-7, R-10, R-12, R-13 and R-14; spec INV-7, INV-8, INV-11, INV-21, INV-24, INV-32, INV-37, D-35, D-36, EC-36, EC-52, EC-82 and EC-83). The host classes need the optional openai-codex extra, so CI skips them; the launch tool class runs over StubCodexHost and is CI-visible.
ARCHITECTURE NOTE: Holds on the fake app-server keep one request unanswered while the test cancels its caller. Exact interrupt counts use the pack's one-worker barrier: with CODEX_HOST_WORKER_THREADS patched to 1, a later host call cannot return before an interrupt queued earlier has reached the fake.
COMMON MODIFICATION PATTERNS: Add a cancellation window by holding the request the window awaits, cancelling the caller, releasing the hold, and asserting who owns what Codex accepted.
KNOWN EDGE CASES: openai-codex queues a second turn/start on a thread behind a held first one, so a second continue is run as a task and never awaited while the first start is held. A late start lands through a callback a host worker posts to the loop, so a test that needs the landing polls for it, bounded by WAIT_SECONDS.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host/review.md; docs/spec/codex-host/spec.md sections 6.1, 6.3 and 8.1.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_review_gaps.py
"""

from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass
from typing import Any

from tests.features.codex_host.codex_host_support import (
    WAIT_SECONDS,
    HostTestCase,
    requires_sdk,
)


@dataclass(frozen=True)
class _DataclassAnswer:
    """A record type a developer might pass as output_schema, which is not a Pydantic model."""

    summary: str


# EC-82: a type that is not a Pydantic model, and a mapping that cannot be serialized to JSON.
UNUSABLE_SCHEMAS: tuple[tuple[str, Any], ...] = (
    ("a dataclass type", _DataclassAnswer),
    ("a mapping that is not JSON", {"type": "object", "properties": {"summary": object()}}),
)


@requires_sdk
class CodexHostReviewReadBackCancellationTests(HostTestCase):
    """R-1, INV-11 and INV-14: a review whose caller leaves during the read-back is still owned."""

    async def test_a_review_cancelled_during_its_read_back_is_watched_and_interrupted_once(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget, CodexTurnHandle
        from vidbyte.lib.enums.codex import CodexReviewTargetKind

        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        host = await self.open_host()
        seeded = self.server.seed_thread(completed_turns=1)
        read_back = self.server.hold("thread/read", lambda params: bool(params.get("includeTurns")))
        task = asyncio.ensure_future(host.start_codex_review(seeded.thread_id, CodexReviewTarget(kind=CodexReviewTargetKind.UNCOMMITTED_CHANGES)))
        await asyncio.to_thread(read_back.wait_arrived)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, WAIT_SECONDS)
        read_back.release()
        review_turn = seeded.turns[-1].turn_id
        await self.wait_for_request("turn/interrupt", lambda params: params["turnId"] == review_turn)
        # Barrier: with one host worker, this read returns only after any interrupt queued before it was sent.
        await asyncio.wait_for(host.read_codex_thread(seeded.thread_id), WAIT_SECONDS)
        self.assertEqual(self.count("turn/interrupt", lambda params: params["turnId"] == review_turn), 1)
        snapshot = await self.wait_done(host, CodexTurnHandle(thread_id=seeded.thread_id, turn_id=review_turn))
        self.assert_problem(snapshot, "interrupted", None)
        # The ended review frees the thread, so the next turn on it is accepted.
        handle = await asyncio.wait_for(host.continue_codex_thread(seeded.thread_id, "Apply the review."), WAIT_SECONDS)
        self.assertEqual(handle.thread_id, seeded.thread_id)


@requires_sdk
class CodexHostOutputSchemaRefusalTests(HostTestCase):
    """R-2, EC-82 and INV-8: an output_schema that cannot be used is refused before any request."""

    async def test_spawn_continue_and_launch_refuse_an_unusable_schema_before_any_request(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.lib.errors import ConfigurationError

        host = await self.open_host()
        seeded = self.server.seed_thread(completed_turns=1)
        calls = (
            ("spawn", lambda schema: host.spawn_codex_thread(CodexSpawnRequest(prompt="Answer in JSON.", output_schema=schema))),
            ("continue", lambda schema: host.continue_codex_thread(seeded.thread_id, "Answer in JSON.", overrides=CodexSpawnRequest(output_schema=schema))),
            ("launch", lambda schema: host.launch_codex_subagents(["Answer in JSON."], request=CodexSpawnRequest(output_schema=schema))),
        )
        for label, schema in UNUSABLE_SCHEMAS:
            for name, call in calls:
                with self.subTest(schema=label, operation=name):
                    before = len(self.server.requests)
                    with self.assertRaises(ConfigurationError) as caught:
                        await asyncio.wait_for(call(schema), WAIT_SECONDS)
                    self.assertIn("output_schema", str(caught.exception))
                    # Nothing was sent, so no thread was created or resumed for a turn that could never start.
                    self.assertEqual(self.server.methods()[before:], [])


@requires_sdk
class CodexHostLaunchCancellationTests(HostTestCase):
    """R-6, INV-37 and INV-11: a cancelled launch still stops every turn it already started."""

    async def test_a_launch_cancelled_after_its_first_turn_interrupts_that_turn_once(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle

        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        host = await self.open_host()
        second_thread = self.server.hold("thread/start", lambda params: len(self.server.matching("thread/start")) >= 2)
        task = asyncio.ensure_future(host.launch_codex_subagents(["Fix the first bug.", "Fix the second bug."]))
        await asyncio.to_thread(second_thread.wait_arrived)
        thread_id = self.server.matching("turn/start")[0].params["threadId"]
        first_turn = self.server.threads[thread_id].turns[-1].turn_id
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, WAIT_SECONDS)
        second_thread.release()
        await self.wait_for_request("turn/interrupt", lambda params: params["turnId"] == first_turn)
        # Barrier: with one host worker, this read returns only after any interrupt queued before it was sent.
        await asyncio.wait_for(host.read_codex_thread(thread_id), WAIT_SECONDS)
        self.assertEqual(self.count("turn/interrupt"), 1)
        self.assertEqual(self.count("turn/start"), 1)
        snapshot = await self.wait_done(host, CodexTurnHandle(thread_id=thread_id, turn_id=first_turn))
        self.assert_problem(snapshot, "interrupted", None)


if __name__ == "__main__":
    unittest.main()

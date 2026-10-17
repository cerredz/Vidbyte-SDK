"""FILE: tests/features/codex_host/test_codex_host_first_class_snippet.py

PURPOSE: Proves the developer-usage snippet of the first-class-features spec runs as written against the in-memory app-server: it prints the plan text as Codex streams it, then the build turn's and the side chat's statuses in the order given, then the MCP server names Codex reports.
ROLE IN CODEBASE: End-to-end acceptance test of the slice-2 tests in tests/features/codex_host/ (docs/spec/codex-host-first-class/spec.md AC-1, section 4). It needs the optional openai-codex extra, so CI skips it.
ARCHITECTURE NOTE: The snippet runs as a task while the test plays Codex. The plan's deltas are emitted while the plan turn runs, and the plan turn is completed only once the snippet has printed the whole plan, which a stdout recorder signals with an asyncio.Event, so the snippet's stream is certainly open before the turn ends (a stream opened after the end yields only ENDED, AC-15). The build and side-chat turns are completed by the fake's autocomplete, switched on before the plan turn ends.
COMMON MODIFICATION PATTERNS: When section 4 changes, copy the new snippet into main() verbatim, apart from asyncio.run, and update the expected lines.
KNOWN EDGE CASES: The snippet opens its own CodexHost, so the test uses HostTestCase's seam and not FeatureHostCase.opened. The plan text ends with a newline, so the printed lines split cleanly although the snippet prints the deltas with end="".
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-first-class/spec.md sections 4 and 6.2; tests/features/codex_host/test_codex_host_lifecycle.py (the slice-1 snippet test).
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_first_class_snippet.py
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import unittest

from tests.features.codex_host.codex_host_support import CLOSE_SECONDS, WAIT_SECONDS, HostTestCase, requires_sdk

PLAN_STEPS = ("1. Reproduce the failing login test.\n", "2. Fix the session check.\n")
PLAN_TEXT = "".join(PLAN_STEPS)
SERVER_NAMES = ("docs", "github")


class _PrintedRecorder(io.StringIO):
    """A stdout stand-in that sets an event once the printed text holds the marker (print runs on the test loop)."""

    def __init__(self, marker: str) -> None:
        super().__init__()
        self.marker = marker
        self.seen = asyncio.Event()

    def write(self, text: str) -> int:
        written = super().write(text)
        if self.marker in self.getvalue():
            self.seen.set()
        return written


@requires_sdk
class CodexFirstClassSnippetTests(HostTestCase):
    """AC-1: the section 4 snippet prints its documented lines."""

    async def test_the_section_4_snippet_prints_the_streamed_plan_then_both_statuses_then_the_server_names(self) -> None:
        from tests.features.codex_host.codex_host_feature_fakes import mcp_server
        from vidbyte.harnesses.native.codex import CodexHost
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.lib.dataclasses.codex_host_features import CodexThreadSettingsUpdate
        from vidbyte.lib.dataclasses.codex_host_modes import CodexCollaborationMode
        from vidbyte.lib.enums.codex import CodexCollaborationModeKind, CodexReasoningEffort, CodexTurnEventKind, CodexTurnWaitMode

        self.server.mcp_servers = [mcp_server(name) for name in SERVER_NAMES]

        async def main() -> None:
            # Spec section 4, verbatim apart from asyncio.run, which the test loop replaces.
            async with CodexHost() as host:
                # Plan first, printing the plan as Codex writes it.
                plan = await host.run_codex_plan("Plan a fix for the failing login test.")
                async for event in host.stream_codex_turn(plan):
                    if event.kind is CodexTurnEventKind.PLAN_DELTA:
                        print(event.text, end="")
                # Raise the thread's effort, leave plan mode to build, and ask a side question meanwhile.
                await host.update_codex_thread_settings(plan.thread_id, CodexThreadSettingsUpdate(effort=CodexReasoningEffort.HIGH))
                default_mode = CodexSpawnRequest(collaboration_mode=CodexCollaborationMode(mode=CodexCollaborationModeKind.DEFAULT))
                build = await host.continue_codex_thread(plan.thread_id, "Implement the plan.", default_mode)
                side = await host.start_codex_side_chat(plan.thread_id, "Which step of the plan is riskiest?")
                done = await host.wait_codex_turns((build, side), return_when=CodexTurnWaitMode.ALL_COMPLETED)
                print([snapshot.status.value for snapshot in done])
                print([server.name for server in (await host.list_codex_mcp_servers()).servers])

        printed = _PrintedRecorder(PLAN_TEXT)
        with contextlib.redirect_stdout(printed):
            snippet = asyncio.ensure_future(main())
            try:
                # Play Codex: the plan turn streams its plan while it runs. A snippet that failed first shows its own error.
                try:
                    start = await self.wait_for_request("turn/start")
                except AssertionError:
                    if snippet.done():
                        snippet.result()
                    raise
                thread_id = start.params["threadId"]
                await self.wait_until(lambda: bool(self.server.threads[thread_id].turns), "Codex to accept the plan turn")
                turn_id = self.server.threads[thread_id].turns[-1].turn_id
                item = self.server.plan_item(PLAN_TEXT)
                notes = [self.server.started_note(thread_id, turn_id, item)]
                notes += [self.server.delta_note("item/plan/delta", thread_id, turn_id, item["id"], step) for step in PLAN_STEPS]
                self.server.emit(notes)
                # The snippet printed the whole plan, so its stream is open; now the later turns finish as they start.
                await asyncio.wait_for(printed.seen.wait(), WAIT_SECONDS)
                self.server.autocomplete = {"final": "Done.", "usage": self.fakes.token_usage((100, 20), (100, 20))}
                self.server.complete_turn(thread_id, turn_id, final=PLAN_TEXT)
                await asyncio.wait_for(asyncio.shield(snippet), CLOSE_SECONDS)
            finally:
                if not snippet.done():
                    snippet.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await snippet
        self.assertEqual(printed.getvalue().splitlines(), [*(step.rstrip("\n") for step in PLAN_STEPS), "['completed', 'completed']", str(list(SERVER_NAMES))])


if __name__ == "__main__":
    unittest.main()

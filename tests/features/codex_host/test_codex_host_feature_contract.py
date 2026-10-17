"""FILE: tests/features/codex_host/test_codex_host_feature_contract.py

PURPOSE: Proves the production bar every one of the twenty-five new CodexHost methods shares: the call guard runs before the input record (not open, another loop, a closed host), the experimental gate refuses the eleven INV-4 functions and any collaboration mode with zero requests while the stable functions still work, every talking function turns a JSON-RPC error into its own CodexErrorMapper packet with exactly one failed call record and no private text in any log, a malformed unmodeled answer becomes a protocol mismatch inside the call, and a dead app-server ends a new call with codex.process_exited.
ROLE IN CODEBASE: Contract layer of the slice-2 tests in tests/features/codex_host/ (docs/spec/codex-host-first-class/spec.md AC-8, AC-34, AC-41, INV-1 to INV-4, INV-6, INV-9, D-3, D-4, EC-1, EC-2, EC-4, NFR-5, NFR-7). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: The guard tables pass a bad argument to every method on purpose: a method that built its record before its guard would raise the record's message, so the guard's own text proves the order (INV-1). The failure table fails only the function's own method, once, with a JSON-RPC internal error (-32603, which _rpc_code maps to codex.api_error), and reads the summary between the packet's head and tail with mapped_summary. Malformed answers are scripted through the fake's feature_answers, so the real openai-codex client and CodexConnection.raw run.
COMMON MODIFICATION PATTERNS: A new talking function adds one row to the failure table and one to _guarded_calls; the completeness checks fail until it does. A new unmodeled method with a required member adds one row to the AC-41 table.
KNOWN EDGE CASES: The experimental gate's {feature} words are not given by the spec, so the gate's message is checked by its fixed head and tail. stream_codex_turn is a plain def whose guard runs at the call, so the guard tables call it inside a coroutine.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-first-class/spec.md sections 6.1, 6.2, 6.3, 8.1 (D-3, D-4) and 9.2; docs/spec/codex-host-first-class/test-plan.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_feature_contract.py
"""

from __future__ import annotations

import asyncio
import types
import unittest
from collections.abc import Awaitable, Callable
from typing import Any

from tests.features.codex_host.codex_host_feature_support import EXPERIMENTAL_FUNCTIONS, FEATURE_METHODS, ITEM_CANARY, OBJECTIVE_CANARY, PROMPT_CANARY
from tests.features.codex_host.codex_host_support import (
    HOST_LOGGER,
    FeatureHostCase,
    assert_no_canary,
    mapped_summary,
    requires_sdk,
    thread_suffix,
)

NOT_OPEN_MESSAGE = "{operation} needs an open CodexHost, and this host is not open: it was never entered, or its async with block already ended. A CodexHost runs its codex app-server only inside 'async with CodexHost(...) as host:', so call {operation} inside that block, or open a new CodexHost."
OTHER_LOOP_MESSAGE = "{operation} was called from another asyncio event loop than the one that opened this CodexHost. The host's turns, watchers and futures belong to that loop, so call {operation} from it, or open a separate CodexHost on this loop."
EXPERIMENTAL_HEAD = "{operation} needs Codex's experimental API for "
EXPERIMENTAL_TAIL = ", but this CodexHost was opened with experimental_api=False. Open the host with CodexClientSettings(experimental_api=True) to use it."
RPC_ERROR_TEXT = "Codex answered {method} with JSON-RPC error {code}: '{message}'."
MISMATCH_TEXT = "Codex's answer to {method} did not match the openai-codex response model."
INTERNAL_ERROR = -32603
# INV-1: the three methods that never talk to Codex.
SILENT_METHODS = frozenset({"stream_codex_turn", "wait_codex_turns", "create_codex_worktree"})
FORK = "<the side chat's fork>"
ITEMS = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": ITEM_CANARY}]}]


async def _stream(host: Any, handle: Any) -> Any:
    """Call the plain-def stream_codex_turn inside a coroutine, so its call-time guard can be awaited like the rest."""
    return host.stream_codex_turn(handle)


def _guarded_calls(host: Any) -> dict[str, Callable[[], Awaitable[Any]]]:
    """Every new method with a bad argument where it takes one: the guard must refuse before the record (INV-1)."""
    return {
        "update_codex_thread_settings": lambda: host.update_codex_thread_settings("", None),
        "list_codex_collaboration_modes": lambda: host.list_codex_collaboration_modes(),
        "run_codex_plan": lambda: host.run_codex_plan(""),
        "stream_codex_turn": lambda: _stream(host, None),
        "wait_codex_turns": lambda: host.wait_codex_turns([]),
        "list_codex_mcp_servers": lambda: host.list_codex_mcp_servers(limit=0),
        "update_codex_turn_settings": lambda: host.update_codex_turn_settings(None),
        "set_codex_thread_memory_mode": lambda: host.set_codex_thread_memory_mode("", None),
        "get_codex_memory_status": lambda: host.get_codex_memory_status(0),
        "reset_codex_memories": lambda: host.reset_codex_memories(),
        "start_codex_side_chat": lambda: host.start_codex_side_chat("", ""),
        "create_codex_worktree": lambda: host.create_codex_worktree("relative", "-x"),
        "pause_codex_goal": lambda: host.pause_codex_goal(""),
        "resume_codex_goal": lambda: host.resume_codex_goal(""),
        "edit_codex_goal": lambda: host.edit_codex_goal(""),
        "clear_codex_goal": lambda: host.clear_codex_goal(""),
        "archive_codex_thread": lambda: host.archive_codex_thread(""),
        "unarchive_codex_thread": lambda: host.unarchive_codex_thread(""),
        "revert_codex_thread": lambda: host.revert_codex_thread("", ""),
        "rename_codex_thread": lambda: host.rename_codex_thread("", ""),
        "inject_codex_items": lambda: host.inject_codex_items("", []),
        "list_codex_background_terminals": lambda: host.list_codex_background_terminals(""),
        "clean_codex_background_terminals": lambda: host.clean_codex_background_terminals(""),
        "search_codex_thread_content": lambda: host.search_codex_thread_content(""),
        "list_codex_child_threads": lambda: host.list_codex_child_threads(""),
    }


class _ContractCase(FeatureHostCase):
    """Shared steps: a seeded idle thread, a seeded thread with a goal, and a running handle on this host."""

    def idle_thread(self) -> str:
        return self.server.seed_thread(completed_turns=2).thread_id

    def goal_thread(self, status: str) -> str:
        thread = self.server.seed_thread(completed_turns=1)
        thread.goal = self.fakes.goal_record(thread.thread_id, f"Ship {OBJECTIVE_CANARY}.", status)
        return thread.thread_id


@requires_sdk
class CodexFeatureGuardTests(_ContractCase):
    """INV-1, EC-1 and EC-2: the guard comes first on every new method."""

    def test_the_guard_table_names_every_new_method(self) -> None:
        self.assertEqual(sorted(_guarded_calls(object())), sorted(FEATURE_METHODS))

    async def test_every_new_method_on_a_host_never_entered_is_refused_as_not_open_before_its_record(self) -> None:
        # EC-1: the not-open text, not a record's message, even though every argument is bad; no client is ever made.
        from vidbyte.harnesses.native.codex import CodexHost
        from vidbyte.lib.errors import ConfigurationError

        idle = CodexHost()
        for name, call in _guarded_calls(idle).items():
            with self.subTest(method=name):
                with self.assertRaises(ConfigurationError) as caught:
                    await self.call(call())
                self.assertEqual(str(caught.exception), NOT_OPEN_MESSAGE.format(operation=name))
        self.assertEqual(self.server.clients_created, 0)

    async def test_every_talking_method_on_a_closed_host_reports_process_exited_and_sends_nothing(self) -> None:
        # EC-1's other half: talks=True and the host closed, so _guard raises codex.process_exited before the record.
        host = await self.opened()
        await self.close_host(host)
        self.remark()
        for name, call in _guarded_calls(host).items():
            if name in SILENT_METHODS:
                continue
            with self.subTest(method=name):
                error = await self.codex_error(call(), "codex.process_exited")
                self.assertEqual(error.operation, name)
        self.assertEqual(self.sent_methods(), [])

    async def test_every_new_method_called_from_another_loop_is_refused_with_the_other_loop_text(self) -> None:
        # EC-2: the loop check is the guard's second step, so a bad argument still never reaches a record.
        from vidbyte.lib.errors import ConfigurationError

        host = await self.opened()
        for name, call in _guarded_calls(host).items():
            with self.subTest(method=name):
                raised = await self.run_in_other_loop(call)
                self.assertIsInstance(raised, ConfigurationError)
                self.assertEqual(str(raised), OTHER_LOOP_MESSAGE.format(operation=name))
        self.assertEqual(self.sent_methods(), [])


@requires_sdk
class CodexFeatureExperimentalGateTests(_ContractCase):
    """AC-8, INV-4 and NFR-5: the experimental gate refuses locally, and the stable functions stay usable."""

    async def test_without_the_experimental_api_the_eleven_functions_and_any_mode_are_refused_with_no_request(self) -> None:
        from vidbyte.lib.dataclasses.codex import CodexClientSettings
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.lib.dataclasses.codex_host_features import CodexThreadSettingsUpdate
        from vidbyte.lib.dataclasses.codex_host_modes import CodexCollaborationMode
        from vidbyte.lib.enums.codex import CodexCollaborationModeKind, CodexMemoryMode, CodexReasoningEffort

        host = await self.opened(CodexClientSettings(experimental_api=False))
        thread_id = self.idle_thread()
        handle = await self.spawn(host)
        self.remark()
        mode = CodexCollaborationMode(mode=CodexCollaborationModeKind.PLAN)
        calls = {
            "update_codex_thread_settings": lambda: host.update_codex_thread_settings(thread_id, CodexThreadSettingsUpdate(effort=CodexReasoningEffort.HIGH)),
            "list_codex_collaboration_modes": lambda: host.list_codex_collaboration_modes(),
            "run_codex_plan": lambda: host.run_codex_plan("Plan the migration."),
            "update_codex_turn_settings": lambda: host.update_codex_turn_settings(handle, effort=CodexReasoningEffort.HIGH),
            "set_codex_thread_memory_mode": lambda: host.set_codex_thread_memory_mode(thread_id, CodexMemoryMode.DISABLED),
            "get_codex_memory_status": lambda: host.get_codex_memory_status(),
            "reset_codex_memories": lambda: host.reset_codex_memories(),
            "list_codex_background_terminals": lambda: host.list_codex_background_terminals(thread_id),
            "clean_codex_background_terminals": lambda: host.clean_codex_background_terminals(thread_id),
            "search_codex_thread_content": lambda: host.search_codex_thread_content("needle"),
            "list_codex_child_threads": lambda: host.list_codex_child_threads(thread_id),
        }
        self.assertEqual(sorted(calls), sorted(EXPERIMENTAL_FUNCTIONS))
        moded = {
            "spawn_codex_thread": lambda: host.spawn_codex_thread(CodexSpawnRequest(prompt="Plan it.", collaboration_mode=mode)),
            "continue_codex_thread": lambda: host.continue_codex_thread(thread_id, "Plan it.", overrides=CodexSpawnRequest(collaboration_mode=mode)),
            "launch_codex_subagents": lambda: host.launch_codex_subagents(["One.", "Two."], request=CodexSpawnRequest(collaboration_mode=mode)),
            "start_codex_side_chat": lambda: host.start_codex_side_chat(thread_id, "Why?", CodexSpawnRequest(collaboration_mode=mode)),
        }
        for name, call in {**calls, **moded}.items():
            with self.subTest(method=name):
                error = await self.refused_locally(call(), "experimental_api")
                self.assertEqual(error.details.get("field"), "experimental_api")
                self.assertTrue(str(error).startswith(EXPERIMENTAL_HEAD.format(operation=name)), str(error))
                self.assertTrue(str(error).endswith(EXPERIMENTAL_TAIL), str(error))

    async def test_without_the_experimental_api_the_stable_functions_still_talk_to_codex(self) -> None:
        # INV-4: the MCP listing, side chat, goals, archive and rename are never gated.
        from vidbyte.lib.dataclasses.codex import CodexClientSettings

        host = await self.opened(CodexClientSettings(experimental_api=False))
        thread_id = self.idle_thread()
        goal_thread = self.goal_thread("active")
        page = await self.call(host.list_codex_mcp_servers())
        self.assertEqual(page.servers, ())
        side = await self.call(host.start_codex_side_chat(thread_id, "Why?"))
        self.assertNotEqual(side.thread_id, thread_id)
        paused = await self.call(host.pause_codex_goal(goal_thread))
        self.assertEqual(paused.status.value, "paused")
        await self.call(host.archive_codex_thread(thread_id))
        await self.call(host.rename_codex_thread(goal_thread, "Release notes"))
        for method in ("mcpServerStatus/list", "thread/fork", "thread/inject_items", "thread/goal/set", "thread/archive", "thread/name/set"):
            with self.subTest(method=method):
                self.assertIn(method, self.sent_methods())


@requires_sdk
class CodexFeatureFailureTests(_ContractCase):
    """AC-34, AC-41, INV-2, INV-3, INV-6, INV-9, D-3 and EC-4: typed failures, one call record each, and private logs."""

    async def failure_rows(self, host: Any) -> list[tuple[str, str, str, Callable[[], Awaitable[Any]]]]:
        """(function, its own method, the thread its error must name or "", call) for each of the 22 talking functions."""
        from vidbyte.lib.dataclasses.codex_host_features import CodexThreadSettingsUpdate
        from vidbyte.lib.enums.codex import CodexMemoryMode, CodexReasoningEffort

        handle = await self.spawn(host)
        threads = {name: self.idle_thread() for name in ("settings", "memory", "side", "archive", "unarchive", "revert", "rename", "inject", "terminals", "clean", "children")}
        goals = {"pause": self.goal_thread("active"), "resume": self.goal_thread("paused"), "edit": self.goal_thread("paused"), "clear": self.goal_thread("paused")}
        revert_point = self.server.threads[threads["revert"]].turns[-1].turn_id
        high = CodexReasoningEffort.HIGH
        return [
            ("update_codex_thread_settings", "thread/settings/update", threads["settings"], lambda: host.update_codex_thread_settings(threads["settings"], CodexThreadSettingsUpdate(effort=high))),
            ("list_codex_collaboration_modes", "collaborationMode/list", "", lambda: host.list_codex_collaboration_modes()),
            ("run_codex_plan", "collaborationMode/list", "", lambda: host.run_codex_plan(f"Plan the {PROMPT_CANARY} migration.")),
            ("list_codex_mcp_servers", "mcpServerStatus/list", "", lambda: host.list_codex_mcp_servers()),
            ("update_codex_turn_settings", "turn/settings/update", handle.thread_id, lambda: host.update_codex_turn_settings(handle, effort=high)),
            ("set_codex_thread_memory_mode", "thread/memoryMode/set", threads["memory"], lambda: host.set_codex_thread_memory_mode(threads["memory"], CodexMemoryMode.DISABLED)),
            ("get_codex_memory_status", "memory/status", "", lambda: host.get_codex_memory_status()),
            ("reset_codex_memories", "memory/reset", "", lambda: host.reset_codex_memories()),
            ("start_codex_side_chat", "thread/inject_items", FORK, lambda: host.start_codex_side_chat(threads["side"], f"Why {PROMPT_CANARY}?")),
            ("pause_codex_goal", "thread/goal/set", goals["pause"], lambda: host.pause_codex_goal(goals["pause"])),
            ("resume_codex_goal", "thread/goal/set", goals["resume"], lambda: host.resume_codex_goal(goals["resume"])),
            ("edit_codex_goal", "thread/goal/set", goals["edit"], lambda: host.edit_codex_goal(goals["edit"], objective=f"Ship {OBJECTIVE_CANARY} now.")),
            ("clear_codex_goal", "thread/goal/clear", goals["clear"], lambda: host.clear_codex_goal(goals["clear"])),
            ("archive_codex_thread", "thread/archive", threads["archive"], lambda: host.archive_codex_thread(threads["archive"])),
            ("unarchive_codex_thread", "thread/unarchive", threads["unarchive"], lambda: host.unarchive_codex_thread(threads["unarchive"])),
            ("revert_codex_thread", "thread/revert", threads["revert"], lambda: host.revert_codex_thread(threads["revert"], revert_point)),
            ("rename_codex_thread", "thread/name/set", threads["rename"], lambda: host.rename_codex_thread(threads["rename"], "Release notes")),
            ("inject_codex_items", "thread/inject_items", threads["inject"], lambda: host.inject_codex_items(threads["inject"], ITEMS)),
            ("list_codex_background_terminals", "thread/backgroundTerminals/list", threads["terminals"], lambda: host.list_codex_background_terminals(threads["terminals"])),
            ("clean_codex_background_terminals", "thread/backgroundTerminals/clean", threads["clean"], lambda: host.clean_codex_background_terminals(threads["clean"])),
            ("search_codex_thread_content", "thread/search", "", lambda: host.search_codex_thread_content("needle")),
            ("list_codex_child_threads", "thread/list", threads["children"], lambda: host.list_codex_child_threads(threads["children"])),
        ]

    async def test_a_json_rpc_error_on_each_functions_own_method_is_its_own_packet_with_one_failed_call_record(self) -> None:
        # AC-34, INV-2, INV-3: the head names the function (run_codex_plan relabels), the tail names the thread when known.
        records = self.capture_logs(HOST_LOGGER)
        host = await self.opened()
        rows = await self.failure_rows(host)
        self.assertEqual(sorted(row[0] for row in rows), sorted(set(FEATURE_METHODS) - SILENT_METHODS))
        for name, method, thread_id, call in rows:
            with self.subTest(function=name):
                start = len(records)
                message = f"{method} store failed"
                self.server.fail(method, self.fakes.FakeRpcError(INTERNAL_ERROR, message), times=1)
                error = await self.codex_error(call(), "codex.api_error")
                named = list(self.server.threads)[-1] if thread_id == FORK else thread_id
                self.assertEqual((error.operation, error.thread_id), (name, named))
                suffix = thread_suffix(named) if named else ""
                self.assertEqual(mapped_summary(self, error), RPC_ERROR_TEXT.format(method=method, code=INTERNAL_ERROR, message=message) + suffix)
                failed = self.call_records(records[start:], "codex_host_call_failed", method)
                self.assertEqual(len(failed), 1, failed)
                self.assertEqual(failed[0]["failure_code"], "codex.api_error")
        # INV-9, NFR-7: prompts, objectives and injected items reach no log record, failed or not.
        self.assertTrue(records)
        assert_no_canary(self, [record.getMessage() for record in records], (PROMPT_CANARY, OBJECTIVE_CANARY, ITEM_CANARY))

    async def test_an_unmodeled_answer_missing_a_member_or_with_a_wrong_type_is_a_protocol_mismatch_inside_the_call(self) -> None:
        # AC-41, INV-6, D-4: the translator runs on the worker, so the call record itself fails with ConfigurationError.
        from vidbyte.lib.enums.codex import CodexReasoningEffort

        records = self.capture_logs(HOST_LOGGER)
        host = await self.opened()
        handle = await self.spawn(host)
        thread_id = self.idle_thread()
        rows = (
            ("list_codex_collaboration_modes", "collaborationMode/list", {"data": [{"mode": "plan"}]}, "", lambda: host.list_codex_collaboration_modes()),
            ("update_codex_turn_settings", "turn/settings/update", {"status": 7}, handle.thread_id, lambda: host.update_codex_turn_settings(handle, effort=CodexReasoningEffort.HIGH)),
            ("get_codex_memory_status", "memory/status", {"v2ConsolidatedThreads": "three", "v2Ready": True}, "", lambda: host.get_codex_memory_status()),
            ("list_codex_background_terminals", "thread/backgroundTerminals/list", {"data": [{"itemId": "item-1"}], "nextCursor": None}, thread_id, lambda: host.list_codex_background_terminals(thread_id)),
            ("search_codex_thread_content", "thread/search", {"data": [{"snippet": "x"}], "nextCursor": None, "backwardsCursor": None}, "", lambda: host.search_codex_thread_content("needle")),
        )
        for name, method, answer, named, call in rows:
            with self.subTest(function=name):
                start = len(records)
                self.server.feature_answers[method] = answer
                error = await self.codex_error(call(), "codex.protocol_mismatch")
                del self.server.feature_answers[method]
                self.assertEqual(error.operation, name)
                self.assertEqual(mapped_summary(self, error), MISMATCH_TEXT.format(method=method) + (thread_suffix(named) if named else ""))
                failed = self.call_records(records[start:], "codex_host_call_failed", method)
                self.assertEqual([(row["failure_code"], row["error_type"]) for row in failed], [("codex.protocol_mismatch", "ConfigurationError")])
                self.assertEqual(self.call_records(records[start:], "codex_host_call", method), [])

    async def test_an_app_server_that_dies_during_a_new_call_ends_it_with_process_exited_naming_the_thread(self) -> None:
        # EC-4: from_exception with dead=True; the next talking call is refused by the guard and sends nothing.
        from vidbyte.lib.dataclasses.codex_host_features import CodexThreadSettingsUpdate
        from vidbyte.lib.enums.codex import CodexReasoningEffort

        host = await self.opened()
        thread_id = self.idle_thread()
        held = self.server.hold("thread/settings/update")
        task = asyncio.ensure_future(host.update_codex_thread_settings(thread_id, CodexThreadSettingsUpdate(effort=CodexReasoningEffort.HIGH)))
        await asyncio.to_thread(held.wait_arrived)
        self.server.die("the app-server stopped")
        error = await self.codex_error(task, "codex.process_exited")
        self.assertEqual((error.operation, error.thread_id), ("update_codex_thread_settings", thread_id))
        sent = len(self.server.requests)
        await self.codex_error(host.archive_codex_thread(thread_id), "codex.process_exited")
        self.assertEqual(len(self.server.requests), sent)


@requires_sdk
class CodexJsonObjectResponseTests(unittest.TestCase):
    """D-3: the passthrough response class hands the translator a read-only copy of the JSON object."""

    def test_model_validate_returns_a_read_only_copy_of_the_answer(self) -> None:
        from vidbyte.harnesses.native.codex.connection import CodexJsonObjectResponse

        answer = {"status": "applied"}
        validated = CodexJsonObjectResponse.model_validate(answer)
        self.assertIsInstance(validated, types.MappingProxyType)
        self.assertEqual(dict(validated), {"status": "applied"})
        answer["status"] = "changed"
        self.assertEqual(validated["status"], "applied")
        with self.assertRaises(TypeError):
            validated["status"] = "edited"  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()

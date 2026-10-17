"""FILE: tests/features/codex_host/test_codex_host_settings_modes.py

PURPOSE: Proves the slice-2 settings and plan-mode functions over the in-memory app-server: update_codex_thread_settings sending exactly the fields that were set after its model check, existence read and load guard; list_codex_collaboration_modes reading Codex's presets; a collaboration mode reaching turn/start with the model Codex resolved and pricing the turn as the mode's model; every call that cannot send a mode refusing it locally; run_codex_plan listing the presets and spawning one plan turn whose plan item is its answer; final_answer's plan fallback; and update_codex_turn_settings acting only on a running turn this host owns, through a goal run's current physical turn.
ROLE IN CODEBASE: Settings layer of the slice-2 tests in tests/features/codex_host/ (docs/spec/codex-host-first-class/spec.md AC-2, AC-3, AC-5, AC-7, AC-9 to AC-11, AC-20, INV-11 to INV-17, INV-25, INV-55, NFR-10, EC-5, EC-8 to EC-14, EC-16, EC-23 to EC-25). Every class but the final-answer one needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: Each test opens a real CodexHost against FakeAppServer through FeatureHostCase, which keeps a request window per test (remark / sent / sent_methods). The fake answers the new methods from codex_host_feature_fakes.FeatureHandlers; a model change Codex reports is scripted with before_response on thread/start. Turn pricing is checked against priced_cost, the repo's own pricing tracker, and packets whose cause and next step the spec overrides are checked whole with assert_packet.
COMMON MODIFICATION PATTERNS: Add a row to the INV-11 wire table when CodexThreadSettingsUpdate gains a field. Add a refusal row to the AC-7 table when another call gains a CODEX_HOST_REJECTED_FIELDS row that names collaboration_mode.
KNOWN EDGE CASES: The model check reads every model/list page only when a model or tier is named, so the AC-2 order filters model/list out and checks it came first. A goal run's current physical turn is read from the SDK goal state, which the reader thread updates before it reads the next answer, so a read_codex_thread call is the barrier after a scripted turn/completed or turn/started. The effort CodexReasoningEffort lacks is "hyper": "ultra" is a member since 0.163.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-first-class/spec.md sections 6.1, 6.2, 6.3, 9.2 and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_settings_modes.py
"""

from __future__ import annotations

import os
import unittest
from typing import Any

from tests.features.codex_host.codex_host_feature_support import (
    LOAD_GOAL_UNFINISHED_CAUSE,
    LOAD_GOAL_UNFINISHED_MESSAGE,
    LOAD_GOAL_UNFINISHED_NEXT_STEP,
    MODE_MODEL_MISSING_CAUSE,
    MODE_MODEL_MISSING_MESSAGE,
    MODE_MODEL_MISSING_NEXT_STEP,
    NO_PLAN_MODE_MESSAGE,
    TURN_SETTINGS_FINISHED_MESSAGE,
    assert_packet,
    priced_cost,
)
from tests.features.codex_host.codex_host_support import (
    DEFAULT_ANSWERS,
    GOAL_FIELD_MESSAGE,
    GOAL_RUN_OWNER,
    GOAL_SPAWN_OWNER,
    UNREGISTERED_TOOL_TEXT,
    USER_REVIEWER_TEXT,
    FeatureHostCase,
    input_texts,
    make_echo_tool,
    mapped_summary,
    requires_sdk,
    thread_suffix,
)

UPDATE = "update_codex_thread_settings"
TURN_UPDATE = "update_codex_turn_settings"
EXTRA_ROOT = os.path.abspath(os.path.join(os.sep, "extra-root"))
OTHER_CWD = os.path.abspath(os.path.join(os.sep, "other-workspace"))
# The model a scripted thread/start reports instead of the one asked for; the fake prices it differently from gpt-5.5.
MINI = "gpt-5.4-mini"
RPC_ERROR_TEXT = "Codex answered {method} with JSON-RPC error {code}: '{message}'."
MISMATCH_TEXT = "Codex's answer to {method} did not match the openai-codex response model."
PLAN_TEXT = "1. Move the tables. 2. Switch the reads."


def _update(**fields: Any) -> Any:
    from vidbyte.lib.dataclasses.codex_host_features import CodexThreadSettingsUpdate

    return CodexThreadSettingsUpdate(**fields)


def _mode(kind: str, **fields: Any) -> Any:
    from vidbyte.lib.dataclasses.codex_host_modes import CodexCollaborationMode
    from vidbyte.lib.enums.codex import CodexCollaborationModeKind

    return CodexCollaborationMode(mode=CodexCollaborationModeKind(kind), **fields)


async def _decline(request: Any) -> Any:
    """An approval handler that declines everything; these tests only need a host that has one."""
    from vidbyte.lib.dataclasses.codex_host import CodexServerAnswer
    from vidbyte.lib.enums.codex import CodexApprovalDecision

    return CodexServerAnswer(decision=CodexApprovalDecision.DECLINE)


class _SettingsCase(FeatureHostCase):
    """Shared steps: a scripted thread/start model, the last turn/start params, and a finished priced turn."""

    def report_model(self, model: str) -> None:
        # Codex resolves the thread's model itself; the next thread/start reports this one instead of the one asked for.
        def action(params: dict[str, Any], result: Any) -> list[Any]:
            result["model"] = model
            result["thread"]["model"] = model
            self.server.threads[result["thread"]["id"]].model = model
            return []

        self.server.before_response("thread/start", action)

    def list_model(self, model: str) -> None:
        self.server.model_pages[0].append(self.fakes._model(model, model))

    def last_turn_start(self) -> dict[str, Any]:
        return self.server.matching("turn/start")[-1].params

    async def finish_priced(self, host: Any, handle: Any) -> float:
        """Complete the turn with 1000 input and 200 output tokens and return the thread's priced cost."""
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="Done.", usage=self.fakes.token_usage((1000, 200), (1000, 200)))
        await self.wait_done(host, handle)
        usage = await self.call(host.track_codex_thread_usage(handle.thread_id))
        return float(usage.cost_usd)


@requires_sdk
class CodexThreadSettingsUpdateHostTests(_SettingsCase):
    """AC-2, AC-3, INV-11, INV-12, EC-5, EC-8, EC-9 and EC-10."""

    async def test_an_update_sends_one_settings_call_holding_only_the_fields_that_were_set(self) -> None:
        # AC-2: model, effort, a cleared tier and cleared plugins; nothing else is a setting key.
        from vidbyte.lib.enums.codex import CodexReasoningEffort

        records = self.capture_logs()
        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        settings = _update(model="gpt-5.5", effort=CodexReasoningEffort.HIGH, clear_service_tier=True, disabled_plugin_ids=())
        self.assertIsNone(await self.call(host.update_codex_thread_settings(thread.thread_id, settings)))
        methods = self.sent_methods()
        self.assertEqual([method for method in methods if method != "model/list"], ["thread/read", "thread/settings/update"])
        self.assertTrue(all(index < methods.index("thread/read") for index, method in enumerate(methods) if method == "model/list"), methods)
        updates = self.server.matching("thread/settings/update")
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].params, {"threadId": thread.thread_id, "model": "gpt-5.5", "effort": "high", "serviceTier": None, "disabledPluginIds": []})
        calls = self.call_records(records, "codex_host_call", "thread/settings/update")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["operation"], UPDATE)
        self.assertEqual(self.call_records(records, "codex_host_call_failed", "thread/settings/update"), [])

    async def test_each_other_setting_reaches_its_own_wire_key_and_nothing_else_is_sent(self) -> None:
        # INV-11: every field reaches the wire, or the record refuses it (INV-10).
        from vidbyte.lib.enums.codex import CodexApprovalPolicy, CodexApprovalsReviewer, CodexReasoningEffort, CodexReasoningSummary

        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        rows: tuple[tuple[str, dict[str, Any], dict[str, Any]], ...] = (
            ("summary", {"summary": CodexReasoningSummary.CONCISE}, {"summary": "concise"}),
            ("cwd", {"cwd": OTHER_CWD}, {"cwd": OTHER_CWD}),
            ("approvals", {"approval_policy": CodexApprovalPolicy.ON_REQUEST, "approvals_reviewer": CodexApprovalsReviewer.AUTO_REVIEW}, {"approvalPolicy": "on-request", "approvalsReviewer": "auto_review"}),
            ("service tier", {"model": "gpt-5.5", "service_tier": "flex"}, {"model": "gpt-5.5", "serviceTier": "flex"}),
            ("plugins", {"disabled_plugin_ids": ("github",)}, {"disabledPluginIds": ["github"]}),
            ("mode with its own model", {"collaboration_mode": _mode("plan", model="gpt-5.5", reasoning_effort=CodexReasoningEffort.HIGH)}, {"collaborationMode": {"mode": "plan", "settings": {"model": "gpt-5.5", "reasoning_effort": "high"}}}),
            ("mode taking the update's model", {"model": "gpt-5.5", "collaboration_mode": _mode("default")}, {"model": "gpt-5.5", "collaborationMode": {"mode": "default", "settings": {"model": "gpt-5.5"}}}),
        )
        for label, fields, wire in rows:
            with self.subTest(row=label):
                self.remark()
                self.assertIsNone(await self.call(host.update_codex_thread_settings(thread.thread_id, _update(**fields))))
                updates = [request for request in self.sent() if request.method == "thread/settings/update"]
                self.assertEqual(len(updates), 1)
                self.assertEqual(updates[0].params, {"threadId": thread.thread_id, **wire})

    async def test_the_sandbox_policy_is_built_exactly_as_a_turn_builds_it(self) -> None:
        # INV-11: sandboxPolicy is CodexParamsTranslator.sandbox_policy, so a turn/start with the same posture is the oracle.
        from vidbyte.lib.dataclasses.codex import CodexTurnSettings
        from vidbyte.lib.enums.codex import CodexSandbox

        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        rows = (
            (CodexSandbox.WORKSPACE_WRITE, {"network_access": True, "writable_roots": (EXTRA_ROOT,)}),
            (CodexSandbox.READ_ONLY, {"network_access": False}),
            (CodexSandbox.READ_ONLY, {}),
        )
        for sandbox, access in rows:
            with self.subTest(sandbox=sandbox.value, access=sorted(access)):
                await self.spawn(host, turn=CodexTurnSettings(sandbox=sandbox), **access)
                oracle = self.last_turn_start()["sandboxPolicy"]
                self.remark()
                await self.call(host.update_codex_thread_settings(thread.thread_id, _update(sandbox=sandbox, **access)))
                self.assertEqual(self.server.matching("thread/settings/update")[-1].params, {"threadId": thread.thread_id, "sandboxPolicy": oracle})

    async def test_a_running_turn_keeps_running_while_its_thread_settings_change(self) -> None:
        # EC-5, INV-12: a thread with a running turn is not refused and not reserved; Codex applies the change to later turns.
        from vidbyte.lib.enums.codex import CodexReasoningEffort

        host = await self.opened()
        handle = await self.spawn(host)
        self.remark()
        self.assertIsNone(await self.call(host.update_codex_thread_settings(handle.thread_id, _update(effort=CodexReasoningEffort.HIGH))))
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/settings/update"])
        self.assertEqual((await self.call(host.get_codex_turn_result(handle))).status.value, "inProgress")
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="Done.")
        self.assertEqual((await self.wait_done(host, handle)).status.value, "completed")

    async def test_a_not_loaded_thread_with_an_active_goal_is_refused_before_any_resume(self) -> None:
        # AC-3, INV-12, D-14: the load guard reads the goal and stops before thread/resume.
        from vidbyte.lib.enums.codex import CodexReasoningEffort

        thread = self.server.seed_thread(completed_turns=1)
        thread.status = "notLoaded"
        thread.goal = self.fakes.goal_record(thread.thread_id, "Ship the fix.", "active")
        host = await self.opened()
        error = await self.codex_error(host.update_codex_thread_settings(thread.thread_id, _update(effort=CodexReasoningEffort.HIGH)), "codex.goal_unfinished")
        assert_packet(
            self,
            error,
            operation=UPDATE,
            code="codex.goal_unfinished",
            message=LOAD_GOAL_UNFINISHED_MESSAGE.format(status="active", operation=UPDATE),
            cause=LOAD_GOAL_UNFINISHED_CAUSE.format(operation=UPDATE),
            next_step=LOAD_GOAL_UNFINISHED_NEXT_STEP,
            thread_id=thread.thread_id,
        )
        self.assertEqual(self.sent_methods(), ["thread/read", "thread/goal/get"])
        self.assertEqual(thread.status, "notLoaded")

    async def test_an_unknown_model_is_refused_before_the_thread_is_read(self) -> None:
        # EC-8: preflight's model check refuses a model Codex does not list, and no update is sent.
        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        error = await self.codex_error(host.update_codex_thread_settings(thread.thread_id, _update(model="gpt-unlisted")), "codex.model_unknown")
        self.assertEqual(error.operation, UPDATE)
        self.assertEqual(set(self.sent_methods()), {"model/list"})

    async def test_a_user_reviewer_is_refused_locally_on_a_host_without_an_approval_handler(self) -> None:
        # EC-9, INV-12: reject_user_reviewer runs on the update's CodexSpawnRequest view, before any request.
        from vidbyte.lib.enums.codex import CodexApprovalsReviewer

        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened()
        error = await self.codex_error(host.update_codex_thread_settings(thread.thread_id, _update(approvals_reviewer=CodexApprovalsReviewer.USER)), "configuration.unsupported_combination")
        self.assertEqual(error.operation, UPDATE)
        self.assertEqual(error.next_step, USER_REVIEWER_TEXT)
        self.assertEqual(self.sent_methods(), [])

    async def test_a_user_reviewer_is_sent_when_the_host_has_an_approval_handler(self) -> None:
        # EC-9's other side: with a handler, the user reviewer reaches the wire.
        from vidbyte.lib.enums.codex import CodexApprovalsReviewer

        thread = self.server.seed_thread(completed_turns=1)
        host = await self.opened(approval_handler=_decline)
        await self.call(host.update_codex_thread_settings(thread.thread_id, _update(approvals_reviewer=CodexApprovalsReviewer.USER)))
        self.assertEqual(self.server.matching("thread/settings/update")[-1].params, {"threadId": thread.thread_id, "approvalsReviewer": "user"})

    async def test_codex_refusing_the_update_is_an_api_error_with_codexs_own_message(self) -> None:
        # EC-10, INV-2: -32600 is mapped by _rpc_code to codex.api_error, naming the thread.
        from vidbyte.lib.enums.codex import CodexReasoningEffort

        thread = self.server.seed_thread(completed_turns=1)
        self.server.fail("thread/settings/update", self.fakes.FakeRpcError(-32600, "permissions are set elsewhere"))
        host = await self.opened()
        error = await self.codex_error(host.update_codex_thread_settings(thread.thread_id, _update(effort=CodexReasoningEffort.HIGH)), "codex.api_error")
        self.assertEqual(error.operation, UPDATE)
        expected = RPC_ERROR_TEXT.format(method="thread/settings/update", code=-32600, message="permissions are set elsewhere")
        self.assertEqual(mapped_summary(self, error), expected + thread_suffix(thread.thread_id))

    async def test_an_unknown_thread_is_refused_by_its_existence_read(self) -> None:
        # INV-12 "Existence": one thread/read, then nothing.
        from vidbyte.lib.enums.codex import CodexReasoningEffort

        host = await self.opened()
        error = await self.codex_error(host.update_codex_thread_settings("thr-never", _update(effort=CodexReasoningEffort.HIGH)), "codex.session_not_found")
        self.assertEqual(error.operation, UPDATE)
        self.assertEqual(self.sent_methods(), ["thread/read"])


@requires_sdk
class CodexCollaborationModeListHostTests(_SettingsCase):
    """AC-9 and INV-15: the presets Codex lists, in its order, and malformed answers."""

    async def test_the_presets_come_back_in_codex_order_with_nulls_read_as_blank(self) -> None:
        from vidbyte.lib.dataclasses.codex_host_modes import CodexCollaborationModePreset
        from vidbyte.lib.enums.codex import CodexCollaborationModeKind

        self.server.collaboration_modes = [
            {"name": "Plan", "mode": "plan", "model": None, "reasoning_effort": "medium"},
            {"name": "Pair", "mode": None, "model": "gpt-5.5", "reasoning_effort": "hyper"},
        ]
        host = await self.opened()
        presets = await self.call(host.list_codex_collaboration_modes())
        self.assertEqual(
            presets,
            (
                CodexCollaborationModePreset(name="Plan", mode=CodexCollaborationModeKind.PLAN, model="", reasoning_effort="medium"),
                CodexCollaborationModePreset(name="Pair", mode=CodexCollaborationModeKind.NONE, model="gpt-5.5", reasoning_effort="hyper"),
            ),
        )
        self.assertIs(presets[0].mode, CodexCollaborationModeKind.PLAN)
        self.assertEqual(self.sent_methods(), ["collaborationMode/list"])

    async def test_a_malformed_preset_answer_is_a_protocol_mismatch_naming_the_method(self) -> None:
        # AC-9, INV-6: the translator reads with .get only, so no KeyError or TypeError reaches the caller.
        host = await self.opened()
        for label, answer in (("data not a list", {"data": "nope"}), ("item without a name", {"data": [{"mode": "plan"}]}), ("no data", {})):
            with self.subTest(answer=label):
                self.server.feature_answers["collaborationMode/list"] = answer
                error = await self.codex_error(host.list_codex_collaboration_modes(), "codex.protocol_mismatch")
                self.assertEqual(error.operation, "list_codex_collaboration_modes")
                self.assertEqual(mapped_summary(self, error), MISMATCH_TEXT.format(method="collaborationMode/list"))


@requires_sdk
class CodexCollaborationModeTurnHostTests(_SettingsCase):
    """AC-5, INV-13, NFR-10 and EC-14: the mode on turn/start, its model, and the turn's price."""

    async def test_a_plan_mode_spawn_sends_the_model_codex_resolved_and_is_priced_as_it(self) -> None:
        # AC-5: no mode model and no turn model, so settings.model is what thread/start reported; no developer_instructions or effort.
        self.report_model(MINI)
        host = await self.opened()
        handle = await self.spawn(host, collaboration_mode=_mode("plan"))
        self.assertEqual(self.last_turn_start()["collaborationMode"], {"mode": "plan", "settings": {"model": MINI}})
        expected = priced_cost(MINI, ((1000, 200),))
        self.assertGreater(expected, 0)
        self.assertNotAlmostEqual(expected, priced_cost("gpt-5.5", ((1000, 200),)), places=9)
        self.assertAlmostEqual(await self.finish_priced(host, handle), expected, places=12)

    async def test_the_mode_settings_take_the_first_model_set_and_any_named_effort(self) -> None:
        # INV-13: mode.model, then turn.model, then the thread's resolved model; reasoning_effort only when one is named.
        from vidbyte.lib.dataclasses.codex import CodexTurnSettings
        from vidbyte.lib.enums.codex import CodexReasoningEffort

        self.list_model(MINI)
        host = await self.opened()
        await self.spawn(host, turn=CodexTurnSettings(model="gpt-5.5", effort=CodexReasoningEffort.LOW), collaboration_mode=_mode("default"))
        self.assertEqual(self.last_turn_start()["collaborationMode"], {"mode": "default", "settings": {"model": "gpt-5.5", "reasoning_effort": "low"}})
        await self.spawn(host, collaboration_mode=_mode("plan", reasoning_effort=CodexReasoningEffort.HIGH))
        self.assertEqual(self.last_turn_start()["collaborationMode"], {"mode": "plan", "settings": {"model": "gpt-5.5", "reasoning_effort": "high"}})
        # NFR-10: a request without a mode sends no collaborationMode key at all.
        await self.spawn(host, turn=CodexTurnSettings(model="gpt-5.5", effort=CodexReasoningEffort.LOW))
        self.assertNotIn("collaborationMode", self.last_turn_start())

    async def test_a_mode_model_is_checked_by_preflight_and_prices_the_turn(self) -> None:
        # INV-13 pricing: turn_model is mode.model or turn.model, so a mode model on a gpt-5.5 thread prices the turn as the mode's model.
        self.list_model(MINI)
        host = await self.opened()
        handle = await self.spawn(host, collaboration_mode=_mode("plan", model=MINI))
        methods = self.sent_methods()
        self.assertIn("model/list", methods)
        self.assertLess(methods.index("model/list"), methods.index("thread/start"))
        self.assertEqual(self.server.threads[handle.thread_id].model, "gpt-5.5")
        self.assertEqual(self.last_turn_start()["collaborationMode"], {"mode": "plan", "settings": {"model": MINI}})
        self.assertAlmostEqual(await self.finish_priced(host, handle), priced_cost(MINI, ((1000, 200),)), places=12)

    async def test_a_mode_model_codex_does_not_list_is_refused_before_the_thread_starts(self) -> None:
        # INV-12 and section 9.2 "preflight": the mode's model goes through the same model check as the turn's.
        host = await self.opened()
        error = await self.codex_error(self.spawn(host, collaboration_mode=_mode("plan", model="gpt-unlisted")), "codex.model_unknown")
        self.assertEqual(error.operation, "spawn_codex_thread")
        self.assertEqual(self.count("thread/start"), 0)

    async def test_a_mode_turn_on_a_thread_without_a_reported_model_is_refused_before_turn_start(self) -> None:
        # EC-14, INV-13: the schema requires settings.model, so start_turn refuses and spawn releases the thread's tools.
        self.report_model("")
        host = await self.opened()
        error = await self.codex_error(self.spawn(host, collaboration_mode=_mode("plan"), tools=(make_echo_tool(),)), "codex.protocol_mismatch")
        thread_id = list(self.server.threads)[-1]
        assert_packet(
            self,
            error,
            operation="spawn_codex_thread",
            code="codex.protocol_mismatch",
            message=MODE_MODEL_MISSING_MESSAGE,
            cause=MODE_MODEL_MISSING_CAUSE,
            next_step=MODE_MODEL_MISSING_NEXT_STEP,
            thread_id=thread_id,
        )
        self.assertEqual(self.count("turn/start"), 0)
        answer = await self.ask("item/tool/call", {"threadId": thread_id, "turnId": "turn-x", "callId": "call-1", "tool": "echo_text", "arguments": {"text": "hi"}})
        self.assertEqual(answer, {"success": False, "contentItems": [{"type": "inputText", "text": UNREGISTERED_TOOL_TEXT}]})
        self.assertIsNone(host._registry.usage(thread_id))
        self.assertFalse(host._registry.busy(thread_id))


@requires_sdk
class CodexModeRefusalHostTests(_SettingsCase):
    """AC-7, INV-10: every call that cannot send a collaboration mode refuses it locally, with zero requests."""

    async def test_every_call_that_cannot_send_a_mode_refuses_it_before_any_request(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexGoal, CodexReviewTarget, CodexSpawnRequest
        from vidbyte.lib.enums.codex import CodexReviewTargetKind
        from vidbyte.lib.errors import ConfigurationError

        stored = self.server.seed_thread(completed_turns=1)
        paused = self.server.seed_thread(completed_turns=1)
        paused.goal = self.fakes.goal_record(paused.thread_id, "Ship the fix.", "paused")
        host = await self.opened()
        with_mode = CodexSpawnRequest(collaboration_mode=_mode("plan"))
        target = CodexReviewTarget(kind=CodexReviewTargetKind.COMMIT, sha="0a1b2c3")
        rows = (
            ("fork_codex_thread", lambda: host.fork_codex_thread(stored.thread_id, overrides=with_mode)),
            ("start_codex_review", lambda: host.start_codex_review(stored.thread_id, target, request=with_mode)),
            ("run_codex_goal", lambda: host.run_codex_goal("Ship the fix.", request=with_mode)),
            ("run_codex_plan", lambda: host.run_codex_plan("Plan the fix.", request=with_mode)),
            ("resume_codex_goal", lambda: host.resume_codex_goal(paused.thread_id, request=with_mode)),
        )
        for label, call in rows:
            with self.subTest(call=label):
                error = await self.refused_locally(call(), "collaboration_mode")
                if label == "run_codex_goal":
                    self.assertEqual(str(error), GOAL_FIELD_MESSAGE.format(owner=GOAL_RUN_OWNER, name="collaboration_mode"))
        # A goal spawn request cannot even be built with a mode.
        with self.assertRaises(ConfigurationError) as caught:
            CodexSpawnRequest(goal=CodexGoal(objective="Ship the fix."), collaboration_mode=_mode("plan"))
        self.assertEqual(str(caught.exception), GOAL_FIELD_MESSAGE.format(owner=GOAL_SPAWN_OWNER, name="collaboration_mode"))
        self.assertEqual(self.sent_methods(), [])


@requires_sdk
class CodexPlanRunHostTests(_SettingsCase):
    """AC-10, AC-11, INV-16, INV-55, EC-11 to EC-13 and EC-16: run_codex_plan over Codex's own plan preset."""

    async def test_a_plan_run_lists_the_presets_then_spawns_one_plan_turn_whose_plan_is_the_answer(self) -> None:
        # AC-10, INV-17: the preset's effort and the thread's model fill the mode; a plan-only turn answers with its plan.
        host = await self.opened()
        handle = await self.call(host.run_codex_plan("Plan the migration."))
        self.assertEqual(self.sent_methods(), ["collaborationMode/list", "account/read", "account/rateLimits/read", "thread/start", "turn/start"])
        turn_start = self.last_turn_start()
        self.assertEqual(turn_start["collaborationMode"], {"mode": "plan", "settings": {"model": "gpt-5.5", "reasoning_effort": "medium"}})
        self.assertEqual(input_texts(turn_start), [("text", "Plan the migration.")])
        self.assertEqual(handle.thread_id, turn_start["threadId"])
        turn = self.server.threads[handle.thread_id].find_turn(handle.turn_id)
        plan = self.server.plan_item(PLAN_TEXT)
        turn.items.append(plan)
        self.server.emit([self.server.item_note(handle.thread_id, handle.turn_id, plan), *self.server.completion_notes(handle.thread_id, handle.turn_id, final=None)])
        snapshot = await self.wait_done(host, handle)
        self.assertEqual(snapshot.status.value, "completed")
        self.assertEqual(snapshot.result.final_response, PLAN_TEXT)

    async def test_a_plan_question_on_a_host_without_a_handler_gets_slice_ones_empty_answer(self) -> None:
        # EC-16, INV-55: plan-mode questions are not special-cased; with no approval_handler the fail-closed answer is sent.
        host = await self.opened()
        handle = await self.call(host.run_codex_plan("Plan the migration."))
        question = {"id": "q1", "header": "Scope", "question": "Should the plan cover the CLI too?"}
        answer = await self.ask("item/tool/requestUserInput", {"threadId": handle.thread_id, "turnId": handle.turn_id, "itemId": "item-q", "questions": [question]})
        self.assertEqual(answer, DEFAULT_ANSWERS["item/tool/requestUserInput"])

    async def test_a_preset_list_without_a_plan_mode_spawns_nothing(self) -> None:
        # AC-11: codex.protocol_mismatch with the no-plan message, and no thread/start.
        self.server.collaboration_modes = [{"name": "Default", "mode": "default", "model": None, "reasoning_effort": None}]
        host = await self.opened()
        error = await self.codex_error(host.run_codex_plan("Plan the migration."), "codex.protocol_mismatch")
        self.assertEqual(error.operation, "run_codex_plan")
        self.assertEqual(mapped_summary(self, error), NO_PLAN_MODE_MESSAGE)
        self.assertEqual(self.sent_methods(), ["collaborationMode/list"])

    async def test_a_cli_without_the_preset_list_is_relabelled_as_the_plan_run(self) -> None:
        # EC-11: -32601 is malformed, so codex.protocol_mismatch; run_codex_plan relabels it and spawns nothing.
        self.server.fail("collaborationMode/list", self.fakes.FakeRpcError(-32601, "method not found: collaborationMode/list"))
        host = await self.opened()
        listed = await self.codex_error(host.list_codex_collaboration_modes(), "codex.protocol_mismatch")
        self.assertEqual(listed.operation, "list_codex_collaboration_modes")
        error = await self.codex_error(host.run_codex_plan("Plan the migration."), "codex.protocol_mismatch")
        self.assertEqual(error.operation, "run_codex_plan")
        self.assertTrue(error.message.startswith("run_codex_plan failed with codex.protocol_mismatch. "), error.message)
        self.assertIn("collaborationMode/list", error.message)
        self.assertEqual(self.count("thread/start"), 0)

    async def test_the_callers_turn_model_and_effort_win_over_the_preset(self) -> None:
        # EC-13, INV-16 step 5: from_preset leaves the mode's model and effort empty where the turn sets them.
        from vidbyte.lib.dataclasses.codex import CodexTurnSettings
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.lib.enums.codex import CodexReasoningEffort

        self.server.collaboration_modes = [{"name": "Plan", "mode": "plan", "model": MINI, "reasoning_effort": "medium"}]
        host = await self.opened()
        request = CodexSpawnRequest(turn=CodexTurnSettings(model="gpt-5.5", effort=CodexReasoningEffort.HIGH))
        await self.call(host.run_codex_plan("Plan the migration.", request))
        self.assertEqual(self.last_turn_start()["collaborationMode"], {"mode": "plan", "settings": {"model": "gpt-5.5", "reasoning_effort": "high"}})

    async def test_a_preset_effort_vidbyte_lacks_leaves_the_effort_to_codex(self) -> None:
        # EC-12: the preset keeps its text, from_preset uses PROVIDER_DEFAULT, and the plan runs without reasoning_effort.
        self.server.collaboration_modes = [{"name": "Plan", "mode": "plan", "model": None, "reasoning_effort": "hyper"}]
        host = await self.opened()
        await self.call(host.run_codex_plan("Plan the migration."))
        self.assertEqual(self.last_turn_start()["collaborationMode"], {"mode": "plan", "settings": {"model": "gpt-5.5"}})

    async def test_a_user_reviewer_is_refused_before_the_presets_are_listed(self) -> None:
        # INV-16 order: the record, the gate, then the reviewer check, all before collaborationMode/list.
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.lib.enums.codex import CodexApprovalsReviewer

        host = await self.opened()
        request = CodexSpawnRequest(approvals_reviewer=CodexApprovalsReviewer.USER)
        error = await self.codex_error(host.run_codex_plan("Plan the migration.", request), "configuration.unsupported_combination")
        self.assertEqual(error.operation, "run_codex_plan")
        self.assertEqual(self.sent_methods(), [])


@requires_sdk
class CodexFinalAnswerPlanFallbackTests(unittest.TestCase):
    """INV-17: a plan item answers only when no final-answer message and no unphased message exists."""

    def test_the_last_plan_answers_only_when_no_agent_message_does(self) -> None:
        from openai_codex.generated.v2_all import ThreadItem

        from vidbyte.harnesses.native.codex.wire import final_answer

        def plan(text: str) -> dict[str, Any]:
            return {"type": "plan", "id": f"plan-{text}", "text": text}

        def message(text: str, phase: str | None) -> dict[str, Any]:
            body: dict[str, Any] = {"type": "agentMessage", "id": f"msg-{text}", "text": text}
            if phase is not None:
                body["phase"] = phase
            return body

        rows: tuple[tuple[str, list[dict[str, Any]], str | None], ...] = (
            ("plan only", [plan("A")], "A"),
            ("two plans", [plan("A"), plan("B")], "B"),
            ("commentary then plan", [message("thinking", "commentary"), plan("A")], "A"),
            ("plan then unphased message", [plan("A"), message("U", None)], "U"),
            ("final message then plan", [message("F", "final_answer"), plan("A")], "F"),
            ("nothing", [], None),
            ("reasoning only", [{"type": "reasoning", "id": "r1", "summary": ["s"], "content": ["c"]}], None),
        )
        for label, items, expected in rows:
            with self.subTest(items=label):
                self.assertEqual(final_answer([ThreadItem.model_validate(item) for item in items]), expected)


@requires_sdk
class CodexTurnSettingsHostTests(_SettingsCase):
    """AC-20, INV-25, EC-23, EC-24 and EC-25: update_codex_turn_settings on a running turn this host owns."""

    async def test_a_running_turn_takes_one_settings_update_and_returns_codexs_status(self) -> None:
        from vidbyte.lib.enums.codex import CodexApprovalsReviewer, CodexReasoningEffort, CodexReasoningSummary, CodexTurnSettingsStatus

        host = await self.opened()
        handle = await self.spawn(host)
        ids = {"threadId": handle.thread_id, "turnId": handle.turn_id}
        self.remark()
        self.assertIs(await self.call(host.update_codex_turn_settings(handle, effort=CodexReasoningEffort.LOW)), CodexTurnSettingsStatus.APPLIED)
        self.assertEqual([(request.method, request.params) for request in self.sent()], [("turn/settings/update", {**ids, "effort": "low"})])
        # TARGET_UNAVAILABLE is Codex's answer, returned as a result, never raised.
        self.server.turn_settings_status = "targetUnavailable"
        self.remark()
        status = await self.call(host.update_codex_turn_settings(handle, summary=CodexReasoningSummary.CONCISE, clear_service_tier=True, approvals_reviewer=CodexApprovalsReviewer.AUTO_REVIEW))
        self.assertIs(status, CodexTurnSettingsStatus.TARGET_UNAVAILABLE)
        self.assertEqual([request.params for request in self.sent()], [{**ids, "summary": "concise", "serviceTier": None, "approvalsReviewer": "auto_review"}])
        self.server.turn_settings_status = "applied"
        self.remark()
        await self.call(host.update_codex_turn_settings(handle, model="gpt-5.5", service_tier="flex"))
        self.assertEqual([request.params for request in self.sent() if request.method != "model/list"], [{**ids, "model": "gpt-5.5", "serviceTier": "flex"}])

    async def test_an_ended_or_unknown_turn_is_refused_locally_and_sends_nothing(self) -> None:
        # AC-20, INV-25: only a running turn this host registered can be targeted.
        from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle
        from vidbyte.lib.enums.codex import CodexReasoningEffort

        host = await self.opened()
        handle = await self.spawn(host)
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="Done.")
        await self.wait_done(host, handle)
        foreign = CodexTurnHandle(thread_id=handle.thread_id, turn_id="turn-elsewhere")
        for label, target in (("ended", handle), ("unknown", foreign)):
            with self.subTest(handle=label):
                self.remark()
                error = await self.codex_error(host.update_codex_turn_settings(target, effort=CodexReasoningEffort.LOW), "codex.session_not_found")
                self.assertEqual(error.operation, TURN_UPDATE)
                summary = mapped_summary(self, error)
                self.assertTrue(summary.startswith(TURN_SETTINGS_FINISHED_MESSAGE.format(turn_id=target.turn_id, thread_id=target.thread_id)), summary)
                self.assertEqual(self.sent_methods(), [])

    async def test_a_goal_run_is_targeted_through_its_current_physical_turn(self) -> None:
        # EC-24, INV-25: between physical turns no request is sent and TARGET_UNAVAILABLE is returned.
        from vidbyte.lib.enums.codex import CodexReasoningEffort, CodexTurnSettingsStatus

        host = await self.opened()
        handle = await self.call(host.run_codex_goal("Ship the fix."))
        thread_id = handle.thread_id
        self.remark()
        self.assertIs(await self.call(host.update_codex_turn_settings(handle, effort=CodexReasoningEffort.LOW)), CodexTurnSettingsStatus.APPLIED)
        self.assertEqual([(request.method, request.params.get("turnId")) for request in self.sent()], [("turn/settings/update", handle.turn_id)])
        # The physical turn completes while the goal stays active; the thread read is the barrier for the reader thread.
        self.server.complete_turn(thread_id, handle.turn_id, final="Drafted.")
        await self.call(host.read_codex_thread(thread_id))
        self.remark()
        self.assertIs(await self.call(host.update_codex_turn_settings(handle, effort=CodexReasoningEffort.LOW)), CodexTurnSettingsStatus.TARGET_UNAVAILABLE)
        self.assertEqual(self.sent_methods(), [])
        # Codex starts the goal's next physical turn, and the update targets it.
        second = self.fakes.FakeTurn(turn_id=self.server.next_turn_id())
        self.server.threads[thread_id].turns.append(second)
        self.server.emit([("turn/started", {"threadId": thread_id, "turn": second.wire(with_items=False)})])
        await self.call(host.read_codex_thread(thread_id))
        self.remark()
        self.assertIs(await self.call(host.update_codex_turn_settings(handle, effort=CodexReasoningEffort.LOW)), CodexTurnSettingsStatus.APPLIED)
        self.assertEqual([(request.method, request.params.get("turnId")) for request in self.sent()], [("turn/settings/update", second.turn_id)])

    async def test_codex_rejecting_an_unsupported_turn_setting_keeps_its_message(self) -> None:
        # EC-25: "Unsupported fields are rejected rather than silently ignored" reaches the caller as Codex said it.
        from vidbyte.lib.enums.codex import CodexReasoningEffort

        text = "Unsupported fields are rejected rather than silently ignored: effort"
        self.server.fail("turn/settings/update", self.fakes.FakeRpcError(-32600, text))
        host = await self.opened()
        handle = await self.spawn(host)
        error = await self.codex_error(host.update_codex_turn_settings(handle, effort=CodexReasoningEffort.LOW), "codex.api_error")
        self.assertEqual(error.operation, TURN_UPDATE)
        self.assertIn(RPC_ERROR_TEXT.format(method="turn/settings/update", code=-32600, message=text), error.message)

    async def test_an_unknown_model_or_a_user_reviewer_is_refused_before_the_update(self) -> None:
        # INV-25 "The checks": the model and the reviewer are checked as INV-12 checks them.
        from vidbyte.lib.enums.codex import CodexApprovalsReviewer

        host = await self.opened()
        handle = await self.spawn(host)
        self.remark()
        await self.codex_error(host.update_codex_turn_settings(handle, model="gpt-unlisted"), "codex.model_unknown")
        error = await self.codex_error(host.update_codex_turn_settings(handle, approvals_reviewer=CodexApprovalsReviewer.USER), "configuration.unsupported_combination")
        self.assertEqual(error.next_step, USER_REVIEWER_TEXT)
        self.assertEqual([method for method in self.sent_methods() if method != "model/list"], [])

    async def test_a_turn_model_change_leaves_the_turn_priced_as_its_start_model(self) -> None:
        # EC-23, NG-12: the turn's pricing stays the model resolved at its start.
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings
        from vidbyte.lib.enums.codex import CodexTurnSettingsStatus

        self.list_model(MINI)
        host = await self.opened()
        handle = await self.spawn(host, thread=CodexThreadSettings(model="gpt-5.5"))
        self.assertIs(await self.call(host.update_codex_turn_settings(handle, model=MINI)), CodexTurnSettingsStatus.APPLIED)
        self.assertAlmostEqual(await self.finish_priced(host, handle), priced_cost("gpt-5.5", ((1000, 200),)), places=12)


if __name__ == "__main__":
    unittest.main()

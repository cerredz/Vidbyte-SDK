"""FILE: tests/features/codex_host/test_codex_host_feature_records.py

PURPOSE: Proves the records the first-class-features spec adds check themselves when they are built: the collaboration-mode records and their from_preset and reject_conflict rules, CodexSpawnRequest.collaboration_mode, CodexThreadSettingsUpdate, CodexTurnEvent and the other output records, GitWorktreeSpec with its git-ref rule (a seeded property test against the spec's own pattern), and the stored forms and refusals of the seventeen input records.
ROLE IN CODEBASE: Record layer of the slice-2 tests in tests/features/codex_host/ (docs/spec/codex-host-first-class/spec.md section 9.1, INV-1, INV-10, INV-14, AC-4, AC-6, AC-18, AC-32, EC-7, EC-12, EC-13, EC-28, EC-32, EC-35, EC-41, EC-46, EC-48, EC-51, T-5). Nothing here needs openai-codex or a host, so these tests also run on CI.
ARCHITECTURE NOTE: Each test reaches the new modules through a small importer function, so a module the feature has not built yet fails that test with ModuleNotFoundError instead of stopping collection. The expected texts are the spec's literals in codex_host_feature_support.py, never the production constants.
COMMON MODIFICATION PATTERNS: When section 9.1 adds a check, add one refused row and one accepted row to the class of that record. Keep the property test's seed fixed, so a failure is reproducible.
KNOWN EDGE CASES: Section 9.2 (r4) names an effort conflict by the collaboration mode's own field, "reasoning_effort", in CODEX_HOST_MODE_CONFLICT_MESSAGE, and fills the network-access message's {sandbox} slot with the CodexSandbox member's .name, so PROVIDER_DEFAULT never leaves the slot empty; both rows check the whole text.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-first-class/spec.md sections 8.5, 9.1, 9.2 and 9.3.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_feature_records.py
"""

from __future__ import annotations

import asyncio
import dataclasses
import itertools
import math
import os
import random
import re
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.features.codex_host.codex_host_feature_support import (
    BUDGET_CLEAR_CONFLICT_MESSAGE,
    GIT_VALUES,
    GOAL_EDIT_EMPTY_MESSAGE,
    INJECT_ITEMS_MESSAGE,
    MODE_CONFLICT_MESSAGE,
    MODE_KIND_MESSAGE,
    SETTINGS_EMPTY_MESSAGE,
    SETTINGS_MODE_MODEL_MESSAGE,
    SETTINGS_NETWORK_ACCESS_MESSAGE,
    SETTINGS_WRITABLE_ROOTS_MESSAGE,
    SIDE_CHAT_REJECTED_FIELDS,
    TIER_CLEAR_CONFLICT_MESSAGE,
    WAIT_HANDLES_MESSAGE,
    WORKTREE_REF_MESSAGE,
    WORKTREE_REPOSITORY_MESSAGE,
)
from tests.features.codex_host.codex_host_support import GOAL_FIELD_MESSAGE, GOAL_REJECTED_FIELDS, LIMIT_MESSAGE, make_echo_tool
from vidbyte.lib.errors import ConfigurationError

WORKSPACE = os.path.abspath(os.path.join(os.sep, "first-class-workspace"))
OTHER_ROOT = os.path.abspath(os.path.join(os.sep, "first-class-workspace", "src"))
SETTINGS_OWNER = "update_codex_thread_settings"
SPAWN_OWNER = "Codex spawn request"
UNUSED_FIELD_MESSAGE = "{operation} does not use the CodexSpawnRequest field {name}; leave it at its default, because {operation} would otherwise drop the value without applying it."
# Section 9.1 "page": limit from 1 to CODEX_HOST_THREAD_LIST_MAX_LIMIT (1000).
PAGE_LIMIT_MAXIMUM = 1000
# The characters the property test draws branch names from: every class GIT_REF_PATTERN treats differently.
REF_ALPHABET = "ab9Z._-/ @:~^?*[\\\n"


def _modes() -> Any:
    from vidbyte.lib.dataclasses import codex_host_modes

    return codex_host_modes


def _features() -> Any:
    from vidbyte.lib.dataclasses import codex_host_features

    return codex_host_features


def _inputs() -> Any:
    from vidbyte.lib.dataclasses import codex_host_inputs

    return codex_host_inputs


def _enums() -> Any:
    from vidbyte.lib.enums import codex

    return codex


def _codex() -> Any:
    from vidbyte.lib.dataclasses import codex

    return codex


def _host_records() -> Any:
    from vidbyte.lib.dataclasses import codex_host

    return codex_host


def _handle(number: int = 1) -> Any:
    return _host_records().CodexTurnHandle(thread_id=f"thr-{number}", turn_id=f"turn-{number}")


def _plan(**fields: Any) -> Any:
    return _modes().CodexCollaborationMode(mode=_enums().CodexCollaborationModeKind.PLAN, **fields)


class _RecordCase(unittest.TestCase):
    """Builds a record and requires the refusal the spec names."""

    def refused(self, build: Any, field: str, message: str | None = None) -> ConfigurationError:
        with self.assertRaises(ConfigurationError) as caught:
            build()
        error = caught.exception
        self.assertTrue(str(error.details.get("field", "")).endswith(field), (field, error.details, str(error)))
        if message is not None:
            self.assertEqual(str(error), message)
        return error

    def assert_frozen_and_slotted(self, record: Any) -> None:
        with self.assertRaises(dataclasses.FrozenInstanceError):
            setattr(record, dataclasses.fields(record)[0].name, None)
        self.assertFalse(hasattr(record, "__dict__"), type(record).__name__)


class CodexCollaborationModeRecordTests(_RecordCase):
    """INV-14, AC-6, EC-12, EC-13 and section 9.1 "Collaboration-mode records"."""

    def test_a_mode_names_plan_or_default_and_defaults_to_no_model_and_the_providers_effort(self) -> None:
        enums = _enums()
        mode = _plan()
        self.assertEqual((mode.mode, mode.model, mode.reasoning_effort), (enums.CodexCollaborationModeKind.PLAN, "", enums.CodexReasoningEffort.PROVIDER_DEFAULT))
        self.assert_frozen_and_slotted(mode)
        default = _modes().CodexCollaborationMode(mode=enums.CodexCollaborationModeKind.DEFAULT, model="gpt-5.5", reasoning_effort=enums.CodexReasoningEffort.HIGH)
        self.assertEqual(default.model, "gpt-5.5")

    def test_a_mode_kind_of_none_is_refused_with_the_kind_message(self) -> None:
        # AC-6: NONE stands only for Codex's null in a preset; a caller cannot send it.
        self.refused(lambda: _modes().CodexCollaborationMode(mode=_enums().CodexCollaborationModeKind.NONE), "mode", MODE_KIND_MESSAGE)

    def test_a_multi_line_model_or_a_wrong_effort_type_is_refused(self) -> None:
        self.refused(lambda: _plan(model="gpt-5.5\nsecond line"), "model")
        self.refused(lambda: _plan(reasoning_effort=3), "reasoning_effort")

    def test_a_conflicting_model_is_refused_naming_the_owner_and_an_equal_or_empty_one_is_not(self) -> None:
        enums = _enums()
        default_effort = enums.CodexReasoningEffort.PROVIDER_DEFAULT
        self.refused(lambda: _plan(model="gpt-5.5").reject_conflict(SPAWN_OWNER, "gpt-5.4-mini", default_effort), "collaboration_mode", MODE_CONFLICT_MESSAGE.format(owner=SPAWN_OWNER, name="model"))
        for mode_model, own_model in (("gpt-5.5", "gpt-5.5"), ("", "gpt-5.4-mini"), ("gpt-5.5", "")):
            with self.subTest(mode_model=mode_model, own_model=own_model):
                self.assertIsNone(_plan(model=mode_model).reject_conflict(SPAWN_OWNER, own_model, default_effort))

    def test_a_conflicting_effort_is_refused_and_a_providers_default_never_conflicts(self) -> None:
        efforts = _enums().CodexReasoningEffort
        # Section 9.2 (r4): {name} is the collaboration mode's own field, reasoning_effort.
        self.refused(lambda: _plan(reasoning_effort=efforts.HIGH).reject_conflict(SETTINGS_OWNER, "", efforts.LOW), "collaboration_mode", MODE_CONFLICT_MESSAGE.format(owner=SETTINGS_OWNER, name="reasoning_effort"))
        for mode_effort, own_effort in ((efforts.HIGH, efforts.HIGH), (efforts.PROVIDER_DEFAULT, efforts.LOW), (efforts.HIGH, efforts.PROVIDER_DEFAULT)):
            with self.subTest(mode_effort=mode_effort, own_effort=own_effort):
                self.assertIsNone(_plan(reasoning_effort=mode_effort).reject_conflict(SETTINGS_OWNER, "", own_effort))

    def test_from_preset_takes_the_presets_model_and_effort_only_where_the_turn_sets_none(self) -> None:
        enums = _enums()
        efforts = enums.CodexReasoningEffort
        turn_settings = _codex().CodexTurnSettings
        preset = _modes().CodexCollaborationModePreset(name="Plan", mode=enums.CodexCollaborationModeKind.PLAN, model="gpt-5.4-mini", reasoning_effort="medium")
        rows = (
            (turn_settings(), "gpt-5.4-mini", efforts.MEDIUM),
            # EC-13: the caller's model wins, so the mode names none and settings.model becomes the turn's.
            (turn_settings(model="gpt-5.5"), "", efforts.MEDIUM),
            (turn_settings(effort=efforts.LOW), "gpt-5.4-mini", efforts.PROVIDER_DEFAULT),
            (turn_settings(model="gpt-5.5", effort=efforts.LOW), "", efforts.PROVIDER_DEFAULT),
        )
        for turn, model, effort in rows:
            with self.subTest(turn=turn):
                mode = _modes().CodexCollaborationMode.from_preset(preset, turn)
                self.assertEqual((mode.mode, mode.model, mode.reasoning_effort), (enums.CodexCollaborationModeKind.PLAN, model, effort))

    def test_from_preset_uses_the_providers_effort_for_an_effort_the_enum_lacks(self) -> None:
        # EC-12: an effort newer than CodexReasoningEffort is kept on the preset and not refused.
        enums = _enums()
        for text in ("hyper", ""):
            with self.subTest(effort=text):
                preset = _modes().CodexCollaborationModePreset(name="Plan", mode=enums.CodexCollaborationModeKind.PLAN, reasoning_effort=text)
                self.assertEqual(preset.reasoning_effort, text)
                mode = _modes().CodexCollaborationMode.from_preset(preset, _codex().CodexTurnSettings())
                self.assertIs(mode.reasoning_effort, enums.CodexReasoningEffort.PROVIDER_DEFAULT)

    def test_from_preset_never_conflicts_with_the_turn_it_was_built_for(self) -> None:
        # INV-16 as a property: every preset and turn pairing yields a mode the turn accepts.
        enums = _enums()
        efforts = enums.CodexReasoningEffort
        turn_settings = _codex().CodexTurnSettings
        for preset_model, preset_effort, turn_model, turn_effort in itertools.product(("", "gpt-5.4-mini"), ("", "medium", "high", "hyper"), ("", "gpt-5.5"), tuple(efforts)):
            preset = _modes().CodexCollaborationModePreset(name="Plan", mode=enums.CodexCollaborationModeKind.PLAN, model=preset_model, reasoning_effort=preset_effort)
            turn = turn_settings(model=turn_model, effort=turn_effort)
            mode = _modes().CodexCollaborationMode.from_preset(preset, turn)
            mode.reject_conflict(SPAWN_OWNER, turn.model, turn.effort)

    def test_a_preset_needs_a_one_line_name_and_takes_none_for_codexs_null_mode(self) -> None:
        kinds = _enums().CodexCollaborationModeKind
        preset_class = _modes().CodexCollaborationModePreset
        self.refused(lambda: preset_class(name="", mode=kinds.PLAN), "name")
        self.refused(lambda: preset_class(name="Plan\nmode", mode=kinds.PLAN), "name")
        preset = preset_class(name="Custom", mode=kinds.NONE)
        self.assertEqual((preset.model, preset.reasoning_effort), ("", ""))
        self.assert_frozen_and_slotted(preset)


class CodexSpawnRequestModeTests(_RecordCase):
    """FR-2, INV-14, AC-6 and section 9.1 "Changed: CodexSpawnRequest"."""

    def test_collaboration_mode_is_the_last_field_and_defaults_to_none(self) -> None:
        spawn_request = _host_records().CodexSpawnRequest
        last = dataclasses.fields(spawn_request)[-1]
        self.assertEqual(last.name, "collaboration_mode")
        self.assertIsNone(spawn_request().collaboration_mode)
        self.assertEqual(spawn_request(prompt="Plan it.", collaboration_mode=_plan()).collaboration_mode, _plan())

    def test_a_mode_whose_model_or_effort_differs_from_the_turns_is_refused_when_built(self) -> None:
        spawn_request = _host_records().CodexSpawnRequest
        turn_settings = _codex().CodexTurnSettings
        efforts = _enums().CodexReasoningEffort
        self.refused(lambda: spawn_request(prompt="p", turn=turn_settings(model="gpt-5.5"), collaboration_mode=_plan(model="gpt-5.4-mini")), "collaboration_mode", MODE_CONFLICT_MESSAGE.format(owner=SPAWN_OWNER, name="model"))
        self.refused(lambda: spawn_request(prompt="p", turn=turn_settings(effort=efforts.LOW), collaboration_mode=_plan(reasoning_effort=efforts.HIGH)), "collaboration_mode", MODE_CONFLICT_MESSAGE.format(owner=SPAWN_OWNER, name="reasoning_effort"))
        # The same model in both places, or a model in only one, is accepted.
        spawn_request(prompt="p", turn=turn_settings(model="gpt-5.5"), collaboration_mode=_plan(model="gpt-5.5"))
        spawn_request(prompt="p", turn=turn_settings(effort=efforts.LOW), collaboration_mode=_plan(model="gpt-5.4-mini"))

    def test_a_collaboration_mode_that_is_not_the_record_is_refused(self) -> None:
        spawn_request = _host_records().CodexSpawnRequest
        for value in ("plan", {"mode": "plan"}):
            with self.subTest(value=value):
                self.refused(lambda value=value: spawn_request(prompt="p", collaboration_mode=value), "collaboration_mode")

    def test_a_goal_request_refuses_a_collaboration_mode_naming_the_field(self) -> None:
        # INV-10: CODEX_HOST_GOAL_REJECTED_FIELDS ends with collaboration_mode.
        goal = _host_records().CodexGoal(objective="Ship the fix.")
        self.refused(lambda: _host_records().CodexSpawnRequest(goal=goal, collaboration_mode=_plan()), "collaboration_mode", GOAL_FIELD_MESSAGE.format(owner="Codex spawn request goal", name="collaboration_mode"))


class CodexThreadSettingsUpdateTests(_RecordCase):
    """FR-1, INV-10, INV-14, AC-4, EC-7 and section 9.1 "Feature records"."""

    def _update(self, **fields: Any) -> Any:
        return _features().CodexThreadSettingsUpdate(**fields)

    def test_an_update_that_sets_nothing_is_refused_naming_settings(self) -> None:
        self.refused(self._update, "settings", SETTINGS_EMPTY_MESSAGE.format(operation=SETTINGS_OWNER))

    def test_each_single_setting_is_an_update_and_an_empty_plugin_list_counts_as_set(self) -> None:
        enums = _enums()
        rows = {
            "model": "gpt-5.5",
            "effort": enums.CodexReasoningEffort.HIGH,
            "summary": enums.CodexReasoningSummary.CONCISE,
            "service_tier": "flex",
            "clear_service_tier": True,
            "cwd": WORKSPACE,
            "approval_policy": enums.CodexApprovalPolicy.NEVER,
            "approvals_reviewer": enums.CodexApprovalsReviewer.AUTO_REVIEW,
            "sandbox": enums.CodexSandbox.READ_ONLY,
            "disabled_plugin_ids": (),
        }
        for name, value in rows.items():
            with self.subTest(field=name):
                update = self._update(**{name: value})
                self.assertEqual(getattr(update, name), value)
        self.assert_frozen_and_slotted(self._update(model="gpt-5.5"))

    def test_a_tier_set_together_with_a_clear_is_refused(self) -> None:
        self.refused(lambda: self._update(service_tier="flex", clear_service_tier=True), "clear_service_tier", TIER_CLEAR_CONFLICT_MESSAGE.format(operation=SETTINGS_OWNER))

    def test_network_access_needs_a_read_only_or_workspace_write_sandbox(self) -> None:
        sandboxes = _enums().CodexSandbox
        for sandbox in (sandboxes.PROVIDER_DEFAULT, sandboxes.FULL_ACCESS):
            with self.subTest(sandbox=sandbox):
                # Section 9.2 (r4): the slot shows the member's name.
                self.refused(lambda sandbox=sandbox: self._update(sandbox=sandbox, network_access=True), "network_access", SETTINGS_NETWORK_ACCESS_MESSAGE.format(sandbox=sandbox.name))
        for sandbox in (sandboxes.READ_ONLY, sandboxes.WORKSPACE_WRITE):
            with self.subTest(allowed=sandbox):
                self.assertIs(self._update(sandbox=sandbox, network_access=False).network_access, False)

    def test_writable_roots_must_be_absolute_and_need_a_workspace_write_sandbox(self) -> None:
        sandboxes = _enums().CodexSandbox
        self.refused(lambda: self._update(writable_roots=(OTHER_ROOT,)), "writable_roots", SETTINGS_WRITABLE_ROOTS_MESSAGE)
        self.refused(lambda: self._update(sandbox=sandboxes.READ_ONLY, writable_roots=(OTHER_ROOT,)), "writable_roots", SETTINGS_WRITABLE_ROOTS_MESSAGE)
        for roots in (("relative/src",), ("",), [OTHER_ROOT]):
            with self.subTest(roots=roots):
                self.refused(lambda roots=roots: self._update(sandbox=sandboxes.WORKSPACE_WRITE, writable_roots=roots), "writable_roots", SETTINGS_WRITABLE_ROOTS_MESSAGE)
        self.assertEqual(self._update(sandbox=sandboxes.WORKSPACE_WRITE, writable_roots=(OTHER_ROOT,)).writable_roots, (OTHER_ROOT,))

    def test_a_collaboration_mode_needs_a_model_in_the_mode_or_the_update(self) -> None:
        # EC-7: the wire needs settings.model, and an update resolves no thread model.
        self.refused(lambda: self._update(collaboration_mode=_plan()), "collaboration_mode", SETTINGS_MODE_MODEL_MESSAGE)
        self.assertEqual(self._update(collaboration_mode=_plan(model="gpt-5.5")).collaboration_mode.model, "gpt-5.5")
        self.assertEqual(self._update(model="gpt-5.5", collaboration_mode=_plan()).model, "gpt-5.5")

    def test_a_mode_that_conflicts_with_the_updates_model_is_refused_naming_the_method(self) -> None:
        self.refused(lambda: self._update(model="gpt-5.5", collaboration_mode=_plan(model="gpt-5.4-mini")), "collaboration_mode", MODE_CONFLICT_MESSAGE.format(owner=SETTINGS_OWNER, name="model"))
        efforts = _enums().CodexReasoningEffort
        self.refused(lambda: self._update(effort=efforts.LOW, collaboration_mode=_plan(model="gpt-5.5", reasoning_effort=efforts.HIGH)), "collaboration_mode", MODE_CONFLICT_MESSAGE.format(owner=SETTINGS_OWNER, name="reasoning_effort"))

    def test_a_relative_cwd_a_blank_plugin_id_and_a_multi_line_model_are_refused(self) -> None:
        self.refused(lambda: self._update(cwd="relative/folder"), "cwd")
        self.refused(lambda: self._update(disabled_plugin_ids=("",)), "disabled_plugin_ids")
        self.refused(lambda: self._update(model="gpt\n5.5"), "model")


class CodexTurnEventRecordTests(_RecordCase):
    """Section 9.1 CodexTurnEvent: the per-kind rules every stream event keeps."""

    def _event(self, kind: str, **fields: Any) -> Any:
        return _features().CodexTurnEvent(sequence=fields.pop("sequence", 1), kind=getattr(_enums().CodexTurnEventKind, kind), handle=_handle(), **fields)

    def _snapshot(self) -> Any:
        # A terminal snapshot the slice-1 record accepts: COMPLETED requires a result, a rule INV-48 keeps frozen.
        handle = _handle()
        result = _codex().CodexRunResult(thread_id=handle.thread_id, turn_id=handle.turn_id, status="completed", final_response="Done.", duration_ms=10, usage=_codex().CodexUsage(), items=())
        return _host_records().CodexTurnSnapshot(handle=handle, status=_enums().CodexTurnStatus.COMPLETED, result=result)

    def test_a_sequence_below_one_is_refused(self) -> None:
        for sequence in (0, -1):
            with self.subTest(sequence=sequence):
                self.refused(lambda sequence=sequence: self._event("MESSAGE_DELTA", sequence=sequence, text="x"), "sequence")
        self.assertEqual(self._event("MESSAGE_DELTA", text="x").sequence, 1)

    def test_a_snapshot_is_there_exactly_when_the_kind_is_ended(self) -> None:
        self.refused(lambda: self._event("ENDED"), "snapshot")
        self.refused(lambda: self._event("MESSAGE_DELTA", snapshot=self._snapshot()), "snapshot")
        self.assertEqual(self._event("ENDED", snapshot=self._snapshot()).snapshot, self._snapshot())

    def test_an_item_is_carried_only_by_item_started_and_item_completed(self) -> None:
        item = _codex().CodexItem(id="item-1", type="agentMessage", fields={"text": "Hi."})
        for kind in ("ITEM_STARTED", "ITEM_COMPLETED"):
            with self.subTest(kind=kind):
                self.assertEqual(self._event(kind, item=item, item_id="item-1", item_type="agentMessage").item, item)
        self.refused(lambda: self._event("MESSAGE_DELTA", item=item), "item")

    def test_dropped_is_at_least_one_exactly_when_the_kind_is_gap(self) -> None:
        self.refused(lambda: self._event("GAP"), "dropped")
        self.refused(lambda: self._event("MESSAGE_DELTA", dropped=1), "dropped")
        self.assertEqual(self._event("GAP", dropped=3).dropped, 3)
        event = self._event("PLAN_UPDATED", plan_steps=(_features().CodexPlanStep(step="Read the test.", status=_enums().CodexPlanStepStatus.IN_PROGRESS),))
        self.assertEqual(event.plan_steps[0].status.value, "inProgress")
        self.assert_frozen_and_slotted(event)


class CodexFeatureOutputRecordTests(_RecordCase):
    """Section 9.1: the records translators build from Codex answers refuse what the schema rules out."""

    def test_an_mcp_server_needs_a_name_and_counts_that_are_not_negative(self) -> None:
        features = _features()
        enums = _enums()
        fields = {"name": "docs", "auth_status": enums.CodexMcpAuthStatus.OAUTH, "connection_status": enums.CodexMcpConnectionStatus.NOT_REPORTED, "tool_names": ("fetch", "search"), "resource_count": 1, "resource_template_count": 0}
        server = features.CodexMcpServer(**fields)
        self.assertEqual((server.plugin_id, server.http_origin, server.tools_error, server.version), ("", "", "", ""))
        for name, value in (("name", ""), ("resource_count", -1), ("resource_template_count", -1), ("tool_names", "fetch")):
            with self.subTest(field=name):
                self.refused(lambda name=name, value=value: features.CodexMcpServer(**{**fields, name: value}), name)
        self.assertEqual(features.CodexMcpServerPage(servers=(server,), next_cursor="").servers, (server,))

    def test_memory_status_worktree_terminal_and_search_records_check_their_fields(self) -> None:
        features = _features()
        self.refused(lambda: features.CodexMemoryStatus(consolidated_threads=-1, ready=True), "consolidated_threads")
        self.assertTrue(features.CodexMemoryStatus(consolidated_threads=0, ready=True).ready)
        self.refused(lambda: features.CodexWorktree(path="", branch="feat/x", base_ref="HEAD", repository=WORKSPACE), "path")
        terminal = {"process_id": "proc-1", "item_id": "item-1", "command": "npm run dev", "cwd": WORKSPACE}
        self.assertIsNone(features.CodexBackgroundTerminal(**terminal).os_pid)
        for name, value in (("process_id", ""), ("item_id", ""), ("os_pid", -1), ("rss_kb", -1), ("cpu_percent", -0.5)):
            with self.subTest(field=name):
                self.refused(lambda name=name, value=value: features.CodexBackgroundTerminal(**{**terminal, name: value}), name)
        self.refused(lambda: features.CodexThreadSearchHit(thread="thr-1", snippet="a line"), "thread")
        self.assertEqual(features.CodexThreadSearchPage(hits=(), next_cursor="", backwards_cursor="").hits, ())


class GitWorktreeSpecTests(_RecordCase):
    """FR-35, T-5, EC-35 and section 9.1 GitWorktreeSpec."""

    def _spec(self, **fields: Any) -> Any:
        from vidbyte.lib.dataclasses.process import GitWorktreeSpec

        values = {"repository": Path(WORKSPACE), "branch": "feat/x", "path": Path(OTHER_ROOT), "timeout_seconds": 1.0, "max_output_bytes": 1, **fields}
        return GitWorktreeSpec(**values)

    def test_a_valid_spec_defaults_its_base_ref_to_blank(self) -> None:
        spec = self._spec()
        self.assertEqual((spec.branch, spec.base_ref), ("feat/x", ""))
        self.assertEqual(self._spec(base_ref="main").base_ref, "main")
        self.assert_frozen_and_slotted(spec)

    def test_relative_paths_and_bounds_that_are_not_positive_are_refused(self) -> None:
        for name, value in (("repository", Path("relative")), ("path", Path("relative")), ("timeout_seconds", 0.0), ("timeout_seconds", -1.0), ("max_output_bytes", 0)):
            with self.subTest(field=name, value=value):
                error = self.refused(lambda name=name, value=value: self._spec(**{name: value}), name)
                self.assertIn(f"GitWorktreeSpec {name}", str(error))

    def test_option_injection_dot_dot_spaces_and_overlong_refs_are_refused(self) -> None:
        # T-5: a leading dash, "..", "//", whitespace, a trailing "." "/" or ".lock", and the 200-character cap.
        for branch in ("-x", "--upload-pack=evil", "a..b", "a//b", "a b", "a.lock", "a/", "a.", "", "x" * 201, "a\nb"):
            with self.subTest(branch=branch):
                self.refused(lambda branch=branch: self._spec(branch=branch), "branch")
        self.refused(lambda: self._spec(base_ref="-x"), "base_ref")
        for branch in ("feat/x", "v1.2", "release-2026_10", "x" * 200):
            with self.subTest(accepted=branch):
                self.assertEqual(self._spec(branch=branch).branch, branch)

    def test_the_branch_rule_matches_the_spec_pattern_and_cap_for_seeded_random_names(self) -> None:
        # A property test: the record accepts a name exactly when the section 9.3 pattern and cap do.
        pattern = GIT_VALUES["GIT_REF_PATTERN"]
        cap = GIT_VALUES["GIT_REF_MAX_CHARS"]
        generator = random.Random(1729)
        names = ["".join(generator.choice(REF_ALPHABET) for _ in range(generator.randint(1, 8))) for _ in range(600)]
        names += ["a" * cap, "a" * (cap + 1)]
        for name in names:
            expected = re.fullmatch(pattern, name) is not None and len(name) <= cap
            try:
                self._spec(branch=name)
                accepted = True
            except ConfigurationError:
                accepted = False
            self.assertEqual(accepted, expected, repr(name))


class CodexFeatureInputRecordTests(_RecordCase):
    """INV-1 and section 9.1 "The 17 input records": stored forms and the refusals each method relies on."""

    def test_a_wait_takes_one_to_1024_distinct_handles_and_stores_them_as_a_tuple(self) -> None:
        inputs = _inputs()
        message = WAIT_HANDLES_MESSAGE.format(maximum=1024)
        request = inputs.CodexTurnsWaitRequest(handles=[_handle(1), _handle(2)])
        self.assertEqual(request.handles, (_handle(1), _handle(2)))
        self.assertIs(request.return_when, _enums().CodexTurnWaitMode.FIRST_COMPLETED)
        self.assertIsNone(request.timeout_seconds)
        # AC-18: empty, a duplicate and one past the cap are refused with the handles message.
        for handles in ((), (_handle(1), _handle(1)), tuple(_handle(number) for number in range(1025))):
            with self.subTest(handles=len(handles)):
                self.refused(lambda handles=handles: inputs.CodexTurnsWaitRequest(handles=handles), "handles", message)
        # A str is never a sequence of handles, and every element must be a handle.
        for handles in ("thr-1", (_handle(1), "turn-2")):
            with self.subTest(handles=handles):
                self.refused(lambda handles=handles: inputs.CodexTurnsWaitRequest(handles=handles), "handles")
        self.assertEqual(len(inputs.CodexTurnsWaitRequest(handles=tuple(_handle(number) for number in range(1024))).handles), 1024)

    def test_a_wait_mode_may_be_given_as_its_value_or_asyncios_and_seconds_must_be_positive(self) -> None:
        # D-13: the mode's values equal asyncio's constants, so either spelling selects it.
        inputs = _inputs()
        modes = _enums().CodexTurnWaitMode
        for given in (modes.ALL_COMPLETED, "ALL_COMPLETED", asyncio.ALL_COMPLETED):
            with self.subTest(given=given):
                self.assertIs(inputs.CodexTurnsWaitRequest(handles=(_handle(),), return_when=given).return_when, modes.ALL_COMPLETED)
        self.refused(lambda: inputs.CodexTurnsWaitRequest(handles=(_handle(),), return_when="FIRST_EXCEPTION"), "return_when")
        for seconds in (0, -1.0, math.nan, True):
            with self.subTest(seconds=seconds):
                self.refused(lambda seconds=seconds: inputs.CodexTurnsWaitRequest(handles=(_handle(),), timeout_seconds=seconds), "timeout_seconds")

    def test_injected_items_are_json_objects_with_a_type_stored_as_copies(self) -> None:
        # INV-37, AC-32, EC-46: 1 to 1024 mappings with a non-empty str type, JSON with allow_nan=False.
        inputs = _inputs()
        message = INJECT_ITEMS_MESSAGE.format(maximum=1024)
        item = {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Note this."}]}
        request = inputs.CodexItemsInjectRequest(thread_id="thr-1", items=[item])
        item["content"][0]["text"] = "Changed after the call."
        self.assertIsInstance(request.items, tuple)
        self.assertEqual(request.items[0]["content"][0]["text"], "Note this.")
        rows = {
            "empty": [],
            "untyped": [{"role": "user"}],
            "blank type": [{"type": ""}],
            "number type": [{"type": 3}],
            "not json": [{"type": "message", "payload": object()}],
            "nan": [{"type": "message", "score": math.nan}],
            "a str": "message",
            "a mapping": {"type": "message"},
            "not a mapping": ["message"],
            "too many": [{"type": "message"}] * 1025,
        }
        for name, items in rows.items():
            with self.subTest(items=name):
                self.refused(lambda items=items: inputs.CodexItemsInjectRequest(thread_id="thr-1", items=items), "items", message)
        self.assertEqual(len(inputs.CodexItemsInjectRequest(thread_id="thr-1", items=[{"type": "message"}] * 1024).items), 1024)

    def test_a_worktree_repository_is_an_existing_absolute_folder_and_refs_follow_the_git_rule(self) -> None:
        inputs = _inputs()
        with tempfile.TemporaryDirectory() as folder:
            request = inputs.CodexWorktreeRequest(repository=folder, branch="feat/x")
            self.assertEqual((request.repository, request.base_ref), (Path(folder), ""))
            missing = os.path.join(folder, "missing")
            a_file = os.path.join(folder, "file.txt")
            Path(a_file).write_text("x", encoding="utf-8")
            for repository in ("relative/repo", missing, a_file, Path("relative")):
                with self.subTest(repository=repository):
                    self.refused(lambda repository=repository: inputs.CodexWorktreeRequest(repository=repository, branch="feat/x"), "repository", WORKTREE_REPOSITORY_MESSAGE)
            for field, value in (("branch", "-x"), ("branch", "a..b"), ("branch", "x" * 201), ("base_ref", "a b")):
                with self.subTest(field=field, value=value):
                    fields = {"repository": folder, "branch": "feat/x", field: value}
                    self.refused(lambda fields=fields: inputs.CodexWorktreeRequest(**fields), field, WORKTREE_REF_MESSAGE.format(field=field, maximum=200))

    def test_a_goal_edit_changes_something_and_never_sets_and_clears_the_budget_together(self) -> None:
        # EC-41.
        inputs = _inputs()
        self.refused(lambda: inputs.CodexGoalEditRequest(thread_id="thr-1"), "objective", GOAL_EDIT_EMPTY_MESSAGE)
        self.refused(lambda: inputs.CodexGoalEditRequest(thread_id="thr-1", token_budget=500, clear_token_budget=True), "clear_token_budget", BUDGET_CLEAR_CONFLICT_MESSAGE)
        self.refused(lambda: inputs.CodexGoalEditRequest(thread_id="thr-1", token_budget=0), "token_budget")
        self.assertEqual(inputs.CodexGoalEditRequest(thread_id="thr-1", objective="New aim.").objective, "New aim.")
        self.assertTrue(inputs.CodexGoalEditRequest(thread_id="thr-1", clear_token_budget=True).clear_token_budget)
        self.assertEqual(inputs.CodexGoalEditRequest(thread_id="thr-1", token_budget=900).token_budget, 900)

    def test_the_memory_threshold_is_the_schemas_range(self) -> None:
        # EC-28: 1 to 4096.
        inputs = _inputs()
        for value in (0, 4097, -1, True, 2.0):
            with self.subTest(value=value):
                self.refused(lambda value=value: inputs.CodexMemoryStatusRequest(min_consolidated_threads=value), "min_consolidated_threads")
        for value in (None, 1, 4096):
            with self.subTest(accepted=value):
                self.assertEqual(inputs.CodexMemoryStatusRequest(min_consolidated_threads=value).min_consolidated_threads, value)

    def test_a_turn_settings_request_changes_something_and_never_sets_and_clears_the_tier(self) -> None:
        inputs = _inputs()
        operation = "update_codex_turn_settings"
        self.refused(lambda: inputs.CodexTurnSettingsRequest(handle=_handle()), "settings", SETTINGS_EMPTY_MESSAGE.format(operation=operation))
        self.refused(lambda: inputs.CodexTurnSettingsRequest(handle=_handle(), service_tier="flex", clear_service_tier=True), "clear_service_tier", TIER_CLEAR_CONFLICT_MESSAGE.format(operation=operation))
        self.assertIs(inputs.CodexTurnSettingsRequest(handle=_handle(), effort=_enums().CodexReasoningEffort.LOW).effort, _enums().CodexReasoningEffort.LOW)
        self.refused(lambda: inputs.CodexTurnSettingsRequest(handle=("thr-1", "turn-1"), model="gpt-5.5"), "handle")

    def test_page_requests_refuse_a_limit_outside_one_to_a_thousand_and_a_cursor_that_is_not_text(self) -> None:
        # EC-51: the listing rule, with the thread-helpers spec's own limit message.
        inputs = _inputs()
        builders = {
            "list_codex_mcp_servers": lambda **page: inputs.CodexMcpServerListRequest(**page),
            "list_codex_background_terminals": lambda **page: inputs.CodexTerminalListRequest(thread_id="thr-1", **page),
            "search_codex_thread_content": lambda **page: inputs.CodexThreadSearchRequest(query="login", **page),
            "list_codex_child_threads": lambda **page: inputs.CodexChildThreadsRequest(thread_id="thr-1", **page),
        }
        for operation, build in builders.items():
            for limit in (0, PAGE_LIMIT_MAXIMUM + 1, True, "5"):
                with self.subTest(operation=operation, limit=limit):
                    self.refused(lambda build=build, limit=limit: build(limit=limit), "limit", LIMIT_MESSAGE.format(operation=operation, minimum=1, maximum=PAGE_LIMIT_MAXIMUM))
            with self.subTest(operation=operation, cursor=5):
                self.refused(lambda build=build: build(cursor=5), "cursor")
            self.assertEqual(build(limit=PAGE_LIMIT_MAXIMUM, cursor="next").limit, PAGE_LIMIT_MAXIMUM)

    def test_a_search_query_must_not_be_blank_and_a_rename_needs_a_one_line_name(self) -> None:
        # EC-48, and section 9.1 rows 12, 13 and 16.
        inputs = _inputs()
        for query in ("", "   ", "\n"):
            with self.subTest(query=query):
                self.refused(lambda query=query: inputs.CodexThreadSearchRequest(query=query), "query")
        self.assertFalse(inputs.CodexThreadSearchRequest(query="login").archived)
        for name in ("", "two\nlines"):
            with self.subTest(name=name):
                self.refused(lambda name=name: inputs.CodexThreadRenameRequest(thread_id="thr-1", name=name), "name")
        self.refused(lambda: inputs.CodexThreadRevertRequest(thread_id="thr-1", before_turn_id=""), "before_turn_id")
        self.refused(lambda: inputs.CodexMemoryModeRequest(thread_id="thr-1", mode=3), "mode")

    def test_the_plan_side_chat_and_resume_records_refuse_every_field_their_row_names(self) -> None:
        # INV-10, EC-32: each refused field keeps CODEX_HOST_UNUSED_FIELD_MESSAGE or the goal rule.
        inputs = _inputs()
        records = _host_records()
        codex = _codex()
        enums = _enums()
        changed = {
            "prompt": {"prompt": "Inline prompt."},
            "goal": {"goal": records.CodexGoal(objective="Ship it.")},
            "name": {"name": "Side chat"},
            "tools": {"tools": (make_echo_tool(),)},
            "collaboration_mode": {"collaboration_mode": _plan()},
            "thread.ephemeral": {"thread": codex.CodexThreadSettings(ephemeral=True)},
            "thread.personality": {"thread": codex.CodexThreadSettings(personality=enums.CodexPersonality.PRAGMATIC)},
            "thread.service_name": {"thread": codex.CodexThreadSettings(service_name="vidbyte")},
            "thread.session_start_source": {"thread": codex.CodexThreadSettings(session_start_source=enums.CodexThreadStartSource.STARTUP)},
        }
        rows = (
            ("run_codex_plan", lambda request: inputs.CodexPlanRunRequest(prompt="Plan it.", request=request), ("prompt", "goal", "collaboration_mode")),
            ("start_codex_side_chat", lambda request: inputs.CodexSideChatRequest(thread_id="thr-1", prompt="Why?", request=request), SIDE_CHAT_REJECTED_FIELDS),
        )
        for operation, build, fields in rows:
            for name in fields:
                with self.subTest(operation=operation, field=name):
                    request = records.CodexSpawnRequest(**changed[name])
                    self.refused(lambda build=build, request=request: build(request), name.split(".")[-1], UNUSED_FIELD_MESSAGE.format(operation=operation, name=name))
        self.assertEqual(inputs.CodexPlanRunRequest(prompt="Plan it.").request, records.CodexSpawnRequest())

    def test_a_resume_request_refuses_the_continue_row_then_every_goal_refused_field(self) -> None:
        inputs = _inputs()
        records = _host_records()
        codex = _codex()
        enums = _enums()
        self.refused(lambda: inputs.CodexGoalResumeRequest(thread_id="thr-1", request=records.CodexSpawnRequest(prompt="Go.")), "prompt", UNUSED_FIELD_MESSAGE.format(operation="resume_codex_goal", name="prompt"))
        goal_rows = {
            "turn": {"turn": codex.CodexTurnSettings(model="gpt-5.5")},
            "output_schema": {"output_schema": {"type": "object"}},
            "disabled_plugin_ids": {"disabled_plugin_ids": ("plugin-a",)},
            "turn_service_tier": {"turn_service_tier": "flex"},
            "network_access": {"turn": codex.CodexTurnSettings(sandbox=enums.CodexSandbox.READ_ONLY), "network_access": True},
            "writable_roots": {"turn": codex.CodexTurnSettings(sandbox=enums.CodexSandbox.WORKSPACE_WRITE), "writable_roots": (OTHER_ROOT,)},
            "collaboration_mode": {"collaboration_mode": _plan()},
        }
        self.assertEqual(tuple(goal_rows), GOAL_REJECTED_FIELDS)
        for name, fields in goal_rows.items():
            with self.subTest(field=name):
                request = records.CodexSpawnRequest(**fields)
                error = self.refused(lambda request=request: inputs.CodexGoalResumeRequest(thread_id="thr-1", request=request), GOAL_REJECTED_FIELDS[0] if name in ("network_access", "writable_roots") else name)
                self.assertIn("resume_codex_goal request", str(error))
        self.assertEqual(inputs.CodexGoalResumeRequest(thread_id="thr-1").request, records.CodexSpawnRequest())


if __name__ == "__main__":
    unittest.main()

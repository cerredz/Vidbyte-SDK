"""FILE: vidbyte/harnesses/native/codex/skill_functions.py

PURPOSE: CodexSkillFunctions, the CodexHost collaborator behind the run wrappers: run_codex_goal starts a goal run and reads its stored goal back, and run_codex_skill and run_codex_openai_docs resolve a skill, start a turn whose input carries it as a first-class item, and read that input back; a run that cannot be confirmed is interrupted once and reported. run_codex_plan lists Codex's collaboration mode presets and spawns one turn in its plan preset.
ROLE IN CODEBASE: A host collaborator of vidbyte/harnesses/native/codex/; CodexHost builds it in _open() with itself as the host, and its three run methods, and CodexSettingsMethods.run_codex_plan, guard, then delegate here (first-class D-8).
ARCHITECTURE NOTE: The wrappers compose CodexHost's own public functions through the CodexSkillHost Protocol defined here, so this module never imports host.py, at runtime or under TYPE_CHECKING, and no import cycle exists (D-2). Every CodexAgentError that escapes a wrapper carries the wrapper's operation: one from a reused function is relabelled through CodexErrorMapper.relabel, which keeps every other field (hardening INV-31, D-22, superseding D-3). The read-back bounds are imported by name and read as module globals at call time (section 13).
COMMON MODIFICATION PATTERNS: A new named skill wrapper is one host method that passes its skill name to run_skill; a new check on a started run reads the run back through CodexSkillHost and ends with the same single interrupt. A new wrapper that needs another host function adds it to CodexSkillHost first.
KNOWN EDGE CASES: turn/start may return before Codex records the turn's input, so the read-back polls a bounded number of times, a fixed interval apart, under one deadline that never cuts a read in flight short (INV-34, EC-50). A cancelled or failed check still sends its one interrupt before the original exception propagates (INV-22, INV-35). An ephemeral thread keeps no history, so a skill run on one is refused before any request (INV-6). The skill is resolved in the folder the turn runs in: the turn's cwd, else the thread's (hardening INV-33). A plan run on a Codex that lists no plan preset is refused before any thread starts, and the turn's own model and effort win over the preset's (first-class INV-16, EC-12, EC-13).
RELATED DOCS: docs/spec/codex-host-thread-helpers/spec.md (sections 6.1 INV-21 to INV-27, INV-34 and INV-35, 8.1 D-2, D-3, D-16 and D-17, and 9.2); docs/spec/codex-host-hardening/spec.md (sections 6.1 INV-31 and INV-33, and 8.1 D-22); docs/spec/codex-host-first-class/spec.md (INV-16, D-8, EC-12 to EC-16)
TESTS: tests/features/codex_host/test_codex_host_goal_skills.py, tests/features/codex_host/test_codex_host_helper_lifecycle.py, tests/features/codex_host/test_codex_host_helper_surface.py, tests/features/codex_host/test_codex_host_resilience.py, tests/features/codex_host/test_codex_host_function_rows.py, tests/features/codex_host/test_codex_host_settings_modes.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import replace
from typing import Any, Protocol

from vidbyte.harnesses.native.codex.errors import CodexErrorMapper
from vidbyte.lib.constants.codex import (
    CODEX_HOST_INPUT_CHECK_ATTEMPTS,
    CODEX_HOST_INPUT_CHECK_DEADLINE_SECONDS,
    CODEX_HOST_INPUT_CHECK_INTERVAL_SECONDS,
    CODEX_HOST_INPUT_CHECK_TURN_LIMIT,
    CODEX_HOST_SKILL_NAMES_IN_ERROR,
    CODEX_USER_MESSAGE_ITEM_TYPE,
)
from vidbyte.lib.constants.codex_host import (
    CODEX_HOST_APP_SERVER_PLACE,
    CODEX_HOST_BUDGET_DIFFERS_MESSAGE,
    CODEX_HOST_CONTENT_FIELD,
    CODEX_HOST_FOLDER_PLACE,
    CODEX_HOST_GOAL_UNCHECKED_SENTENCE,
    CODEX_HOST_INPUT_NOT_RECORDED_MESSAGE,
    CODEX_HOST_LIST_SEPARATOR,
    CODEX_HOST_MORE_NAMES_TEXT,
    CODEX_HOST_NO_GOAL_MESSAGE,
    CODEX_HOST_NO_NAMES_TEXT,
    CODEX_HOST_NO_PLAN_MODE_MESSAGE,
    CODEX_HOST_OBJECTIVE_DIFFERS_MESSAGE,
    CODEX_HOST_SKILL_DISABLED_MESSAGE,
    CODEX_HOST_SKILL_DROPPED_MESSAGE,
    CODEX_HOST_SKILL_NOT_FOUND_MESSAGE,
    CODEX_HOST_SKILL_UNCHECKED_SENTENCE,
)
from vidbyte.lib.dataclasses.codex import (
    CodexRunInput,
    CodexSkillInput,
    CodexTextInput,
)
from vidbyte.lib.dataclasses.codex_host import (
    CodexGoal,
    CodexSkillInfo,
    CodexSpawnRequest,
    CodexThreadGoal,
    CodexTurnHandle,
    CodexTurnPage,
)
from vidbyte.lib.dataclasses.codex_host_inputs import (
    CodexGoalRunRequest,
    CodexPlanRunRequest,
    CodexSkillRunRequest,
)
from vidbyte.lib.dataclasses.codex_host_modes import (
    CodexCollaborationMode,
    CodexCollaborationModePreset,
)
from vidbyte.lib.enums.codex import (
    CodexCollaborationModeKind,
    CodexHostOperation,
    CodexInputType,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError


class CodexSkillHost(Protocol):
    """The CodexHost functions the run wrappers compose: spawn, skill listing, mode listing, goal read, turn listing and interrupt."""

    async def spawn_codex_thread(self, request: CodexSpawnRequest) -> CodexTurnHandle: ...

    async def list_codex_skills(self, cwd: str = "", force_reload: bool = False) -> tuple[CodexSkillInfo, ...]: ...

    async def list_codex_collaboration_modes(self) -> tuple[CodexCollaborationModePreset, ...]: ...

    async def get_codex_goal(self, thread_id: str) -> CodexThreadGoal | None: ...

    async def list_codex_turns(self, thread_id: str, cursor: str = "", limit: int | None = None) -> CodexTurnPage: ...

    async def interrupt_codex_turn(self, handle: CodexTurnHandle) -> None: ...


class CodexSkillFunctions:
    """Starts goal and skill runs through CodexHost's own functions, and confirms each one took."""

    def __init__(self, host: CodexSkillHost) -> None:
        # The host whose public functions every run goes through.
        self._host = host

    async def run_goal(self, operation: CodexHostOperation, goal_run: CodexGoalRunRequest) -> CodexTurnHandle:
        # @intent a-goal-run-returns-only-once-its-goal-is-confirmed
        # A goal run is started through spawn's goal path, then its
        # stored goal is read back; a goal that is missing or differs,
        # or a check that fails, gets one interrupt so the run never
        # keeps spending unseen (INV-21, INV-22). Every host error that
        # escapes names run_codex_goal (hardening INV-31).
        # Take the caller's posture unchanged, apart from the goal; the
        # record already refused a request with its own prompt or goal.
        goal = goal_run.goal
        try:
            handle = await self._host.spawn_codex_thread(replace(goal_run.request, goal=goal))
        except CodexAgentError as exc:
            raise CodexErrorMapper.relabel(exc, operation) from None
        # Read the stored goal back. A failed or cancelled read stops
        # the run, and a host error says the run was interrupted.
        try:
            stored = await self._host.get_codex_goal(handle.thread_id)
        except CodexAgentError as exc:
            await self._interrupt(handle)
            unchecked = exc.with_sentence(CODEX_HOST_GOAL_UNCHECKED_SENTENCE.format(thread_id=handle.thread_id))
            raise CodexErrorMapper.relabel(unchecked, operation) from None
        except BaseException:
            await self._interrupt(handle)
            raise
        # A goal that did not take stops the run and is reported.
        problem = self._goal_problem(stored, goal)
        if problem:
            await self._interrupt(handle)
            raise CodexErrorMapper.error(FailureCode.CODEX_COMMAND_NOT_RUN, problem, operation, handle.thread_id)
        return handle

    async def run_skill(self, skill_run: CodexSkillRunRequest) -> CodexTurnHandle:
        # @intent a-skill-run-returns-only-once-codex-recorded-the-skill
        # The skill is resolved before any thread starts, sent as a
        # first-class input item after the caller's text, and then read
        # back from the stored turn; a run whose input cannot be
        # confirmed gets one interrupt and is reported (INV-24, INV-25,
        # INV-34, INV-35). Every host error that escapes names the
        # wrapper the caller called (hardening INV-31).
        # The record already checked the request, the skill name and
        # the text, so a bad argument sent nothing.
        operation, skill, spawn = skill_run.operation, skill_run.skill, skill_run.request
        text = CodexTextInput(text=skill_run.prompt)
        # Find the first enabled skill of that exact name for the
        # folder the turn will run in: the turn's own, else the
        # thread's (hardening INV-33). Then start the thread with the
        # skill as an input item.
        cwd = spawn.turn.cwd or spawn.thread.cwd
        try:
            path = self._skill_path(operation, skill, cwd, await self._host.list_codex_skills(cwd))
            run_input = CodexRunInput(items=(text, CodexSkillInput(name=skill, path=path)))
            handle = await self._host.spawn_codex_thread(replace(spawn, prompt=run_input))
        except CodexAgentError as exc:
            raise CodexErrorMapper.relabel(exc, operation) from None
        # Read the turn's recorded input back. A failed or cancelled
        # read stops the run, and a host error says so.
        try:
            content = await self._recorded_input(handle)
        except CodexAgentError as exc:
            await self._interrupt(handle)
            unchecked = exc.with_sentence(CODEX_HOST_SKILL_UNCHECKED_SENTENCE.format(thread_id=handle.thread_id))
            raise CodexErrorMapper.relabel(unchecked, operation) from None
        except BaseException:
            await self._interrupt(handle)
            raise
        # Input never recorded, or recorded without the skill, stops
        # the run and is reported.
        if content is None or not any(entry.get("type") == CodexInputType.SKILL.value and entry.get("name") == skill for entry in content):
            await self._interrupt(handle)
            missing = CODEX_HOST_INPUT_NOT_RECORDED_MESSAGE.format(skill=skill, seconds=CODEX_HOST_INPUT_CHECK_DEADLINE_SECONDS)
            message = missing if content is None else CODEX_HOST_SKILL_DROPPED_MESSAGE.format(skill=skill)
            raise CodexErrorMapper.error(FailureCode.CODEX_COMMAND_NOT_RUN, message, operation, handle.thread_id)
        return handle

    async def run_plan(self, plan_run: CodexPlanRunRequest) -> CodexTurnHandle:
        # @intent a-plan-run-is-one-spawn-in-codexs-plan-preset
        # A plan run lists Codex's presets and spawns one turn in the
        # first preset whose mode is plan, so the plan Codex writes is
        # the turn's answer. Every host error that escapes names
        # run_codex_plan (first-class INV-16, D-8).
        operation = CodexHostOperation.RUN_CODEX_PLAN
        try:
            # Find Codex's own plan preset; a Codex without one gets
            # no thread at all (INV-16, AC-11).
            presets = await self._host.list_codex_collaboration_modes()
            preset = next((entry for entry in presets if entry.mode is CodexCollaborationModeKind.PLAN), None)
            if preset is None:
                raise CodexErrorMapper.error(FailureCode.CODEX_PROTOCOL_MISMATCH, CODEX_HOST_NO_PLAN_MODE_MESSAGE, operation)
            # Build the mode from the preset, with the caller's turn
            # model and effort winning, then spawn the one plan turn.
            mode = CodexCollaborationMode.from_preset(preset, plan_run.request.turn)
            return await self._host.spawn_codex_thread(replace(plan_run.request, prompt=plan_run.prompt, collaboration_mode=mode))
        except CodexAgentError as exc:
            raise CodexErrorMapper.relabel(exc, operation) from None

    @staticmethod
    def _skill_path(operation: CodexHostOperation, skill: str, cwd: str, listed: Sequence[CodexSkillInfo]) -> str:
        # The first enabled exact-name match supplies the path. The
        # refusals name the skill and folder, never a path or a
        # description, and list at most a bounded number of enabled
        # names (INV-24, D-20, D-24).
        matches = [info for info in listed if info.name == skill]
        enabled = next((info.path for info in matches if info.enabled), None)
        if enabled is not None:
            return enabled
        place = CODEX_HOST_FOLDER_PLACE.format(cwd=cwd) if cwd else CODEX_HOST_APP_SERVER_PLACE
        if matches:
            raise CodexErrorMapper.error(FailureCode.CODEX_SKILL_DISABLED, CODEX_HOST_SKILL_DISABLED_MESSAGE.format(skill=skill, place=place), operation)
        names = list(dict.fromkeys(info.name for info in listed if info.enabled))
        shown = CODEX_HOST_LIST_SEPARATOR.join(names[:CODEX_HOST_SKILL_NAMES_IN_ERROR]) or CODEX_HOST_NO_NAMES_TEXT
        capped = len(names) > CODEX_HOST_SKILL_NAMES_IN_ERROR
        tail = CODEX_HOST_MORE_NAMES_TEXT.format(count=len(names) - CODEX_HOST_SKILL_NAMES_IN_ERROR) if capped else ""
        raise CodexErrorMapper.error(FailureCode.CODEX_SKILL_NOT_FOUND, CODEX_HOST_SKILL_NOT_FOUND_MESSAGE.format(skill=skill, place=place, names=shown + tail), operation)

    async def _recorded_input(self, handle: CodexTurnHandle) -> list[Any] | None:
        # @intent the-input-read-back-is-bounded-twice
        # Codex may record a turn's input a little after turn/start
        # returns (A-19), so the new thread's first turn is read up to
        # CODEX_HOST_INPUT_CHECK_ATTEMPTS times, a fixed interval
        # apart. One deadline, taken before the first read, ends the
        # read-back once the next wait would pass it. A read already in
        # flight is never cut short, because cancelling it would turn a
        # plain miss into a timeout (EC-50). None means no input yet.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + CODEX_HOST_INPUT_CHECK_DEADLINE_SECONDS
        for attempt in range(CODEX_HOST_INPUT_CHECK_ATTEMPTS):
            if attempt:
                if loop.time() + CODEX_HOST_INPUT_CHECK_INTERVAL_SECONDS >= deadline:
                    return None
                await asyncio.sleep(CODEX_HOST_INPUT_CHECK_INTERVAL_SECONDS)
            page = await self._host.list_codex_turns(handle.thread_id, limit=CODEX_HOST_INPUT_CHECK_TURN_LIMIT)
            content = next((item.fields[CODEX_HOST_CONTENT_FIELD] for turn in page.turns if turn.turn_id == handle.turn_id for item in turn.items if item.type == CODEX_USER_MESSAGE_ITEM_TYPE), None)
            if content is not None:
                return list(content)
        return None

    async def _interrupt(self, handle: CodexTurnHandle) -> None:
        # The single stop of a run that could not be confirmed; its own
        # failure is ignored, so the reason the run stopped is what the
        # caller sees (INV-22, INV-35).
        with suppress(CodexAgentError):
            await self._host.interrupt_codex_turn(handle)

    @staticmethod
    def _goal_problem(stored: CodexThreadGoal | None, goal: CodexGoal) -> str:
        # Why the stored goal does not match the one sent, or "" when
        # it does; a budget is compared only when one was sent (INV-21).
        if stored is None:
            return CODEX_HOST_NO_GOAL_MESSAGE
        if stored.objective != goal.objective:
            return CODEX_HOST_OBJECTIVE_DIFFERS_MESSAGE
        if goal.token_budget is not None and stored.token_budget != goal.token_budget:
            return CODEX_HOST_BUDGET_DIFFERS_MESSAGE.format(stored=stored.token_budget, sent=goal.token_budget)
        return ""


__all__ = ["CodexSkillFunctions", "CodexSkillHost"]

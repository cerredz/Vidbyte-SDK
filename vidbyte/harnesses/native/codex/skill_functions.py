"""FILE: vidbyte/harnesses/native/codex/skill_functions.py

PURPOSE: CodexSkillFunctions, the CodexHost collaborator behind the run wrappers: run_codex_goal starts a goal run and reads its stored goal back, and run_codex_skill and run_codex_openai_docs resolve a skill, start a turn whose input carries it as a first-class item, and read that input back; a run that cannot be confirmed is interrupted once and reported.
ROLE IN CODEBASE: A host collaborator of vidbyte/harnesses/native/codex/; CodexHost builds it in _open() with itself as the host, and its three run methods guard, then delegate here.
ARCHITECTURE NOTE: The wrappers compose CodexHost's own public functions through the CodexSkillHost Protocol defined here, so this module never imports host.py, at runtime or under TYPE_CHECKING, and no import cycle exists (D-2). Errors from a reused function keep that function's operation; only the errors a wrapper raises itself carry the wrapper's (D-3). The read-back bounds are imported by name and read as module globals at call time (section 13).
COMMON MODIFICATION PATTERNS: A new named skill wrapper is one host method that passes its skill name to run_skill; a new check on a started run reads the run back through CodexSkillHost and ends with the same single interrupt.
KNOWN EDGE CASES: turn/start may return before Codex records the turn's input, so the read-back polls a bounded number of times, a fixed interval apart, under one deadline that never cuts a read in flight short (INV-34, EC-50). A cancelled or failed check still sends its one interrupt before the original exception propagates (INV-22, INV-35). An ephemeral thread keeps no history, so a skill run on one is refused before any request (INV-6).
RELATED DOCS: docs/spec/codex-host-thread-helpers/spec.md (sections 6.1 INV-21 to INV-27, INV-34 and INV-35, 8.1 D-2, D-3, D-16 and D-17, and 9.2)
TESTS: tests/features/codex_host/test_codex_host_goal_skills.py, tests/features/codex_host/test_codex_host_helper_lifecycle.py, tests/features/codex_host/test_codex_host_helper_surface.py
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
from vidbyte.lib.enums.codex import CodexHostOperation, CodexInputType
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError, ConfigurationError

OWN_INPUT_MESSAGE = "{operation} takes its input as arguments; leave request.prompt and request.goal at their defaults."
EPHEMERAL_SKILL_MESSAGE = "{operation} needs a stored thread to confirm the skill run, so request.thread.ephemeral must be False."
SKILL_NAME_MESSAGE = "{operation} skill must be a non-empty string."
SKILL_NOT_FOUND_MESSAGE = "Codex lists no skill named '{skill}' for {place}. Enabled skills: {names}."
SKILL_DISABLED_MESSAGE = "The Codex skill '{skill}' is disabled for {place}."
NO_GOAL_MESSAGE = "Codex reports no goal on the thread after the goal run started."
OBJECTIVE_DIFFERS_MESSAGE = "Codex reports a goal objective different from the one sent."
BUDGET_DIFFERS_MESSAGE = "Codex reports a goal token budget of {stored}, not the {sent} that was sent."
GOAL_UNCHECKED_MESSAGE = " The goal run on thread {thread_id} was interrupted because its goal could not be checked."
INPUT_NOT_RECORDED_MESSAGE = "Codex recorded no input for the turn of skill '{skill}' within {seconds} seconds, so the skill run could not be confirmed."
SKILL_DROPPED_MESSAGE = "Codex recorded the turn's input without the skill '{skill}', so the run did not use the skill."
SKILL_UNCHECKED_MESSAGE = " The skill run on thread {thread_id} was interrupted because its input could not be checked."
# How the skill messages name the folder whose skills were listed.
FOLDER_PLACE = "the folder {cwd}"
APP_SERVER_PLACE = "the app-server's working folder"
# The enabled-names list of a skill_not_found message: its separator,
# its capped tail, and its text when nothing is enabled.
NAME_SEPARATOR = ", "
MORE_NAMES_TEXT = " and {count} more"
NO_NAMES_TEXT = "none"
# The stored item that holds a turn's recorded input.
USER_MESSAGE_ITEM_TYPE = "userMessage"


class CodexSkillHost(Protocol):
    """The CodexHost functions the run wrappers compose: spawn, skill listing, goal read, turn listing and interrupt."""

    async def spawn_codex_thread(self, request: CodexSpawnRequest) -> CodexTurnHandle: ...

    async def list_codex_skills(self, cwd: str = "") -> tuple[CodexSkillInfo, ...]: ...

    async def get_codex_goal(self, thread_id: str) -> CodexThreadGoal | None: ...

    async def list_codex_turns(self, thread_id: str, cursor: str = "", limit: int | None = None) -> CodexTurnPage: ...

    async def interrupt_codex_turn(self, handle: CodexTurnHandle) -> None: ...


class CodexSkillFunctions:
    """Starts goal and skill runs through CodexHost's own functions, and confirms each one took."""

    def __init__(self, host: CodexSkillHost) -> None:
        # The host whose public functions every run goes through.
        self._host = host

    async def run_goal(
        self,
        operation: CodexHostOperation,
        objective: str,
        token_budget: int | None,
        request: CodexSpawnRequest | None,
    ) -> CodexTurnHandle:
        # @intent a-goal-run-returns-only-once-its-goal-is-confirmed
        # A goal run is started through spawn's goal path, then its
        # stored goal is read back; a goal that is missing or differs,
        # or a check that fails, gets one interrupt so the run never
        # keeps spending unseen (INV-21, INV-22).
        # Take the caller's posture unchanged, apart from the goal.
        spawn = request or CodexSpawnRequest()
        self._reject_own_input(operation, spawn)
        goal = CodexGoal(objective=objective, token_budget=token_budget)
        handle = await self._host.spawn_codex_thread(replace(spawn, goal=goal))
        # Read the stored goal back. A failed or cancelled read stops
        # the run, and a host error says the run was interrupted.
        try:
            stored = await self._host.get_codex_goal(handle.thread_id)
        except CodexAgentError as exc:
            await self._interrupt(handle)
            raise self._unchecked(exc, GOAL_UNCHECKED_MESSAGE.format(thread_id=handle.thread_id)) from None
        except BaseException:
            await self._interrupt(handle)
            raise
        # A goal that did not take stops the run and is reported.
        problem = self._goal_problem(stored, goal)
        if problem:
            await self._interrupt(handle)
            raise CodexErrorMapper.error(FailureCode.CODEX_COMMAND_NOT_RUN, problem, operation, handle.thread_id)
        return handle

    async def run_skill(
        self,
        operation: CodexHostOperation,
        skill: str,
        prompt: str,
        request: CodexSpawnRequest | None,
    ) -> CodexTurnHandle:
        # @intent a-skill-run-returns-only-once-codex-recorded-the-skill
        # The skill is resolved before any thread starts, sent as a
        # first-class input item after the caller's text, and then read
        # back from the stored turn; a run whose input cannot be
        # confirmed gets one interrupt and is reported (INV-24, INV-25,
        # INV-34, INV-35).
        # Check the request, the skill name and the text first, so a
        # bad argument sends nothing.
        spawn = request or CodexSpawnRequest()
        self._reject_own_input(operation, spawn)
        self._reject_skill_arguments(operation, skill, spawn)
        text = CodexTextInput(text=prompt)
        # Find the first enabled skill of that exact name for the
        # folder the thread will run in.
        cwd = spawn.thread.cwd
        path = self._skill_path(operation, skill, cwd, await self._host.list_codex_skills(cwd))
        run_input = CodexRunInput(items=(text, CodexSkillInput(name=skill, path=path)))
        handle = await self._host.spawn_codex_thread(replace(spawn, prompt=run_input))
        # Read the turn's recorded input back. A failed or cancelled
        # read stops the run, and a host error says so.
        try:
            content = await self._recorded_input(handle)
        except CodexAgentError as exc:
            await self._interrupt(handle)
            raise self._unchecked(exc, SKILL_UNCHECKED_MESSAGE.format(thread_id=handle.thread_id)) from None
        except BaseException:
            await self._interrupt(handle)
            raise
        # Input never recorded, or recorded without the skill, stops
        # the run and is reported.
        if content is None or not any(entry.get("type") == CodexInputType.SKILL.value and entry.get("name") == skill for entry in content):
            await self._interrupt(handle)
            missing = INPUT_NOT_RECORDED_MESSAGE.format(skill=skill, seconds=CODEX_HOST_INPUT_CHECK_DEADLINE_SECONDS)
            message = missing if content is None else SKILL_DROPPED_MESSAGE.format(skill=skill)
            raise CodexErrorMapper.error(FailureCode.CODEX_COMMAND_NOT_RUN, message, operation, handle.thread_id)
        return handle

    @staticmethod
    def _reject_own_input(operation: CodexHostOperation, spawn: CodexSpawnRequest) -> None:
        # The wrapper sets the prompt or goal itself, so a request that
        # carries its own would be ambiguous (INV-6, EC-37).
        if isinstance(spawn.prompt, CodexRunInput) or spawn.prompt or spawn.goal is not None:
            raise ConfigurationError(OWN_INPUT_MESSAGE.format(operation=operation.value))

    @staticmethod
    def _reject_skill_arguments(operation: CodexHostOperation, skill: str, spawn: CodexSpawnRequest) -> None:
        # An ephemeral thread keeps no history, so its skill run could
        # never be confirmed and would only spend (INV-6, EC-48).
        if spawn.thread.ephemeral:
            raise ConfigurationError(EPHEMERAL_SKILL_MESSAGE.format(operation=operation.value))
        if not isinstance(skill, str) or not skill.strip():
            raise ConfigurationError(SKILL_NAME_MESSAGE.format(operation=operation.value))

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
        place = FOLDER_PLACE.format(cwd=cwd) if cwd else APP_SERVER_PLACE
        if matches:
            raise CodexErrorMapper.error(FailureCode.CODEX_SKILL_DISABLED, SKILL_DISABLED_MESSAGE.format(skill=skill, place=place), operation)
        names = list(dict.fromkeys(info.name for info in listed if info.enabled))
        shown = NAME_SEPARATOR.join(names[:CODEX_HOST_SKILL_NAMES_IN_ERROR]) or NO_NAMES_TEXT
        capped = len(names) > CODEX_HOST_SKILL_NAMES_IN_ERROR
        tail = MORE_NAMES_TEXT.format(count=len(names) - CODEX_HOST_SKILL_NAMES_IN_ERROR) if capped else ""
        raise CodexErrorMapper.error(FailureCode.CODEX_SKILL_NOT_FOUND, SKILL_NOT_FOUND_MESSAGE.format(skill=skill, place=place, names=shown + tail), operation)

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
            content = next((item.fields["content"] for turn in page.turns if turn.turn_id == handle.turn_id for item in turn.items if item.type == USER_MESSAGE_ITEM_TYPE), None)
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
            return NO_GOAL_MESSAGE
        if stored.objective != goal.objective:
            return OBJECTIVE_DIFFERS_MESSAGE
        if goal.token_budget is not None and stored.token_budget != goal.token_budget:
            return BUDGET_DIFFERS_MESSAGE.format(stored=stored.token_budget, sent=goal.token_budget)
        return ""

    @staticmethod
    def _unchecked(exc: CodexAgentError, sentence: str) -> CodexAgentError:
        # The check's own error, with its code, operation and next step,
        # plus the sentence that says the run was interrupted.
        return CodexAgentError(exc.message + sentence, failure_code=exc.failure_code, operation=exc.operation, next_step=exc.next_step)


__all__ = ["CodexSkillFunctions", "CodexSkillHost"]

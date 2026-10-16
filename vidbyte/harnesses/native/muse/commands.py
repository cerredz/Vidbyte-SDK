"""FILE: vidbyte/harnesses/native/muse/commands.py

PURPOSE: Defines the six public Muse skill functions (MuseCommands: run_muse_skill, run_muse_goal, run_muse_plan, run_muse_import, run_muse_scaffold and run_muse_browser_app) and the flow of one run (MuseCommandRun): run #1036's `muse exec` once with a prompt that asks for the skill or the goal, then read the new thread's own record back and return only when it shows the skill was loaded or the goal set.
ROLE IN CODEBASE: The functions are bound as module names in vidbyte/harnesses/native/muse/__init__.py and re-exported from vidbyte.harnesses.native. MuseCommandRun runs the thread with MuseThreadRun.execute (muse/threads.py), reads the evidence with MuseHelperRun.tool_calls or, after compaction, MuseHelperRun.transcript (muse/helpers.py), and checks it with NativeCommandEvidence from hostkit. init_muse_workspace is keyless and lives in MuseThreadHelpers (muse/helpers.py).
ARCHITECTURE NOTE: muse exec does not expand slash commands, so a skill is asked for in the prompt (MUSE_SKILL_PROMPT_TEMPLATE, MUSE_GOAL_PROMPT_TEMPLATE) and the evidence is the model's own tool call (spec D-9): a read_skill call whose args name the skill, or a create_goal call. Evidence fails closed (spec INV-8). The evidence read is a keyless `muse serve` session/read with items in a fresh private config folder (spec INV-23); when the history is an anchored snapshot, whose items start after a compaction, the run's own keyless `muse export` transcript must hold the tool name and the skill id instead (spec D-33). Every error after the run carries the new thread's id (spec EC-61). The text is checked under its public name before anything starts (spec D-25). The module holds no literals of its own (spec INV-15).
FUNCTION INVENTORY: MuseCommands holds the six public functions and _call, the one guarded try they share. MuseCommandRun.execute is the narrated main function of one run.
COMMON MODIFICATION PATTERNS: A new bundled Muse skill is one MuseSkill member, one NativeThreadOperation member, its text name in NATIVE_TEXT_ARGUMENTS and one wrapper here that passes the skill id.
WHAT NOT TO DO IN THIS FILE: 1. Do not give the evidence read or the export a key; only the exec child carries META_API_KEY. 2. Do not accept a run without its evidence, and do not drop the new thread's id from an error raised after the run. 3. Do not send a slash command to muse exec; it reaches the model as plain text.
KNOWN EDGE CASES: History mode none has no items and fails closed naming noneReason (spec EC-56). A user skill is named by its folder name and a bundled one by its bundled: id (spec EC-55). On Windows, Muse runs only through config.wsl_distro or config.muse_command (spec EC-34).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_muse_commands.py, tests/features/harness_threads/test_harness_threads_helper_arguments.py, tests/features/harness_threads/test_harness_threads_helper_bounds.py, tests/features/harness_threads/test_harness_threads_helper_credentials.py
"""

from __future__ import annotations

import asyncio
import dataclasses
import sys
from collections.abc import Sequence
from pathlib import Path

from vidbyte.harnesses.native.hostkit import NativeCommandEvidence, NativeErrorFactory
from vidbyte.harnesses.native.muse.helpers import MuseHelperRun
from vidbyte.harnesses.native.muse.threads import MuseThreadRun
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    MuseThreadConfig,
    NativeThreadRequest,
    NativeThreadResult,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_threads import (
    MuseSkill,
    NativeHarness,
    NativeThreadOperation,
    NativeThreadVerb,
)
from vidbyte.lib.errors import ConfigurationError, NativeThreadError


class MuseCommands:
    """The public Muse Code skill functions: run one skill or goal headless with the caller's key, and return only when the thread shows it ran."""

    @staticmethod
    async def run_muse_skill(skill: str, prompt: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: MuseThreadConfig | None = None) -> NativeThreadResult:
        """Run prompt as one new Muse Code thread that loads the skill skill (a user skill's folder name or a bundled: id)."""
        return await MuseCommands._call(NativeThreadOperation.RUN_MUSE_SKILL, skill=skill, text=prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_muse_goal(objective: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: MuseThreadConfig | None = None) -> NativeThreadResult:
        """Set objective as the new thread's goal with create_goal and work until it is met."""
        return await MuseCommands._call(NativeThreadOperation.RUN_MUSE_GOAL, text=objective, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_muse_plan(task: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: MuseThreadConfig | None = None) -> NativeThreadResult:
        """Plan task with Muse's bundled plan skill."""
        return await MuseCommands._call(NativeThreadOperation.RUN_MUSE_PLAN, skill=MuseSkill.PLAN.value, text=task, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_muse_import(session_ref: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: MuseThreadConfig | None = None) -> NativeThreadResult:
        """Import the session session_ref from another coding agent with Muse's bundled import skill."""
        return await MuseCommands._call(NativeThreadOperation.RUN_MUSE_IMPORT, skill=MuseSkill.IMPORT.value, text=session_ref, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_muse_scaffold(description: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: MuseThreadConfig | None = None) -> NativeThreadResult:
        """Scaffold the project description describes with Muse's bundled greenfield scaffolding skill."""
        return await MuseCommands._call(NativeThreadOperation.RUN_MUSE_SCAFFOLD, skill=MuseSkill.SCAFFOLD.value, text=description, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_muse_browser_app(description: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: MuseThreadConfig | None = None) -> NativeThreadResult:
        """Build the browser app description describes with Muse's bundled browser-app delivery skill."""
        return await MuseCommands._call(NativeThreadOperation.RUN_MUSE_BROWSER_APP, skill=MuseSkill.BROWSER_APP.value, text=description, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def _call(
        operation: NativeThreadOperation,
        *,
        skill: str | None = None,
        text: str,
        api_key: str,
        workspace: str | Path,
        model: str | None,
        skills: Sequence[str | Path],
        config: MuseThreadConfig | None,
    ) -> NativeThreadResult:
        # One guarded try per call: cancellation and the feature's own
        # errors pass through, a refused argument names the argument,
        # and anything else is a defect named only by its class.
        errors = NativeErrorFactory(NativeHarness.MUSE, operation)
        request: NativeThreadRequest | None = None
        try:
            # Check the text under its public name first, also against
            # the Windows command-line budget, so a refusal never names
            # the prompt the SDK builds (spec D-25).
            field = native_threads.NATIVE_TEXT_ARGUMENTS[operation]
            RecordFieldValidator.require_text(text, field, max_chars=native_threads.NATIVE_COMMAND_TEXT_MAX_CHARS, pattern=native_threads.NATIVE_COMMAND_TEXT_PATTERN)
            if sys.platform == native_threads.NATIVE_WINDOWS_PLATFORM:
                RecordFieldValidator.require_command_line_units(text, field, max_units=native_threads.NATIVE_WINDOWS_COMMAND_TEXT_MAX_UNITS)

            # The run is a new thread; the skill id is checked as the
            # request's command under the name skill.
            request = NativeThreadRequest(harness=NativeHarness.MUSE, verb=NativeThreadVerb.RUN, prompt=text, api_key=api_key, workspace=workspace, model=model, skills=skills, command=skill)
            settings = MuseThreadConfig() if config is None else RecordFieldConverter.require_instance(config, native_threads.NATIVE_CONFIG_ARGUMENT, MuseThreadConfig)

            # A skill run asks for the skill and is proven by read_skill
            # naming it; a goal run asks for create_goal.
            goal = skill is None
            template = native_threads.MUSE_GOAL_PROMPT_TEMPLATE if goal else native_threads.MUSE_SKILL_PROMPT_TEMPLATE
            tool = native_threads.MUSE_CREATE_GOAL_TOOL if goal else native_threads.MUSE_READ_SKILL_TOOL
            return await MuseCommandRun.execute(request, settings, errors, template=template, tool=tool, fragment=request.command)
        except asyncio.CancelledError:
            raise
        except NativeThreadError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, request) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, request) from exc


class MuseCommandRun:
    """One Muse skill run: the exec run with the template prompt, then the keyless evidence read."""

    @staticmethod
    async def execute(request: NativeThreadRequest, config: MuseThreadConfig, errors: NativeErrorFactory, *, template: str, tool: str, fragment: str | None) -> NativeThreadResult:
        # @intent muse-exec-does-not-expand-slash-commands
        # muse exec sends a slash command to the model as plain text,
        # so the prompt asks for the skill or the goal in words, then
        # #1036's run starts the thread with the caller's key.
        prompted = dataclasses.replace(request, prompt=template.format(skill=request.command, prompt=request.prompt))
        result = await MuseThreadRun.execute(prompted, config, errors)
        thread_id = result.thread_id

        # @intent muse-skill-evidence-fails-closed
        # Read the new thread's own items back, with no key, and return
        # only when they hold the tool call that proves the skill ran
        # (spec INV-8); every error from here on names the new thread.
        calls = await MuseHelperRun.tool_calls(prompted, config, errors, thread_id=thread_id)
        if calls is not None:
            NativeCommandEvidence.require(calls, tools=(tool,), fragment=fragment, errors=errors, request=prompted, thread_id=thread_id)
            return result

        # After a compaction the items start past the early call, so
        # the run's own export transcript must hold the tool name and,
        # for a skill, its id (spec D-33).
        transcript = await MuseHelperRun.transcript(prompted, config, errors, thread_id=thread_id)
        NativeCommandEvidence.require_text(transcript, fragment=tool, errors=errors, request=prompted, thread_id=thread_id)
        if fragment is not None:
            NativeCommandEvidence.require_text(transcript, fragment=fragment, errors=errors, request=prompted, thread_id=thread_id)
        return result


__all__ = ["MuseCommandRun", "MuseCommands"]

"""FILE: vidbyte/harnesses/native/opencode/commands.py

PURPOSE: Defines the four public opencode command functions (OpencodeCommands: run_opencode_command, run_opencode_review, run_opencode_init and run_opencode_plan): run one opencode command, or the plan agent, headless once with the caller's key, through #1036's opencode run.
ROLE IN CODEBASE: The functions are bound as module names in vidbyte/harnesses/native/opencode/__init__.py and re-exported from vidbyte.harnesses.native. Each call builds a NativeThreadRequest whose command field is the opencode command name and runs it with OpencodeThreadRun.execute (opencode/threads.py), which adds --command=<name> and sends the arguments on stdin; OpencodeWire.read (opencode/wire.py) maps opencode's unknown-command answer to command_not_run.
ARCHITECTURE NOTE: The evidence that a command ran is opencode's own dispatch (spec D-8): `opencode run --command` refuses an unknown name with "Command not found", which becomes opencode.command_not_run, and runs a known one. The text argument is checked under its public name before anything starts (spec D-25); it travels on stdin, so it can never become a flag (spec INV-9). run_opencode_plan is #1036's run with config.agent set to the plan agent; a config naming another agent is refused. The module holds no literals of its own (spec INV-15).
FUNCTION INVENTORY: OpencodeCommands holds the four public functions and _call, the one guarded try they share.
COMMON MODIFICATION PATTERNS: A new named opencode command is one NativeThreadOperation member, its text name in NATIVE_TEXT_ARGUMENTS, its command word in vidbyte/lib/constants/native_threads.py and one wrapper here.
WHAT NOT TO DO IN THIS FILE: 1. Do not put the key or the arguments on argv; the key travels in OPENCODE_CONFIG_CONTENT and the arguments on stdin. 2. Do not run a second opencode child to verify a command; opencode's dispatch is the evidence (spec D-8). 3. Do not let run_opencode_plan run another agent than plan.
KNOWN EDGE CASES: A project command (.opencode/command/<name>.md) runs like a bundled one, because opencode's dispatch decides (spec D-8). Another vendor error stays run_failed with opencode's text. A workspace opencode.json can add commands and agents; pass only trusted workspaces (spec T-6).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_opencode_commands.py, tests/features/harness_threads/test_harness_threads_helper_arguments.py, tests/features/harness_threads/test_harness_threads_helper_bounds.py, tests/features/harness_threads/test_harness_threads_helper_credentials.py
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Sequence
from pathlib import Path

from vidbyte.harnesses.native.hostkit import NativeErrorFactory
from vidbyte.harnesses.native.opencode.threads import OpencodeThreadRun
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    NativeThreadRequest,
    NativeThreadResult,
    OpencodeThreadConfig,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_threads import (
    NativeHarness,
    NativeThreadOperation,
    NativeThreadVerb,
)
from vidbyte.lib.errors import ConfigurationError, NativeThreadError


class OpencodeCommands:
    """The public opencode command functions: run one opencode command, or the plan agent, headless with the caller's key for the model's provider."""

    @staticmethod
    async def run_opencode_command(command: str, arguments: str = "", *, api_key: str, workspace: str | Path, model: str, skills: Sequence[str | Path] = (), config: OpencodeThreadConfig | None = None) -> NativeThreadResult:
        """Run the opencode command named command with arguments on stdin as one new session; an unknown name is command_not_run."""
        return await OpencodeCommands._call(NativeThreadOperation.RUN_OPENCODE_COMMAND, command=command, text=arguments, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_opencode_review(target: str | None = None, *, api_key: str, workspace: str | Path, model: str, skills: Sequence[str | Path] = (), config: OpencodeThreadConfig | None = None) -> NativeThreadResult:
        """Run opencode's review command on target, or on the uncommitted changes when target is None."""
        return await OpencodeCommands._call(NativeThreadOperation.RUN_OPENCODE_REVIEW, command=native_threads.OPENCODE_REVIEW_COMMAND, text="" if target is None else target, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_opencode_init(*, api_key: str, workspace: str | Path, model: str, skills: Sequence[str | Path] = (), config: OpencodeThreadConfig | None = None) -> NativeThreadResult:
        """Run opencode's init command, which writes or updates AGENTS.md in workspace."""
        return await OpencodeCommands._call(NativeThreadOperation.RUN_OPENCODE_INIT, command=native_threads.OPENCODE_INIT_COMMAND, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def run_opencode_plan(task: str, *, api_key: str, workspace: str | Path, model: str, skills: Sequence[str | Path] = (), config: OpencodeThreadConfig | None = None) -> NativeThreadResult:
        """Run task with opencode's plan agent, which plans without editing; config.agent must be None or plan."""
        return await OpencodeCommands._call(NativeThreadOperation.RUN_OPENCODE_PLAN, text=task, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def _call(
        operation: NativeThreadOperation,
        *,
        command: str | None = None,
        text: str = "",
        api_key: str,
        workspace: str | Path,
        model: str,
        skills: Sequence[str | Path],
        config: OpencodeThreadConfig | None,
    ) -> NativeThreadResult:
        # One guarded try per call: cancellation and the feature's own
        # errors pass through, a refused argument names the argument,
        # and anything else is a defect named only by its class.
        errors = NativeErrorFactory(NativeHarness.OPENCODE, operation)
        request: NativeThreadRequest | None = None
        try:
            # Check the text under its public name first (spec D-25);
            # init takes none, and raw arguments or a review target may
            # be empty.
            field = native_threads.NATIVE_TEXT_ARGUMENTS.get(operation)
            if field is not None:
                RecordFieldValidator.require_text(text, field, max_chars=native_threads.NATIVE_COMMAND_TEXT_MAX_CHARS, pattern=native_threads.NATIVE_COMMAND_TEXT_PATTERN, allow_blank=operation in native_threads.NATIVE_BLANK_TEXT_OPERATIONS)

            # The run is a new session whose stdin is the text, with the
            # command name checked as the request's command (spec D-8).
            request = NativeThreadRequest(harness=NativeHarness.OPENCODE, verb=NativeThreadVerb.RUN, prompt=text, api_key=api_key, workspace=workspace, model=model, skills=skills, command=command)
            settings = OpencodeThreadConfig() if config is None else RecordFieldConverter.require_instance(config, native_threads.NATIVE_CONFIG_ARGUMENT, OpencodeThreadConfig)

            # @intent opencode-plan-runs-only-the-plan-agent
            # The plan function always runs the plan agent; a config that
            # names another agent is refused, not overridden.
            if operation is NativeThreadOperation.RUN_OPENCODE_PLAN:
                if settings.agent not in (None, native_threads.OPENCODE_PLAN_AGENT):
                    raise ConfigurationError(native_threads.OPENCODE_PLAN_AGENT_RULE.format(agent=native_threads.OPENCODE_PLAN_AGENT, got=settings.agent), details={native_threads.NATIVE_FIELD_DETAIL_KEY: native_threads.NATIVE_CONFIG_ARGUMENT})
                settings = dataclasses.replace(settings, agent=native_threads.OPENCODE_PLAN_AGENT)
            return await OpencodeThreadRun.execute(request, settings, errors)
        except asyncio.CancelledError:
            raise
        except NativeThreadError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, request) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, request) from exc


__all__ = ["OpencodeCommands"]

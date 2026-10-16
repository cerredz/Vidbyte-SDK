"""FILE: vidbyte/harnesses/native/grok/threads.py

PURPOSE: Defines the three public Grok Build thread functions (GrokThreads: run_grok_thread, continue_grok_thread, fork_grok_thread) and the flow of one call (GrokThreadRun): find grok, prepare the private Grok home with the caller's skills, run `grok --single` headless once with the caller's key, and read its one JSON answer.
ROLE IN CODEBASE: The functions are bound as module names in vidbyte/harnesses/native/grok/__init__.py and re-exported from vidbyte.harnesses.native. GrokThreadRun uses NativeLauncher, NativeSkillFolders and NativeErrorFactory from hostkit, CliArgv and CliRunner from vidbyte.lib.process, and GrokWire (grok/wire.py) to read the answer.
ARCHITECTURE NOTE: Every call runs grok with GROK_HOME set to a private home under ~/.vidbyte/grok-homes/, keyed by the resolved workspace (spec D-24), so no stored grok login and no file a workspace ships can supply the credential, an endpoint, a hook or a plugin; the caller's key reaches grok only through the child's environment. Continue and fork find the thread because the same workspace always maps to the same home. The module holds no literals of its own (spec INV-15): flags are GrokFlag members and every other value comes from vidbyte/lib/constants/native_threads.py.
FUNCTION INVENTORY: GrokThreads.run_grok_thread, continue_grok_thread and fork_grok_thread are the public functions; GrokThreads._call is the one guarded try they share. GrokThreadRun.execute is the narrated main function of one call; _fallback names the installer's grok, _prepare_home creates the private home and its skills folder, _environment builds the child's environment overlay and _argv builds the command line.
COMMON MODIFICATION PATTERNS: A new Grok option is a GrokThreadConfig field (vidbyte/lib/dataclasses/native_threads.py), a GrokFlag member and one CliOption in _argv. A new failure condition goes in GrokWire.read.
WHAT NOT TO DO IN THIS FILE: 1. Do not put the key on argv or in a file; it travels only in XAI_API_KEY and GROK_CODE_XAI_API_KEY of the child. 2. Do not create the private home inside the workspace, and do not write anything into the workspace. 3. Do not pass an approve-everything permission mode; GrokPermissionMode has none.
KNOWN EDGE CASES: Concurrent Grok calls in one workspace share one private home, so calls whose skill sets differ can collide while its skills folder is rebuilt (spec EC-27, an accepted limit; the GROK_LAUNCH_FAILED likely cause says so). An unknown model is not checked first: grok silently uses its default model (EC-25). The default permission mode refuses edits in a headless run (A-3). Grok prints the thread id only in the JSON answer at exit, so a run that fails before exit carries no new id (D-27).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from vidbyte.harnesses.native.grok.wire import GrokWire
from vidbyte.harnesses.native.hostkit import (
    NativeErrorFactory,
    NativeLauncher,
    NativeSkillFolders,
)
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    GrokThreadConfig,
    NativeThreadRequest,
    NativeThreadResult,
)
from vidbyte.lib.dataclasses.process import CliInvocation, CliOption
from vidbyte.lib.dataclasses.validation import RecordFieldConverter
from vidbyte.lib.enums.native_threads import (
    GrokFlag,
    NativeEnvironmentVariable,
    NativeHarness,
    NativeThreadOperation,
    NativeThreadProblem,
    NativeThreadVerb,
)
from vidbyte.lib.enums.process import CliOptionStyle
from vidbyte.lib.errors import ConfigurationError, NativeThreadError
from vidbyte.lib.process import CliArgv, CliRunner


class GrokThreads:
    """The public Grok Build thread functions: start, continue or fork one thread headless with the caller's key."""

    @staticmethod
    async def run_grok_thread(prompt: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Start a new Grok Build thread in workspace, run prompt once with api_key, and return its id and answer."""
        return await GrokThreads._call(NativeThreadOperation.RUN_GROK_THREAD, NativeThreadVerb.RUN, None, prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def continue_grok_thread(thread_id: str, prompt: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Run prompt once more on the Grok Build thread thread_id, which only the workspace that created it can reach."""
        return await GrokThreads._call(NativeThreadOperation.CONTINUE_GROK_THREAD, NativeThreadVerb.CONTINUE, thread_id, prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def fork_grok_thread(thread_id: str, prompt: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Copy the Grok Build thread thread_id into a new thread, run prompt on the copy, and return the new id."""
        return await GrokThreads._call(NativeThreadOperation.FORK_GROK_THREAD, NativeThreadVerb.FORK, thread_id, prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def _call(operation: NativeThreadOperation, verb: NativeThreadVerb, thread_id: str | None, prompt: str, *, api_key: str, workspace: str | Path, model: str | None, skills: Sequence[str | Path], config: GrokThreadConfig | None) -> NativeThreadResult:
        # One guarded try per call: cancellation and the feature's own
        # errors pass through, a refused argument names the argument,
        # and anything else is a defect named only by its class.
        errors = NativeErrorFactory(NativeHarness.GROK, operation)
        request: NativeThreadRequest | None = None
        try:
            request = NativeThreadRequest(harness=NativeHarness.GROK, verb=verb, prompt=prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, thread_id=thread_id)
            settings = GrokThreadConfig() if config is None else RecordFieldConverter.require_instance(config, native_threads.NATIVE_CONFIG_ARGUMENT, GrokThreadConfig)
            return await GrokThreadRun.execute(request, settings, errors)
        except asyncio.CancelledError:
            raise
        except NativeThreadError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, request) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, request) from exc


class GrokThreadRun:
    """One Grok Build call: launcher, private home, environment, argv, run and answer."""

    @staticmethod
    async def execute(request: NativeThreadRequest, config: GrokThreadConfig, errors: NativeErrorFactory) -> NativeThreadResult:
        # Find grok: the caller's command, then PATH, then the copy the
        # Grok installer puts under the user's home folder.
        launcher = NativeLauncher.resolve(config.grok_command, program=native_threads.GROK_PROGRAM, fallback=GrokThreadRun._fallback(), errors=errors, request=request)

        # Prepare the private Grok home for this workspace and put the
        # caller's skills in it, off the event loop.
        home = await asyncio.to_thread(GrokThreadRun._prepare_home, request, errors)

        # From here on the key is scrubbed from anything grok prints.
        errors.register_secret(request.api_key)

        # Run grok once, headless, in the workspace, with the key and
        # the private home in its environment and no standard input.
        invocation = CliInvocation(
            argv=GrokThreadRun._argv(launcher, request, config),
            env_overlay=GrokThreadRun._environment(request, home),
            timeout_seconds=config.timeout_seconds,
            max_output_bytes=native_threads.GROK_CLI_MAX_OUTPUT_BYTES,
            cwd=Path(request.workspace),
        )
        outcome = await CliRunner().run(invocation)

        # A program the OS would not start is reported with its path.
        if outcome.launch_failure is not None:
            program, *_arguments = launcher
            raise errors.from_launch_failure(outcome.launch_failure, program, request=request)

        # Read the one JSON answer: the thread id and the final text.
        return GrokWire.read(outcome, request, errors, timeout_seconds=config.timeout_seconds)

    @staticmethod
    def _fallback() -> Path | None:
        # The installer's ~/.grok/bin/grok[.exe]; skipped when the user
        # home cannot be determined.
        suffix = native_threads.NATIVE_WINDOWS_EXECUTABLE_SUFFIX if sys.platform == native_threads.NATIVE_WINDOWS_PLATFORM else ""
        try:
            return Path.home().joinpath(*native_threads.GROK_HOME_FOLDERS, native_threads.GROK_PROGRAM + suffix)
        except RuntimeError:
            return None

    @staticmethod
    def _prepare_home(request: NativeThreadRequest, errors: NativeErrorFactory) -> Path:
        # @intent grok-home-stays-outside-the-workspace
        # Grok trusts everything under GROK_HOME as user scope, so the
        # home lives under the user's home folder, never in the
        # workspace a repository controls; its key is a hash of the
        # resolved workspace so a continue finds the same home.
        key = hashlib.sha256(os.path.normcase(str(request.workspace)).encode()).hexdigest()[: native_threads.GROK_HOME_KEY_HEX_CHARS]
        try:
            home = Path.home().joinpath(*native_threads.GROK_PRIVATE_HOMES_PARTS, key)
        except RuntimeError as exc:
            raise errors.failure(NativeThreadProblem.LAUNCH_FAILED, request=request, searched=native_threads.GROK_HOME_UNKNOWN_DETAIL.format(error_type=type(exc).__name__)) from exc
        try:
            home.mkdir(parents=True, exist_ok=True)
            NativeSkillFolders.replace(tuple(Path(skill) for skill in request.skills), home / native_threads.GROK_SKILLS_DIR)
        except OSError as exc:
            detail = native_threads.GROK_HOME_FAILURE_DETAIL.format(home=home, error_type=type(exc).__name__, reason=exc.strerror or type(exc).__name__)
            raise errors.failure(NativeThreadProblem.LAUNCH_FAILED, request=request, searched=detail) from exc
        return home

    @staticmethod
    def _environment(request: NativeThreadRequest, home: Path) -> dict[str, str]:
        # @intent grok-key-wins-through-a-private-home
        # The private home holds no login, so the key passed here is the
        # only credential grok can use; both names carry it because the
        # precedence of the legacy alias is unknown. Self-update is off.
        return {
            NativeEnvironmentVariable.XAI_API_KEY.value: request.api_key,
            NativeEnvironmentVariable.GROK_CODE_XAI_API_KEY.value: request.api_key,
            NativeEnvironmentVariable.GROK_HOME.value: str(home),
            NativeEnvironmentVariable.GROK_DISABLE_AUTOUPDATER.value: native_threads.NATIVE_ENABLED_SWITCH,
        }

    @staticmethod
    def _argv(launcher: tuple[str, ...], request: NativeThreadRequest, config: GrokThreadConfig) -> tuple[str, ...]:
        # Every option is one --flag=value element, and the prompt
        # travels inside --single=, so it can never become a flag.
        options = [
            CliOption(GrokFlag.OUTPUT_FORMAT, native_threads.GROK_JSON_OUTPUT_FORMAT),
            CliOption(GrokFlag.CWD, str(request.workspace)),
            CliOption(GrokFlag.PERMISSION_MODE, config.permission_mode.value),
        ]
        if request.model is not None:
            options.append(CliOption(GrokFlag.MODEL, request.model))
        if config.reasoning_effort is not None:
            options.append(CliOption(GrokFlag.REASONING_EFFORT, config.reasoning_effort.value))
        if request.thread_id is not None:
            options.append(CliOption(GrokFlag.RESUME, request.thread_id))
        if request.verb is NativeThreadVerb.FORK:
            options.append(CliOption(GrokFlag.FORK_SESSION))
        options.append(CliOption(GrokFlag.SINGLE, request.prompt))
        return CliArgv.build(launcher, options=tuple(options), style=CliOptionStyle.JOINED)


__all__ = ["GrokThreadRun", "GrokThreads"]

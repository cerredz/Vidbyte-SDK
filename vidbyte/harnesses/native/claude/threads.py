"""FILE: vidbyte/harnesses/native/claude/threads.py

PURPOSE: Defines the three public Claude Code thread functions (ClaudeThreads: run_claude_thread, continue_claude_thread, fork_claude_thread) and the flow of one call (ClaudeThreadRun): find claude, prepare the private config folder with the caller's skills, run `claude --print` headless once with the caller's key and the prompt on stdin, and read its one JSON answer.
ROLE IN CODEBASE: The functions are bound as module names in vidbyte/harnesses/native/claude/__init__.py and re-exported from vidbyte.harnesses.native. ClaudeThreadRun uses NativeLauncher, NativePrivateFolders and NativeErrorFactory from hostkit, CliArgv and CliRunner from vidbyte.lib.process, and ClaudeWire (claude/wire.py) to read the answer.
ARCHITECTURE NOTE: Every call runs claude with CLAUDE_CONFIG_DIR set to a private config folder under ~/.vidbyte/claude-configs/, keyed by the resolved workspace, with every inherited ANTHROPIC_* and CLAUDE* variable left out and with --setting-sources user, so no stored claude login, no inherited credential and no settings file a workspace ships can supply the credential, an endpoint, a hook or an MCP server; the caller's key reaches claude only as ANTHROPIC_API_KEY in the child's environment. Continue and fork find the thread because the same workspace always maps to the same folder. The module holds no literals of its own (spec INV-16): flags are ClaudeFlag members and every other value comes from vidbyte/lib/constants/native_threads.py.
FUNCTION INVENTORY: ClaudeThreads.run_claude_thread, continue_claude_thread and fork_claude_thread are the public functions; ClaudeThreads._call is the one guarded try they share. ClaudeThreadRun.execute is the narrated main function of one call and prepares the private config folder and its skills folder through NativePrivateFolders.prepare; _fallback names the native installer's claude, _environment builds the child's environment overlay, _inherited_names lists the caller's variables the child must not inherit and _argv builds the command line.
COMMON MODIFICATION PATTERNS: A new Claude Code option is a ClaudeThreadConfig field (vidbyte/lib/dataclasses/native_threads.py), a ClaudeFlag member and one CliOption in _argv. A new failure condition goes in ClaudeWire.read.
WHAT NOT TO DO IN THIS FILE: 1. Do not put the key on argv, on stdin or in a file; it travels only in ANTHROPIC_API_KEY of the child. 2. Do not create the private config folder inside the workspace, and do not write anything into the workspace or the user's ~/.claude. 3. Do not pass an approve-everything permission mode or --dangerously-skip-permissions; ClaudePermissionMode has none. 4. Do not drop --setting-sources user; it is what keeps a workspace's settings, hooks and MCP servers from loading.
KNOWN EDGE CASES: A wrong or revoked key is retried by Claude Code for about three minutes before it reports key_rejected, so a shorter timeout_seconds reports timed_out instead (spec EC-4). The workspace's own CLAUDE.md, skills, agents, commands and .mcp.json are not loaded, and neither are the user's ~/.claude settings (EC-10). A headless run denies every request its permission mode would prompt for and goes on, so the answer says what it could not do (EC-20, A-2). Concurrent calls in one workspace share one config folder, so calls whose skill sets differ can collide while its skills folder is rebuilt (EC-21, an accepted limit; the CLAUDE_LAUNCH_FAILED likely cause says so). The SDK never removes a config folder; its transcripts are plain text that Claude Code sweeps after 30 days (EC-28), and Claude Code's auto memory notes there reach every later thread of the workspace and are never swept (EC-37). The thread id is read only from the JSON answer at exit, so a run that fails before exit carries no new id (D-9).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_claude_argv.py, tests/features/harness_threads/test_harness_threads_claude_credentials.py, tests/features/harness_threads/test_harness_threads_claude_launcher.py, tests/features/harness_threads/test_harness_threads_claude_acceptance.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from vidbyte.harnesses.native.claude.wire import ClaudeWire
from vidbyte.harnesses.native.hostkit import (
    NativeErrorFactory,
    NativeLauncher,
    NativePrivateFolders,
)
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    ClaudeThreadConfig,
    NativeThreadRequest,
    NativeThreadResult,
)
from vidbyte.lib.dataclasses.process import CliInvocation, CliOption
from vidbyte.lib.dataclasses.validation import RecordFieldConverter
from vidbyte.lib.enums.native_threads import (
    ClaudeFlag,
    NativeEnvironmentVariable,
    NativeHarness,
    NativeThreadOperation,
    NativeThreadVerb,
)
from vidbyte.lib.enums.process import CliOptionStyle
from vidbyte.lib.errors import ConfigurationError, NativeThreadError
from vidbyte.lib.process import CliArgv, CliRunner


class ClaudeThreads:
    """The public Claude Code thread functions: start, continue or fork one thread headless with the caller's key."""

    @staticmethod
    async def run_claude_thread(prompt: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: ClaudeThreadConfig | None = None) -> NativeThreadResult:
        """Start a new Claude Code thread in workspace, run prompt once with api_key, and return its id and answer."""
        return await ClaudeThreads._call(NativeThreadOperation.RUN_CLAUDE_THREAD, NativeThreadVerb.RUN, None, prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def continue_claude_thread(thread_id: str, prompt: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: ClaudeThreadConfig | None = None) -> NativeThreadResult:
        """Run prompt once more on the Claude Code thread thread_id, which only the workspace that created it can reach."""
        return await ClaudeThreads._call(NativeThreadOperation.CONTINUE_CLAUDE_THREAD, NativeThreadVerb.CONTINUE, thread_id, prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def fork_claude_thread(thread_id: str, prompt: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: ClaudeThreadConfig | None = None) -> NativeThreadResult:
        """Copy the Claude Code thread thread_id into a new thread, run prompt on the copy, and return the new id."""
        return await ClaudeThreads._call(NativeThreadOperation.FORK_CLAUDE_THREAD, NativeThreadVerb.FORK, thread_id, prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def _call(operation: NativeThreadOperation, verb: NativeThreadVerb, thread_id: str | None, prompt: str, *, api_key: str, workspace: str | Path, model: str | None, skills: Sequence[str | Path], config: ClaudeThreadConfig | None) -> NativeThreadResult:
        # One guarded try per call: cancellation and the feature's own
        # errors pass through, a refused argument names the argument,
        # and anything else is a defect named only by its class.
        errors = NativeErrorFactory(NativeHarness.CLAUDE, operation)
        request: NativeThreadRequest | None = None
        try:
            request = NativeThreadRequest(harness=NativeHarness.CLAUDE, verb=verb, prompt=prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, thread_id=thread_id)
            settings = ClaudeThreadConfig() if config is None else RecordFieldConverter.require_instance(config, native_threads.NATIVE_CONFIG_ARGUMENT, ClaudeThreadConfig)
            return await ClaudeThreadRun.execute(request, settings, errors)
        except asyncio.CancelledError:
            raise
        except NativeThreadError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, request) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, request) from exc


class ClaudeThreadRun:
    """One Claude Code call: launcher, private config folder, environment, argv, run and answer."""

    @staticmethod
    async def execute(request: NativeThreadRequest, config: ClaudeThreadConfig, errors: NativeErrorFactory) -> NativeThreadResult:
        # Find claude: the caller's command, then PATH, then the copy
        # the native installer puts under the user's home folder.
        launcher = NativeLauncher.resolve(config.claude_command, program=native_threads.CLAUDE_PROGRAM, fallback=ClaudeThreadRun._fallback(), errors=errors, request=request)

        # Prepare the private config folder for this workspace and put
        # the caller's skills in it, off the event loop.
        config_dir = await asyncio.to_thread(
            NativePrivateFolders.prepare,
            request,
            errors,
            parts=native_threads.CLAUDE_PRIVATE_CONFIGS_PARTS,
            key_hex_chars=native_threads.CLAUDE_CONFIG_KEY_HEX_CHARS,
            skills_dir=native_threads.CLAUDE_SKILLS_DIR,
            unknown_detail=native_threads.CLAUDE_CONFIG_UNKNOWN_DETAIL,
            failure_detail=native_threads.CLAUDE_CONFIG_FAILURE_DETAIL,
        )

        # From here on the key is scrubbed from anything claude prints.
        errors.register_secret(request.api_key)

        # Run claude once, headless, in the workspace: the key and the
        # private folder in its environment, the caller's own Anthropic
        # and Claude variables left out, and the prompt on stdin.
        invocation = CliInvocation(
            argv=ClaudeThreadRun._argv(launcher, request, config),
            env_overlay=ClaudeThreadRun._environment(request, config_dir),
            env_remove=ClaudeThreadRun._inherited_names(),
            timeout_seconds=config.timeout_seconds,
            max_output_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES,
            cwd=Path(request.workspace),
            stdin_text=request.prompt,
        )
        outcome = await CliRunner().run(invocation)

        # A program the OS would not start is reported with its path.
        if outcome.launch_failure is not None:
            program, *_arguments = launcher
            raise errors.from_launch_failure(outcome.launch_failure, program, request=request)

        # Read the one JSON answer: the thread id and the final text.
        return ClaudeWire.read(outcome, request, errors, timeout_seconds=config.timeout_seconds)

    @staticmethod
    def _fallback() -> Path | None:
        # The native installer's ~/.local/bin/claude[.exe]; skipped when
        # the user home cannot be determined.
        suffix = native_threads.NATIVE_WINDOWS_EXECUTABLE_SUFFIX if sys.platform == native_threads.NATIVE_WINDOWS_PLATFORM else ""
        try:
            return Path.home().joinpath(*native_threads.CLAUDE_INSTALL_FOLDERS, native_threads.CLAUDE_PROGRAM + suffix)
        except RuntimeError:
            return None

    @staticmethod
    def _environment(request: NativeThreadRequest, config_dir: Path) -> dict[str, str]:
        # @intent claude-key-wins-through-a-private-config
        # The private config folder holds no login, so the key passed
        # here is the only credential claude can use. Self-update and
        # the traffic that is not needed for the run are off.
        return {
            NativeEnvironmentVariable.ANTHROPIC_API_KEY.value: request.api_key,
            NativeEnvironmentVariable.CLAUDE_CONFIG_DIR.value: str(config_dir),
            NativeEnvironmentVariable.DISABLE_AUTOUPDATER.value: native_threads.NATIVE_ENABLED_SWITCH,
            NativeEnvironmentVariable.CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC.value: native_threads.NATIVE_ENABLED_SWITCH,
        }

    @staticmethod
    def _inherited_names() -> tuple[str, ...]:
        # @intent claude-child-drops-inherited-credentials
        # Every ANTHROPIC_* and CLAUDE* variable of the caller is left
        # out, so no inherited token, endpoint, cloud provider or config
        # folder can stand in for the caller's key; only the Git Bash
        # path Claude Code needs on Windows is kept.
        return tuple(name for name in os.environ if name.startswith(native_threads.CLAUDE_INHERITED_ENVIRONMENT_PREFIXES) and name not in native_threads.CLAUDE_INHERITED_ENVIRONMENT_KEPT)

    @staticmethod
    def _argv(launcher: tuple[str, ...], request: NativeThreadRequest, config: ClaudeThreadConfig) -> tuple[str, ...]:
        # @intent claude-workspace-settings-never-load
        # Only the user settings source is read, and that is the private
        # config folder, so no settings file of the workspace can add an
        # env block, a key helper, a hook or an MCP server. Each value
        # is a separate element and the prompt is never one.
        options = [
            CliOption(ClaudeFlag.PRINT),
            CliOption(ClaudeFlag.OUTPUT_FORMAT, native_threads.CLAUDE_JSON_OUTPUT_FORMAT),
            CliOption(ClaudeFlag.SETTING_SOURCES, native_threads.CLAUDE_USER_SETTING_SOURCE),
            CliOption(ClaudeFlag.PERMISSION_MODE, config.permission_mode.value),
        ]
        if request.model is not None:
            options.append(CliOption(ClaudeFlag.MODEL, request.model))
        if config.reasoning_effort is not None:
            options.append(CliOption(ClaudeFlag.EFFORT, config.reasoning_effort.value))
        if request.thread_id is not None:
            options.append(CliOption(ClaudeFlag.RESUME, request.thread_id))
        if request.verb is NativeThreadVerb.FORK:
            options.append(CliOption(ClaudeFlag.FORK_SESSION))
        return CliArgv.build(launcher, options=tuple(options), style=CliOptionStyle.SEPARATE)


__all__ = ["ClaudeThreadRun", "ClaudeThreads"]

"""FILE: vidbyte/harnesses/native/opencode/threads.py

PURPOSE: Defines the three public opencode thread functions (OpencodeThreads: run_opencode_thread, continue_opencode_thread, fork_opencode_thread) and the flow of one call (OpencodeThreadRun): find opencode, bind the caller's key to the model's provider in an inline config, run `opencode run --format=json` headless once with the prompt on stdin, and read its JSON events.
ROLE IN CODEBASE: The functions are bound as module names in vidbyte/harnesses/native/opencode/__init__.py and re-exported from vidbyte.harnesses.native. OpencodeThreadRun uses NativeLauncher and NativeErrorFactory from hostkit, CliArgv and CliRunner from vidbyte.lib.process, and OpencodeWire (opencode/wire.py) to build the config and read the events. GLM and DeepSeek are reached through the model argument ("zai-coding-plan/glm-5.3", "deepseek/deepseek-v4-pro").
ARCHITECTURE NOTE: The key reaches opencode only inside OPENCODE_CONFIG_CONTENT, whose provider apiKey beats a stored auth.json login (spec D-8); the caller's skill folders are listed in the same config and read in place, never copied. The prompt travels on stdin, so no prompt can become a flag and no prompt length meets the argv limit. The module holds no literals of its own (spec INV-15): flags are OpencodeFlag members and every other value comes from vidbyte/lib/constants/native_threads.py.
FUNCTION INVENTORY: OpencodeThreads.run_opencode_thread, continue_opencode_thread and fork_opencode_thread are the public functions; OpencodeThreads._call is the one guarded try they share. OpencodeThreadRun.execute is the narrated main function of one call; _environment builds the child's environment overlay and _argv builds the command line.
COMMON MODIFICATION PATTERNS: A new opencode option is an OpencodeThreadConfig field (vidbyte/lib/dataclasses/native_threads.py), an OpencodeFlag member and one CliOption in _argv. A new failure condition goes in OpencodeWire.read.
WHAT NOT TO DO IN THIS FILE: 1. Do not put the key on argv, on stdin or in a file; it travels only inside OPENCODE_CONFIG_CONTENT of the child. 2. Do not drop --dir or the cwd; an inherited PWD must never choose the project. 3. Do not copy skills; opencode reads the folders the caller passed.
KNOWN EDGE CASES: opencode also reads the workspace's own opencode.json, so a workspace can add providers, agents or plugins; pass only trusted workspaces (spec T-6). The key works only for providers that take an API key (EC-39). An unknown provider or model is reported by opencode and becomes run_failed with its text (EC-24).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

from vidbyte.harnesses.native.hostkit import NativeErrorFactory, NativeLauncher
from vidbyte.harnesses.native.opencode.wire import OpencodeWire
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    NativeThreadRequest,
    NativeThreadResult,
    OpencodeThreadConfig,
)
from vidbyte.lib.dataclasses.process import CliInvocation, CliOption
from vidbyte.lib.dataclasses.validation import RecordFieldConverter
from vidbyte.lib.enums.native_threads import (
    NativeEnvironmentVariable,
    NativeHarness,
    NativeThreadOperation,
    NativeThreadVerb,
    OpencodeFlag,
)
from vidbyte.lib.enums.process import CliOptionStyle
from vidbyte.lib.errors import ConfigurationError, NativeThreadError
from vidbyte.lib.process import CliArgv, CliRunner


class OpencodeThreads:
    """The public opencode thread functions: start, continue or fork one session headless with the caller's key for the model's provider."""

    @staticmethod
    async def run_opencode_thread(prompt: str, *, api_key: str, workspace: str | Path, model: str, skills: Sequence[str | Path] = (), config: OpencodeThreadConfig | None = None) -> NativeThreadResult:
        """Start a new opencode session in workspace, run prompt once on model with api_key, and return its id and answer."""
        return await OpencodeThreads._call(NativeThreadOperation.RUN_OPENCODE_THREAD, NativeThreadVerb.RUN, None, prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def continue_opencode_thread(thread_id: str, prompt: str, *, api_key: str, workspace: str | Path, model: str, skills: Sequence[str | Path] = (), config: OpencodeThreadConfig | None = None) -> NativeThreadResult:
        """Run prompt once more on the opencode session thread_id."""
        return await OpencodeThreads._call(NativeThreadOperation.CONTINUE_OPENCODE_THREAD, NativeThreadVerb.CONTINUE, thread_id, prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def fork_opencode_thread(thread_id: str, prompt: str, *, api_key: str, workspace: str | Path, model: str, skills: Sequence[str | Path] = (), config: OpencodeThreadConfig | None = None) -> NativeThreadResult:
        """Copy the opencode session thread_id into a new session, run prompt on the copy, and return the new id."""
        return await OpencodeThreads._call(NativeThreadOperation.FORK_OPENCODE_THREAD, NativeThreadVerb.FORK, thread_id, prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def _call(operation: NativeThreadOperation, verb: NativeThreadVerb, thread_id: str | None, prompt: str, *, api_key: str, workspace: str | Path, model: str, skills: Sequence[str | Path], config: OpencodeThreadConfig | None) -> NativeThreadResult:
        # One guarded try per call: cancellation and the feature's own
        # errors pass through, a refused argument names the argument,
        # and anything else is a defect named only by its class.
        errors = NativeErrorFactory(NativeHarness.OPENCODE, operation)
        request: NativeThreadRequest | None = None
        try:
            request = NativeThreadRequest(harness=NativeHarness.OPENCODE, verb=verb, prompt=prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, thread_id=thread_id)
            settings = OpencodeThreadConfig() if config is None else RecordFieldConverter.require_instance(config, native_threads.NATIVE_CONFIG_ARGUMENT, OpencodeThreadConfig)
            return await OpencodeThreadRun.execute(request, settings, errors)
        except asyncio.CancelledError:
            raise
        except NativeThreadError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, request) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, request) from exc


class OpencodeThreadRun:
    """One opencode call: launcher, inline config, environment, argv, run and events."""

    @staticmethod
    async def execute(request: NativeThreadRequest, config: OpencodeThreadConfig, errors: NativeErrorFactory) -> NativeThreadResult:
        # Find opencode: the caller's command, then PATH.
        launcher = NativeLauncher.resolve(config.opencode_command, program=native_threads.OPENCODE_PROGRAM, fallback=None, errors=errors, request=request)

        # From here on the key, and the config value that holds it, are
        # scrubbed from anything opencode prints.
        content = OpencodeWire.config_content(request)
        errors.register_secret(request.api_key)
        errors.register_secret(content)

        # @intent opencode-prompt-travels-on-stdin
        # Run opencode once, headless, in the workspace, with the inline
        # config in its environment and the prompt on stdin followed by
        # end of input, so the prompt is never read as an option.
        invocation = CliInvocation(
            argv=OpencodeThreadRun._argv(launcher, request, config),
            env_overlay=OpencodeThreadRun._environment(content),
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

        # Read the JSON events: the session id and the final text.
        return OpencodeWire.read(outcome, request, errors, timeout_seconds=config.timeout_seconds)

    @staticmethod
    def _environment(content: str) -> dict[str, str]:
        # @intent opencode-key-wins-through-inline-config
        # The inline config binds the key to the model's provider and
        # beats a stored auth.json login; self-update is off.
        return {
            NativeEnvironmentVariable.OPENCODE_CONFIG_CONTENT.value: content,
            NativeEnvironmentVariable.OPENCODE_DISABLE_AUTOUPDATE.value: native_threads.NATIVE_ENABLED_SWITCH,
        }

    @staticmethod
    def _argv(launcher: tuple[str, ...], request: NativeThreadRequest, config: OpencodeThreadConfig) -> tuple[str, ...]:
        # @intent opencode-dir-is-always-explicit
        # Every option is one --flag=value element; --dir always names
        # the resolved workspace, so an inherited PWD never chooses the
        # project.
        options = [
            CliOption(OpencodeFlag.FORMAT, native_threads.OPENCODE_JSON_FORMAT),
            CliOption(OpencodeFlag.DIR, str(request.workspace)),
            CliOption(OpencodeFlag.MODEL, request.model),
        ]
        if config.agent is not None:
            options.append(CliOption(OpencodeFlag.AGENT, config.agent))
        if config.variant is not None:
            options.append(CliOption(OpencodeFlag.VARIANT, config.variant))
        if request.thread_id is not None:
            options.append(CliOption(OpencodeFlag.SESSION, request.thread_id))
        if request.verb is NativeThreadVerb.FORK:
            options.append(CliOption(OpencodeFlag.FORK))
        return CliArgv.build(launcher, command=(native_threads.OPENCODE_RUN_COMMAND,), options=tuple(options), style=CliOptionStyle.JOINED)


__all__ = ["OpencodeThreadRun", "OpencodeThreads"]

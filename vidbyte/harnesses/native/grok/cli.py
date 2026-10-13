"""FILE: vidbyte/harnesses/native/grok/cli.py

PURPOSE: Defines GrokCli, which finds the Grok Build launcher, builds every argv GrokHost runs (grok --version, grok models, the one-shot and fork runs, and the `grok agent --no-leader ... stdio` peer) and runs the command-line ones through CliRunner.
ROLE IN CODEBASE: Owned by GrokHost in vidbyte/harnesses/native/grok/host.py; the host calls resolve_launcher at __aenter__, peer_argv when it starts a NativePeer, and run for every bounded CLI run. GrokWire then reads the CliOutcome.
ARCHITECTURE NOTE: Argument building only; no output parsing and no error mapping, which belong to GrokWire. Every caller-supplied value travels inside one --name=value element, so a prompt or rule that looks like a flag stays a value (T-2). Children get the caller's environment (D-18) and the workspace as their working folder.
FUNCTION INVENTORY: resolve_launcher finds grok (D-19); peer_argv, version_argv, models_argv, one_shot_argv and fork_argv build argv tuples; run executes one argv with a time bound and the output cap.
COMMON MODIFICATION PATTERNS: A new Grok flag is one more --name=value element in the builder that needs it; a new CLI run is one more builder plus a run call in the host.
WHAT NOT TO DO IN THIS FILE: 1. Do not pass any approve-everything flag (--always-approve and the like); the permission mode comes only from GrokPermissionMode (INV-9). 2. Do not put a value in its own argv element after a flag. 3. Do not check that an explicit grok_command exists; launch failures are mapped when it runs.
KNOWN EDGE CASES: On Windows shutil.which returns the grok.cmd shim, which CliRunner and the peer transport start like any program. The home fallback is ~/.grok/bin/grok, with .exe on Windows, and is used only when it is a file.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Grok host), §6.3.3, D-2, D-18, D-19, T-2
TESTS: tests/features/grok_host/test_grok_host_reads.py, tests/features/grok_host/test_grok_host_turns.py, tests/features/grok_host/test_grok_host_acceptance.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from vidbyte.harnesses.native.hostkit import NativeChildEnvironment
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.grok import GrokHostSettings, GrokOneShotRequest
from vidbyte.lib.dataclasses.process import CliInvocation, CliOutcome
from vidbyte.lib.process import CliRunner

_PROGRAM = "grok"
_HOME_FOLDERS = (".grok", "bin")
_WINDOWS_SUFFIX = ".exe"
_PEER_PREFIX = ("agent", "--no-leader")
_PEER_SUFFIX = ("stdio",)
_VERSION_ARGS = ("--version",)
_MODELS_ARGS = ("models",)
_JSON_OUTPUT = "--output-format=json"
_FORK_FLAG = "--fork-session"


class GrokCli:
    """Finds the Grok Build launcher and builds and runs its command lines."""

    def __init__(self, settings: GrokHostSettings) -> None:
        self._settings = settings
        self._launcher: tuple[str, ...] = settings.grok_command or ()
        self._runner = CliRunner()

    def resolve_launcher(self) -> bool:
        # @intent grok-launcher-resolution-order
        # D-19: an explicit grok_command wins and is never checked, because a
        # launch failure is mapped when it runs; otherwise grok on PATH, then
        # the installer's ~/.grok/bin/grok. False means none was found.
        if self._launcher:
            return True
        found = shutil.which(_PROGRAM)
        home = Path.home().joinpath(*_HOME_FOLDERS, _PROGRAM + (_WINDOWS_SUFFIX if sys.platform == "win32" else ""))
        if found is None and home.is_file():
            found = str(home)
        self._launcher = (found,) if found is not None else ()
        return bool(self._launcher)

    def peer_argv(self, model: str | None, reasoning_effort: str | None) -> tuple[str, ...]:
        # D-2: agent --no-leader [--model=<id>] [--reasoning-effort=<effort>] stdio.
        flags = self._model_flags(model, reasoning_effort)
        return (*self._launcher, *_PEER_PREFIX, *flags, *_PEER_SUFFIX)

    def version_argv(self) -> tuple[str, ...]:
        # grok --version prints "grok <major>.<minor>.<patch> (...)".
        return (*self._launcher, *_VERSION_ARGS)

    def models_argv(self) -> tuple[str, ...]:
        # grok models lists the models, or prints the signed-out line.
        return (*self._launcher, *_MODELS_ARGS)

    def one_shot_argv(self, one_shot: GrokOneShotRequest) -> tuple[str, ...]:
        # One headless run in the workspace with JSON output and the run's own permission mode and rules.
        return (*self._launcher, *self._run_flags(one_shot), "--single=" + one_shot.prompt)

    def fork_argv(self, session_id: str, one_shot: GrokOneShotRequest, new_session_id: str | None) -> tuple[str, ...]:
        # A one-shot run that resumes the source session as a fork, under new_session_id when one is given.
        target = ("--session-id=" + new_session_id,) if new_session_id is not None else ()
        fork = ("--resume=" + session_id, _FORK_FLAG, *target)
        return (*self._launcher, *fork, *self._run_flags(one_shot), "--single=" + one_shot.prompt)

    async def run(self, argv: tuple[str, ...], *, timeout_seconds: float) -> CliOutcome:
        # @intent grok-cli-runs-are-bounded
        # Every CLI run is time-bounded and its output capped by CliRunner,
        # which stops the whole tree on timeout or cancellation; the child
        # gets the caller's environment and the workspace as its folder.
        invocation = CliInvocation(
            argv=argv,
            env=NativeChildEnvironment.build({}),
            timeout_seconds=timeout_seconds,
            max_output_bytes=native_host_constants.GROK_CLI_MAX_OUTPUT_BYTES,
            cwd=self._settings.workspace,
        )
        return await self._runner.run(invocation)

    def _run_flags(self, one_shot: GrokOneShotRequest) -> tuple[str, ...]:
        # @intent grok-one-shot-permissions-come-from-the-record
        # The flags a one-shot and a fork run share, every value in
        # --name=value form; the permission mode and the allow and deny rules
        # come only from the validated record, never an approve-everything
        # flag (INV-9, T-2).
        fixed = (_JSON_OUTPUT, "--permission-mode=" + one_shot.permission_mode.value, "--cwd=" + str(self._settings.workspace))
        rules = tuple("--allow=" + rule for rule in one_shot.allow_rules) + tuple("--deny=" + rule for rule in one_shot.deny_rules)
        turns = ("--max-turns=" + str(one_shot.max_turns),) if one_shot.max_turns is not None else ()
        model = ("--model=" + one_shot.model,) if one_shot.model is not None else ()
        effort = ("--reasoning-effort=" + one_shot.reasoning_effort,) if one_shot.reasoning_effort is not None else ()
        return (*fixed, *model, *effort, *rules, *turns)

    @staticmethod
    def _model_flags(model: str | None, reasoning_effort: str | None) -> tuple[str, ...]:
        # The optional model and effort flags of a peer.
        model_flag = ("--model=" + model,) if model is not None else ()
        effort_flag = ("--reasoning-effort=" + reasoning_effort,) if reasoning_effort is not None else ()
        return (*model_flag, *effort_flag)


__all__ = ["GrokCli"]

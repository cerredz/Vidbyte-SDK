"""FILE: vidbyte/harnesses/native/muse/launcher.py

PURPOSE: Defines MuseLauncher, which decides how one Muse call starts `muse` (an explicit muse_command, `wsl.exe -d <distro> -e <muse_path>` on Windows, or muse on PATH), shows each path the way muse sees it, builds the WSL environment (the peer mark and the WSLENV entries), explains WSL launch failures and reaps the marked processes inside the distro; and MusePathTranslator, which maps a Windows path to its /mnt form inside WSL.
ROLE IN CODEBASE: Built once per call by MuseThreadRun (vidbyte/harnesses/native/muse/threads.py) with the call's MuseThreadConfig and NativeErrorFactory. Runs `wsl.exe -l -q` and the reap through CliRunner (vidbyte/lib/process/runner.py); muse itself is started by MuseThreadRun.
ARCHITECTURE NOTE: In WSL mode every muse child carries a fresh VIDBYTE_PEER_MARK, forwarded through WSLENV with the overlay names, so the reap `sh -s <mark>` (MUSE_REAP_SCRIPT on stdin, run with the caller's environment, which lacks the mark) kills exactly that call's in-distro tree. Only names the SDK put in the overlay are forwarded, never names taken from the caller's environment, so a caller's own META_API_KEY never reaches `muse serve`. Every flag is a WslFlag or ShellFlag member and every other value comes from vidbyte/lib/constants/native_threads.py (spec INV-15).
FUNCTION INVENTORY: MusePathTranslator.to_wsl maps a drive path to /mnt/<drive>/... MuseLauncher: wsl_mode says whether WSL launches muse; resolve finds the launcher prefix or raises; visible_path gives a path as muse sees it; new_mark mints a peer mark; environment adds the mark and WSLENV to an overlay; launch_failure turns WSL failure text into its error; list_distros runs `wsl.exe -l -q`; reap runs the in-distro reap.
COMMON MODIFICATION PATTERNS: A new launch mode is one more branch in resolve and, if it crosses an OS boundary, a forwarding rule in environment; a new WSL failure text is one more marker in launch_failure.
WHAT NOT TO DO IN THIS FILE: 1. Do not run anything through a shell; argv goes to CliRunner as a tuple built by CliArgv (S055). 2. Do not forward a variable into WSL that the overlay does not hold. 3. Do not read or log the value of META_API_KEY.
KNOWN EDGE CASES: `wsl.exe -l -q` prints UTF-16-LE, which CliRunner decodes as UTF-8; dropping the NUL characters keeps ASCII distro names intact. WSL's own error text may also arrive as UTF-16-LE, so NUL characters are dropped before the markers are searched. A UNC or drive-less path has no /mnt form and is refused naming workspace, before anything is written. A reap with a mark that does not match MUSE_PEER_MARK_PATTERN, or outside WSL mode, does nothing. On Windows, muse is never looked up on PATH.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_wsl.py, tests/features/harness_threads/test_harness_threads_launcher.py
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath

from vidbyte.harnesses.native.hostkit import NativeErrorFactory, NativeLauncher
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    MuseThreadConfig,
    NativeThreadRequest,
)
from vidbyte.lib.dataclasses.process import CliInvocation, CliOption, CliOutcome
from vidbyte.lib.enums.native_threads import (
    NativeEnvironmentVariable,
    NativeThreadProblem,
    ShellFlag,
    WslFlag,
)
from vidbyte.lib.enums.process import CliOptionStyle
from vidbyte.lib.errors import ConfigurationError, NativeThreadError
from vidbyte.lib.process import CliArgv, CliRunner


class MusePathTranslator:
    """Maps a Windows drive path to the path WSL mounts it at."""

    @staticmethod
    def to_wsl(path: PureWindowsPath) -> str:
        # C:\w\repo becomes /mnt/c/w/repo. A UNC path, a drive-relative
        # path or a path without a drive has no /mnt form, so it is
        # refused naming workspace.
        if re.fullmatch(native_threads.MUSE_WINDOWS_DRIVE_PATTERN, path.drive) is None or path.root != native_threads.NATIVE_WINDOWS_ROOT:
            raise ConfigurationError(native_threads.MUSE_WSL_WORKSPACE_RULE, details={native_threads.NATIVE_FIELD_DETAIL_KEY: native_threads.NATIVE_WORKSPACE_ARGUMENT})
        letter = path.drive[0].lower()
        _anchor, *parts = path.parts
        return PurePosixPath(native_threads.MUSE_WSL_MOUNT_ROOT, letter, *parts).as_posix()


class MuseLauncher:
    """Resolves how muse is launched for one call, builds its WSL environment, explains WSL launch failures and reaps WSL runs."""

    def __init__(self, config: MuseThreadConfig, errors: NativeErrorFactory) -> None:
        self._config = config
        self._errors = errors
        self._wsl_program = ""

    @property
    def wsl_mode(self) -> bool:
        # WSL launches muse when a distro is named and no explicit
        # muse_command overrides it.
        return self._config.muse_command is None and self._config.wsl_distro is not None

    def resolve(self, request: NativeThreadRequest) -> tuple[str, ...]:
        # An explicit muse_command wins; a wsl_distro means
        # `wsl.exe -d <distro> -e <muse_path>`; otherwise muse on PATH,
        # which on Windows is not an option.
        config = self._config
        if not self.wsl_mode and (config.muse_command is not None or sys.platform != native_threads.NATIVE_WINDOWS_PLATFORM):
            return NativeLauncher.resolve(config.muse_command, program=native_threads.MUSE_PROGRAM, fallback=None, errors=self._errors, request=request)
        if config.wsl_distro is None:
            raise self._errors.failure(NativeThreadProblem.WSL_UNAVAILABLE, request=request, searched=native_threads.MUSE_NO_WSL_DETAIL)
        found = shutil.which(native_threads.WSL_PROGRAM)
        if found is None:
            raise self._errors.failure(NativeThreadProblem.WSL_UNAVAILABLE, request=request, searched=native_threads.MUSE_NO_WSL_PROGRAM_DETAIL.format(program=native_threads.WSL_PROGRAM))
        self._wsl_program = found
        options = (CliOption(WslFlag.DISTRIBUTION, config.wsl_distro), CliOption(WslFlag.EXEC, config.muse_path))
        return CliArgv.build((found,), options=options, style=CliOptionStyle.SEPARATE)

    def visible_path(self, path: Path) -> str:
        # A path as muse sees it: its /mnt form inside WSL, else the
        # path itself.
        return MusePathTranslator.to_wsl(PureWindowsPath(path)) if self.wsl_mode else str(path)

    def new_mark(self) -> str | None:
        # A fresh random mark for one call's WSL processes (not a
        # secret); a muse outside WSL needs none.
        return uuid.uuid4().hex if self.wsl_mode else None

    def environment(self, overlay: Mapping[str, str], mark: str | None) -> dict[str, str]:
        # @intent muse-wsl-forwards-only-the-key-and-mark
        # In WSL mode the overlay also carries the call's mark, and
        # WSLENV forwards exactly the overlay's names into the distro,
        # after the caller's own WSLENV entries; names that are only in
        # the caller's environment, such as a META_API_KEY of their
        # own, are never forwarded. Outside WSL the overlay is used as
        # is.
        if mark is None:
            return dict(overlay)
        marked = {**overlay, NativeEnvironmentVariable.VIDBYTE_PEER_MARK.value: mark}
        caller = [entry for entry in os.environ.get(NativeEnvironmentVariable.WSLENV.value, "").split(native_threads.NATIVE_WSLENV_SEPARATOR) if entry]
        forwarded = [name + native_threads.NATIVE_WSLENV_UNIX_FLAG for name in marked]
        return {**marked, NativeEnvironmentVariable.WSLENV.value: native_threads.NATIVE_WSLENV_SEPARATOR.join(caller + forwarded)}

    async def launch_failure(self, outcome: CliOutcome, request: NativeThreadRequest, *, thread_id: str | None) -> NativeThreadError | None:
        # In WSL mode, a run that failed may have failed inside wsl.exe:
        # the distro-not-found text is wsl_unavailable naming the
        # distros WSL lists, and exit 127 or the ENOENT text is a muse
        # missing at muse_path inside the distro. Anything else is no
        # WSL launch failure.
        if not self.wsl_mode or outcome.timed_out or outcome.exit_code == native_threads.NATIVE_SUCCESS_EXIT_CODE:
            return None
        text = outcome.stderr.replace(native_threads.NATIVE_NUL_CHARACTER, "")
        distro, muse_path = self._config.wsl_distro, self._config.muse_path
        if native_threads.MUSE_DISTRO_NOT_FOUND_MARKER in text:
            distros = self._errors.listing(await self.list_distros())
            detail = native_threads.MUSE_DISTRO_MISSING_DETAIL.format(distro=distro, program=native_threads.WSL_PROGRAM, distros=distros)
            return self._errors.failure(NativeThreadProblem.WSL_UNAVAILABLE, request=request, thread_id=thread_id, outcome=outcome, vendor_text=text, searched=detail)
        if outcome.exit_code == native_threads.NATIVE_COMMAND_NOT_FOUND_EXIT_CODE or native_threads.MUSE_NO_SUCH_FILE_MARKER in text:
            detail = native_threads.MUSE_NOT_IN_DISTRO_DETAIL.format(muse_path=muse_path, distro=distro)
            return self._errors.failure(NativeThreadProblem.NOT_INSTALLED, request=request, thread_id=thread_id, outcome=outcome, vendor_text=text, searched=detail)
        return None

    async def list_distros(self) -> tuple[str, ...]:
        # `wsl.exe -l -q` once, within the control timeout; a run that
        # fails lists nothing.
        argv = CliArgv.build((self._wsl_program,), options=(CliOption(WslFlag.LIST), CliOption(WslFlag.QUIET)), style=CliOptionStyle.SEPARATE)
        invocation = CliInvocation(argv=argv, env_overlay={}, timeout_seconds=native_threads.NATIVE_CONTROL_TIMEOUT_SECONDS, max_output_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES)
        outcome = await CliRunner().run(invocation)
        names = (line.strip() for line in outcome.stdout.replace(native_threads.NATIVE_NUL_CHARACTER, "").splitlines())
        return tuple(name for name in names if name)

    async def reap(self, mark: str | None) -> None:
        # @intent muse-wsl-reap-kills-the-marked-tree
        # Kill every in-distro process carrying the call's mark, and
        # their descendants, within MUSE_REAP_TIMEOUT_SECONDS. The
        # script arrives on stdin and runs with the caller's
        # environment, which lacks the mark, so it never matches
        # itself. A failed or timed-out reap is not raised.
        distro = self._config.wsl_distro
        if mark is None or distro is None or not self._wsl_program or re.fullmatch(native_threads.MUSE_PEER_MARK_PATTERN, mark) is None:
            return
        options = (CliOption(WslFlag.DISTRIBUTION, distro), CliOption(WslFlag.EXEC, native_threads.MUSE_REAP_SHELL))
        argv = CliArgv.build((self._wsl_program,), options=options, style=CliOptionStyle.SEPARATE, operands=(ShellFlag.READ_STDIN, mark))
        invocation = CliInvocation(
            argv=argv,
            env_overlay={},
            timeout_seconds=native_threads.MUSE_REAP_TIMEOUT_SECONDS,
            max_output_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES,
            stdin_text=native_threads.MUSE_REAP_SCRIPT,
        )
        await CliRunner().run(invocation)


__all__ = ["MuseLauncher", "MusePathTranslator"]

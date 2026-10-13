"""FILE: vidbyte/harnesses/native/muse/launcher.py

PURPOSE: Defines MuseLauncher, which decides how MuseHost starts `muse` (an explicit muse_command, `wsl.exe -d <distro> -e <muse_path>` on win32, or muse on PATH), builds each peer's environment (the WSL peer mark and the WSLENV entries), lists the WSL distros, recognises WSL launch failures, and runs the in-distro reap after a turn peer closes; and MusePathTranslator, which maps a Windows workspace path to its /mnt form inside WSL.
ROLE IN CODEBASE: Built and used by MuseHost (vidbyte/harnesses/native/muse/host.py) only. Runs `wsl.exe -l -q` and the reap through CliRunner (vidbyte/lib/process/runner.py); peers themselves are started by NativePeer in host.py.
ARCHITECTURE NOTE: The launcher holds no process: resolve() looks the launcher up once at __aenter__, argv() appends `serve` or `--version` to that prefix (D-19), and every child gets the caller's environment plus an overlay (D-18). In WSL mode each peer carries a fresh VIDBYTE_PEER_MARK, forwarded through WSLENV, so the reap `sh -s <mark>` (MUSE_REAP_SCRIPT on stdin, with the caller's environment, which lacks the mark) kills exactly that peer's in-distro tree (D-23). MusePathTranslator is pure and raises ConfigurationError; the host turns it into configuration.invalid_argument naming workspace.
FUNCTION INVENTORY: MusePathTranslator.to_wsl maps a drive path to /mnt/<drive>/... MuseLauncher: resolve finds the launcher prefix or names the failure row; prefix and wsl_mode describe it; argv builds a launch argv; workspace_root gives the workspace as muse sees it; new_mark mints a peer mark; peer_environment builds a peer's environment; list_distros runs `wsl.exe -l -q` and keeps the names; launch_failure turns WSL failure text into its row; reap runs the in-distro reap.
COMMON MODIFICATION PATTERNS: A new launch mode is one more branch in resolve and, if it crosses an OS boundary, a forwarding rule in peer_environment; a new WSL failure text is one more marker in launch_failure.
WHAT NOT TO DO IN THIS FILE: 1. Do not run anything through a shell or put `--` before the reap arguments; argv goes to CliRunner as a tuple (S055). 2. Do not forward any variable into WSL except META_API_KEY (only when set) and the peer mark (T-8). 3. Do not read or log the value of META_API_KEY; only its presence matters.
KNOWN EDGE CASES: `wsl.exe -l -q` prints UTF-16-LE; CliRunner decodes it as UTF-8, which keeps ASCII names intact, so the text is re-encoded and decoded as UTF-16-LE when it holds NUL characters (a WSL_UTF8 console prints UTF-8 and is used as is). WSL's own error text may also arrive as UTF-16-LE, so NUL characters are dropped before the markers are searched. A reap with a mark that does not match MUSE_PEER_MARK_PATTERN, or outside WSL mode, does nothing.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.5 (EC-94, EC-95), §8.1 D-18, D-19, D-23, §8.5 (MuseLauncher, MusePathTranslator), §9.3, §10 T-7, T-8
TESTS: tests/features/muse_host/test_muse_host_wsl.py, tests/features/muse_host/test_muse_host_errors.py
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import uuid
from pathlib import PurePosixPath, PureWindowsPath

from vidbyte.harnesses.native.hostkit import NativeChildEnvironment, NativeErrorFactory
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.muse import MuseHostSettings
from vidbyte.lib.dataclasses.process import CliInvocation
from vidbyte.lib.errors import ConfigurationError, NativeHostError
from vidbyte.lib.process import CliRunner

_DRIVE_PATTERN = r"[A-Za-z]:"
_WINDOWS_ROOT = "\\"
_WSL_MOUNT_ROOT = "/mnt"
_WORKSPACE_FIELD = "workspace"
_WSL_EXECUTABLE = "wsl.exe"
_MUSE_EXECUTABLE = "muse"
_DISTRO_FLAG = "-d"
_EXEC_FLAG = "-e"
_LIST_ARGUMENTS = ("-l", "-q")
_REAP_SHELL = ("sh", "-s")
_WSLENV_VARIABLE = "WSLENV"
_WSLENV_SEPARATOR = ":"
_META_KEY_VARIABLE = "META_API_KEY"
_UNIX_PATH_FLAG = "/u"
_NUL = "\x00"
_BYTE_ORDER_MARK = "\ufeff"
_DISTRO_NOT_FOUND_MARKER = "WSL_E_DISTRO_NOT_FOUND"
_NO_SUCH_FILE_MARKER = "No such file or directory"
_COMMAND_NOT_FOUND_EXIT_CODE = 127
_SUCCESS_EXIT_CODE = 0
_WSL_UNAVAILABLE = "wsl_unavailable"
_NOT_INSTALLED = "not_installed"


class MusePathTranslator:
    """Maps a Windows drive path to the path WSL mounts it at."""

    @staticmethod
    def to_wsl(path: PureWindowsPath) -> str:
        # C:\w\repo becomes /mnt/c/w/repo. A UNC path, a drive-relative path
        # or a path without a drive has no /mnt form, so it is refused.
        if re.fullmatch(_DRIVE_PATTERN, path.drive) is None or path.root != _WINDOWS_ROOT:
            raise ConfigurationError("workspace must be an absolute Windows path on a drive letter; UNC and drive-less paths have no /mnt form inside WSL.", details={"field": _WORKSPACE_FIELD})
        return PurePosixPath(_WSL_MOUNT_ROOT, path.drive[0].lower(), *path.parts[1:]).as_posix()


class MuseLauncher:
    """Resolves how muse is launched, builds each peer's environment, lists WSL distros and reaps WSL peers."""

    def __init__(self, settings: MuseHostSettings) -> None:
        self._settings = settings
        self._runner = CliRunner()
        self._wsl_executable = ""
        self._prefix: tuple[str, ...] = ()
        self._distros: tuple[str, ...] = ()

    @property
    def wsl_mode(self) -> bool:
        # WSL mode is chosen by naming a distro (D-19).
        return self._settings.wsl_distro is not None

    @property
    def prefix(self) -> tuple[str, ...]:
        # The resolved launcher argv prefix; empty until resolve succeeds.
        return self._prefix

    def resolve(self) -> str | None:
        # D-19: an explicit muse_command wins; a wsl_distro means
        # `wsl.exe -d <distro> -e <muse_path>`; otherwise muse on PATH, which
        # on win32 is not an option (EC-94). Returns the failure row's
        # problem name when no launcher can be found, else None.
        settings = self._settings
        if settings.muse_command is not None:
            self._prefix = settings.muse_command
            return None
        if settings.wsl_distro is not None:
            self._wsl_executable = shutil.which(_WSL_EXECUTABLE) or ""
            if not self._wsl_executable:
                return _WSL_UNAVAILABLE
            self._prefix = (self._wsl_executable, _DISTRO_FLAG, settings.wsl_distro, _EXEC_FLAG, settings.muse_path)
            return None
        if sys.platform == "win32":
            return _WSL_UNAVAILABLE
        found = shutil.which(_MUSE_EXECUTABLE)
        if found is None:
            return _NOT_INSTALLED
        self._prefix = (found,)
        return None

    def argv(self, *arguments: str) -> tuple[str, ...]:
        # The launcher prefix plus what this launch appends, such as serve or --version.
        return (*self._prefix, *arguments)

    def workspace_root(self) -> str:
        # The workspace as muse sees it: its /mnt form inside WSL, else the path itself.
        if self.wsl_mode:
            return MusePathTranslator.to_wsl(PureWindowsPath(self._settings.workspace))
        return str(self._settings.workspace)

    def new_mark(self) -> str | None:
        # A fresh random mark for one WSL peer (not a secret); native peers need none.
        return uuid.uuid4().hex if self.wsl_mode else None

    def peer_environment(self, mark: str | None) -> dict[str, str]:
        # @intent muse-wsl-forwards-only-the-key-and-mark
        # The caller's environment. In WSL mode every peer, short-lived
        # reads included, also gets the WSLENV entry that carries
        # META_API_KEY into the distro when it is set (D-18), and a turn
        # peer gets its mark and the mark's entry; the caller's own entries
        # stay first. Nothing to forward leaves the environment unchanged.
        marked = {} if mark is None else {native_host_constants.MUSE_PEER_MARK_VARIABLE: mark}
        forwarded = [name + _UNIX_PATH_FLAG for name in (_META_KEY_VARIABLE,) if name in os.environ] + [name + _UNIX_PATH_FLAG for name in marked]
        if not self.wsl_mode or not forwarded:
            return NativeChildEnvironment.build({})
        entries = [entry for entry in os.environ.get(_WSLENV_VARIABLE, "").split(_WSLENV_SEPARATOR) if entry]
        return NativeChildEnvironment.build({**marked, _WSLENV_VARIABLE: _WSLENV_SEPARATOR.join(entries + forwarded)})

    async def list_distros(self) -> tuple[str, ...]:
        # `wsl.exe -l -q` once, within the control timeout; a run that fails
        # lists nothing, which the host reports as EC-94 naming no distros.
        invocation = CliInvocation(
            argv=(self._wsl_executable, *_LIST_ARGUMENTS),
            env=NativeChildEnvironment.build({}),
            timeout_seconds=self._settings.control_timeout_seconds,
            max_output_bytes=native_host_constants.NATIVE_PROCESS_MAX_OUTPUT_BYTES,
        )
        raw = (await self._runner.run(invocation)).stdout
        text = raw.encode("utf-8").decode("utf-16-le", errors="ignore") if _NUL in raw else raw
        self._distros = tuple(name for name in (line.strip().lstrip(_BYTE_ORDER_MARK) for line in text.splitlines()) if name)
        return self._distros

    def launch_failure(self, stderr: str, exit_code: int | None, *, errors: NativeErrorFactory, operation: str) -> NativeHostError | None:
        # EC-94 and EC-95 in WSL mode: a process that ended before answering
        # may say why. wsl.exe's distro-not-found text is wsl_unavailable,
        # naming the listed distros; exit code 127 or the ENOENT text is a
        # muse missing inside the distro. A run that exited 0, or anything
        # else, is no WSL launch failure.
        if not self.wsl_mode or exit_code == _SUCCESS_EXIT_CODE:
            return None
        text = stderr.replace(_NUL, "")
        if _DISTRO_NOT_FOUND_MARKER in text:
            return errors.build(errors.code(_WSL_UNAVAILABLE), "WSL could not find the configured distro.", operation=operation, context={"distros": errors.listing(self._distros)})
        if exit_code == _COMMAND_NOT_FOUND_EXIT_CODE or _NO_SUCH_FILE_MARKER in text:
            return errors.build(errors.code(_NOT_INSTALLED), "Muse Code was not found at muse_path inside the WSL distro.", operation=operation)
        return None

    async def reap(self, mark: str) -> None:
        # @intent muse-wsl-reap-kills-the-marked-tree
        # D-23: after a WSL turn peer closes, kill every in-distro process
        # carrying its mark, and their descendants. The script arrives on
        # stdin and runs with the caller's environment, which lacks the mark,
        # so it never matches itself. A failed or timed-out reap is not
        # raised, because closing never raises.
        distro = self._settings.wsl_distro
        if distro is None or not self._wsl_executable or re.fullmatch(native_host_constants.MUSE_PEER_MARK_PATTERN, mark) is None:
            return
        invocation = CliInvocation(
            argv=(self._wsl_executable, _DISTRO_FLAG, distro, _EXEC_FLAG, *_REAP_SHELL, mark),
            env=NativeChildEnvironment.build({}),
            timeout_seconds=native_host_constants.MUSE_REAP_TIMEOUT_SECONDS,
            max_output_bytes=native_host_constants.NATIVE_PROCESS_MAX_OUTPUT_BYTES,
            stdin_text=native_host_constants.MUSE_REAP_SCRIPT,
        )
        await self._runner.run(invocation)


__all__ = ["MuseLauncher", "MusePathTranslator"]

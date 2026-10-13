"""FILE: vidbyte/harnesses/native/opencode/server.py

PURPOSE: Defines OpencodeServer, which gives an OpencodeHost its server: either it owns `opencode serve` (loopback, random port, a fresh random basic-auth password and the backend keys in the child's environment only) through ManagedProcess, or it records an attached server_url with the caller's credentials.
ROLE IN CODEBASE: Built by OpencodeHost; started in __aenter__ and stopped in __aexit__ or when __aenter__ fails. OpencodeClient reads exit_code to tell a dead owned server (EC-56) from an unreachable one (EC-55).
ARCHITECTURE NOTE: Owned mode follows FR-18 and D-4: argv `<command> serve --hostname 127.0.0.1 --port 0`, the address read from the `opencode server listening on …` line, the password from secrets.token_urlsafe and registered with the error factory. Backend keys are read from os.environ and checked before anything starts (EC-61), copied under the variable opencode reads (D-16), and never written to os.environ (D-18). The server is never restarted (EC-153).
FUNCTION INVENTORY: start is the narrated main function and returns the base URL and the credentials; stop stops and reaps an owned server; exit_code reports its collected exit; _attached reads the attached address; _command finds the executable; _backend_overlay collects the backend keys; _launch starts the child and waits for its address.
COMMON MODIFICATION PATTERNS: A new serve flag is one more item of _SERVE_ARGUMENTS; a new backend is wired through build_opencode_backend_provider, not here.
WHAT NOT TO DO IN THIS FILE: 1. Do not put the password or a key on argv or into os.environ; they travel only in the child's environment (INV-6). 2. Do not bind anything but 127.0.0.1. 3. Do not start a process outside the try/finally in _launch that stops it on every failure path.
KNOWN EDGE CASES: A server that prints its address and then dies is found by the next failed request (EC-153). A launch that raises FileNotFoundError is not_installed; another OSError is process_exited. An early exit is reported with its exit code.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (OpencodeServer), FR-18, D-4, D-16, D-18, EC-54 to EC-56, EC-61, EC-62, AC-9
TESTS: tests/features/opencode_host/test_opencode_host_owned_server.py, tests/features/opencode_host/test_opencode_host_security.py
"""

from __future__ import annotations

import os
import re
import secrets
import shutil

from vidbyte.harnesses.native.backends import build_opencode_backend_provider
from vidbyte.harnesses.native.hostkit import NativeChildEnvironment, NativeErrorFactory
from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.opencode import OpencodeHostSettings
from vidbyte.lib.dataclasses.process import CliInvocation
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.process import ManagedProcess

_EXECUTABLE = "opencode"
_SERVE_ARGUMENTS = ("serve", "--hostname", "127.0.0.1", "--port", "0")
_LOGIN_VARIABLE = "OPENCODE_SERVER_USERNAME"
_CREDENTIAL_VARIABLE = "OPENCODE_SERVER_PASSWORD"
_CREDENTIAL_BYTES = 32


class OpencodeServer:
    """The opencode server one host talks to: an owned `opencode serve` child or an attached URL."""

    def __init__(self, settings: OpencodeHostSettings, errors: NativeErrorFactory) -> None:
        self._settings = settings
        self._errors = errors
        self._process: ManagedProcess | None = None

    @property
    def exit_code(self) -> int | None:
        # The owned server's collected exit code; None while it runs,
        # before it started, or when attached.
        return None if self._process is None else self._process.exit_code

    async def start(self, *, operation: str) -> tuple[str, tuple[str, str] | None]:
        # @intent opencode-server-credentials-stay-in-child-env
        # The owned server's password is fresh per host and registered
        # as a secret before the child starts; it and the backend keys
        # travel only in the child's environment, never on argv or in
        # os.environ. An attached server is used as configured, with the
        # caller's credentials if any.
        if self._settings.server_url is not None:
            return self._attached()

        # Find the executable and every backend key
        # before anything starts.
        command = self._command(operation=operation)
        overlay = self._backend_overlay(operation=operation)

        # A fresh random password for this host only, known to the child
        # through its environment.
        credential = secrets.token_urlsafe(_CREDENTIAL_BYTES)
        self._errors.register_secret(credential)
        overlay[_LOGIN_VARIABLE] = native_host_constants.OPENCODE_SERVER_LOGIN
        overlay[_CREDENTIAL_VARIABLE] = credential

        # Start `opencode serve` on loopback and use
        # the address it prints.
        base_url = await self._launch(command, overlay, operation=operation)
        return base_url, (native_host_constants.OPENCODE_SERVER_LOGIN, credential)

    async def stop(self) -> None:
        # Stops and reaps an owned server's whole tree, once; an
        # attached server is left alone.
        if self._process is not None:
            await self._process.stop()

    def _attached(self) -> tuple[str, tuple[str, str] | None]:
        # The attached URL without a trailing slash, and the caller's
        # credentials when both are set.
        url = str(self._settings.server_url).rstrip("/")
        username, credential = self._settings.server_username, self._settings.server_password
        if username is None or credential is None:
            return url, None
        self._errors.register_secret(credential)
        return url, (username, credential)

    def _command(self, *, operation: str) -> tuple[str, ...]:
        # The configured launcher, or `opencode` found on PATH.
        if self._settings.opencode_command is not None:
            return self._settings.opencode_command
        found = shutil.which(_EXECUTABLE)
        if found is None:
            raise self._errors.build(FailureCode.OPENCODE_NOT_INSTALLED, "No opencode executable was found on PATH.", operation=operation)
        return (found,)

    def _backend_overlay(self, *, operation: str) -> dict[str, str]:
        # @intent opencode-backend-keys-child-env-only
        # Each backend's key is read from the caller's
        # environment, refused when unset or blank before any
        # process starts, registered as a secret, and copied under
        # the variable opencode's built-in provider reads, in the
        # child's environment only.
        overlay: dict[str, str] = {}
        for backend in self._settings.backends:
            provider = build_opencode_backend_provider(backend)
            key = os.environ.get(provider.source_env_var, "")
            if not key.strip():
                raise self._errors.build(FailureCode.BACKEND_NOT_SIGNED_IN, f"{provider.source_env_var} is not set in the environment.", operation=operation, next_step=native_host_constants.BACKEND_KEY_MISSING_NEXT_STEP.format(variable=provider.source_env_var))
            self._errors.register_secret(key)
            overlay[provider.child_env_var] = key
        return overlay

    async def _launch(self, command: tuple[str, ...], overlay: dict[str, str], *, operation: str) -> str:
        # @intent opencode-owned-server-start-stops-on-failure
        # The child starts inside a try/finally that stops and reaps it
        # on every path that does not end with its address: a launch
        # failure, an early exit, a silent server past
        # startup_timeout_seconds, or a cancelled start.
        invocation = CliInvocation(
            argv=(*command, *_SERVE_ARGUMENTS),
            env=NativeChildEnvironment.build(overlay),
            timeout_seconds=self._settings.startup_timeout_seconds,
            max_output_bytes=native_host_constants.NATIVE_TOOL_OUTPUT_MAX_BYTES,
            cwd=self._settings.workspace,
        )
        pattern = re.compile(native_host_constants.OPENCODE_LISTENING_PATTERN)
        process = ManagedProcess(invocation)
        self._process = process
        ready = False
        try:
            outcome = await process.start(pattern)
            if outcome.launch_failure is not None:
                raise self._errors.from_launch_failure(outcome.launch_failure, operation=operation)
            if outcome.timed_out:
                raise self._errors.build(FailureCode.OPENCODE_SERVER_UNREACHABLE, "The opencode server did not print its address within startup_timeout_seconds.", operation=operation)
            found = pattern.search(outcome.ready_line or "")
            if found is None:
                exit_code = "" if outcome.exit_code is None else str(outcome.exit_code)
                raise self._errors.build(FailureCode.OPENCODE_PROCESS_EXITED, "The opencode server exited before printing its address.", operation=operation, context={"exit_code": exit_code})
            ready = True
            return found.group(1)
        finally:
            if not ready:
                await process.stop()


__all__ = ["OpencodeServer"]

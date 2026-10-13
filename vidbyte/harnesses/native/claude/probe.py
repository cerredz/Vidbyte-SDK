"""FILE: vidbyte/harnesses/native/claude/probe.py

PURPOSE: Finds the Claude Code executable and probes it with one initialize handshake that sends no prompt, for readiness and the model list.
ROLE IN CODEBASE: Used by ClaudeHost (host.py). locate_cli resolves the host's CLI path once at entry and screens a request's own cli_path; readiness backs check_claude_ready; initialize, version_ok, signed_in and models back list_claude_models; version_ok also backs the version check a turn runs after it connects (session.py).
ARCHITECTURE NOTE: locate_cli only looks paths up with shutil.which and Path.is_file, and never opens or runs a file. initialize starts Claude Code with nothing but cli_path, reads the answer it gave while starting, and always closes it through one disconnect task that a cancellation cannot cut short.
COMMON MODIFICATION PATTERNS: A new readiness fact adds one read of the initialize answer in readiness and one ClaudeReadiness field. A new install location adds one entry to the CLI path constants in vidbyte/lib/constants/claude.py.
KNOWN EDGE CASES: On Windows the SDK can start only a native executable, so an npm .cmd or .bat shim is never returned, and a given path naming one screens to "" (claude.not_installed); every suffix test ignores case and trailing dots and spaces. An account whose provider is not Anthropic's own API counts as signed in, because its credentials live outside Claude Code. A disconnect that fails after a probe leaves the probe's answer unchanged.
RELATED DOCS: https://platform.claude.com/docs/en/agent-sdk/python; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Mapping
from pathlib import Path, PurePath
from typing import Any

from vidbyte.harnesses.native.claude.failures import ClaudeFailureMapper
from vidbyte.harnesses.native.claude.sdk import _ClaudeClient
from vidbyte.lib.constants.claude import (
    CLAUDE_ABSENT_SOURCE,
    CLAUDE_ACCOUNT_FIELD,
    CLAUDE_CLI_EXE_NAME,
    CLAUDE_CLI_NAME,
    CLAUDE_CONNECT_OPERATION,
    CLAUDE_CREDENTIAL_SOURCE_FIELDS,
    CLAUDE_FIRST_PARTY_PROVIDER,
    CLAUDE_HOME_CLI_PARTS,
    CLAUDE_MIN_CLI_VERSION,
    CLAUDE_POSIX_CLI_LOCATIONS,
    CLAUDE_PROVIDER_FIELD,
    CLAUDE_VERSION_FIELD,
    CLAUDE_WINDOWS_BATCH_SUFFIXES,
    CLAUDE_WINDOWS_NATIVE_SUFFIXES,
)
from vidbyte.lib.dataclasses.claude_host import (
    ClaudeFailure,
    ClaudeModelInfo,
    ClaudeReadiness,
    ClaudeSdkTypes,
)
from vidbyte.lib.enums.claude import ClaudeEffort
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import ClaudeOperationError


class ClaudeProbe:
    """Locates the claude executable and checks it with a prompt-free initialize handshake."""

    @staticmethod
    def locate_cli(cli_path: str, *, windows: bool, home: Path) -> str:
        """Return the executable to start: a given path as it is, else the first one found, or "" when none can be started."""
        # A given path is used as it is, except a Windows batch script, which the SDK cannot start.
        if cli_path:
            return "" if windows and ClaudeProbe._suffix(cli_path) in CLAUDE_WINDOWS_BATCH_SUFFIXES else cli_path
        found = shutil.which(CLAUDE_CLI_NAME) or ""
        # On Windows only a native executable starts without a shell, so an npm shim found first
        # gives way to claude.exe on the PATH, then to the native installer's copy in the home folder.
        if windows:
            if ClaudeProbe._suffix(found) in CLAUDE_WINDOWS_NATIVE_SUFFIXES:
                return found
            installed = home.joinpath(*CLAUDE_HOME_CLI_PARTS)
            return shutil.which(CLAUDE_CLI_EXE_NAME) or (str(installed) if installed.is_file() else "")
        # Elsewhere the PATH hit wins, then the places the SDK itself searches, in its order.
        return found or next((str(home / entry) for entry in CLAUDE_POSIX_CLI_LOCATIONS if (home / entry).is_file()), "")

    @staticmethod
    async def initialize(sdk: ClaudeSdkTypes, cli_path: str) -> Mapping[str, Any]:
        """Start Claude Code with only cli_path, return the answer it gave while starting, and close it first; no prompt is sent."""
        # @intent a-probe-always-closes-its-process
        # The probe's process is closed by one disconnect task that nothing
        # cancels, and a cancelled caller waits for it again before the
        # cancellation goes on, so a probe never leaves a claude process running.
        client: _ClaudeClient = sdk.client_class(options=sdk.options_class(cli_path=cli_path))
        operation = CLAUDE_CONNECT_OPERATION
        try:
            # Start Claude Code; a failure here is a start failure with its own next step.
            await client.connect()
            # Read the version, account and models it reported while starting.
            operation = "get_server_info"
            info = dict(await client.get_server_info() or {})
        except Exception as exc:
            raise ClaudeFailureMapper.from_exception(exc, operation=operation, sdk=sdk) from exc
        finally:
            # Close it through one task nothing cancels; a cancelled caller waits for the close, then goes on cancelling.
            closing = asyncio.create_task(client.disconnect())
            try:
                await asyncio.shield(closing)
            except asyncio.CancelledError:
                await asyncio.wait({closing})
                raise
            except Exception:
                # A failed close leaves the probe's answer unchanged.
                pass
        return info

    @staticmethod
    async def readiness(sdk: ClaudeSdkTypes, cli_path: str) -> ClaudeReadiness:
        """Return whether Claude Code at cli_path starts, is new enough and is signed in; a failed check is reported, never raised."""
        # Without an executable there is nothing to start.
        if not cli_path:
            missing = ClaudeFailureMapper.failure(FailureCode.CLAUDE_NOT_INSTALLED, "No Claude Code executable was found or given.")
            return ClaudeReadiness(cli_path="", cli_version="", signed_in=False, failure=missing)
        # Start Claude Code once, with no prompt; a failure to start or answer becomes the readiness failure.
        try:
            info = await ClaudeProbe.initialize(sdk, cli_path)
        except ClaudeOperationError as error:
            failed = ClaudeFailure(code=FailureCode(error.failure_code), reason=error.reason, next_step=error.next_step)
            return ClaudeReadiness(cli_path=cli_path, cli_version="", signed_in=False, failure=failed)
        # Check the version it reported first, then whether an account or API key is in use.
        version = str(info.get(CLAUDE_VERSION_FIELD) or "")
        account = info.get(CLAUDE_ACCOUNT_FIELD)
        signed_in = ClaudeProbe.signed_in(account if isinstance(account, Mapping) else {})
        failure = None
        if not ClaudeProbe.version_ok(version):
            failure = ClaudeFailureMapper.failure(FailureCode.CLAUDE_VERSION_UNSUPPORTED, f"Claude Code reported version {version or 'none'}, older than {CLAUDE_MIN_CLI_VERSION}.")
        elif not signed_in:
            failure = ClaudeFailureMapper.failure(FailureCode.CLAUDE_NOT_SIGNED_IN, "Claude Code reports no signed-in account and no API key.")
        return ClaudeReadiness(cli_path=cli_path, cli_version=version, signed_in=signed_in, failure=failure)

    @staticmethod
    def models(info: Mapping[str, Any]) -> tuple[ClaudeModelInfo, ...]:
        """Return the models the initialize answer lists, keeping only the effort levels ClaudeEffort names."""
        known = {effort.value: effort for effort in ClaudeEffort if effort.value}
        try:
            return tuple(
                ClaudeModelInfo(
                    value=model["value"],
                    display_name=model.get("displayName") or "",
                    description=model.get("description") or "",
                    resolved_model=model.get("resolvedModel") or "",
                    supports_effort=model.get("supportsEffort"),
                    supported_effort_levels=tuple(known[level] for level in model.get("supportedEffortLevels") or () if level in known),
                    supports_adaptive_thinking=model.get("supportsAdaptiveThinking"),
                    supports_fast_mode=model.get("supportsFastMode"),
                    supports_auto_mode=model.get("supportsAutoMode"),
                )
                for model in info.get("models") or ()
            )
        except Exception as exc:
            raise ClaudeFailureMapper.from_exception(exc, operation="get_server_info", sdk=None) from exc

    @staticmethod
    def version_ok(text: str) -> bool:
        """Return whether a dotted version is at least CLAUDE_MIN_CLI_VERSION, comparing each part as a number."""
        parts = text.split(".")
        if not all(part.isdecimal() for part in parts):
            return False
        return tuple(int(part) for part in parts) >= tuple(int(part) for part in CLAUDE_MIN_CLI_VERSION.split("."))

    @staticmethod
    def signed_in(account: Mapping[str, Any]) -> bool:
        """Return whether the account can call a model: any provider but Anthropic's own API, or a credential source in use."""
        if (account.get(CLAUDE_PROVIDER_FIELD) or CLAUDE_FIRST_PARTY_PROVIDER) != CLAUDE_FIRST_PARTY_PROVIDER:
            return True
        return any(account.get(name) not in (None, CLAUDE_ABSENT_SOURCE) for name in CLAUDE_CREDENTIAL_SOURCE_FIELDS)

    @staticmethod
    def _suffix(path: str) -> str:
        """Return a path's suffix in lower case, ignoring the trailing dots and spaces Windows drops from names."""
        return PurePath(path.rstrip(". ")).suffix.lower()


__all__ = ["ClaudeProbe"]

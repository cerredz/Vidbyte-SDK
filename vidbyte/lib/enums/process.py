"""FILE: vidbyte/lib/enums/process.py

PURPOSE: Defines ProcessLaunchFailure, the closed set of reasons a child process could not be started by the canonical process helpers.
ROLE IN CODEBASE: Returned inside CliOutcome and ProcessStartOutcome (vidbyte/lib/dataclasses/process.py) by CliRunner and ManagedProcess (vidbyte/lib/process/), and mapped to not_installed or process_exited rows by NativeErrorFactory in vidbyte/harnesses/native/hostkit/errors.py. Exported from vidbyte/lib/enums/__init__.py.
ARCHITECTURE NOTE: The process helpers never raise for a launch failure; they report one of these members so each caller picks its own error row.
FUNCTION INVENTORY: No functions. ProcessLaunchFailure.
COMMON MODIFICATION PATTERNS: Add a member only for an OSError family a caller must treat differently, and map it in NativeErrorFactory.from_launch_failure in the same change.
WHAT NOT TO DO IN THIS FILE: 1. Do not import anything from vidbyte. 2. Do not carry the OSError text here; it can hold user paths.
KNOWN EDGE CASES: A Windows .cmd shim that cannot be found is NOT_FOUND; any OSError other than FileNotFoundError and PermissionError is OS_ERROR.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Process helpers), §9.1
TESTS: tests/features/grok_host/test_grok_host_process_helpers.py
"""

from __future__ import annotations

from enum import Enum


class ProcessLaunchFailure(str, Enum):
    """Why a child process could not be started."""

    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    OS_ERROR = "os_error"


__all__ = ["ProcessLaunchFailure"]

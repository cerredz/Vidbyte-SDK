"""FILE: vidbyte/lib/enums/process.py

PURPOSE: Defines the closed sets of the canonical process helpers: ProcessLaunchFailure, why a child process could not be started, and CliOptionStyle, whether CliArgv joins an option to its value (--flag=value) or keeps them as separate argv elements.
ROLE IN CODEBASE: ProcessLaunchFailure is returned inside CliOutcome (vidbyte/lib/dataclasses/process.py) by CliRunner (vidbyte/lib/process/runner.py) and mapped to not_installed or launch_failed by NativeErrorFactory in vidbyte/harnesses/native/hostkit/errors.py. CliOptionStyle is passed to CliArgv.build (vidbyte/lib/process/argv.py) by the harness thread functions. Both are exported from vidbyte/lib/enums/__init__.py.
ARCHITECTURE NOTE: Both are StrEnums, so their values read cleanly in error messages. The process helpers never raise for a launch failure; they report one of these members so each caller picks its own error.
FUNCTION INVENTORY: No functions. ProcessLaunchFailure and CliOptionStyle.
COMMON MODIFICATION PATTERNS: Add a ProcessLaunchFailure member only for an OSError family a caller must treat differently, and map it in NativeErrorFactory.from_launch_failure in the same change. A new option style needs its branch in CliArgv.build.
WHAT NOT TO DO IN THIS FILE: 1. Do not import anything from vidbyte. 2. Do not carry the OSError text here; it can hold user paths.
KNOWN EDGE CASES: A Windows .cmd shim that cannot be found is NOT_FOUND; any OSError other than FileNotFoundError and PermissionError is OS_ERROR, including a file Windows will not run as a program.
RELATED DOCS: vidbyte/lib/README.md
TESTS: tests/features/harness_threads/test_harness_threads_runner.py, tests/features/harness_threads/test_harness_threads_argv.py
"""

from __future__ import annotations

from enum import StrEnum


class ProcessLaunchFailure(StrEnum):
    """Why a child process could not be started."""

    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    OS_ERROR = "os_error"


class CliOptionStyle(StrEnum):
    """How CliArgv writes a valued option: one --flag=value element, or the flag and the value as two elements."""

    JOINED = "joined"
    SEPARATE = "separate"


__all__ = ["CliOptionStyle", "ProcessLaunchFailure"]

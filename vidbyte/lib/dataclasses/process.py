"""FILE: vidbyte/lib/dataclasses/process.py

PURPOSE: Defines the records of the canonical process helpers: CliInvocation (what to run, with which environment, bounds and standard input), CliOutcome (what a finished CLI run produced) and ProcessStartOutcome (how a long-running process start went).
ROLE IN CODEBASE: Taken and returned by CliRunner and ManagedProcess in vidbyte/lib/process/; built by GrokCli, OpencodeServer and MuseLauncher under vidbyte/harnesses/native/.
ARCHITECTURE NOTE: Data only; frozen, slotted, validated in __post_init__. The environment and the standard-input text are repr=False because they can hold keys and prompts. stdin_text set means a pipe that receives it and is then closed; None means the child gets DEVNULL, so no child ever reads the caller's standard input.
FUNCTION INVENTORY: CliInvocation, CliOutcome, ProcessStartOutcome; each has only __post_init__.
COMMON MODIFICATION PATTERNS: A new process option adds a validated field to CliInvocation and its use in vidbyte/lib/process/runner.py or managed.py in the same change.
WHAT NOT TO DO IN THIS FILE: 1. Do not accept a list for argv; argv is an immutable tuple. 2. Do not show env or stdin_text in repr. 3. Do not import from a layer above vidbyte.lib.
KNOWN EDGE CASES: exit_code is None when the process never started, and launch_failure then says why. A timed-out run still reports the exit code the tree stop produced.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Process helpers, Standard input), §9.1 (vidbyte.lib.dataclasses.process)
TESTS: tests/features/grok_host/test_grok_host_process_helpers.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from vidbyte.lib.constants.native_hosts import (
    NATIVE_PROCESS_MAX_OUTPUT_BYTES,
    NATIVE_TURN_MAX_SECONDS,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.process import ProcessLaunchFailure


@dataclass(frozen=True, slots=True)
class CliInvocation:
    """One child process to run: argv, environment, time and output bounds, working folder and optional standard input."""

    argv: tuple[str, ...]
    env: Mapping[str, str] = field(repr=False)
    timeout_seconds: float
    max_output_bytes: int
    cwd: Path | None = None
    stdin_text: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        RecordFieldValidator.require_argv(self.argv, "CliInvocation.argv")
        object.__setattr__(self, "env", RecordFieldConverter.to_mapping(self.env, "CliInvocation.env"))
        RecordFieldValidator.require_number(self.timeout_seconds, "CliInvocation.timeout_seconds", maximum=NATIVE_TURN_MAX_SECONDS)
        RecordFieldValidator.require_int(self.max_output_bytes, "CliInvocation.max_output_bytes", minimum=1, maximum=NATIVE_PROCESS_MAX_OUTPUT_BYTES)
        RecordFieldConverter.require_instance(self.cwd, "CliInvocation.cwd", Path, optional=True)
        RecordFieldConverter.require_instance(self.stdin_text, "CliInvocation.stdin_text", str, optional=True)


@dataclass(frozen=True, slots=True)
class CliOutcome:
    """What a finished CLI run produced; exit_code is None when the process never started."""

    exit_code: int | None
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    timed_out: bool
    launch_failure: ProcessLaunchFailure | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.exit_code, "CliOutcome.exit_code", int, optional=True)
        RecordFieldConverter.require_instance(self.stdout, "CliOutcome.stdout", str)
        RecordFieldConverter.require_instance(self.stderr, "CliOutcome.stderr", str)
        RecordFieldValidator.require_bool(self.stdout_truncated, "CliOutcome.stdout_truncated")
        RecordFieldValidator.require_bool(self.stderr_truncated, "CliOutcome.stderr_truncated")
        RecordFieldValidator.require_bool(self.timed_out, "CliOutcome.timed_out")
        if self.launch_failure is not None:
            RecordFieldValidator.require_enum(self.launch_failure, ProcessLaunchFailure, "CliOutcome.launch_failure")


@dataclass(frozen=True, slots=True)
class ProcessStartOutcome:
    """How a long-running process start went: its ready line, or why it never got there."""

    ready_line: str | None
    launch_failure: ProcessLaunchFailure | None
    exit_code: int | None
    timed_out: bool
    stderr_tail: str

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.ready_line, "ProcessStartOutcome.ready_line", str, optional=True)
        if self.launch_failure is not None:
            RecordFieldValidator.require_enum(self.launch_failure, ProcessLaunchFailure, "ProcessStartOutcome.launch_failure")
        RecordFieldConverter.require_instance(self.exit_code, "ProcessStartOutcome.exit_code", int, optional=True)
        RecordFieldValidator.require_bool(self.timed_out, "ProcessStartOutcome.timed_out")
        RecordFieldConverter.require_instance(self.stderr_tail, "ProcessStartOutcome.stderr_tail", str)


__all__ = ["CliInvocation", "CliOutcome", "ProcessStartOutcome"]

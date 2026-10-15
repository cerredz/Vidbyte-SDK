"""FILE: vidbyte/lib/dataclasses/process.py

PURPOSE: Defines the records of the canonical process helpers: CliOption (one command-line option, a flag with an optional value), CliInvocation (what to run, which environment names to add or leave out, the time and output bounds and the optional standard input) and CliOutcome (what a finished CLI run produced).
ROLE IN CODEBASE: CliOption is taken by CliArgv.build in vidbyte/lib/process/argv.py; CliInvocation is taken and CliOutcome returned by CliRunner in vidbyte/lib/process/runner.py. The harness thread functions under vidbyte/harnesses/native/ build all three.
ARCHITECTURE NOTE: Data only; frozen, slotted, validated in __post_init__. The environment overlay and the standard-input text are repr=False because they can hold keys and prompts; env_remove holds only names, so it stays in the repr. The runner starts the child with the caller's environment minus env_remove, then env_overlay on top. stdin_text set means a pipe that receives it and is then closed; None means the child gets DEVNULL, so no child ever reads the caller's standard input.
FUNCTION INVENTORY: CliOption, CliInvocation, CliOutcome; each has only __post_init__.
COMMON MODIFICATION PATTERNS: A new process option adds a validated field to CliInvocation and its use in vidbyte/lib/process/runner.py in the same change.
WHAT NOT TO DO IN THIS FILE: 1. Do not accept a list for argv; argv is an immutable tuple. 2. Do not show env_overlay or stdin_text in repr. 3. Do not import from a layer above vidbyte.lib.
KNOWN EDGE CASES: exit_code is None when the process never started, and launch_failure then says why. A timed-out run still reports the exit code the tree stop produced. A CliOption flag keeps the enum member it was given; CliArgv turns it into plain text.
RELATED DOCS: vidbyte/lib/README.md
TESTS: tests/features/harness_threads/test_harness_threads_runner.py, tests/features/harness_threads/test_harness_threads_records.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from vidbyte.lib.constants.native_threads import (
    NATIVE_PROCESS_FLAG_MAX_CHARS,
    NATIVE_PROCESS_FLAG_PATTERN,
    NATIVE_PROCESS_MAX_OUTPUT_BYTES,
    NATIVE_PROCESS_VALUE_PATTERN,
    NATIVE_PROMPT_MAX_CHARS,
    NATIVE_THREAD_MAX_SECONDS,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.process import ProcessLaunchFailure


@dataclass(frozen=True, slots=True)
class CliOption:
    """One command-line option: a flag that starts with a dash, and its value, or None for a bare switch."""

    flag: str
    value: str | None = None

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.flag, "CliOption.flag", max_chars=NATIVE_PROCESS_FLAG_MAX_CHARS, pattern=NATIVE_PROCESS_FLAG_PATTERN)
        # The longest value a caller passes is a prompt, so the prompt
        # cap bounds every value.
        if self.value is not None:
            RecordFieldValidator.require_text(self.value, "CliOption.value", max_chars=NATIVE_PROMPT_MAX_CHARS, pattern=NATIVE_PROCESS_VALUE_PATTERN, allow_blank=True)


@dataclass(frozen=True, slots=True)
class CliInvocation:
    """One child process to run: argv, the environment names to add and to leave out, time and output bounds, working folder and optional standard input."""

    argv: tuple[str, ...]
    env_overlay: Mapping[str, str] = field(repr=False)
    timeout_seconds: float
    max_output_bytes: int
    cwd: Path | None = None
    stdin_text: str | None = field(default=None, repr=False)
    env_remove: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        RecordFieldValidator.require_argv(self.argv, "CliInvocation.argv")
        object.__setattr__(self, "env_overlay", RecordFieldConverter.to_mapping(self.env_overlay, "CliInvocation.env_overlay"))
        RecordFieldValidator.require_number(self.timeout_seconds, "CliInvocation.timeout_seconds", maximum=NATIVE_THREAD_MAX_SECONDS)
        RecordFieldValidator.require_int(self.max_output_bytes, "CliInvocation.max_output_bytes", minimum=1, maximum=NATIVE_PROCESS_MAX_OUTPUT_BYTES)
        RecordFieldConverter.require_instance(self.cwd, "CliInvocation.cwd", Path, optional=True)
        RecordFieldConverter.require_instance(self.stdin_text, "CliInvocation.stdin_text", str, optional=True)
        object.__setattr__(self, "env_remove", RecordFieldConverter.to_tuple(self.env_remove, "CliInvocation.env_remove", item_type=str))


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


__all__ = ["CliInvocation", "CliOption", "CliOutcome"]

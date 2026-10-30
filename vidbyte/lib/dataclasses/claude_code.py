"""FILE: vidbyte/lib/dataclasses/claude_code.py

PURPOSE: Defines the validated records of the Claude Code harness agent: the public ClaudeCodeImage, ClaudeCodeRunInput, ClaudeCodeUsage and ClaudeCodeRunResult, and the internal ClaudeCodeCommandRequest (what one command line is built from) and ClaudeCodeWireRequest (what the stream-json reader needs besides the process outcome).
ROLE IN CODEBASE: ClaudeCodeHarnessAgent.arun (vidbyte/agents/claude_code/agent.py) takes a ClaudeCodeRunInput and returns a ClaudeCodeRunResult; ClaudeCodeCommand.argv takes a ClaudeCodeCommandRequest and ClaudeCodeWire.read takes a ClaudeCodeWireRequest. The four public records are re-exported from vidbyte.agents.claude_code, vidbyte.agents and the root vidbyte package. ClaudeCodeHarnessAgentSettings is not here: an agent settings object lives in the agent's own settings.py (AGENTS.md placement exception 1).
ARCHITECTURE NOTE: Data only; frozen, slotted, validated in __post_init__ through the shared RecordFieldValidator and RecordFieldConverter, so a bad value fails where it enters. The public field names and their order are pinned by the cross-repo suggest-BYOK contract (section 2); fields after the pinned ones have defaults, so they are optional additions. Image data and the prompt are repr=False because they can be large or private.
COMMON MODIFICATION PATTERNS: A new optional result field is appended with a default and filled in ClaudeCodeWire.read. Never reorder or rename a pinned field: vidbyte-cli builds and reads these records by name.
KNOWN EDGE CASES: ClaudeCodeImage accepts any media type text so that ClaudeCodeHarnessAgent.arun, not construction, refuses an unsupported attachment with ClaudeCodeAgentError(UNSUPPORTED_INPUT) naming it, as the contract requires. ClaudeCodeRunResult.output is a plain dict (JSON-serializable), not a read-only view. cost_usd is None only when the agent had no baseline for a resumed saved session and Claude Code omitted its per-run cost.
RELATED DOCS: docs/design/claude-code-harness-agent.md; vidbyte/agents/claude_code/README.md
TESTS: tests/features/claude_code_agent/test_claude_code_records.py
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vidbyte.lib.constants.claude_code import (
    CLAUDE_CODE_MAX_TIMEOUT_SECONDS,
    CLAUDE_CODE_MEDIA_TYPE_MAX_CHARS,
    CLAUDE_CODE_MEDIA_TYPE_PATTERN,
    CLAUDE_CODE_MODEL_MAX_CHARS,
    CLAUDE_CODE_SESSION_ID_PATTERN,
)
from vidbyte.lib.dataclasses.process import CliOutcome
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.claude_code import ClaudeCodeEffort
from vidbyte.lib.errors import ConfigurationError

_FLOAT_MAX = float("inf")


@dataclass(frozen=True, slots=True)
class ClaudeCodeImage:
    """One image attachment: its media type and its bytes as standard base64 text."""

    media_type: str
    data_base64: str = field(repr=False)

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.media_type, "ClaudeCodeImage.media_type", max_chars=CLAUDE_CODE_MEDIA_TYPE_MAX_CHARS, pattern=CLAUDE_CODE_MEDIA_TYPE_PATTERN)
        RecordFieldValidator.require_text(self.data_base64, "ClaudeCodeImage.data_base64")
        # @intent image-data-is-real-base64
        # Claude Code forwards the text as is, so data that is not base64
        # would fail inside the API call after the process started; it is
        # refused here, without quoting the data.
        try:
            base64.b64decode(self.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ConfigurationError("ClaudeCodeImage.data_base64 must be standard base64 text.", details={"field": "ClaudeCodeImage.data_base64"}) from exc


@dataclass(frozen=True, slots=True)
class ClaudeCodeRunInput:
    """One turn's input: the prompt text and the images sent with it, in order."""

    prompt: str = field(repr=False)
    images: tuple[ClaudeCodeImage, ...] = ()

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.prompt, "ClaudeCodeRunInput.prompt")
        object.__setattr__(self, "images", RecordFieldConverter.to_tuple(self.images, "ClaudeCodeRunInput.images", item_type=ClaudeCodeImage))


@dataclass(frozen=True, slots=True)
class ClaudeCodeUsage:
    """The tokens one run used, as Claude Code reported them for that run alone."""

    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int

    def __post_init__(self) -> None:
        RecordFieldValidator.require_int(self.input_tokens, "ClaudeCodeUsage.input_tokens", minimum=0)
        RecordFieldValidator.require_int(self.output_tokens, "ClaudeCodeUsage.output_tokens", minimum=0)
        RecordFieldValidator.require_int(self.cache_read_input_tokens, "ClaudeCodeUsage.cache_read_input_tokens", minimum=0)
        RecordFieldValidator.require_int(self.cache_creation_input_tokens, "ClaudeCodeUsage.cache_creation_input_tokens", minimum=0)

    @property
    def total_tokens(self) -> int:
        """Every input, cached input and output token of the run."""
        return self.input_tokens + self.output_tokens + self.cache_read_input_tokens + self.cache_creation_input_tokens


@dataclass(frozen=True, slots=True)
class ClaudeCodeRunResult:
    """What one Claude Code run returned: structured output, final text, session, usage, cost and model."""

    output: dict[str, Any] | None
    text: str
    session_id: str
    usage: ClaudeCodeUsage
    cost_usd: float | None
    model: str
    num_turns: int = 0
    duration_ms: int = 0
    session_cost_usd: float | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.output, "ClaudeCodeRunResult.output", dict, optional=True)
        RecordFieldConverter.require_instance(self.text, "ClaudeCodeRunResult.text", str)
        RecordFieldValidator.require_text(self.session_id, "ClaudeCodeRunResult.session_id", pattern=CLAUDE_CODE_SESSION_ID_PATTERN)
        RecordFieldConverter.require_instance(self.usage, "ClaudeCodeRunResult.usage", ClaudeCodeUsage)
        if self.cost_usd is not None:
            RecordFieldValidator.require_number(self.cost_usd, "ClaudeCodeRunResult.cost_usd", maximum=_FLOAT_MAX, allow_zero=True)
        RecordFieldValidator.require_text(self.model, "ClaudeCodeRunResult.model", max_chars=CLAUDE_CODE_MODEL_MAX_CHARS, one_line=True)
        RecordFieldValidator.require_int(self.num_turns, "ClaudeCodeRunResult.num_turns", minimum=0)
        RecordFieldValidator.require_int(self.duration_ms, "ClaudeCodeRunResult.duration_ms", minimum=0)
        if self.session_cost_usd is not None:
            RecordFieldValidator.require_number(self.session_cost_usd, "ClaudeCodeRunResult.session_cost_usd", maximum=_FLOAT_MAX, allow_zero=True)


@dataclass(frozen=True, slots=True)
class ClaudeCodeCommandRequest:
    """What one `claude` command line is built from: the launcher, the private instructions file, the tool, model, effort and schema choices, and the session to start or resume."""

    launcher: tuple[str, ...]
    instructions_file: Path
    allowed_tools: tuple[str, ...]
    model: str | None
    effort: ClaudeCodeEffort | None
    output_schema_json: str | None = field(repr=False)
    session_id: str
    resume: bool

    def __post_init__(self) -> None:
        RecordFieldValidator.require_argv(self.launcher, "ClaudeCodeCommandRequest.launcher")
        RecordFieldConverter.require_instance(self.instructions_file, "ClaudeCodeCommandRequest.instructions_file", Path)
        RecordFieldValidator.require_text_items(self.allowed_tools, "ClaudeCodeCommandRequest.allowed_tools")
        RecordFieldValidator.require_optional_text(self.model, "ClaudeCodeCommandRequest.model", max_chars=CLAUDE_CODE_MODEL_MAX_CHARS, one_line=True)
        if self.effort is not None:
            RecordFieldValidator.require_enum(self.effort, ClaudeCodeEffort, "ClaudeCodeCommandRequest.effort")
        RecordFieldValidator.require_optional_text(self.output_schema_json, "ClaudeCodeCommandRequest.output_schema_json", one_line=True)
        RecordFieldValidator.require_text(self.session_id, "ClaudeCodeCommandRequest.session_id", pattern=CLAUDE_CODE_SESSION_ID_PATTERN)
        RecordFieldValidator.require_bool(self.resume, "ClaudeCodeCommandRequest.resume")


@dataclass(frozen=True, slots=True)
class ClaudeCodeWireRequest:
    """What ClaudeCodeWire.read needs besides the outcome: the session it asked for, whether output is structured, the allowed tools, the last session total and the time bound."""

    outcome: CliOutcome = field(repr=False)
    session_id: str
    expects_output: bool
    allowed_tools: tuple[str, ...]
    previous_session_cost_usd: float | None
    timeout_seconds: float

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.outcome, "ClaudeCodeWireRequest.outcome", CliOutcome)
        RecordFieldValidator.require_text(self.session_id, "ClaudeCodeWireRequest.session_id", pattern=CLAUDE_CODE_SESSION_ID_PATTERN)
        RecordFieldValidator.require_bool(self.expects_output, "ClaudeCodeWireRequest.expects_output")
        RecordFieldValidator.require_text_items(self.allowed_tools, "ClaudeCodeWireRequest.allowed_tools")
        if self.previous_session_cost_usd is not None:
            RecordFieldValidator.require_number(self.previous_session_cost_usd, "ClaudeCodeWireRequest.previous_session_cost_usd", maximum=_FLOAT_MAX, allow_zero=True)
        RecordFieldValidator.require_number(self.timeout_seconds, "ClaudeCodeWireRequest.timeout_seconds", maximum=CLAUDE_CODE_MAX_TIMEOUT_SECONDS)


__all__ = [
    "ClaudeCodeCommandRequest",
    "ClaudeCodeImage",
    "ClaudeCodeRunInput",
    "ClaudeCodeRunResult",
    "ClaudeCodeUsage",
    "ClaudeCodeWireRequest",
]

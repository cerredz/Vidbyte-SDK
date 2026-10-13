"""FILE: vidbyte/harnesses/native/claude/failures.py

PURPOSE: Turns an exception from claude-agent-sdk, or the facts of a finished turn, into one claude.* failure code with its reason and next step.
ROLE IN CODEBASE: The one place ClaudeHost chooses a failure code. The session pump, the probe, the history functions and the host map every exception they catch through from_exception, and the pump classifies each finished turn through classify_turn. The host and the session build their refusals through error, and both apply usage_limited, the one check of whether a rate-limit window refuses new sessions (D-29).
ARCHITECTURE NOTE: from_exception walks one ordered table of exception classes, each subclass before its base, so CLINotFoundError wins over CLIConnectionError and ResultError over ProcessError. The guarded try lives at each SDK call site, which passes what it caught here. classify_turn checks a fixed precedence and returns at the first match, so a turn carries exactly one code.
COMMON MODIFICATION PATTERNS: A new SDK exception adds one row to _rows, placed before its base class. A new turn condition adds one ClaudeTurnOutcome field and one check at its place in the precedence.
WHAT NOT TO DO IN THIS FILE: 1. Do not catch BaseException; only an Exception reaches the mapper, so a cancellation always propagates. 2. Do not format the exception's text, its stderr or any message text into a reason; a reason names the operation and the exception class, or CLI vocabulary such as a result subtype.
KNOWN EDGE CASES: MessageParseError is not exported by the SDK, so it maps through its ClaudeSDKError base. A ValueError or TypeError is an argument the SDK rejected only from connect, which builds the options and starts the process, or from fork; from any other operation, such as converting a malformed SDK record, it is a protocol mismatch. A refusing rate-limit window or an assistant rate_limit error fails a turn even when its result is a success. A caller's interrupt is never a failure, but the time budget's own interrupt is.
RELATED DOCS: https://platform.claude.com/docs/en/agent-sdk/python; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

import time

from vidbyte.lib.constants.claude import (
    CLAUDE_CONNECT_OPERATION,
    CLAUDE_FAILURE_NEXT_STEPS,
    CLAUDE_FORK_OPERATION,
    CLAUDE_HISTORY_READ_NEXT_STEP,
    CLAUDE_HISTORY_READ_OPERATIONS,
    CLAUDE_INVALID_ARGUMENT_NEXT_STEP,
    CLAUDE_START_FAILURE_NEXT_STEP,
)
from vidbyte.lib.dataclasses.claude_host import (
    ClaudeFailure,
    ClaudeRateLimitWindow,
    ClaudeSdkTypes,
    ClaudeTurnOutcome,
)
from vidbyte.lib.enums.claude import ClaudeRateLimitStatus, ClaudeTurnStatus
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import ClaudeOperationError

# Result subtypes that mean the turn used up its turn or dollar budget.
_BUDGET_SUBTYPES = ("error_max_budget_usd", "error_max_turns")
# The result subtype that means Claude Code gave up matching output_schema.
_SCHEMA_SUBTYPE = "error_max_structured_output_retries"
# Assistant error kinds that fail a turn, in the order they win over each other.
_ASSISTANT_ERROR_CODES = (
    ("rate_limit", FailureCode.CLAUDE_USAGE_LIMITED),
    ("billing_error", FailureCode.CLAUDE_BILLING_ERROR),
    ("authentication_failed", FailureCode.CLAUDE_NOT_SIGNED_IN),
    ("model_not_found", FailureCode.CLAUDE_MODEL_UNKNOWN),
)


class ClaudeFailureMapper:
    """Chooses the one failure code, reason and next step for an SDK exception or a finished turn."""

    @staticmethod
    def from_exception(exc: Exception, *, operation: str, sdk: ClaudeSdkTypes | None) -> ClaudeOperationError:
        """Map an exception one SDK operation raised to its semantic error, naming only the operation and the exception class."""
        # Take the first row whose class matches; anything the table does not know is a protocol mismatch.
        rows = ClaudeFailureMapper._rows(operation, sdk)
        code = next((mapped for kind, mapped in rows.items() if isinstance(exc, kind)), FailureCode.CLAUDE_PROTOCOL_MISMATCH)
        # A ResultError carries the failed result's subtype, which picks a budget, schema or API failure like a turn's result does.
        if sdk is not None and isinstance(exc, sdk.result_error):
            code = ClaudeFailureMapper._result_code(getattr(exc, "subtype", None))
        # A failed start and an unreadable session file get their own next step; every other code keeps its usual one.
        next_step = ClaudeFailureMapper._next_step(code, operation)
        return ClaudeOperationError(f"{operation} raised {type(exc).__name__}.", failure_code=code.value, operation=operation, next_step=next_step)

    @staticmethod
    def classify_turn(outcome: ClaudeTurnOutcome) -> tuple[ClaudeTurnStatus, ClaudeFailure | None]:
        """Return a finished turn's status and its one failure, taking the first condition that matches in a fixed order."""
        # @intent one-failure-code-per-turn
        # The checks run in a fixed order and stop at the first match, so a turn
        # reports exactly one code and permission denials only annotate a success;
        # reordering them would give the same turn a different code.
        # A version or login-type check failed after Claude Code started, so no prompt was sent.
        if outcome.precondition_failure is not None:
            return ClaudeTurnStatus.FAILED, outcome.precondition_failure
        # The host's time budget stopped the turn; its own interrupt is never reported as the caller's.
        if outcome.budget_expired:
            return ClaudeTurnStatus.FAILED, ClaudeFailureMapper.failure(FailureCode.CLAUDE_BUDGET_EXHAUSTED, "The turn ran past its timeout_seconds budget, so the host interrupted it.")
        # The caller, a close or an unanswered steer interrupted the turn, which is a stop rather than a failure.
        if outcome.interrupted:
            return ClaudeTurnStatus.INTERRUPTED, None
        # A rate limit, an account problem or an error result reported during the turn fails it, even after a success.
        reported = ClaudeFailureMapper._reported(outcome)
        if reported is not None:
            return ClaudeTurnStatus.FAILED, ClaudeFailureMapper.failure(*reported)
        # The output ended before the prompt's own result arrived, either with an exception or simply by ending.
        if not outcome.result_seen:
            return ClaudeTurnStatus.FAILED, outcome.stream_failure or ClaudeFailureMapper.failure(FailureCode.CLAUDE_PROCESS_EXITED, "Claude Code's output ended before the turn's result arrived.")
        # A success whose tool calls were refused still completes, and the failure explains why some work may be missing.
        if outcome.permission_denials:
            return ClaudeTurnStatus.COMPLETED, ClaudeFailureMapper.failure(FailureCode.CLAUDE_PERMISSION_DENIED, "The turn completed, but Claude Code was refused tool calls; permission_denials lists each one.")
        return ClaudeTurnStatus.COMPLETED, None

    @staticmethod
    def failure(code: FailureCode, reason: str) -> ClaudeFailure:
        """Return a failure for a claude.* code, carrying the next step that code always has."""
        return ClaudeFailure(code=code, reason=reason, next_step=CLAUDE_FAILURE_NEXT_STEPS[code.value])

    @staticmethod
    def error(code: FailureCode, reason: str, *, operation: str, next_step: str = "") -> ClaudeOperationError:
        """Return the error for a refused call, with the given next step or else the one a claude.* code always has."""
        return ClaudeOperationError(reason, failure_code=code.value, operation=operation, next_step=next_step or CLAUDE_FAILURE_NEXT_STEPS[code.value])

    @staticmethod
    def usage_limited(window: ClaudeRateLimitWindow) -> bool:
        """Return whether a window refuses new sessions: rejected, resetting later than now, and with no allowed overage (D-29)."""
        overage_allowed = window.overage_status in (ClaudeRateLimitStatus.ALLOWED, ClaudeRateLimitStatus.ALLOWED_WARNING)
        return window.status is ClaudeRateLimitStatus.REJECTED and window.resets_at is not None and window.resets_at > time.time() and not overage_allowed

    @staticmethod
    def _rows(operation: str, sdk: ClaudeSdkTypes | None) -> dict[type, FailureCode]:
        """Return the exception classes this operation maps, each subclass before its base."""
        rows: dict[type, FailureCode] = {}
        if sdk is not None:
            rows[sdk.cli_not_found_error] = FailureCode.CLAUDE_NOT_INSTALLED
            rows[sdk.result_error] = FailureCode.CLAUDE_API_ERROR
            rows[sdk.process_error] = FailureCode.CLAUDE_PROCESS_EXITED
            rows[sdk.cli_connection_error] = FailureCode.CLAUDE_PROCESS_EXITED
            rows[sdk.cli_json_decode_error] = FailureCode.CLAUDE_PROTOCOL_MISMATCH
            rows[sdk.sdk_error] = FailureCode.CLAUDE_PROTOCOL_MISMATCH
        if operation == CLAUDE_FORK_OPERATION:
            rows[FileNotFoundError] = FailureCode.CLAUDE_SESSION_NOT_FOUND
        if operation in CLAUDE_HISTORY_READ_OPERATIONS:
            rows[OSError] = FailureCode.CLAUDE_SESSION_NOT_FOUND
        if operation in (CLAUDE_CONNECT_OPERATION, CLAUDE_FORK_OPERATION):
            rows[ValueError] = FailureCode.CONFIGURATION_INVALID_ARGUMENT
            rows[TypeError] = FailureCode.CONFIGURATION_INVALID_ARGUMENT
        return rows

    @staticmethod
    def _result_code(subtype: object) -> FailureCode:
        """Return the code a failed result's subtype names: a used-up budget, the output schema, or else the API."""
        if subtype in _BUDGET_SUBTYPES:
            return FailureCode.CLAUDE_BUDGET_EXHAUSTED
        if subtype == _SCHEMA_SUBTYPE:
            return FailureCode.CLAUDE_SCHEMA_VIOLATION
        return FailureCode.CLAUDE_API_ERROR

    @staticmethod
    def _next_step(code: FailureCode, operation: str) -> str:
        """Return the next step for a mapped code; a failed start and an unreadable session file have their own."""
        if code is FailureCode.CLAUDE_PROCESS_EXITED and operation == CLAUDE_CONNECT_OPERATION:
            return CLAUDE_START_FAILURE_NEXT_STEP
        if code is FailureCode.CLAUDE_SESSION_NOT_FOUND and operation in CLAUDE_HISTORY_READ_OPERATIONS:
            return CLAUDE_HISTORY_READ_NEXT_STEP
        if code is FailureCode.CONFIGURATION_INVALID_ARGUMENT:
            return CLAUDE_INVALID_ARGUMENT_NEXT_STEP
        return CLAUDE_FAILURE_NEXT_STEPS[code.value]

    @staticmethod
    def _reported(outcome: ClaudeTurnOutcome) -> tuple[FailureCode, str] | None:
        """Return the code and reason for what the stream and the latest result reported, or None when neither failed."""
        if outcome.rate_limit_rejected:
            return FailureCode.CLAUDE_USAGE_LIMITED, "A rate-limit window that refuses new sessions arrived during the turn."
        for kind, code in _ASSISTANT_ERROR_CODES:
            if kind in outcome.assistant_errors:
                return code, f"Claude Code reported the assistant error {kind} during the turn."
        if outcome.subtype in _BUDGET_SUBTYPES:
            return FailureCode.CLAUDE_BUDGET_EXHAUSTED, f"The turn's result ended with subtype {outcome.subtype}."
        if outcome.subtype == _SCHEMA_SUBTYPE or outcome.structured_output_missing:
            return FailureCode.CLAUDE_SCHEMA_VIOLATION, f"The turn's result (subtype {outcome.subtype}) has no structured output matching output_schema; result_text keeps the raw text."
        if outcome.is_error:
            errors = ", ".join(outcome.assistant_errors) or "none"
            return FailureCode.CLAUDE_API_ERROR, f"The turn ended with an error result: subtype {outcome.subtype}, terminal_reason {outcome.terminal_reason}, api_error_status {outcome.api_error_status}, assistant errors {errors}."
        return None


__all__ = ["ClaudeFailureMapper"]

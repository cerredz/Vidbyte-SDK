"""FILE: vidbyte/harnesses/native/codex/errors.py

PURPOSE: Builds every failure CodexHost reports: the CodexProblem records snapshots and readiness carry, the CodexAgentError its methods raise, and the mapping from openai-codex exceptions and turn errors to the section 9.2 failure codes.
ROLE IN CODEBASE: The error layer of vidbyte/harnesses/native/codex/; the host, its connection, preflight and response translator call it, so each failure code, operation and next step is chosen in one place.
ARCHITECTURE NOTE: A static helper class. openai-codex is imported inside from_exception only, so importing this module never loads the SDK (D-21). No message ever carries an exception's own text, stderr, env values or the account email; Codex's JSON-RPC message, the method, the code and a type name are the only variable parts (INV-9).
COMMON MODIFICATION PATTERNS: A new failure source gets a branch in from_exception or a small builder here, using CODEX_NEXT_STEPS for its next step; callers raise the result from None.
KNOWN EDGE CASES: A plain CodexError is exactly that class, never a subclass; once the connection's death flag is set every failure is codex.process_exited, because openai-codex fails every waiter with the reader's own error, which can quote a raw stdout line (EC-72).
RELATED DOCS: docs/spec/codex-host/spec.md (sections 8.1 D-13 and D-27, and 9.2 error codes)
TESTS: tests/features/codex_host/test_codex_host_failures.py, tests/features/codex_host/test_codex_host_turns.py
"""

from __future__ import annotations

from pydantic import ValidationError

from vidbyte.lib.constants.codex import (
    CODEX_ERROR_INFO_CODES,
    CODEX_HOST_MINIMUM_VERSION,
    CODEX_NEXT_STEPS,
    CODEX_SDK_EXTRA,
    CODEX_THREAD_FORK_METHOD,
    CODEX_THREAD_READ_METHOD,
)
from vidbyte.lib.dataclasses.codex import CodexTurnError
from vidbyte.lib.dataclasses.codex_host import CodexProblem
from vidbyte.lib.enums.codex import CodexGoalStatus, CodexHostOperation
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError

# The SDK call whose plain CodexError means its goal start window
# elapsed (D-13).
GOAL_START_CALL = "start_goal_operation"
# The message of each stop reason Vidbyte itself sends an interrupt for
# (D-7).
STOP_MESSAGES = {
    FailureCode.CODEX_TURN_TIMED_OUT: "Vidbyte interrupted the turn because its timeout_seconds elapsed.",
    FailureCode.CODEX_BUDGET_EXHAUSTED: "Vidbyte interrupted the turn because its output tokens passed max_output_tokens.",
}
# The goal statuses that stop a goal run for a limit, as a failure
# (9.2).
GOAL_PROBLEM_CODES = {
    CodexGoalStatus.BUDGET_LIMITED: FailureCode.CODEX_BUDGET_EXHAUSTED,
    CodexGoalStatus.USAGE_LIMITED: FailureCode.CODEX_USAGE_LIMITED,
}


class CodexErrorMapper:
    """Builds CodexHost problems and errors, and maps SDK exceptions to failure codes."""

    @staticmethod
    def problem(code: FailureCode, message: str) -> CodexProblem:
        # A problem always carries its code's fixed next step.
        return CodexProblem(code=code, message=message, next_step=CODEX_NEXT_STEPS[code.value])

    @staticmethod
    def stop_problem(code: FailureCode) -> CodexProblem:
        # The problem of a turn Vidbyte itself interrupted for a budget.
        return CodexProblem(code=code, message=STOP_MESSAGES[code], next_step=CODEX_NEXT_STEPS[code.value])

    @staticmethod
    def error(code: FailureCode, message: str, operation: CodexHostOperation, thread_id: str = "") -> CodexAgentError:
        # Name a thread that already exists, so the caller can find it
        # again.
        text = f"{message} Thread: {thread_id}." if thread_id else message
        return CodexAgentError(text, failure_code=code.value, operation=operation.value, next_step=CODEX_NEXT_STEPS[code.value])

    @classmethod
    def from_exception(cls, exc: Exception, operation: CodexHostOperation, method: str, *, dead: bool, bound_seconds: float, thread_id: str = "") -> CodexAgentError:
        # Map one exception raised while talking to Codex, in the
        # section 9.2 order. The SDK is imported here only, so importing
        # this module never loads it.
        from openai_codex import errors as sdk

        # Once the app-server died, every failure is that death,
        # whatever the SDK raised, and its text is never shown.
        if dead or isinstance(exc, sdk.TransportClosedError):
            return cls.error(FailureCode.CODEX_PROCESS_EXITED, f"The Codex app-server exited during {method}.", operation, thread_id)
        # A JSON-RPC error carries Codex's own message and code, which
        # are safe to show; the method decides what the error means.
        if isinstance(exc, sdk.JsonRpcError):
            malformed = isinstance(exc, (sdk.InvalidParamsError, sdk.MethodNotFoundError, sdk.ParseError))
            refused = isinstance(exc, (sdk.InvalidRequestError, sdk.InvalidParamsError))
            code = cls._rpc_code(method, malformed=malformed, refused=refused)
            return cls.error(code, f"Codex answered {method} with JSON-RPC error {exc.code}: {exc.message}", operation, thread_id)
        # A plain CodexError from the goal start is its start window
        # elapsing; any other SDK error is the SDK refusing the call.
        if isinstance(exc, sdk.CodexError):
            window = type(exc) is sdk.CodexError and method == GOAL_START_CALL
            code = FailureCode.CODEX_API_ERROR if window else FailureCode.CODEX_PROTOCOL_MISMATCH
            return cls.error(code, f"openai-codex could not complete {method}.", operation, thread_id)
        # Everything else is local: an answer the SDK model rejected,
        # the time bound elapsing, or an error nobody expected.
        code, message = cls._local_failure(exc, method, bound_seconds)
        return cls.error(code, message, operation, thread_id)

    @staticmethod
    def _rpc_code(method: str, *, malformed: bool, refused: bool) -> FailureCode:
        # Two methods' JSON-RPC errors carry a context meaning of their
        # own: a failed thread read means the thread is unknown, and a
        # refused fork means the fork point is wrong (D-13).
        if method == CODEX_THREAD_READ_METHOD:
            return FailureCode.CODEX_SESSION_NOT_FOUND
        if method == CODEX_THREAD_FORK_METHOD and refused:
            return FailureCode.CODEX_FORK_FAILED
        if malformed:
            return FailureCode.CODEX_PROTOCOL_MISMATCH
        return FailureCode.CODEX_API_ERROR

    @staticmethod
    def _local_failure(exc: Exception, method: str, bound_seconds: float) -> tuple[FailureCode, str]:
        # Only the method, the bound and the exception's type name are
        # shown.
        if isinstance(exc, ValidationError):
            return FailureCode.CODEX_PROTOCOL_MISMATCH, f"Codex's answer to {method} did not match the openai-codex response model."
        if isinstance(exc, TimeoutError):
            return FailureCode.CODEX_API_ERROR, f"Codex did not answer {method} within {bound_seconds:g} seconds."
        return FailureCode.CODEX_API_ERROR, f"{method} failed with {type(exc).__name__}."

    @staticmethod
    def missing_sdk() -> CodexAgentError:
        # The Python extra is what is missing, so the next step installs
        # it.
        return CodexAgentError(
            "openai-codex is not installed, so CodexHost cannot talk to Codex.",
            failure_code=FailureCode.CODEX_NOT_INSTALLED.value,
            operation=CodexHostOperation.OPEN_HOST.value,
            next_step=f'Install the Python SDK extra: pip install "{CODEX_SDK_EXTRA}".',
        )

    @classmethod
    def not_installed(cls, target: str) -> CodexAgentError:
        # Name what was searched for or launched, never the environment.
        return cls.error(FailureCode.CODEX_NOT_INSTALLED, f"The Codex CLI could not be started from {target}.", CodexHostOperation.OPEN_HOST)

    @classmethod
    def version_unsupported(cls, found: str) -> CodexAgentError:
        # Name both versions, so the caller knows how far to update.
        message = f"The Codex app-server reports version '{found}', and CodexHost needs {CODEX_HOST_MINIMUM_VERSION} or newer."
        return cls.error(FailureCode.CODEX_VERSION_UNSUPPORTED, message, CodexHostOperation.OPEN_HOST)

    @classmethod
    def reviewer_refusal(cls, operation: CodexHostOperation, thread_id: str) -> CodexAgentError:
        # Codex would route approvals to a person nothing in this
        # release answers, so the operation stops before the thread
        # spends (D-32).
        message = "Codex routes this thread's approval requests to a user reviewer, and CodexHost cannot answer them."
        return cls.error(FailureCode.CONFIGURATION_UNSUPPORTED_COMBINATION, message, operation, thread_id)

    @classmethod
    def process_exited(cls, operation: CodexHostOperation, thread_id: str = "") -> CodexAgentError:
        # A closed or dead host sends nothing, so this needs no
        # exception.
        return cls.error(FailureCode.CODEX_PROCESS_EXITED, "CodexHost is closed or its Codex app-server exited.", operation, thread_id)

    @classmethod
    def goal_problem(cls, status: CodexGoalStatus) -> CodexProblem | None:
        # A goal Codex stopped for its token budget or the account's
        # usage limit is a failure; every other final goal status is
        # not.
        code = GOAL_PROBLEM_CODES.get(status)
        return None if code is None else cls.problem(code, f"Codex stopped the goal run with status {status.value}.")

    @staticmethod
    def turn_problem(error: CodexTurnError | None) -> CodexProblem:
        # The key is the codexErrorInfo string, or the one key of an
        # object variant; every key the table does not name means
        # codex.api_error.
        info = error.codex_error_info if error is not None else None
        key = ""
        if isinstance(info, str):
            key = info
        elif isinstance(info, dict):
            key = next(iter(info), "")
        code = FailureCode(CODEX_ERROR_INFO_CODES.get(key, FailureCode.CODEX_API_ERROR.value))
        message = f"Codex failed the turn: {error.message}" if error is not None else "Codex failed the turn without an error."
        return CodexProblem(code=code, message=message, next_step=CODEX_NEXT_STEPS[code.value])


__all__ = ["CodexErrorMapper"]

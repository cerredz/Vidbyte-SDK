"""FILE: vidbyte/harnesses/native/codex/errors.py

PURPOSE: Builds every failure CodexHost reports: the CodexProblem records snapshots and readiness carry, the CodexAgentError its methods raise, and the mapping from openai-codex exceptions and turn errors to the section 9.2 failure codes.
ROLE IN CODEBASE: The error layer of vidbyte/harnesses/native/codex/; the host, its connection, preflight, collaborators and response translator call it, so each failure code, operation, likely cause and next step is chosen in one place.
ARCHITECTURE NOTE: A static helper class with no values of its own: every sentence, table and bound comes from vidbyte/lib/constants/codex_host.py and vidbyte/lib/constants/codex.py. error() composes each message the way the lib error packets read (operation and code, what happened, the thread, the likely cause, the next step) and fills CodexAgentError's diagnostic fields with that code's own cause, the host's docs and its tests. openai-codex is imported inside from_exception only, so importing this module never loads the SDK (D-21).
COMMON MODIFICATION PATTERNS: A new failure source gets a branch in from_exception or a small builder here that passes its summary sentence to error(); a new code needs its row in CODEX_HOST_LIKELY_CAUSES and CODEX_NEXT_STEPS. Callers raise the result from None.
KNOWN EDGE CASES: A plain CodexError is exactly that class, never a subclass; once the connection's death flag is set every failure is codex.process_exited, because openai-codex fails every waiter with the reader's own error, which can quote a raw stdout line (EC-72). No message carries an exception's own text, stderr, env values or the account email; Codex's JSON-RPC message, the method, the code and a type name are the only variable parts (INV-9).
RELATED DOCS: docs/spec/codex-host/spec.md (sections 8.1 D-13 and D-27, and 9.2 error codes); vidbyte/lib/errors/base.py (CodexAgentError's packet)
TESTS: tests/features/codex_host/test_codex_host_failures.py, tests/features/codex_host/test_codex_host_turns.py, tests/features/codex_host/test_codex_host_error_details.py
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
from vidbyte.lib.constants.codex_host import (
    CODEX_GOAL_START_CALL,
    CODEX_HOST_EXITED_DURING_MESSAGE,
    CODEX_HOST_GOAL_PROBLEM_CODES,
    CODEX_HOST_GOAL_STOPPED_MESSAGE,
    CODEX_HOST_LIKELY_CAUSE_SENTENCE,
    CODEX_HOST_LIKELY_CAUSES,
    CODEX_HOST_LOCAL_FAILURE_MESSAGE,
    CODEX_HOST_MESSAGE_HEAD,
    CODEX_HOST_MISSING_SDK_CAUSE,
    CODEX_HOST_MISSING_SDK_MESSAGE,
    CODEX_HOST_MISSING_SDK_NEXT_STEP,
    CODEX_HOST_MODEL_MISMATCH_MESSAGE,
    CODEX_HOST_NEXT_STEP_SENTENCE,
    CODEX_HOST_NO_ANSWER_MESSAGE,
    CODEX_HOST_NOT_INSTALLED_MESSAGE,
    CODEX_HOST_PROCESS_EXITED_MESSAGE,
    CODEX_HOST_RELATED_DOCS,
    CODEX_HOST_RELEVANT_TESTS,
    CODEX_HOST_REVIEWER_MESSAGE,
    CODEX_HOST_RPC_ERROR_MESSAGE,
    CODEX_HOST_SDK_REFUSED_MESSAGE,
    CODEX_HOST_SENTENCE_SEPARATOR,
    CODEX_HOST_STOP_MESSAGES,
    CODEX_HOST_THREAD_SENTENCE,
    CODEX_HOST_TURN_FAILED_MESSAGE,
    CODEX_HOST_TURN_FAILED_SILENTLY_MESSAGE,
    CODEX_HOST_VERSION_MESSAGE,
)
from vidbyte.lib.dataclasses.codex import CodexTurnError
from vidbyte.lib.dataclasses.codex_host import CodexProblem
from vidbyte.lib.enums.codex import CodexGoalStatus, CodexHostOperation
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError


class CodexErrorMapper:
    """Builds CodexHost problems and errors, and maps SDK exceptions to failure codes."""

    @staticmethod
    def problem(code: FailureCode, message: str) -> CodexProblem:
        # A problem always carries its code's fixed next step.
        return CodexProblem(code=code, message=message, next_step=CODEX_NEXT_STEPS[code.value])

    @staticmethod
    def stop_problem(code: FailureCode) -> CodexProblem:
        # The problem of a turn Vidbyte itself interrupted for a budget.
        return CodexProblem(code=code, message=CODEX_HOST_STOP_MESSAGES[code], next_step=CODEX_NEXT_STEPS[code.value])

    @staticmethod
    def error(
        code: FailureCode,
        summary: str,
        operation: CodexHostOperation,
        thread_id: str = "",
        *,
        method: str = "",
        error_type: str = "",
        next_step: str = "",
        likely_cause: str = "",
    ) -> CodexAgentError:
        # The message reads as the lib error packets do: which function
        # failed with which code, what happened, the thread when one
        # exists, then the code's likely cause and its next step, so the
        # caller can act on the message alone. The same cause, the
        # host's docs and its tests fill the packet's fields.
        next_step = next_step or CODEX_NEXT_STEPS[code.value]
        likely_cause = likely_cause or CODEX_HOST_LIKELY_CAUSES[code.value]
        sentences = [CODEX_HOST_MESSAGE_HEAD.format(operation=operation.value, code=code.value), summary]
        if thread_id:
            sentences.append(CODEX_HOST_THREAD_SENTENCE.format(thread_id=thread_id))
        sentences.append(CODEX_HOST_LIKELY_CAUSE_SENTENCE.format(likely_cause=likely_cause))
        sentences.append(CODEX_HOST_NEXT_STEP_SENTENCE.format(next_step=next_step))
        return CodexAgentError(
            CODEX_HOST_SENTENCE_SEPARATOR.join(sentences),
            failure_code=code.value,
            operation=operation.value,
            error_type=error_type,
            next_step=next_step,
            thread_id=thread_id,
            likely_cause=likely_cause,
            method=method,
            related_docs=CODEX_HOST_RELATED_DOCS,
            relevant_tests=CODEX_HOST_RELEVANT_TESTS,
        )

    @classmethod
    def from_exception(cls, exc: Exception, operation: CodexHostOperation, method: str, *, dead: bool, bound_seconds: float, thread_id: str = "") -> CodexAgentError:
        # Map one exception raised while talking to Codex, in the
        # section 9.2 order. The SDK is imported here only, so importing
        # this module never loads it. Only the exception's class name
        # travels with the error, never its text.
        from openai_codex import errors as sdk

        error_type = type(exc).__name__
        # Once the app-server died, every failure is that death,
        # whatever the SDK raised, and its text is never shown.
        if dead or isinstance(exc, sdk.TransportClosedError):
            summary = CODEX_HOST_EXITED_DURING_MESSAGE.format(method=method)
            return cls.error(FailureCode.CODEX_PROCESS_EXITED, summary, operation, thread_id, method=method, error_type=error_type)
        # A JSON-RPC error carries Codex's own message and code, which
        # are safe to show; the method decides what the error means.
        if isinstance(exc, sdk.JsonRpcError):
            malformed = isinstance(exc, (sdk.InvalidParamsError, sdk.MethodNotFoundError, sdk.ParseError))
            refused = isinstance(exc, (sdk.InvalidRequestError, sdk.InvalidParamsError))
            code = cls._rpc_code(method, malformed=malformed, refused=refused)
            summary = CODEX_HOST_RPC_ERROR_MESSAGE.format(method=method, code=exc.code, message=exc.message)
            return cls.error(code, summary, operation, thread_id, method=method, error_type=error_type)
        # A plain CodexError from the goal start is its start window
        # elapsing; any other SDK error is the SDK refusing the call.
        if isinstance(exc, sdk.CodexError):
            window = type(exc) is sdk.CodexError and method == CODEX_GOAL_START_CALL
            code = FailureCode.CODEX_API_ERROR if window else FailureCode.CODEX_PROTOCOL_MISMATCH
            summary = CODEX_HOST_SDK_REFUSED_MESSAGE.format(method=method)
            return cls.error(code, summary, operation, thread_id, method=method, error_type=error_type)
        # Everything else is local: an answer the SDK model rejected,
        # the time bound elapsing, or an error nobody expected.
        code, summary = cls._local_failure(exc, method, bound_seconds)
        return cls.error(code, summary, operation, thread_id, method=method, error_type=error_type)

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
            return FailureCode.CODEX_PROTOCOL_MISMATCH, CODEX_HOST_MODEL_MISMATCH_MESSAGE.format(method=method)
        if isinstance(exc, TimeoutError):
            return FailureCode.CODEX_API_ERROR, CODEX_HOST_NO_ANSWER_MESSAGE.format(method=method, seconds=bound_seconds)
        return FailureCode.CODEX_API_ERROR, CODEX_HOST_LOCAL_FAILURE_MESSAGE.format(method=method, error_type=type(exc).__name__)

    @classmethod
    def missing_sdk(cls) -> CodexAgentError:
        # The Python extra is what is missing, so the cause and the next
        # step name the package and its install command, not the CLI.
        next_step = CODEX_HOST_MISSING_SDK_NEXT_STEP.format(extra=CODEX_SDK_EXTRA)
        return cls.error(FailureCode.CODEX_NOT_INSTALLED, CODEX_HOST_MISSING_SDK_MESSAGE, CodexHostOperation.OPEN_HOST, next_step=next_step, likely_cause=CODEX_HOST_MISSING_SDK_CAUSE)

    @classmethod
    def not_installed(cls, target: str) -> CodexAgentError:
        # Name what was searched for or launched, never the environment.
        return cls.error(FailureCode.CODEX_NOT_INSTALLED, CODEX_HOST_NOT_INSTALLED_MESSAGE.format(target=target), CodexHostOperation.OPEN_HOST)

    @classmethod
    def version_unsupported(cls, found: str) -> CodexAgentError:
        # Name both versions, so the caller knows how far to update.
        summary = CODEX_HOST_VERSION_MESSAGE.format(found=found, minimum=CODEX_HOST_MINIMUM_VERSION)
        return cls.error(FailureCode.CODEX_VERSION_UNSUPPORTED, summary, CodexHostOperation.OPEN_HOST)

    @classmethod
    def reviewer_refusal(cls, operation: CodexHostOperation, thread_id: str) -> CodexAgentError:
        # Codex would route approvals to a person nothing in this
        # release answers, so the operation stops before the thread
        # spends (D-32).
        return cls.error(FailureCode.CONFIGURATION_UNSUPPORTED_COMBINATION, CODEX_HOST_REVIEWER_MESSAGE, operation, thread_id)

    @classmethod
    def process_exited(cls, operation: CodexHostOperation, thread_id: str = "") -> CodexAgentError:
        # A closed or dead host sends nothing, so this needs no
        # exception.
        return cls.error(FailureCode.CODEX_PROCESS_EXITED, CODEX_HOST_PROCESS_EXITED_MESSAGE, operation, thread_id)

    @classmethod
    def goal_problem(cls, status: CodexGoalStatus) -> CodexProblem | None:
        # A goal Codex stopped for its token budget or the account's
        # usage limit is a failure; every other final goal status is
        # not.
        code = CODEX_HOST_GOAL_PROBLEM_CODES.get(status)
        return None if code is None else cls.problem(code, CODEX_HOST_GOAL_STOPPED_MESSAGE.format(status=status.value))

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
        message = CODEX_HOST_TURN_FAILED_MESSAGE.format(message=error.message) if error is not None else CODEX_HOST_TURN_FAILED_SILENTLY_MESSAGE
        return CodexProblem(code=code, message=message, next_step=CODEX_NEXT_STEPS[code.value])


__all__ = ["CodexErrorMapper"]

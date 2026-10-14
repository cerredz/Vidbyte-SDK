"""FILE: vidbyte/harnesses/native/codex/preflight.py

PURPOSE: Runs the checks CodexHost makes before anything spends: the account is signed in, ordinary usage is not used up, the Windows sandbox is ready, every model named is listed, the thread is idle and exists, and each request field is one its operation uses.
ROLE IN CODEBASE: The check layer of vidbyte/harnesses/native/codex/; CodexHost calls it at the start of every operation that starts a turn, reads a thread or forks one.
ARCHITECTURE NOTE: Imports no openai-codex module; it reaches Codex only through CodexConnection, so every check is bounded and mapped like any other call. sys.platform is read at call time through sys, as section 13 requires, and the all-pages model list is fetched at most once per host.
COMMON MODIFICATION PATTERNS: A new check is one step in run(), in the section 9.2 order; a new per-operation field rule is one entry in REJECTED_FIELDS.
KNOWN EDGE CASES: A rate-limit read error or a None allowance passes, so preflight never infers exhaustion or recovery (EC-8). A runtime that cannot report Windows sandbox readiness passes (EC-11), and FULL_ACCESS skips that check. A custom model_provider skips the model check, because the list describes the default provider (EC-13).
RELATED DOCS: docs/spec/codex-host/spec.md (sections 8.1 D-28, 9.2 per-operation field rules)
TESTS: tests/features/codex_host/test_codex_host_threads.py, tests/features/codex_host/test_codex_host_turns.py
"""

from __future__ import annotations

import operator
import sys
from contextlib import suppress
from typing import TYPE_CHECKING

from vidbyte.harnesses.native.codex.errors import CodexErrorMapper
from vidbyte.lib.constants.codex import (
    CODEX_MODEL_LIST_METHOD,
    CODEX_RATE_LIMITS_READ_METHOD,
)
from vidbyte.lib.dataclasses.codex_host import CodexModelInfo, CodexSpawnRequest
from vidbyte.lib.enums.codex import CodexHostOperation, CodexSandbox
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError, ConfigurationError

if TYPE_CHECKING:
    from openai_codex.generated.v2_all import Thread

    from vidbyte.harnesses.native.codex.connection import CodexConnection
    from vidbyte.harnesses.native.codex.turns import CodexTurnRegistry
    from vidbyte.harnesses.native.codex.wire import (
        CodexParamsTranslator,
        CodexResponseTranslator,
    )

# The only platform with a sandbox readiness check (D-28).
WINDOWS_PLATFORM = "win32"
# The request every rejected field is compared with.
DEFAULT_REQUEST = CodexSpawnRequest()
# The fields each operation rejects when they differ from the default (INV-27).
REJECTED_FIELDS: dict[CodexHostOperation, tuple[str, ...]] = {
    CodexHostOperation.CONTINUE_CODEX_THREAD: (
        "prompt",
        "goal",
        "thread.ephemeral",
        "thread.thread_source",
        "thread.service_name",
        "thread.session_start_source",
        "tools",
        "name",
    ),
    CodexHostOperation.FORK_CODEX_THREAD: (
        "prompt",
        "goal",
        "thread.personality",
        "thread.service_name",
        "thread.session_start_source",
        "turn",
        "tools",
        "disabled_plugin_ids",
        "output_schema",
        "max_output_tokens",
        "timeout_seconds",
    ),
    CodexHostOperation.LAUNCH_CODEX_SUBAGENTS: ("prompt", "goal"),
}
USAGE_LIMITED_MESSAGE = "Codex reports that ordinary usage is not allowed right now."
BUSY_MESSAGE = "The thread already has a running turn on this host."


class CodexPreflight:
    """The section 9.2 checks CodexHost runs before any request that spends."""

    def __init__(
        self,
        connection: CodexConnection,
        params: CodexParamsTranslator,
        responses: CodexResponseTranslator,
        registry: CodexTurnRegistry,
    ) -> None:
        # The model list is fetched once, with hidden models, and reused.
        self._connection = connection
        self._params = params
        self._responses = responses
        self._registry = registry
        self._models: tuple[CodexModelInfo, ...] = ()

    async def run(self, operation: CodexHostOperation, request: CodexSpawnRequest, *, check_model: bool = True) -> None:
        # @intent check-before-anything-spends
        # The checks run in the section 9.2 order and stop at the first
        # failure, before any request that spends (D-28).
        # 1. The account must be signed in. The client method is looked up
        #    now, so a patched or replaced reader is the one used.
        account = await self._connection.call(operation, "account/read", self._connection.client.account_read)
        problem = self._responses.sign_in_problem(account)
        if problem is not None:
            raise CodexErrorMapper.error(problem.code, problem.message, operation)
        # 2. Ordinary usage must not be used up. A read error or a None
        #    allowance passes, so neither exhaustion nor recovery is guessed.
        allowed = None
        with suppress(CodexAgentError):
            limits = await self._connection.call(operation, CODEX_RATE_LIMITS_READ_METHOD, self._connection.raw(CODEX_RATE_LIMITS_READ_METHOD, None))
            allowed = limits.ordinary_usage_allowed
        if allowed is False:
            raise CodexErrorMapper.error(FailureCode.CODEX_USAGE_LIMITED, USAGE_LIMITED_MESSAGE, operation)
        # 3. On Windows the sandbox must be ready, unless the turn's
        #    sandbox, else the thread's, is FULL_ACCESS.
        sandbox = request.turn.sandbox.value or request.thread.sandbox.value
        if sandbox != CodexSandbox.FULL_ACCESS.value:
            problem = self._responses.sandbox_problem(await self.sandbox_status(operation))
            if problem is not None:
                raise CodexErrorMapper.error(problem.code, problem.message, operation)
        # 4. Every model named must be listed, hidden ones included, unless
        #    a custom provider is set, whose models the list does not show.
        names = {request.thread.model, request.turn.model} - {""}
        if not check_model or not names or request.thread.model_provider:
            return
        self._models = self._models or await self.models(operation, include_hidden=True)
        known = {model.model_id for model in self._models} | {model.model for model in self._models}
        unknown = sorted(names - known)
        if unknown:
            visible = ", ".join(model.model_id for model in self._models if not model.hidden)
            message = f"Codex lists no model named {', '.join(unknown)}. Listed models: {visible}."
            raise CodexErrorMapper.error(FailureCode.CODEX_MODEL_UNKNOWN, message, operation)

    async def sandbox_status(self, operation: CodexHostOperation) -> str:
        # The readiness check exists only on Windows, read at call time;
        # elsewhere the sandbox is not checked.
        if sys.platform != WINDOWS_PLATFORM:
            return ""
        return await self._connection.sandbox_status(operation)

    async def models(self, operation: CodexHostOperation, include_hidden: bool) -> tuple[CodexModelInfo, ...]:
        # @intent list-every-model-page-once
        # model/list is read page by page until the cursor is empty, or
        # repeats, which ends the loop rather than spinning on it.
        models: list[CodexModelInfo] = []
        cursor = ""
        seen: set[str] = set()
        while True:
            fetch_page = self._connection.raw(CODEX_MODEL_LIST_METHOD, self._params.model_page(include_hidden, cursor))
            page = await self._connection.call(operation, CODEX_MODEL_LIST_METHOD, fetch_page)
            models.extend(self._responses.model_info(model) for model in page.data)
            seen.add(cursor)
            cursor = page.next_cursor or ""
            if not cursor or cursor in seen:
                return tuple(models)

    def require_idle(self, operation: CodexHostOperation, thread_id: str) -> None:
        # A thread with a running or reserved turn takes no second one (INV-24).
        if self._registry.busy(thread_id):
            raise CodexErrorMapper.error(FailureCode.CODEX_SESSION_BUSY, BUSY_MESSAGE, operation, thread_id)

    async def require_thread(self, operation: CodexHostOperation, thread_id: str, include_turns: bool = False) -> Thread:
        # The thread must exist; a failed read maps to session_not_found.
        response = await self._connection.call(operation, "thread/read", self._connection.client.thread_read, thread_id, include_turns, thread_id=thread_id)
        return response.thread

    @staticmethod
    def reject_unusable_fields(request: CodexSpawnRequest, operation: CodexHostOperation) -> None:
        # A field the operation does not use fails before any request, so
        # a setting is never silently ignored (INV-27).
        for name in REJECTED_FIELDS.get(operation, ()):
            read = operator.attrgetter(name)
            if read(request) != read(DEFAULT_REQUEST):
                raise ConfigurationError(f"{operation.value} does not use the CodexSpawnRequest field {name}; leave it at its default.")


__all__ = ["CodexPreflight"]

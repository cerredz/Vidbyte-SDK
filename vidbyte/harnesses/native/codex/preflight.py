"""FILE: vidbyte/harnesses/native/codex/preflight.py

PURPOSE: Runs the checks CodexHost makes before anything spends: a USER approvals reviewer has a handler to answer it, a feature that needs Codex's experimental API is used only on a host that opted in, the account is signed in, ordinary usage is not used up, the Windows sandbox is ready, every model and service tier named is listed, and the thread is idle and exists.
ROLE IN CODEBASE: The check layer of vidbyte/harnesses/native/codex/; CodexHost and its feature mixins call it at the start of every operation that starts a turn, changes settings, reads a thread or forks one, check_codex_ready reuses its usage read, the run wrappers and the fork call its reviewer checks on their own, and every experimental function calls its one experimental gate right after its input record (first-class D-15).
ARCHITECTURE NOTE: Imports no openai-codex module; it reaches Codex only through CodexConnection, so every check is bounded and mapped like any other call. sys.platform is read at call time through sys, as section 13 requires. The all-pages model list is cached per host and read once more only when the cached list misses a model or tier the request names (hardening INV-25, D-26).
COMMON MODIFICATION PATTERNS: A new check is one step in run(), in the section 9.2 order, with its message in vidbyte/lib/constants/codex_host.py. A new function that needs Codex's experimental API calls require_experimental_api right after its record, never a gate of its own. A per-operation field rule is an argument check, so it belongs to the operation's input record in vidbyte/lib/dataclasses/codex_host_inputs.py (CODEX_HOST_REJECTED_FIELDS), not here.
KNOWN EDGE CASES: A rate-limit read error or a None allowance passes, so preflight never infers exhaustion or recovery (EC-8). A runtime that cannot report Windows sandbox readiness passes (EC-11), and FULL_ACCESS skips that check. A custom model_provider skips the model and tier checks, because the list describes the default provider (EC-13); a tier is checked only against models that list tiers, so a tierless model leaves the choice to Codex (hardening EC-35). A fork runs only step 0 and the model and tier check (spends=False), and a USER reviewer passes on a host whose approval_handler answers it (hardening INV-20). A collaboration mode is refused locally on a host opened without the experimental API, and its model is checked like the turn's; the gate is local, so its refusal sends nothing (first-class INV-4, INV-12). A reviewer Codex resolved, which the request never named, is refused by reject_routed_reviewer only on a host without an approval_handler (first-class D-36).
RELATED DOCS: docs/spec/codex-host/spec.md (sections 8.1 D-28 and 9.2 preflight order); docs/spec/codex-host-hardening/spec.md (sections 6.1 INV-20, INV-24, INV-25 and INV-36, and 8.1 D-5, D-25 and D-26); docs/spec/codex-host-first-class/spec.md (INV-4, INV-12, INV-13, D-15, D-36)
TESTS: tests/features/codex_host/test_codex_host_threads.py, tests/features/codex_host/test_codex_host_turns.py, tests/features/codex_host/test_codex_host_function_rows.py, tests/features/codex_host/test_codex_host_turn_settings.py, tests/features/codex_host/test_codex_host_approvals.py, tests/features/codex_host/test_codex_host_feature_contract.py, tests/features/codex_host/test_codex_host_settings_modes.py, tests/features/codex_host/test_codex_host_side_chat.py
"""

from __future__ import annotations

import sys
from contextlib import suppress
from typing import TYPE_CHECKING

from vidbyte.harnesses.native.codex.errors import CodexErrorMapper
from vidbyte.lib.constants.codex import (
    CODEX_ACCOUNT_READ_METHOD,
    CODEX_HOST_USER_REVIEWER_TEXT,
    CODEX_MODEL_LIST_METHOD,
    CODEX_RATE_LIMITS_READ_METHOD,
    CODEX_THREAD_READ_METHOD,
)
from vidbyte.lib.constants.codex_host import (
    CODEX_DEFAULT_SERVICE_TIER,
    CODEX_HOST_ANY_MODEL_TEXT,
    CODEX_HOST_BUSY_MESSAGE,
    CODEX_HOST_EXPERIMENTAL_FEATURE_MESSAGE,
    CODEX_HOST_LIST_SEPARATOR,
    CODEX_HOST_MODEL_UNKNOWN_MESSAGE,
    CODEX_HOST_SANDBOX_PLATFORM,
    CODEX_HOST_UNKNOWN_TIER_MESSAGE,
    CODEX_HOST_USAGE_LIMITED_MESSAGE,
    CODEX_HOST_USER_REVIEWER_MESSAGE,
)
from vidbyte.lib.dataclasses.codex_host import (
    CodexModelInfo,
    CodexProblem,
    CodexSpawnRequest,
)
from vidbyte.lib.enums.codex import (
    CodexApprovalsReviewer,
    CodexHostOperation,
    CodexSandbox,
    CodexSandboxReadiness,
)
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

class CodexPreflight:
    """The section 9.2 checks CodexHost runs before any request that spends."""

    def __init__(
        self,
        connection: CodexConnection,
        params: CodexParamsTranslator,
        responses: CodexResponseTranslator,
        registry: CodexTurnRegistry,
        *,
        approvals_answered: bool,
        experimental_api: bool = True,
    ) -> None:
        # The model list is fetched with hidden models and reused until
        # it misses a name. approvals_answered says whether the host has
        # an approval_handler, which a USER reviewer needs, and
        # experimental_api whether the host opted in to Codex's
        # experimental API (first-class D-15).
        self._connection = connection
        self._params = params
        self._responses = responses
        self._registry = registry
        self._approvals_answered = approvals_answered
        self._experimental_api = experimental_api
        self._models: tuple[CodexModelInfo, ...] = ()

    async def run(self, operation: CodexHostOperation, request: CodexSpawnRequest, *, check_model: bool = True, spends: bool = True) -> None:
        # @intent check-before-anything-spends
        # The checks run in the section 9.2 order and stop at the first
        # failure, before any request that spends (D-28).
        # 0. A USER reviewer needs a handler to answer its approvals;
        #    this check is local, so its refusal sends nothing.
        self.reject_user_reviewer(operation, request)
        # A collaboration mode needs the experimental API; this gate is
        # local too (first-class INV-4).
        self.require_experimental_api(operation, "collaboration_mode", used=request.collaboration_mode is not None)
        # A fork spends nothing, so it skips the account, usage and
        # sandbox and keeps only the model and tier check.
        if spends:
            # 1. The account must be signed in. The client method is
            #    looked up now, so a patched or replaced reader is used.
            account = await self._connection.call(operation, CODEX_ACCOUNT_READ_METHOD, self._connection.client.account_read)
            problem = self._responses.sign_in_problem(account)
            if problem is not None:
                raise CodexErrorMapper.error(problem.code, problem.message, operation)
            # 2. Ordinary usage must not be used up.
            problem = await self.usage_problem(operation)
            if problem is not None:
                raise CodexErrorMapper.error(problem.code, problem.message, operation)
            # 3. On Windows the sandbox must be ready, unless the turn's
            #    sandbox, else the thread's, is FULL_ACCESS.
            sandbox = request.turn.sandbox.value or request.thread.sandbox.value
            if sandbox != CodexSandbox.FULL_ACCESS.value:
                problem = self._responses.sandbox_problem(await self.sandbox_status(operation))
                if problem is not None:
                    raise CodexErrorMapper.error(problem.code, problem.message, operation)
        # 4. Every model and service tier named must be listed, hidden
        #    models included, unless a custom provider is set, whose
        #    models the list does not show. A collaboration mode's model
        #    wins over the turn's, so it is the one checked (first-class
        #    INV-13). The default tier and an empty one leave the choice
        #    to Codex.
        names = {request.thread.model, self._params.turn_model(request)} - {""}
        asked = (request.thread.service_tier, request.turn.service_tier, request.turn_service_tier)
        tiers = tuple(tier for tier in asked if tier not in ("", CODEX_DEFAULT_SERVICE_TIER))
        if not check_model or not (names or tiers) or request.thread.model_provider:
            return
        # A miss on the cached list reads the list once more, because
        # Codex may have added the model or tier since; a list this
        # check has just fetched is not read again (INV-25, D-26).
        cached = bool(self._models)
        self._models = self._models or await self.models(operation, include_hidden=True)
        problem_text = self._model_problem(names) or self._tier_problem(names, tiers)
        if problem_text and cached:
            self._models = await self.models(operation, include_hidden=True)
            problem_text = self._model_problem(names) or self._tier_problem(names, tiers)
        if problem_text:
            raise CodexErrorMapper.error(FailureCode.CODEX_MODEL_UNKNOWN, problem_text, operation)

    def reject_user_reviewer(self, operation: CodexHostOperation, request: CodexSpawnRequest) -> None:
        # @intent a-user-reviewer-needs-a-handler-to-answer-it
        # A USER reviewer sends the thread's approval requests to this
        # process, so on a host built without an approval_handler it is
        # refused here, locally, before any request (hardening INV-20).
        if request.approvals_reviewer is CodexApprovalsReviewer.USER and not self._approvals_answered:
            raise CodexErrorMapper.error(FailureCode.CONFIGURATION_UNSUPPORTED_COMBINATION, CODEX_HOST_USER_REVIEWER_MESSAGE, operation, next_step=CODEX_HOST_USER_REVIEWER_TEXT)

    def require_experimental_api(self, operation: CodexHostOperation, feature: str, *, used: bool = True) -> None:
        # @intent one-gate-for-every-experimental-feature
        # A feature Codex accepts only from clients that opt in to its
        # experimental API is refused here, locally, on a host opened
        # without it, so the refusal sends nothing (first-class INV-4,
        # D-15). used is False when the request does not use it.
        if used and not self._experimental_api:
            raise ConfigurationError(CODEX_HOST_EXPERIMENTAL_FEATURE_MESSAGE.format(operation=operation.value, feature=feature), details={"field": "experimental_api"})

    def reject_routed_reviewer(self, operation: CodexHostOperation, thread_id: str, routed: bool) -> None:
        # @intent a-reviewer-codex-resolved-needs-a-handler-too
        # A thread Codex opened with its approvals routed to a person,
        # from config.toml or a parent, though the request named no
        # reviewer, is refused on a host without an approval_handler,
        # naming that thread (first-class D-36, hardening D-32).
        if routed and not self._approvals_answered:
            raise CodexErrorMapper.reviewer_refusal(operation, thread_id)

    async def usage_problem(self, operation: CodexHostOperation) -> CodexProblem | None:
        # Ordinary usage used up is a problem. A read error or a None
        # allowance is none, so neither exhaustion nor recovery is
        # guessed (EC-8); check_codex_ready reports the same problem
        # (hardening INV-24, D-25).
        with suppress(CodexAgentError):
            limits = await self._connection.call(operation, CODEX_RATE_LIMITS_READ_METHOD, self._connection.raw(CODEX_RATE_LIMITS_READ_METHOD, None))
            if limits.ordinary_usage_allowed is False:
                return CodexErrorMapper.problem(FailureCode.CODEX_USAGE_LIMITED, CODEX_HOST_USAGE_LIMITED_MESSAGE)
        return None

    async def sandbox_status(self, operation: CodexHostOperation) -> CodexSandboxReadiness:
        # The readiness check exists only on Windows, read at call time;
        # elsewhere the sandbox is not checked.
        if sys.platform != CODEX_HOST_SANDBOX_PLATFORM:
            return CodexSandboxReadiness.NOT_CHECKED
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
        # A thread with a running or reserved turn, or with a start
        # still in flight after its caller left, takes no second one
        # (INV-24).
        if self._registry.busy(thread_id) or self._connection.starting(thread_id):
            raise CodexErrorMapper.error(FailureCode.CODEX_SESSION_BUSY, CODEX_HOST_BUSY_MESSAGE, operation, thread_id)

    async def require_thread(self, operation: CodexHostOperation, thread_id: str, include_turns: bool = False) -> Thread:
        # The thread must exist; a refused read maps to
        # session_not_found (hardening INV-4).
        response = await self._connection.call(operation, CODEX_THREAD_READ_METHOD, self._connection.client.thread_read, thread_id, include_turns, thread_id=thread_id)
        return response.thread

    def _model_problem(self, names: set[str]) -> str:
        # The refusal text for the named models the cached list lacks,
        # by id or by name, or "" when every one is listed.
        known = {model.model_id for model in self._models} | {model.model for model in self._models}
        unknown = sorted(names - known)
        if not unknown:
            return ""
        visible = CODEX_HOST_LIST_SEPARATOR.join(model.model_id for model in self._models if not model.hidden)
        return CODEX_HOST_MODEL_UNKNOWN_MESSAGE.format(unknown=CODEX_HOST_LIST_SEPARATOR.join(unknown), visible=visible)

    def _tier_problem(self, names: set[str], tiers: tuple[str, ...]) -> str:
        # The refusal text for the first tier asked for that the named
        # models, or every listed model when none is named, do not
        # list; "" when each is listed, or when those models list no
        # tiers at all (hardening INV-36, EC-35).
        models = [model for model in self._models if not names or model.model_id in names or model.model in names]
        listed = sorted({tier.tier_id for model in models for tier in model.service_tiers})
        unlisted = [tier for tier in tiers if tier not in listed]
        if not listed or not unlisted:
            return ""
        named = CODEX_HOST_LIST_SEPARATOR.join(sorted(names)) if names else CODEX_HOST_ANY_MODEL_TEXT
        return CODEX_HOST_UNKNOWN_TIER_MESSAGE.format(tier=unlisted[0], models=named, tiers=CODEX_HOST_LIST_SEPARATOR.join(listed))


__all__ = ["CodexPreflight"]

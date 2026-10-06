"""FILE: tests/test_codex_failure_recovery.py

PURPOSE:
    Feature tests for the Codex failure vocabulary and model fallback:
    CodexFailureTranslator's per-code classification, CodexFailureLedger's
    per-turn lifecycle, CodexFallbackCoordinator's construction gates and
    advance decision, and CodexHarnessAgent's attempt loop. Locks the
    behavior docs/design/codex-failure-recovery.md specifies: an unclassified
    code is terminal, both judgments must agree before spending an extra
    turn, and a fallback answer is reported as one.

ROLE IN CODEBASE:
    Exercises vidbyte/agents/codex/failures.py,
    vidbyte/agents/codex/fallback.py, the attempt loop in
    vidbyte/agents/codex/agent.py, and the metadata keys in
    vidbyte/agents/codex/result.py, against the real
    vidbyte/agents/fallback.py and vidbyte/lib/dataclasses/failure.py.

ARCHITECTURE NOTE:
    Every test runs offline. Only CodexTransport is faked; the real
    AgentFallbackSettings, AgentFallback, Failure, and FailureSafety all run,
    because the defect this guards against — the two judgments disagreeing,
    or a retry on a terminal code — only appears wired together.

FUNCTION INVENTORY:
    No production functions. _error() builds one classified adapter error,
    _codex_settings() builds provider settings naming a primary model, and
    _build_agent() wires an agent to a scripted transport.

COMMON MODIFICATION PATTERNS:
    Add a codex.* failure code, then add its row to the classification table;
    ClassificationCoverageTests fails until you do.

WHAT NOT TO DO IN THIS FILE:
    Do not assert that an unclassified code is retryable, and do not assert a
    specific FallbackModel api_key reaches any record — it must not.

KNOWN EDGE CASES:
    A recovered turn still records its failed attempt; a cancelled turn is
    never classified and never triggers a fallback.

RELATED DOCS: docs/design/codex-failure-recovery.md
TESTS: python -m pytest tests/test_codex_failure_recovery.py
"""

from __future__ import annotations

import asyncio
import unittest

from vidbyte.agents.codex.agent import CodexHarnessAgent
from vidbyte.agents.codex.failures import CodexFailureLedger, CodexFailureTranslator
from vidbyte.agents.codex.fallback import CodexFallbackCoordinator
from vidbyte.agents.settings.fallback import AgentFallbackSettings
from vidbyte.lib.constants.codex import (
    CODEX_ANSWERING_MODEL_KEY,
    CODEX_FAILURE_CLASSIFICATION,
    CODEX_FAILURE_SOURCE,
    CODEX_FAILURES_KEY,
    CODEX_FALLBACK_ATTEMPTS_KEY,
    CODEX_MAX_TURN_FAILURES,
    CODEX_USAGE_PROVIDER,
)
from vidbyte.lib.dataclasses.agents import FallbackModel
from vidbyte.lib.dataclasses.codex import (
    CodexAgentSettings,
    CodexFailureRecord,
    CodexFailureTranslationRequest,
    CodexFallbackAttempt,
    CodexFallbackDecision,
    CodexHarnessAgentSettings,
    CodexRunInput,
    CodexRunResult,
    CodexThreadSettings,
    CodexTransportRunRequest,
    CodexTurnSettings,
    CodexUsage,
)
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.lib.enums.codex import CodexFailureClass
from vidbyte.lib.enums.failure import (
    FailureCode,
    FailureDisposition,
    FailurePhase,
    FailureSeverity,
)
from vidbyte.lib.errors import CodexAgentError, ConfigurationError
from vidbyte.middleware.base import AgentMiddleware

FINAL_RESPONSE = "codex reply"
PRIMARY_MODEL = "gpt-5-codex"
BACKUP_MODEL = "gpt-5-codex-mini"


def _run_result() -> CodexRunResult:
    # Builds one completed native snapshot with no usage reported.
    return CodexRunResult(
        thread_id="th_1",
        turn_id="tu_1",
        status="completed",
        final_response=FINAL_RESPONSE,
        duration_ms=12,
        usage=CodexUsage(),
        items=(),
    )


def _error(
    code: FailureCode = FailureCode.CODEX_TURN_FAILED, cause: Exception | None = None
) -> CodexAgentError:
    # Builds one classified adapter error, optionally with a chained cause.
    error = CodexAgentError(
        "Codex failed the requested turn.",
        failure_code=code.value,
        operation="turn_run",
    )
    if cause is not None:
        try:
            raise error from cause
        except CodexAgentError as raised:
            return raised
    return error


def _codex_settings(
    turn_model: str = PRIMARY_MODEL,
    thread_model: str = "",
    model_provider: str = "",
) -> CodexAgentSettings:
    # Builds provider settings that may name a model at either lifecycle layer.
    return CodexAgentSettings(
        thread=CodexThreadSettings(model=thread_model, model_provider=model_provider),
        turn=CodexTurnSettings(model=turn_model),
    )


class _ScriptedTransport:
    """Stands in for CodexTransport, raising a scripted sequence then succeeding."""

    def __init__(self, failures: list[BaseException] | None = None) -> None:
        self.failures = list(failures or [])
        self.requests: list[CodexTransportRunRequest] = []

    async def run(self, request: CodexTransportRunRequest) -> CodexRunResult:
        # Records each attempt's request so the per-attempt model override is visible.
        self.requests.append(request)
        if self.failures:
            raise self.failures.pop(0)
        return _run_result()


class _ErrorObserver(AgentMiddleware):
    """Records every exception on_model_error was handed."""

    def __init__(self) -> None:
        self.errors: list[BaseException | None] = []

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Captures the error so the test can count failed attempts it observed.
        self.errors.append(ctx.error)
        return MiddlewareDecision.continue_()


def _build_agent(
    failures: list[BaseException] | None = None,
    fallback: AgentFallbackSettings | None = None,
    codex: CodexAgentSettings | None = None,
    middleware: tuple[AgentMiddleware, ...] = (),
) -> tuple[CodexHarnessAgent, _ScriptedTransport]:
    # Builds an agent whose transport is scripted, so no Codex process is started.
    agent = CodexHarnessAgent(
        CodexHarnessAgentSettings(
            name="codex-agent",
            system_prompt="You are a Codex harness agent.",
            codex=codex if codex is not None else _codex_settings(),
            fallback=fallback,
            middleware=middleware,
        )
    )
    transport = _ScriptedTransport(failures)
    agent._transport = transport  # type: ignore[assignment]
    return agent, transport


class ClassificationCoverageTests(unittest.TestCase):
    """Covers that the classification table stays complete as codes are added."""

    def test_every_codex_failure_code_has_a_classification_row(self) -> None:
        codex_codes = {
            code.value for code in FailureCode if code.value.startswith("codex.")
        }

        self.assertEqual(codex_codes - set(CODEX_FAILURE_CLASSIFICATION), set())

    def test_every_classification_row_names_a_real_failure_code(self) -> None:
        known = {code.value for code in FailureCode}

        self.assertEqual(set(CODEX_FAILURE_CLASSIFICATION) - known, set())


class FailureTranslationTests(unittest.TestCase):
    """Covers how one adapter error becomes a canonical failure record."""

    def test_classifies_a_turn_failure_as_model_retryable(self) -> None:
        record = CodexFailureTranslator.translate(
            CodexFailureTranslationRequest(error=_error())
        )

        self.assertIs(record.failure_class, CodexFailureClass.MODEL_RETRYABLE)
        self.assertIs(record.failure.phase, FailurePhase.MODEL)

    def test_classifies_a_missing_sdk_as_terminal(self) -> None:
        record = CodexFailureTranslator.translate(
            CodexFailureTranslationRequest(
                error=_error(FailureCode.CODEX_SDK_UNAVAILABLE)
            )
        )

        self.assertIs(record.failure_class, CodexFailureClass.TERMINAL)
        self.assertIs(record.failure.phase, FailurePhase.CONFIGURATION)

    def test_classifies_a_translation_failure_as_terminal_input(self) -> None:
        record = CodexFailureTranslator.translate(
            CodexFailureTranslationRequest(
                error=_error(FailureCode.CODEX_VIDBYTE_TRANSLATION_FAILED)
            )
        )

        self.assertIs(record.failure_class, CodexFailureClass.TERMINAL)
        self.assertIs(record.failure.phase, FailurePhase.INPUT)

    def test_classifies_a_resume_failure_as_transient(self) -> None:
        record = CodexFailureTranslator.translate(
            CodexFailureTranslationRequest(
                error=_error(FailureCode.CODEX_THREAD_RESUME_FAILED)
            )
        )

        self.assertIs(record.failure_class, CodexFailureClass.TRANSIENT)
        self.assertIs(record.failure.phase, FailurePhase.SESSION)

    def test_an_unclassified_code_resolves_to_terminal_and_critical(self) -> None:
        rule = CodexFailureTranslator._rule("codex.added_without_a_table_row")

        self.assertEqual(
            rule,
            (
                CodexFailureClass.TERMINAL.value,
                FailurePhase.UNKNOWN.value,
                FailureSeverity.CRITICAL.value,
                FailureDisposition.RAISE.value,
            ),
        )

    def test_a_code_outside_the_shared_enum_is_rejected_by_Failure(self) -> None:
        error = _error()
        error.failure_code = "codex.not_a_failure_code_member"

        with self.assertRaises(ValueError):
            CodexFailureTranslator.translate(
                CodexFailureTranslationRequest(error=error)
            )

    def test_marks_a_classified_code_as_classified(self) -> None:
        record = CodexFailureTranslator.translate(
            CodexFailureTranslationRequest(error=_error())
        )

        self.assertTrue(record.failure.details["classified"])

    def test_names_the_codex_adapter_as_the_failure_source(self) -> None:
        record = CodexFailureTranslator.translate(
            CodexFailureTranslationRequest(error=_error())
        )

        self.assertEqual(record.failure.source, CODEX_FAILURE_SOURCE)

    def test_carries_the_operation_into_details(self) -> None:
        record = CodexFailureTranslator.translate(
            CodexFailureTranslationRequest(error=_error())
        )

        self.assertEqual(record.failure.details["operation"], "turn_run")

    def test_carries_the_chained_cause_type_into_details(self) -> None:
        record = CodexFailureTranslator.translate(
            CodexFailureTranslationRequest(error=_error(cause=TimeoutError("slow")))
        )

        self.assertEqual(record.failure.details["error_type"], "TimeoutError")

    def test_carries_the_attempt_and_chain_index_into_details(self) -> None:
        record = CodexFailureTranslator.translate(
            CodexFailureTranslationRequest(error=_error(), attempt=3, chain_index=2)
        )

        self.assertEqual(record.failure.details["attempt"], 3)
        self.assertEqual(record.failure.details["chain_index"], 2)

    def test_redacts_a_credential_shaped_detail_key(self) -> None:
        error = _error()
        error.operation = "turn_run"

        record = CodexFailureTranslator.translate(
            CodexFailureTranslationRequest(error=error)
        )
        polluted = dict(record.failure.details)
        polluted["api_key_hint"] = "sk-live"
        from vidbyte.lib.dataclasses.failure import FailureSafety

        self.assertNotIn("api_key_hint", FailureSafety.sanitize_mapping(polluted))

    def test_rejects_an_exception_without_a_failure_code(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexFailureTranslationRequest(error=TimeoutError("no code"))

    def test_rejects_a_negative_attempt(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexFailureTranslationRequest(error=_error(), attempt=-1)


class FailureLedgerTests(unittest.TestCase):
    """Covers the bounded per-turn ledger."""

    def setUp(self) -> None:
        self.ledger = CodexFailureLedger()

    def _record(self) -> CodexFailureRecord:
        # Builds one classified record for the ledger under test.
        return CodexFailureTranslator.translate(
            CodexFailureTranslationRequest(error=_error())
        )

    def test_starts_empty(self) -> None:
        self.assertEqual(self.ledger.failures, ())

    def test_reset_clears_recorded_failures(self) -> None:
        self.ledger.record(self._record())

        self.ledger.reset()

        self.assertEqual(self.ledger.failures, ())

    def test_bounds_retained_failures_keeping_the_most_recent(self) -> None:
        for index in range(CODEX_MAX_TURN_FAILURES + 5):
            self.ledger.record(
                CodexFailureTranslator.translate(
                    CodexFailureTranslationRequest(error=_error(), attempt=index + 1)
                )
            )

        retained = self.ledger.failures
        self.assertEqual(len(retained), CODEX_MAX_TURN_FAILURES)
        self.assertEqual(
            retained[-1].details["attempt"], CODEX_MAX_TURN_FAILURES + 5
        )


class FallbackConstructionTests(unittest.TestCase):
    """Covers the gates CodexFallbackCoordinator.build applies."""

    def test_is_disabled_without_a_chain(self) -> None:
        coordinator = CodexFallbackCoordinator.build(
            CodexHarnessAgentSettings(name="a", system_prompt="p")
        )

        self.assertFalse(coordinator.enabled)

    def test_is_disabled_for_a_chain_marked_not_enabled(self) -> None:
        coordinator = CodexFallbackCoordinator.build(
            CodexHarnessAgentSettings(
                name="a",
                system_prompt="p",
                codex=_codex_settings(),
                fallback=AgentFallbackSettings(models=[BACKUP_MODEL], enabled=False),
            )
        )

        self.assertFalse(coordinator.enabled)

    def test_raises_when_no_model_is_named_at_either_layer(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexFallbackCoordinator.build(
                CodexHarnessAgentSettings(
                    name="a",
                    system_prompt="p",
                    codex=_codex_settings(turn_model="", thread_model=""),
                    fallback=AgentFallbackSettings(models=[BACKUP_MODEL]),
                )
            )

    def test_raises_naming_an_entry_whose_provider_is_unreachable(self) -> None:
        with self.assertRaises(ConfigurationError) as caught:
            CodexFallbackCoordinator.build(
                CodexHarnessAgentSettings(
                    name="a",
                    system_prompt="p",
                    codex=_codex_settings(),
                    fallback=AgentFallbackSettings(
                        models=[
                            FallbackModel(provider="anthropic", model="claude-opus-5")
                        ]
                    ),
                )
            )

        self.assertIn("anthropic", str(caught.exception))

    def test_accepts_an_entry_matching_a_custom_thread_model_provider(self) -> None:
        coordinator = CodexFallbackCoordinator.build(
            CodexHarnessAgentSettings(
                name="a",
                system_prompt="p",
                codex=_codex_settings(model_provider="my-gateway"),
                fallback=AgentFallbackSettings(
                    models=[FallbackModel(provider="my-gateway", model=BACKUP_MODEL)]
                ),
            )
        )

        self.assertTrue(coordinator.enabled)

    def test_primary_model_prefers_the_turn_model(self) -> None:
        primary = CodexFallbackCoordinator.primary_model(
            _codex_settings(turn_model="turn-model", thread_model="thread-model")
        )

        self.assertEqual(primary.model, "turn-model")
        self.assertEqual(primary.provider, CODEX_USAGE_PROVIDER)

    def test_primary_model_falls_back_to_the_thread_model(self) -> None:
        primary = CodexFallbackCoordinator.primary_model(
            _codex_settings(turn_model="", thread_model="thread-model")
        )

        self.assertEqual(primary.model, "thread-model")


class FallbackDecisionTests(unittest.TestCase):
    """Covers the two judgments that must agree before spending another turn."""

    def setUp(self) -> None:
        self.coordinator = CodexFallbackCoordinator.build(
            CodexHarnessAgentSettings(
                name="a",
                system_prompt="p",
                codex=_codex_settings(),
                fallback=AgentFallbackSettings(
                    models=[BACKUP_MODEL], fallback_on=(CodexAgentError,)
                ),
            )
        )

    def _decision(self, code: FailureCode, index: int = 0) -> CodexFallbackDecision:
        # Pairs one classified failure with the chain index it happened at.
        error = _error(code)
        record = CodexFailureTranslator.translate(
            CodexFailureTranslationRequest(error=error, chain_index=index)
        )
        return CodexFallbackDecision(record=record, error=error, index=index)

    def test_advances_for_a_model_retryable_failure(self) -> None:
        self.assertEqual(
            self.coordinator.next_index(
                self._decision(FailureCode.CODEX_TURN_FAILED)
            ),
            1,
        )

    def test_refuses_a_terminal_classification(self) -> None:
        self.assertIsNone(
            self.coordinator.next_index(
                self._decision(FailureCode.CODEX_SDK_UNAVAILABLE)
            )
        )

    def test_refuses_a_transient_classification(self) -> None:
        self.assertIsNone(
            self.coordinator.next_index(
                self._decision(FailureCode.CODEX_RESPONSE_INVALID)
            )
        )

    def test_refuses_when_the_caller_error_filter_rejects(self) -> None:
        coordinator = CodexFallbackCoordinator.build(
            CodexHarnessAgentSettings(
                name="a",
                system_prompt="p",
                codex=_codex_settings(),
                fallback=AgentFallbackSettings(
                    models=[BACKUP_MODEL], fallback_on=(TimeoutError,)
                ),
            )
        )

        self.assertIsNone(
            coordinator.next_index(self._decision(FailureCode.CODEX_TURN_FAILED))
        )

    def test_refuses_at_the_end_of_the_chain(self) -> None:
        self.assertIsNone(
            self.coordinator.next_index(
                self._decision(FailureCode.CODEX_TURN_FAILED, index=1)
            )
        )

    def test_settings_for_replaces_only_the_turn_model(self) -> None:
        codex = _codex_settings()

        overridden = self.coordinator.settings_for(codex, 1)

        self.assertEqual(overridden.turn.model, BACKUP_MODEL)
        self.assertEqual(overridden.turn.sandbox, codex.turn.sandbox)
        self.assertEqual(overridden.turn.approval_mode, codex.turn.approval_mode)
        self.assertEqual(overridden.thread, codex.thread)

    def test_settings_for_index_zero_returns_the_original(self) -> None:
        codex = _codex_settings()

        self.assertIs(self.coordinator.settings_for(codex, 0), codex)

    def test_attempt_records_no_credential(self) -> None:
        attempt = self.coordinator.attempt(1, "codex.turn_failed")

        self.assertEqual(
            set(CodexFallbackAttempt.__dataclass_fields__),
            {"index", "provider", "model", "failure_code"},
        )
        self.assertEqual(attempt.model, BACKUP_MODEL)


class AgentAttemptLoopTests(unittest.IsolatedAsyncioTestCase):
    """Covers the wired attempt loop through real turns."""

    async def test_a_recovered_turn_reports_the_answering_model(self) -> None:
        agent, transport = _build_agent(
            failures=[_error()],
            fallback=AgentFallbackSettings(
                models=[BACKUP_MODEL], fallback_on=(CodexAgentError,)
            ),
        )

        reply = await agent.arun(CodexRunInput.text("go"))

        self.assertEqual(reply.content, FINAL_RESPONSE)
        self.assertEqual(reply.metadata[CODEX_ANSWERING_MODEL_KEY], BACKUP_MODEL)
        self.assertEqual(len(transport.requests), 2)

    async def test_a_recovered_turn_records_both_attempts(self) -> None:
        agent, _ = _build_agent(
            failures=[_error()],
            fallback=AgentFallbackSettings(
                models=[BACKUP_MODEL], fallback_on=(CodexAgentError,)
            ),
        )

        reply = await agent.arun(CodexRunInput.text("go"))

        attempts = reply.metadata[CODEX_FALLBACK_ATTEMPTS_KEY]
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0].failure_code, FailureCode.CODEX_TURN_FAILED.value)
        self.assertEqual(attempts[1].model, BACKUP_MODEL)

    async def test_a_recovered_turn_still_records_the_failure(self) -> None:
        agent, _ = _build_agent(
            failures=[_error()],
            fallback=AgentFallbackSettings(
                models=[BACKUP_MODEL], fallback_on=(CodexAgentError,)
            ),
        )

        reply = await agent.arun(CodexRunInput.text("go"))

        self.assertEqual(len(agent.failures), 1)
        self.assertIs(agent.failures[0].phase, FailurePhase.MODEL)
        self.assertEqual(len(reply.metadata[CODEX_FAILURES_KEY]), 1)

    async def test_a_terminal_failure_spends_only_one_turn(self) -> None:
        agent, transport = _build_agent(
            failures=[_error(FailureCode.CODEX_SDK_UNAVAILABLE)],
            fallback=AgentFallbackSettings(
                models=[BACKUP_MODEL], fallback_on=(CodexAgentError,)
            ),
        )

        with self.assertRaises(CodexAgentError):
            await agent.arun(CodexRunInput.text("go"))

        self.assertEqual(len(transport.requests), 1)

    async def test_an_exhausted_chain_reraises_the_last_error(self) -> None:
        last = _error(FailureCode.CODEX_THREAD_START_FAILED)
        agent, transport = _build_agent(
            failures=[_error(), last],
            fallback=AgentFallbackSettings(
                models=[BACKUP_MODEL], fallback_on=(CodexAgentError,)
            ),
        )

        with self.assertRaises(CodexAgentError) as caught:
            await agent.arun(CodexRunInput.text("go"))

        self.assertIs(caught.exception, last)
        self.assertEqual(len(transport.requests), 2)

    async def test_each_attempt_carries_its_own_model_to_the_transport(self) -> None:
        agent, transport = _build_agent(
            failures=[_error()],
            fallback=AgentFallbackSettings(
                models=[BACKUP_MODEL], fallback_on=(CodexAgentError,)
            ),
        )

        await agent.arun(CodexRunInput.text("go"))

        self.assertEqual(transport.requests[0].settings.turn.model, PRIMARY_MODEL)
        self.assertEqual(transport.requests[1].settings.turn.model, BACKUP_MODEL)

    async def test_a_cancelled_turn_is_never_classified_or_retried(self) -> None:
        agent, transport = _build_agent(
            failures=[asyncio.CancelledError()],
            fallback=AgentFallbackSettings(
                models=[BACKUP_MODEL], fallback_on=(CodexAgentError,)
            ),
        )

        with self.assertRaises(asyncio.CancelledError):
            await agent.arun(CodexRunInput.text("go"))

        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(agent.failures, ())

    async def test_an_agent_without_a_chain_runs_one_turn_and_reports_nothing(
        self,
    ) -> None:
        agent, transport = _build_agent()

        reply = await agent.arun(CodexRunInput.text("go"))

        self.assertEqual(len(transport.requests), 1)
        self.assertNotIn(CODEX_ANSWERING_MODEL_KEY, reply.metadata)
        self.assertNotIn(CODEX_FALLBACK_ATTEMPTS_KEY, reply.metadata)
        self.assertNotIn(CODEX_FAILURES_KEY, reply.metadata)

    async def test_a_failure_without_a_chain_propagates_and_is_recorded(self) -> None:
        agent, _ = _build_agent(failures=[_error()])

        with self.assertRaises(CodexAgentError):
            await agent.arun(CodexRunInput.text("go"))

        self.assertEqual(len(agent.failures), 1)

    async def test_on_model_error_observes_each_failed_attempt_once(self) -> None:
        observer = _ErrorObserver()
        first = _error()
        agent, transport = _build_agent(
            failures=[first],
            fallback=AgentFallbackSettings(
                models=[BACKUP_MODEL], fallback_on=(CodexAgentError,)
            ),
            middleware=(observer,),
        )

        reply = await agent.arun(CodexRunInput.text("go"))

        self.assertEqual(reply.content, FINAL_RESPONSE)
        self.assertEqual(observer.errors, [first])
        self.assertEqual(len(transport.requests), 2)

    async def test_the_ledger_resets_between_turns(self) -> None:
        agent, _ = _build_agent(
            failures=[_error()],
            fallback=AgentFallbackSettings(
                models=[BACKUP_MODEL], fallback_on=(CodexAgentError,)
            ),
        )
        await agent.arun(CodexRunInput.text("one"))

        await agent.arun(CodexRunInput.text("two"))

        self.assertEqual(agent.failures, ())


if __name__ == "__main__":
    unittest.main()

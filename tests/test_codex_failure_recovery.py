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
    vidbyte/agents/codex/agent.py, the failed-turn error in
    vidbyte/agents/codex/transport.py, and the metadata keys in
    vidbyte/agents/codex/result.py, against the real
    vidbyte/agents/fallback.py and vidbyte/lib/dataclasses/failure.py.

ARCHITECTURE NOTE:
    Every test runs offline. Only CodexTransport is faked, or, for the
    same-thread tests, the optional openai_codex SDK beneath it; the real
    AgentFallbackSettings, AgentFallback, Failure, and FailureSafety all run,
    because the defect this guards against — the two judgments disagreeing,
    or a retry on a terminal code — only appears wired together.

FUNCTION INVENTORY:
    No production functions. _error() builds one classified adapter error,
    _codex_settings() builds provider settings naming a primary model,
    _build_agent() wires an agent to a scripted transport, and _fake_sdk()
    builds an SDK whose turns fail on one model.

COMMON MODIFICATION PATTERNS:
    Add a codex.* failure code, then add its row to the classification table;
    ClassificationCoverageTests fails until you do.

WHAT NOT TO DO IN THIS FILE:
    Do not assert that an unclassified code is retryable, and do not assert a
    specific provider key reaches any record — it must not. Fallback models
    take their keys from the agent's api_keys, not from a key of their own.

KNOWN EDGE CASES:
    A recovered turn still records its failed attempt; a cancelled turn is
    never classified and never triggers a fallback.

RELATED DOCS: docs/design/codex-failure-recovery.md
TESTS: python -m pytest tests/test_codex_failure_recovery.py
"""

from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest import mock

from vidbyte.agents.codex.agent import CodexHarnessAgent
from vidbyte.agents.codex.failures import CodexFailureLedger, CodexFailureTranslator
from vidbyte.agents.codex.fallback import CodexFallbackCoordinator
from vidbyte.agents.codex.transport import CodexTransport
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
    CodexPrompt,
    CodexRunInput,
    CodexRunResult,
    CodexSdkTypes,
    CodexTextInput,
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
PRICED_PRIMARY_MODEL = "gpt-5.6-sol"
PRICED_BACKUP_MODEL = "gpt-5.6-luna"


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
    code: FailureCode = FailureCode.CODEX_TURN_FAILED,
    cause: Exception | None = None,
    thread_id: str = "",
) -> CodexAgentError:
    # Builds one classified adapter error, optionally with a chained cause and
    # the native thread the failed operation ran on.
    error = CodexAgentError(
        "Codex failed the requested turn.",
        failure_code=code.value,
        operation="turn_run",
        thread_id=thread_id,
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
    ephemeral: bool = False,
) -> CodexAgentSettings:
    # Builds provider settings that may name a model at either lifecycle layer.
    return CodexAgentSettings(
        thread=CodexThreadSettings(
            model=thread_model, model_provider=model_provider, ephemeral=ephemeral
        ),
        turn=CodexTurnSettings(model=turn_model),
    )


class _ScriptedTransport:
    """Stands in for CodexTransport, raising a scripted sequence then succeeding."""

    def __init__(self, failures: list[BaseException] | None = None) -> None:
        self.failures = list(failures or [])
        self.requests: list[CodexTransportRunRequest] = []
        self.result = _run_result()

    async def run(self, request: CodexTransportRunRequest) -> CodexRunResult:
        # Records each attempt's request so the per-attempt model override is visible.
        self.requests.append(request)
        if self.failures:
            raise self.failures.pop(0)
        return self.result


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


class _FakeThread:
    """Native thread whose turns fail on _FakeAsyncCodex.failing_model."""

    def __init__(self, thread_id: str) -> None:
        self.id = thread_id

    async def run(self, input: object, **kwargs: object) -> object:
        # Logs which thread and model ran the turn, then fails on the scripted model.
        model = kwargs.get("model")
        _FakeAsyncCodex.events.append(("turn", self.id, model))
        if model == _FakeAsyncCodex.failing_model:
            raise RuntimeError("model overloaded")
        return object()


class _FakeAsyncCodex:
    """Stands in for openai_codex.AsyncCodex, numbering each new native thread."""

    events: list[tuple[str, ...]] = []
    started = 0
    failing_model = PRIMARY_MODEL

    def __init__(self, config: object = None) -> None:
        self._client = SimpleNamespace(_sync=None)

    async def __aenter__(self) -> _FakeAsyncCodex:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def thread_start(self, **kwargs: object) -> _FakeThread:
        # Opens a new thread under the next number, as the app-server does.
        _FakeAsyncCodex.started += 1
        thread_id = f"th_{_FakeAsyncCodex.started}"
        _FakeAsyncCodex.events.append(("start", thread_id))
        return _FakeThread(thread_id)

    async def thread_resume(self, thread_id: str, **kwargs: object) -> _FakeThread:
        # Reopens a saved thread by its id.
        _FakeAsyncCodex.events.append(("resume", thread_id))
        return _FakeThread(thread_id)


def _fake_sdk() -> CodexSdkTypes:
    # Builds SDK types whose constructors accept the adapter's default arguments.
    _FakeAsyncCodex.events = []
    _FakeAsyncCodex.started = 0
    passthrough = SimpleNamespace
    return CodexSdkTypes(
        async_codex=_FakeAsyncCodex,
        codex_config=passthrough,
        approval_mode=str,
        sandbox=str,
        personality=str,
        reasoning_effort=str,
        reasoning_summary=mock.Mock(),
        thread_source=str,
        thread_start_source=str,
        text_input=lambda text: text,
        image_input=lambda url: url,
        local_image_input=lambda path: path,
        skill_input=lambda name, path: name,
        mention_input=lambda name, path: name,
    )


def _serialize(thread_id: str, result: object) -> CodexRunResult:
    # Stands in for CodexResultSerializer.from_sdk, keeping the thread the turn ran on.
    return replace(_run_result(), thread_id=thread_id)


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
        polluted["openai_api_key"] = "sk-live"
        from vidbyte.lib.dataclasses.failure import FailureSafety

        self.assertNotIn("openai_api_key", FailureSafety.sanitize_mapping(polluted))

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

    async def test_a_recovered_turn_records_usage_under_the_answering_model(
        self,
    ) -> None:
        # The primary fails and the backup answers, so usage must be filed and
        # priced as the backup, matching the answering_model metadata.
        usage = CodexUsage(
            input_tokens=120,
            cached_input_tokens=20,
            output_tokens=30,
            reasoning_output_tokens=5,
            total_tokens=150,
        )
        reported = replace(
            _run_result(), usage=usage, last_usage=usage, usage_available=True
        )
        agent, transport = _build_agent(
            failures=[_error()],
            fallback=AgentFallbackSettings(
                models=[PRICED_BACKUP_MODEL], fallback_on=(CodexAgentError,)
            ),
            codex=_codex_settings(turn_model="", thread_model=PRICED_PRIMARY_MODEL),
        )
        transport.result = reported
        direct, direct_transport = _build_agent(
            codex=_codex_settings(turn_model="", thread_model=PRICED_BACKUP_MODEL)
        )
        direct_transport.result = reported

        reply = await agent.arun(CodexRunInput.text("go"))
        await direct.arun(CodexRunInput.text("go"))

        self.assertEqual(reply.metadata[CODEX_ANSWERING_MODEL_KEY], PRICED_BACKUP_MODEL)
        self.assertEqual(agent.get_usage().calls[0].model, PRICED_BACKUP_MODEL)
        self.assertIsNotNone(direct.get_cost_usd())
        self.assertEqual(agent.get_cost_usd(), direct.get_cost_usd())


class AgentFallbackThreadTests(unittest.IsolatedAsyncioTestCase):
    """Covers which native thread each fallback attempt is sent to."""

    async def test_a_fallback_after_a_failed_first_turn_continues_on_its_thread(
        self,
    ) -> None:
        agent, transport = _build_agent(
            failures=[_error(thread_id="th_open")],
            fallback=AgentFallbackSettings(
                models=[BACKUP_MODEL], fallback_on=(CodexAgentError,)
            ),
        )

        await agent.arun(CodexRunInput.text("go"))

        self.assertEqual(transport.requests[0].thread_id, "")
        self.assertEqual(transport.requests[1].thread_id, "th_open")

    async def test_a_failed_thread_start_lets_the_next_attempt_start_one(
        self,
    ) -> None:
        agent, transport = _build_agent(
            failures=[_error(FailureCode.CODEX_THREAD_START_FAILED)],
            fallback=AgentFallbackSettings(
                models=[BACKUP_MODEL], fallback_on=(CodexAgentError,)
            ),
        )

        await agent.arun(CodexRunInput.text("go"))

        self.assertEqual(transport.requests[1].thread_id, "")

    async def test_a_held_thread_is_sent_on_every_attempt(self) -> None:
        agent, transport = _build_agent(
            failures=[_error(thread_id="th_held")],
            fallback=AgentFallbackSettings(
                models=[BACKUP_MODEL], fallback_on=(CodexAgentError,)
            ),
        )
        agent.thread_id = "th_held"

        await agent.arun(CodexRunInput.text("go"))

        self.assertEqual(
            [request.thread_id for request in transport.requests],
            ["th_held", "th_held"],
        )

    async def test_an_ephemeral_thread_is_not_reopened_by_the_next_attempt(
        self,
    ) -> None:
        # An ephemeral thread is not saved, so a new app-server cannot resume it.
        agent, transport = _build_agent(
            failures=[_error(thread_id="th_open")],
            fallback=AgentFallbackSettings(
                models=[BACKUP_MODEL], fallback_on=(CodexAgentError,)
            ),
            codex=_codex_settings(ephemeral=True),
        )

        await agent.arun(CodexRunInput.text("go"))

        self.assertEqual(transport.requests[1].thread_id, "")


class TransportFailedTurnThreadTests(unittest.IsolatedAsyncioTestCase):
    """Covers that a failed turn names its thread, through the real transport."""

    async def asyncSetUp(self) -> None:
        patches = (
            mock.patch.object(CodexTransport, "_load_sdk", return_value=_fake_sdk()),
            mock.patch(
                "vidbyte.agents.codex.transport.CodexResultSerializer.from_sdk",
                side_effect=_serialize,
            ),
        )
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    async def test_a_turn_failing_after_thread_start_names_the_started_thread(
        self,
    ) -> None:
        request = CodexTransportRunRequest(
            thread_id="",
            system_prompt="You are a Codex harness agent.",
            prompt=CodexPrompt(
                items=(CodexTextInput("go"),),
                user_prompt="go",
                recipient="codex-agent",
                metadata={},
            ),
            settings=_codex_settings(),
            output_schema={},
        )

        with self.assertRaises(CodexAgentError) as caught:
            await CodexTransport().run(request)

        self.assertEqual(
            caught.exception.failure_code, FailureCode.CODEX_TURN_FAILED.value
        )
        self.assertEqual(caught.exception.thread_id, "th_1")

    async def test_a_fresh_agent_runs_every_attempt_on_one_started_thread(
        self,
    ) -> None:
        agent = CodexHarnessAgent(
            CodexHarnessAgentSettings(
                name="codex-agent",
                system_prompt="You are a Codex harness agent.",
                codex=_codex_settings(),
                fallback=AgentFallbackSettings(
                    models=[BACKUP_MODEL], fallback_on=(CodexAgentError,)
                ),
            )
        )

        reply = await agent.arun(CodexRunInput.text("go"))

        self.assertEqual(reply.metadata[CODEX_ANSWERING_MODEL_KEY], BACKUP_MODEL)
        self.assertEqual(
            _FakeAsyncCodex.events,
            [
                ("start", "th_1"),
                ("turn", "th_1", PRIMARY_MODEL),
                ("resume", "th_1"),
                ("turn", "th_1", BACKUP_MODEL),
            ],
        )
        self.assertEqual(agent.thread_id, "th_1")


if __name__ == "__main__":
    unittest.main()

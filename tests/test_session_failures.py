"""FILE: tests/test_session_failures.py

PURPOSE: Verifies the fixed failure vocabulary, rule router, and Session recovery integration.
ROLE IN CODEBASE: Exercises the public Session failure API without provider or network dependencies.
ARCHITECTURE NOTE: Uses fake agents and stores to isolate local handling from Session escalation.
COMMON MODIFICATION PATTERNS: Add one focused test when a code, disposition, or recovery contract changes.
KNOWN EDGE CASES: Covers fail-open/closed rules, bounded history, exception chaining, and async callbacks.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from tests.agent_test_support import build_test_agent
from vidbyte import (
    AgentMessage,
    AgentMiddleware,
    Failure,
    FailureCode,
    FailureDisposition,
    FailureMetadataNormalizer,
    FailureMiddleware,
    FailurePhase,
    FailureRaisedError,
    FailureRouter,
    FailureStatus,
    ForkRecovery,
    MiddlewareDecision,
    RuleErrorMode,
    Session,
    StopRecovery,
    rule,
    tool,
)
from vidbyte.agents import AgentLoopSettings, ToolSettings
from vidbyte.lib.dataclasses.middleware import (
    MiddlewareAction,
    MiddlewareContext,
    MiddlewareHook,
)
from vidbyte.lib.dataclasses.sessions import SESSION_SCHEMA_VERSION, RunState
from vidbyte.lib.errors import AgentExecutionError
from vidbyte.sessions.failure.recovery import (
    CompactRecovery,
    RaiseRecovery,
    RecoveryResult,
)
from vidbyte.sessions.stores.memory import InMemorySessionStore


class _FakeAgent:
    """Small Session-compatible agent used to exercise routing without a provider."""

    session_persistence_supported = True

    def __init__(self, metadata: dict | None = None, *, fail: BaseException | None = None) -> None:
        self.name = "fake"
        self.history: list[AgentMessage] = []
        self.last_reply: AgentMessage | None = None
        self.session = None
        self.metadata = metadata or {}
        self.fail = fail

    def bind_session(self, session: Session) -> None:
        # Capture the Session so fake runs follow the BaseAgent notification seam.
        self.session = session

    async def arun(self, message: str, **_options: object) -> AgentMessage:
        # Return scripted metadata or raise the configured exception.
        if self.fail is not None:
            raise self.fail
        reply = AgentMessage(sender=self.name, recipient="orchestrator", content=message, metadata=dict(self.metadata))
        self.history.append(reply)
        self.last_reply = reply
        if self.session is not None:
            self.session.record_turn(reply)
        return reply

    def export_state(self) -> RunState:
        # Build the minimum serializable state required by Session checkpoints.
        return RunState(schema_version=SESSION_SCHEMA_VERSION, agent_name=self.name, system_prompt="system", description="", capabilities=(), provider="openai", model_name="test", temperature=None, runtime_type="linear", runtime_config={}, algorithm="default", metadata={}, agent_metadata={}, tool_names=(), history=tuple({"sender": item.sender, "recipient": item.recipient, "content": item.content, "message_type": item.message_type, "metadata": dict(item.metadata)} for item in self.history))


class _FailingStore(InMemorySessionStore):
    """Store that keeps Session metadata but rejects checkpoint writes."""

    def put(self, checkpoint):
        # Simulate a fail-open persistence boundary.
        raise RuntimeError("disk full")


class _FailingRunner:
    """Offline runner that raises so direct BaseAgent exception capture can be tested."""

    def run(self, _prompt: str, **_options: object):
        # Raise an ordinary provider-boundary exception without network access.
        raise RuntimeError("runner failed")


class _RefundCallRunner:
    """Offline runner that asks for one refund tool call, then finishes."""

    def __init__(self) -> None:
        self.responses = [("refund", '{"amount": 900}'), ("isDone", '{"final_answer": "done"}')]

    def run(self, _prompt: str, **_options: object) -> SimpleNamespace:
        # Script one OpenAI-style tool call per model request without network access.
        name, arguments = self.responses.pop(0)
        call = {"id": f"call_{name}", "type": "function", "function": {"name": name, "arguments": arguments}}
        return SimpleNamespace(text="", raw={"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [call]}}]})


class _DenyRefundMiddleware(AgentMiddleware):
    """Middleware that refuses every refund call, the reference refusal for ledger comparisons."""

    async def before_tool_call(self, context: MiddlewareContext) -> MiddlewareDecision:
        # Refuse the refund tool and let every other call through.
        if context.tool_call is not None and context.tool_call.tool_name == "refund":
            return MiddlewareDecision.deny_tool("refunds are blocked")
        return MiddlewareDecision.continue_()


class FailureContractsTests(unittest.TestCase):
    def test_every_code_has_category_prefix(self) -> None:  # [Edge Case]
        # Verify every public code is groupable by its first dotted component.
        self.assertTrue(all("." in code.value for code in FailureCode))

    def test_failure_sanitizes_secrets_and_serializes_enums(self) -> None:  # [Silent Failure]
        # Verify details stay safe and as_dict exposes stable strings.
        failure = Failure(code=FailureCode.ACTION_UNSAFE, source="test", phase=FailurePhase.ACTION, details={"api_key": "secret", "ok": 1})
        self.assertNotIn("api_key", failure.details)
        self.assertEqual(failure.as_dict()["code"], "action.unsafe")
        self.assertEqual(failure.as_dict()["category"], "action")

    def test_failure_details_keep_non_credential_keys(self) -> None:  # [Silent Failure]
        # @intent failure-details-use-precise-credential-keys
        # Verify diagnostics that merely contain TOKEN or AUTH survive while real credentials are dropped.
        details = {"tokens_used": 5, "max_tokens": 9, "author": "ana", "api_key": "sk-1", "authorization": "Bearer x", "accessToken": "t", "client_secret": "s"}
        failure = Failure(code=FailureCode.RUNTIME_ERROR, source="probe", details=details)
        self.assertEqual(dict(failure.details), {"tokens_used": 5, "max_tokens": 9, "author": "ana"})

    def test_unknown_exception_maps_to_runtime_error(self) -> None:  # [Hidden Assumption]
        # Verify arbitrary exceptions do not create dynamic vocabulary entries.
        failure = Failure.from_exception(RuntimeError("boom"))
        self.assertIs(failure.code, FailureCode.RUNTIME_ERROR)

    def test_router_history_is_bounded_and_filterable(self) -> None:  # [Edge Case]
        # Verify the oldest record is evicted and filters preserve insertion order.
        router = FailureRouter(object(), max_history=2)
        router.emit(FailureCode.ACTION_UNSAFE, phase=FailurePhase.ACTION, source="one")
        router.emit(FailureCode.TOOL_TIMEOUT, phase=FailurePhase.TOOL, source="two")
        router.emit(FailureCode.ACTION_UNSAFE, phase=FailurePhase.ACTION, source="three")
        self.assertEqual([item.source for item in router.history()], ["two", "three"])
        self.assertEqual(len(router.history(code=FailureCode.ACTION_UNSAFE)), 1)

    def test_disabled_router_does_not_record(self) -> None:  # [Hidden Assumption]
        # Verify disabled instrumentation has no policy side effects.
        router = FailureRouter(object(), enabled=False)
        failure = router.emit(FailureCode.ACTION_UNSAFE, phase=FailurePhase.ACTION, source="test")
        self.assertEqual(router.history(), ())
        self.assertEqual(failure.code, FailureCode.ACTION_UNSAFE)


class FailureRuleTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_and_async_rules_run_in_priority_order(self) -> None:  # [Silent Failure]
        # Verify high-priority rules run first and async callbacks are awaited.
        router = FailureRouter(object())
        seen: list[str] = []

        @rule(code=FailureCode.ACTION_WRONG_TARGET, on=MiddlewareHook.AFTER_TOOL_CALL, on_match=FailureDisposition.RECORD, priority=10)
        def high(_context):
            seen.append("high")
            return Failure(code=FailureCode.ACTION_WRONG_TARGET, source="high", phase="action")

        @rule(code=FailureCode.ACTION_UNSAFE, on=MiddlewareHook.AFTER_TOOL_CALL, on_match=FailureDisposition.RECORD, priority=1)
        async def low(_context):
            await asyncio.sleep(0)
            seen.append("low")
            return Failure(code=FailureCode.ACTION_UNSAFE, source="low", phase="action")

        router.add_rule(low)
        router.add_rule(high)
        found = await router.evaluate("after_tool_call", object())
        self.assertEqual(seen, ["high", "low"])
        self.assertEqual([failure.code for failure in found], [FailureCode.ACTION_WRONG_TARGET, FailureCode.ACTION_UNSAFE])

    async def test_decorated_rules_keep_function_names_and_identity(self) -> None:  # [Silent Failure]
        # Verify decorated rules report their own names and async rules can be deduplicated, run, and removed.
        router = FailureRouter(object())
        seen: list[str] = []

        @rule(code=FailureCode.OUTPUT_INVALID, on=MiddlewareHook.AFTER_TOOL_CALL, on_match=FailureDisposition.RECORD)
        def no_leaks(_context):
            return None

        @rule(code=FailureCode.ACTION_UNSAFE, on=MiddlewareHook.AFTER_TOOL_CALL, on_match=FailureDisposition.RECORD)
        async def audit_async(_context):
            await asyncio.sleep(0)
            seen.append("audit_async")
            return Failure(code=FailureCode.ACTION_UNSAFE, source="audit", phase="action")

        @rule(code=FailureCode.ACTION_UNSAFE, on=MiddlewareHook.AFTER_TOOL_CALL, name="explicit-name")
        async def renamed(_context):
            return None

        router.add_rule(no_leaks)
        router.add_rule(audit_async)
        router.add_rule(audit_async)
        router.add_rule(renamed)
        self.assertEqual([item.name for item in router._rules], ["no_leaks", "audit_async", "explicit-name"])
        found = await router.evaluate("after_tool_call", object())
        self.assertEqual(seen, ["audit_async"])
        self.assertEqual([failure.code for failure in found], [FailureCode.ACTION_UNSAFE])
        router.remove_rule(audit_async)
        router.remove_rule(no_leaks)
        router.remove_rule(renamed)
        self.assertEqual(router._rules, [])

    async def test_fail_open_rule_error_records_and_continues(self) -> None:  # [Hidden Failure]
        # Verify an optional detector cannot stop the run when it crashes.
        router = FailureRouter(object())

        @rule(code=FailureCode.ACTION_POLICY_VIOLATION, on=MiddlewareHook.BEFORE_TOOL_CALL, on_error=RuleErrorMode.OPEN)
        def broken(_context):
            raise RuntimeError("detector broke")

        router.add_rule(broken)
        await router.evaluate("before_tool_call", object())
        self.assertEqual(router.history()[0].code, FailureCode.RULE_EVALUATION_FAILED)
        self.assertEqual(router.history()[0].status, FailureStatus.OBSERVED)

    async def test_fail_closed_rule_error_is_terminal(self) -> None:  # [Hidden Failure]
        # Verify a safety detector error is visible as a terminal failure.
        router = FailureRouter(object())

        @rule(code=FailureCode.ACTION_UNSAFE, on=MiddlewareHook.BEFORE_TOOL_CALL, on_match=FailureDisposition.STOP, on_error=RuleErrorMode.CLOSED)
        def broken(_context):
            raise RuntimeError("detector broke")

        router.add_rule(broken)
        await router.evaluate("before_tool_call", object())
        self.assertEqual(router.history()[0].code, FailureCode.RULE_EVALUATION_FAILED)
        self.assertEqual(router.history()[0].status, FailureStatus.TERMINAL)
        self.assertEqual(len(router.history()), 1)

    async def test_fail_closed_rule_error_aborts_middleware(self) -> None:  # [Hidden Failure]
        # Verify a detector crash cannot accidentally allow the protected hook.
        router = FailureRouter(object())

        @rule(code=FailureCode.ACTION_UNSAFE, on=MiddlewareHook.BEFORE_TOOL_CALL, on_match=FailureDisposition.STOP, on_error=RuleErrorMode.CLOSED)
        def broken(_context):
            raise RuntimeError("detector broke")

        router.add_rule(broken)
        decision = await FailureMiddleware(router).before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="agent"))
        self.assertEqual(decision.action, MiddlewareAction.ABORT_RUN)

    async def test_rule_route_runs_recovery_once(self) -> None:  # [Hidden Failure]
        # Verify explicit routing invokes the registered handler exactly once.
        router = FailureRouter(object())
        calls = 0

        class Handler:
            name = "counter"
            on_error = "closed"

            def recover(self, failure, *, session):
                nonlocal calls
                calls += 1
                return RecoveryResult(True, details={"code": failure.code.value})

        router.on(FailureCode.ACTION_WRONG_TARGET, Handler())

        @rule(code=FailureCode.ACTION_WRONG_TARGET, on=MiddlewareHook.AFTER_TOOL_CALL, on_match=FailureDisposition.ROUTE)
        def detected(_context):
            return Failure(code=FailureCode.ACTION_WRONG_TARGET, source="rule", phase="action")

        router.add_rule(detected)
        await router.evaluate("after_tool_call", object())
        self.assertEqual(calls, 1)
        self.assertEqual(router.history()[0].status, FailureStatus.RECOVERED)

    async def test_rule_middleware_blocks_before_tool_execution(self) -> None:  # [Hidden Failure]
        # Verify a fail-closed before-tool rule uses the existing middleware decision contract.
        router = FailureRouter(object())

        @rule(code=FailureCode.ACTION_UNSAFE, on=MiddlewareHook.BEFORE_TOOL_CALL, on_match=FailureDisposition.STOP, on_error=RuleErrorMode.CLOSED)
        def safety(_context):
            return Failure(code=FailureCode.ACTION_UNSAFE, source="safety", phase="action")

        router.add_rule(safety)
        decision = await FailureMiddleware(router).before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="agent"))
        self.assertEqual(decision.action, MiddlewareAction.ABORT_RUN)


class FailureNormalizationTests(unittest.TestCase):
    def test_normal_reply_has_no_false_failure(self) -> None:  # [Silent Failure]
        # Verify normal final responses do not pollute failure history.
        router = FailureRouter(object())
        reply = AgentMessage(sender="a", recipient="o", content="done", metadata={"stop_reason": "final_response"})
        self.assertEqual(router.capture_reply(reply), ())

    def test_stop_reasons_map_to_specific_codes(self) -> None:  # [Silent Failure]
        # Verify runtime and tool limits remain distinguishable.
        router = FailureRouter(object())
        reply = AgentMessage(sender="a", recipient="o", content="stopped", metadata={"stop_reason": "max_tokens"})
        self.assertEqual(router.capture_reply(reply)[0].code, FailureCode.RUNTIME_MAX_TOKENS)
        reply2 = AgentMessage(sender="a", recipient="o", content="stopped", metadata={"stop_reason": "max_identical_calls"})
        self.assertEqual(router.capture_reply(reply2)[0].code, FailureCode.TOOL_IDENTICAL_CALL_LIMIT)

    def test_loop_stop_failure_keeps_tokens_used(self) -> None:  # [Silent Failure]
        # Verify the runtime's own loop-stop record keeps its token count in details.
        reply = AgentMessage(sender="a", recipient="o", content="stopped", metadata={"stop_reason": "max_iterations", "iteration_count": 2, "tokens_used": 300})
        failure = FailureMetadataNormalizer.from_reply(reply)[0]
        self.assertEqual(failure.code, FailureCode.RUNTIME_MAX_ITERATIONS)
        self.assertEqual(dict(failure.details), {"stop_reason": "max_iterations", "iteration_count": 2, "tokens_used": 300})

    def test_fallback_success_is_recorded_as_recovered(self) -> None:  # [Hidden Failure]
        # Verify local fallback remains the handler and Session does not route it again.
        router = FailureRouter(object())
        reply = AgentMessage(sender="a", recipient="o", content="done", metadata={"fallback": {"used": True, "attempts": [{"from": "a", "to": "b"}], "final_model": "b"}})
        failure = router.capture_reply(reply)[0]
        self.assertEqual(failure.status, FailureStatus.RECOVERED)
        self.assertEqual(failure.handled_by, "agent_fallback")

    def test_middleware_abort_and_session_persistence_are_distinct(self) -> None:  # [Silent Failure]
        # Verify independent boundaries retain independent remediation codes.
        router = FailureRouter(object())
        reply = AgentMessage(sender="a", recipient="o", content="stopped", metadata={"middleware": {"events": [{"action": "abort_run", "reason": "policy", "middleware_name": "guard", "hook": "before_tool_call"}]}, "__session_error__": "RuntimeError: disk full"})
        codes = {failure.code for failure in router.capture_reply(reply)}
        self.assertIn(FailureCode.RUNTIME_MIDDLEWARE_ABORT, codes)
        self.assertIn(FailureCode.SESSION_PERSISTENCE_FAILED, codes)

    def test_tool_result_metadata_keeps_specific_code(self) -> None:  # [Silent Failure]
        # Verify result metadata is more specific than the generic failed-call state.
        router = FailureRouter(object())
        reply = AgentMessage(
            sender="a",
            recipient="o",
            content="stopped",
            metadata={
                "tool_call_states": ("failed",),
                "tool_calls": (SimpleNamespace(result=SimpleNamespace(metadata={"error": "timeout"})),),
            },
        )
        codes = {failure.code for failure in router.capture_reply(reply)}
        self.assertIn(FailureCode.TOOL_TIMEOUT, codes)

    def test_legacy_argument_error_kinds_record_arguments_invalid(self) -> None:  # [Silent Failure]
        # @intent ledger-tool-error-kinds-match-the-model-visible-kind
        # Verify every form the model is shown as invalid_arguments reaches the ledger as that code.
        forms = ({"error": "validation"}, {"error": "argument_error"}, {"error": "arguments_error"}, {"error": "Validation_Error"}, {"error_type": "validation"})
        for form in forms:
            with self.subTest(form=form):
                reply = AgentMessage(sender="a", recipient="o", content="done", metadata={"tool_calls": (SimpleNamespace(result=SimpleNamespace(metadata=form)),)})
                failures = FailureMetadataNormalizer.from_reply(reply)
                self.assertEqual([(item.code, item.source) for item in failures], [(FailureCode.TOOL_ARGUMENTS_INVALID, "tool_runtime")])
        success = AgentMessage(sender="a", recipient="o", content="done", metadata={"tool_calls": (SimpleNamespace(result=SimpleNamespace(metadata={"source": "cache"})),)})
        self.assertEqual(FailureMetadataNormalizer.from_reply(success), ())

    def test_contract_stop_yields_one_routable_failure(self) -> None:  # [Hidden Failure]
        # @intent one-stop-one-routable-failure
        # Verify a contract stop keeps only the specific output_contract record, not a runtime twin.
        reply = AgentMessage(sender="a", recipient="o", content="stopped", metadata={"stop_reason": "contract_unsatisfied", "contract_evaluations": ({"name": "MinToolCalls", "satisfied": False},)})
        failures = FailureMetadataNormalizer.from_reply(reply)
        self.assertEqual([(item.code, item.source, item.status) for item in failures], [(FailureCode.CONTRACT_UNSATISFIED, "output_contract", FailureStatus.EXHAUSTED)])

    def test_tool_budget_stop_yields_one_routable_failure(self) -> None:  # [Hidden Failure]
        # Verify a tool-settings budget stop keeps only the tool_settings record.
        reply = AgentMessage(sender="a", recipient="o", content="stopped", metadata={"stop_reason": "max_identical_calls", "tool_settings_budget": "max_identical_calls"})
        failures = FailureMetadataNormalizer.from_reply(reply)
        self.assertEqual([(item.code, item.source) for item in failures], [(FailureCode.TOOL_IDENTICAL_CALL_LIMIT, "tool_settings")])

    def test_middleware_abort_stop_yields_one_record(self) -> None:  # [Hidden Failure]
        # @intent one-middleware-abort-one-record
        # Verify one middleware abort keeps only the richer middleware record, not a runtime twin.
        for reason, code in (("policy", FailureCode.RUNTIME_MIDDLEWARE_ABORT), ("middleware_error", FailureCode.RUNTIME_MIDDLEWARE_ERROR)):
            event = {"action": "abort_run", "reason": reason, "middleware_name": "guard", "hook": "before_tool_call"}
            reply = AgentMessage(sender="a", recipient="o", content="stopped", metadata={"stop_reason": "middleware_abort", "middleware": {"events": [event]}})
            failures = FailureRouter(object()).capture_reply(reply)
            self.assertEqual([(item.code, item.source, item.status) for item in failures], [(code, "guard", FailureStatus.TERMINAL)])
        bare = AgentMessage(sender="a", recipient="o", content="stopped", metadata={"stop_reason": "middleware_abort"})
        failures = FailureRouter(object()).capture_reply(bare)
        self.assertEqual([(item.code, item.source) for item in failures], [(FailureCode.RUNTIME_MIDDLEWARE_ABORT, "agent_runtime")])


class SessionFailureIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_contract_stop_runs_bound_handler_once(self) -> None:  # [Hidden Failure]
        # Verify one contract stop routes to its bound recovery handler exactly once.
        session = Session(_FakeAgent(metadata={"stop_reason": "contract_unsatisfied", "contract_evaluations": ({"name": "MinToolCalls", "satisfied": False},)}))
        session.failures.on(FailureCode.CONTRACT_UNSATISFIED, StopRecovery(reason="contract exhausted"))
        await session.arun("work")
        self.assertEqual(len(session.failures.recovery_attempts), 1)

    async def test_session_exposes_stable_router_and_records_stop_reason(self) -> None:  # [Hidden Assumption]
        # Verify Session owns one router and captures completed reply metadata.
        agent = _FakeAgent(metadata={"stop_reason": "max_iterations"})
        session = Session(agent)
        self.assertIs(session.failures, session.failures)
        await session.arun("work")
        self.assertEqual(session.failures.history()[0].code, FailureCode.RUNTIME_MAX_ITERATIONS)

    async def test_session_routes_exhausted_failure_after_local_handling(self) -> None:  # [Hidden Failure]
        # Verify Session recovery runs after the runtime reports an exhausted local budget.
        session = Session(_FakeAgent(metadata={"stop_reason": "max_tokens"}))
        session.failures.on(FailureCode.RUNTIME_MAX_TOKENS, StopRecovery(reason="budget exhausted"))
        await session.arun("work")
        self.assertEqual(session.failures.history()[0].status, FailureStatus.RECOVERED)
        self.assertEqual(session.failures.recovery_attempts[0].handler, "stop")

    async def test_direct_bound_agent_exception_reaches_session_router(self) -> None:  # [Hidden Failure]
        # Verify BaseAgent direct execution reports failures even without Session.arun().
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=_FailingRunner())
        session = Session(agent)
        with self.assertRaises(AgentExecutionError):
            await agent.arun("work")
        self.assertEqual(session.failures.history()[0].code, FailureCode.RUNTIME_ERROR)

    async def test_in_loop_raise_rule_surfaces_typed_error(self) -> None:  # [Hidden Failure]
        # @intent raise-disposition-reaches-the-caller
        # Verify a matched, fail-closed crashing, or RaiseRecovery-routed rule raises FailureRaisedError, blocks the tool, and leaves one ledger record.
        def over_limit(context):
            return Failure(code=FailureCode.ACTION_POLICY_VIOLATION, source="refund_limit", phase=FailurePhase.ACTION)

        def crashing(_context):
            raise RuntimeError("limits service down")

        raise_ = FailureDisposition.RAISE
        cases = ((over_limit, raise_, RuleErrorMode.OPEN, FailureCode.ACTION_POLICY_VIOLATION), (crashing, raise_, RuleErrorMode.CLOSED, FailureCode.RULE_EVALUATION_FAILED), (over_limit, FailureDisposition.ROUTE, RuleErrorMode.OPEN, FailureCode.ACTION_POLICY_VIOLATION))
        for detector, on_match, on_error, code in cases:
            with self.subTest(detector=detector.__name__, on_match=on_match.value):
                refunded: list[int] = []

                @tool
                def refund(amount: int) -> str:
                    """Refund an order."""
                    refunded.append(amount)
                    return "refunded"

                session = Session(build_test_agent(name="payments", system_prompt="Pay.", runner=_RefundCallRunner(), tools=[refund]))
                session.failures.add_rule(rule(code=FailureCode.ACTION_POLICY_VIOLATION, on=MiddlewareHook.BEFORE_TOOL_CALL, on_match=on_match, on_error=on_error)(detector))
                session.failures.on(FailureCode.ACTION_POLICY_VIOLATION, RaiseRecovery())
                with self.assertRaises(FailureRaisedError) as raised:
                    await session.arun("refund order o1")
                self.assertEqual(refunded, [])
                self.assertEqual([(item.code, item.status, item.disposition) for item in session.failures.history()], [(code, FailureStatus.TERMINAL, FailureDisposition.RAISE)])
                self.assertEqual(raised.exception.failure.id, session.failures.history()[0].id)

    async def test_settings_refusals_record_tool_runtime_cause_like_middleware(self) -> None:  # [Silent Failure]
        # @intent ledger-records-every-refusal-kind
        # Verify a ToolSettings or allowed_tools refusal leaves the same tool_runtime permission record as a middleware refusal.
        guards = {
            "middleware": {"middleware": [_DenyRefundMiddleware()]},
            "tool_settings": {"agent_loop_settings": AgentLoopSettings(tool_settings=ToolSettings(denied_tools=["refund"]))},
            "allowed_tools": {"agent_loop_settings": AgentLoopSettings(allowed_tools=("lookup",))},
        }
        ledgers: dict[str, set[tuple[str, FailureCode]]] = {}
        for name, options in guards.items():
            with self.subTest(guard=name):
                refunded: list[int] = []

                @tool
                def refund(amount: int) -> str:
                    """Refund an order."""
                    refunded.append(amount)
                    return "refunded"

                @tool
                def lookup(order_id: str) -> str:
                    """Look up an order."""
                    return "found"

                session = Session(build_test_agent(name="payments", system_prompt="Pay.", runner=_RefundCallRunner(), tools=[refund, lookup], **options))
                await session.arun("refund order o1")
                self.assertEqual(refunded, [])
                ledgers[name] = {(item.source, item.code) for item in session.failures.history()}
                self.assertIn(("tool_runtime", FailureCode.TOOL_PERMISSION_DENIED), ledgers[name])
        self.assertEqual(ledgers["tool_settings"], ledgers["middleware"])
        self.assertEqual(ledgers["allowed_tools"], ledgers["middleware"])

    async def test_session_routes_exception_after_local_handling(self) -> None:  # [Hidden Failure]
        # Verify exception-time escalation runs once after the local agent boundary records it.
        session = Session(_FakeAgent(fail=RuntimeError("runner failed")))
        session.failures.on(FailureCode.RUNTIME_ERROR, StopRecovery(reason="runtime exhausted"))
        with self.assertRaises(RuntimeError):
            await session.arun("work")
        self.assertEqual(session.failures.history()[0].status, FailureStatus.RECOVERED)
        self.assertEqual(session.failures.recovery_attempts[0].handler, "stop")

    async def test_fail_open_persistence_is_recorded_without_stopping(self) -> None:  # [Hidden Failure]
        # Verify checkpoint failure preserves the reply and emits a Session failure.
        session = Session(_FakeAgent(), store=_FailingStore())
        reply = await session.arun("work")
        self.assertEqual(reply.content, "work")
        self.assertEqual(session.failures.history()[0].code, FailureCode.SESSION_PERSISTENCE_FAILED)

    async def test_fork_recovery_returns_child_session(self) -> None:  # [Edge Case]
        # Verify the built-in fork handler delegates to the existing Session fork seam.
        session = Session(_FakeAgent())
        await session.arun("checkpoint")
        failure = session.failures.emit(FailureCode.ACTION_WRONG_TARGET, phase=FailurePhase.ACTION, source="test", status=FailureStatus.EXHAUSTED, disposition=FailureDisposition.ROUTE)
        session.failures.on(FailureCode.ACTION_WRONG_TARGET, ForkRecovery(at=session.head))
        result = await session.failures.route(failure)
        self.assertIsNotNone(result)
        self.assertTrue(result.succeeded)

    async def test_fork_recovery_accepts_session_overrides(self) -> None:  # [Edge Case]
        # Verify explicit branch policy, trace, and tags are forwarded through fork_from().
        session = Session(_FakeAgent())
        await session.arun("checkpoint")
        failure = session.failures.emit(FailureCode.ACTION_WRONG_TARGET, phase=FailurePhase.ACTION, source="test", status=FailureStatus.EXHAUSTED, disposition=FailureDisposition.ROUTE)
        session.failures.on(FailureCode.ACTION_WRONG_TARGET, ForkRecovery(at=session.head, policy=Session.MANUAL_POLICY, trace=Session.OFF_TRACE, tags=("repair",)))
        result = await session.failures.route(failure)
        self.assertTrue(result.succeeded)
        self.assertEqual(result.value._policy.value, Session.MANUAL_POLICY)
        self.assertEqual(result.value._tags, ("repair",))

    def test_fork_recovery_refuses_bare_string_tags(self) -> None:  # [Hidden Assumption]
        # Verify tags="incident" is refused instead of tagging the branch with its characters.
        with self.assertRaisesRegex(ValueError, "ForkRecovery.tags must be a list of tag names"):
            ForkRecovery(tags="incident")
        self.assertEqual(ForkRecovery(tags=["incident"])._fork_settings.tags, ("incident",))

    async def test_raise_recovery_uses_typed_error(self) -> None:  # [Hidden Assumption]
        # Verify terminal recovery never falls back to an untyped raw exception.
        router = FailureRouter(object())
        failure = router.emit(FailureCode.ACTION_UNSAFE, phase=FailurePhase.ACTION, source="test")
        router.on(FailureCode.ACTION_UNSAFE, RaiseRecovery())
        with self.assertRaises(FailureRaisedError):
            await router.route(failure)
        self.assertEqual(router.history()[0].status, FailureStatus.TERMINAL)

    async def test_async_callback_recovery_preserves_value(self) -> None:  # [Hidden Failure]
        # Verify asynchronous compaction callbacks are awaited and their result retained.
        async def compact(_failure, _session):
            return {"compacted": True}

        router = FailureRouter(object())
        failure = router.emit(FailureCode.RUNTIME_COMPACTION_FAILED, phase=FailurePhase.RUNTIME, source="test")
        router.on(FailureCode.RUNTIME_COMPACTION_FAILED, CompactRecovery(compact))
        result = await router.route(failure)
        self.assertEqual(result.value, {"compacted": True})


if __name__ == "__main__":
    unittest.main()

"""FILE: tests/test_codex_middleware.py

PURPOSE:
    Feature tests for Codex turn-boundary middleware: CodexMiddlewareValidator's
    construction-time rejection of the six inner-loop hooks, and
    CodexMiddlewareRunner's handling of every MiddlewareDecision action and
    transform field at a boundary with no tool call and no retry loop. Locks
    the behavior docs/design/codex-middleware.md specifies: an unenforceable
    hook fails when declared, and an unrepresentable decision fails loudly
    rather than being treated as a no-op.

ROLE IN CODEBASE:
    Exercises vidbyte/agents/codex/middleware.py, the middleware validation in
    vidbyte/agents/codex/config.py, and the turn-boundary wiring in
    vidbyte/agents/codex/agent.py, against the real
    vidbyte/middleware/pipeline.py so fail_closed policy is genuinely in force.

ARCHITECTURE NOTE:
    Every test runs offline. Only CodexTransport is faked; MiddlewarePipeline
    is real, because the defects here — an abort that still calls the
    provider, a fail_closed error that does not abort, a swallowed transport
    exception — only appear in the wired lifecycle.

FUNCTION INVENTORY:
    No production functions. _build_agent() wires an agent to a recording
    transport; the _* middleware classes each override exactly one hook to
    return one scripted decision.

COMMON MODIFICATION PATTERNS:
    Add a decision action to CodexMiddlewareRunner._apply, then add its case
    to MiddlewareDecisionTests and its lifecycle case to
    CodexHarnessAgentMiddlewareTests.

WHAT NOT TO DO IN THIS FILE:
    Do not reimplement fail_closed expectations against a fake pipeline, and
    do not assert that an unsupported decision is silently ignored.

KNOWN EDGE CASES:
    A SLEEP decision is consumed inside MiddlewarePipeline and never reaches
    the runner, so there is no runner-level SLEEP case to assert.

RELATED DOCS: docs/design/codex-middleware.md
TESTS: python -m pytest tests/test_codex_middleware.py
"""

from __future__ import annotations

import unittest

from vidbyte.agents.codex.agent import CodexHarnessAgent
from vidbyte.agents.codex.middleware import (
    CodexMiddlewareRunner,
    CodexMiddlewareValidator,
)
from vidbyte.lib.constants.codex import (
    CODEX_MIDDLEWARE_METADATA_KEY,
    CODEX_UNSUPPORTED_MIDDLEWARE_HOOKS,
)
from vidbyte.lib.dataclasses.codex import (
    CodexHarnessAgentSettings,
    CodexMiddlewareRequest,
    CodexRunInput,
    CodexRunResult,
    CodexTransportRunRequest,
    CodexUsage,
)
from vidbyte.lib.dataclasses.middleware import (
    MiddlewareAction,
    MiddlewareContext,
    MiddlewareDecision,
    MiddlewareTransform,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError, ConfigurationError
from vidbyte.middleware.base import AgentMiddleware

FINAL_RESPONSE = "codex reply"
PROMPT = "do the thing"


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


class _RecordingTransport:
    """Stands in for CodexTransport, recording calls and optionally raising."""

    def __init__(self) -> None:
        self.requests: list[CodexTransportRunRequest] = []
        self.failure: Exception | None = None

    async def run(self, request: CodexTransportRunRequest) -> CodexRunResult:
        # Records the call so an abort can be proven to have prevented it.
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return _run_result()


class _NoOpMiddleware(AgentMiddleware):
    """Overrides nothing, so every hook keeps AgentMiddleware's default."""


class _BeforeRunMiddleware(AgentMiddleware):
    """Overrides only a supported hook and records the context it saw."""

    def __init__(self) -> None:
        self.seen: MiddlewareContext | None = None

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Captures the context so the test can assert which fields were populated.
        self.seen = ctx
        return MiddlewareDecision.continue_()


class _ScriptedBeforeRun(AgentMiddleware):
    """Returns one caller-supplied decision from before_run."""

    def __init__(self, decision: MiddlewareDecision) -> None:
        self.decision = decision

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Returns the scripted decision unchanged.
        del ctx
        return self.decision


class _ScriptedAfterRun(AgentMiddleware):
    """Returns one caller-supplied decision from after_run."""

    def __init__(self, decision: MiddlewareDecision) -> None:
        self.decision = decision

    async def after_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Returns the scripted decision unchanged.
        del ctx
        return self.decision


class _RaisingBeforeRun(AgentMiddleware):
    """Raises from before_run, exercising the pipeline's fail_closed policy."""

    def __init__(self, fail_closed: bool) -> None:
        self.fail_closed = fail_closed

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Simulates a buggy or deliberately strict policy middleware.
        del ctx
        raise RuntimeError("policy check exploded")


class _ErrorObserver(AgentMiddleware):
    """Records the exception on_model_error was handed."""

    def __init__(self) -> None:
        self.errors: list[BaseException | None] = []

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Captures the error and asks to abort, which must not replace the real one.
        self.errors.append(ctx.error)
        return MiddlewareDecision.abort("observed")


class _MetadataMiddleware(AgentMiddleware):
    """Returns continue metadata from before_run, tagged with its own name."""

    def __init__(self, name: str, value: str) -> None:
        self.name = name
        self.value = value

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Emits one metadata key so ordering and merge precedence are observable.
        del ctx
        return MiddlewareDecision.continue_(metadata={"policy": self.value})


def _make_unsupported(hook: str) -> AgentMiddleware:
    # Builds a middleware overriding exactly one unsupported hook by name.
    async def override(self: AgentMiddleware, ctx: MiddlewareContext) -> MiddlewareDecision:
        del ctx
        return MiddlewareDecision.continue_()

    subclass = type("Unsupported", (AgentMiddleware,), {hook: override})
    return subclass()


def _build_agent(
    middleware: tuple[AgentMiddleware, ...] = (),
) -> tuple[CodexHarnessAgent, _RecordingTransport]:
    # Builds an agent whose transport is a recorder, so no Codex process is started.
    agent = CodexHarnessAgent(
        CodexHarnessAgentSettings(
            name="codex-agent",
            system_prompt="You are a Codex harness agent.",
            middleware=middleware,
        )
    )
    transport = _RecordingTransport()
    agent._transport = transport  # type: ignore[assignment]
    return agent, transport


class MiddlewareValidationTests(unittest.TestCase):
    """Covers which middleware CodexMiddlewareValidator admits."""

    def test_accepts_middleware_overriding_only_before_run(self) -> None:
        CodexMiddlewareValidator.validate((_BeforeRunMiddleware(),))

    def test_accepts_middleware_overriding_no_hooks(self) -> None:
        CodexMiddlewareValidator.validate((_NoOpMiddleware(),))

    def test_accepts_a_subclass_that_overrides_nothing_new(self) -> None:
        class Deeper(_BeforeRunMiddleware):
            """Inherits a supported override and adds none of its own."""

        CodexMiddlewareValidator.validate((Deeper(),))

    def test_rejects_before_tool_call_naming_the_hook(self) -> None:
        with self.assertRaises(ConfigurationError) as caught:
            CodexMiddlewareValidator.validate((_make_unsupported("before_tool_call"),))

        self.assertIn("before_tool_call", str(caught.exception))

    def test_rejects_every_unsupported_hook(self) -> None:
        for hook in sorted(CODEX_UNSUPPORTED_MIDDLEWARE_HOOKS):
            with self.subTest(hook=hook):
                with self.assertRaises(ConfigurationError) as caught:
                    CodexMiddlewareValidator.validate((_make_unsupported(hook),))
                self.assertIn(hook, str(caught.exception))

    def test_names_every_unsupported_hook_a_middleware_overrode(self) -> None:
        async def override(
            self: AgentMiddleware, ctx: MiddlewareContext
        ) -> MiddlewareDecision:
            del ctx
            return MiddlewareDecision.continue_()

        subclass = type(
            "TwoHooks",
            (AgentMiddleware,),
            {"before_tool_call": override, "after_iteration": override},
        )

        with self.assertRaises(ConfigurationError) as caught:
            CodexMiddlewareValidator.validate((subclass(),))

        message = str(caught.exception)
        self.assertIn("before_tool_call", message)
        self.assertIn("after_iteration", message)

    def test_agent_construction_rejects_unsupported_middleware(self) -> None:
        with self.assertRaises(CodexAgentError) as caught:
            CodexHarnessAgent(
                CodexHarnessAgentSettings(
                    name="codex-agent",
                    system_prompt="prompt",
                    middleware=(_make_unsupported("before_model_call"),),
                )
            )

        self.assertEqual(
            caught.exception.failure_code,
            FailureCode.CODEX_VIDBYTE_TRANSLATION_FAILED.value,
        )


class MiddlewareSettingsValidationTests(unittest.TestCase):
    """Covers the settings record's own middleware boundary."""

    def test_rejects_a_list_instead_of_a_tuple(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexHarnessAgentSettings(
                name="a", system_prompt="p", middleware=[_NoOpMiddleware()]  # type: ignore[arg-type]
            )

    def test_rejects_an_object_that_is_not_middleware(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexHarnessAgentSettings(
                name="a", system_prompt="p", middleware=(object(),)  # type: ignore[arg-type]
            )


class MiddlewareDecisionTests(unittest.IsolatedAsyncioTestCase):
    """Covers how CodexMiddlewareRunner interprets each decision."""

    async def test_is_disabled_for_an_empty_tuple(self) -> None:
        runner = CodexMiddlewareRunner(())

        self.assertFalse(runner.enabled)
        self.assertEqual(
            await runner.before_run(
                CodexMiddlewareRequest(agent_name="a", prompt=PROMPT)
            ),
            {},
        )

    async def test_rejects_a_deny_tool_decision(self) -> None:
        runner = CodexMiddlewareRunner(
            (_ScriptedBeforeRun(MiddlewareDecision(action=MiddlewareAction.DENY_TOOL)),)
        )

        with self.assertRaises(CodexAgentError) as caught:
            await runner.before_run(
                CodexMiddlewareRequest(agent_name="a", prompt=PROMPT)
            )

        self.assertEqual(
            caught.exception.failure_code,
            FailureCode.CODEX_MIDDLEWARE_UNSUPPORTED.value,
        )

    async def test_rejects_a_retry_decision(self) -> None:
        runner = CodexMiddlewareRunner(
            (_ScriptedBeforeRun(MiddlewareDecision(action=MiddlewareAction.RETRY)),)
        )

        with self.assertRaises(CodexAgentError) as caught:
            await runner.before_run(
                CodexMiddlewareRequest(agent_name="a", prompt=PROMPT)
            )

        self.assertEqual(
            caught.exception.safe_runtime_details["error_type"],
            MiddlewareAction.RETRY.value,
        )

    async def test_rejects_a_system_transform_naming_the_field(self) -> None:
        runner = CodexMiddlewareRunner(
            (
                _ScriptedBeforeRun(
                    MiddlewareDecision.continue_(
                        transform=MiddlewareTransform(system="rewritten")
                    )
                ),
            )
        )

        with self.assertRaises(CodexAgentError) as caught:
            await runner.before_run(
                CodexMiddlewareRequest(agent_name="a", prompt=PROMPT)
            )

        self.assertEqual(caught.exception.safe_runtime_details["error_type"], "system")

    async def test_applies_transform_metadata(self) -> None:
        runner = CodexMiddlewareRunner(
            (
                _ScriptedBeforeRun(
                    MiddlewareDecision.continue_(
                        transform=MiddlewareTransform(metadata={"tag": "value"})
                    )
                ),
            )
        )

        applied = await runner.before_run(
            CodexMiddlewareRequest(agent_name="a", prompt=PROMPT)
        )

        self.assertEqual(applied, {"tag": "value"})

    async def test_populates_the_observable_context_fields(self) -> None:
        middleware = _BeforeRunMiddleware()
        runner = CodexMiddlewareRunner((middleware,))

        await runner.before_run(
            CodexMiddlewareRequest(agent_name="codex-agent", prompt=PROMPT)
        )

        seen = middleware.seen
        assert seen is not None
        self.assertEqual(seen.agent_name, "codex-agent")
        self.assertEqual(seen.message, PROMPT)
        self.assertEqual(seen.hook.value, "before_run")

    async def test_leaves_inner_loop_context_fields_at_their_defaults(self) -> None:
        middleware = _BeforeRunMiddleware()
        runner = CodexMiddlewareRunner((middleware,))

        await runner.before_run(
            CodexMiddlewareRequest(agent_name="codex-agent", prompt=PROMPT)
        )

        seen = middleware.seen
        assert seen is not None
        self.assertEqual(seen.iteration_count, 0)
        self.assertIsNone(seen.tool_call)
        self.assertIsNone(seen.model_response)


class CodexHarnessAgentMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    """Covers the wired turn lifecycle with a real MiddlewarePipeline."""

    async def test_before_run_abort_prevents_the_native_turn(self) -> None:
        agent, transport = _build_agent(
            (_ScriptedBeforeRun(MiddlewareDecision.abort("blocked")),)
        )

        with self.assertRaises(CodexAgentError) as caught:
            await agent.arun(CodexRunInput.text(PROMPT))

        self.assertEqual(
            caught.exception.failure_code,
            FailureCode.CODEX_MIDDLEWARE_ABORTED.value,
        )
        self.assertEqual(caught.exception.operation, "before_run")
        self.assertEqual(transport.requests, [])

    async def test_fail_closed_middleware_error_aborts_the_turn(self) -> None:
        agent, transport = _build_agent((_RaisingBeforeRun(fail_closed=True),))

        with self.assertRaises(CodexAgentError):
            await agent.arun(CodexRunInput.text(PROMPT))

        self.assertEqual(transport.requests, [])

    async def test_fail_open_middleware_error_lets_the_turn_proceed(self) -> None:
        agent, transport = _build_agent((_RaisingBeforeRun(fail_closed=False),))

        reply = await agent.arun(CodexRunInput.text(PROMPT))

        self.assertEqual(reply.content, FINAL_RESPONSE)
        self.assertEqual(len(transport.requests), 1)
        reasons = {
            event["reason"]
            for event in reply.metadata[CODEX_MIDDLEWARE_METADATA_KEY]["events"]
        }
        self.assertIn("middleware_error_fail_open", reasons)

    async def test_on_model_error_never_replaces_the_transport_exception(self) -> None:
        observer = _ErrorObserver()
        agent, transport = _build_agent((observer,))
        transport.failure = TimeoutError("too slow")

        with self.assertRaises(TimeoutError):
            await agent.arun(CodexRunInput.text(PROMPT))

        self.assertEqual(len(observer.errors), 1)
        self.assertIsInstance(observer.errors[0], TimeoutError)

    async def test_after_run_abort_reports_its_own_boundary(self) -> None:
        agent, transport = _build_agent(
            (_ScriptedAfterRun(MiddlewareDecision.abort("too expensive")),)
        )

        with self.assertRaises(CodexAgentError) as caught:
            await agent.arun(CodexRunInput.text(PROMPT))

        self.assertEqual(caught.exception.operation, "after_run")
        self.assertEqual(len(transport.requests), 1)

    async def test_middleware_runs_in_declared_order_with_later_keys_winning(
        self,
    ) -> None:
        agent, _ = _build_agent(
            (
                _MetadataMiddleware("first", "first-value"),
                _MetadataMiddleware("second", "second-value"),
            )
        )

        reply = await agent.arun(CodexRunInput.text(PROMPT))

        self.assertEqual(reply.metadata["policy"], "second-value")

    async def test_middleware_metadata_reaches_the_reply(self) -> None:
        agent, _ = _build_agent((_BeforeRunMiddleware(),))

        reply = await agent.arun(CodexRunInput.text(PROMPT))

        self.assertIn(CODEX_MIDDLEWARE_METADATA_KEY, reply.metadata)

    async def test_no_middleware_leaves_the_reply_metadata_untouched(self) -> None:
        agent, _ = _build_agent()

        reply = await agent.arun(CodexRunInput.text(PROMPT))

        self.assertNotIn(CODEX_MIDDLEWARE_METADATA_KEY, reply.metadata)
        self.assertNotIn("policy", reply.metadata)


if __name__ == "__main__":
    unittest.main()

"""FILE: tests/test_codex_fork_inheritance.py

PURPOSE:
    Feature tests for what a CodexHarnessAgent fork inherits from its parent
    beyond tools: the turn middleware, the model fallback chain, and the loop
    settings that carry output contracts. Locks the guarantee that branching a
    guarded thread never silently strips the guardrails the parent enforces,
    and that an inherited chain the child cannot reach fails before Codex
    creates a native branch.

ROLE IN CODEBASE:
    Exercises CodexFork._prepare_child and CodexFork.afork in
    vidbyte/agents/codex/fork.py through the public CodexHarnessAgent.afork,
    together with the middleware, fallback, and contract wiring in
    vidbyte/agents/codex/agent.py that the child must still run.

ARCHITECTURE NOTE:
    Every test runs offline and without the optional openai-codex extra. Only
    CodexTransport is replaced, by _ScriptedTransport, which records each run
    and each native fork; middleware, fallback, and contract evaluation are the
    real implementations, because a dropped guardrail only shows up when the
    forked child actually runs a turn.

FUNCTION INVENTORY:
    No production functions. _codex() builds provider settings; _parent()
    builds a parent agent bound to an existing thread and to a scripted
    transport; _fork() forks it and binds the child to the same transport.

COMMON MODIFICATION PATTERNS:
    When CodexHarnessAgentSettings gains another guardrail, add it to
    _parent()'s guarded case and assert both the child's settings and the
    child's behaviour in CodexForkGuardrailInheritanceTests.

WHAT NOT TO DO IN THIS FILE:
    Do not assert only on child settings; a guardrail is kept only when the
    child's turn is refused, retried, or rejected the way the parent's is.

KNOWN EDGE CASES:
    A codex= override replaces the parent's whole CodexAgentSettings, so an
    override naming no model leaves an inherited fallback chain with no primary
    and must fail as codex.fork_failed before any native fork.

RELATED DOCS: vidbyte/agents/codex/README.md (section 9, Forking a thread)
TESTS: python -m pytest tests/test_codex_fork_inheritance.py
"""

from __future__ import annotations

import unittest

from vidbyte.agents.codex.agent import CodexHarnessAgent
from vidbyte.agents.codex.fork import CodexFork
from vidbyte.agents.contracts import MinToolCalls
from vidbyte.agents.settings.fallback import AgentFallbackSettings
from vidbyte.agents.settings.loop import AgentLoopSettings
from vidbyte.lib.dataclasses.codex import (
    CodexAgentSettings,
    CodexForkSettings,
    CodexHarnessAgentSettings,
    CodexRunInput,
    CodexRunResult,
    CodexThreadIdentity,
    CodexTransportForkRequest,
    CodexTransportRunRequest,
    CodexTurnSettings,
    CodexUsage,
)
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError
from vidbyte.middleware.base import AgentMiddleware

FINAL_RESPONSE = "codex reply"
PARENT_THREAD = "th_parent"
CHILD_THREAD = "th_child"
PRIMARY_MODEL = "gpt-5.5"
BACKUP_MODEL = "gpt-5.4-mini"
PROTECTED_PROMPT = "Edit migrations/0042.sql"
SAFE_PROMPT = "Fix the flaky test."
CHILD_CWD = "worktrees/child"


class _ProtectedPathGuard(AgentMiddleware):
    """Refuses any turn whose prompt names a protected path."""

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Aborts before the turn reaches Codex, so a refused prompt edits nothing.
        if "migrations/" in (ctx.message or ""):
            return MiddlewareDecision.abort("protected paths requested")
        return MiddlewareDecision.continue_()


class _ScriptedTransport:
    """Stands in for CodexTransport, recording runs and native forks."""

    def __init__(self) -> None:
        self.runs: list[CodexTransportRunRequest] = []
        self.forks: list[CodexTransportForkRequest] = []
        self.failing_model = ""

    async def run(self, request: CodexTransportRunRequest) -> CodexRunResult:
        # Records the run and fails it when it targets the scripted failing model.
        self.runs.append(request)
        if self.failing_model and request.settings.turn.model == self.failing_model:
            raise CodexAgentError(
                "Codex failed the requested turn.",
                failure_code=FailureCode.CODEX_TURN_FAILED.value,
                operation="turn_run",
            )
        return CodexRunResult(
            thread_id=request.thread_id,
            turn_id="tu_1",
            status="completed",
            final_response=FINAL_RESPONSE,
            duration_ms=12,
            usage=CodexUsage(),
            items=(),
        )

    async def fork_thread(self, request: CodexTransportForkRequest) -> CodexThreadIdentity:
        # Records the native fork so a test can prove whether one was created.
        self.forks.append(request)
        return CodexThreadIdentity(thread_id=CHILD_THREAD)


def _codex(model: str = PRIMARY_MODEL, cwd: str = "") -> CodexAgentSettings:
    # Builds provider settings naming an optional turn model and working directory.
    return CodexAgentSettings(turn=CodexTurnSettings(model=model, cwd=cwd))


def _parent(**guardrails: object) -> tuple[CodexHarnessAgent, _ScriptedTransport]:
    # Builds a parent already bound to a thread, so it can fork without a first run.
    agent = CodexHarnessAgent(
        CodexHarnessAgentSettings(
            name="guarded",
            system_prompt="Implement the change.",
            thread_id=PARENT_THREAD,
            codex=_codex(),
            **guardrails,  # type: ignore[arg-type]
        )
    )
    transport = _ScriptedTransport()
    agent._transport = transport  # type: ignore[assignment]
    agent._forks = CodexFork(transport)  # type: ignore[arg-type]
    return agent, transport


async def _fork(
    parent: CodexHarnessAgent,
    transport: _ScriptedTransport,
    settings: CodexForkSettings | None = None,
) -> CodexHarnessAgent:
    # Forks the parent and points the child at the same scripted transport.
    child = await parent.afork(settings or CodexForkSettings())
    child._transport = transport  # type: ignore[assignment]
    return child


def _fallback() -> AgentFallbackSettings:
    # Builds a one-step chain that retries a failed Codex turn on the backup model.
    return AgentFallbackSettings(models=[BACKUP_MODEL], fallback_on=(CodexAgentError,))


class CodexForkGuardrailInheritanceTests(unittest.IsolatedAsyncioTestCase):
    """A default fork keeps the parent's middleware, fallback chain, and loop settings."""

    async def test_default_fork_inherits_middleware_fallback_and_loop(self) -> None:
        guard = _ProtectedPathGuard()
        fallback = _fallback()
        loop = AgentLoopSettings(output_contracts=(MinToolCalls(1),))
        parent, transport = _parent(middleware=(guard,), fallback=fallback, loop=loop)

        child = await _fork(parent, transport)

        self.assertEqual(child.settings.middleware, (guard,))
        self.assertIs(child.settings.fallback, fallback)
        self.assertIs(child.settings.loop, loop)
        self.assertEqual(child.thread_id, CHILD_THREAD)

    async def test_forked_guard_refuses_before_any_transport_run(self) -> None:
        parent, transport = _parent(middleware=(_ProtectedPathGuard(),))
        child = await _fork(parent, transport)

        with self.assertRaises(CodexAgentError) as caught:
            await child.arun(CodexRunInput.text(PROTECTED_PROMPT))

        self.assertEqual(
            caught.exception.failure_code, FailureCode.CODEX_MIDDLEWARE_ABORTED.value
        )
        self.assertEqual(transport.runs, [])

    async def test_forked_fallback_chain_answers_on_the_backup_model(self) -> None:
        parent, transport = _parent(fallback=_fallback())
        child = await _fork(parent, transport)
        transport.failing_model = PRIMARY_MODEL

        reply = await child.arun(CodexRunInput.text(SAFE_PROMPT))

        self.assertEqual(reply.content, FINAL_RESPONSE)
        self.assertEqual(
            [request.settings.turn.model for request in transport.runs],
            [PRIMARY_MODEL, BACKUP_MODEL],
        )

    async def test_forked_output_contract_rejects_a_turn_with_no_tool_calls(self) -> None:
        parent, transport = _parent(
            loop=AgentLoopSettings(output_contracts=(MinToolCalls(1),))
        )
        child = await _fork(parent, transport)

        with self.assertRaises(CodexAgentError) as caught:
            await child.arun(CodexRunInput.text(SAFE_PROMPT))

        self.assertEqual(
            caught.exception.failure_code, FailureCode.CODEX_CONTRACT_UNMET.value
        )


class CodexForkFallbackValidationTests(unittest.IsolatedAsyncioTestCase):
    """An inherited chain the child cannot reach fails before any native fork."""

    async def test_override_naming_no_model_fails_before_the_native_fork(self) -> None:
        parent, transport = _parent(fallback=_fallback())

        with self.assertRaises(CodexAgentError) as caught:
            await parent.afork(CodexForkSettings(codex=_codex(model="", cwd=CHILD_CWD)))

        self.assertEqual(caught.exception.failure_code, FailureCode.CODEX_FORK_FAILED.value)
        self.assertEqual(caught.exception.operation, "prepare_fork")
        self.assertEqual(transport.forks, [])


class CodexForkControlTests(unittest.IsolatedAsyncioTestCase):
    """Forks that need no guardrail handling keep working as before."""

    async def test_fork_of_an_unguarded_parent_runs_a_turn(self) -> None:
        parent, transport = _parent()
        child = await _fork(parent, transport)

        reply = await child.arun(CodexRunInput.text(SAFE_PROMPT))

        self.assertEqual(reply.content, FINAL_RESPONSE)
        self.assertEqual(child.settings.middleware, ())
        self.assertIsNone(child.settings.fallback)
        self.assertIsNone(child.settings.loop)
        self.assertEqual([request.thread_id for request in transport.runs], [CHILD_THREAD])

    async def test_override_naming_the_model_keeps_the_chain(self) -> None:
        fallback = _fallback()
        parent, transport = _parent(fallback=fallback)

        child = await _fork(
            parent, transport, CodexForkSettings(codex=_codex(cwd=CHILD_CWD))
        )

        self.assertIs(child.settings.fallback, fallback)
        self.assertEqual(child.settings.codex.turn.cwd, CHILD_CWD)
        self.assertEqual(len(transport.forks), 1)


if __name__ == "__main__":
    unittest.main()

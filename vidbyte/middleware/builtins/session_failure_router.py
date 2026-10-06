"""FILE: vidbyte/middleware/builtins/session_failure_router.py

PURPOSE: Bridges a Session's FailureRouter into the ordinary linear AgentMiddleware lifecycle.
ROLE IN CODEBASE: Lets a bound FailureRouter evaluate developer @rule detectors at every runtime hook
    using the same policy-middleware seam every other built-in guardrail uses.
ARCHITECTURE NOTE: Only type-checks against vidbyte.sessions.failure.router.FailureRouter; it never
    imports the sessions package at runtime, so vidbyte.sessions.failure.router can construct this
    middleware without creating an import cycle between the middleware and sessions domain layers.
COMMON MODIFICATION PATTERNS: Add a hook override here when the runtime gains a new lifecycle breakpoint;
    keep rule evaluation itself owned by FailureRouter.evaluate().
KNOWN EDGE CASES: A matched rule with a stop/raise disposition aborts the run; every other disposition
    is left to FailureRouter's own history and recovery bookkeeping.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/README.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.lib.enums.failure import FailureCode, FailureDisposition
from vidbyte.middleware.base import AgentMiddleware

if TYPE_CHECKING:
    from vidbyte.sessions.failure.router import FailureRouter

__all__ = ["FailureMiddleware"]


class FailureMiddleware(AgentMiddleware):
    """Bridge Session rules into the existing linear AgentMiddleware lifecycle."""

    name = "session_failure_router"
    fail_closed = True

    def __init__(self, router: "FailureRouter") -> None:
        """Bind one middleware instance to a Session failure router."""
        self.router = router

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Evaluate Session rules before a run begins."""
        return await self._evaluate("before_run", ctx)

    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Evaluate Session rules before each loop iteration."""
        return await self._evaluate("before_iteration", ctx)

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Evaluate Session rules before a model request."""
        return await self._evaluate("before_model_call", ctx)

    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Evaluate Session rules after a model response."""
        return await self._evaluate("after_model_response", ctx)

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Evaluate Session rules when a model request errors."""
        return await self._evaluate("on_model_error", ctx)

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Evaluate Session rules before a tool is permitted to execute."""
        return await self._evaluate("before_tool_call", ctx)

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Evaluate Session rules after a tool result is available."""
        return await self._evaluate("after_tool_call", ctx)

    async def after_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Evaluate Session rules after one loop iteration."""
        return await self._evaluate("after_iteration", ctx)

    async def after_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Evaluate Session rules before the runtime returns its final result."""
        return await self._evaluate("after_run", ctx)

    async def _evaluate(self, hook: str, context: MiddlewareContext) -> MiddlewareDecision:
        # Translate rule dispositions into the existing middleware decision contract.
        failures = await self.router.evaluate(hook, context)
        for failure in failures:
            if failure.disposition in (FailureDisposition.STOP, FailureDisposition.RAISE):
                return MiddlewareDecision.abort("failure_rule", metadata={"failure_code": FailureCode.from_value(failure.code).value, "failure_id": failure.id, "rule": failure.source})
        return MiddlewareDecision.continue_()

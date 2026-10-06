"""FILE: vidbyte/agents/codex/middleware.py

PURPOSE: Runs the turn-boundary middleware hooks Codex can honestly support, and
    rejects at construction the six inner-loop hooks it cannot enforce.
ROLE IN CODEBASE: config.py validates at construction; agent.py runs the hooks per turn.
    MiddlewarePipeline owns dispatch, fail_closed policy, sleeps, and event recording.
ARCHITECTURE NOTE: before_run, after_run, and on_model_error sit at boundaries Vidbyte
    owns. The other six describe positions inside a loop Codex owns, where no point
    exists at which Vidbyte could refuse an action; declaring one fails to load.
FUNCTION INVENTORY: CodexMiddlewareValidator.validate rejects unsupported overrides;
    CodexMiddlewareRunner.before_run/after_run/on_model_error dispatch one hook each.
COMMON MODIFICATION PATTERNS: To support a new hook, prove its enforcement point first,
    then remove it from CODEX_UNSUPPORTED_MIDDLEWARE_HOOKS and add its runner method.
WHAT NOT TO DO IN THIS FILE: Do not reimplement fail_closed, sleep, or event recording
    (MiddlewarePipeline owns them), and never treat an unrepresentable decision as a
    no-op: a caller returning RETRY must learn nothing retried.
KNOWN EDGE CASES: A SLEEP decision never reaches this module because the pipeline awaits
    it and continues. An after_run abort cannot un-run the turn, so it says so.
RELATED DOCS: docs/design/codex-middleware.md
TESTS: tests/test_codex_middleware.py; python scripts/run_ci.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.lib.constants.codex import CODEX_UNSUPPORTED_MIDDLEWARE_HOOKS
from vidbyte.lib.dataclasses.codex import CodexMiddlewareRequest
from vidbyte.lib.dataclasses.middleware import (
    MiddlewareAction,
    MiddlewareContext,
    MiddlewareDecision,
    MiddlewareHook,
    MiddlewareTransform,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError, ConfigurationError
from vidbyte.middleware.base import AgentMiddleware
from vidbyte.middleware.pipeline import MiddlewarePipeline

_UNREPRESENTABLE_ACTIONS = {
    MiddlewareAction.DENY_TOOL: "no Vidbyte-owned tool boundary exists in a Codex turn",
    MiddlewareAction.RETRY: "no Vidbyte-owned retry loop exists in a Codex turn",
}
_UNSUPPORTED_TRANSFORM_FIELDS = (
    "system",
    "provider_messages",
    "model_visible_tool_result",
)


class CodexMiddlewareValidator:
    """Rejects middleware whose hooks have no Codex enforcement point."""

    @classmethod
    def validate(cls, middleware: Sequence[AgentMiddleware]) -> None:
        # @intent fail-when-declared-not-when-relied-on
        # A fail_closed tool policy that loads and never runs is indistinguishable
        # from one that works, so an unenforceable hook must break construction.
        for entry in middleware:
            overridden = cls._unsupported_overrides(entry)
            if not overridden:
                continue
            raise ConfigurationError(
                f"Codex cannot enforce middleware {cls._name(entry)!r} hooks "
                f"{', '.join(overridden)}: Codex owns its model and tool loop, so "
                "Vidbyte has no point at which to refuse those actions. Only "
                "before_run, after_run, and on_model_error are supported."
            )

    @staticmethod
    def _unsupported_overrides(middleware: AgentMiddleware) -> tuple[str, ...]:
        # Compares function objects so an inherited, untouched hook is not a finding;
        # getattr walks the MRO, which is what makes a subclass of a subclass correct.
        owner = type(middleware)
        return tuple(
            hook
            for hook in sorted(CODEX_UNSUPPORTED_MIDDLEWARE_HOOKS)
            if getattr(owner, hook, None) is not getattr(AgentMiddleware, hook, None)
        )

    @staticmethod
    def _name(middleware: AgentMiddleware) -> str:
        # Prefers the middleware's own display name for an actionable message.
        return getattr(middleware, "middleware_name", type(middleware).__name__)


class CodexMiddlewareRunner:
    """Runs the turn-boundary middleware hooks Codex can honestly support."""

    def __init__(self, middleware: Sequence[AgentMiddleware]) -> None:
        # An empty tuple leaves the agent's hot path untouched, with no pipeline work.
        self._middleware = tuple(middleware)
        self._pipeline = MiddlewarePipeline(self._middleware)

    @property
    def enabled(self) -> bool:
        """Return whether any middleware is attached to this agent."""
        return bool(self._middleware)

    async def before_run(self, request: CodexMiddlewareRequest) -> Mapping[str, Any]:
        """Run before_run and return its merged transform metadata."""
        # @intent decide-before-the-provider-is-touched
        # An abort evaluated after the transport call would already have spent
        # tokens and possibly edited files, so this must precede the native turn.
        if not self.enabled:
            return {}
        decision = await self._pipeline.before_run(
            self._context(MiddlewareHook.BEFORE_RUN, request)
        )
        return self._apply(decision, MiddlewareHook.BEFORE_RUN)

    async def after_run(self, request: CodexMiddlewareRequest) -> Mapping[str, Any]:
        """Run after_run and return its merged transform metadata."""
        if not self.enabled:
            return {}
        decision = await self._pipeline.after_run(
            self._context(MiddlewareHook.AFTER_RUN, request)
        )
        return self._apply(decision, MiddlewareHook.AFTER_RUN)

    async def on_model_error(self, request: CodexMiddlewareRequest) -> None:
        """Run on_model_error for observation only, discarding its decision."""
        # @intent never-replace-the-real-failure
        # The transport's exception is what the caller needs; a middleware decision
        # here would substitute a diagnosis for the actual cause.
        if not self.enabled:
            return
        await self._pipeline.on_model_error(
            self._context(MiddlewareHook.ON_MODEL_ERROR, request)
        )

    def metadata(self) -> dict[str, Any]:
        """Return the pipeline's accumulated middleware metadata and events."""
        return self._pipeline.metadata()

    def _context(
        self, hook: MiddlewareHook, request: CodexMiddlewareRequest
    ) -> MiddlewareContext:
        # @intent report-only-what-is-observable
        # Inner-loop fields stay at their defaults on purpose: reporting an
        # iteration_count of 1 would describe a Vidbyte loop that never ran, and a
        # middleware reading it would make a decision on a fabricated fact.
        return MiddlewareContext(
            hook=hook,
            agent_name=request.agent_name,
            provider=None,
            message=request.prompt,
            elapsed_seconds=request.elapsed_seconds,
            error=request.error,
        )

    def _apply(
        self, decision: MiddlewareDecision, hook: MiddlewareHook
    ) -> Mapping[str, Any]:
        # Dispatch on the action so the unrepresentable set is visible in one place
        # and a future MiddlewareAction member fails loudly instead of falling through.
        if decision.action is MiddlewareAction.ABORT_RUN:
            raise CodexAgentError(
                f"Vidbyte middleware aborted the Codex turn at {hook.value}.",
                failure_code=FailureCode.CODEX_MIDDLEWARE_ABORTED.value,
                operation=hook.value,
                error_type=decision.reason or "abort_run",
            )
        reason = _UNREPRESENTABLE_ACTIONS.get(decision.action)
        if reason is not None:
            raise CodexAgentError(
                f"Vidbyte middleware requested {decision.action.value} at "
                f"{hook.value}, which Codex cannot carry out: {reason}.",
                failure_code=FailureCode.CODEX_MIDDLEWARE_UNSUPPORTED.value,
                operation=hook.value,
                error_type=decision.action.value,
            )
        if decision.action is not MiddlewareAction.CONTINUE:
            raise CodexAgentError(
                f"Vidbyte middleware returned unhandled action "
                f"{decision.action.value} at {hook.value}.",
                failure_code=FailureCode.CODEX_MIDDLEWARE_UNSUPPORTED.value,
                operation=hook.value,
                error_type=decision.action.value,
            )
        # Decision metadata is the common case (MiddlewareDecision.continue_(metadata=...));
        # a transform's metadata layers on top of it, matching the pipeline's own merge.
        return {
            **dict(decision.metadata),
            **dict(self._transform_metadata(decision.transform, hook)),
        }

    @staticmethod
    def _transform_metadata(
        transform: MiddlewareTransform | None, hook: MiddlewareHook
    ) -> Mapping[str, Any]:
        # Metadata is carried; the other fields rewrite a Vidbyte-owned message list
        # or system prompt whose Codex lifetime is undecided, so they fail loudly.
        if transform is None:
            return {}
        for field_name in _UNSUPPORTED_TRANSFORM_FIELDS:
            if getattr(transform, field_name, None) is not None:
                raise CodexAgentError(
                    f"Vidbyte middleware transform field {field_name!r} at "
                    f"{hook.value} has no defined Codex representation.",
                    failure_code=FailureCode.CODEX_MIDDLEWARE_UNSUPPORTED.value,
                    operation=hook.value,
                    error_type=field_name,
                )
        return dict(transform.metadata)


__all__ = ["CodexMiddlewareRunner", "CodexMiddlewareValidator"]

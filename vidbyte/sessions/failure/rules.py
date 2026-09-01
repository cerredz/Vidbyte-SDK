"""FILE: vidbyte/sessions/failure/rules.py

PURPOSE: Defines developer-owned Session failure detectors and the @rule decorator.
ROLE IN CODEBASE: Stores explicit rule metadata and invokes sync or async callbacks for lifecycle hooks.
ARCHITECTURE NOTE: Decoration is metadata-only; registration is explicit on one Session failure router.
COMMON MODIFICATION PATTERNS: Add hook validation or disposition behavior without creating global registries.
KNOWN EDGE CASES: Rule callbacks may return None, must return Failure otherwise, and have separate error posture.
RELATED DOCS: docs/design/session-failure-vocabulary.md; skills/failure/authoring.md.
TESTS: python -m pytest -q tests/test_session_failures.py.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar, cast

from vidbyte.sessions.failure.types import (
    Failure,
    FailureCode,
    FailureDisposition,
    RuleErrorMode,
)

_RuleFunction = TypeVar("_RuleFunction", bound=Callable[..., Any])
_RULE_HOOKS = frozenset({"before_run", "before_iteration", "before_model_call", "after_model_response", "on_model_error", "before_tool_call", "after_tool_call", "after_iteration", "after_run"})


@dataclass(frozen=True, slots=True)
class FailureRule:
    """Immutable metadata wrapper around a developer-provided failure detector."""

    callback: Callable[..., Any]
    code: FailureCode
    on: str
    on_match: FailureDisposition
    on_error: RuleErrorMode
    priority: int = 0
    name: str = ""

    def __post_init__(self) -> None:
        """Validate hook and policy values before a rule enters a router."""
        if not callable(self.callback):
            raise TypeError("FailureRule.callback must be callable.")
        if self.on not in _RULE_HOOKS:
            raise ValueError(f"FailureRule.on must be one of {sorted(_RULE_HOOKS)}.")
        object.__setattr__(self, "code", FailureCode.from_value(self.code))
        object.__setattr__(self, "on_match", FailureDisposition(self.on_match))
        object.__setattr__(self, "on_error", RuleErrorMode(self.on_error))
        object.__setattr__(self, "name", self.name.strip() or getattr(self.callback, "__name__", type(self.callback).__name__))

    async def invoke(self, context: object) -> Failure | None:
        """Invoke the rule callback and normalize its return value."""
        value = self.callback(context)
        if inspect.isawaitable(value):
            value = await cast(Awaitable[Any], value)
        if value is None:
            return None
        if not isinstance(value, Failure):
            raise TypeError(f"Failure rule {self.name!r} must return Failure or None, got {type(value).__name__}.")
        if value.code is not self.code:
            return Failure(code=self.code, source=value.source, phase=value.phase, status=value.status, disposition=value.disposition, severity=value.severity, summary=value.summary, details=value.details, handled_by=value.handled_by, parent_id=value.parent_id, iteration=value.iteration, step=value.step, id=value.id, occurred_at=value.occurred_at)
        return value

    @classmethod
    def from_callable(cls, callback: Callable[..., Any]) -> FailureRule:
        """Create a descriptor from metadata attached by ``@rule``."""
        metadata = getattr(callback, "__vidbyte_failure_rule__", None)
        if not isinstance(metadata, FailureRule):
            raise TypeError("Callable was not decorated with @rule; pass explicit FailureRule metadata.")
        return metadata


def rule(*, code: FailureCode | str, on: str, on_match: FailureDisposition | str = FailureDisposition.ROUTE, on_error: RuleErrorMode | str = RuleErrorMode.OPEN, priority: int = 0, name: str = "") -> Callable[[_RuleFunction], _RuleFunction]:
    """Attach Session failure-rule metadata without registering or executing the callback."""
    descriptor = FailureRule(callback=lambda _context: None, code=FailureCode.from_value(code), on=on, on_match=FailureDisposition(on_match), on_error=RuleErrorMode(on_error), priority=priority, name=name)

    def decorate(callback: _RuleFunction) -> _RuleFunction:
        # Store a callback-bound descriptor so registration remains explicitly Session-scoped.
        bound = FailureRule(callback=callback, code=descriptor.code, on=descriptor.on, on_match=descriptor.on_match, on_error=descriptor.on_error, priority=descriptor.priority, name=descriptor.name)
        if inspect.iscoroutinefunction(callback):
            @wraps(callback)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await callback(*args, **kwargs)

            wrapper_any = cast(Any, async_wrapper)
            wrapper_any.__vidbyte_failure_rule__ = bound
            return cast(_RuleFunction, async_wrapper)
        callback_any = cast(Any, callback)
        callback_any.__vidbyte_failure_rule__ = bound
        return callback

    return decorate


__all__ = ["FailureRule", "rule"]

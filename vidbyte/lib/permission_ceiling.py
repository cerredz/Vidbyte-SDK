"""FILE: vidbyte/lib/permission_ceiling.py

PURPOSE: Names the highest tool permissions the current run, and every agent and task it starts, may still use, so one scope can make a whole run unable to write or execute however its agents are configured.
ROLE IN CODEBASE: PermissionPolicy.check (vidbyte/lib/dataclasses/security.py) consults PermissionCeiling on every decision, and both enforcement points, AgentRuntime._check_permission and ToolExecutor.execute_call, call that check; JevRuntime opens PermissionCeiling.scope(PermissionCeiling.READ_ONLY) for a run its READ_ONLY preflight judged to ask only for an assessment.
ARCHITECTURE NOTE: The ceiling is a ContextVar, like vidbyte/lib/usage_ledger.py, so concurrent runs stay isolated and every asyncio task created inside a scope (a specialist, bulk-work agents, clones, swarm helpers, fresh continuations, forks) inherits it with no per-path plumbing. A ceiling only ever removes permissions: it caps a policy and never grants what the policy withholds.
COMMON MODIFICATION PATTERNS: A new run-wide permission cap opens scope() with its own named set here; a new enforcement point calls PermissionPolicy.check instead of reading the ContextVar itself.
KNOWN EDGE CASES: A nested scope intersects with the active ceiling, so it can narrow but never widen it; two non-overlapping scopes leave an empty ceiling that refuses every tool, isDone included. A bare string, an empty set, or an unknown permission is rejected. A thread started without contextvars.copy_context() does not inherit the ceiling; no SDK run path starts one.
RELATED DOCS: docs/design/jev-read-only-intent.md.
TESTS: tests/features/jev_read_only/test_jev_read_only.py and scripts/test-jev-read-only.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import ClassVar

from vidbyte.lib.dataclasses.tools import ToolPermission
from vidbyte.lib.errors import ConfigurationError


class PermissionCeiling:
    """The tool permissions the current run, and every agent and task it starts, may still use."""

    READ_ONLY: ClassVar[frozenset[ToolPermission]] = frozenset({ToolPermission.SAFE, ToolPermission.READ})
    _active: ClassVar[ContextVar[frozenset[ToolPermission] | None]] = ContextVar("vidbyte_permission_ceiling", default=None)

    @classmethod
    def current(cls) -> frozenset[ToolPermission] | None:
        # Returns the permissions the active ceiling allows, or None
        # when no ceiling is in effect.
        return cls._active.get()

    @classmethod
    def allows(cls, permission: ToolPermission) -> bool:
        # Returns True when no ceiling is active or the active ceiling
        # includes the permission.
        ceiling = cls._active.get()
        return ceiling is None or permission in ceiling

    @classmethod
    def denial_note(cls, permission: ToolPermission) -> str:
        # Returns the clause a denial message appends when the ceiling,
        # not the caller's policy, is why a tool cannot run.
        ceiling = cls._active.get()
        if ceiling is None or permission in ceiling:
            return ""
        if not ceiling:
            return "; this run allows no tools"
        return f"; this run allows only {', '.join(sorted(item.value for item in ceiling))} tools"

    @classmethod
    @contextmanager
    def scope(cls, allowed: Iterable[ToolPermission | str]) -> Iterator[frozenset[ToolPermission]]:
        # Caps tool permissions to `allowed` until the block exits, for
        # this run and every task it starts.
        # @intent a-ceiling-only-narrows
        # A nested agent may open its own scope, and a scope that could
        # widen the outer one would let a spawned agent write inside a
        # read-only run, so the new ceiling is the intersection.
        requested = cls._normalize(allowed)
        outer = cls._active.get()
        ceiling = requested if outer is None else outer & requested
        token = cls._active.set(ceiling)
        try:
            yield ceiling
        finally:
            cls._active.reset(token)

    @staticmethod
    def _normalize(allowed: Iterable[ToolPermission | str]) -> frozenset[ToolPermission]:
        # Converts the caller's permissions to a non-empty frozenset of
        # ToolPermission, rejecting a bare string or an unknown value.
        if isinstance(allowed, (str, bytes)):
            raise ConfigurationError(
                "PermissionCeiling.scope needs a collection of tool permissions, not a single string.",
                details={"received": repr(allowed), "available": [item.value for item in ToolPermission]},
            )
        try:
            permissions = frozenset(ToolPermission(value) for value in allowed)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                "PermissionCeiling.scope received a value that is not a tool permission.",
                details={"received": repr(allowed), "available": [item.value for item in ToolPermission]},
            ) from exc
        if not permissions:
            raise ConfigurationError(
                "PermissionCeiling.scope needs at least one tool permission; an empty ceiling would refuse every tool, isDone included.",
                details={"received": repr(allowed), "available": [item.value for item in ToolPermission]},
            )
        return permissions


__all__ = ["PermissionCeiling"]

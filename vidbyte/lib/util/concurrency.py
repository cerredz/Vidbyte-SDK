"""Shared SDK asynchronous capacity admission.

PURPOSE: Centralize bounded admission to concurrent SDK operations.
ROLE IN CODEBASE: Used by native Codex control with one execution slot.
ARCHITECTURE NOTE: BoundedSemaphore owns permit accounting and cancelled waiters.
COMMON MODIFICATION PATTERNS: Preserve capacity through exceptions and cancellation.
KNOWN EDGE CASES: A cancelled waiter has no permit to release.
RELATED DOCS: docs/design/codex-live-control.md
TESTS: tests/codex_control/test_control.py
"""

from __future__ import annotations

import asyncio
from types import TracebackType

from pydantic import PositiveInt, TypeAdapter


class AsyncCapacityLimiter:
    """SDK-owned async context manager for bounded concurrent operations."""

    def __init__(self, capacity: int = 1) -> None:
        # Validate capacity before constructing an admission boundary.
        validated = TypeAdapter(PositiveInt).validate_python(capacity, strict=True)
        self._slots = asyncio.BoundedSemaphore(validated)

    async def __aenter__(self) -> AsyncCapacityLimiter:
        # Admit this operation; cancelled waiting tasks never enter the protected scope.
        await self._slots.acquire()
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None) -> None:
        # Release the admitted operation's permit even when its body raises or cancels.
        self._slots.release()


__all__ = ["AsyncCapacityLimiter"]

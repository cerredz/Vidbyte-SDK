"""Live steering and interruption of one native Codex turn.

PURPOSE: Send actual native control requests with bounded lifecycle checks.
ROLE IN CODEBASE: The stream runner gives each configured callback one run handle.
ARCHITECTURE NOTE: Supplemental steering cannot replace Codex-owned model context.
COMMON MODIFICATION PATTERNS: Keep native acknowledgment and stale-handle tests together.
KNOWN EDGE CASES: Native completion may race a pending control request.
RELATED DOCS: docs/design/codex-live-control.md
TESTS: tests/codex_control/test_control.py
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol

from vidbyte.lib.dataclasses.codex import CodexControlSettings
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError
from vidbyte.lib.util.concurrency import AsyncCapacityLimiter

if TYPE_CHECKING:
    from openai_codex.generated.v2_all import TurnInterruptResponse, TurnSteerResponse


class CodexNativeControl(Protocol):
    """Public native operations used by both SDK transport paths."""

    async def steer(self, input: str) -> TurnSteerResponse: ...
    async def interrupt(self) -> TurnInterruptResponse: ...


class CodexRunControl:
    """An ephemeral capability for one native thread/turn, never a reusable agent handle."""

    def __init__(self, thread_id: str, turn_id: str, native: CodexNativeControl, timeout_seconds: float) -> None:
        # Retain native identity and serialize commands belonging to this turn.
        self.thread_id = thread_id
        self.turn_id = turn_id
        self._native = native
        self._timeout_seconds = timeout_seconds
        self._active = True
        self._capacity = AsyncCapacityLimiter()

    @property
    def active(self) -> bool:
        # Report whether the collector still owns this turn's control lifetime.
        return self._active

    async def ready(self, settings: CodexControlSettings) -> None:
        # @intent bounded-control-registration
        # Callback failure must abort collection rather than silently lose requested control.
        try:
            await asyncio.wait_for(settings.on_ready(self), timeout=settings.timeout_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise self.error("control_ready", exc) from exc

    async def steer(self, text: str) -> None:
        # @intent steer-only-the-bound-native-turn
        # Preserve feedback exactly and reject an acknowledgment for another turn.
        if not isinstance(text, str) or not text.strip():
            raise self.error("control_steer", ValueError("Steering requires nonblank text."))
        async with self._capacity:
            self.require_active()
            try:
                response = await asyncio.wait_for(self._native.steer(text), timeout=self._timeout_seconds)
                self.require_active()
                if response.turn_id != self.turn_id:
                    raise ValueError("Native steering acknowledged a different turn.")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise self.error("control_steer", exc) from exc

    async def interrupt(self) -> None:
        # @intent request-native-interruption
        # Native acknowledgment is a request receipt, not rollback of prior effects.
        async with self._capacity:
            self.require_active()
            try:
                await asyncio.wait_for(self._native.interrupt(), timeout=self._timeout_seconds)
                self.require_active()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise self.error("control_interrupt", exc) from exc

    def close(self) -> None:
        # Invalidate future commands and acknowledgments arriving after collection ends.
        self._active = False

    def require_active(self) -> None:
        # @intent never-retarget-stale-control
        # A completed turn's handle cannot silently steer its parent's next turn.
        if not self._active:
            raise self.error("control_inactive", ValueError("Native turn control is inactive."))

    @staticmethod
    def error(operation: str, error: BaseException) -> CodexAgentError:
        # Publish operation identity without feedback text or raw provider exceptions.
        return CodexAgentError("Codex live control failed; use the active turn's handle and inspect native status before retrying.", failure_code=FailureCode.CODEX_CONTROL_FAILED.value, operation=operation, error_type=type(error).__name__)


__all__ = ["CodexNativeControl", "CodexRunControl"]

"""Per-invocation capture of reviewed native Codex observations.

PURPOSE: Write a shared trajectory export before required successful publication.
ROLE IN CODEBASE: Created by the facade and attached to its existing observation stream.
ARCHITECTURE NOTE: The existing TrajectorySink owns persistence; no parallel Session store.
COMMON MODIFICATION PATTERNS: Keep failure receipts and one-write semantics explicit.
KNOWN EDGE CASES: A timed-out sink may already have written; no automatic retry is safe.
RELATED DOCS: docs/design/codex-trajectory-capture.md
TESTS: tests/codex_capture/test_capture.py
"""

from __future__ import annotations

import asyncio
import copy
from collections import deque
from dataclasses import replace
from typing import Any
from uuid import uuid4

from vidbyte.agents.codex.capture_format import CodexTrajectoryFormatter
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.constants.codex import CODEX_EVENT_SEQUENCE_STEP
from vidbyte.lib.dataclasses.codex import (
    CodexCaptureSettings,
    CodexHarnessAgentSettings,
    CodexObservation,
    CodexPrompt,
    CodexRunInput,
    CodexRunResult,
    CodexTrajectorySnapshot,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError


class CodexTrajectoryCapture:
    """One bounded native evidence window and one attempted export per invocation."""

    def __init__(self, settings: CodexCaptureSettings, agent: CodexHarnessAgentSettings, request: CodexRunInput) -> None:
        # @intent independent-consented-export
        # Establish an independent dataset identity and snapshot the initial user input.
        self.settings = settings
        self.formatter = CodexTrajectoryFormatter(settings, agent)
        self.run_id = uuid4().hex
        self.task: CodexRunInput | CodexPrompt = copy.deepcopy(request)
        self.candidate: AgentMessage | None = None
        self.native_result: CodexRunResult | None = None
        self.events: deque[CodexObservation] = deque(maxlen=settings.max_observations)
        self.event_count = 0
        self.attempted = False
        self.saved = False
        self.error_type = ""

    async def observe(self, event: CodexObservation) -> None:
        # Keep the reviewed snapshot isolated and make every discarded event count visible.
        self.events.append(copy.deepcopy(event))
        self.event_count += CODEX_EVENT_SEQUENCE_STEP

    def set_prompt(self, prompt: CodexPrompt) -> None:
        # Replace raw input with the actual translated native prompt when available.
        self.task = copy.deepcopy(prompt)

    def set_candidate(self, reply: AgentMessage) -> None:
        # Retain candidate evidence even if final application acceptance rejects it.
        self.candidate = copy.deepcopy(reply)

    def set_result(self, result: CodexRunResult) -> None:
        # Retain reviewed native output even if shared output-schema validation rejects it.
        self.native_result = copy.deepcopy(result)

    async def finish(self, reply: AgentMessage) -> AgentMessage:
        # @intent required-export-before-success
        # Lack of storage acknowledgment cannot produce a saved receipt or automatic retry.
        try:
            self.set_candidate(reply)
            await self.write("succeeded")
        except asyncio.CancelledError:
            self.error_type = "CancelledError"
            raise
        except Exception as exc:
            self.error_type = type(exc).__name__
            if self.settings.required:
                raise CodexAgentError("Codex trajectory export was not acknowledged; inspect the sink and run ID before retrying a potentially completed write.", failure_code=FailureCode.CODEX_CAPTURE_FAILED.value, operation="trajectory_capture", error_type=self.error_type) from exc
        return replace(reply, metadata={**dict(reply.metadata), "capture": self.receipt()})

    async def failed(self, error: BaseException) -> None:
        # @intent preserve-primary-run-failure
        # Diagnostic export is best effort and cannot replace the exception being unwound.
        status = "cancelled" if isinstance(error, asyncio.CancelledError) else "failed"
        try:
            await self.write(status, error_type=type(error).__name__)
        except asyncio.CancelledError:
            self.error_type = "CancelledError"
            raise
        except Exception as capture_error:
            self.error_type = type(capture_error).__name__

    async def write(self, status: str, *, error_type: str = "") -> None:
        # @intent exactly-one-export-attempt
        # A partial or timed-out sink write must never trigger a second record automatically.
        if self.attempted:
            raise RuntimeError("Codex capture already attempted its final write.")
        self.attempted = True
        snapshot = CodexTrajectorySnapshot(self.run_id, self.task, self.candidate, tuple(self.events), status, self.event_count, self.event_count - len(self.events), error_type, self.native_result)
        record = self.formatter.record(snapshot)
        await asyncio.wait_for(self.settings.sink.write(record), timeout=self.settings.timeout_seconds)
        self.saved = True

    def receipt(self) -> dict[str, Any]:
        # Return isolated storage acknowledgment and dataset-completeness diagnostics.
        return {"run_id": self.run_id, "saved": self.saved, "observed_event_count": self.event_count, "dropped_event_count": self.event_count - len(self.events), "error_type": self.error_type or None}


__all__ = ["CodexTrajectoryCapture"]

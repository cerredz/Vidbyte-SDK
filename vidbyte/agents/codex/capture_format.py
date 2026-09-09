"""Reviewed native trajectory projection and mandatory export redaction.

PURPOSE: Reuse Vidbyte's TrajectoryRecord without fabricating resumable model state.
ROLE IN CODEBASE: Called by the per-run capture bridge before its sink write.
ARCHITECTURE NOTE: Client environment and arbitrary process config are never projected.
COMMON MODIFICATION PATTERNS: Add fields only with scope and redaction acceptance cases.
KNOWN EDGE CASES: Common credential scrubbing is not exhaustive PII detection.
RELATED DOCS: docs/design/codex-trajectory-capture.md
TESTS: tests/codex_capture/test_capture.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any

from vidbyte.agents.codex.tool_wire import CodexToolWire
from vidbyte.harnesses.contracts import HARNESS_SCHEMA_VERSION, TrajectoryRecord
from vidbyte.harnesses.serialization import HarnessRedactor
from vidbyte.lib.dataclasses.codex import (
    CodexCaptureSettings,
    CodexHarnessAgentSettings,
    CodexTrajectorySnapshot,
)


class CodexTrajectoryFormatter:
    """Project only reviewed behavior and evidence into the existing dataset contract."""

    def __init__(self, settings: CodexCaptureSettings, agent: CodexHarnessAgentSettings) -> None:
        # Keep capture policy separate from the agent settings projected into export.
        self.settings = settings
        self.agent = agent
        self.baseline = HarnessRedactor()

    def record(self, snapshot: CodexTrajectorySnapshot) -> TrajectoryRecord:
        # @intent observed-native-data-not-fabricated-model-state
        # Label unavailable internals explicitly instead of inferring model iterations.
        native = snapshot.reply.codex if snapshot.reply else snapshot.native_result
        identity = native or (snapshot.observations[-1] if snapshot.observations else None)
        agent = {"agent_name": self.agent.name, "thread_id": identity.thread_id if identity else None, "turn_id": identity.turn_id if identity else None, "native_status": native.status if native else None, "observations": snapshot.observations, "trace_artifact": snapshot.reply.metadata.get("trace") if snapshot.reply else None, "capture_scope": "reviewed_native_events", "unavailable": ["internal_model_prompts", "hidden_reasoning", "full_native_context", "unreported_tool_deltas"], "observed_event_count": snapshot.observed_event_count, "dropped_event_count": snapshot.dropped_event_count, "error_type": snapshot.error_type}
        return TrajectoryRecord(schema_version=HARNESS_SCHEMA_VERSION, run_id=snapshot.run_id, task=self.redact(snapshot.task), spec=self.redact(self.specification()), agents=(self.redact(agent),), output=self.redact(snapshot.reply or snapshot.native_result), status=snapshot.status, reward=None, created_at=datetime.now(timezone.utc).isoformat())

    def specification(self) -> dict[str, Any]:
        # @intent exclude-native-process-secrets-by-construction
        # Export selected behavior settings without traversing env or arbitrary config.
        codex = self.agent.codex
        return {"agent_name": self.agent.name, "system_prompt": self.agent.system_prompt, "thread_model": codex.thread.model, "turn_model": codex.turn.model, "thread_sandbox": codex.thread.sandbox.value, "turn_sandbox": codex.turn.sandbox.value, "thread_approval": codex.thread.approval_mode.value, "turn_approval": codex.turn.approval_mode.value, "tools": CodexToolWire.declarations(self.agent.tool_bridge.tools) if self.agent.tool_bridge else [], "trace_schema": self.agent.continual_trace.schema if self.agent.continual_trace else None}

    def redact(self, value: Any) -> Any:
        # @intent mandatory-redaction-after-tenant-transformation
        # A custom callback cannot bypass baseline credential-key or text scrubbing.
        transformed = self.settings.redactor(value) if self.settings.redactor else value
        return self.scrub_text(self.baseline.redact(transformed))

    def scrub_text(self, value: Any) -> Any:
        # Scrub common credential assignments recursively without truncating task content.
        if isinstance(value, str):
            return self.baseline.safe_error_message(value, max_chars=sys.maxsize) if value.strip() else value
        if isinstance(value, list):
            return [self.scrub_text(item) for item in value]
        if isinstance(value, dict):
            return {key: self.scrub_text(item) for key, item in value.items()}
        return value


__all__ = ["CodexTrajectoryFormatter"]

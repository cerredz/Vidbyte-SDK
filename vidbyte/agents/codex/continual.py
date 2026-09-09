"""FILE: vidbyte/agents/codex/continual.py

PURPOSE: Generates schema-validated trace patches on deterministic item boundaries.
ROLE IN CODEBASE: CodexHarnessAgent creates one bridge per invocation.
ARCHITECTURE NOTE: Separate native turns produce JSON; UpdateTraceTool owns merges.
FUNCTION INVENTORY: update issues native JSON requests; observe schedules; finalize publishes.
COMMON MODIFICATION PATTERNS: Keep cadence and schema tests beside changes.
WHAT NOT TO DO: Inject artifacts into main context or reuse the main native thread.
KNOWN EDGE CASES: Read-only sandbox does not constrain external configured tools.
RELATED DOCS: docs/design/codex-continual-artifacts.md
TESTS: tests/codex_continual/test_continual.py
"""

from __future__ import annotations

import asyncio
import copy
import json
from collections import deque
from dataclasses import asdict, replace
from typing import Any

from vidbyte.agents.codex.transport import CodexTransport
from vidbyte.lib.constants.codex import CODEX_EVENT_SEQUENCE_STEP
from vidbyte.lib.dataclasses.codex import (
    CodexAgentSettings,
    CodexContinualTraceSettings,
    CodexObservation,
    CodexPrompt,
    CodexSubagentSettings,
    CodexTextInput,
    CodexTraceUpdateRequest,
    CodexTransportRunRequest,
)
from vidbyte.lib.enums.codex import CodexApprovalMode, CodexEventMethod, CodexSandbox
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.continual_trace import UPDATE_TRACE_TOOL_NAME, UpdateTraceTool
from vidbyte.tools.types import ToolCall, ToolStatus


class CodexTraceUpdater:
    """Uses native authentication and schema-constrained output for one trace patch."""

    async def update(self, request: CodexTraceUpdateRequest) -> dict[str, Any]:
        # @intent native-trace-update-boundary
        # A separate thread avoids recursive observation and main-context pollution.
        tool = UpdateTraceTool(request.schema)
        native = self.native_settings(request.settings)
        text = json.dumps({"previous_trace": request.artifact, "observations": [asdict(item) for item in request.observations]})
        prompt = CodexPrompt((CodexTextInput(text),), text, "user", {})
        result = await CodexTransport().run(CodexTransportRunRequest("", Prompts().get(Prompt.CODEX_CONTINUAL_TRACE_SYSTEM_PROMPT), prompt, native, tool.spec().input_schema or {}))
        if result.status != "completed" or result.final_response is None:
            raise ValueError("Codex trace updater did not complete.")
        payload = json.loads(result.final_response)
        if not isinstance(payload, dict) or not isinstance(payload.get("trace"), dict):
            raise ValueError("Codex trace update must return a trace object.")
        return payload["trace"]

    @staticmethod
    def native_settings(settings: CodexAgentSettings) -> CodexAgentSettings:
        # @intent constrain-native-trace-work
        # Preserve credentials/model while disallowing native filesystem mutations and approvals.
        thread = replace(settings.thread, sandbox=CodexSandbox.READ_ONLY, approval_mode=CodexApprovalMode.DENY_ALL, ephemeral=True)
        turn = replace(settings.turn, sandbox=CodexSandbox.READ_ONLY, approval_mode=CodexApprovalMode.DENY_ALL)
        return replace(settings, thread=thread, turn=turn, subagents=CodexSubagentSettings(enabled=False))


class CodexContinualTraceBridge:
    """Per-run scheduler with a bounded evidence window and fail-open update diagnostics."""

    def __init__(self, config: CodexContinualTraceSettings, settings: CodexAgentSettings) -> None:
        # Seed a fresh artifact; duplicate tracking is linear in unique completed items.
        self.config = config
        self.settings = settings
        self.tool = UpdateTraceTool(config.schema)
        self.updater = CodexTraceUpdater()
        self.window: deque[CodexObservation] = deque(maxlen=config.max_observations)
        self.seen: set[str] = set()
        self.update_count = 0
        self.error_count = 0
        self.last_error: str | None = None
        self.last_updated_count = -1
        self.truncated_count = 0
        self.finalized = False

    async def observe(self, event: CodexObservation) -> None:
        # @intent completed-item-cadence
        # Duplicate completion notifications must not charge for an extra update.
        if event.method != CodexEventMethod.ITEM_COMPLETED or event.item is None or event.item.id in self.seen:
            return
        self.seen.add(event.item.id)
        if len(self.window) == self.config.max_observations:
            self.truncated_count += CODEX_EVENT_SEQUENCE_STEP
        self.window.append(copy.deepcopy(event))
        if len(self.seen) % self.config.every_n_completed_items == 0:
            await self.update()

    async def update(self) -> None:
        # @intent fail-open-trace-artifact
        # Apply only accepted patches; cancellation must still unwind the main run.
        request = CodexTraceUpdateRequest(self.settings, self.config.schema, copy.deepcopy(self.tool.current_trace()), tuple(self.window))
        for _ in range(self.config.max_update_attempts):
            try:
                patch = await asyncio.wait_for(self.updater.update(request), timeout=self.config.timeout_seconds)
                result = await self.tool.execute(ToolCall(UPDATE_TRACE_TOOL_NAME, {"trace": patch}))
                if result.status != ToolStatus.SUCCESS:
                    raise ValueError("Codex trace patch violated its schema.")
            except Exception as exc:
                self.error_count += CODEX_EVENT_SEQUENCE_STEP
                self.last_error = type(exc).__name__
                continue
            self.update_count += CODEX_EVENT_SEQUENCE_STEP
            self.last_updated_count = len(self.seen)
            self.last_error = None
            return

    async def finalize(self) -> None:
        # Avoid a duplicate final model call when this item boundary was already updated.
        if not self.finalized:
            if self.last_updated_count != len(self.seen):
                await self.update()
            self.finalized = True

    def artifact(self) -> dict[str, Any]:
        # Give callers an isolated artifact rather than the merger's mutable backing data.
        return copy.deepcopy(self.tool.current_trace())

    def metadata(self) -> dict[str, Any]:
        # Report actual cadence and truncation without publishing native error contents.
        return {"mode": "continual", "schema": self.config.schema.name, "boundary": "completed_items", "completed_item_count": len(self.seen), "update_count": self.update_count, "error_count": self.error_count, "last_error": self.last_error, "truncated_observation_count": self.truncated_count, "final_update_complete": self.finalized and self.last_updated_count == len(self.seen)}


__all__ = ["CodexContinualTraceBridge", "CodexTraceUpdater"]

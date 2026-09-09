"""Final application acceptance for native Codex candidates.

PURPOSE: Require configured artifacts and checks before successful publication.
ROLE IN CODEBASE: CodexHarnessAgent invokes the gate before committing reply history.
ARCHITECTURE NOTE: This gate cannot undo native effects; it controls Vidbyte success.
COMMON MODIFICATION PATTERNS: Validate actual producer state, never user metadata claims.
KNOWN EDGE CASES: Earlier trace success does not establish final-boundary freshness.
RELATED DOCS: docs/design/codex-final-acceptance.md
TESTS: tests/codex_acceptance/test_acceptance.py
"""

from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import replace

from vidbyte.agents.types import AgentMessage
from vidbyte.lib.dataclasses.codex import (
    CodexAcceptanceRequest,
    CodexAcceptanceSettings,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError
from vidbyte.providers.output_schema import OutputSchemaFormatter


class CodexAcceptanceGate:
    """Fail closed on required native status, trace freshness, schema, and callbacks."""

    def __init__(self, settings: CodexAcceptanceSettings) -> None:
        # Retain one immutable policy for this candidate's final acceptance.
        self.settings = settings

    async def accept(self, request: CodexAcceptanceRequest) -> AgentMessage:
        # @intent application-success-after-evidence
        # Model completion alone cannot satisfy missing artifacts or failed checks.
        try:
            self.validate_candidate(request)
            await self.run_checks(request)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            native = request.reply.codex
            error = CodexAgentError("Codex candidate failed final acceptance; inspect required artifacts and application checks before retrying native work.", failure_code=FailureCode.CODEX_ACCEPTANCE_FAILED.value, operation="final_acceptance", error_type=type(exc).__name__)
            error.safe_runtime_details.update(thread_id=native.thread_id if native else "", turn_id=native.turn_id if native else "")
            raise error from exc
        receipt = {"accepted": True, "check_count": len(self.settings.checks)}
        return replace(request.reply, metadata={**dict(request.reply.metadata), "acceptance": receipt})

    def validate_candidate(self, request: CodexAcceptanceRequest) -> None:
        # @intent require-current-final-artifact
        # A stale trace from an earlier successful patch must not satisfy this gate.
        native = request.reply.codex
        if self.settings.require_completed and (native is None or native.status != "completed"):
            raise ValueError("Native turn did not complete.")
        if self.settings.require_trace or self.settings.trace_schema is not None:
            if not request.trace or request.trace_metadata.get("final_update_complete") is not True:
                raise ValueError("Required final trace is missing or stale.")
        if self.settings.trace_schema is not None:
            _, error = OutputSchemaFormatter().validate(json.dumps(request.trace, allow_nan=False), self.settings.trace_schema)
            if error is not None:
                raise ValueError("Final trace does not satisfy its acceptance schema.")

    async def run_checks(self, request: CodexAcceptanceRequest) -> None:
        # @intent checks-cannot-forge-other-check-evidence
        # Each check receives an isolated candidate and must explicitly accept it.
        for check in self.settings.checks:
            accepted = await asyncio.wait_for(check(copy.deepcopy(request)), timeout=self.settings.timeout_seconds)
            if accepted is not True:
                raise ValueError("Application acceptance check did not return True.")


__all__ = ["CodexAcceptanceGate"]

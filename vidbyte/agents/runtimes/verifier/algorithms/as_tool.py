"""Context Protocol Header

Description:
    Defines the verifier-as-tool algorithm mode and its bound tool.
Purpose:
    Lets the model request verification through the normal SDK tool catalog
    while reusing the shared verifier kernel and optional finalization check.
Architecture note:
    - VerifierAsToolMode: contributes one bound VerifierTool and enforces its
      call ceiling / required-finalization policy.
    - VerifierTool: translates a model tool call into a verifier checkpoint.
Relations:
    Uses vidbyte.tools.base.BaseTool and vidbyte.tools.types.ToolSpec /
    ToolResult, so AgentRuntime needs no special tool-execution branch.
Role in codebase:
    Adapts the verifier checkpoint kernel to the model-callable tool boundary.
Common modification patterns:
    Change call limits or tool schema through VerifierAsToolModeParams.
Known edge cases:
    A tool call can be rejected by the mode budget before verification runs.
Related docs:
    docs/design/verifier-runtime-algorithms.md
Tests:
    Covered by verifier runtime tool import and execution tests.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from vidbyte.agents.runtimes.verifier.algorithms.base import VerifierRuntimeMode
from vidbyte.lib.dataclasses.verifier import ResolutionContext, VerifierAsToolModeParams, VerifierRuntimeModeKind, VerifierRuntimeOutcome
from vidbyte.agents.runtimes.verifier.types import GateDecision
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.verifier.runtime import AgentVerifierRuntime


class VerifierAsToolMode(VerifierRuntimeMode):
    """Exposes the configured verifier as a model-callable tool."""

    kind = VerifierRuntimeModeKind.AS_TOOL

    def __init__(self, params: VerifierAsToolModeParams | None = None) -> None:
        # Stores validated tool-mode settings for this runtime.
        self.params = params or VerifierAsToolModeParams()

    def tools(self, runtime: AgentVerifierRuntime) -> tuple[BaseTool, ...]:
        # Contributes one tool bound to this run's verifier runtime.
        return (VerifierTool(runtime, self.params),)

    # @intent tool-finalization
    async def on_finalization(self, runtime: AgentVerifierRuntime, context: ResolutionContext) -> VerifierRuntimeOutcome:
        # Requires a successful tool result when configured, otherwise leaves finalization advisory.
        if not self.params.required_before_finalization or runtime.last_tool_passed:
            return VerifierRuntimeOutcome(GateDecision.ALLOW_FINALIZE, None, None)
        return await runtime.evaluate_checkpoint(context)


class VerifierTool(BaseTool):
    """Adapts one AgentVerifierRuntime to the SDK's model-facing tool contract."""

    def __init__(self, runtime: AgentVerifierRuntime, params: VerifierAsToolModeParams) -> None:
        # Retains the owning verifier runtime and its validated tool settings.
        self.runtime = runtime
        self.params = params

    def spec(self) -> ToolSpec:
        # Returns the provider-facing schema for a candidate verification request.
        return ToolSpec(
            name=self.params.tool_name,
            description="Run the configured mechanical verifiers against the current candidate output and return diagnostics.",
            parameters=(
                ToolParameter(name="candidate_output", type="string", description="Candidate text to verify.", required=False),
            ),
            input_schema={
                "type": "object",
                "properties": {"candidate_output": {"type": "string", "description": "Candidate text to verify."}},
                "additionalProperties": False,
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Executes one verifier checkpoint and renders its decision as JSON tool output.
        if not self.runtime.allow_tool_call():
            return ToolResult.failure(self.name, f"Verifier tool call limit reached for '{self.name}'.")
        candidate = call.arguments.get("candidate_output")
        outcome = await self.runtime.evaluate_tool(str(candidate) if candidate is not None else "")
        payload = {
            "decision": outcome.decision.value,
            "passed": outcome.decision is GateDecision.ALLOW_FINALIZE,
            "feedback": outcome.feedback,
        }
        return ToolResult.success(self.name, json.dumps(payload))


__all__ = ["VerifierAsToolMode", "VerifierTool"]

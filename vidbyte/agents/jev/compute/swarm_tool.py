"""FILE: vidbyte/agents/jev/compute/swarm_tool.py

PURPOSE: Implements launch_swarm, the internal tool the main agent receives after Jev selects SWARM: it reads and checks the submitted plan, runs one helper per assignment, records the launch, and returns the results.
ROLE IN CODEBASE: JevComputeController arms one instance per run on a SWARM selection, and JevRuntime adds it to that run's catalog after the checkpoint; the next run's runtime starts from the agent's own catalog without it.
ARCHITECTURE NOTE: The tool is internal, so the runtime gives it no timeout, no tool-settings limits, and no result compaction; helper output is bounded by clipping in JevSwarmAgent.results instead.
COMMON MODIFICATION PATTERNS: Keep model-facing text in vidbyte/prompts/prompts/jev_swarm/jev_swarm.json and plan rules in swarm_plan.py; keep this module to the launch sequence and the attempt budget.
KNOWN EDGE CASES: A rejected plan costs one of JEV_SWARM_PLAN_MAX_ATTEMPTS attempts, and the last rejection closes the tool. After one launch or that last rejection, every call returns the closed message. The runtime awaits a turn's tool calls in order, and the tool closes before its helpers start, so a second call in the same turn cannot launch again.
RELATED DOCS: docs/design/jev-compute-swarm.md.
TESTS: tests/test_jev_compute_swarm.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from vidbyte.agents.jev.brief import JevRunBriefKeeper
from vidbyte.agents.jev.compute.swarm import JevSwarmAgent
from vidbyte.agents.jev.compute.swarm_plan import JevSwarmPlanCheck, JevSwarmPlanReader
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import (
    JEV_COMPUTE_SWARM_AGENTS_MIN,
    JEV_SWARM_PLAN_MAX_ATTEMPTS,
    JEV_SWARM_TOOL_NAME,
)
from vidbyte.lib.dataclasses.jev import JevSwarmResult
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)

_FIELD_DESCRIPTIONS: Mapping[str, Prompt] = MappingProxyType(
    {
        "name": Prompt.JEV_SWARM_NAME_DESCRIPTION,
        "objective": Prompt.JEV_SWARM_OBJECTIVE_DESCRIPTION,
        "inputs": Prompt.JEV_SWARM_INPUTS_DESCRIPTION,
        "deliverable": Prompt.JEV_SWARM_DELIVERABLE_DESCRIPTION,
        "boundaries": Prompt.JEV_SWARM_BOUNDARIES_DESCRIPTION,
        "verification": Prompt.JEV_SWARM_VERIFICATION_DESCRIPTION,
    }
)
_NO_ATTEMPTS_LEFT = 0
_ATTEMPTS_PER_PLAN = 1


class JevSwarmTool(BaseTool):
    """The one-time launch_swarm tool: check the main agent's plan, run its helpers, and return their results."""

    def __init__(self, settings: JevAgentSettings, decision: DecisionModelConfig, response: JevResponse, keeper: JevRunBriefKeeper, iteration: int, limit: int) -> None:
        self.settings = settings
        self.check = JevSwarmPlanCheck(decision)
        self.response = response
        self.keeper = keeper
        self.iteration = iteration
        self.limit = limit
        self.attempts = 0
        self.closed = False

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration, with the assignment count bounded by this run's swarm size."""
        prompts = Prompts()
        conventions = prompts.get(Prompt.JEV_SWARM_CONVENTIONS_DESCRIPTION)
        assignments = prompts.get(Prompt.JEV_SWARM_ASSIGNMENTS_DESCRIPTION)
        return ToolSpec(
            name=JEV_SWARM_TOOL_NAME,
            description=prompts.get(Prompt.JEV_SWARM_TOOL_DESCRIPTION),
            parameters=(
                ToolParameter(name="conventions", type="string", description=conventions, required=True),
                ToolParameter(name="assignments", type="array", description=assignments, required=True),
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "conventions": {"type": "string", "description": conventions},
                    "assignments": {
                        "type": "array",
                        "description": assignments,
                        "minItems": JEV_COMPUTE_SWARM_AGENTS_MIN,
                        "maxItems": self.limit,
                        "items": {
                            "type": "object",
                            "properties": {field: {"type": "string", "description": prompts.get(_FIELD_DESCRIPTIONS[field])} for field in JevSwarmPlanReader.FIELDS},
                            "required": list(JevSwarmPlanReader.FIELDS),
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["conventions", "assignments"],
                "additionalProperties": False,
            },
            permission=ToolPermission.SAFE,
            metadata={"internal": True},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Read and check the submitted plan, launch its helpers once it passes, and return their results or what to fix."""
        # @intent the-swarm-launches-at-most-once-per-run
        # Each launch multiplies the run's cost, so the tool closes before its helpers start and after its last rejected plan.
        brief = self.keeper.brief
        if self.closed or brief is None:
            return ToolResult.error(JEV_SWARM_TOOL_NAME, Prompts().get(Prompt.JEV_SWARM_CLOSED_PROMPT))
        self.attempts += _ATTEMPTS_PER_PLAN
        try:
            plan = JevSwarmPlanReader.read(call.arguments, self.limit)
        except ConfigurationError as exc:
            return self._reject((str(exc),))
        gaps = await self.check.review(self.keeper.request, brief, plan)
        if gaps:
            return self._reject(gaps)
        self.closed = True
        outputs = await JevSwarmAgent.attempt(self.settings, self.keeper.request, brief, plan)
        self.response.swarm(JevSwarmResult(iteration=self.iteration, plan=plan, outputs=outputs, attempts=self.attempts))
        return ToolResult.success(JEV_SWARM_TOOL_NAME, JevSwarmAgent.results(outputs), metadata={"attempts": self.attempts})

    def _reject(self, reasons: Iterable[str]) -> ToolResult:
        # Returns every problem with the plan and either the remaining attempts or the closed message.
        prompts = Prompts()
        remaining = JEV_SWARM_PLAN_MAX_ATTEMPTS - self.attempts
        if remaining <= _NO_ATTEMPTS_LEFT:
            self.closed = True
            next_step = prompts.get(Prompt.JEV_SWARM_CLOSED_PROMPT)
        else:
            next_step = prompts.get(Prompt.JEV_SWARM_RETRY_PROMPT).format(remaining=remaining)
        listed = "\n".join(f"- {reason}" for reason in reasons)
        output = prompts.get(Prompt.JEV_SWARM_REJECTED_PROMPT).format(reasons=listed, next_step=next_step)
        return ToolResult.error(JEV_SWARM_TOOL_NAME, output, metadata={"attempts": self.attempts})


__all__ = ["JevSwarmTool"]

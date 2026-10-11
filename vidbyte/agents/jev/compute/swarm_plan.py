"""FILE: vidbyte/agents/jev/compute/swarm_plan.py

PURPOSE: Reads the launch_swarm tool's arguments into a validated JevSwarmPlan and asks Jev whether every assignment is self-contained, disjoint, in scope, and checkable.
ROLE IN CODEBASE: JevSwarmTool reads each submitted plan here, then reviews it here before any helper starts; the gaps it returns become the rejection the main agent fixes.
ARCHITECTURE NOTE: Plan question content lives in vidbyte/lib/jev/compute/plan.py; this module only builds the shared state, sends one Jev request, and maps failed answers to gap text.
COMMON MODIFICATION PATTERNS: Add an assignment field to FIELDS, JevSwarmAssignment, and the assignment prompt together; add a plan question in plan.py instead of a code-side rule here.
KNOWN EDGE CASES: Malformed arguments raise ConfigurationError with a message the main agent can act on. An unavailable Jev, or an answer that cannot be scored, passes the plan, because the check only improves a team Jev already chose.
RELATED DOCS: docs/design/jev-compute-swarm.md.
TESTS: tests/test_jev_compute_swarm.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.agents.jev.compute.states import JevComputeStates
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import (
    JEV_COMPUTE_SWARM_AGENTS_MIN,
    JEV_RUN_BRIEF_REQUEST_MAX_CHARS,
    JEV_SWARM_ASSIGNMENT_ID_PREFIX,
    JEV_SWARM_FIRST_ASSIGNMENT,
    JEV_SWARM_PLAN_MIN_THRESHOLD,
)
from vidbyte.lib.dataclasses.jev import (
    JevDecisionRequest,
    JevRunBrief,
    JevSwarmAssignment,
    JevSwarmPlan,
)
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.jev.compute import JevSwarmPlanRegistry
from vidbyte.lib.jev.decision import DecisionModelHelper


class JevSwarmPlanReader:
    """Turn the launch tool's raw arguments into a JevSwarmPlan whose assignment ids follow plan order."""

    FIELDS: tuple[str, ...] = ("name", "objective", "inputs", "deliverable", "boundaries", "verification")

    @classmethod
    def read(cls, arguments: Mapping[str, Any], limit: int) -> JevSwarmPlan:
        """Return the validated plan, or raise ConfigurationError naming what the main agent must fix."""
        # @intent ids-come-from-code-not-the-model
        # Results are matched to assignments by id, so code numbers assignments by position instead of trusting model ids.
        conventions = arguments.get("conventions")
        if not isinstance(conventions, str) or not conventions.strip():
            raise ConfigurationError("conventions must be non-blank text stating the decisions every helper shares.")
        raw = arguments.get("assignments")
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise ConfigurationError("assignments must be a list of assignment objects.")
        if not JEV_COMPUTE_SWARM_AGENTS_MIN <= len(raw) <= limit:
            raise ConfigurationError(f"assignments must hold from {JEV_COMPUTE_SWARM_AGENTS_MIN} through {limit} assignments; received {len(raw)}.")
        assignments = tuple(cls._assignment(position, entry) for position, entry in enumerate(raw, start=JEV_SWARM_FIRST_ASSIGNMENT))
        return JevSwarmPlan(conventions=conventions.strip(), assignments=assignments)

    @classmethod
    def _assignment(cls, position: int, entry: object) -> JevSwarmAssignment:
        # Validates one raw assignment object and gives it the id for its position in the plan.
        if not isinstance(entry, Mapping):
            raise ConfigurationError(f"Assignment {position} must be an object with the fields {', '.join(cls.FIELDS)}.")
        missing = tuple(field for field in cls.FIELDS if not isinstance(entry.get(field), str) or not entry[field].strip())
        if missing:
            raise ConfigurationError(f"Assignment {position} needs non-blank text for: {', '.join(missing)}.")
        return JevSwarmAssignment(id=f"{JEV_SWARM_ASSIGNMENT_ID_PREFIX}{position}", **{field: entry[field].strip() for field in cls.FIELDS})


class JevSwarmPlanCheck:
    """Ask Jev once whether every assignment of a plan is self-contained, disjoint, in scope, and checkable."""

    def __init__(self, decision: DecisionModelConfig) -> None:
        self.decision = decision

    async def review(self, request: str, brief: JevRunBrief, plan: JevSwarmPlan) -> tuple[str, ...]:
        """Return one gap line for every failed assignment question, or nothing when the plan passes or Jev is unavailable."""
        # @intent an-unavailable-check-never-blocks-the-swarm
        # The check refines a team Jev already selected, so an outage or an unscorable answer passes the plan rather than costing the run its swarm.
        state = {
            "request": JevComputeStates.clip(request, JEV_RUN_BRIEF_REQUEST_MAX_CHARS),
            "brief": brief.render(),
            "conventions": plan.conventions,
            "assignments": {assignment.id: {field: getattr(assignment, field) for field in JevSwarmPlanReader.FIELDS} for assignment in plan.assignments},
        }
        questions = JevSwarmPlanRegistry.questions(assignment.id for assignment in plan.assignments)
        try:
            decision = await DecisionModelHelper(self.decision).arun(JevDecisionRequest(state=state, questions=questions))
        except VidbyteSdkError:
            return ()
        gaps: list[str] = []
        for assignment in plan.assignments:
            for key in JevSwarmPlanRegistry.question_keys():
                question = JevSwarmPlanRegistry.get(key)
                if DecisionModelHelper.noul_passes(decision.answers, question.name(assignment.id), JEV_SWARM_PLAN_MIN_THRESHOLD) is False:
                    gaps.append(f"{assignment.id} ({assignment.name}): {question.gap}")
        return tuple(gaps)


__all__ = ["JevSwarmPlanCheck", "JevSwarmPlanReader"]

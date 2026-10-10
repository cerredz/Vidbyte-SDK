"""FILE: vidbyte/agents/jev/bulk_work.py

PURPOSE: Implements BULK_WORK's run_bulk_work tool and its JevBulkWorker pipeline stages: the main agent writes the tasks as the tool's arguments, one fresh copy of the main agent runs each task, all of them run at once through ParallelPipeline, and their handoffs come back to the main agent as the tool result.
ROLE IN CODEBASE: JevAgent builds the per-run constructor from JevBulkWorkTool.for_agent when BULK_WORK is enabled; JevRuntime adds one tool to the main agent's catalog for a run whose preflight gate approved bulk work, and the tool records its launch through JevResponse.
ARCHITECTURE NOTE: Each JevBulkWorker is a BasePipeline stage that wraps one BaseAgent, so ParallelPipeline runs the team and joins the handoffs in task order. A worker gets the main agent's model, prompt, permission policy, and loop limits, and only the tools the selector kept for this run; its usage reaches the run's ledger through BaseAgent.generate_reply.
COMMON MODIFICATION PATTERNS: Keep model-facing text in vidbyte/prompts/prompts/jev_bulk_work/, settings in JevBulkSettings, and the decision to offer the tool in JevPreflightGate; keep this module to the launch.
KNOWN EDGE CASES: Invalid tasks are rejected with what to fix and leave the tool open; after one launch every call returns the closed message. The tool closes before its workers start, so a second call in the same turn cannot launch them again. A worker that raises VidbyteSdkError or returns an empty reply is marked failed while the others still hand back their work.
RELATED DOCS: docs/design/jev-bulk-work.md and docs/design/jev-compute-swarm.md.
TESTS: tests/features/jev_bulk_work/test_jev_bulk_work.py and scripts/test-jev-bulk-work.py.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.fork import AgentForker
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.lib.constants.jev import JEV_BULK_WORK_MIN_AGENTS, JEV_BULK_WORK_TOOL_NAME
from vidbyte.lib.dataclasses.jev import JevBulkHandoff, JevBulkWorkResult
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.pipelines.base import BasePipeline
from vidbyte.pipelines.parallel import ParallelPipeline
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.base import BaseTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)


class JevBulkWorker(BasePipeline):
    """One pipeline stage: a fresh copy of the main agent that carries out one bulk-work task and returns its handoff."""

    def __init__(self, settings: JevAgentSettings, tools: tuple[object, ...], number: int, task: str) -> None:
        # @intent workers-keep-the-main-agent-limits
        # A worker must never do more than the main agent could, so it gets the same model, permissions, and loop
        # limits, and only the tools the selector kept; agent-bound tools are cloned so they stay bound to the main agent.
        self.number = number
        self.task = task
        self.handoff: JevBulkHandoff | None = None
        self.agent = BaseAgent(
            name=f"{settings.name}-bulk-{number}",
            system_prompt=f"{settings.system_prompt}\n\n{Prompts().get(Prompt.JEV_BULK_WORK_WORKER_SYSTEM_PROMPT)}",
            provider=settings.provider,
            model_name=settings.model_name,
            api_key=settings.api_key,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
            tools=tuple(AgentForker._clone_tool(tool, None, None) for tool in tools),
            permission_policy=settings.permission_policy,
            agent_loop_settings=settings.loop,
        )

    async def run(self, prompt: str) -> str:
        """Carry out this worker's task with the user's original request as background, and return its handoff section."""
        # @intent one-failed-worker-does-not-stop-the-others
        # Tasks are independent, so a provider failure in one worker is reported as that task failing rather than
        # raised through ParallelPipeline, which would drop every other worker's finished handoff.
        message = Prompts().get(Prompt.JEV_BULK_WORK_TASK_PROMPT).format(request=prompt, task=self.task)
        try:
            reply = await self.agent.arun(message)
        except VidbyteSdkError:
            output = ""
        else:
            output = reply.content.strip()
        self.handoff = JevBulkHandoff(task=self.task, output=output, completed=bool(output))
        if not output:
            return f"## Task {self.number} (failed)\n\n{self.task}"
        return f"## Task {self.number} (completed)\n\n{self.task}\n\n### Handoff\n\n{output}"


class JevBulkWorkTool(BaseTool):
    """The one-time run_bulk_work tool: run the main agent's tasks on fresh agents at once and hand their results back."""

    def __init__(self, settings: JevAgentSettings, response: JevResponse, request: str, tools: tuple[object, ...]) -> None:
        self.settings = settings
        self.response = response
        self.request = request
        self.tools = tools
        self.closed = False

    @classmethod
    def for_agent(cls, settings: JevAgentSettings, response: JevResponse) -> Callable[[str, tuple[object, ...]], JevBulkWorkTool]:
        """Return the per-run constructor JevRuntime calls with the request and the selected tools."""
        # @intent the-bulk-tool-never-collides-with-a-caller-tool
        # The tool joins the catalog at run time, so a name clash must fail when JevAgent is built, not in the middle of a run.
        if JEV_BULK_WORK_TOOL_NAME in Tools(settings.tools):
            raise ConfigurationError(f"JevAgentSettings.tools already has a tool named {JEV_BULK_WORK_TOOL_NAME!r}, which the BULK_WORK preset reserves; rename that tool or remove BULK_WORK from preflight.")
        return partial(cls, settings, response)

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration, with the task count bounded by the configured number of agents."""
        prompts = Prompts()
        agents = self.settings.bulk_work.agents
        tasks = prompts.get(Prompt.JEV_BULK_WORK_TASKS_DESCRIPTION).format(min_agents=JEV_BULK_WORK_MIN_AGENTS, agents=agents)
        return ToolSpec(
            name=JEV_BULK_WORK_TOOL_NAME,
            description=prompts.get(Prompt.JEV_BULK_WORK_TOOL_DESCRIPTION).format(min_agents=JEV_BULK_WORK_MIN_AGENTS, agents=agents),
            parameters=(ToolParameter(name="tasks", type="array", description=tasks, required=True),),
            input_schema={
                "type": "object",
                "properties": {"tasks": {"type": "array", "description": tasks, "minItems": JEV_BULK_WORK_MIN_AGENTS, "maxItems": agents, "items": {"type": "string"}}},
                "required": ["tasks"],
                "additionalProperties": False,
            },
            permission=ToolPermission.SAFE,
            metadata={"internal": True},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Check the tasks, run one fresh agent per task at the same time, record the launch, and return every handoff."""
        prompts = Prompts()
        # The agents run once per request, because every launch multiplies what the run costs.
        if self.closed:
            return ToolResult.error(JEV_BULK_WORK_TOOL_NAME, prompts.get(Prompt.JEV_BULK_WORK_CLOSED_PROMPT))
        # Send tasks the agents cannot run back to the main agent with what to fix, keeping the tool open.
        try:
            tasks = self._tasks(call.arguments.get("tasks"))
        except ConfigurationError as exc:
            return ToolResult.error(JEV_BULK_WORK_TOOL_NAME, prompts.get(Prompt.JEV_BULK_WORK_REJECTED_PROMPT).format(problem=exc.message))
        # Close the tool before the agents start, so a second call in the same turn cannot launch them again.
        self.closed = True
        workers = tuple(JevBulkWorker(self.settings, self.tools, number, task) for number, task in enumerate(tasks, start=1))
        # Run every worker at the same time; each one gets the user's original request as background for its task.
        handoffs = await ParallelPipeline(workers).run(self.request)
        # Record what each worker handed back, then return the handoffs so the main agent can check them and answer.
        self.response.bulk_work(JevBulkWorkResult(handoffs=tuple(worker.handoff for worker in workers if worker.handoff is not None)))
        return ToolResult.success(JEV_BULK_WORK_TOOL_NAME, prompts.get(Prompt.JEV_BULK_WORK_SYNTHESIS_PROMPT).format(handoffs=handoffs))

    def _tasks(self, tasks: object) -> tuple[str, ...]:
        # Returns the submitted tasks, trimmed, or raises ConfigurationError naming what the main agent must fix.
        agents = self.settings.bulk_work.agents
        if not isinstance(tasks, list) or not all(isinstance(task, str) and task.strip() for task in tasks):
            raise ConfigurationError("tasks must be a list of non-blank task instructions.")
        if not JEV_BULK_WORK_MIN_AGENTS <= len(tasks) <= agents:
            raise ConfigurationError(f"tasks must hold from {JEV_BULK_WORK_MIN_AGENTS} through {agents} tasks; received {len(tasks)}.")
        return tuple(task.strip() for task in tasks)


__all__ = ["JevBulkWorkTool", "JevBulkWorker"]

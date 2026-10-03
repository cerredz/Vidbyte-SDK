"""FILE: vidbyte/agents/jev/bulk_work.py

PURPOSE: Implements JevBulkWork, the bounded, tool-free structured planner and per-item BaseAgent coordinator. It validates a complete plan before any work starts, preserves ordered success/failure records, and never constructs or recursively invokes JevAgent.
ROLE IN CODEBASE: JevAgent builds one coordinator from JevAgentSettings; JevRuntime calls it only after bulk preflight approval and normal tool selection. The coordinator calls BaseAgent for planning and fresh workers, clones selected tools through `AgentForker._clone_tool`'s `clone_for_fork()` contract, and returns records from `vidbyte/lib/dataclasses/jev.py` for JevResponse and final context synthesis.
ARCHITECTURE NOTE: The coordinator subclasses BaseAgent so its planner owns its own raw usage tracker, but disables implicit internal tools and is never given user tools. Bounded `asyncio.Queue` workers each own one fresh BaseAgent history; the fixed worker count bounds concurrency, while result slots preserve request order.
FUNCTION INVENTORY: `JevBulkWork.__init__(settings)` builds the structured planner and resource caps; `plan_and_run(message, context, tools, *, claude_skills=())` validates a generated plan and returns a typed attempt record; `result_artifact(result)` creates untrusted synthesis context for a valid plan. Private helpers validate plans, build isolated workers and prompts, consume the bounded queue, and render outcomes. Feature contracts live in `tests/features/jev_bulk_work/test_jev_bulk_work.py`; the executable verification is `scripts/test-jev-bulk-work.py`.
COMMON MODIFICATION PATTERNS: Keep planner schema and public outcomes in `vidbyte/lib/dataclasses/jev.py`, settings in `vidbyte/agents/jev/settings.py`, gate decisions in `vidbyte/agents/jev/gate/gate.py`, and runtime ordering in `vidbyte/agents/jev/runtime.py`. Preserve whole-plan rejection, worker ordering, selected tool names, owner permission policy, raw child usage, and cancellation cleanup together.
WHAT NOT TO DO IN THIS FILE: 1. Do not call Jev or perform fixed question scoring; `JevPreflightGate` owns that boundary. 2. Do not choose which user tools are allowed; consume only the runtime's already selected catalog. 3. Do not truncate a plan or start workers before validating the whole plan. 4. Do not flatten or re-record worker usage in the planner or owner's tracker. 5. Do not expose exception messages, secrets, or raw repr values in public failure records.
KNOWN EDGE CASES: A rejected plan still reports planner usage and a safe failure code but creates no workers. A successful plan can contain failed items; those failures remain explicit and the final agent must not describe them as completed. Mutable custom tools without `clone_for_fork()` retain the existing fork contract's identity behavior.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/jev-bulk-work.md and https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-fork-isolation.md.
TESTS: `tests/features/jev_bulk_work/test_jev_bulk_work.py` covers planner validation, queue bounds, result order, errors, cancellation, tools, and usage. No per-file coverage percentage is published.
CONCURRENCY MODEL: The planner runs once before task workers start. The coordinator creates exactly `min(max_parallel_agents, item_count)` worker tasks and feeds item indexes through a queue bounded to that worker count; cancellation cancels and gathers every sibling task before propagating.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import Any

from pydantic import ValidationError

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.dataclasses.context import BaseAgentContext, ContextArtifact
from vidbyte.lib.dataclasses.skills import ClaudeSkillReference
from vidbyte.lib.dataclasses.jev import (
    JevBulkItemResult,
    JevBulkPlan,
    JevBulkPlanItem,
    JevBulkWorkResult,
    _JevBulkPlanAssessment,
)
from vidbyte.lib.enums.jev import JevBulkItemError, JevBulkPlanningError
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.prompts import Prompts
from vidbyte.tools._internal import with_internal_agent_tools
from vidbyte.tools.catalog import Tools


class JevBulkWork(BaseAgent):
    """Tool-free planner that coordinates bounded, isolated BaseAgent work items."""

    def __init__(self, settings: JevAgentSettings) -> None:
        # Builds the planner with the owner's model and the named planner resource caps.
        # @intent planner-and-workers-own-independent-agent-state
        # Separate BaseAgent instances provide bounded loop settings, fresh histories, permission policy,
        # and usage trackers without granting tools to the planner.
        self._owner_settings = settings
        self._bulk_settings = settings.bulk_work
        self._worker_system_prompt = Prompts().get(Prompt.JEV_BULK_WORK_WORKER_SYSTEM_PROMPT)
        self.synthesis_prompt = Prompts().get(Prompt.JEV_BULK_WORK_SYNTHESIS_PROMPT)
        super().__init__(
            name=f"{settings.name}-bulk-planner",
            system_prompt=Prompts().get(Prompt.JEV_BULK_WORK_SYSTEM_PROMPT),
            permission_policy=settings.permission_policy,
            agent_loop_settings=AgentLoopSettings(
                max_iterations=settings.bulk_work.planner_max_iterations,
                max_tokens=settings.bulk_work.planner_max_tokens,
                timeout_seconds=settings.timeout_seconds,
            ),
            api_key=settings.api_key,
            provider=settings.provider,
            model_name=settings.model_name,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
            output_schema=JevBulkPlan,
        )

    async def plan_and_run(self, message: str, context: BaseAgentContext, tools: tuple[object, ...], *, claude_skills: tuple[ClaudeSkillReference, ...] = ()) -> JevBulkWorkResult:
        # Plans from the exact request, rejects the entire invalid plan, then runs a bounded worker pool.
        # @intent only-independent-work-is-fanned-out
        # Bulk execution is safe only when Jev recognized separate independent work and the generated
        # plan preserves every item. Rejecting the complete plan protects the user's requested scope:
        # truncation can silently omit work, while accepting a malformed plan can invent or merge tasks.
        # Each worker gets a fresh history and the exact effective selected tools, with the owner's
        # permission policy. A task failure remains visible to final synthesis instead of being hidden
        # by sibling successes, and cancellation is never converted into a completed item.
        if not isinstance(claude_skills, tuple) or not all(isinstance(skill, ClaudeSkillReference) for skill in claude_skills):
            raise ConfigurationError("claude_skills must be a tuple of ClaudeSkillReference values.")
        attempt = await self._request_plan(message, context)
        if attempt.plan is None:
            return self._rejected_result(attempt)
        items = await self._run_plan(message, context, tools, attempt.plan, claude_skills)
        return JevBulkWorkResult(plan_valid=True, items=items, planner_usage=self.get_usage(), planning_error=None)

    def result_artifact(self, result: JevBulkWorkResult) -> ContextArtifact:
        # Serializes ordered task records with an explicit rule that failures are not completed work.
        if not result.plan_valid:
            raise ConfigurationError("Only a valid bulk plan has task results for synthesis context.")
        payload = {
            "items": [self._item_payload(item) for item in result.items],
        }
        return ContextArtifact(
            name="Jev bulk-work results (untrusted worker output)",
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            artifact_type="jev_bulk_work_results",
            metadata={"source": "jev_bulk_work"},
        )

    def _runtime_extension_kwargs(self) -> dict[str, Any]:
        # Removes implicit agent tools so planning cannot delegate or execute user work.
        return {"include_internal_tools": False}

    async def _request_plan(self, message: str, context: BaseAgentContext) -> _JevBulkPlanAssessment:
        # Runs one structured planning turn with the unchanged request and a tool-free context.
        # @intent planner-rejection-keeps-serial-work-available
        # A planner transport or structured-output failure rejects only fan-out; JevRuntime still gives
        # the unchanged request to the ordinary main loop.
        self._reset_planner_state()
        try:
            planner_context = replace(context, system_prompt=self.system_prompt, history=(), tools=(), tool_calls=(), responses=())
            reply = await self.arun(message, context=planner_context)
        except Exception:
            return _JevBulkPlanAssessment(plan=None, failure=JevBulkPlanningError.PLANNER_FAILURE)
        finally:
            self.history.clear()
            self._tool_call_contexts.clear()
        return self._assess_plan(reply.structured)

    def _reset_planner_state(self) -> None:
        # Prevents a prior call's planner transcript from entering the next independent plan.
        self.history.clear()
        self._tool_call_contexts.clear()
        self.last_reply = None
        self.last_prompt = ""

    def _assess_plan(self, value: object) -> _JevBulkPlanAssessment:
        # Validates structure, item count, unique identifiers, and every planner field atomically.
        try:
            plan = value if isinstance(value, JevBulkPlan) else JevBulkPlan.model_validate(value)
        except (ValidationError, TypeError, ValueError):
            return _JevBulkPlanAssessment(plan=None, failure=JevBulkPlanningError.MALFORMED_OUTPUT)
        if len(plan.items) < 2:
            return _JevBulkPlanAssessment(plan=None, failure=JevBulkPlanningError.TOO_FEW_ITEMS)
        if len(plan.items) > self._bulk_settings.max_items:
            return _JevBulkPlanAssessment(plan=None, failure=JevBulkPlanningError.TOO_MANY_ITEMS)
        identifiers = tuple(item.identifier for item in plan.items)
        if len(set(identifiers)) != len(identifiers):
            return _JevBulkPlanAssessment(plan=None, failure=JevBulkPlanningError.DUPLICATE_IDENTIFIERS)
        return _JevBulkPlanAssessment(plan=plan, failure=None)

    def _rejected_result(self, attempt: _JevBulkPlanAssessment) -> JevBulkWorkResult:
        # Preserves planner usage and the safe rejection category when serial fallback is required.
        # @intent rejected-plans-never-start-partial-work
        # Keeping an invalid whole plan visible as one typed rejection prevents dropped or malformed
        # tasks from appearing completed while leaving standard Jev execution available.
        return JevBulkWorkResult(
            plan_valid=False,
            items=(),
            planner_usage=self.get_usage(),
            planning_error=attempt.failure or JevBulkPlanningError.MALFORMED_OUTPUT,
        )

    async def _run_plan(self, message: str, context: BaseAgentContext, tools: tuple[object, ...], plan: JevBulkPlan, claude_skills: tuple[ClaudeSkillReference, ...]) -> tuple[JevBulkItemResult, ...]:
        # Runs plan indexes through a fixed worker count and returns records in plan order.
        worker_count = min(self._bulk_settings.max_parallel_agents, len(plan.items))
        queue: asyncio.Queue[int | None] = asyncio.Queue(maxsize=worker_count)
        results: list[JevBulkItemResult | None] = [None] * len(plan.items)
        workers = [asyncio.create_task(self._consume_items(queue, results, message, context, tools, plan, claude_skills)) for _ in range(worker_count)]
        try:
            for index in range(len(plan.items)):
                await queue.put(index)
            for _ in workers:
                await queue.put(None)
            await asyncio.gather(*workers)
        except BaseException:
            await self._cancel_workers(workers)
            raise
        return tuple(self._completed_result(index, item, results[index]) for index, item in enumerate(plan.items))

    async def _consume_items(self, queue: asyncio.Queue[int | None], results: list[JevBulkItemResult | None], message: str, context: BaseAgentContext, tools: tuple[object, ...], plan: JevBulkPlan, claude_skills: tuple[ClaudeSkillReference, ...]) -> None:
        # Takes queue indexes until the sentinel and stores each item result at its original position.
        while True:
            index = await queue.get()
            try:
                if index is None:
                    return
                item = plan.items[index]
                results[index] = await self._run_item(message, context, tools, item, claude_skills)
            finally:
                queue.task_done()

    async def _run_item(self, message: str, context: BaseAgentContext, tools: tuple[object, ...], item: JevBulkPlanItem, claude_skills: tuple[ClaudeSkillReference, ...]) -> JevBulkItemResult:
        # Runs one item with a fresh agent and captures ordinary failures as safe typed records.
        worker: BaseAgent | None = None
        try:
            worker = self._build_worker(item, tools)
            system_prompt = context.system_prompt if context.system_prompt is not None else self._owner_settings.system_prompt
            scoped_prompt = f"{system_prompt}\n\n{self._worker_system_prompt}"
            worker_context = replace(
                context,
                system_prompt=scoped_prompt,
                history=(),
                tools=with_internal_agent_tools(Tools(worker.tools)).specs(),
                tool_calls=(),
                responses=(),
            )
            reply = await worker.arun(
                self._task_message(message, item),
                context=worker_context,
                claude_skills=claude_skills,
                claude_skill_session=None,
            )
            return JevBulkItemResult(identifier=item.identifier, title=item.title, output=reply.content, error=None, usage=worker.get_usage())
        except asyncio.CancelledError:
            raise
        except Exception:
            return JevBulkItemResult(identifier=item.identifier, title=item.title, output=None, error=JevBulkItemError.WORKER_FAILURE, usage=None if worker is None else worker.get_usage())

    def _build_worker(self, item: JevBulkPlanItem, tools: tuple[object, ...]) -> BaseAgent:
        # Constructs one item-scoped BaseAgent after cloning bound SDK tools, never binding originals.
        # @intent workers-preserve-owner-permissions-and-selected-tools
        # Each fresh worker receives only the selector-approved tool catalog and owner policy; cloned
        # SDK tools bind to that worker while custom tools keep the existing identity contract.
        settings = self._owner_settings
        return BaseAgent(
            name=f"{settings.name}-bulk-{item.identifier}",
            system_prompt=settings.system_prompt,
            tools=self._clone_selected_tools(tools),
            permission_policy=settings.permission_policy,
            agent_loop_settings=settings.loop,
            api_key=settings.api_key,
            provider=settings.provider,
            model_name=settings.model_name,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
        )

    @staticmethod
    def _clone_selected_tools(tools: tuple[object, ...]) -> tuple[object, ...]:
        # Clones agent-bound SDK tools through the same hook as AgentForker and preserves other tools by identity.
        return tuple(JevBulkWork._clone_tool(tool) for tool in tools)

    @staticmethod
    def _clone_tool(tool: object) -> object:
        # Calls a tool's existing fork hook when available without changing generic tool semantics.
        clone = getattr(tool, "clone_for_fork", None)
        return clone() if callable(clone) else tool

    @staticmethod
    def _task_message(message: str, item: JevBulkPlanItem) -> str:
        # Encodes the exact request and one planner item as data for an isolated worker turn.
        return json.dumps(
            {
                "original_user_request": message,
                "work_item": {"identifier": item.identifier, "title": item.title, "prompt": item.prompt},
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _completed_result(index: int, item: JevBulkPlanItem, result: JevBulkItemResult | None) -> JevBulkItemResult:
        # Makes an impossible missing queue result visible instead of silently dropping a requested item.
        if result is not None:
            return result
        return JevBulkItemResult(
            identifier=item.identifier,
            title=item.title,
            output=None,
            error=JevBulkItemError.MISSING_RESULT,
        )

    @staticmethod
    def _item_payload(item: JevBulkItemResult) -> dict[str, object]:
        # Renders a task result with an explicit status while omitting private usage details from model context.
        return {
            "identifier": item.identifier,
            "title": item.title,
            "status": "completed" if item.error is None else "failed",
            "output": item.output,
            "error": item.error,
        }

    @staticmethod
    async def _cancel_workers(workers: list[asyncio.Task[None]]) -> None:
        # Cancels and gathers every sibling so cancellation cannot strand parallel work.
        for worker in workers:
            if not worker.done():
                worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


__all__ = ["JevBulkWork"]

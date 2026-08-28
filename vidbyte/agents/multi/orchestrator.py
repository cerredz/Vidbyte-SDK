"""Context Protocol Header

Description:
    Defines the multi-agent orchestrator protocol and manager-agent adapter.
Purpose:
    Separates planning policy from controller mechanics while providing a
    Magentic-One-inspired implementation with structured plan/progress phases.
Architecture:
    - MultiAgentOrchestrator: Run-local planning/decision/finalization contract.
    - MagenticOneOrchestrator: Schema-free manager plus short-lived structured forks.
    - MultiAgentContext: Context-layer renderer for trusted and untrusted primitives.
Relations:
    Called by runtime collaborators; reads prompt assets and immutable ledger contracts.
"""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from vidbyte.agents.base import BaseAgent
from vidbyte.context.multi_agent import MultiAgentContext
from vidbyte.lib.dataclasses.agents import AgentForkSettings
from vidbyte.lib.dataclasses.multi_agent import (
    FinalizationContext,
    FinalizationRenderer,
    ManagerAgentCloser,
    ManagerAgentFactory,
    OrchestrationContext,
    OrchestrationRenderer,
    OrchestratorDecision,
    OrchestratorPlan,
    TaskSpec,
)
from vidbyte.lib.enums.multi_agent import OrchestratorAction
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, MultiAgentExecutionError
from vidbyte.prompts import Prompts


@runtime_checkable
class MultiAgentOrchestrator(Protocol):
    """Run-local policy contract consumed by the deterministic controller loop."""

    def fork(self) -> "MultiAgentOrchestrator":
        # Returns an isolated orchestrator lifecycle for one MultiAgent run.
        ...

    async def plan(self, context: OrchestrationContext) -> OrchestratorPlan:
        # Produces the initial task graph without mutating the supplied snapshot.
        ...

    async def decide(self, context: OrchestrationContext) -> OrchestratorDecision:
        # Selects exactly one delegate, replan, or finish action for the next round.
        ...

    async def replan(self, context: OrchestrationContext) -> OrchestratorPlan:
        # Produces a replacement plan after stalls or explicit recovery decisions.
        ...

    async def finalize(self, context: FinalizationContext) -> str:
        # Produces the user-facing answer for a non-timeout terminal state.
        ...

    async def aclose(self) -> None:
        # Releases every manager resource owned by this run-local orchestrator.
        ...


class _TaskSpecOutput(BaseModel):
    """Provider-facing schema for one planned task."""

    model_config = ConfigDict(extra="forbid")
    task_id: str
    goal: str
    owner: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    required: bool = True
    acceptance_criteria: list[str] = Field(default_factory=list)
    payload: Any = None
    max_attempts: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class _PlanOutput(BaseModel):
    """Provider-facing schema for initial and replacement plans."""

    model_config = ConfigDict(extra="forbid")
    plan_summary: str
    tasks: list[_TaskSpecOutput]
    verified_facts: list[str] = Field(default_factory=list)
    facts_to_find: list[str] = Field(default_factory=list)
    facts_to_derive: list[str] = Field(default_factory=list)
    educated_guesses: list[str] = Field(default_factory=list)
    next_action: str | None = None
    rationale: str = ""


class _DecisionOutput(BaseModel):
    """Provider-facing schema for one progress decision."""

    model_config = ConfigDict(extra="forbid")
    action: OrchestratorAction
    task_id: str | None = None
    owner: str | None = None
    instruction: str | None = None
    payload: Any = None
    next_action: str | None = None
    final_answer: str | None = None
    loop_detected: bool = False
    progress_made: bool = False
    rationale: str = ""


class MagenticOneOrchestrator:
    """Magentic-One-inspired manager that plans, tracks progress, replans, and finalizes."""

    def __init__(self, manager: BaseAgent, *, planning_prompt: str | None = None, progress_prompt: str | None = None, replanning_prompt: str | None = None, final_prompt: str | None = None, context_renderer: OrchestrationRenderer | None = None, finalization_renderer: FinalizationRenderer | None = None, parse_retries: int | None = None, manager_agent_factory: ManagerAgentFactory | None = None, manager_agent_closer: ManagerAgentCloser | None = None) -> None:
        # Stores a schema-free manager template and explicit phase customization hooks.
        if not isinstance(manager, BaseAgent):
            raise ConfigurationError("MagenticOneOrchestrator.manager must be a BaseAgent.")
        if manager_agent_factory is None and (type(manager) is not BaseAgent or manager.output_schema is not None):
            raise ConfigurationError("The default manager fork path requires an exact, schema-free BaseAgent; provide manager_agent_factory for specialized agents.", details={"manager_type": type(manager).__name__, "has_output_schema": manager.output_schema is not None})
        if parse_retries is not None and parse_retries < 0:
            raise ConfigurationError("MagenticOneOrchestrator.parse_retries must be non-negative when provided.")
        for label, callback in (("context_renderer", context_renderer), ("finalization_renderer", finalization_renderer), ("manager_agent_factory", manager_agent_factory), ("manager_agent_closer", manager_agent_closer)):
            if callback is not None and not callable(callback):
                raise ConfigurationError(f"MagenticOneOrchestrator.{label} must be callable when provided.", details={"actual_type": type(callback).__name__})
        prompts = Prompts()
        self._manager_template = manager
        self._planning_prompt = planning_prompt or prompts.get(Prompt.MULTI_AGENT_ORCHESTRATOR_PLANNING_PROMPT)
        self._progress_prompt = progress_prompt or prompts.get(Prompt.MULTI_AGENT_ORCHESTRATOR_PROGRESS_PROMPT)
        self._replanning_prompt = replanning_prompt or prompts.get(Prompt.MULTI_AGENT_ORCHESTRATOR_REPLANNING_PROMPT)
        self._final_prompt = final_prompt or prompts.get(Prompt.MULTI_AGENT_ORCHESTRATOR_FINAL_PROMPT)
        self._context_renderer = context_renderer or MultiAgentContext.render_orchestration
        self._finalization_renderer = finalization_renderer or MultiAgentContext.render_finalization
        self._parse_retries = parse_retries
        self._manager_agent_factory = manager_agent_factory
        self._manager_agent_closer = manager_agent_closer
        self._run_manager: BaseAgent | None = None
        self._closed = False

    def fork(self) -> "MagenticOneOrchestrator":
        # Creates one run-local adapter whose schema-free manager is initialized on first use.
        clone = MagenticOneOrchestrator(manager=self._manager_template, planning_prompt=self._planning_prompt, progress_prompt=self._progress_prompt, replanning_prompt=self._replanning_prompt, final_prompt=self._final_prompt, context_renderer=self._context_renderer, finalization_renderer=self._finalization_renderer, parse_retries=self._parse_retries, manager_agent_factory=self._manager_agent_factory, manager_agent_closer=self._manager_agent_closer)
        return clone

    async def plan(self, context: OrchestrationContext) -> OrchestratorPlan:
        # Runs the structured planning phase and maps its validated output to public contracts.
        prompt = self._phase_message(self._planning_prompt, context)
        output = await self._structured_phase("plan", prompt, _PlanOutput, self._retry_budget(context), context.round)
        return self._to_plan(output)

    async def decide(self, context: OrchestrationContext) -> OrchestratorDecision:
        # Runs one structured progress assessment against the latest ledger revision.
        prompt = self._phase_message(self._progress_prompt, context)
        output = await self._structured_phase("progress", prompt, _DecisionOutput, self._retry_budget(context), context.round)
        return self._to_decision(output, tuple(card.name for card in context.team))

    async def replan(self, context: OrchestrationContext) -> OrchestratorPlan:
        # Runs the structured recovery phase without granting it direct ledger mutation.
        prompt = self._phase_message(self._replanning_prompt, context)
        output = await self._structured_phase("replan", prompt, _PlanOutput, self._retry_budget(context), context.round)
        return self._to_plan(output)

    async def finalize(self, context: FinalizationContext) -> str:
        # Uses the schema-free run manager to synthesize the terminal user-facing answer.
        manager = self._require_run_manager()
        prompt = f"{self._final_prompt}\n\n{self._finalization_renderer(context)}"
        reply = await manager.generate_reply(prompt, trace_metadata={"multi_agent_phase": "finalize"})
        content = reply.content.strip()
        if not content:
            raise MultiAgentExecutionError("Multi-agent manager returned a blank final answer.", details={"phase": "finalize"})
        return reply.content

    async def aclose(self) -> None:
        # Closes the schema-free run manager exactly once while leaving the template untouched.
        if self._closed:
            return
        self._closed = True
        manager, self._run_manager = self._run_manager, None
        if manager is not None:
            await self._close_manager(manager, "run")

    async def _structured_phase(self, phase: str, prompt: str, schema: type[BaseModel], retries: int, round_number: int) -> BaseModel:
        # Retries only manager invocation/parse failures and closes every structured phase fork.
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            phase_agent = self._create_manager(phase, AgentForkSettings(include_history=False, output_schema=schema))
            try:
                if phase_agent.output_schema is not schema:
                    raise ConfigurationError("manager_agent_factory must honor the requested output schema for each phase.", details={"phase": phase, "expected_schema": schema.__name__, "actual_schema": getattr(phase_agent.output_schema, "__name__", None)})
                suffix = "" if attempt == 0 else "\n\nYour prior response was invalid. Return only data matching the required schema."
                reply = await phase_agent.generate_reply(prompt + suffix, trace_metadata={"multi_agent_phase": phase, "parse_attempt": attempt + 1})
                return self._parse_phase_reply(reply.content, reply.metadata, schema)
            except ConfigurationError:
                raise
            except Exception as exc:
                last_error = exc
            finally:
                await self._close_manager(phase_agent, phase)
        error_type = type(last_error).__name__ if last_error is not None else "UnknownParseError"
        raise MultiAgentExecutionError("Multi-agent manager phase failed after bounded parse retries.", details={"phase": phase, "round": round_number, "attempts": retries + 1, "error_type": error_type}) from last_error

    def _create_manager(self, phase: str, settings: AgentForkSettings) -> BaseAgent:
        # Creates a manager through the explicit subtype factory or the safe BaseAgent fork path.
        source = self._manager_template if phase == "run" else self._require_run_manager()
        manager = source.fork(settings) if self._manager_agent_factory is None else self._manager_agent_factory(source, phase, settings)
        if inspect.isawaitable(manager):
            if inspect.iscoroutine(manager):
                manager.close()
            raise ConfigurationError("manager_agent_factory must synchronously return BaseAgent.", details={"phase": phase, "actual_type": type(manager).__name__})
        if not isinstance(manager, BaseAgent):
            raise ConfigurationError("manager_agent_factory must synchronously return BaseAgent.", details={"phase": phase, "actual_type": type(manager).__name__})
        return manager

    async def _close_manager(self, manager: BaseAgent, phase: str) -> None:
        # Releases one manager through the custom compound closer or standard MCP cleanup.
        if self._manager_agent_closer is None:
            await manager.close_mcp_servers()
            return
        result = self._manager_agent_closer(manager, phase)
        if inspect.isawaitable(result):
            await result

    def _require_run_manager(self) -> BaseAgent:
        # Lazily creates a schema-free run manager for direct protocol use outside MultiAgent.
        if self._closed:
            raise MultiAgentExecutionError("MagenticOneOrchestrator cannot be reused after aclose().")
        if self._run_manager is None:
            self._run_manager = self._create_manager("run", AgentForkSettings(include_history=False))
        if self._run_manager.output_schema is not None:
            raise ConfigurationError("Run-local manager must remain schema-free.", details={"manager_type": type(self._run_manager).__name__})
        return self._run_manager

    def _phase_message(self, instruction: str, context: OrchestrationContext) -> str:
        # Combines trusted phase instructions with the explicitly delimited run renderer.
        return f"{instruction}\n\n{self._context_renderer(context)}"

    def _retry_budget(self, context: OrchestrationContext) -> int:
        # Resolves an adapter override before falling back to the team settings.
        return context.settings.orchestrator_parse_retries if self._parse_retries is None else self._parse_retries

    @classmethod
    def _parse_phase_reply(cls, content: str, metadata: Mapping[str, Any], schema: type[BaseModel]) -> BaseModel:
        # Provider-native structured data wins; fenced JSON is a bounded compatibility path.
        structured = metadata.get("structured")
        if structured is not None:
            return schema.model_validate(structured)
        raw = content.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
        return schema.model_validate(json.loads(fenced.group(1) if fenced is not None else raw))

    @classmethod
    def _to_plan(cls, output: BaseModel) -> OrchestratorPlan:
        # Mapping private provider schemas here prevents them from leaking into public contracts.
        validated = _PlanOutput.model_validate(output)
        tasks = tuple(cls._to_task(item) for item in validated.tasks)
        return OrchestratorPlan(plan_summary=validated.plan_summary, tasks=tasks, verified_facts=tuple(validated.verified_facts), facts_to_find=tuple(validated.facts_to_find), facts_to_derive=tuple(validated.facts_to_derive), educated_guesses=tuple(validated.educated_guesses), next_action=validated.next_action, rationale=validated.rationale)

    @classmethod
    def _to_task(cls, item: _TaskSpecOutput) -> TaskSpec:
        # One task mapper keeps the plan conversion readable and independently auditable.
        return TaskSpec(task_id=item.task_id, goal=item.goal, owner=item.owner, depends_on=tuple(item.depends_on), required=item.required, acceptance_criteria=tuple(item.acceptance_criteria), payload=item.payload, max_attempts=item.max_attempts, metadata=item.metadata)

    @classmethod
    def _to_decision(cls, output: BaseModel, owners: tuple[str, ...]) -> OrchestratorDecision:
        # A single-worker team may omit owner; every other delegate remains explicit.
        validated = _DecisionOutput.model_validate(output)
        owner = owners[0] if validated.action is OrchestratorAction.DELEGATE and validated.owner is None and len(owners) == 1 else validated.owner
        return OrchestratorDecision(action=validated.action, task_id=validated.task_id, owner=owner, instruction=validated.instruction, payload=validated.payload, next_action=validated.next_action, final_answer=validated.final_answer, loop_detected=validated.loop_detected, progress_made=validated.progress_made, rationale=validated.rationale)


default_orchestration_renderer: OrchestrationRenderer = MultiAgentContext.render_orchestration
default_finalization_renderer: FinalizationRenderer = MultiAgentContext.render_finalization


__all__ = ["FinalizationRenderer", "MagenticOneOrchestrator", "MultiAgentOrchestrator", "OrchestrationRenderer", "default_finalization_renderer", "default_orchestration_renderer"]

"""Context Protocol Header

Description:
    Implements ContextMinimalFanoutParadigm — the four-stage context-minimal
    fanout harness (context, split, adversarial de-overlap, parallel implement).
Purpose:
    Turns one large implementation request into non-overlapping, context-rich
    prompts and runs them in parallel in fresh agent contexts.
Architecture:
    - ContextMinimalFanoutParadigm: ParadigmHarness with a four-stage arun.
Relations:
    Composes vidbyte.agents.BaseAgent, the ParadigmMinimalToolset, the runtime
    output-schema tools, and the paradigm's typed contracts.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from vidbyte.agents import BaseAgent
from vidbyte.middleware.builtins import CostBudgetMiddleware, TokenBudgetMiddleware
from vidbyte.paradigms.base import ParadigmHarness
from vidbyte.paradigms.context_minimal_fanout.prompts import ContextMinimalFanoutPrompts
from vidbyte.paradigms.context_minimal_fanout.types import (
    AgentRoleSettings,
    ContextMinimalFanoutResult,
    ContextMinimalFanoutSettings,
    EnvironmentContext,
    ImplementationOutput,
    PromptSplitPlan,
    SplitPrompt,
)
from vidbyte.tools.builtins.output_schema import AppendOutputTool, DeclareOutputSchemaTool, ExtendOutputSchemaTool, OutputSchemaBuilder
from vidbyte.tools.toolsets import ParadigmMinimalToolset


class ContextMinimalFanoutParadigm(ParadigmHarness):
    """Extracts context, splits it into non-overlapping prompts, and runs them in parallel."""

    def __init__(self, settings: ContextMinimalFanoutSettings | None = None, **kwargs: Any) -> None:
        # Stores construction settings and lazily loads package-local prompt text.
        self.settings = settings.with_overrides(**kwargs) if settings is not None else ContextMinimalFanoutSettings(**kwargs)
        self._prompts = ContextMinimalFanoutPrompts()

    async def arun(self, prompt: str, **options: Any) -> ContextMinimalFanoutResult:
        # Runs the four-stage pipeline and returns the structured fanout result.
        settings = self._resolve_settings(options)
        environment = await self._run_context_agent(prompt, settings)
        plan = await self._run_splitter(prompt, environment, settings)
        plan = await self._run_adversarial_loop(prompt, plan, environment, settings)
        plan.validate(max_prompt_count=settings.max_prompt_count)
        plan_markdown = plan.to_markdown()
        self._write_plan_if_requested(plan_markdown, settings)
        outputs = await self._run_implementation_prompts(plan, environment, settings)
        metadata = self._build_result_metadata(plan, outputs, settings)
        return ContextMinimalFanoutResult(plan=plan, plan_markdown=plan_markdown, environment=environment, outputs=outputs, metadata=metadata)

    def _resolve_settings(self, options: dict[str, Any]) -> ContextMinimalFanoutSettings:
        # Applies per-run settings overrides without mutating the harness defaults.
        if not options:
            return self.settings
        return self.settings.with_overrides(**options)

    async def _run_context_agent(self, prompt: str, settings: ContextMinimalFanoutSettings) -> EnvironmentContext:
        # Runs the context-extraction agent and maps its snapshot to EnvironmentContext.
        builder = OutputSchemaBuilder()
        tools = (*self._read_only_toolset(settings), *settings.context.tools, *self._output_schema_tools(builder))
        middleware = self._with_budget_middleware(settings.context.middleware, settings.context.max_tokens, settings)
        agent = BaseAgent(
            name=settings.context.name,
            system_prompt=settings.context.system_prompt or self._prompts.for_role("context"),
            runner=settings.context.runner,
            tools=tools,
            middleware=middleware,
            api_key=settings.context.api_key,
            provider=settings.context.provider,
            model_name=settings.context.model_name,
            temperature=settings.context.temperature,
            metadata={"role": "context"},
            **dict(settings.context.agent_options),
        )
        reply = await agent.arun(self._build_context_message(prompt))
        return EnvironmentContext.from_snapshot(builder.snapshot(), fallback_text=reply.content)

    async def _run_splitter(self, prompt: str, environment: EnvironmentContext, settings: ContextMinimalFanoutSettings) -> PromptSplitPlan:
        # Runs the splitter agent and maps its snapshot to a PromptSplitPlan.
        builder = OutputSchemaBuilder()
        agent = self._build_planning_agent(settings.splitter, "splitter", builder, settings)
        message = self._build_splitter_message(prompt, environment)
        await agent.arun(message)
        return PromptSplitPlan.from_snapshot(builder.snapshot())

    async def _run_adversarial_loop(self, prompt: str, plan: PromptSplitPlan, environment: EnvironmentContext, settings: ContextMinimalFanoutSettings) -> PromptSplitPlan:
        # Runs the adversarial de-overlap agent at least once, then repeats while overlap remains.
        current = plan
        for _ in range(settings.max_adversarial_rounds):
            builder = OutputSchemaBuilder()
            agent = self._build_planning_agent(settings.adversarial, "adversarial", builder, settings)
            message = self._build_adversarial_message(prompt, current, environment)
            await agent.arun(message)
            current = PromptSplitPlan.from_snapshot(builder.snapshot())
            if not current.overlap_conflicts():
                break
        return current

    async def _run_implementation_prompts(self, plan: PromptSplitPlan, environment: EnvironmentContext, settings: ContextMinimalFanoutSettings) -> tuple[ImplementationOutput, ...]:
        # Runs implementation prompts concurrently while respecting max_concurrency.
        semaphore = asyncio.Semaphore(settings.max_concurrency)
        tasks = [self._run_one_with_semaphore(semaphore, split_prompt, plan, environment, settings) for split_prompt in plan.prompts]
        return tuple(await asyncio.gather(*tasks))

    async def _run_one_with_semaphore(self, semaphore: asyncio.Semaphore, split_prompt: SplitPrompt, plan: PromptSplitPlan, environment: EnvironmentContext, settings: ContextMinimalFanoutSettings) -> ImplementationOutput:
        # Executes one implementation branch under the shared concurrency limit.
        async with semaphore:
            return await self._run_one_implementation_prompt(split_prompt, plan, environment, settings)

    async def _run_one_implementation_prompt(self, split_prompt: SplitPrompt, plan: PromptSplitPlan, environment: EnvironmentContext, settings: ContextMinimalFanoutSettings) -> ImplementationOutput:
        # Runs one implementation agent and normalizes success or captured failure.
        agent = self._build_implementation_agent(split_prompt, settings)
        message = self._build_implementation_message(split_prompt, plan, environment)
        try:
            reply = await agent.arun(message)
            return ImplementationOutput(prompt_id=split_prompt.id, title=split_prompt.title, content=reply.content, metadata=dict(reply.metadata))
        except Exception as exc:
            if not settings.return_exceptions:
                raise
            return ImplementationOutput(prompt_id=split_prompt.id, title=split_prompt.title, content="", error=repr(exc), metadata={"exception_type": exc.__class__.__name__})

    def _build_planning_agent(self, role_settings: AgentRoleSettings, role: str, builder: OutputSchemaBuilder, settings: ContextMinimalFanoutSettings) -> BaseAgent:
        # Constructs a splitter/adversarial planning agent with output-schema tools.
        tools = (*self._read_only_toolset(settings), *role_settings.tools, *self._output_schema_tools(builder))
        middleware = self._with_budget_middleware(role_settings.middleware, role_settings.max_tokens, settings)
        return BaseAgent(
            name=role_settings.name,
            system_prompt=role_settings.system_prompt or self._prompts.for_role(role),
            runner=role_settings.runner,
            tools=tools,
            middleware=middleware,
            api_key=role_settings.api_key,
            provider=role_settings.provider,
            model_name=role_settings.model_name,
            temperature=role_settings.temperature,
            metadata={"role": role},
            **dict(role_settings.agent_options),
        )

    def _build_implementation_agent(self, split_prompt: SplitPrompt, settings: ContextMinimalFanoutSettings) -> BaseAgent:
        # Constructs a fresh implementation agent for one split prompt.
        tools = (*self._implementation_toolset(settings), *settings.implementation.tools)
        middleware = self._with_budget_middleware(settings.implementation.middleware, settings.implementation.max_tokens, settings)
        return BaseAgent(
            name=f"{settings.implementation.name}-{split_prompt.id}",
            system_prompt=settings.implementation.system_prompt or self._prompts.for_role("implementation"),
            runner=settings.implementation.runner,
            tools=tools,
            middleware=middleware,
            api_key=settings.implementation.api_key,
            provider=settings.implementation.provider,
            model_name=settings.implementation.model_name,
            temperature=settings.implementation.temperature,
            metadata={"role": "implementation", "split_prompt_id": split_prompt.id},
            **dict(settings.implementation.agent_options),
        )

    def _read_only_toolset(self, settings: ContextMinimalFanoutSettings) -> tuple[object, ...]:
        # Builds the read-only minimal toolset for planning agents when enabled.
        if not settings.include_minimal_toolset:
            return ()
        toolset = ParadigmMinimalToolset(settings.default_tool_root, include_execution=settings.include_execution_tool, include_write=False)
        return toolset.all()

    def _implementation_toolset(self, settings: ContextMinimalFanoutSettings) -> tuple[object, ...]:
        # Builds the write-enabled minimal toolset for implementation agents when enabled.
        if not settings.include_minimal_toolset:
            return ()
        toolset = ParadigmMinimalToolset(settings.default_tool_root, include_execution=settings.include_execution_tool, include_write=settings.implementation_include_write)
        return toolset.all()

    def _output_schema_tools(self, builder: OutputSchemaBuilder) -> tuple[object, ...]:
        # Binds the declare/extend/append output-schema tools to a run-local builder.
        return (DeclareOutputSchemaTool(builder), ExtendOutputSchemaTool(builder), AppendOutputTool(builder))

    def _build_context_message(self, prompt: str) -> str:
        # Wraps the caller request in a stable context-agent input envelope.
        return "\n".join([
            "<user_request>",
            prompt.strip(),
            "</user_request>",
            "",
            "Explore the repository, then return the relevant context using declare_output_schema and append_output.",
        ])

    def _build_splitter_message(self, prompt: str, environment: EnvironmentContext) -> str:
        # Builds the splitter input from the request and the environment context.
        return "\n".join([
            "<user_request>",
            prompt.strip(),
            "</user_request>",
            "",
            environment.to_prompt_block(),
            "",
            "Return the split plan using declare_output_schema and append_output.",
        ])

    def _build_adversarial_message(self, prompt: str, plan: PromptSplitPlan, environment: EnvironmentContext) -> str:
        # Builds the adversarial input from the request, current plan, and overlaps.
        conflicts = plan.overlap_conflicts()
        return "\n".join([
            "<user_request>",
            prompt.strip(),
            "</user_request>",
            "",
            environment.to_prompt_block(),
            "",
            "<current_split_plan>",
            plan.to_markdown().rstrip(),
            "</current_split_plan>",
            "",
            "<detected_overlaps>",
            "\n".join(f"- {item}" for item in conflicts) or "- None detected; still verify ownership.",
            "</detected_overlaps>",
            "",
            "Return the corrected, non-overlapping split plan using declare_output_schema and append_output.",
        ])

    def _build_implementation_message(self, split_prompt: SplitPrompt, plan: PromptSplitPlan, environment: EnvironmentContext) -> str:
        # Builds the branch-specific prompt with global, environment, and ownership context.
        return "\n".join([
            "<global_goal>",
            plan.goal,
            "</global_goal>",
            "",
            "<global_instructions>",
            plan.global_instructions,
            "</global_instructions>",
            "",
            environment.to_prompt_block(),
            "",
            "<non_overlap_requirements>",
            "\n".join(f"- {item}" for item in plan.non_overlap_requirements) or "- N/A",
            "</non_overlap_requirements>",
            "",
            f"<implementation_prompt id=\"{split_prompt.id}\" title=\"{split_prompt.title}\">",
            split_prompt.prompt,
            "</implementation_prompt>",
            "",
            "<owned_paths>",
            "\n".join(f"- {item}" for item in split_prompt.owned_paths) or "- N/A",
            "</owned_paths>",
            "",
            "<read_only_paths>",
            "\n".join(f"- {item}" for item in split_prompt.read_only_paths) or "- N/A",
            "</read_only_paths>",
            "",
            "<commands>",
            "\n".join(f"- {item}" for item in split_prompt.commands) or "- N/A",
            "</commands>",
            "",
            "<notes>",
            "\n".join(f"- {item}" for item in split_prompt.notes) or "- N/A",
            "</notes>",
        ])

    def _write_plan_if_requested(self, plan_markdown: str, settings: ContextMinimalFanoutSettings) -> None:
        # Writes the Markdown split plan only when the caller requested a path.
        if settings.plan_output_path is None:
            return
        path = Path(settings.plan_output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(plan_markdown, encoding="utf-8")

    def _with_budget_middleware(self, middleware: tuple[object, ...], max_tokens: int | None, settings: ContextMinimalFanoutSettings) -> tuple[object, ...]:
        # Appends token and cost budget middleware according to the harness settings.
        resolved = tuple(middleware)
        if max_tokens is not None:
            resolved = (*resolved, TokenBudgetMiddleware(max_tokens=max_tokens, allow_final_response_over_budget=True))
        if settings.max_cost_usd is not None and settings.cost_per_million_tokens is not None:
            resolved = (*resolved, CostBudgetMiddleware(max_spend_usd=settings.max_cost_usd, cost_per_million_tokens=settings.cost_per_million_tokens))
        return resolved

    def _build_result_metadata(self, plan: PromptSplitPlan, outputs: tuple[ImplementationOutput, ...], settings: ContextMinimalFanoutSettings) -> dict[str, Any]:
        # Summarizes run shape and branch success for caller inspection.
        failed = tuple(output for output in outputs if output.error)
        return {
            "paradigm": "context_minimal_fanout",
            "prompt_count": len(plan.prompts),
            "output_count": len(outputs),
            "failed_count": len(failed),
            "max_concurrency": settings.max_concurrency,
            "plan_output_path": str(settings.plan_output_path) if settings.plan_output_path is not None else None,
        }


__all__ = [
    "ContextMinimalFanoutParadigm",
]

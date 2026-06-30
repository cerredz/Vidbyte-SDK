from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from vidbyte.agents import BaseAgent
from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig
from vidbyte.middleware.builtins import CostBudgetMiddleware, TokenBudgetMiddleware
from vidbyte.paradigms.base import ParadigmHarness
from vidbyte.paradigms.context_minimal_fanout.multiple_prompts.prompts import MultiplePromptFanoutPrompts
from vidbyte.paradigms.context_minimal_fanout.multiple_prompts.types import (
    ContextMinimalFanoutResult,
    ImplementationOutput,
    MultiplePromptFanoutSettings,
    PromptSplitPlan,
    SplitPrompt,
)
from vidbyte.tools.builtins.code_execution import CodeExecutionTool
from vidbyte.tools.builtins.code_search import GlobTool, GrepTool
from vidbyte.tools.filesystem import ReadLinesTool, ReadTextTool


class MultiplePromptFanoutHarness(ParadigmHarness):
    """Splits one prompt into non-overlapping prompts and runs them in parallel."""

    def __init__(self, settings: MultiplePromptFanoutSettings | None = None, **kwargs: Any) -> None:
        # Stores construction settings and lazily loads package-local prompt text.
        self.settings = settings.with_overrides(**kwargs) if settings is not None else MultiplePromptFanoutSettings(**kwargs)
        self._prompts = MultiplePromptFanoutPrompts()

    async def arun(self, prompt: str, **options: Any) -> ContextMinimalFanoutResult:
        # Runs the splitter, validates the plan, fans out implementation agents, and returns all outputs.
        settings = self._resolve_settings(options)
        plan = await self._run_splitter(prompt, settings)
        plan.validate(max_prompt_count=settings.max_prompt_count)
        plan_markdown = plan.to_markdown()
        self._write_plan_if_requested(plan_markdown, settings)
        outputs = await self._run_implementation_prompts(plan, settings)
        metadata = self._build_result_metadata(plan, outputs, settings)
        return ContextMinimalFanoutResult(plan=plan, plan_markdown=plan_markdown, outputs=outputs, metadata=metadata)

    def _resolve_settings(self, options: dict[str, Any]) -> MultiplePromptFanoutSettings:
        # Applies per-run settings overrides without mutating the harness defaults.
        if not options:
            return self.settings
        return self.settings.with_overrides(**options)

    async def _run_splitter(self, prompt: str, settings: MultiplePromptFanoutSettings) -> PromptSplitPlan:
        # Executes the split-planning agent and parses its JSON split plan.
        splitter = self._build_splitter_agent(settings)
        message = self._build_splitter_message(prompt)
        reply = await splitter.arun(message)
        return PromptSplitPlan.from_json_text(reply.content)

    def _build_splitter_agent(self, settings: MultiplePromptFanoutSettings) -> BaseAgent:
        # Constructs the splitter agent with read-oriented defaults and caller tools.
        tools = (*self._default_splitter_tools(settings), *settings.splitter_tools)
        middleware = self._with_budget_middleware(settings.splitter_middleware, settings.max_splitter_tokens, settings)
        return BaseAgent(
            name=settings.splitter_name,
            system_prompt=settings.splitter_system_prompt or self._prompts.splitter(),
            runner=settings.splitter_runner,
            tools=tools,
            middleware=middleware,
            api_key=settings.splitter_api_key,
            provider=settings.splitter_provider,
            model_name=settings.splitter_model_name,
            temperature=settings.splitter_temperature,
            **dict(settings.splitter_agent_options),
        )

    def _default_splitter_tools(self, settings: MultiplePromptFanoutSettings) -> tuple[object, ...]:
        # Builds the default read/search/code toolset for the splitter agent.
        if not settings.include_default_splitter_tools:
            return ()
        root = Path(settings.default_tool_root)
        fs_config = FileSystemToolConfig(root=root)
        return (
            GlobTool(root_dir=root),
            GrepTool(root_dir=root),
            ReadTextTool(fs_config),
            ReadLinesTool(fs_config),
            CodeExecutionTool(),
        )

    def _build_splitter_message(self, prompt: str) -> str:
        # Wraps the caller request in a stable splitter input envelope.
        return "\n".join([
            "<user_request>",
            prompt.strip(),
            "</user_request>",
            "",
            "Return only the JSON split plan described in your system prompt.",
        ])

    def _write_plan_if_requested(self, plan_markdown: str, settings: MultiplePromptFanoutSettings) -> None:
        # Writes the Markdown split plan only when the caller explicitly requested a path.
        if settings.plan_output_path is None:
            return
        path = Path(settings.plan_output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(plan_markdown, encoding="utf-8")

    async def _run_implementation_prompts(self, plan: PromptSplitPlan, settings: MultiplePromptFanoutSettings) -> tuple[ImplementationOutput, ...]:
        # Runs implementation prompts concurrently while respecting max_concurrency.
        semaphore = asyncio.Semaphore(settings.max_concurrency)
        tasks = [self._run_one_with_semaphore(semaphore, split_prompt, plan, settings) for split_prompt in plan.prompts]
        return tuple(await asyncio.gather(*tasks))

    async def _run_one_with_semaphore(self, semaphore: asyncio.Semaphore, split_prompt: SplitPrompt, plan: PromptSplitPlan, settings: MultiplePromptFanoutSettings) -> ImplementationOutput:
        # Executes one implementation branch under the shared concurrency limit.
        async with semaphore:
            return await self._run_one_implementation_prompt(split_prompt, plan, settings)

    async def _run_one_implementation_prompt(self, split_prompt: SplitPrompt, plan: PromptSplitPlan, settings: MultiplePromptFanoutSettings) -> ImplementationOutput:
        # Runs one implementation agent and normalizes success or captured failure.
        agent = self._build_implementation_agent(split_prompt, settings)
        message = self._build_implementation_message(split_prompt, plan)
        try:
            reply = await agent.arun(message)
            return ImplementationOutput(prompt_id=split_prompt.id, title=split_prompt.title, content=reply.content, metadata=dict(reply.metadata))
        except Exception as exc:
            if not settings.return_exceptions:
                raise
            return ImplementationOutput(prompt_id=split_prompt.id, title=split_prompt.title, content="", error=repr(exc), metadata={"exception_type": exc.__class__.__name__})

    def _build_implementation_agent(self, split_prompt: SplitPrompt, settings: MultiplePromptFanoutSettings) -> BaseAgent:
        # Constructs a fresh implementation agent for one split prompt.
        middleware = self._with_budget_middleware(settings.implementation_middleware, settings.max_implementation_tokens, settings)
        return BaseAgent(
            name=f"{settings.implementation_name_prefix}-{split_prompt.id}",
            system_prompt=settings.implementation_system_prompt or self._prompts.implementation(),
            runner=settings.implementation_runner,
            tools=settings.implementation_tools,
            middleware=middleware,
            api_key=settings.implementation_api_key,
            provider=settings.implementation_provider,
            model_name=settings.implementation_model_name,
            temperature=settings.implementation_temperature,
            metadata={"split_prompt_id": split_prompt.id},
            **dict(settings.implementation_agent_options),
        )

    def _build_implementation_message(self, split_prompt: SplitPrompt, plan: PromptSplitPlan) -> str:
        # Builds the branch-specific prompt with global and ownership context.
        return "\n".join([
            "<global_goal>",
            plan.goal,
            "</global_goal>",
            "",
            "<global_instructions>",
            plan.global_instructions,
            "</global_instructions>",
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

    def _with_budget_middleware(self, middleware: tuple[object, ...], max_tokens: int | None, settings: MultiplePromptFanoutSettings) -> tuple[object, ...]:
        # Appends existing budget middleware according to the harness settings.
        resolved = tuple(middleware)
        if max_tokens is not None:
            resolved = (*resolved, TokenBudgetMiddleware(max_tokens=max_tokens, allow_final_response_over_budget=True))
        if settings.max_cost_usd is not None and settings.cost_per_million_tokens is not None:
            resolved = (*resolved, CostBudgetMiddleware(max_spend_usd=settings.max_cost_usd, cost_per_million_tokens=settings.cost_per_million_tokens))
        return resolved

    def _build_result_metadata(self, plan: PromptSplitPlan, outputs: tuple[ImplementationOutput, ...], settings: MultiplePromptFanoutSettings) -> dict[str, Any]:
        # Summarizes run shape and branch success for caller inspection.
        failed = tuple(output for output in outputs if output.error)
        return {
            "paradigm": "context_minimal_fanout",
            "implementation": "multiple_prompts",
            "prompt_count": len(plan.prompts),
            "output_count": len(outputs),
            "failed_count": len(failed),
            "max_concurrency": settings.max_concurrency,
            "plan_output_path": str(settings.plan_output_path) if settings.plan_output_path is not None else None,
        }


__all__ = [
    "MultiplePromptFanoutHarness",
]

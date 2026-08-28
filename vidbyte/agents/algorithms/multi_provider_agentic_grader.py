"""Context Protocol Header

Description:
    Executes the Multi-Provider Agentic Grader context-window algorithm for AgentRuntime.
Purpose:
    Handles concurrent direct loop invocations across model providers and
    applies the meta-grader evaluation to pick the best response.
Architecture:
    - MultiProviderAgenticGraderRuntimeAlgorithm: Coordinates parallel runs and grading call.
Key Functions:
    - arun: Orchestrates concurrent agent trials across providers, captures outputs, and runs the meta-grader.
    - _run_provider_trial: Runs the agentic loop for a single provider and captures output text.
    - _collect_candidates: Filters trial results into a candidates dict and aggregates tokens/calls.
    - _build_candidates_text: Formats the candidates dict into a labeled text block for the grader.
    - _run_grader: Invokes the meta-grader model call via middleware.
    - _select_winner: Picks the best candidate from the grader's output.
    - _build_result_metadata: Assembles the final algorithm metadata payload.
Relations:
    Used by AgentRuntimeContextAlgorithms as part of the core agent execution pipeline.
    Consumes MultiProviderAgenticGraderAlgorithm from vidbyte.context.algorithms.
Similar Files:
    - vidbyte/agents/algorithms/reflexion.py: A similar context-window agent runtime algorithm.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from vidbyte.context.algorithms.multi_provider_agentic_grader import (
    MultiProviderAgenticGraderAlgorithm,
)
from vidbyte.lib.agents.modality_detector import ModalityDetector
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums import ModelModality
from vidbyte.lib.errors import AgentExecutionError
from vidbyte.lib.models import ProviderModelRegistry
from vidbyte.lib.tracing import SpanContext

if TYPE_CHECKING:
    from vidbyte.agents.runtime import AgentRuntime


class MultiProviderAgenticGraderRuntimeAlgorithm:
    """Runtime implementation for the Multi-Provider Agentic Grader context-window algorithm."""

    name = "multi_provider_agentic_grader"

    def __init__(self, runtime: AgentRuntime, algorithm: MultiProviderAgenticGraderAlgorithm) -> None:
        # Initializes the Multi-Provider Agentic Grader runtime adapter.
        self.runtime = runtime
        self.algorithm = algorithm

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        # Orchestrates concurrent provider trials followed by a meta-grader selection pass.
        started_at = self.runtime.middleware.clock()
        active_models = ProviderModelRegistry.resolve_active(self.algorithm.provider_models, options)
        results = await self._run_provider_trials(message, context, handle, metadata, options, trace_context, active_models)
        candidates, total_tokens, call_contexts = self._collect_candidates(active_models, results)
        candidates_text = self._build_candidates_text(candidates)
        raw_result = await self._run_grader(message, candidates_text, context, handle, metadata, started_at, trace_context)
        if isinstance(raw_result, AgentResult):
            return raw_result
        selected_output, selected_provider = self._select_winner(candidates, raw_result, handle)
        res_metadata = self._build_result_metadata(metadata, active_models, selected_provider, candidates, total_tokens, call_contexts)
        return AgentResult(output=selected_output, strategy_name="multi_provider_agentic_grader", calls=tuple(call_contexts), metadata=res_metadata)

    async def _run_provider_trials(self, message: str, context: BaseAgentContext, handle: RunnerHandle, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None, active_models: dict[str, str]) -> list[Any]:
        # Launches all provider loops concurrently and returns their results, including exceptions.
        tasks = [
            self._run_provider_trial(p_name, m_name, message, context, handle, metadata, options, trace_context)
            for p_name, m_name in active_models.items()
        ]
        return list(await asyncio.gather(*tasks, return_exceptions=True))

    async def _run_provider_trial(self, provider_name: str, model_name: str, message: str, context: BaseAgentContext, handle: RunnerHandle, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> AgentResult:
        # Runs a single provider's agentic loop, capturing output text via wrap_text for grading.
        trial_prompt = self.algorithm.agent_system_prompt_text(context.system_prompt or "")
        trial_context = dataclasses.replace(context, system_prompt=trial_prompt)
        p_runner = ModalityDetector.create_runner(modality=ModelModality.TEXT, provider=provider_name, model=model_name)
        captured_output: list[str] = []
        trial_handle = handle.with_runner(p_runner, provider_name).wrap_text(captured_output.append)
        res = await self.runtime._arun_once(
            message,
            handle=trial_handle,
            context=trial_context,
            metadata={**dict(metadata or {}), "context_window_algorithm": "multi_provider_agentic_grader", "grader_stage": "agent_loop", "loop_provider": provider_name, "loop_model": model_name},
            options=dict(options or {}),
            trace_context=trace_context,
        )
        if captured_output:
            res = dataclasses.replace(res, output=captured_output[-1])
        return res

    def _collect_candidates(self, active_models: dict[str, str], results: list[Any]) -> tuple[dict[str, str], int, list[Any]]:
        # Extracts successful trial outputs and accumulates token counts and tool call records.
        candidates: dict[str, str] = {}
        total_tokens = 0
        call_contexts: list[Any] = []
        for (p_name, _m_name), res in zip(active_models.items(), results):
            if isinstance(res, Exception):
                continue
            candidates[p_name] = res.output
            if res.metadata:
                total_tokens += res.metadata.get("tokens_used", 0) or 0
                if "tool_calls" in res.metadata:
                    call_contexts.extend(res.metadata["tool_calls"])
        if not candidates:
            failures = [str(r) for r in results if isinstance(r, Exception)]
            raise AgentExecutionError(f"All provider loops failed: {', '.join(failures)}")
        return candidates, total_tokens, call_contexts

    def _build_candidates_text(self, candidates: dict[str, str]) -> str:
        # Formats all candidate outputs into a labeled block for the grader prompt.
        return "".join(f"### Model Provider: {p_name}\nCandidate Output:\n{text}\n\n" for p_name, text in candidates.items())

    async def _run_grader(self, message: str, candidates_text: str, context: BaseAgentContext, handle: RunnerHandle, metadata: Mapping[str, Any] | None, started_at: Any, trace_context: SpanContext | None) -> Any:
        # Invokes the meta-grader model call via middleware and returns its raw result.
        grader_prompt = self.algorithm.render_grader_prompt(message, candidates_text)
        grader_runner = ModalityDetector.create_runner(modality=ModelModality.TEXT, provider=self.algorithm.grader_provider, model=self.algorithm.grader_model)
        grader_handle = handle.with_runner(grader_runner, self.algorithm.grader_provider)
        raw_result, _, _ = await self.runtime._invoke_with_middleware(
            grader_handle,
            grader_prompt,
            {"system": self.algorithm.grader_system_prompt_text()},
            context=context,
            iteration_count=0,
            model_call_count=0,
            call_contexts=(),
            tokens_used=None,
            started_at=started_at,
            metadata={**dict(metadata or {}), "context_window_algorithm": "multi_provider_agentic_grader", "grader_stage": "grade"},
            trace_context=trace_context,
        )
        return raw_result

    def _select_winner(self, candidates: dict[str, str], raw_result: Any, handle: RunnerHandle) -> tuple[str, str]:
        # Matches the grader's output against candidate texts and returns the selected output and provider name.
        grader_output = handle.extract_text(raw_result).strip()
        for p_name, text in candidates.items():
            if text.strip() in grader_output or grader_output in text.strip():
                return text, p_name
        return grader_output, "grader_raw"

    def _build_result_metadata(self, metadata: Mapping[str, Any] | None, active_models: dict[str, str], selected_provider: str, candidates: dict[str, str], total_tokens: int, call_contexts: list[Any]) -> dict[str, Any]:
        # Assembles the final result metadata dict including grader decision and algorithm trace.
        return {
            **dict(metadata or {}),
            "multi_provider_agentic_grader": {
                "grader_decision": {
                    "selected_provider": selected_provider,
                    "model": active_models.get(selected_provider, self.algorithm.grader_model),
                },
                "candidates": candidates,
                "total_runs": len(candidates),
                "tokens_used": total_tokens,
            },
        }


__all__ = [
    "MultiProviderAgenticGraderRuntimeAlgorithm",
]



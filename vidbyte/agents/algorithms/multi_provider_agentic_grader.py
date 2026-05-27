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
    - _resolve_active_models: Identifies which providers have valid environment credentials.
Relations:
    Used by AgentRuntimeContextAlgorithms as part of the core agent execution pipeline.
    Consumes MultiProviderAgenticGraderAlgorithm from vidbyte.context.algorithms.
Similar Files:
    - vidbyte/agents/algorithms/reflexion.py: A similar context-window agent runtime algorithm.
"""

from __future__ import annotations

import asyncio
import dataclasses
import os
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from vidbyte.context.algorithms.multi_provider_agentic_grader import MultiProviderAgenticGraderAlgorithm
from vidbyte.lib.config.constants import API_KEY_ENV_VARS
from vidbyte.lib.enums import ModelModality, ModelProvider
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError
from vidbyte.lib.agents.modality_detector import ModalityDetector
from vidbyte.lib.tracing import SpanContext
from vidbyte.strategies.types import BaseAgentContext, StrategyResult

if TYPE_CHECKING:
    from vidbyte.agents.runtime import AgentRuntime


DEFAULT_PROVIDER_MODELS = {
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-latest",
    "gemini": "gemini-1.5-pro",
    "xai": "grok-beta",
    "deepseek": "deepseek-chat",
    "glm": "glm-4",
    "minimax": "abab6.5-chat",
}


class MultiProviderAgenticGraderRuntimeAlgorithm:
    """Runtime implementation for the Multi-Provider Agentic Grader context-window algorithm."""

    name = "multi_provider_agentic_grader"

    def __init__(self, runtime: AgentRuntime, algorithm: MultiProviderAgenticGraderAlgorithm) -> None:
        # Initializes the Multi-Provider Agentic Grader runtime adapter.
        self.runtime = runtime
        self.algorithm = algorithm

    async def arun(self, message: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], runner_output_metadata: Callable[[object], Mapping[str, Any]], metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> StrategyResult:
        # Executes concurrent loops across providers and votes via the meta-grader.
        started_at = self.runtime.middleware.clock()
        active_models = self._resolve_active_models(options)

        async def run_single_provider(provider_name: str, model_name: str) -> StrategyResult:
            # Executes the agentic loop on a single provider concurrently and captures text output.
            trial_prompt = self.algorithm.agent_system_prompt_text(context.system_prompt or "")
            trial_context = dataclasses.replace(context, system_prompt=trial_prompt)
            p_runner = ModalityDetector.create_runner(
                modality=ModelModality.TEXT,
                provider=provider_name,
                model=model_name,
            )
            captured_output = []
            def wrapped_output_text(r: object) -> str:
                # Intercepts raw runner output to capture final verbatim candidate response.
                txt = runner_output_text(r)
                captured_output.append(txt)
                return txt

            res = await self.runtime._arun_once(
                message,
                runner=p_runner,
                context=trial_context,
                provider=provider_name,
                invoke_runner=invoke_runner,
                runner_output_text=wrapped_output_text,
                runner_output_metadata=runner_output_metadata,
                metadata={
                    **dict(metadata or {}),
                    "context_window_algorithm": "multi_provider_agentic_grader",
                    "grader_stage": "agent_loop",
                    "loop_provider": provider_name,
                    "loop_model": model_name,
                },
                options=dict(options or {}),
                trace_context=trace_context,
            )
            if captured_output:
                res = dataclasses.replace(res, output=captured_output[-1])
            return res

        tasks = [run_single_provider(p_name, m_name) for p_name, m_name in active_models.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        candidates = {}
        total_tokens = 0
        call_contexts = []
        for (p_name, m_name), res in zip(active_models.items(), results):
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

        candidates_text = ""
        for p_name, text in candidates.items():
            candidates_text += f"### Model Provider: {p_name}\nCandidate Output:\n{text}\n\n"

        grader_prompt = self.algorithm.render_grader_prompt(message, candidates_text)
        grader_runner = ModalityDetector.create_runner(
            modality=ModelModality.TEXT,
            provider=self.algorithm.grader_provider,
            model=self.algorithm.grader_model,
        )

        raw_result, _ = await self.runtime._invoke_with_middleware(
            grader_runner,
            grader_prompt,
            {"system": self.algorithm.grader_system_prompt_text()},
            context=context,
            provider=self.algorithm.grader_provider,
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            iteration_count=0,
            model_call_count=0,
            call_contexts=(),
            tokens_used=None,
            started_at=started_at,
            metadata={
                **dict(metadata or {}),
                "context_window_algorithm": "multi_provider_agentic_grader",
                "grader_stage": "grade",
            },
            trace_context=trace_context,
        )

        if isinstance(raw_result, StrategyResult):
            return raw_result

        grader_output = runner_output_text(raw_result).strip()
        selected_output = grader_output
        selected_provider = "grader_raw"

        for p_name, text in candidates.items():
            if text.strip() in grader_output or grader_output in text.strip():
                selected_output = text
                selected_provider = p_name
                break

        res_metadata = {
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

        return StrategyResult(
            output=selected_output,
            strategy_name="multi_provider_agentic_grader",
            calls=tuple(call_contexts),
            metadata=res_metadata,
        )

    def _resolve_active_models(self, options: Mapping[str, Any] | None) -> dict[str, str]:
        # Resolves which model providers and models are active and available.
        opts = options or {}
        if self.algorithm.provider_models is not None:
            active_models = {}
            for provider_name, model_name in self.algorithm.provider_models.items():
                p_enum = ModelProvider(provider_name)
                env_var = API_KEY_ENV_VARS.get(p_enum)
                if env_var and not os.environ.get(env_var) and not opts.get("api_key"):
                    raise ConfigurationError(f"Missing API key for explicitly requested provider '{provider_name}'. Set {env_var}.")
                active_models[provider_name] = model_name
        else:
            active_models = {}
            for provider_name, model_name in DEFAULT_PROVIDER_MODELS.items():
                p_enum = ModelProvider(provider_name)
                env_var = API_KEY_ENV_VARS.get(p_enum)
                if env_var and os.environ.get(env_var):
                    active_models[provider_name] = model_name
            if not active_models:
                raise ConfigurationError("No model providers have API keys configured in the environment.")
        return active_models


__all__ = [
    "MultiProviderAgenticGraderRuntimeAlgorithm",
]

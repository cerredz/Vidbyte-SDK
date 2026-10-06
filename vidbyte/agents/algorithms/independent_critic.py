"""Context Protocol Header

Description:
    Executes the Independent Critic context-window algorithm for AgentRuntime.
Purpose:
    Produces one candidate, then reviews it inside a fresh allowlist-built
    runtime without producer history, middleware, options, or private state.
Architecture:
    - IndependentCriticRuntimeAlgorithm: Orchestrates producer and critic stages.
    - Reviewer projection helpers: Resolve explicit artifacts and detached tools.
    - Result helpers: Preserve the producer result and add bounded review metadata.
Key Functions:
    - arun: Runs the producer once and applies the configured review failure policy.
    - _run_review: Creates and invokes the isolated reviewer runtime.
    - _build_reviewer_context: Positively constructs the reviewer-visible context.
Relations:
    Instantiated by vidbyte.agents.context_algorithms. Consumes the immutable
    config from vidbyte.context.algorithms.independent_critic.
What Not To Do:
    Never copy or replace the producer context for reviewer use. Never inherit
    producer middleware/options, and never merge reviewer calls into top-level calls.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from vidbyte.context.algorithms.independent_critic import CriticFailurePolicy, IndependentCriticAlgorithm
from vidbyte.lib.agents.modality_detector import ModalityDetector
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.context import BaseAgentContext, BaseContext, ContextArtifact
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums import ModelModality
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError
from vidbyte.lib.tracing import SpanContext
from vidbyte.tools.catalog import Tools

if TYPE_CHECKING:
    from vidbyte.agents.runtime import AgentRuntime

_UNSAFE_REVIEWER_TOOL_MODULE_PREFIXES = (
    "vidbyte.tools.agent_tool",
    "vidbyte.tools.builtins.fork",
    "vidbyte.tools.builtins.handoff",
    "vidbyte.tools.builtins.mcp",
    "vidbyte.tools.builtins.run_prompts_sequentially",
    "vidbyte.tools.builtins.sessions",
    "vidbyte.tools.mcp",
)


class IndependentCriticRuntimeAlgorithm:
    """Return-level runtime adapter for an isolated, review-only critic."""

    name = "independent_critic"

    def __init__(self, runtime: AgentRuntime, algorithm: IndependentCriticAlgorithm) -> None:
        # Retain the producer runtime only for its normal loop and shared infrastructure.
        self.runtime = runtime
        self.algorithm = algorithm

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        # Resolve explicit capabilities, produce once, then review without feeding findings back.
        self.runtime.recorder.append("system_prompt")
        artifacts = self._resolve_artifacts(context)
        tools = self._resolve_tools()
        candidate = await self._run_candidate(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)
        try:
            report, reviewer_result, reviewer_handle = await self._run_review(message, candidate.output, artifacts=artifacts, tools=tools, handle=handle, trace_context=trace_context)
            return self._with_review_metadata(candidate, report, reviewer_result, artifacts=artifacts, tools=tools, handle=reviewer_handle)
        except Exception as exc:
            self.runtime.recorder.append("independent_critic_failure")
            if self.algorithm.failure_policy is CriticFailurePolicy.RETURN_CANDIDATE:
                return self._with_failure_metadata(candidate, exc, artifacts=artifacts, tools=tools, handle=handle)
            raise AgentExecutionError(
                f"Independent critic review stage failed ({type(exc).__name__}): {self._bounded_error(exc)}",
                details={"algorithm": self.name, "stage": "review", "error_type": type(exc).__name__},
            ) from exc

    async def _run_candidate(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> AgentResult:
        # Preserve the producer's ordinary context, options, middleware, and result contract.
        self.runtime.recorder.append("independent_critic_candidate")
        return await self.runtime._arun_once(message, handle=handle, context=context, metadata=metadata, options=dict(options or {}), trace_context=trace_context)

    async def _run_review(self, task: str, candidate: str, *, artifacts: Sequence[ContextArtifact], tools: Tools, handle: RunnerHandle, trace_context: SpanContext | None) -> tuple[dict[str, Any], AgentResult, RunnerHandle]:
        # Invoke a fresh critic runtime whose only model-visible evidence is the rendered payload.
        self.runtime.recorder.append("independent_critic_review")
        review_prompt = self.algorithm.render_review_prompt(task, candidate, artifacts)
        reviewer_handle = self._reviewer_handle(handle)
        reviewer_runtime = self._build_reviewer_runtime(tools=tools)
        reviewer_context = self._build_reviewer_context(reviewer_runtime=reviewer_runtime)
        reviewer_result = await reviewer_runtime._arun_once(
            review_prompt,
            handle=reviewer_handle,
            context=reviewer_context,
            metadata={"context_window_algorithm": self.name, "independent_critic_stage": "review"},
            options={},
            trace_context=trace_context,
        )
        report_source = reviewer_result.structured if reviewer_result.structured is not None else reviewer_result.output
        return self.algorithm.normalize_review(report_source), reviewer_result, reviewer_handle

    def _build_reviewer_runtime(self, *, tools: Tools) -> AgentRuntime:
        # Construct a reviewer-local runtime with empty middleware and no implicit control tools.
        from vidbyte.agents.runtime import AgentRuntime

        return AgentRuntime(
            agent_name=f"{self.runtime.agent_name}:independent-critic",
            system_prompt=self.algorithm.reviewer_system_prompt_text(),
            tools=tools,
            permission_policy=self.runtime.permission_policy,
            config=AgentRuntimeConfig(
                max_iterations=self.algorithm.reviewer_max_iterations,
                max_tokens=self.algorithm.reviewer_max_tokens,
                max_tool_calls=self.algorithm.reviewer_max_tool_calls,
            ),
            tracer=self.runtime._tracer,
            middleware=(),
            algorithm=None,
            context_manager=None,
            recorder=self.runtime.recorder,
            output_schema=self.algorithm.review_output_schema(),
            output_contract=None,
            include_internal_tools=False,
        )

    def _build_reviewer_context(self, *, reviewer_runtime: AgentRuntime) -> BaseAgentContext:
        # Positively build a context so future producer-context fields remain excluded by default.
        base = BaseContext(system_prompt=self.algorithm.reviewer_system_prompt_text())
        return reviewer_runtime.build_context(
            "",
            base_context=base,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
            input_metadata={},
            modality=None,
            agentic_loop=False,
            context_items=(),
            context_manager=None,
        )

    def _resolve_artifacts(self, context: BaseAgentContext) -> tuple[ContextArtifact, ...]:
        # Select every permitted artifact by exact unique name without copying metadata.
        selected: list[ContextArtifact] = []
        for name in self.algorithm.allowed_artifact_names:
            matches = tuple(artifact for artifact in context.artifacts if artifact.name == name)
            if not matches:
                raise ConfigurationError(f"Independent critic artifact allowlist name {name!r} was not found.")
            if len(matches) > 1:
                raise ConfigurationError(f"Independent critic artifact allowlist name {name!r} is ambiguous ({len(matches)} matches).")
            artifact = matches[0]
            selected.append(ContextArtifact(name=artifact.name, artifact_type=artifact.artifact_type, content=artifact.content))
        return tuple(selected)

    def _resolve_tools(self) -> Tools:
        # Select exact producer tools, detach safe cloneable tools, and reject live-owner tools.
        selected = self.runtime.user_tools.subset(self.algorithm.allowed_tool_names)
        detached = tuple(self._detach_tool(tool) for tool in selected)
        return Tools(detached)

    def _detach_tool(self, tool: object) -> object:
        # Fail closed when an SDK tool can retain producer agent, session, or MCP authority.
        tool_name = str(getattr(tool, "name", tool.__class__.__name__))
        if self._tool_requires_owner(tool):
            raise ConfigurationError(
                f"Independent critic tool {tool_name!r} is agent/session/MCP-bound and cannot be isolated in version 1."
            )
        clone = getattr(tool, "clone_for_fork", None)
        if not callable(clone):
            return tool
        detached = clone()
        if detached is tool:
            raise ConfigurationError(f"Independent critic tool {tool_name!r} returned itself from clone_for_fork().")
        detached_name = str(getattr(detached, "name", detached.__class__.__name__))
        if detached_name != tool_name:
            raise ConfigurationError(f"Independent critic tool {tool_name!r} cloned to unexpected tool name {detached_name!r}.")
        if self._tool_requires_owner(detached):
            raise ConfigurationError(f"Independent critic tool {tool_name!r} remained agent/session/MCP-bound after clone_for_fork().")
        return detached

    @staticmethod
    def _tool_requires_owner(tool: object) -> bool:
        # Identify SDK and structural owner-binding surfaces that cannot cross the critic boundary.
        module_name = tool.__class__.__module__
        return module_name.startswith(_UNSAFE_REVIEWER_TOOL_MODULE_PREFIXES) or any(callable(getattr(tool, name, None)) for name in ("bind_agent", "bind_session", "bind_context_getter"))

    def _reviewer_handle(self, producer_handle: RunnerHandle) -> RunnerHandle:
        # Reuse only invocation transport by default, or create the explicit reviewer model.
        if self.algorithm.reviewer_provider is None:
            return producer_handle
        runner = ModalityDetector.create_runner(
            modality=ModelModality.TEXT,
            provider=self.algorithm.reviewer_provider,
            model=self.algorithm.reviewer_model or "",
        )
        return producer_handle.with_runner(runner, self.algorithm.reviewer_provider)

    def _with_review_metadata(self, candidate: AgentResult, review: Mapping[str, Any], reviewer_result: AgentResult, *, artifacts: Sequence[ContextArtifact], tools: Tools, handle: RunnerHandle) -> AgentResult:
        # Add bounded advisory findings while preserving every producer result field.
        metadata = dict(candidate.metadata)
        metadata[self.name] = {
            "status": "reviewed",
            "reviewed": True,
            "review_only": True,
            "candidate_revised": False,
            "adjudicated": False,
            "verdict": review["verdict"],
            "summary": review["summary"],
            "findings": review["findings"],
            "truncation": dict(review["truncation"]),
            "input_projection": self._input_projection(artifacts, tools),
            "reviewer": self._reviewer_metadata(reviewer_result, handle),
            "config_metadata": dict(self.algorithm.metadata),
        }
        return dataclasses.replace(candidate, metadata=metadata)

    def _with_failure_metadata(self, candidate: AgentResult, exc: Exception, *, artifacts: Sequence[ContextArtifact], tools: Tools, handle: RunnerHandle) -> AgentResult:
        # Mark fail-open output honestly without changing candidate text or producer accounting.
        metadata = dict(candidate.metadata)
        metadata[self.name] = {
            "status": "review_failed",
            "reviewed": False,
            "review_only": True,
            "candidate_revised": False,
            "adjudicated": False,
            "error": {"type": type(exc).__name__, "message": self._bounded_error(exc)},
            "input_projection": self._input_projection(artifacts, tools),
            "reviewer": {
                "provider": self.algorithm.reviewer_provider or handle.provider,
                "model": self.algorithm.reviewer_model or self.runtime._runner_model_name(handle.runner),
            },
            "config_metadata": dict(self.algorithm.metadata),
        }
        return dataclasses.replace(candidate, metadata=metadata)

    def _reviewer_metadata(self, result: AgentResult, handle: RunnerHandle) -> dict[str, Any]:
        # Publish reviewer-local counters and bounded structural call summaries only.
        metadata = dict(result.metadata)
        calls = tuple(metadata.get("tool_calls", ()))
        return {
            "provider": self.algorithm.reviewer_provider or handle.provider,
            "model": self.algorithm.reviewer_model or self.runtime._runner_model_name(handle.runner),
            "stop_reason": metadata.get("stop_reason"),
            "iteration_count": metadata.get("iteration_count", 0),
            "tool_call_count": metadata.get("tool_call_count", len(calls)),
            "tokens_used": metadata.get("tokens_used"),
            "tool_calls": tuple(self._reviewer_call_summary(call) for call in calls[: self.algorithm.reviewer_max_tool_calls]),
        }

    def _input_projection(self, artifacts: Sequence[ContextArtifact], tools: Tools) -> dict[str, Any]:
        # Describe the positive projection without copying task, candidate, or evidence content.
        return {
            "original_task": True,
            "candidate": True,
            "artifact_names": tuple(artifact.name for artifact in artifacts),
            "tool_names": tools.names(),
        }

    @staticmethod
    def _reviewer_call_summary(call: object) -> dict[str, Any]:
        # Keep reviewer calls separate from producer calls and omit arguments/results.
        state = getattr(call, "state", None)
        return {
            "tool_name": str(getattr(call, "tool_name", "unknown")),
            "state": str(getattr(state, "value", state or "unknown")),
            "iteration_count": getattr(call, "iteration_count", None),
        }

    def _bounded_error(self, exc: Exception) -> str:
        # Bound fail-open diagnostics so arbitrary provider text cannot inflate result metadata.
        text = str(exc)
        if len(text) <= self.algorithm.max_finding_chars:
            return text
        marker = "...[truncated]"
        return text[: max(0, self.algorithm.max_finding_chars - len(marker))] + marker


__all__ = [
    "IndependentCriticRuntimeAlgorithm",
]

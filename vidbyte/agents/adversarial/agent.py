"""Context Protocol Header

FILE:
    vidbyte/agents/adversarial/agent.py owns AdversarialAgent — a thin BaseAgent
    connector for the runnerless adversarial-review workflow.
PURPOSE:
    Wires the worker prototype, resolved AdversarialSettings, and an
    AdversarialContext together; builds the run controller; and owns the public
    surface — generate_reply normalization, the single committed turn, tracing,
    card(), fork(), last_result, and the runnerless capability boundary. The staged
    sequencing itself lives in runtime.py; this class delegates rather than embeds.
ROLE IN CODEBASE:
    Reached through vidbyte.agents exports and AgentClient.adversarial(). Delegates
    one run to _AdversarialRunController and commits its outcome as one agent turn.
ARCHITECTURE NOTE:
    The facade owns identity and lifecycle. Run-local child forks own model
    execution, tools, middleware, permissions, context, and MCP resources. It has
    no runner/provider/model/API-key parameter or **kwargs, by contract.
COMMON MODIFICATION PATTERNS:
    Add a setting to AdversarialSettings (in vidbyte/lib/dataclasses/adversarial.py)
    and validate/enforce it there; include only a bounded safe summary in
    message/card metadata; document its call-cost implications. Change prompt
    envelopes only in AdversarialContext so child-call ordering stays independent
    of presentation details.
WHAT NOT TO DO IN THIS FILE:
    Do not add facade runner/provider/model ownership; configure worker/adversary.
    Do not attach facade tools or MCP servers; child agents own those capabilities.
    Do not embed round/loop orchestration here; it belongs to runtime.py.
FOLLOW-UP (deferred — runtime/strategy design):
    The worker=/adversary= two-peer constructor surface will be reconsidered when
    the reviewer-roster model is settled; do not harden that API shape yet.
KNOWN EDGE CASES:
    Specialized child prototypes must implement subtype-preserving fork(); ordinary
    BaseAgent.fork() intentionally produces BaseAgent. Blank replies count as
    failures. Repeated worker passes may repeat write-side effects. Forwarding
    truncation never truncates the full successful artifacts retained in last_result.
RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/adversarial-agent.md
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.agents.adversarial.context import AdversarialContext
from vidbyte.agents.adversarial.runtime import (
    _AdversarialRunController,
    _AdversarialRunOutcome,
    _AdversarialRunRequest,
)
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.types import AgentCard, AgentInput, AgentMessage
from vidbyte.context import BaseContext
from vidbyte.context.handoff import Handoff, MinimalHandoff
from vidbyte.lib.dataclasses.adversarial import AdversarialResult, AdversarialSettings
from vidbyte.lib.dataclasses.agents import AgentMetadata
from vidbyte.lib.enums import ModelModality
from vidbyte.lib.errors import AdversarialExecutionError, ConfigurationError
from vidbyte.lib.tracing import SpanContext, TracerBase
from vidbyte.tools.mcp.types import McpServerConfig, McpToolPermission
from vidbyte.trace.adversarial import AdversarialAgentTraceController


class AdversarialAgent(BaseAgent):
    """BaseAgent-compatible facade for sequential worker/adversary refinement."""

    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        worker: BaseAgent,
        adversary: BaseAgent,
        settings: AdversarialSettings | None = None,
        description: str = "",
        capabilities: Sequence[str] = (),
        agent_metadata: AgentMetadata | None = None,
        metadata: dict[str, Any] | None = None,
        tracer: type[TracerBase] | TracerBase | None = None,
        trace: type[TracerBase] | TracerBase | None = None,
    ) -> None:
        # Validate composition and initialize only facade identity, metadata, tracing, and lifecycle state.
        if not isinstance(worker, BaseAgent):
            raise ConfigurationError(
                "AdversarialAgent.worker must be a configured BaseAgent instance.",
                details={
                    "field": "worker",
                    "actual_type": type(worker).__name__,
                    "expected": "BaseAgent",
                },
            )
        if not isinstance(adversary, BaseAgent):
            raise ConfigurationError(
                "AdversarialAgent.adversary must be a configured BaseAgent instance.",
                details={
                    "field": "adversary",
                    "actual_type": type(adversary).__name__,
                    "expected": "BaseAgent",
                },
            )
        super().__init__(
            name=name,
            system_prompt=system_prompt,
            description=description,
            capabilities=capabilities,
            agent_metadata=agent_metadata,
            metadata=metadata,
            tracer=tracer,
            trace=trace,
        )
        self.worker = worker
        self.adversary = adversary
        self.settings = settings or AdversarialSettings()
        if not isinstance(self.settings, AdversarialSettings):
            raise ConfigurationError(
                "AdversarialAgent.settings must be an AdversarialSettings instance.",
                details={
                    "field": "settings",
                    "actual_type": type(self.settings).__name__,
                    "expected": "AdversarialSettings",
                },
            )
        self._context = AdversarialContext(self.settings)
        self.last_result: AdversarialResult | None = None

    # @intent worker-remains-final-authority
    # This facade improves a worker result through challenge and revision, but it never
    # lets reviewer text become the final answer directly. Reviewers may be mistaken,
    # malicious, stale, or unable to inspect the worker's actual artifacts. The same
    # run-local worker receives every review bundle, verifies the claims, and produces
    # the only result exposed as the facade reply. Preserve the one-final-history-entry
    # boundary: child transcripts stay on child forks while callers see a normal agent
    # turn with detailed full artifacts available separately through last_result.
    async def generate_reply(
        self,
        message: str | AgentInput,
        *,
        modality: ModelModality | str | None = None,
        context: BaseContext | None = None,
        history: Sequence[AgentMessage] = (),
        recipient: str = "orchestrator",
        **options: Any,
    ) -> AgentMessage:
        # Normalize one public request, delegate the staged run to the controller, and commit facade state only on full success.
        prompt, input_metadata = self._normalize_input(message)
        self._active_prompt = prompt
        self._behavior_view = None
        self.last_result = None
        trace_context: SpanContext | None = None
        trace_closed = False
        try:
            trace_metadata = dict(options.get("trace_metadata", {}) or {})
            trace_context = self._start_adversarial_trace(
                prompt, input_metadata, trace_metadata
            )
            request = _AdversarialRunRequest(
                message=message,
                original_prompt=prompt,
                modality=modality,
                context=context,
                history=(*tuple(history), *tuple(self.history)),
                options=dict(options),
            )
            adversarial_trace = AdversarialAgentTraceController()
            controller = _AdversarialRunController(
                facade_name=self.name,
                workflow_instructions=self.system_prompt,
                worker_prototype=self.worker,
                adversary_prototype=self.adversary,
                settings=self.settings,
                context=self._context,
                tracer=self._tracer,
                trace_context=trace_context,
                request=request,
                adversarial_trace=adversarial_trace,
            )
            outcome = await self._run_with_timeout(controller)
            reply = self._build_final_reply(outcome, recipient, adversarial_trace)
            self._tracer.end_trace(trace_context, output=outcome.result.final_output)
            trace_closed = True
            self._commit_success(prompt, reply, outcome)
            self._notify_session(reply)
            if self._queued_prompts and not self._draining_queued_prompts:
                await self._drain_queued_prompts(reply.metadata)
            return reply
        except (AdversarialExecutionError, ConfigurationError) as exc:
            if trace_context is not None and not trace_closed:
                self._tracer.end_trace(trace_context, error=exc)
            raise
        except Exception as exc:
            if trace_context is not None and not trace_closed:
                self._tracer.end_trace(trace_context, error=exc)
            raise AdversarialExecutionError(
                f"AdversarialAgent '{self.name}' failed to complete its staged run.",
                details={
                    "file": "vidbyte/agents/adversarial/agent.py",
                    "function": "AdversarialAgent.generate_reply",
                    "facade": self.name,
                    "phase": "facade_orchestration",
                    "error_type": type(exc).__name__,
                    "expected": "a complete initial pass and every configured review/revision round",
                    "remediation": "Inspect the chained exception and child traces; child execution configuration lives on worker/adversary.",
                },
            ) from exc
        except BaseException as exc:
            if trace_context is not None and not trace_closed:
                self._tracer.end_trace(trace_context, error=exc)
            raise
        finally:
            self._active_prompt = ""

    def fork(
        self,
        *,
        name: str | None = None,
        system_prompt: str | None = None,
        metadata: dict[str, Any] | None = None,
        include_history: bool = False,
    ) -> AdversarialAgent:
        # Rebuild the runnerless facade with the same prototypes/settings and optional public transcript copy.
        merged_metadata = {**self.metadata, **dict(metadata or {})}
        child = type(self)(
            name=name or self.name,
            system_prompt=self.system_prompt
            if system_prompt is None
            else system_prompt,
            worker=self.worker,
            adversary=self.adversary,
            settings=self.settings,
            description=self.description,
            capabilities=self.capabilities,
            agent_metadata=self.agent_metadata,
            metadata=merged_metadata,
            tracer=self._tracer,
        )
        if include_history:
            child.history = list(self.history)
        return child

    def card(self) -> AgentCard:
        # Project worker capabilities through the facade without exposing child execution objects or prompts.
        worker_card = self.worker.card()
        adversarial_metadata = {
            "worker_name": self.worker.name,
            "adversary_name": self.adversary.name,
            "num_adversaries": self.settings.num_adversaries,
            "adversarial_rounds": self.settings.adversarial_rounds,
            "min_successful_adversaries": self.settings.min_successful_adversaries,
            "per_adversary_timeout": self.settings.per_adversary_timeout,
            "max_review_chars": self.settings.max_review_chars,
            "max_worker_output_chars": self.settings.max_worker_output_chars,
            "specialty_count": len(self.settings.specialties),
            "fresh_adversaries_each_round": self.settings.fresh_adversaries_each_round,
            "run_timeout_seconds": self.settings.run_timeout_seconds,
            "max_child_calls": self.settings.max_child_calls,
        }
        return AgentCard(
            name=self.name,
            description=self.description,
            system_prompt=self.system_prompt,
            capabilities=self.capabilities or worker_card.capabilities,
            tool_names=worker_card.tool_names,
            mcp_tool_names=worker_card.mcp_tool_names,
            mcp_server_names=worker_card.mcp_server_names,
            metadata={**self.metadata, "adversarial": adversarial_metadata},
        )

    def add_tool(self, tool: object) -> AdversarialAgent:
        # Reject facade tool mutation before catalog/binding side effects can occur.
        raise self._facade_capability_error(
            "add_tool", "worker.add_tool(...) or adversary.add_tool(...)"
        )

    async def handoff(
        self, spec: Handoff | None = None, *, by: BaseAgent | None = None
    ) -> Handoff:
        # Use an explicit generator when supplied, otherwise derive handoff execution from the worker prototype.
        from vidbyte.agents.handoff import HandoffAgent

        resolved = spec or MinimalHandoff()
        generator = by or HandoffAgent.from_source_agent(self.worker, resolved)
        return await generator.generate_handoff(HandoffAgent.render_source_run(self))

    async def attach_mcp_server(
        self,
        command: Sequence[str],
        *,
        name: str | None = None,
        permission: McpToolPermission = McpToolPermission.EXECUTE,
        env: Mapping[str, str] | None = None,
        timeout: float = 30.0,
    ) -> AdversarialAgent:
        # Reject direct MCP ownership before a subprocess can be started.
        raise self._facade_capability_error(
            "attach_mcp_server",
            "worker.attach_mcp_server(...) or adversary.attach_mcp_server(...)",
        )

    async def attach_preset_mcp_server(
        self,
        preset_name: str,
        *,
        name: str | None = None,
        permission: McpToolPermission = McpToolPermission.EXECUTE,
        env: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        extra_args: Sequence[str] | None = None,
    ) -> AdversarialAgent:
        # Reject direct preset MCP ownership before registry lookup or subprocess startup.
        raise self._facade_capability_error(
            "attach_preset_mcp_server",
            "worker.attach_preset_mcp_server(...) or adversary.attach_preset_mcp_server(...)",
        )

    async def attach_mcp_servers(
        self, servers: Sequence[McpServerConfig]
    ) -> AdversarialAgent:
        # Reject batch MCP ownership before any concurrent startup side effects.
        raise self._facade_capability_error(
            "attach_mcp_servers",
            "worker.attach_mcp_servers(...) or adversary.attach_mcp_servers(...)",
        )

    def with_mcp_server(
        self,
        command: Sequence[str],
        *,
        name: str | None = None,
        permission: McpToolPermission = McpToolPermission.EXECUTE,
        env: Mapping[str, str] | None = None,
        timeout: float = 30.0,
    ) -> AdversarialAgent:
        # Reject deferred MCP ownership before pending facade configuration is mutated.
        raise self._facade_capability_error(
            "with_mcp_server",
            "worker.with_mcp_server(...) or adversary.with_mcp_server(...)",
        )

    def with_preset_mcp_server(
        self,
        preset_name: str,
        *,
        name: str | None = None,
        permission: McpToolPermission = McpToolPermission.EXECUTE,
        env: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        extra_args: Sequence[str] | None = None,
    ) -> AdversarialAgent:
        # Reject deferred preset MCP ownership before pending facade configuration is mutated.
        raise self._facade_capability_error(
            "with_preset_mcp_server",
            "worker.with_preset_mcp_server(...) or adversary.with_preset_mcp_server(...)",
        )

    def _start_adversarial_trace(
        self,
        prompt: str,
        input_metadata: Mapping[str, Any],
        trace_metadata: Mapping[str, Any],
    ) -> SpanContext:
        # Open one facade trace with child identities and settings, excluding raw review content and secrets.
        metadata = {
            **self.metadata,
            **dict(input_metadata),
            **dict(trace_metadata),
            "worker_name": self.worker.name,
            "adversary_name": self.adversary.name,
            "num_adversaries": self.settings.num_adversaries,
            "adversarial_rounds": self.settings.adversarial_rounds,
            "specialty_count": len(self.settings.specialties),
            "fresh_adversaries_each_round": self.settings.fresh_adversaries_each_round,
            "run_timeout_seconds": self.settings.run_timeout_seconds,
            "max_child_calls": self.settings.max_child_calls,
        }
        return self._tracer.start_trace(
            "agent.run",
            agent_name=self.name,
            run_id=self.worker.runner_config.run_id,
            strategy="adversarial",
            prompt=self._safe_trace_value(prompt),
            system_prompt=self._safe_trace_value(self.system_prompt),
            tools=self._safe_trace_value(self.worker._trace_tool_specs()),
            provider=self.worker.runner_config.provider,
            model=self.worker.runner_config.model_name,
            metadata=self._safe_trace_value(metadata),
        )

    async def _run_with_timeout(
        self, controller: _AdversarialRunController
    ) -> _AdversarialRunOutcome:
        """Run the controller and convert a total timeout into a safe SDK error."""

        timeout = self.settings.run_timeout_seconds
        if timeout is None:
            return await controller.run()
        try:
            return await asyncio.wait_for(controller.run(), timeout=timeout)
        except TimeoutError as exc:
            raise AdversarialExecutionError(
                f"AdversarialAgent '{self.name}' exceeded its configured run timeout.",
                details={
                    "file": "vidbyte/agents/adversarial/agent.py",
                    "function": "AdversarialAgent._run_with_timeout",
                    "facade": self.name,
                    "phase": "run_timeout",
                    "run_timeout_seconds": timeout,
                    "expected": "active adversarial controller work to complete within run_timeout_seconds",
                    "remediation": "Increase run_timeout_seconds or reduce reviewer count, rounds, and child workload.",
                },
            ) from exc

    def _build_final_reply(
        self,
        outcome: _AdversarialRunOutcome,
        recipient: str,
        adversarial_trace: AdversarialAgentTraceController | None = None,
    ) -> AgentMessage:
        # Preserve the final worker's metadata and add only a bounded workflow + custom-trace summary.
        summary = {
            **dict(outcome.result.metadata),
            "successful_review_count": outcome.result.successful_review_count,
            "failed_review_count": outcome.result.failed_review_count,
        }
        if adversarial_trace is not None:
            summary["adversarial_trace"] = adversarial_trace.metadata()
        if outcome.adversarial_trace:
            summary["adversarial_trace_artifact"] = {
                "worker_name": outcome.adversarial_trace.get("worker_name"),
                "adversary_name": outcome.adversarial_trace.get("adversary_name"),
                "worker_event_count": len(
                    outcome.adversarial_trace.get("worker_events") or []
                ),
                "adversary_event_count": len(
                    outcome.adversarial_trace.get("adversary_events") or []
                ),
                "current_status": outcome.adversarial_trace.get("current_status"),
            }
        metadata = {**dict(outcome.final_worker_reply.metadata), "adversarial": summary}
        return AgentMessage(
            sender=self.name,
            recipient=recipient,
            content=outcome.result.final_output,
            metadata=metadata,
        )

    def _commit_success(
        self, prompt: str, reply: AgentMessage, outcome: _AdversarialRunOutcome
    ) -> None:
        # Publish one facade turn only after every configured child stage has completed successfully.
        self.history.append(reply)
        self.last_prompt = prompt
        self.last_reply = reply
        self.last_result = outcome.result
        self._tool_call_contexts.extend(outcome.tool_call_contexts)

    def _facade_capability_error(
        self, operation: str, remediation: str
    ) -> ConfigurationError:
        # Centralize actionable runnerless-boundary diagnostics for unsupported facade mutation.
        return ConfigurationError(
            f"AdversarialAgent '{self.name}' cannot perform facade-level {operation}; configure a child agent instead.",
            details={
                "facade": self.name,
                "operation": operation,
                "expected_owner": "worker or adversary child agent",
                "remediation": remediation,
            },
        )

"""Context Protocol Header

Description:
    Implements the Multi-Provider Aggregator (Mixture-of-Agents) engine and the
    AggregateAgent class that exposes it as a first-class SDK agent.
Purpose:
    Fans a request out to several proposer models concurrently and routes their
    candidate answers to a final aggregator model that synthesizes a new response
    grounded in all of them (it composes its own answer, it does not select one).
Architecture:
    - MultiProviderAggregator: Pure async orchestration over agent-like objects.
    - AggregateResult: Frozen carrier for the synthesized content and metadata.
    - AggregateAgent: BaseAgent subclass that builds proposer/aggregator child
      agents from ProposerSpecs and runs the engine inside generate_reply.
Relations:
    Sibling of vidbyte/agents/algorithms/multi_provider_agentic_grader.py, which
    selects a winning candidate instead of synthesizing a new answer. Reused by
    BaseAgent's native multi-model overload.
"""

from __future__ import annotations

import asyncio
import string
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.types import AgentInput, AgentMessage
from vidbyte.lib.dataclasses.agents import AgentMetadata
from vidbyte.lib.dataclasses.multi_agent import AggregateConfig, ProposerSpec
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import AggregateExecutionError, ConfigurationError
from vidbyte.lib.tracing import NullTracer, SpanContext, TracerBase
from vidbyte.middleware import AgentMiddleware
from vidbyte.prompts import Prompts
from vidbyte.tools.catalog import Tools

_REQUIRED_TEMPLATE_PLACEHOLDERS = {"request", "candidates"}
_TRUNCATION_MARKER = "\n...[truncated]"


@dataclass(frozen=True, slots=True)
class AggregateResult:
    """Result of one aggregate run: the synthesized answer plus per-candidate detail."""

    content: str
    candidates: Mapping[str, str]
    metadata: Mapping[str, Any] = field(default_factory=dict)


class MultiProviderAggregator:
    """Fans a prompt out to labeled proposer agents and synthesizes their outputs via an aggregator agent."""

    def __init__(self, proposers: Sequence[tuple[str, Any]], aggregator: Any, config: AggregateConfig, prompt_template: str, tracer: TracerBase | None = None) -> None:
        # Stores the labeled proposers, the aggregator agent, run config, and the validated synthesis template.
        if not proposers:
            raise ConfigurationError("MultiProviderAggregator requires at least one proposer.")
        self._validate_config(config)
        self._validate_template(prompt_template)
        self._proposers = tuple(proposers)
        self._aggregator = aggregator
        self._config = config
        self._prompt_template = prompt_template
        self._tracer = tracer or NullTracer()

    async def aggregate(self, prompt: str) -> AggregateResult:
        # Runs all proposers concurrently, collects survivors, and synthesizes one answer from them.
        span = self._tracer.start_span("aggregate.run", proposer_count=len(self._proposers), min_successful=self._config.min_successful)
        try:
            labeled_results = await self._run_proposers(prompt)
            candidates, failed_labels = self._collect_candidates(labeled_results)
            candidates_block = self._build_candidates_block(candidates)
            reply = await self._synthesize(prompt, candidates_block)
            result = self._build_result(reply, candidates, failed_labels)
            self._tracer.end_span(span, output=result.content)
            return result
        except BaseException as exc:
            self._tracer.end_span(span, error=exc)
            raise

    async def _run_proposers(self, prompt: str) -> list[tuple[str, Any]]:
        # Launches every proposer concurrently (bounded and timed if configured) and returns (label, result_or_exception).
        semaphore = asyncio.Semaphore(self._config.max_concurrency) if self._config.max_concurrency else None
        tasks = [self._run_one_proposer(agent, prompt, semaphore) for _label, agent in self._proposers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [(label, result) for (label, _agent), result in zip(self._proposers, results)]

    async def _run_one_proposer(self, agent: Any, prompt: str, semaphore: asyncio.Semaphore | None) -> Any:
        # Calls one proposer under the optional concurrency semaphore and per-proposer timeout.
        span = self._tracer.start_span("aggregate.proposer", agent_name=getattr(agent, "name", None))
        if semaphore is None:
            return await self._call_one_proposer_with_trace(agent, prompt, span)
        async with semaphore:
            return await self._call_one_proposer_with_trace(agent, prompt, span)

    async def _call_one_proposer_with_trace(self, agent: Any, prompt: str, span: SpanContext) -> Any:
        # Calls one proposer and closes its aggregate proposer span.
        try:
            result = await self._call_with_timeout(agent, prompt)
            self._tracer.end_span(span, output=self._reply_text(result))
            return result
        except BaseException as exc:
            self._tracer.end_span(span, error=exc)
            raise

    async def _call_with_timeout(self, agent: Any, prompt: str) -> Any:
        # Awaits the proposer's reply, enforcing per_proposer_timeout when one is set.
        if self._config.per_proposer_timeout is None:
            return await agent.generate_reply(prompt)
        return await asyncio.wait_for(agent.generate_reply(prompt), self._config.per_proposer_timeout)

    def _collect_candidates(self, labeled_results: Sequence[tuple[str, Any]]) -> tuple[dict[str, str], list[str]]:
        # Keeps non-blank successful replies as candidates and records the labels that failed.
        candidates: dict[str, str] = {}
        failed_labels: list[str] = []
        for label, result in labeled_results:
            text = "" if isinstance(result, BaseException) else self._reply_text(result).strip()
            if not text:
                failed_labels.append(label)
                continue
            candidates[label] = self._reply_text(result)
        if len(candidates) < self._config.min_successful:
            raise AggregateExecutionError(
                f"Aggregate run produced {len(candidates)} successful proposer(s); "
                f"min_successful={self._config.min_successful} required.",
                details={"failed_labels": failed_labels, "successful_labels": list(candidates)},
            )
        return candidates, failed_labels

    def _build_candidates_block(self, candidates: Mapping[str, str]) -> str:
        # Formats every surviving candidate into a labeled, per-candidate-truncated text block.
        blocks = [f"### Candidate [{label}]\n{self._truncate(text)}\n" for label, text in candidates.items()]
        return "\n".join(blocks)

    async def _synthesize(self, prompt: str, candidates_block: str) -> Any:
        # Renders the synthesis message and asks the aggregator agent to compose the final answer.
        span = self._tracer.start_span("aggregate.synthesis", candidate_chars=len(candidates_block))
        message = self._prompt_template.format(request=prompt, candidates=candidates_block)
        try:
            reply = await self._aggregator.generate_reply(message)
            self._tracer.end_span(span, output=self._reply_text(reply))
            return reply
        except BaseException as exc:
            self._tracer.end_span(span, error=exc)
            raise

    def _build_result(self, reply: Any, candidates: Mapping[str, str], failed_labels: Sequence[str]) -> AggregateResult:
        # Wraps the aggregator reply and per-candidate detail into an AggregateResult.
        metadata = {
            "aggregate": {
                "candidates": dict(candidates),
                "successful_labels": list(candidates),
                "failed_labels": list(failed_labels),
                "proposer_count": len(self._proposers),
            }
        }
        return AggregateResult(content=self._reply_text(reply), candidates=dict(candidates), metadata=metadata)

    def _truncate(self, text: str) -> str:
        # Caps a single candidate's text at max_candidate_chars, appending a truncation marker when cut.
        limit = self._config.max_candidate_chars
        if len(text) <= limit:
            return text
        return text[:limit] + _TRUNCATION_MARKER

    @staticmethod
    def _reply_text(reply: Any) -> str:
        # Extracts plain text from an AgentMessage-like reply, falling back to str().
        return getattr(reply, "content", None) if getattr(reply, "content", None) is not None else str(reply)

    @staticmethod
    def _validate_config(config: AggregateConfig) -> None:
        # Rejects nonsensical aggregate settings before any model call is made.
        if config.min_successful < 1:
            raise ConfigurationError("AggregateConfig.min_successful must be at least 1.")
        if config.max_candidate_chars <= 0:
            raise ConfigurationError("AggregateConfig.max_candidate_chars must be greater than zero.")
        if config.max_concurrency is not None and config.max_concurrency < 1:
            raise ConfigurationError("AggregateConfig.max_concurrency must be at least 1 when set.")
        if config.per_proposer_timeout is not None and config.per_proposer_timeout <= 0:
            raise ConfigurationError("AggregateConfig.per_proposer_timeout must be positive when set.")

    @staticmethod
    def _validate_template(template: str) -> None:
        # Ensures the synthesis template exposes the {request} and {candidates} placeholders.
        if not template or not template.strip():
            raise ConfigurationError("Aggregate synthesis template must be a non-empty string.")
        found = {name for _, name, _, _ in string.Formatter().parse(template) if name is not None}
        missing = _REQUIRED_TEMPLATE_PLACEHOLDERS - found
        if missing:
            raise ConfigurationError(f"Aggregate synthesis template is missing required placeholders: {sorted(missing)}.")


class AggregateAgent(BaseAgent):
    """A BaseAgent whose generate_reply fans out to multiple proposer models and synthesizes one answer."""

    def __init__(self, *, name: str, system_prompt: str, proposers: Sequence[ProposerSpec | tuple[str, ...] | Any], aggregator: ProposerSpec | tuple[str, ...] | Any | None = None, config: AggregateConfig | None = None, provider: str | None = None, model_name: str | None = None, api_key: str | None = None, agent_metadata: AgentMetadata | None = None, tools: Sequence[object] | Tools = (), middleware: Sequence[AgentMiddleware] = (), temperature: float | None = None, metadata: dict[str, Any] | None = None, tracer: type[TracerBase] | TracerBase | None = None, trace: type[TracerBase] | TracerBase | None = None) -> None:
        # Builds proposer and aggregator child agents from specs and wires them into a MultiProviderAggregator.
        super().__init__(name=name, system_prompt=system_prompt, agent_metadata=agent_metadata, metadata=metadata, tracer=tracer, trace=trace)
        if not proposers:
            raise ConfigurationError("AggregateAgent requires at least one proposer.")
        self._proposer_inputs = tuple(proposers)
        self._aggregator_input = aggregator
        self._config = config or AggregateConfig()
        self._proposer_provider_defaults = (provider, model_name)
        self._proposer_api_key = api_key
        self._proposer_tools = tools
        self._proposer_middleware = tuple(middleware)
        self._proposer_temperature = temperature
        labeled_proposers = self._build_proposers()
        aggregator_agent = self._build_aggregator()
        template = self._config.synthesis_prompt_template or Prompts().get(Prompt.MULTI_PROVIDER_AGGREGATOR_SYNTHESIS_PROMPT)
        self._engine = MultiProviderAggregator(labeled_proposers, aggregator_agent, self._config, template, tracer=self._tracer)

    async def generate_reply(self, message: str | AgentInput, **options: Any) -> AgentMessage:
        # Runs the aggregation engine on the prompt and returns the synthesized AgentMessage.
        prompt = self._coerce_prompt(message)
        self._active_prompt = prompt
        trace_ctx = self._tracer.start_trace("agent.run", agent_name=self.name, strategy="aggregate", prompt=self._safe_trace_value(prompt), system_prompt=self._safe_trace_value(self.system_prompt), metadata=self._safe_trace_value(self.metadata))
        try:
            result = await self._engine.aggregate(prompt)
            reply = AgentMessage(
                sender=self.name,
                recipient=str(options.get("recipient", "orchestrator")),
                content=result.content,
                metadata=dict(result.metadata),
            )
            self.history.append(reply)
            self.last_prompt = prompt
            self.last_reply = reply
            self._tracer.end_trace(trace_ctx, output=result.content)
            return reply
        except BaseException as exc:
            self._tracer.end_trace(trace_ctx, error=exc)
            raise
        finally:
            self._active_prompt = ""

    def fork(self, *, name: str | None = None, **_overrides: Any) -> AggregateAgent:
        # Rebuilds an equivalent AggregateAgent so as_tool() and delegation keep aggregating.
        return AggregateAgent(
            name=name or self.name,
            system_prompt=self.system_prompt,
            proposers=self._proposer_inputs,
            aggregator=self._aggregator_input,
            config=self._config,
            provider=self._proposer_provider_defaults[0],
            model_name=self._proposer_provider_defaults[1],
            api_key=self._proposer_api_key,
            agent_metadata=self.agent_metadata,
            tools=self._proposer_tools,
            middleware=self._proposer_middleware,
            temperature=self._proposer_temperature,
            metadata=dict(self.metadata),
            tracer=self._tracer,
        )

    def _build_proposers(self) -> list[tuple[str, Any]]:
        # Normalizes each proposer input into a (unique_label, agent) pair, building child agents from specs.
        labeled: list[tuple[str, Any]] = []
        used_labels: set[str] = set()
        for index, item in enumerate(self._proposer_inputs):
            spec = self._coerce_spec(item)
            if spec is None:
                label = self._unique_label(getattr(item, "name", None) or f"proposer-{index}", used_labels)
                labeled.append((label, item))
                continue
            label = self._unique_label(spec.label or f"{spec.provider}:{spec.model}", used_labels)
            labeled.append((label, self._build_proposer_agent(label, spec)))
        return labeled

    def _build_proposer_agent(self, label: str, spec: ProposerSpec) -> BaseAgent:
        # Constructs one proposer BaseAgent carrying this agent's tools, middleware, and temperature.
        return BaseAgent(
            name=f"{self.name}:proposer:{label}",
            system_prompt=spec.system_prompt or self.system_prompt,
            provider=spec.provider,
            model_name=spec.model,
            api_key=self._proposer_api_key,
            tools=self._proposer_tools,
            middleware=self._proposer_middleware,
            temperature=self._proposer_temperature,
            tracer=self._tracer,
        )

    def _build_aggregator(self) -> Any:
        # Resolves the aggregator into a tool-free synthesis agent, defaulting to this agent's own model.
        if self._aggregator_input is not None and self._coerce_spec(self._aggregator_input) is None:
            return self._aggregator_input
        spec = self._resolve_aggregator_spec()
        system_prompt = self._config.synthesis_system_prompt or Prompts().get(Prompt.MULTI_PROVIDER_AGGREGATOR_SYNTHESIS_SYSTEM_PROMPT)
        return BaseAgent(
            name=f"{self.name}:aggregator",
            system_prompt=system_prompt,
            provider=spec.provider,
            model_name=spec.model,
            api_key=self._proposer_api_key,
            tracer=self._tracer,
        )

    def _resolve_aggregator_spec(self) -> ProposerSpec:
        # Returns the explicit aggregator spec, or falls back to the host provider/model, erroring if neither resolves.
        spec = self._coerce_spec(self._aggregator_input) if self._aggregator_input is not None else None
        if spec is not None:
            return spec
        provider, model = self._proposer_provider_defaults
        if not provider or not model:
            raise ConfigurationError(
                "AggregateAgent could not resolve an aggregator: pass aggregator=... or provider/model_name.",
                details={"provider": provider, "model": model},
            )
        return ProposerSpec(provider=provider, model=model)

    def _coerce_prompt(self, message: str | AgentInput) -> str:
        # Extracts plain prompt text from a string or AgentInput for the aggregation engine.
        if isinstance(message, AgentInput):
            return message.prompt
        return message if isinstance(message, str) else str(message)

    @staticmethod
    def _coerce_spec(item: Any) -> ProposerSpec | None:
        # Converts a ProposerSpec or (provider, model[, label[, system_prompt]]) tuple into a ProposerSpec, else None.
        if isinstance(item, ProposerSpec):
            return item
        if isinstance(item, tuple) and len(item) >= 2 and all(isinstance(part, str) for part in item[:2]):
            return ProposerSpec(*item[:4])
        return None

    @staticmethod
    def _unique_label(base: str, used_labels: set[str]) -> str:
        # Returns a label unique within the run, suffixing duplicates with #2, #3, and so on.
        if base not in used_labels:
            used_labels.add(base)
            return base
        suffix = 2
        while f"{base}#{suffix}" in used_labels:
            suffix += 1
        label = f"{base}#{suffix}"
        used_labels.add(label)
        return label


__all__ = [
    "AggregateAgent",
    "AggregateResult",
    "MultiProviderAggregator",
]

"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the dedicated execution seam for the opinionated Jev agent: it runs the JevPreflightGate, then returns the gate's response, hands the run to the specialist the gate chose, or writes the run state with supplied prior user turns, applies the tool selector, and runs the inherited linear loop, whose finish attempts the enabled done checks may send back to work.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV to JevRuntime; JevAgent builds the gate, the JevRunState, the JevContinuation, and the JevResponse writer at construction and passes them in, and the runtime keeps run-local tool selection ahead of the inherited agent loop and answers AgentRuntime's finish-attempt hook by asking the JevContinuation whether to continue.
ARCHITECTURE NOTE: JevRuntime retains the standard runner, usage, speed, tracing, and session wiring while applying named policies internally. It wraps the whole run in JevUsageAccount.scope(), so every generative and decision call from this agent and every agent it spawns lands in this agent's one usage ledger, checks that ledger at each phase boundary, and fails the run closed when any usage cannot be recorded or priced.
COMMON MODIFICATION PATTERNS: Add fixed preflight, compute, or coordination phases around inherited execution while keeping their policy internal.
KNOWN EDGE CASES: With a managed decision config, the whole run is one managed run on Vidbyte's gateway and is closed when arun returns or raises. With no done check enabled there is no JevRunState, so no run state is written and every finish attempt stands. A gate with no fixed-question preset and no specialist performs no Jev call, and a closed gate never reaches the generative runner. A chosen specialist runs through its own agent, so neither this agent's tool selector nor its done checks apply to it. A disabled selector performs no Jev call; an unavailable selector keeps the original tool catalog. A plain BaseAgent(runtime="jev") has no JevRuntimeSettings, gate, or response writer and is refused here. With JevRuntimeSettings.compute set, the main agent's run calls the JevComputeController after every tool iteration that continues; a specialist's run does not.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-tool-selector.md, docs/design/jev-specialist-routing.md, docs/design/jev-multipart-done-criteria.md, docs/design/jev-cumulative-obligations-done-check.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, tests/test_jev_tool_selector.py, tests/test_jev_done.py, tests/test_jev_compute.py, and scripts/test-jev-tool-selector.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from vidbyte.agents.jev.compute import JevComputeController
from vidbyte.agents.jev.continuation import JevContinuation
from vidbyte.agents.jev.done import JevRunState
from vidbyte.agents.jev.gate import JevPreflightGate
from vidbyte.agents.jev.preflight import JevPreflightTools
from vidbyte.agents.jev.preload import JevPreload
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevRuntimeSettings
from vidbyte.agents.jev.usage import JevUsageAccount
from vidbyte.agents.runtime import AgentRuntime, BaseAgentRuntimeLoopState
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums.jev import JevPreflightPreset
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev.managed import JevManagedRun
from vidbyte.lib.tracing import SpanContext
from vidbyte.tools._internal import with_internal_agent_tools


class JevRuntime(AgentRuntime):
    """Linear runtime seam reserved for opinionated Jev capabilities."""

    def __init__(
        self,
        *,
        runtime_settings: JevRuntimeSettings | None = None,
        preflight: JevPreflightGate | None = None,
        run_state: JevRunState | None = None,
        continuation: JevContinuation | None = None,
        compute: JevComputeController | None = None,
        response: JevResponse | None = None,
        skill_preload: JevPreload | None = None,
        **kwargs: Any,
    ) -> None:
        # Retains the validated runtime settings, the gate, the done checks, the continuation, and the response writer JevAgent built, and delegates the loop to AgentRuntime.
        # @intent jev-runtime-needs-jev-agent
        # AgentRuntimeType.JEV is selectable by string, so a generic BaseAgent can reach this class
        # without them; refusing here names JevAgent instead of failing later on a None field.
        if (
            not isinstance(runtime_settings, JevRuntimeSettings)
            or not isinstance(preflight, JevPreflightGate)
            or not isinstance(response, JevResponse)
            or (skill_preload is not None and not isinstance(skill_preload, JevPreload))
        ):
            raise ConfigurationError(
                "The 'jev' runtime is only available through JevAgent; construct JevAgent(JevAgentSettings(...)) instead of BaseAgent(runtime='jev').",
                details={
                    "received_runtime_settings": type(runtime_settings).__name__,
                    "received_preflight": type(preflight).__name__,
                    "received_response": type(response).__name__,
                    "received_skill_preload": type(skill_preload).__name__,
                },
            )
        self.runtime_settings = runtime_settings
        self.preflight = preflight
        self.run_state = run_state
        self.continuation = continuation
        self.compute = compute
        self.response = response
        self.skill_preload = skill_preload
        super().__init__(**kwargs)
        self.usage = JevUsageAccount(self.usage_tracker, self.agent_name)

    async def arun(
        self,
        message: str,
        *,
        handle: RunnerHandle,
        context: BaseAgentContext,
        metadata: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
        trace_context: SpanContext | None = None,
    ) -> AgentResult:
        """Run one managed gateway scope with this JevAgent's usage ledger active for every phase."""
        # @intent one-agent-run-is-one-managed-run
        # Every Jev call shares one X-Vidbyte-Run-Id, while every generative and decision call is added to this
        # agent's ledger. The nested contexts restore independently, and the gateway closes after accounting settles.
        async with JevManagedRun(self.runtime_settings.decision):
            with self.usage.scope():
                return await self._arun_metered(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context)

    async def _arun_metered(
        self,
        message: str,
        *,
        handle: RunnerHandle,
        context: BaseAgentContext,
        metadata: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
        trace_context: SpanContext | None = None,
    ) -> AgentResult:
        # Runs every phase with the ledger open, checking it before each phase that spends more.
        # @intent closed-gate-never-reaches-the-model
        # A closed gate returns without invoking the generative runner, so an unclear request is answered
        # with questions before any generative tokens are spent.
        self.response.start(message)
        if not await self.preflight.pass_(message):
            return self.response.stopped(self.usage.settle())
        self.usage.require_accounted()
        if self.preflight.specialist is not None:
            reply = await self.preflight.specialist.agent.arun(message)
            return self.response.delegated(reply, self.usage.settle())
        context, options = await self._preload_skills(message, context, options)
        self.usage.require_accounted()
        if self.compute is not None:
            self.compute.begin(message)
        if self.run_state is not None:
            await self.run_state.begin(message, prior_user_turns=self._prior_user_turns(context.history))
            self.usage.require_accounted()
            sequence_instructions = self.run_state.agent_instructions()
            if sequence_instructions:
                context = replace(context, system_prompt=f"{context.system_prompt or ''}\n\n{sequence_instructions}")
        if JevPreflightPreset.TOOL_SELECTOR not in self.runtime_settings.preflight:
            result = await super().arun(
                message,
                handle=handle,
                context=context,
                metadata=metadata,
                options=options,
                trace_context=trace_context,
            )
            return self.response.finished(result, self.usage.settle())

        candidate_tool_count = len(self.user_tools)
        selector = JevPreflightTools(
            self.runtime_settings.decision,
            self.runtime_settings.tool_selector_threshold,
        )
        self.user_tools = await selector.run(message, self.user_tools)
        self.usage.require_accounted()
        self.tools = with_internal_agent_tools(self.user_tools)
        context = replace(context, tools=self.tools.specs())
        run_options = dict(options or {})
        run_options.pop("tools", None)
        result = await super().arun(
            message,
            handle=handle,
            context=context,
            metadata=metadata,
            options=run_options,
            trace_context=trace_context,
        )
        selector_metadata: dict[str, Any] = {
            "available": selector.available,
            "candidate_tool_count": candidate_tool_count,
            "selected_tool_count": len(self.user_tools),
        }
        if selector.usage is not None:
            selector_metadata["usage"] = {
                "model": selector.model,
                "input_tokens": selector.usage.input_tokens,
                "output_tokens": selector.usage.output_tokens,
            }
        return self.response.finished(replace(
            result,
            metadata={
                **dict(result.metadata),
                "jev_tool_selector": selector_metadata,
            },
        ), self.usage.settle())

    async def _preload_skills(self, message: str, context: BaseAgentContext, options: Mapping[str, Any] | None) -> tuple[BaseAgentContext, Mapping[str, Any] | None]:
        # @intent explicit-system-option-is-the-effective-skill-baseline
        # An explicit provider override remains the caller's baseline, with selected skill text appended in the run context and provider option.
        if self.skill_preload is None:
            return context, options
        run_options = dict(options or {})
        explicit_system = run_options.get("system")
        has_system_override = isinstance(explicit_system, str)
        if has_system_override:
            context = replace(context, system_prompt=explicit_system)
        context = await self.skill_preload.run(message, context)
        if has_system_override:
            run_options["system"] = context.system_prompt
        outcome = self.response.state.skills
        if outcome is None:
            raise ConfigurationError("The Jev skill preload did not record its outcome.")
        run_options["claude_skills"] = outcome.claude_skills
        run_options["claude_skill_session"] = None
        return context, run_options

    @staticmethod
    def _prior_user_turns(history: Sequence[object]) -> tuple[str, ...]:
        """Keep only caller-provided user messages; BaseAgent also places its own replies in context history."""
        # @intent completion-requires-the-users-turns
        # Earlier user requirements remain binding when later turns add detail or move to another topic. The
        # same history also contains this agent's prior replies, so only messages explicitly sent by the user
        # may define obligations or explicitly cancel them.
        return tuple(
            message.content
            for message in history
            if isinstance(message, AgentMessage) and message.sender.casefold() == "user" and message.content.strip()
        )

    async def _continue_finish_attempt(self, result: AgentResult, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> bool:
        """Ask the continuation whether this finish attempt continues the loop, and let it shape what the main agent reads next."""
        # @intent continuation-logic-lives-in-the-continuation
        # The owner asked the runtime to only ask "should we continue?" and then "continue", so every reason to
        # continue and every message it sends lives in a JevContinuation subclass, never in this runtime.
        if self.continuation is None or not await self.continuation.should_continue(result.output, state.iteration_outputs, state.call_contexts):
            return False
        self.usage.require_accounted()
        extra_iterations, extra_tokens, extra_tool_calls = self.continuation.budget_extension()
        limits: dict[str, int] = {}
        granted: dict[str, int] = {}
        for field_name, extra in (
            ("max_iterations", extra_iterations),
            ("max_tokens", extra_tokens),
            ("max_tool_calls", extra_tool_calls),
        ):
            configured = getattr(self.config, field_name)
            if configured is not None and extra:
                limits[field_name] = configured + extra
                granted[field_name] = extra
        if limits:
            # The runtime is run-local; expand only configured ceilings before the same loop consumes the continuation.
            self.config = replace(self.config, **limits)
            self.response.continuation_budget(granted)
        evidence = self.continuation.continue_(messages)
        if evidence is not None and self.run_state is not None:
            self.run_state.add_continuation_evidence(evidence)
        return True


    async def _after_tool_iteration(self, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> None:
        """Hand the mid-run compute checkpoint the live loop state after each tool iteration that continues the run."""
        # @intent the-runtime-only-forwards-the-checkpoint
        # Every mid-run compute step lives in JevComputeController, so adding one never adds a branch here; without
        # compute settings there is no controller and the loop runs exactly as the linear runtime does.
        if self.compute is not None:
            await self.compute.checkpoint(state, messages)
            self.usage.require_accounted()


__all__ = ["JevRuntime"]

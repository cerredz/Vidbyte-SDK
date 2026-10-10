"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the dedicated execution seam for the opinionated Jev agent: it runs the JevPreflightGate, then returns the gate's response, hands the run to the specialist the gate chose, or applies the enabled run-local setup phases (prompt and tool alignment, skill preload, run state, tool selector, and bulk work) before running the inherited linear loop, whose finish attempts the enabled done checks may send back to work.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV to JevRuntime; JevAgent builds the gate, the alignment helper, the skill preload, the bulk-work coordinator, the JevRunState, the JevContinuation, and the JevResponse writer at construction and passes them in, and the runtime answers AgentRuntime's finish-attempt hook by asking the JevContinuation whether to continue.
ARCHITECTURE NOTE: JevRuntime retains the standard runner, usage, speed, tracing, and session wiring while applying named policies internally. It wraps the whole run in JevUsageAccount.scope(), so every generative and decision call from this agent and every agent it spawns lands in this agent's one usage ledger, checks that ledger at each phase boundary, and fails the run closed when any usage cannot be recorded or priced. Run-local system prompt and tool mutations are restored on every exit so repeated calls do not inherit another run's alignment.
COMMON MODIFICATION PATTERNS: Add fixed preflight, compute, or coordination phases around inherited execution while keeping their policy internal.
KNOWN EDGE CASES: With a managed decision config, the whole run is one managed run on Vidbyte's gateway and is closed when arun returns or raises. With no done check and no run-state relation there is no JevRunState, so no run state is written and every finish attempt stands. A gate with no fixed-question preset and no specialist performs no Jev call, and a closed gate never reaches the generative runner. A chosen specialist runs through its own agent, so this agent's alignment, selector, bulk work, and done checks do not apply to it. A disabled selector performs no Jev call; an unavailable selector keeps the original tool catalog. Alignment sessions close even when the main run fails. A plain BaseAgent(runtime="jev") has no JevRuntimeSettings, gate, or response writer and is refused here. With JevRuntimeSettings.compute set, the main agent's run calls the JevComputeController after every tool iteration that continues; a specialist's run does not.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-preflight-clarity.md, docs/design/jev-tool-selector.md, docs/design/jev-specialist-routing.md, docs/design/jev-multipart-done-criteria.md, docs/design/jev-cumulative-obligations-done-check.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_preflight.py, tests/test_jev_tool_selector.py, tests/test_jev_done.py, tests/test_jev_compute.py, tests/test_jev_runtime_setup_integration.py, and scripts/test-jev-tool-selector.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from vidbyte.agents.jev.alignment import (
    JevAgentAlignment,
    JevAlignmentResult,
    JevAlignmentStatus,
    JevToolAlignmentResult,
    JevToolAlignmentStatus,
    JevToolAttachment,
)
from vidbyte.agents.jev.bulk_work import JevBulkWork
from vidbyte.agents.jev.compute import JevComputeController
from vidbyte.agents.jev.continuation import JevContinuation
from vidbyte.agents.jev.done import JevRunState
from vidbyte.agents.jev.gate import JevPreflightGate
from vidbyte.agents.jev.preflight import JevPreflightTools
from vidbyte.agents.jev.preload import JevPreload
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAlignmentSettings, JevRuntimeSettings
from vidbyte.agents.jev.usage import JevUsageAccount
from vidbyte.agents.runtime import AgentRuntime, BaseAgentRuntimeLoopState
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.jev import JevBulkWorkResult
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums.jev import JevPreflightPreset
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev.managed import JevManagedRun
from vidbyte.lib.tracing import SpanContext
from vidbyte.tools._internal import with_internal_agent_tools

_SCOPE_ANSWERED = frozenset({JevAlignmentStatus.ALIGNED, JevAlignmentStatus.NO_GAPS, JevAlignmentStatus.EDITS_REJECTED})


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
        alignment: JevAgentAlignment | None = None,
        alignment_settings: JevAlignmentSettings | None = None,
        skill_preload: JevPreload | None = None,
        bulk_work: JevBulkWork | None = None,
        **kwargs: Any,
    ) -> None:
        # @intent jev-runtime-invariants-are-validated-at-construction
        # The factory is the supported construction path, and skill preload must accompany nonempty validated skill settings.
        # Retains the validated runtime settings, the gate, the done checks, the continuation, and the response writer JevAgent built, and delegates the loop to AgentRuntime.
        # @intent jev-runtime-needs-jev-agent
        # AgentRuntimeType.JEV is selectable by string, so a generic BaseAgent can reach this class
        # without them; refusing here names JevAgent instead of failing later on a None field.
        if (
            not isinstance(runtime_settings, JevRuntimeSettings)
            or not isinstance(preflight, JevPreflightGate)
            or not isinstance(response, JevResponse)
            or not isinstance(bulk_work, JevBulkWork)
            or not isinstance(alignment_settings, JevAlignmentSettings)
            or (alignment is not None and not isinstance(alignment, JevAgentAlignment))
            or (alignment is None and (alignment_settings.system_prompt or alignment_settings.tool_settings))
            or (skill_preload is not None and not isinstance(skill_preload, JevPreload))
            or (alignment_settings.skills and not isinstance(skill_preload, JevPreload))
        ):
            raise ConfigurationError(
                "The 'jev' runtime is only available through JevAgent; construct JevAgent(JevAgentSettings(...)) instead of BaseAgent(runtime='jev').",
                details={
                    "received_runtime_settings": type(runtime_settings).__name__,
                    "received_preflight": type(preflight).__name__,
                    "received_response": type(response).__name__,
                    "received_alignment": type(alignment).__name__,
                    "received_skill_preload": type(skill_preload).__name__,
                    "received_bulk_work": type(bulk_work).__name__,
                },
            )
        self.runtime_settings = runtime_settings
        self.preflight = preflight
        self.run_state = run_state
        self.continuation = continuation
        self.compute = compute
        self.response = response
        self.alignment = alignment
        self.alignment_settings = alignment_settings
        self.skill_preload = skill_preload
        self.bulk_work = bulk_work
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
        # @intent each-run-owns-alignment-and-skill-context
        # Temporary prompts and tools are scoped to this call; preflight reads the persistent run-state record, not the reset response.
        # @intent closed-gate-never-reaches-the-model
        # A closed gate returns without invoking the generative runner, so an unclear request is answered
        # with questions before any generative tokens are spent.
        self.response.start(message)
        run_state_record = None if self.run_state is None else self.run_state.record
        if not await self.preflight.pass_(message, run_state_record):
            return self.response.stopped(self.usage.settle())
        self.usage.require_accounted()
        if self.preflight.specialist is not None:
            return await self._delegate(message, context)

        alignment = self.alignment
        prompt_result: JevAlignmentResult | None = None
        attachment: JevToolAttachment | None = None
        original_system_prompt = self.system_prompt
        original_user_tools = self.user_tools
        original_tools = self.tools
        try:
            if alignment is not None and self.alignment_settings.system_prompt:
                prompt_result, context = await self._align(alignment, message, context)
                self.response.alignment(prompt_result)
                self.usage.require_accounted()
            if alignment is not None and self.alignment_settings.tool_settings:
                attachment = await self._align_tools(alignment, message, prompt_result)
                self.response.tool_alignment(attachment.result)
                self.usage.require_accounted()
                context, options = self._with_attached_tools(attachment, context, options)

            context, options = await self._preload_skills(message, context, options)
            self.usage.require_accounted()

            context = await self._begin_run_state(message, context)
            context, options, selector_metadata = await self._select_tools(message, context, options)
            context, bulk_outcome = await self._run_bulk_work(message, context)
            context, options = self._prepare_bulk_synthesis(context, options, bulk_outcome)

            result = await super().arun(
                message,
                handle=handle,
                context=context,
                metadata=metadata,
                options=options,
                trace_context=trace_context,
            )
            if attachment is not None and attachment.result.summary():
                result = replace(result, output=self._announced(result, attachment))
            if selector_metadata is not None:
                result = replace(result, metadata={**dict(result.metadata), "jev_tool_selector": selector_metadata})
            return self.response.finished(result, self.usage.settle())
        finally:
            self.system_prompt = original_system_prompt
            self.user_tools = original_user_tools
            self.tools = original_tools
            if attachment is not None and alignment is not None:
                await alignment.release_tools(attachment)

    async def _delegate(self, message: str, context: BaseAgentContext) -> AgentResult:
        # Applies the run-state relation policy before handing the request to the specialist the gate chose.
        if self.run_state is not None:
            await self.run_state.begin_delegated(message, prior_user_turns=self._prior_user_turns(context.history))
            self.usage.require_accounted()
        reply = await self.preflight.specialist.agent.arun(message)
        return self.response.delegated(reply, self.usage.settle())

    async def _begin_run_state(self, message: str, context: BaseAgentContext) -> BaseAgentContext:
        # Starts the compute checkpoint and writes the run state, adding any required-sequence instructions to the run prompt.
        if self.compute is not None:
            self.compute.begin(message)
        if self.run_state is None:
            return context
        await self.run_state.begin(message, prior_user_turns=self._prior_user_turns(context.history))
        self.usage.require_accounted()
        sequence_instructions = self.run_state.agent_instructions()
        if not sequence_instructions:
            return context
        return replace(context, system_prompt=f"{context.system_prompt or ''}\n\n{sequence_instructions}")

    async def _preload_skills(self, message: str, context: BaseAgentContext, options: Mapping[str, Any] | None) -> tuple[BaseAgentContext, Mapping[str, Any] | None]:
        # @intent explicit-system-option-is-the-effective-skill-baseline
        # An explicit provider override remains the caller's baseline, with selected skill text appended in the run context and provider option.
        run_options = dict(options or {})
        explicit_system = run_options.get("system")
        # The context copy also carries this baseline to workers when no skill loader exists.
        has_system_override = isinstance(explicit_system, str)
        if has_system_override:
            context = replace(context, system_prompt=explicit_system)
        if self.skill_preload is None:
            return context, run_options if has_system_override else options
        context = await self.skill_preload.run(message, context)
        if has_system_override:
            run_options["system"] = context.system_prompt
        outcome = self.response.state.skills
        if outcome is None:
            raise ConfigurationError("The Jev skill preload did not record its outcome.")
        run_options["claude_skills"] = outcome.claude_skills
        run_options["claude_skill_session"] = None
        return context, run_options

    async def _select_tools(self, message: str, context: BaseAgentContext, options: Mapping[str, Any] | None) -> tuple[BaseAgentContext, Mapping[str, Any] | None, dict[str, Any] | None]:
        # @intent selector-is-a-separate-run-phase
        # The selector owns only the user tool catalog and removes the original provider tool override after filtering.
        if JevPreflightPreset.TOOL_SELECTOR not in self.runtime_settings.preflight:
            return context, options, None
        candidate_tool_count = len(self.user_tools)
        selector = JevPreflightTools(self.runtime_settings.decision, self.runtime_settings.tool_selector_threshold)
        self.user_tools = await selector.run(message, self.user_tools)
        self.usage.require_accounted()
        self.tools = with_internal_agent_tools(self.user_tools)
        context = replace(context, tools=self.tools.specs())
        run_options = dict(options or {})
        run_options.pop("tools", None)
        metadata: dict[str, Any] = {
            "available": selector.available,
            "candidate_tool_count": candidate_tool_count,
            "selected_tool_count": len(self.user_tools),
        }
        if selector.usage is not None:
            metadata["usage"] = {"model": selector.model, "input_tokens": selector.usage.input_tokens, "output_tokens": selector.usage.output_tokens}
        return context, run_options, metadata

    async def _run_bulk_work(self, message: str, context: BaseAgentContext) -> tuple[BaseAgentContext, JevBulkWorkResult | None]:
        # Runs bounded work only after selection and adds ordered results as immutable context data.
        if not self.preflight.bulk_work_requested:
            return context, None
        skill_outcome = self.response.state.skills
        claude_skills = () if skill_outcome is None else skill_outcome.claude_skills
        outcome = await self.bulk_work.plan_and_run(message, context, self.user_tools.all(), claude_skills=claude_skills)
        self.response.bulk_work(outcome)
        self.usage.require_accounted()
        if outcome.plan_valid:
            artifact = self.bulk_work.result_artifact(outcome)
            context = replace(context, tools=self.tools.specs(), artifacts=(*context.artifacts, artifact))
        return context, outcome

    def _prepare_bulk_synthesis(self, context: BaseAgentContext, options: Mapping[str, Any] | None, outcome: JevBulkWorkResult | None) -> tuple[BaseAgentContext, Mapping[str, Any] | None]:
        # Appends trusted synthesis instructions only for a valid plan, preserving a caller's explicit system override.
        if outcome is None or not outcome.plan_valid:
            return context, options
        run_options = dict(options or {})
        explicit_system = run_options.get("system")
        if isinstance(explicit_system, str):
            run_options["system"] = f"{explicit_system}\n\n{self.bulk_work.synthesis_prompt}"
            return context, run_options
        effective_system = context.system_prompt or self.system_prompt
        return replace(context, system_prompt=f"{effective_system}\n\n{self.bulk_work.synthesis_prompt}"), options

    async def _align_tools(self, alignment: JevAgentAlignment, message: str, prompt_result: JevAlignmentResult | None) -> JevToolAttachment:
        if prompt_result is not None and prompt_result.status is JevAlignmentStatus.OUT_OF_SCOPE:
            return JevToolAttachment(JevToolAlignmentResult(JevToolAlignmentStatus.OUT_OF_SCOPE, detail="Prompt alignment found the request out of scope, so no tools were added."))
        scope_checked = prompt_result is not None and prompt_result.status in _SCOPE_ANSWERED
        return await alignment.align_tools(message, self.system_prompt, self.user_tools, scope_checked=scope_checked)

    def _with_attached_tools(self, attachment: JevToolAttachment, context: BaseAgentContext, options: Mapping[str, Any] | None) -> tuple[BaseAgentContext, Mapping[str, Any] | None]:
        if not attachment.tools:
            return context, options
        self.user_tools = self.user_tools.extend(attachment.tools)
        self.tools = with_internal_agent_tools(self.user_tools)
        run_options = dict(options or {})
        run_options.pop("tools", None)
        return replace(context, tools=self.tools.specs()), run_options

    def _announced(self, result: AgentResult, attachment: JevToolAttachment) -> str:
        if not self.alignment_settings.tool_settings or not self.alignment_settings.tool_options.announce or result.structured is not None:
            return result.output
        summary = attachment.result.summary()
        return f"{result.output.rstrip()}\n\n{summary}" if summary and result.output.strip() else summary or result.output

    async def _align(self, alignment: JevAgentAlignment, message: str, context: BaseAgentContext) -> tuple[JevAlignmentResult, BaseAgentContext]:
        original = self.system_prompt
        current = context.system_prompt or ""
        prefix = original if current.startswith(original) else original.strip()
        if not current.startswith(prefix):
            return JevAlignmentResult(JevAlignmentStatus.SKIPPED, original, detail="The run context carries a caller-supplied system prompt."), context
        tools = tuple(f"{spec.name}: {spec.description}" for spec in self.user_tools.specs())
        aligned = await alignment.align(message, original, tools=tools)
        if aligned.system_prompt == original:
            return aligned, context
        self.system_prompt = aligned.system_prompt
        return aligned, replace(context, system_prompt=aligned.system_prompt.strip() + current[len(prefix):])

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

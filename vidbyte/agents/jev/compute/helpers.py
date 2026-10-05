"""FILE: vidbyte/agents/jev/compute/helpers.py

PURPOSE: Implements JevComputeHelpers, which builds and runs JevAgent's compute helper agents: separate linear agents with the main agent's model, tools, and permissions, a clean history, and their own loop limits, whose final report and run come back as a JevComputeHelperResult.
ROLE IN CODEBASE: Every compute move (the reset move today) starts its helpers through `run`; JevComputeController records each result and passes its evidence to the done checks.
ARCHITECTURE NOTE: A helper is built fresh with BaseAgent rather than forked from the JevAgent: a fork would keep the jev runtime, which JevRuntime refuses without its gate, and would share the main agent's context manager. Helpers run the linear runtime with no compute checkpoint of their own, so a helper can never start helpers. Tools that bind to an agent are cloned, as AgentForker does, so a helper never takes the main agent's bindings.
COMMON MODIFICATION PATTERNS: Keep helper construction here and each move's prompt and policy in its own module; a move that needs other limits should get them from JevComputeSettings.
KNOWN EDGE CASES: Any SDK failure while a helper runs returns None and is recorded as a failed move; a helper that answers with nothing also returns None. Cancellation is never caught.
RELATED DOCS: docs/design/jev-compute-reset.md.
TESTS: tests/test_jev_compute_reset.py.
"""

from __future__ import annotations

from collections.abc import Mapping

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.settings import JevAgentSettings, JevComputeSettings
from vidbyte.agents.pricing import UsageRollup, UsageTracker
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.dataclasses.agents import AgentInput, AgentMessage
from vidbyte.lib.dataclasses.jev import JevComputeHelperResult, JevContinuationEvidence
from vidbyte.lib.dataclasses.tools import ToolCallContext
from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.errors import VidbyteSdkError


class JevComputeHelpers:
    """Builds and runs JevAgent's compute helpers: separate linear agents with the main agent's tools and a clean history."""

    def __init__(self, settings: JevAgentSettings, compute: JevComputeSettings) -> None:
        # Keeps the main agent's settings and the helpers' loop limits, fixed at JevAgent construction.
        self.settings = settings
        self.compute = compute

    def build(self, role: str) -> BaseAgent:
        """Return a new helper agent named for its role, on the linear runtime, with the main agent's model, tools, and permissions."""
        settings = self.settings
        return BaseAgent(
            name=f"{settings.name}-compute-{role}",
            system_prompt=settings.system_prompt,
            runtime=AgentRuntimeType.LINEAR,
            tools=tuple(self._clone(tool) for tool in settings.tools),
            permission_policy=settings.permission_policy,
            agent_loop_settings=AgentLoopSettings(max_iterations=self.compute.helper_max_iterations, max_tokens=self.compute.helper_max_tokens),
            api_key=settings.api_key,
            provider=settings.provider,
            model_name=settings.model_name,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
        )

    async def run(self, role: str, prompt: str, *, source: str) -> JevComputeHelperResult | None:
        """Run one new helper on the prompt and return its report and run, or None when it failed or reported nothing."""
        # @intent a-failed-helper-never-fails-the-run
        # A helper is extra compute, not part of the main agent's own loop, so an SDK failure or an empty report is
        # recorded as a failed move and the main agent simply continues as it would have without the helper.
        helper = self.build(role)
        try:
            reply = await helper.arun(AgentInput(prompt=prompt))
        except VidbyteSdkError:
            return None
        output = reply.content.strip()
        if not output:
            return None
        return JevComputeHelperResult(output=output, evidence=self._evidence(reply, source), usage=helper.get_usage())

    @staticmethod
    def combined_usage(results: tuple[JevComputeHelperResult, ...]) -> UsageRollup | None:
        """Return the helpers' usage folded into one rollup without repricing, or None when none reported usage."""
        rollups = tuple(result.usage for result in results if result.usage is not None)
        if not rollups:
            return None
        tracker = UsageTracker()
        for rollup in rollups:
            tracker.merge(rollup)
        return tracker.rollup()

    @staticmethod
    def _evidence(reply: AgentMessage, source: str) -> JevContinuationEvidence:
        # Turns the helper's responses and tool calls into one evidence segment for the done checks.
        raw = getattr(reply, "metadata", None)
        metadata: Mapping[str, object] = raw if isinstance(raw, Mapping) else {}
        outputs = metadata.get("iteration_outputs")
        responses = tuple(outputs) if isinstance(outputs, (tuple, list)) and all(isinstance(item, str) for item in outputs) else ()
        if not responses or responses[-1] != reply.content:
            responses = (*responses, reply.content)
        raw_calls = metadata.get("tool_calls")
        calls = tuple(call for call in raw_calls if isinstance(call, ToolCallContext)) if isinstance(raw_calls, (tuple, list)) else ()
        return JevContinuationEvidence(source=source, responses=responses, tool_calls=calls)

    @staticmethod
    def _clone(tool: object) -> object:
        # Clones tools that carry an agent binding, so the helper binds its own copy; other tools are shared as they are.
        clone = getattr(tool, "clone_for_fork", None)
        return clone() if callable(clone) else tool


__all__ = ["JevComputeHelpers"]

"""FILE: vidbyte/agents/agent_swarm/compaction.py

PURPOSE: Defines the two parts a swarm member compacts its own history with: AgentSwarmHandoffSummarizer, which asks the member's own model to write a handoff summary of the older messages, and AgentSwarmCompactTool, the compact tool the model calls to ask for a compaction before its next model call.
ROLE IN CODEBASE: AgentSwarmMemberAgent (member.py) builds one AgentSwarmHandoffSummarizer for itself and hands it to its AgentSwarmMemberRuntime, whose _after_tool_iteration gives it to ContextCompactionEngine (vidbyte/middleware/compaction/engine.py) in summarize_range mode. AgentSwarmRuntime (runtime.py) builds one AgentSwarmCompactTool per member. Neither class is exported from the package.
ARCHITECTURE NOTE: The summarizer implements the Summarizer protocol of vidbyte/middleware/compaction/base.py, so the engine decides what is old, keeps whole tool-call groups, and repairs tool pairing; this module only writes the summary. The summary call is one call on the member's own runner, through AgentSwarmMemberAgent.call_model, with the summarizer leaf as its system text and a transcript of the older messages as its prompt. The raw response is kept in last_response, so the member runtime can record its usage once. The compact tool only records a request on the swarm runtime; the rewrite itself happens in the member runtime, after the iteration's tool results and before any mail. AgentSwarmRuntime and AgentSwarmMemberAgent are imported only for type checking, so this module never imports them at run time.
FUNCTION INVENTORY: AgentSwarmHandoffSummarizer.__init__ reads the two compaction leaves; summarize writes one summary. AgentSwarmCompactTool.spec declares compact with one optional focus; execute records the request and returns the swarm's reply.
COMMON MODIFICATION PATTERNS: Change what the summary must hold in vidbyte/prompts/prompts/agent_swarm/compaction_summarizer_prompt.md, and what the agent reads before it in compaction_summary_prefix.md; change when a compaction runs in AgentSwarmMemberRuntime._after_tool_iteration.
WHAT NOT TO DO IN THIS FILE: 1. Do not rewrite the history here; the engine and the member runtime own the rewrite. 2. Do not record events here; the member runtime records the side call and the compaction through the swarm runtime. 3. Do not import AgentSwarmRuntime or AgentSwarmMemberAgent at run time. 4. Do not write model-facing text here; it comes from the agent_swarm prompt family.
KNOWN EDGE CASES: A blank summary still compacts, to the prefix leaf alone. A focus is passed to the summarizer as text, never as a template, so braces in it reach the model unchanged. A failed summary call raises out of summarize; the member runtime records it as model_error and keeps the history.
RELATED DOCS: docs/spec/agent-swarm-v2/spec.md (sections 6.1 INV-30 to INV-35, 8.1 D-10, D-11 and D-15, and 8.5); vidbyte/agents/agent_swarm/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_compaction.py and tests/features/agent_swarm/test_agent_swarm_contract.py
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from vidbyte.lib.constants.agent_swarm import (
    AGENT_SWARM_COMPACT_FOCUS_ARGUMENT,
    AGENT_SWARM_COMPACT_TOOL_NAME,
)
from vidbyte.lib.dataclasses.context import ContextMessage
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.agents.agent_swarm.member import AgentSwarmMemberAgent
    from vidbyte.agents.agent_swarm.runtime import AgentSwarmRuntime


class AgentSwarmHandoffSummarizer:
    """Writes the handoff summary that replaces a member's older messages, through the member's own model."""

    def __init__(self, agent: AgentSwarmMemberAgent) -> None:
        self._agent = agent
        prompts = Prompts()
        self._instructions = prompts.get(Prompt.AGENT_SWARM_COMPACTION_SUMMARIZER_PROMPT).strip()
        self._prefix = prompts.get(Prompt.AGENT_SWARM_COMPACTION_SUMMARY_PREFIX).strip()
        # Set by the member runtime before each compaction: the agent's
        # own focus ("" for none), and the raw response of the summary
        # call, so its usage can be recorded once.
        self.focus = ""
        self.last_response: object | None = None

    async def summarize(self, messages: Sequence[ContextMessage]) -> str:
        """Return the prefix leaf followed by the member model's summary of the given older messages."""
        # @intent the-agent-summarizes-its-own-history
        # The member's own model writes the summary, in the ten sections
        # the summarizer leaf asks for, from a plain transcript of only
        # the older messages; the focus is one more instruction.
        transcript = "\n".join(f"{message.role}: {message.content}" for message in messages)
        response = await self._agent.call_model(transcript, system=self._instructions.format(focus=self.focus), messages=())
        self.last_response = response
        # The agent reads the prefix first, so it knows the text after
        # it is its own summary of what came before.
        text = str(getattr(response, "text", "") or "").strip()
        return f"{self._prefix}\n\n{text}"


class AgentSwarmCompactTool(BaseTool):
    """The compact tool: ask for this agent's older history to be summarized before its next model call."""

    def __init__(self, swarm_runtime: AgentSwarmRuntime, sender: str) -> None:
        self.swarm_runtime = swarm_runtime
        self.sender = sender

    def spec(self) -> ToolSpec:
        """Return the compact declaration, with one optional focus."""
        prompts = Prompts()
        properties = {AGENT_SWARM_COMPACT_FOCUS_ARGUMENT: {"type": "string", "description": prompts.get(Prompt.AGENT_SWARM_COMPACT_FOCUS_DESCRIPTION).strip()}}
        return ToolSpec(
            name=AGENT_SWARM_COMPACT_TOOL_NAME,
            description=prompts.get(Prompt.AGENT_SWARM_COMPACT_TOOL_DESCRIPTION).strip(),
            permission=ToolPermission.SAFE,
            input_schema={"type": "object", "properties": properties, "additionalProperties": False},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Record the compaction request and return the swarm's reply."""
        # @intent compact-only-asks
        # The rewrite waits for the end of this tool iteration, so the
        # model's own call and its result are never cut apart; a second
        # request before then replaces the first one's focus.
        reply = await self.swarm_runtime.request_compaction(self.sender, call.arguments.get(AGENT_SWARM_COMPACT_FOCUS_ARGUMENT))
        return ToolResult.success(AGENT_SWARM_COMPACT_TOOL_NAME, reply)


__all__ = ["AgentSwarmCompactTool", "AgentSwarmHandoffSummarizer"]

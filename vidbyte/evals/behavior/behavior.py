"""Context Protocol Header

Description:
    Implements the Behavior facade that composes category behavior classes.
Purpose:
    Provides a single entry point accessed via agent.behavior that lazily builds
    a RunProbe and exposes tool, tool_args, stop, handoff, and output predicate groups.
Architecture:
    - Behavior: holds a BaseAgent reference, lazily builds RunProbe, and
      initializes ToolBehavior, ToolArgumentBehavior, StopBehavior, HandoffBehavior, OutputBehavior.
    - probe property: cached RunProbe built from the agent on first access.
    - tool / tool_args / stop / handoff / output properties: return pre-built category objects.
Relations:
    Instantiated by BaseAgent.behavior property; re-exported from vidbyte.evals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vidbyte.evals.behavior.handoff import HandoffBehavior
from vidbyte.evals.behavior.output import OutputBehavior
from vidbyte.evals.behavior.probe import RunProbe
from vidbyte.evals.behavior.stop import StopBehavior
from vidbyte.evals.behavior.tool import ToolBehavior
from vidbyte.evals.behavior.tool_arguments import ToolArgumentBehavior

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent


class Behavior:
    """Post-run predicate facade over a BaseAgent's last execution."""

    def __init__(self, agent: BaseAgent) -> None:
        # Stores the agent reference and initializes category behaviors with self.
        self._agent = agent
        self._probe: RunProbe | None = None
        self._tool = ToolBehavior(self)
        self._tool_args = ToolArgumentBehavior(self)
        self._stop = StopBehavior(self)
        self._handoff = HandoffBehavior(self)
        self._output = OutputBehavior(self)

    @property
    def probe(self) -> RunProbe:
        # Lazily builds and caches the RunProbe from the agent's last run.
        if self._probe is None:
            self._probe = RunProbe.from_agent(self._agent)
        return self._probe

    @property
    def tool(self) -> ToolBehavior:
        # Returns the tool presence and outcome predicate group.
        return self._tool

    @property
    def tool_args(self) -> ToolArgumentBehavior:
        # Returns the tool argument predicate group.
        return self._tool_args

    @property
    def stop(self) -> StopBehavior:
        # Returns the stop reason and budget predicate group.
        return self._stop

    @property
    def handoff(self) -> HandoffBehavior:
        # Returns the handoff occurrence predicate group.
        return self._handoff

    @property
    def output(self) -> OutputBehavior:
        # Returns the output shape and structured-output predicate group.
        return self._output


__all__ = ["Behavior"]

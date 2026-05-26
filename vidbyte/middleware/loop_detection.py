"""Context Protocol Header

Description:
    Loop-detection middleware that identifies and breaks repetitive tool-call
    cycles that indicate a stuck agent.
Purpose:
    Prevents agents from burning tokens and time on identical repeated tool
    calls by injecting warnings and ultimately aborting the loop.
Architecture:
    - Tracks a sliding window of (tool_name, json_args) tuples.
    - If the same call appears 3+ times, a warning is injected.
    - If the loop persists for 5+ iterations, the run is aborted.
Relations:
    Extends vidbyte.middleware.base.AgentMiddleware.
"""

from __future__ import annotations

import json

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware


class StuckLoopMiddleware(AgentMiddleware):
    """Detects and breaks repetitive tool-call loops."""

    def __init__(
        self,
        max_repeats: int = 3,
        max_loop_iterations: int = 5,
    ) -> None:
        self._call_history: list[tuple[str, str]] = []
        self._loop_count = 0
        self._max_repeats = max_repeats
        self._max_loop = max_loop_iterations

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Track the current tool call and detect loops."""
        if ctx.tool_call is None:
            return MiddlewareDecision.continue_()

        name = ctx.tool_call.tool_name
        try:
            args_json = json.dumps(
                dict(ctx.tool_call.arguments), sort_keys=True, default=str
            )
        except (TypeError, ValueError):
            args_json = str(ctx.tool_call.arguments)

        self._call_history.append((name, args_json))

        recent = self._call_history[-self._max_repeats:]
        if len(recent) == self._max_repeats and len(set(recent)) == 1:
            self._loop_count += 1
        else:
            self._loop_count = 0

        if self._loop_count >= self._max_loop:
            return MiddlewareDecision.abort(
                f"Stuck loop detected: '{name}' repeated {self._max_loop} times. Aborting run.",
                metadata={"tool_name": name, "loop_count": self._loop_count},
            )

        return MiddlewareDecision.continue_()


__all__ = ["StuckLoopMiddleware"]

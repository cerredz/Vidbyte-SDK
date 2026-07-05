"""Context Protocol Header

Description:
    Provides deterministic effort-floor output contracts.
Purpose:
    Lets developers require an agent to reach a minimum amount of work (tokens,
    tool calls, iterations, or elapsed time) before it is allowed to stop.
Architecture:
    - EffortFloor: Shared base declaring a runtime dimension and minimum.
    - MinTokens / MinToolCalls / MinIterations / MinElapsedSeconds: Concrete floors.
Relations:
    Subclasses of vidbyte.agents.contracts.base.OutputContract. Statically checked
    against AgentLoopSettings by vidbyte.agents.contracts.validation.
"""

from __future__ import annotations

from vidbyte.agents.contracts.base import ContractVerdict, OutputContract, TerminationContext
from vidbyte.lib.errors import ConfigurationError


class EffortFloor(OutputContract):
    """A deterministic contract requiring a runtime counter to reach a minimum."""

    dimension: str = ""
    minimum: float = 0

    def _require_positive(self, minimum: float) -> None:
        # Rejects non-positive floor minimums at construction time.
        if minimum <= 0:
            raise ConfigurationError(
                f"{self.__class__.__name__} minimum must be greater than zero, got {minimum}."
            )

    def _verdict(self, observed: float, *, unit: str) -> ContractVerdict:
        # Builds a satisfied/unsatisfied verdict comparing observed work to the minimum.
        if observed >= self.minimum:
            return ContractVerdict(True, metadata={"observed": observed, "required": self.minimum})
        feedback = (
            f"You have used {observed} {unit} but must reach at least {self.minimum} "
            f"before completing. Keep working."
        )
        return ContractVerdict(False, feedback=feedback, metadata={"observed": observed, "required": self.minimum})


class MinTokens(EffortFloor):
    """Requires the run to consume at least a minimum number of tokens before stopping."""

    dimension = "tokens"

    def __init__(self, minimum: int) -> None:
        # Stores the required minimum token count, rejecting non-positive values.
        self._require_positive(minimum)
        self.minimum = minimum

    async def evaluate(self, ctx: TerminationContext) -> ContractVerdict:
        # Satisfied once reported token usage reaches the configured minimum.
        return self._verdict(ctx.tokens_used or 0, unit="tokens")


class MinToolCalls(EffortFloor):
    """Requires the run to make at least a minimum number of tool calls before stopping."""

    dimension = "tool_calls"

    def __init__(self, minimum: int) -> None:
        # Stores the required minimum tool-call count, rejecting non-positive values.
        self._require_positive(minimum)
        self.minimum = minimum

    async def evaluate(self, ctx: TerminationContext) -> ContractVerdict:
        # Satisfied once the observed tool-call count reaches the configured minimum.
        return self._verdict(ctx.tool_call_count, unit="tool call(s)")


class MinIterations(EffortFloor):
    """Requires the run to complete at least a minimum number of loop iterations before stopping."""

    dimension = "iterations"

    def __init__(self, minimum: int) -> None:
        # Stores the required minimum iteration count, rejecting non-positive values.
        self._require_positive(minimum)
        self.minimum = minimum

    async def evaluate(self, ctx: TerminationContext) -> ContractVerdict:
        # Satisfied once the observed iteration count reaches the configured minimum.
        return self._verdict(ctx.iteration_count, unit="iteration(s)")


class MinElapsedSeconds(EffortFloor):
    """Requires the run to last at least a minimum number of seconds before stopping."""

    dimension = "elapsed_seconds"

    def __init__(self, minimum: float) -> None:
        # Stores the required minimum elapsed seconds, rejecting non-positive values.
        self._require_positive(minimum)
        self.minimum = minimum

    async def evaluate(self, ctx: TerminationContext) -> ContractVerdict:
        # Satisfied once the observed elapsed time reaches the configured minimum.
        return self._verdict(ctx.elapsed_seconds, unit="second(s)")


__all__ = [
    "EffortFloor",
    "MinElapsedSeconds",
    "MinIterations",
    "MinTokens",
    "MinToolCalls",
]

"""Context Protocol Header

Description:
    The output contract that holds an agent to its declared output_schema.
Purpose:
    Turns schema conformance into something the runtime evaluates at its stop boundary, so a
    malformed final answer is rejected and repaired in-loop like any other unmet contract instead
    of being validated after the loop can no longer act on it.
Architecture:
    - SchemaConformance: Boolean contract over counters["final_output"], memoized per output text.
Relations:
    Registered automatically by vidbyte.agents.base.BaseAgent when output_schema is set; evaluated
    by vidbyte.agents.runtime.AgentRuntime through AgentLoopSettingsOutputContract.
Similar Files:
    - vidbyte/agents/contracts/floors.py: The deterministic effort floors sharing this base.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.agents.contracts import OutputContract


class SchemaConformance(OutputContract):
    """Requires the agent's final output to validate against its declared output schema."""

    key = "final_output"
    ceiling_key = None
    unit = "schema-valid output"
    category = "semantic"

    def __init__(self, schema: type | Mapping[str, Any]) -> None:
        # Holds the declared schema and the memo of the last output this contract evaluated.
        # Imported lazily because vidbyte.providers imports back through the config package.
        from vidbyte.providers.output_schema import OutputSchemaFormatter

        super().__init__(1)
        self.schema = schema
        self._formatter = OutputSchemaFormatter()
        self._memo_output: str | None = None
        self._memo_result: tuple[Any, str | None] = (None, None)

    def satisfied(self, counters: Mapping[str, Any]) -> bool:
        # Returns whether the current final output validates against the declared schema.
        return self.evaluate(counters)[1] is None

    def error(self, counters: Mapping[str, Any]) -> str:
        # Builds the corrective feedback naming exactly which part of the schema the output violated.
        detail = self.evaluate(counters)[1] or "the output was empty"
        return f"Your response did not match the required output schema: {detail}. Reply with only a JSON object matching the schema."

    def observed(self, counters: Mapping[str, Any]) -> int:
        # Reports conformance as 0 or 1 so contract_evaluations stays uniform with the numeric floors.
        return 1 if self.satisfied(counters) else 0

    def evaluate(self, counters: Mapping[str, Any]) -> tuple[Any, str | None]:
        # Validates the final output into (instance, error), reusing the memo when the text is unchanged.
        output = str(counters.get(self.key) or "")
        if output != self._memo_output:
            self._memo_output = output
            self._memo_result = self._formatter.validate(output, self.schema)
        return self._memo_result


__all__ = ["SchemaConformance"]

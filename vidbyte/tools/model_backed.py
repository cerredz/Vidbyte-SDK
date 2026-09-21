"""FILE: vidbyte/tools/model_backed.py

PURPOSE: Defines ModelBackedTool, the base for tools that call a model on the agent's behalf and report that usage through their result.
ROLE IN CODEBASE: `AgentRuntime._record_tool_model_usage` detects this base (after unwrapping activity or customization views) and records each reported ToolModelCall in the agent's UsageTracker; `vidbyte/tools/classifier/jev_decide.py` is the first subclass.
ARCHITECTURE NOTE: Mirrors PricedOperationTool: usage travels in result metadata so the tool stays stateless per call and the runtime remains the single place that writes to the ledger.
COMMON MODIFICATION PATTERNS: Subclasses call _model_usage_metadata() and merge it into every result whose model call reached the provider, including error results.
KNOWN EDGE CASES: model_calls() ignores anything in the metadata slot that is not a ToolModelCall, so a tool cannot inject malformed ledger rows.
RELATED DOCS: docs/design/jev-decide-tool.md and field-guide/vidbyte-sdk/runtime-boundaries.md.
TESTS: tests/test_jev_decide_tool.py and scripts/test_jev_decide_tool.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, ClassVar

from vidbyte.lib.dataclasses.tool_model_usage import ToolModelCall
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolResult


class ModelBackedTool(BaseTool):
    """Base for a tool whose execution makes model calls the agent's usage ledger must record."""

    _MODEL_USAGE_KEY: ClassVar[str] = "model_usage"

    @classmethod
    def model_calls(cls, result: ToolResult) -> tuple[ToolModelCall, ...]:
        # Returns the well-typed model calls a result reports; anything else in the slot is ignored.
        metadata = getattr(result, "metadata", None)
        if not isinstance(metadata, Mapping):
            return ()
        calls = metadata.get(cls._MODEL_USAGE_KEY)
        if not isinstance(calls, (tuple, list)):
            return ()
        return tuple(call for call in calls if isinstance(call, ToolModelCall))

    @classmethod
    def _model_usage_metadata(cls, calls: Iterable[ToolModelCall]) -> dict[str, Any]:
        # Builds the metadata slot a subclass merges into its ToolResult for runtime metering.
        return {cls._MODEL_USAGE_KEY: tuple(calls)}


__all__ = ["ModelBackedTool"]

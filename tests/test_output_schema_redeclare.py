"""FILE: tests/test_output_schema_redeclare.py

PURPOSE: Prove OutputSchemaBuilder keeps each value slot in the shape of its latest declaration.
ROLE IN CODEBASE: Drives DeclareOutputSchemaTool, AppendOutputTool and ExtendOutputSchemaTool on one shared OutputSchemaBuilder.
ARCHITECTURE NOTE: Pure in-memory tests; no agent, runner or network.
COMMON MODIFICATION PATTERNS: Add a case when a new declaration attribute changes how values are stored.
KNOWN EDGE CASES: Scalar to repeated wraps a set value; repeated to scalar keeps the latest entry; empty slots reseed.
RELATED DOCS: docs/design/builtin-tool-transport-and-builder-fixes.md
TESTS: This module; full source gate via scripts/run_ci.py.
"""

from __future__ import annotations

import pytest

from vidbyte.lib.dataclasses import ToolCall
from vidbyte.tools.builtins.output_schema import AppendOutputTool, DeclareOutputSchemaTool, ExtendOutputSchemaTool, OutputSchemaBuilder


def _tools(builder: OutputSchemaBuilder) -> tuple[DeclareOutputSchemaTool, AppendOutputTool, ExtendOutputSchemaTool]:
    return DeclareOutputSchemaTool(builder), AppendOutputTool(builder), ExtendOutputSchemaTool(builder)


@pytest.mark.asyncio
async def test_scalar_redeclared_as_repeated_keeps_prior_value_and_accepts_appends() -> None:
    builder = OutputSchemaBuilder()
    declare, append, extend = _tools(builder)
    await declare.execute(ToolCall("declare_output_schema", {"fields": [{"name": "summary"}]}))
    await append.execute(ToolCall("append_output", {"field": "summary", "value": "first take"}))

    await extend.execute(ToolCall("extend_output_schema", {"fields": [{"name": "summary", "repeated": True}]}))
    result = await append.execute(ToolCall("append_output", {"field": "summary", "value": "second take"}))

    assert result.status.value == "success", result.output
    assert builder.snapshot()["values"]["summary"] == ["first take", "second take"]


@pytest.mark.asyncio
async def test_repeated_redeclared_as_scalar_keeps_latest_entry() -> None:
    builder = OutputSchemaBuilder()
    declare, append, extend = _tools(builder)
    await declare.execute(ToolCall("declare_output_schema", {"fields": [{"name": "notes", "repeated": True}]}))
    await append.execute(ToolCall("append_output", {"field": "notes", "value": "a"}))
    await append.execute(ToolCall("append_output", {"field": "notes", "value": "b"}))

    await extend.execute(ToolCall("extend_output_schema", {"fields": [{"name": "notes", "repeated": False}]}))

    assert builder.snapshot()["values"]["notes"] == "b"
    result = await append.execute(ToolCall("append_output", {"field": "notes", "value": "c"}))
    assert result.status.value == "success", result.output
    assert builder.snapshot()["values"]["notes"] == "c"


def test_redeclaring_empty_fields_seeds_the_new_shape() -> None:
    builder = OutputSchemaBuilder()
    builder.declare([{"name": "a"}, {"name": "b", "repeated": True}])

    builder.declare([{"name": "a", "repeated": True}, {"name": "b"}])

    assert builder.snapshot()["values"] == {"a": [], "b": None}

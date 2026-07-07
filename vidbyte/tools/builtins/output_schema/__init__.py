"""Context Protocol Header

Description:
    Exports the runtime output-schema tool primitive.
Purpose:
    Lets agents declare a structured output shape and append entries to it during
    a run, so harnesses can read a compressed structured snapshot afterward.
Architecture:
    - OutputSchemaBuilder / OutputSchemaField: runtime accumulator + field model.
    - DeclareOutputSchemaTool / AppendOutputTool: agent-facing builtins.
Relations:
    Re-exported by vidbyte.tools.builtins and consumed by paradigm harnesses.
"""

from __future__ import annotations

from vidbyte.tools.builtins.output_schema.append import AppendOutputTool
from vidbyte.tools.builtins.output_schema.builder import OutputSchemaBuilder, OutputSchemaField
from vidbyte.tools.builtins.output_schema.declare import DeclareOutputSchemaTool
from vidbyte.tools.builtins.output_schema.extend import ExtendOutputSchemaTool

__all__ = [
    "AppendOutputTool",
    "DeclareOutputSchemaTool",
    "ExtendOutputSchemaTool",
    "OutputSchemaBuilder",
    "OutputSchemaField",
]

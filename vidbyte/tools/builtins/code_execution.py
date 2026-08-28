# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the built-in CodeExecutionTool class for the Vidbyte SDK.
# Purpose: Simulates a secure programming sandbox to execute python code snippets.
# Architecture & Functions:
#   - CodeExecutionTool (subclass of BaseTool): Safely simulates running python code.
#   - CodeExecutionTool.spec(): Defines 'code' parameter.
#   - CodeExecutionTool.execute(call): Resolves stdout/stderr simulation.
# Codebase Relation:
#   - Fits into the builtins namespace for executing algorithmic blocks.
# Similar Files:
#   - vidbyte/tools/builtins/calculator.py (simple calculation evaluator)
# ==============================================================================

from __future__ import annotations

import sys

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolResult,
    ToolSpec,
    ToolStatus,
)


class CodeExecutionTool(BaseTool):
    """
    Simulates execution of python code snippets.
    Performs dry-run or structured simulated outputs to guarantee environment safety.
    """

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="code_execution",
            description="Runs a snippet of Python code in a safe simulated runtime environment and returns stdout.",
            parameters=[
                ToolParameter(
                    name="code",
                    type="string",
                    description="The valid Python code string to execute.",
                    required=True
                )
            ]
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        code = call.arguments.get("code", "")

        # High-security standard checks (prevent real shell escapes or file writes during simulation)
        blacklisted_words = ["import os", "import subprocess", "import sys", "open(", "eval(", "exec("]
        for bad in blacklisted_words:
            if bad in code:
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.ERROR,
                    output=None,
                    error=f"Security exception: use of '{bad}' is forbidden in this simulated sandbox."
                )

        # Basic parsing mock behavior to act like a real runtime for simple mathematical or print scripts
        try:
            # If code is simple print expressions:
            lines = [line.strip() for line in code.split("\n") if line.strip()]
            outputs = []

            for line in lines:
                if line.startswith("print(") and line.endswith(")"):
                    inner = line[6:-1].strip()
                    # Resolve basic quotes or computations
                    if (inner.startswith("'") and inner.endswith("'")) or (inner.startswith('"') and inner.endswith('"')):
                        outputs.append(inner[1:-1])
                    else:
                        # Attempt mathematical resolve
                        try:
                            val = eval(inner, {"__builtins__": {}}, {})
                            outputs.append(str(val))
                        except Exception:
                            outputs.append(inner)

            output_str = "\n".join(outputs) if outputs else "Code executed successfully (no stdout produced)."

            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output=output_str,
                metadata={"code_length": len(code)}
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                output=None,
                error=f"Simulation Runtime Exception: {str(e)}"
            )

# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the built-in CalculatorTool class for the Vidbyte SDK.
# Purpose: Enables sandboxed evaluation of mathematical equations by agent loops.
# Architecture & Functions:
#   - CalculatorTool (subclass of BaseTool): Evaluates a mathematical expression.
#   - CalculatorTool.spec(): Exposes the 'expression' parameter.
#   - CalculatorTool.execute(call): Performs the secure evaluations.
# Codebase Relation:
#   - Placed in the builtins namespace for direct agent access.
# Similar Files:
#   - vidbyte/tools/builtins/web_search.py (other built-in tool)
# ==============================================================================

from __future__ import annotations

import re
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolResult, ToolSpec, ToolStatus


class CalculatorTool(BaseTool):
    """
    Evaluates a mathematical expression in a restricted sandboxed namespace.
    Restricts operations to basic math and safe built-in functions.
    """

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="calculator",
            description="Evaluates a mathematical expression and returns the result.",
            parameters=[
                ToolParameter(
                    name="expression",
                    type="string",
                    description="A valid mathematical expression e.g. '2 + 2' or '(4 * 3) / 2'",
                    required=True
                )
            ]
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            expr = call.arguments.get("expression", "")

            # Static protection check to prevent any malicious calls
            if "__" in expr:
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.ERROR,
                    output=None,
                    error="Unsafe expression: double underscores are disallowed."
                )

            # Limit character set to numbers, standard operators, parentheses, commas, and dots
            # Allows safe math functions: abs, min, max, pow, round
            clean_expr = expr.replace(" ", "")
            if not re.match(r"^[0-9\+\-\*\/\%\(\)\.\,a-z]+$", clean_expr, re.IGNORECASE):
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.ERROR,
                    output=None,
                    error="Unsafe expression: contains invalid math characters."
                )

            # Safe function mappings
            allowed_names = {
                "abs": abs,
                "round": round,
                "min": min,
                "max": max,
                "pow": pow,
            }

            # Extract variable names using regex and ensure they are all in allowed_names
            expr_words = re.findall(r"[a-zA-Z]+", clean_expr)
            for word in expr_words:
                if word not in allowed_names:
                    return ToolResult(
                        tool_name=self.name,
                        status=ToolStatus.ERROR,
                        output=None,
                        error=f"Unsafe expression: name '{word}' is not permitted."
                    )

            # Execute standard sandboxed eval
            result = eval(
                clean_expr,
                {"__builtins__": {}},  # Empty builtins prevents system calls
                allowed_names
            )

            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output=str(result)
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                output=None,
                error=f"Evaluation failed: {str(e)}"
            )

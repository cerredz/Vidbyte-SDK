from __future__ import annotations

import re

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolResult, ToolSpec


class CalculatorTool(BaseTool):
    """Evaluates a mathematical expression in a restricted sandboxed namespace."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="calculator",
            description="Evaluates a mathematical expression and returns the result.",
            parameters=(
                ToolParameter(
                    name="expression",
                    type="string",
                    description="A valid mathematical expression e.g. '2 + 2' or '(4 * 3) / 2'",
                    required=True,
                ),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        expr = call.arguments.get("expression", "")

        if "__" in expr:
            return ToolResult.error(self.name, "Unsafe expression: double underscores are disallowed.")

        clean_expr = expr.replace(" ", "")
        if not re.match(r"^[0-9\+\-\*\/\%\(\)\.\,a-z]+$", clean_expr, re.IGNORECASE):
            return ToolResult.error(self.name, "Unsafe expression: contains invalid math characters.")

        allowed_names = {"abs": abs, "round": round, "min": min, "max": max, "pow": pow}
        expr_words = re.findall(r"[a-zA-Z]+", clean_expr)
        for word in expr_words:
            if word not in allowed_names:
                return ToolResult.error(self.name, f"Unsafe expression: name '{word}' is not permitted.")

        try:
            result = eval(clean_expr, {"__builtins__": {}}, allowed_names)
            return ToolResult.success(self.name, str(result))
        except Exception as exc:
            return ToolResult.error(self.name, f"Evaluation failed: {exc}")

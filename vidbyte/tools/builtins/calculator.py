from __future__ import annotations

import ast
import re
from collections.abc import Callable
from typing import Any

from vidbyte.lib.errors import ToolExecutionError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.code_execution import SafePrintExpression
from vidbyte.tools.types import ToolCall, ToolParameter, ToolResult, ToolSpec

_CALCULATOR_FUNCTIONS: dict[str, Callable[..., Any]] = {"abs": abs, "round": round, "min": min, "max": max, "pow": pow}


class CalculatorExpression(SafePrintExpression):
    """Evaluates calculator arithmetic plus positional calls to the whitelisted math functions."""

    BOUND_NAME = "calculator"

    # @intent calculator-work-is-bounded
    # Model text, including prompt-injected text it repeats, reaches this tool and runs
    # synchronously on the event loop, so every power is bounded before it is computed.
    @classmethod
    def evaluate(cls, text: str) -> object:
        """Return the value of a whitelisted, bounded expression or raise."""
        return cls._walk(ast.parse(text, mode="eval").body)

    @classmethod
    def _walk(cls, node: ast.expr) -> object:
        """Evaluate a whitelisted function call, delegating every other node to the shared walker."""
        if not isinstance(node, ast.Call):
            return super()._walk(node)
        function = cls._function(node)
        args = [cls._walk(arg) for arg in node.args]
        # pow(a, b) is a**b, and round(x, n) computes 10**|n| internally, so bound both as powers.
        if function in (pow, round) and len(args) >= 2:
            cls._require_operands(ast.Pow(), 10 if function is round else args[0], args[1])
        return cls._bounded(function(*args))

    @staticmethod
    def _function(node: ast.Call) -> Callable[..., Any]:
        """Return the whitelisted function a call names, rejecting keyword arguments."""
        if not isinstance(node.func, ast.Name) or node.func.id not in _CALCULATOR_FUNCTIONS or node.keywords:
            raise ToolExecutionError("only positional calls to abs, round, min, max, and pow are supported")
        return _CALCULATOR_FUNCTIONS[node.func.id]


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

        expr_words = re.findall(r"[a-zA-Z]+", clean_expr)
        for word in expr_words:
            if word not in _CALCULATOR_FUNCTIONS:
                return ToolResult.error(self.name, f"Unsafe expression: name '{word}' is not permitted.")

        # Walk the expression instead of eval-ing it, so oversized powers fail before any work is done.
        try:
            result = CalculatorExpression.evaluate(clean_expr)
            return ToolResult.success(self.name, str(result))
        except Exception as exc:
            return ToolResult.error(self.name, f"Evaluation failed: {exc}")

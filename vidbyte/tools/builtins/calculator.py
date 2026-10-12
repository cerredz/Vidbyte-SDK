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
# A decimal number written in scientific notation, such as 2.5e-3 or 6.022E23, that does not start mid-name.
_EXPONENT_LITERAL = re.compile(r"(?<![\w.])(?:\d+\.?\d*|\.\d+)[eE][+-]?\d+")


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

        # Drop every kind of whitespace (spaces, tabs, newlines) before checking the characters.
        clean_expr = "".join(expr.split())
        if not re.match(r"^[0-9\+\-\*\/\%\(\)\.\,a-z]+$", clean_expr, re.IGNORECASE):
            return ToolResult.error(self.name, "Unsafe expression: contains invalid math characters.")

        # @intent calculator-exponents-are-not-names
        # The "e" in 2.5e-3 is part of a number, not a name, so scientific-notation literals are
        # removed before collecting names; the walker below still bounds what those numbers do.
        expr_words = re.findall(r"[a-zA-Z]+", _EXPONENT_LITERAL.sub(" ", clean_expr))
        for word in expr_words:
            if word not in _CALCULATOR_FUNCTIONS:
                return ToolResult.error(self.name, f"Unsafe expression: name '{word}' is not permitted.")

        # @intent calculator-whitespace-separates-tokens
        # Evaluate with whitespace collapsed, not removed, so "1 000" is a syntax error rather than 1000.
        spaced_expr = " ".join(expr.split())
        # Walk the expression instead of eval-ing it, so oversized powers fail before any work is done.
        try:
            result = CalculatorExpression.evaluate(spaced_expr)
            return ToolResult.success(self.name, str(result))
        except Exception as exc:
            return ToolResult.error(self.name, f"Evaluation failed: {exc}")

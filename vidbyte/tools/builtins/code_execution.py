"""FILE: vidbyte/tools/builtins/code_execution.py

PURPOSE: Defines the built-in CodeExecutionTool, a simulated Python runtime that
only renders `print(...)` lines and never executes model-supplied code.
ROLE IN CODEBASE: Registered as a builtin tool; agents call it with a `code`
string and receive simulated stdout as a ToolResult.
ARCHITECTURE NOTE: `print` arguments are evaluated by SafePrintExpression, a
small AST whitelist walker (numbers, string literals, arithmetic, unary signs,
parentheses). Nothing reaches `eval`, so attribute traversal and calls are
impossible by construction. Unevaluable arguments are echoed verbatim.
COMMON MODIFICATION PATTERNS: Widen the whitelist by adding one AST node or
operator to SafePrintExpression and a regression test beside it.
KNOWN EDGE CASES: Integer results are bounded by MAX_PRINT_INT_BITS and powers
by MAX_PRINT_EXPONENT so a model cannot pin the CPU; oversized expressions echo.
RELATED DOCS: docs/design/code-execution-safe-eval.md
TESTS: tests/test_agent_abstractions.py (TestTools, TestCodeExecutionSafeEval).
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from typing import Any

from vidbyte.lib.errors import ToolExecutionError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolResult, ToolSpec

MAX_PRINT_EXPONENT = 128
MAX_PRINT_INT_BITS = 4096
BLOCKED_CODE_FRAGMENTS = ("import os", "import subprocess", "import sys", "open(", "eval(", "exec(")
NO_STDOUT_MESSAGE = "Code executed successfully (no stdout produced)."

_BINARY_OPERATORS: dict[type[ast.operator], Callable[[Any, Any], object]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[Any], object]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class SafePrintExpression:
    """Evaluates one `print` argument through a whitelist of literal and arithmetic AST nodes."""

    # @intent no-eval-on-model-text
    # Model text, including prompt-injected tool output, reaches this tool. Emptying
    # `__builtins__` around `eval` is not a sandbox because attribute traversal stays
    # reachable, so only the node types listed here are ever interpreted. Every other
    # node (attribute, call, name, subscript, comprehension, lambda) raises and the
    # caller echoes the text instead of running it.
    @classmethod
    def evaluate(cls, text: str) -> object:
        """Return the value of a whitelisted expression or raise ToolExecutionError."""
        try:
            tree = ast.parse(text, mode="eval")
        except SyntaxError as exc:
            raise ToolExecutionError("print argument is not a single expression") from exc
        return cls._walk(tree.body)

    @classmethod
    def _walk(cls, node: ast.expr) -> object:
        """Recursively evaluate a whitelisted node."""
        if isinstance(node, ast.Constant) and type(node.value) in (int, float, str):
            return node.value
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            operand = cls._walk(node.operand)
            cls._require_number(operand)
            return _UNARY_OPERATORS[type(node.op)](operand)
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            left, right = cls._walk(node.left), cls._walk(node.right)
            cls._require_operands(node.op, left, right)
            return cls._bounded(_BINARY_OPERATORS[type(node.op)](left, right))
        raise ToolExecutionError(f"unsupported expression node {type(node).__name__}")

    @staticmethod
    def _require_number(value: object) -> None:
        """Reject non-numeric operands for unary signs."""
        if type(value) not in (int, float):
            raise ToolExecutionError("unary signs apply to numbers only")

    @staticmethod
    def _require_operands(op: ast.operator, left: object, right: object) -> None:
        """Allow string concatenation and numeric arithmetic with a bounded exponent."""
        if isinstance(op, ast.Add) and type(left) is str and type(right) is str:
            return
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            raise ToolExecutionError("arithmetic applies to numbers only")
        if isinstance(op, ast.Pow) and abs(right) > MAX_PRINT_EXPONENT:
            raise ToolExecutionError("exponent exceeds the simulated runtime bound")
        if isinstance(op, ast.Pow) and isinstance(left, int) and abs(left).bit_length() * abs(right) > MAX_PRINT_INT_BITS:
            raise ToolExecutionError("power result exceeds the simulated runtime bound")

    @staticmethod
    def _bounded(value: object) -> object:
        """Reject integer results too large to render cheaply."""
        if type(value) is int and value.bit_length() > MAX_PRINT_INT_BITS:
            raise ToolExecutionError("integer result exceeds the simulated runtime bound")
        return value


class CodeExecutionTool(BaseTool):
    """
    Simulates execution of python code snippets.
    Performs dry-run or structured simulated outputs to guarantee environment safety.
    """

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="code_execution",
            description=(
                "Runs a snippet of Python code in a safe simulated runtime environment and returns stdout. Only print(...) lines produce output; every other line is accepted but not executed. Print arguments may be numbers, string literals, and arithmetic using + - * / // % ** and parentheses. Any other print argument is echoed back verbatim instead of being evaluated."
            ),
            parameters=(
                ToolParameter(
                    name="code",
                    type="string",
                    description=(
                        "The valid Python code string to execute. Put each statement on its own line. Use print(...) for every value you want to see in stdout. Imports, file access, and dynamic evaluation are rejected by the simulated runtime."
                    ),
                    required=True,
                ),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        code = call.arguments.get("code", "")

        # Refuse obvious shell, file, and dynamic-evaluation requests up front with a clear error.
        blocked = self._blocked_fragment(code)
        if blocked is not None:
            return ToolResult.error(
                self.name,
                f"Security exception: use of '{blocked}' is forbidden in this simulated sandbox.",
            )

        # Simulate stdout by rendering each print line; other statements produce no output.
        lines = [line.strip() for line in code.split("\n") if line.strip()]
        outputs = [self._render_print(line) for line in lines if line.startswith("print(") and line.endswith(")")]

        # Report the simulated stdout, or a neutral message when nothing was printed.
        output_str = "\n".join(outputs) if outputs else NO_STDOUT_MESSAGE
        return ToolResult.success(self.name, output_str, metadata={"code_length": len(code)})

    @staticmethod
    def _blocked_fragment(code: str) -> str | None:
        """Return the first blocked fragment present in the code, if any."""
        return next((bad for bad in BLOCKED_CODE_FRAGMENTS if bad in code), None)

    @staticmethod
    def _render_print(line: str) -> str:
        """Render one print line, echoing the argument when it is not a whitelisted expression."""
        inner = line[6:-1].strip()
        try:
            return str(SafePrintExpression.evaluate(inner))
        except (ToolExecutionError, ArithmeticError, ValueError, RecursionError):
            quoted = len(inner) >= 2 and inner[0] == inner[-1] and inner[0] in ("'", '"')
            return inner[1:-1] if quoted else inner

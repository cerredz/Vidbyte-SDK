"""FILE: lint/rules/s045_async_function_with_timeout.py

PURPOSE: Defines S045 for async functions that accept timeout-like parameters.
ROLE IN CODEBASE: Makes asynchronous deadline ownership explicit.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not accept a timeout parameter and ignore it in the async body.
KNOWN EDGE CASES: Ruff owns the timeout-name and async-function classification.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S045.
"""

from lint.core.ruff import RuffBackedRule


class AsyncFunctionWithTimeoutRule(RuffBackedRule):
    """Requires async timeout parameters to be used by an explicit deadline policy."""

    id = "S045"
    name = "async-function-with-timeout"
    summary = (
        "Async functions that expose timeout-like parameters use them to bound their awaited work. "
        "A timeout argument that never reaches the operation gives callers false control over latency. "
        "That can leave an agent request, provider call, or cleanup task waiting indefinitely. "
        "Deadline ownership must be visible from the async boundary to the awaited operation."
    )
    codes = frozenset({"ASYNC109"})
    impact = (
        "Ignoring a supplied timeout breaks the caller's expectation that the operation is bounded. "
        "In a fan-out or retry loop, one unbounded coroutine can hold resources and delay every sibling. "
        "The resulting hang may look like provider instability instead of a local contract violation. "
        "Explicit timeout propagation protects task lifetime and recovery behavior."
    )
    repair = (
        "Pass the timeout through to the awaited client or wrap the operation in the repository's approved timeout context. "
        "Choose one owner for deadline enforcement and preserve cancellation propagation. "
        "Do not rename the parameter or replace it with an undocumented constant. "
        "Run the focused rule and a timeout/cancellation test after the edit."
    )


RULE = AsyncFunctionWithTimeoutRule()

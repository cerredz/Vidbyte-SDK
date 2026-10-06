"""FILE: lint/rules/s047_blocking_open_in_async_function.py

PURPOSE: Defines S047 for synchronous file opens inside async functions.
ROLE IN CODEBASE: Prevents local filesystem waits from blocking SDK coroutines.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not make a blocking open look asynchronous by adding await elsewhere.
KNOWN EDGE CASES: Ruff owns the supported open-call classification.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S047.
"""

from lint.core.ruff import RuffBackedRule


class BlockingOpenInAsyncFunctionRule(RuffBackedRule):
    """Requires async code to keep synchronous file operations off the event loop."""

    id = "S047"
    name = "blocking-open-in-async-function"
    summary = (
        "Async SDK functions do not call blocking open directly while the event loop is responsible for other work. "
        "A local file may still wait on a slow filesystem, network mount, or large decode. "
        "That pause can delay unrelated requests and defeat cancellation. "
        "Use an async file boundary or an explicit offload owned by the runtime policy."
    )
    codes = frozenset({"ASYNC230"})
    impact = (
        "Blocking file access turns one coroutine's local I/O into a stall for every task on the loop. "
        "The effect is visible as tail-latency spikes and delayed provider or model work. "
        "It is especially costly when a workflow reads several assets concurrently. "
        "Async code needs an explicit ownership boundary for filesystem waits."
    )
    repair = (
        "Use an async file API where the dependency supports it, or move the synchronous operation through the approved executor boundary. "
        "Preserve encoding, cleanup, timeout, and cancellation behavior. "
        "Do not simply call open from another helper or add a cosmetic await around it. "
        "Run the focused rule and the affected async file-path test after the edit."
    )


RULE = BlockingOpenInAsyncFunctionRule()

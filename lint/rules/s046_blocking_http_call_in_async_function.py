"""FILE: lint/rules/s046_blocking_http_call_in_async_function.py

PURPOSE: Defines S046 for blocking HTTP calls inside async functions.
ROLE IN CODEBASE: Protects the SDK event loop from synchronous network waits.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not hide a synchronous HTTP client behind a helper name.
KNOWN EDGE CASES: Ruff owns the supported blocking HTTP call classification.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S046.
"""

from lint.core.ruff import RuffBackedRule


class BlockingHttpCallInAsyncFunctionRule(RuffBackedRule):
    """Requires asynchronous code to avoid blocking HTTP clients on the event loop."""

    id = "S046"
    name = "blocking-http-call-in-async-function"
    summary = (
        "Async SDK functions do not perform synchronous HTTP waits directly on the event loop. "
        "A blocking client pauses unrelated tasks while the network is slow. "
        "That destroys concurrency for fan-out, streaming, and cancellation-sensitive workflows. "
        "Use the repository's async transport or an explicit offloading boundary."
    )
    codes = frozenset({"ASYNC210"})
    impact = (
        "One blocking request can stall every coroutine sharing the loop. "
        "Provider latency then becomes global SDK latency, and cancellation cannot interrupt the synchronous wait promptly. "
        "Retries and parallel workflows amplify the resource starvation. "
        "Async boundaries must keep network I/O non-blocking and deadline-aware."
    )
    repair = (
        "Use the approved async HTTP client, or isolate an unavoidable synchronous call in the repository's explicit thread-offload utility. "
        "Propagate timeout and cancellation semantics through that boundary. "
        "Do not merely wrap the call in an async function or rename the client. "
        "Run the focused rule and the affected transport/concurrency test after the edit."
    )


RULE = BlockingHttpCallInAsyncFunctionRule()

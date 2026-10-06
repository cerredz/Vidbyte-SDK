"""FILE: lint/rules/s048_blocking_sleep_in_async_function.py

PURPOSE: Defines S048 for blocking sleep calls inside async functions.
ROLE IN CODEBASE: Keeps retry and backoff delays cooperative with the event loop.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not use time.sleep as an async backoff primitive.
KNOWN EDGE CASES: Ruff owns the supported blocking sleep classification.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S048.
"""

from lint.core.ruff import RuffBackedRule


class BlockingSleepInAsyncFunctionRule(RuffBackedRule):
    """Requires async delays to yield cooperatively instead of blocking the loop."""

    id = "S048"
    name = "blocking-sleep-in-async-function"
    summary = (
        "Async retry and pacing code uses a cooperative sleep primitive. "
        "time.sleep blocks the entire event loop for its full delay. "
        "That prevents other requests, cancellation handlers, and cleanup tasks from running. "
        "Use an awaited async delay for coroutine-owned backoff."
    )
    codes = frozenset({"ASYNC251"})
    impact = (
        "A blocking sleep makes a local retry decision stall unrelated SDK work. "
        "The delay can multiply across concurrent retries and make a timeout impossible to honor promptly. "
        "Agents and callers then observe queueing rather than a controlled backoff. "
        "Cooperative scheduling keeps delay ownership local to the retrying task."
    )
    repair = (
        "Replace time.sleep with await asyncio.sleep or the repository's cancellation-aware backoff helper. "
        "Keep the delay bounded and preserve the surrounding retry budget. "
        "Do not put the blocking call behind a renamed helper unless that helper is an explicit executor boundary. "
        "Run the focused rule and the affected retry/cancellation test after the edit."
    )


RULE = BlockingSleepInAsyncFunctionRule()

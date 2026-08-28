"""FILE: lint/rules/s026_async_blocking_io.py

PURPOSE: Defines S026 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps blocking-call-inside-async-function findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/lint-rule-catalog-expansion.md
TESTS: Exercised by python lint/run.py --rule S026.
"""

from lint.core.ruff import RuffBackedRule


class AsyncBlockingIoRule(RuffBackedRule):
    """Enforces that async functions never block the event loop."""

    id = "S026"
    name = "async-blocking-io"
    summary = "Async functions use non-blocking sleep, subprocess, file, and HTTP calls."
    codes = frozenset({"ASYNC100", "ASYNC105", "ASYNC109", "ASYNC110", "ASYNC210", "ASYNC220", "ASYNC221", "ASYNC230", "ASYNC251"})
    impact = "A synchronous sleep, subprocess, open(), or HTTP call inside an async def blocks the single event-loop thread every concurrent agent, timeout, and transport task shares, turning one slow call into a stall for the whole runtime."
    repair = "Use the approved async path for the same operation: HttpTransport (S010) for HTTP, asyncio.sleep for delays, asyncio.create_subprocess_exec for subprocesses, or asyncio.to_thread(...) to move genuinely blocking work off the loop."


RULE = AsyncBlockingIoRule()

"""FILE: lint/rules/s006_async_task_ownership.py

PURPOSE: Defines S006 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps async task ownership findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S006.
"""

from lint.core.ruff import RuffBackedRule


class AsyncTaskOwnershipRule(RuffBackedRule):
    """Enforces the async-task-ownership policy."""

    id = "S006"
    name = "async-task-ownership"
    summary = (
        "This rule requires every created asyncio task to have an owner responsible for its lifetime and outcome. "
        "It applies to background provider work, stream consumers, tracing flushes, retries, and other tasks that can continue after the initiating function returns. "
        "A finding identifies a task whose reference, exception, cancellation, or completion path is not retained by a lifecycle owner. "
        "The contract turns fire-and-forget concurrency into deliberate work management that an agent can inspect."
    )
    codes = frozenset({"RUF006"})
    impact = (
        "An unreferenced task may be garbage-collected before it finishes or may report an exception after the initiating code has lost the context to handle it. "
        "A task that outlives a run can keep sockets, provider requests, trace buffers, or usage accounting active after cancellation. "
        "Those orphaned effects create leaked work, duplicate side effects, noisy warnings, and non-deterministic shutdown behavior. "
        "The failure is especially costly for agents because a single abandoned run can leave hidden activity in a long-lived process."
    )
    repair = (
        "Identify the component that owns the task and store the task where that component can observe completion and failure. "
        "Prefer a task group or an existing lifecycle registry that awaits normal completion and cancels outstanding work during teardown. "
        "Make cancellation and exception handling explicit without converting a failed background operation into silent success. "
        "Run the focused rule and the owning shutdown or cancellation checks to prove no task remains unaccounted for."
    )
    examples = (
        "An asyncio.TaskGroup that scopes child tasks to one agent run",
        "A component task registry that retains tasks until await or cancellation completes",
    )
    will_not_work = (
        "Calling create_task and discarding the returned task because the work is considered background.",
        "Keeping a task reference without ever awaiting, cancelling, or inspecting its result.",
    )


RULE = AsyncTaskOwnershipRule()

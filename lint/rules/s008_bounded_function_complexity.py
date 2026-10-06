"""FILE: lint/rules/s008_bounded_function_complexity.py

PURPOSE: Defines S008 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps bounded function complexity findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S008.
"""

from lint.core.ruff import RuffBackedRule


class BoundedFunctionComplexityRule(RuffBackedRule):
    """Enforces the bounded-function-complexity policy."""

    id = "S008"
    name = "bounded-function-complexity"
    summary = "This rule keeps production functions small enough that one agent can understand their control flow in one read. It targets branch count, statement count, and cyclomatic complexity where retries, errors, cancellation, and lifecycle transitions become entangled. A finding is a design signal that one callable is carrying more decisions than its name and local contract can explain honestly. The rule favors named orchestration and focused leaf functions that can evolve without reopening every neighboring concern. Complexity is measured as a boundary-clarity risk, not as a demand for arbitrary short functions."
    codes = frozenset({"C901", "PLR0912", "PLR0915"})
    impact = "A dense function forces an agent to hold unrelated branches, side effects, and invariants in context before it can make a local change. That makes it easy to alter retry behavior while fixing validation, swallow an error while adding a success path, or break cleanup in a rare branch. Tests also become broad and ambiguous because the callable has no single behavior that can be asserted in isolation. The resulting code raises review cost and makes failures harder to attribute to one contract. Moving the same tangled branches into anonymous helpers can preserve the metric while leaving the reasoning boundary just as difficult."
    repair = "Map the function's decisions and separate validation, orchestration, pure calculation, external I/O, and cleanup into coherent named responsibilities. Keep the public method as a readable sequence on the owning class and move implementation detail into typed private leaf methods. Preserve side-effect order, error translation, cancellation behavior, and shared invariants while extracting rather than rewriting unrelated logic. Run the focused rule and the narrow tests or source gate for every branch whose ownership changed. Name each extracted responsibility after its contract so the resulting structure reduces context rather than merely reducing a count."
    examples = (
        "An owning runner method that delegates request validation, transport, and result mapping to named leaves",
        "A pure helper that computes one retry or normalization decision without performing I/O",
    )
    will_not_work = (
        "Splitting the function into anonymous fragments that preserve the same tangled responsibilities.",
        "Disabling the complexity selector or moving branches into a generic utility without restoring ownership clarity.",
    )


RULE = BoundedFunctionComplexityRule()

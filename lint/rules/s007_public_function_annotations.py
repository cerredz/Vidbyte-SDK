"""FILE: lint/rules/s007_public_function_annotations.py

PURPOSE: Defines S007 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps public function annotations findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S007.
"""

from lint.core.ruff import RuffBackedRule


class PublicFunctionAnnotationsRule(RuffBackedRule):
    """Enforces the public-function-annotations policy."""

    id = "S007"
    name = "public-function-annotations"
    summary = (
        "This rule requires public SDK functions and methods to declare the types that callers must understand. "
        "It protects parameters, return values, asynchronous boundaries, provider payloads, data-transfer objects, and public error paths from disappearing into inference gaps. "
        "A finding marks a callable whose interface cannot be checked reliably by mypy, an IDE, or a downstream coding agent. "
        "The rule permits dynamic internals where the repository contract allows them while keeping public seams explicit."
    )
    codes = frozenset({"ANN001", "ANN002", "ANN003", "ANN201", "ANN202", "ANN204", "ANN205", "ANN206"})
    impact = (
        "Without annotations, callers cannot tell whether a value is optional, awaitable, serialized, provider-specific, or guaranteed to have a stable shape. "
        "Mypy then cannot catch coroutine misuse, swapped arguments, missing fields, or an error contract that changed during a refactor. "
        "Agents compensate by opening more implementation files and may still choose a type that passes one path while breaking another. "
        "The missing contract therefore increases both integration risk and the context required to modify the SDK safely."
    )
    repair = (
        "Read the callable's callers and return construction before selecting an annotation so the type describes actual behavior rather than an idealized one. "
        "Annotate every public parameter and return with the narrowest truthful SDK, standard-library, or typed collection type. "
        "Use explicit unions and protocols at dynamic provider boundaries, and keep Any only where the repository intentionally permits untyped data. "
        "Run the focused rule and mypy against the affected package after checking both synchronous and asynchronous call sites."
    )
    examples = (
        "A public runner method annotated with its request type and concrete result type",
        "A provider protocol that states whether request returns an awaitable response",
    )
    will_not_work = (
        "Annotating every value as Any or object merely to make the diagnostic disappear.",
        "Adding a return annotation while leaving public parameters ambiguous at the same boundary.",
    )


RULE = PublicFunctionAnnotationsRule()

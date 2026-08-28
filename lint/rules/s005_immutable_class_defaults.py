"""FILE: lint/rules/s005_immutable_class_defaults.py

PURPOSE: Defines S005 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps immutable class defaults findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S005.
"""

from lint.core.ruff import RuffBackedRule


class ImmutableClassDefaultsRule(RuffBackedRule):
    """Enforces the immutable-class-defaults policy."""

    id = "S005"
    name = "immutable-class-defaults"
    summary = "This rule distinguishes intentionally shared class state from mutable state that belongs to each SDK instance. It protects lists, dictionaries, sets, and similar containers declared on classes that providers, tools, runners, or registries may instantiate repeatedly. A finding marks a default whose mutation can outlive the call that made it and influence later callers. The rule therefore makes lifecycle ownership visible instead of relying on test order or convention. The declaration should tell a reader whether the value is shared policy or isolated request state before any method mutates it."
    codes = frozenset({"RUF012"})
    impact = "A mutable class attribute is allocated once and then observed by every instance that reaches it. One request can append a tool, cache a provider value, or alter configuration that changes the behavior of an unrelated later request. The resulting leak is order-dependent, difficult to reproduce, and especially misleading in a long-lived agent process. If sharing is intentional but unmarked, future agents may also fix the shared registry and break its lifecycle contract. The same defect can contaminate tests, retries, tenants, or concurrent runs without any individual caller appearing to mutate the wrong object."
    repair = "Decide first whether the value is per-instance state or an intentionally shared immutable or registry-owned value. For per-instance state, initialize it in the constructor with a fresh value or use a default factory on the owning dataclass. For intentional sharing, annotate the class variable with ClassVar and keep mutation behind the class's explicit ownership API. Run the focused rule and an isolation check that creates two instances and proves their mutable state cannot cross-contaminate. Exercise a repeated or concurrent lifecycle as well as construction so the repair covers the way the SDK actually reuses the class."
    examples = (
        "A dataclass field with a default_factory=list for per-instance state",
        "ClassVar[dict[str, str]] for a deliberately shared immutable or registry-owned map",
    )
    will_not_work = (
        "Copying the mutable class attribute only after the first request has already mutated it.",
        "Adding ClassVar to silence the finding when the value is actually request-specific state.",
    )


RULE = ImmutableClassDefaultsRule()

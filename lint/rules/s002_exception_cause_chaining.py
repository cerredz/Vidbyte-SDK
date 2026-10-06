"""FILE: lint/rules/s002_exception_cause_chaining.py

PURPOSE: Defines S002 as one independently ratcheted Ruff-backed SDK policy.
ROLE IN CODEBASE: Keeps exception cause chaining findings separate and focused.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S002.
"""

from lint.core.ruff import RuffBackedRule


class ExceptionCauseChainingRule(RuffBackedRule):
    """Enforces the exception-cause-chaining policy."""

    id = "S002"
    name = "exception-cause-chaining"
    summary = "This rule protects causal history when the SDK translates one exception into another. It covers provider, transport, protocol, and configuration boundaries where callers need both a stable public error and the original failure relationship. The rule treats an unchained replacement as a loss of diagnostic data, even when the replacement type is otherwise correct. Keeping the chain explicit lets agents and operators distinguish the boundary failure from the underlying cause. The resulting traceback should show both the stable SDK boundary and the lower-level event that explains it."
    codes = frozenset({"B904"})
    impact = "Without an exception cause, a typed provider or protocol error looks disconnected from the timeout, parser, or library failure that produced it. That disconnect removes the traceback edge needed to identify which boundary translated the error and which dependency failed first. It also forces callers to infer provenance from unstable message text, which makes automated diagnosis and retry decisions less reliable. A missing chain therefore turns a recoverable SDK failure into an opaque debugging trail. The loss is especially damaging when several providers normalize different library exceptions into one public error type."
    repair = "Inspect the caught exception and the replacement error before changing the raise statement. Raise the stable SDK error with from exc so the public type remains predictable while the internal cause remains available to diagnostics. Use from None only when hiding the implementation cause is an intentional security or abstraction decision that the boundary documents. Run the focused rule and the affected error-path tests or source gate after confirming the replacement preserves its public fields. Check that sensitive data is still redacted from the public message even when the cause is retained internally."
    examples = (
        "vidbyte/lib/http/transport.py - translate provider failures while preserving their cause",
        "A raise TypedSdkError from exc statement at a boundary translation",
    )
    will_not_work = (
        "Replacing the exception with a new message and omitting from exc.",
        "Using from None merely to shorten a traceback or make a test assertion pass.",
    )


RULE = ExceptionCauseChainingRule()

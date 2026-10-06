"""FILE: lint/rules/s050_insecure_hash.py

PURPOSE: Defines S050 for insecure cryptographic hash usage.
ROLE IN CODEBASE: Makes SDK hashing intent explicit at security-sensitive boundaries.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not use a broken hash for identity, integrity, or authentication.
KNOWN EDGE CASES: Non-security fingerprints still require explicit design review.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S050.
"""

from lint.core.ruff import RuffBackedRule


class InsecureHashRule(RuffBackedRule):
    """Requires hash algorithms to match the security property of the SDK operation."""

    id = "S050"
    name = "insecure-hash"
    summary = (
        "SDK hashing calls do not use algorithms that are unsuitable for security-sensitive values. "
        "Weak hashes can collide or be deliberately manipulated when used for integrity, identity, or authentication. "
        "A hash that is acceptable for a cache key is not automatically acceptable for a security boundary. "
        "Make the required property explicit and choose an approved primitive."
    )
    codes = frozenset({"S324"})
    impact = (
        "An insecure digest can let distinct inputs share an identifier or let an attacker influence a verification result. "
        "The defect may remain invisible until values are adversarial or the namespace becomes large. "
        "Using the same primitive across unrelated domains can also remove needed separation. "
        "Cryptographic intent must be reviewed at the call site that owns the value's meaning."
    )
    repair = (
        "Use the repository-approved modern hash or a dedicated keyed primitive for the actual security property. "
        "If the value is only a non-security fingerprint, document that ownership and confirm the call is not reused for integrity or identity. "
        "Do not silence the rule merely because current inputs are short or trusted. "
        "Run the focused rule and the affected security/compatibility tests after the edit."
    )


RULE = InsecureHashRule()

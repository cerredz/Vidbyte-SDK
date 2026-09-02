"""FILE: lint/rules/s054_bandit_security_subset.py

PURPOSE: Defines S054 as one independently ratcheted Ruff-backed SDK security policy.
ROLE IN CODEBASE: Groups a narrow, hand-selected bandit-family finding set under one baseline.
ARCHITECTURE NOTE: Detection is delegated to the cached isolated Ruff adapter; only codes verified
    to have a clear, low-false-positive remediation in this codebase are selected (see
    docs/design/lint-rule-catalog-expansion.md section 6.5 for the codes deliberately omitted).
    Excludes S506 and S324, which origin/main's S049 (unsafe-yaml-load) and S050 (insecure-hash)
    already own, so the same finding is never counted under two rule IDs.
FUNCTION INVENTORY: Module exports declarative policy or package markers; no hidden runtime work.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/lint-rule-catalog-expansion.md
TESTS: Exercised by python lint/run.py --rule S054.
"""

from lint.core.ruff import RuffBackedRule


class BanditSecuritySubsetRule(RuffBackedRule):
    """Enforces a narrow set of security-relevant bandit findings: unsafe deserialization, weak crypto, TLS bypass, hardcoded credentials."""

    id = "S054"
    name = "bandit-security-subset"
    summary = "Source avoids pickle/marshal deserialization, disabled TLS verification, hardcoded credential-shaped literals, and predictable temp paths (weak-hash and unsafe-YAML coverage lives in S050/S049)."
    codes = frozenset({"S105", "S106", "S107", "S108", "S301", "S302", "S501"})
    impact = "Each finding in this family turns a call site into a code-execution, credential-exposure, or man-in-the-middle vector when it later receives untrusted input: yaml.load and pickle/marshal can construct arbitrary objects, MD5/SHA-1 are not collision-resistant for anything security-relevant, verify=False accepts any certificate, and a literal that looks like a password or a predictable tmp filename can leak a real value or be raced by another process."
    repair = "Use yaml.safe_load with schema validation, replace pickle/marshal with a data-only format plus validation, use hashlib.sha256 or better for anything security-relevant, remove verify=False (or gate it behind a test-only fixture that cannot run in production), and replace the literal with an environment-sourced value or a securely generated temp path (tempfile.mkstemp)."


RULE = BanditSecuritySubsetRule()

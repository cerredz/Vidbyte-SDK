"""FILE: lint/rules/s039_banned_api_policy.py

PURPOSE: Defines S039 for repository-owned banned API imports.
ROLE IN CODEBASE: Keeps compatibility and concurrency choices on approved SDK seams.
ARCHITECTURE NOTE: Ruff reads the explicit lint/ruff.toml policy table.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not bypass a banned API by renaming or re-exporting it.
KNOWN EDGE CASES: The policy list is intentionally narrow and reviewable.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S039.
"""

from lint.core.ruff import RuffBackedRule


class BannedApiPolicyRule(RuffBackedRule):
    """Requires SDK code to use the repository-approved alternatives to banned APIs."""

    id = "S039"
    name = "banned-api-policy"
    summary = (
        "The SDK does not import APIs listed in its repository-owned banned-api policy. "
        "Those entries represent compatibility, ownership, or concurrency decisions that callers rely on. "
        "Using the convenient low-level API can bypass the shared boundary that enforces those decisions. "
        "The explicit policy file keeps the exception list visible and deterministic."
    )
    codes = frozenset({"TID251"})
    impact = (
        "A banned import can split behavior between the SDK's approved abstraction and an ad hoc local implementation. "
        "That creates incompatible typing, synchronization, or runtime behavior across consumers. "
        "The resulting drift is difficult to detect from one unit test or one provider path. "
        "Central ownership is part of the SDK contract, not a stylistic preference."
    )
    repair = (
        "Use the approved SDK abstraction named by lint/ruff.toml or add the necessary behavior to that owning boundary. "
        "If the API truly needs to become allowed, change the policy through an explicit design review rather than a local exception. "
        "Do not alias, re-export, or dynamically import the same banned API to evade detection. "
        "Run the focused rule and the relevant source/package gate after the edit."
    )


RULE = BannedApiPolicyRule()

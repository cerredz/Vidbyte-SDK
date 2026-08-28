"""FILE: lint/rules/s057_no_model_construct_without_review.py

PURPOSE: Rejects Pydantic model_construct() calls outside a reviewed allowlist.
ROLE IN CODEBASE: Keeps validation-skipping construction from landing silently.
ARCHITECTURE NOTE: Pure syntactic AST match on the method name; no type inference is attempted.
FUNCTION INVENTORY: NoModelConstructWithoutReviewRule scans every call for .model_construct(.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/lint-rule-catalog-expansion.md
TESTS: Exercised by python lint/run.py --rule S057.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule

# Paths reviewed and approved to skip Pydantic validation via model_construct(). Empty today:
# add a path here only after confirming its input is already a validated or trusted model.
ALLOWLIST: frozenset[str] = frozenset()


class NoModelConstructWithoutReviewRule(Rule):
    """Rejects model_construct() calls outside the reviewed allowlist."""

    id = "S057"
    name = "no-model-construct-without-review"
    severity = "blocking"
    summary = "Pydantic model_construct() is used only in reviewed, allowlisted modules."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Walks every call expression looking for the validation-skipping constructor.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None or source.rel in ALLOWLIST:
                continue
            for node in ast.walk(source.tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "model_construct":
                    findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=node.lineno, source_line=source.line_at(node.lineno), symbol="model_construct"))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Explains the validation gap and the two ways to close it.
        return Diagnostic(
            what_happened=f"{finding.rel_path}:{finding.line} calls model_construct(), which builds a Pydantic model without running field validation.",
            why_blocked="model_construct() can produce an invalid model if any field's data has not already passed through validation elsewhere; a model built this way looks the same as a validated one to every downstream consumer, so a malformed value can propagate silently.",
            how_to_fix="Use the normal constructor or model_validate(...) so Pydantic validates the data. If this call site is a genuine, reviewed performance boundary building from already-validated or already-trusted data, add its relative path to ALLOWLIST in lint/rules/s031_no_model_construct_without_review.py with a comment naming the trusted source.",
            correct_examples=("Model.model_validate(payload) or Model(**validated_kwargs) - both run full field validation.",),
            will_not_work=("Adding the path to ALLOWLIST without confirming the input is already validated or trusted.", "Wrapping the call in a try/except instead of validating the data."),
            verify=self.verify_command(),
        )


RULE = NoModelConstructWithoutReviewRule()

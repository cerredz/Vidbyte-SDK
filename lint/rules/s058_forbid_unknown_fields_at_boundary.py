"""FILE: lint/rules/s032_forbid_unknown_fields_at_boundary.py

PURPOSE: Requires public-seam Pydantic models to make an explicit extra-field choice.
ROLE IN CODEBASE: Prevents a silently permissive default from hiding a typo'd or attacker-controlled field.
ARCHITECTURE NOTE: Flags only the absence of any model_config/Config declaration; a class that
    explicitly sets extra="allow" or extra="ignore" has already made a visible, reviewable choice
    and is compliant, matching the two production classes that already set extra="forbid".
FUNCTION INVENTORY: ForbidUnknownFieldsAtBoundaryRule scans public-seam BaseModel subclasses.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/lint-rule-catalog-expansion.md
TESTS: Exercised by python lint/run.py --rule S032.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule

PUBLIC_SEAM_PREFIXES = ("vidbyte/sessions/", "vidbyte/lib/dataclasses/")
PUBLIC_SEAM_FILES = ("vidbyte/tools/types.py", "vidbyte/mcp_server/schema.py")


def _in_public_seam(rel_path: str) -> bool:
    # Matches the public-seam directories and files this policy governs.
    return rel_path.startswith(PUBLIC_SEAM_PREFIXES) or rel_path in PUBLIC_SEAM_FILES


def _base_names(class_node: ast.ClassDef) -> set[str]:
    # Returns the simple names of every declared base class.
    names: set[str] = set()
    for base in class_node.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
    return names


def _declares_extra_policy(class_node: ast.ClassDef) -> bool:
    # Confirms the class makes an explicit model_config/Config extra-field choice.
    for node in class_node.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "model_config" for target in node.targets):
            return True
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "model_config":
            return True
        if isinstance(node, ast.ClassDef) and node.name == "Config":
            return True
    return False


class ForbidUnknownFieldsAtBoundaryRule(Rule):
    """Requires public-seam BaseModel subclasses to declare an explicit extra-field policy."""

    id = "S032"
    name = "forbid-unknown-fields-at-boundary"
    severity = "blocking"
    summary = "Public-seam Pydantic models declare model_config instead of relying on Pydantic's silent default."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans public-seam class definitions for a BaseModel subclass missing an extra-field policy.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None or not _in_public_seam(source.rel):
                continue
            for node in ast.walk(source.tree):
                if isinstance(node, ast.ClassDef) and "BaseModel" in _base_names(node) and not _declares_extra_policy(node):
                    findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=node.lineno, source_line=source.line_at(node.lineno), symbol=node.name))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Names the class and the two acceptable declared policies.
        return Diagnostic(
            what_happened=f"{finding.rel_path}:{finding.line} defines {finding.symbol}(BaseModel) with no model_config declaration.",
            why_blocked="Pydantic silently discards unknown fields by default, so a client typo, a protocol drift between SDK versions, or an attacker-controlled extra field on this public-seam model disappears without any signal that it was ever present.",
            how_to_fix='Add `model_config = ConfigDict(extra="forbid")` to reject unknown fields, or `model_config = ConfigDict(extra="allow")` / `extra="ignore"` if this model is a deliberate open envelope - either choice satisfies this rule as long as it is explicit.',
            correct_examples=('vidbyte/agents/multi/orchestrator.py - model_config = ConfigDict(extra="forbid") on its request/response models.', 'vidbyte/lib/dataclasses/prosecutor_defender_judge.py - same explicit extra="forbid" convention.'),
            will_not_work=("Leaving model_config unset because the fields today happen to be complete.", "Adding a comment instead of the model_config declaration itself."),
            verify=self.verify_command(),
        )


RULE = ForbidUnknownFieldsAtBoundaryRule()

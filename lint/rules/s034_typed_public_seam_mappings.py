"""FILE: lint/rules/s034_typed_public_seam_mappings.py

PURPOSE: Rejects dict[str, Any] in public-seam function and method signatures.
ROLE IN CODEBASE: Keeps protocol payloads at the SDK's most visible boundaries nameable and typed.
ARCHITECTURE NOTE: Scoped to public-seam directories only (a strict subset of the 423 repo-wide
    hits this audit found); the remaining internal dict[str, Any] usage is intentionally out of
    scope for this rule, per docs/design/lint-rule-catalog-expansion.md section 6.11.
FUNCTION INVENTORY: TypedPublicSeamMappingsRule scans public function/method annotations.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/lint-rule-catalog-expansion.md
TESTS: Exercised by python lint/run.py --rule S034.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule

PUBLIC_SEAM_PREFIXES = ("vidbyte/sessions/", "vidbyte/lib/dataclasses/")
PUBLIC_SEAM_FILES = ("vidbyte/tools/types.py", "vidbyte/mcp_server/schema.py")


def _in_public_seam(rel_path: str) -> bool:
    # Matches the same public-seam directories and files S032 governs.
    return rel_path.startswith(PUBLIC_SEAM_PREFIXES) or rel_path in PUBLIC_SEAM_FILES


def _is_dict_str_any(node: ast.expr | None) -> bool:
    # Matches dict[str, Any] / Dict[str, Any] subscript annotations.
    if not isinstance(node, ast.Subscript):
        return False
    base = node.value
    base_name = base.id if isinstance(base, ast.Name) else base.attr if isinstance(base, ast.Attribute) else None
    if base_name not in {"dict", "Dict"}:
        return False
    sl = node.slice
    if not isinstance(sl, ast.Tuple) or len(sl.elts) != 2:
        return False
    key, value = sl.elts
    key_ok = isinstance(key, ast.Name) and key.id == "str"
    value_ok = isinstance(value, ast.Name) and value.id == "Any" or (isinstance(value, ast.Attribute) and value.attr == "Any")
    return key_ok and value_ok


class TypedPublicSeamMappingsRule(Rule):
    """Rejects dict[str, Any] in public function/method signatures under public-seam directories."""

    id = "S034"
    name = "typed-public-seam-mappings"
    severity = "blocking"
    summary = "Public-seam function and method signatures name their mapping shape instead of dict[str, Any]."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans public-seam function/method parameter and return annotations.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None or not _in_public_seam(source.rel):
                continue
            for node in ast.walk(source.tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name.startswith("_"):
                    continue
                params = (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
                offending = [arg.arg for arg in params if _is_dict_str_any(arg.annotation)]
                if _is_dict_str_any(node.returns):
                    offending.append("return")
                for symbol in offending:
                    findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=node.lineno, source_line=source.line_at(node.lineno), symbol=f"{node.name}:{symbol}", extra={"function": node.name, "parameter": symbol}))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Names the function and parameter and points at the TypedDict/DTO alternative.
        return Diagnostic(
            what_happened=f"{finding.rel_path}:{finding.line} - {finding.extra.get('function', '')} declares dict[str, Any] for {finding.extra.get('parameter', '')}.",
            why_blocked="A public seam typed as dict[str, Any] gives every caller and every future maintainer the appearance of a typed contract while carrying none of the shape information a TypedDict, dataclass, or Pydantic model would - the actual required/optional keys and their types exist only in whichever function body happens to read them.",
            how_to_fix="Replace dict[str, Any] with a TypedDict, a Pydantic model, or an existing named mapping type that documents the actual keys this seam accepts or returns.",
            correct_examples=("vidbyte/mcp_server/schema.py - McpSchema types its tool/resource payloads instead of leaving them as dict[str, Any].",),
            will_not_work=("Aliasing dict[str, Any] under a new type name without adding any key structure.", "Adding a docstring describing the keys instead of a checked type."),
            verify=self.verify_command(),
        )


RULE = TypedPublicSeamMappingsRule()

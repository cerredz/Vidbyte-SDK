"""FILE: lint/rules/s035_bounded_safe_path.py

PURPOSE: Flags file I/O on a non-literal path outside the reviewed path-containment helper.
ROLE IN CODEBASE: Guards against a future untrusted path fragment reaching open()/extractall() unresolved.
ARCHITECTURE NOTE: Pure syntactic AST match; a dynamic first argument is a proxy for "not a
    hardcoded internal path", not proof of untrusted input - hence ratcheted, not zero-tolerance.
FUNCTION INVENTORY: BoundedSafePathRule scans file/archive calls for a non-literal path argument.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/lint-rule-catalog-expansion.md
TESTS: Exercised by python lint/run.py --rule S035.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule

# The reviewed path-containment helper this rule treats as the compliant pattern; call sites in
# this module already resolve and contain paths before touching the filesystem.
ALLOWLIST = frozenset({"vidbyte/lib/tools/filesystem/backends/local.py"})

_FILE_METHODS = frozenset({"write_text", "write_bytes", "read_text", "read_bytes"})
_SHUTIL_METHODS = frozenset({"copy", "copy2", "copyfile", "move"})
_ARCHIVE_METHODS = frozenset({"extractall"})


def _dotted_tail(node: ast.expr) -> str | None:
    # Returns the final attribute name of a call target, if any.
    return node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else None


def _receiver_is_filesystem_backend(node: ast.expr) -> bool:
    # Excludes calls already routed through the reviewed FileSystemBackend abstraction, e.g.
    # self.backend.read_text(...) - the backend itself owns path resolution and containment.
    return isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute) and node.value.attr == "backend"


def _is_literal_path(node: ast.expr | None) -> bool:
    # A hardcoded string literal (or None) needs no containment check.
    return node is None or isinstance(node, ast.Constant) and isinstance(node.value, str)


class BoundedSafePathRule(Rule):
    """Flags file/archive I/O on a non-literal path outside the reviewed containment helper."""

    id = "S035"
    name = "bounded-safe-path"
    severity = "blocking"
    summary = "File and archive I/O on a non-literal path routes through a resolved, contained path helper."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Walks every call expression looking for file/archive I/O on a dynamic path.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None or source.rel in ALLOWLIST:
                continue
            for node in ast.walk(source.tree):
                if not isinstance(node, ast.Call):
                    continue
                tail = _dotted_tail(node.func)
                if tail == "open" and isinstance(node.func, ast.Name):
                    path_arg = node.args[0] if node.args else None
                elif (tail in _FILE_METHODS or tail in _SHUTIL_METHODS or tail in _ARCHIVE_METHODS) and not _receiver_is_filesystem_backend(node.func):
                    path_arg = node.args[0] if node.args else None
                else:
                    continue
                if path_arg is not None and not _is_literal_path(path_arg):
                    findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=node.lineno, source_line=source.line_at(node.lineno), symbol=tail))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Points at the containment helper and the traversal risk of an unresolved dynamic path.
        return Diagnostic(
            what_happened=f"{finding.rel_path}:{finding.line} calls {finding.symbol}(...) with a non-literal path argument.",
            why_blocked="A path built from a variable can contain '..' segments, an absolute path, or a symlink that escapes the intended directory; without resolving and checking containment first, this call can read, write, or extract outside the directory the caller assumed it was confined to.",
            how_to_fix="Resolve the path and verify it stays under the intended root before this call, using the same pattern as vidbyte/lib/tools/filesystem/backends/local.py's LocalFileSystemBackend, or confirm (and note in a nearby comment) that this path is always an internal, hardcoded value never derived from external input.",
            correct_examples=("vidbyte/lib/tools/filesystem/backends/local.py - LocalFileSystemBackend resolves and contains every path before touching the filesystem.",),
            will_not_work=("Adding a comment claiming the input is trusted without a resolve+containment check.", "Blocking only '../' with a string replace instead of resolving the path."),
            verify=self.verify_command(),
        )


RULE = BoundedSafePathRule()

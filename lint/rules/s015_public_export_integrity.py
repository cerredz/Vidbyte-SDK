"""FILE: lint/rules/s015_public_export_integrity.py

PURPOSE: Verifies package __all__ entries and root public imports are statically bound.
ROLE IN CODEBASE: Prevents installed-package import failures and undocumented API drift.
ARCHITECTURE NOTE: Lazy exports are accepted only through an explicit local mapping.
FUNCTION INVENTORY: ExportIntegrityAnalyzer extracts bound/imported/exported names.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S015 and wheel smoke CI.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule


class ExportIntegrityAnalyzer:
    """Finds duplicate, unbound, and root-unlisted public export names."""

    def analyze(self, source: SourceFile) -> list[tuple[int, str, str]]:
        # Compares literal __all__ with imports/definitions/assignments in one package initializer.
        if source.tree is None:
            return []
        exported, line = self._exports(source.tree)
        if exported is None:
            return []
        bound, imported_public = self._bound_names(source.tree)
        lazy = self._lazy_names(source.tree)
        hits: list[tuple[int, str, str]] = []
        seen: set[str] = set()
        for name in exported:
            if name in seen:
                hits.append((line, name, "duplicate __all__ entry"))
            seen.add(name)
            if name not in bound | lazy:
                hits.append((line, name, "__all__ entry is not bound/imported/lazily declared"))
        if source.rel == "vidbyte/__init__.py":
            for name in sorted(imported_public - set(exported)):
                hits.append((line, name, "root public import is missing from __all__"))
        return hits

    def _exports(self, tree: ast.Module) -> tuple[list[str] | None, int]:
        # Extracts a literal list/tuple __all__ assignment without executing concatenations.
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets) and isinstance(node.value, (ast.List, ast.Tuple)):
                return [item.value for item in node.value.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)], node.lineno
        return None, 1

    def _bound_names(self, tree: ast.Module) -> tuple[set[str], set[str]]:
        # Collects top-level definitions, assignments, and imported aliases.
        bound: set[str] = set()
        imported_public: set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                bound.update(target.id for target in targets if isinstance(target, ast.Name))
            elif isinstance(node, ast.Import):
                names = {alias.asname or alias.name.split(".", 1)[0] for alias in node.names}
                bound.update(names)
                imported_public.update(name for name in names if not name.startswith("_"))
            elif isinstance(node, ast.ImportFrom):
                if node.module == "__future__":
                    continue
                names = {alias.asname or alias.name for alias in node.names if alias.name != "*"}
                bound.update(names)
                imported_public.update(name for name in names if not name.startswith("_"))
        return bound, imported_public

    def _lazy_names(self, tree: ast.Module) -> set[str]:
        # Extracts string keys from conventionally named lazy-export mappings.
        names: set[str] = set()
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if any(isinstance(target, ast.Name) and "lazy" in target.id.lower() and "export" in target.id.lower() for target in targets) and isinstance(value, ast.Dict):
                names.update(key.value for key in value.keys if isinstance(key, ast.Constant) and isinstance(key.value, str))
        return names


class PublicExportIntegrityRule(Rule):
    """Requires declared public exports to resolve statically and uniquely."""

    id = "S015"
    name = "public-export-integrity"
    severity = "blocking"
    summary = "This rule protects the package's explicitly declared public import surface. It verifies that each __all__ entry is unique and bound, and that root-level public imports are discoverable through the root export list. It also recognizes lazy exports only when their names are declared in a local mapping that static analysis can inspect. The contract keeps source-tree imports, installed-package imports, documentation, and IDE discovery pointed at the same API surface. Export declarations therefore act as a checked compatibility boundary rather than a manually maintained list of hopeful names."
    impact = "An unbound export advertises a symbol that can fail with ImportError or AttributeError when a user imports the package. A missing root export makes a working public symbol invisible to star imports, documentation tools, and agents that inspect __all__. Duplicate or drifted entries obscure which declaration is authoritative and can pass code review until packaging or a downstream import runs. Because the root initializer is a high fan-out boundary, a small export mismatch can break many unrelated consumers at once. Import behavior can also differ between a source checkout and an installed wheel when the two paths do not expose the same bindings."
    repair = "Inspect the initializer's definitions, imports, assignments, lazy-export mapping, and __all__ as one public contract. Bind or import the intended symbol once and list it once, or remove both the binding and export when the symbol is no longer public. Use the explicit lazy-export mapping only for intentional deferred imports and preserve the package's existing initialization behavior. Run the focused rule, direct import checks, and installed wheel smoke checks before declaring the export repair complete. Check package-level and namespace-level imports so a fix for one initializer does not leave a nested public surface inconsistent."
    examples = (
        "vidbyte/lib/registries/__init__.py - explicit local imports paired with __all__",
        "A lazy export declared in the local mapping consumed by __getattr__",
    )
    will_not_work = (
        "Relying on a star import or documentation entry to bind a missing __all__ symbol.",
        "Adding a string to __all__ without binding the symbol or declaring a supported lazy export.",
    )

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans only package initializer modules that declare public surfaces.
        findings: list[Finding] = []
        analyzer = ExportIntegrityAnalyzer()
        for source in catalog.python_files():
            if not source.rel.endswith("/__init__.py") and source.rel != "vidbyte/__init__.py":
                continue
            findings.extend(Finding(rule_id=self.id, rel_path=source.rel, line=line, source_line=source.line_at(line), symbol=symbol, extra={"reason": reason}) for line, symbol, reason in analyzer.analyze(source))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Repairs the export declaration at the owning package boundary.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} export {finding.symbol} is invalid: {finding.extra.get('reason', 'export drift')}.", why_blocked=self.impact, how_to_fix=self.repair, correct_examples=self.examples, will_not_work=self.will_not_work, verify=self.verify_command())


RULE = PublicExportIntegrityRule()

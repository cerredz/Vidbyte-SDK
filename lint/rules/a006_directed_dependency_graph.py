"""FILE: lint/rules/a006_directed_dependency_graph.py

PURPOSE: Defines A006 as the SDK's concrete-module dependency-graph policy.
ROLE IN CODEBASE: Prevents import cycles and upward dependencies across architecture layers.
ARCHITECTURE NOTE: Graph edges come from AST imports; package code is never imported.
FUNCTION INVENTORY: DependencyGraphAnalyzer and DirectedDependencyGraphRule build/report.
COMMON MODIFICATION PATTERNS: Change layer boundaries and diagnostics together; rerun A006.
WHAT NOT TO DO: Do not follow façade re-exports, TYPE_CHECKING edges, or suppress cycles.
KNOWN EDGE CASES: Only tracked concrete modules participate; missing targets are ignored.
RELATED DOCS: docs/design/agent-native-lint-rules.md
TESTS: Exercised by python lint/run.py --rule A006.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

ORCHESTRATION_PREFIXES = (
    "vidbyte.agents",
    "vidbyte.context",
    "vidbyte.middleware",
    "vidbyte.tools",
    "vidbyte.pipelines",
    "vidbyte.workflows",
    "vidbyte.harnesses",
    "vidbyte.trace",
    "vidbyte.evals",
    "vidbyte.paradigms",
)
APPLICATION_PREFIXES = ("vidbyte.client", "vidbyte.config", "vidbyte.cli", "vidbyte.mcp_server")
LOWER_LAYER_PREFIXES = ("vidbyte.lib", "vidbyte.providers", "vidbyte.sessions", "vidbyte.sources")


@dataclass(frozen=True, slots=True)
class ImportEdge:
    """One concrete source-to-target module import with its source location."""

    source: str
    target: str
    rel_path: str
    line: int


class DependencyGraphAnalyzer:
    """Builds concrete imports and finds cycles or forbidden layer crossings."""

    def analyze(self, sources: tuple[SourceFile, ...]) -> list[tuple[ImportEdge, str]]:
        # Resolves concrete imports, then reports cycles and documented upward edges.
        modules = {self._module_name(source.rel): source for source in sources if self._is_concrete(source)}
        edges = [edge for source in modules.values() for edge in self._imports(source, modules)]
        findings = [(edge, reason) for edge in edges if (reason := self._layer_violation(edge.source, edge.target))]
        components = self._components(tuple(modules), edges)
        for component in components:
            if len(component) == 1:
                continue
            rendered = " -> ".join(component)
            findings.extend((edge, f"concrete import cycle: {rendered}") for edge in edges if edge.source in component and edge.target in component)
        return findings

    def _is_concrete(self, source: SourceFile) -> bool:
        # Excludes package façade initializers and syntax-error files from graph nodes.
        return source.tree is not None and not source.rel.endswith("/__init__.py") and source.rel != "vidbyte/__init__.py"

    def _module_name(self, rel_path: str) -> str:
        # Converts a tracked Python path into its dotted concrete module name.
        return rel_path[:-3].replace("/", ".").replace("\\", ".")

    def _imports(self, source: SourceFile, modules: dict[str, SourceFile]) -> list[ImportEdge]:
        # Collects runtime absolute/relative imports while skipping TYPE_CHECKING bodies.
        collector = ImportCollector(self._module_name(source.rel))
        collector.visit(source.tree)
        return [ImportEdge(source=collector.module, target=target, rel_path=source.rel, line=line) for line, target in collector.imports if target in modules]

    def _layer_violation(self, source: str, target: str) -> str:
        # Applies the documented lower-layer-to-orchestration/application restriction.
        if not source.startswith(LOWER_LAYER_PREFIXES):
            return ""
        if target.startswith(ORCHESTRATION_PREFIXES + APPLICATION_PREFIXES):
            return "lower-layer module imports orchestration/application module"
        return ""

    def _components(self, modules: tuple[str, ...], edges: list[ImportEdge]) -> list[tuple[str, ...]]:
        # Returns deterministic strongly connected components for the concrete graph.
        graph = {module: set() for module in modules}
        for edge in edges:
            graph[edge.source].add(edge.target)
        index = 0
        indices: dict[str, int] = {}
        lowlinks: dict[str, int] = {}
        stack: list[str] = []
        on_stack: set[str] = set()
        components: list[tuple[str, ...]] = []

        def visit(module: str) -> None:
            # Runs one Tarjan traversal for a deterministic graph node.
            nonlocal index
            indices[module] = index
            lowlinks[module] = index
            index += 1
            stack.append(module)
            on_stack.add(module)
            for target in sorted(graph[module]):
                if target not in indices:
                    visit(target)
                    lowlinks[module] = min(lowlinks[module], lowlinks[target])
                elif target in on_stack:
                    lowlinks[module] = min(lowlinks[module], indices[target])
            if lowlinks[module] == indices[module]:
                component: list[str] = []
                while True:
                    target = stack.pop()
                    on_stack.remove(target)
                    component.append(target)
                    if target == module:
                        break
                components.append(tuple(sorted(component)))

        for module in sorted(modules):
            if module not in indices:
                visit(module)
        return [component for component in components if len(component) > 1]


class ImportCollector(ast.NodeVisitor):
    """Collects concrete import targets while preserving relative-import semantics."""

    def __init__(self, module: str) -> None:
        # Retains the current module so relative imports resolve without imports.
        self.module = module
        self.imports: list[tuple[int, str]] = []
        self._skip_type_checking = False

    def visit_If(self, node: ast.If) -> None:
        # Skips imports guarded by TYPE_CHECKING while retaining runtime else branches.
        if self._is_type_checking(node.test):
            for statement in node.orelse:
                self.visit(statement)
            return
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        # Records absolute imports whose root belongs to the SDK package.
        for alias in node.names:
            if alias.name.startswith("vidbyte."):
                self.imports.append((node.lineno, alias.name))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # Resolves absolute and relative imports to one concrete module target.
        target = self._target(node)
        if target and target.startswith("vidbyte."):
            self.imports.append((node.lineno, target))

    def _is_type_checking(self, test: ast.expr) -> bool:
        # Recognizes both TYPE_CHECKING and typing.TYPE_CHECKING guards.
        return isinstance(test, ast.Name) and test.id == "TYPE_CHECKING" or isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"

    def _target(self, node: ast.ImportFrom) -> str:
        # Calculates the module named by an absolute or relative import statement.
        if node.level == 0:
            return node.module or ""
        parts = self.module.split(".")[:-1]
        base = parts[: len(parts) - node.level + 1]
        return ".".join((*base, *(node.module.split(".") if node.module else ())))


class DirectedDependencyGraphRule(Rule):
    """Rejects concrete import cycles and lower-layer upward dependencies."""

    id = "A006"
    name = "directed-dependency-graph"
    severity = "blocking"
    summary = "Concrete module imports obey the SDK layer graph and contain no cycles."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Builds one graph from the shared source catalogue and reports each bad edge.
        findings: list[Finding] = []
        analyzer = DependencyGraphAnalyzer()
        sources = catalog.python_files()
        source_by_rel = {source.rel: source for source in sources}
        for edge, reason in analyzer.analyze(sources):
            source_line = source_by_rel[edge.rel_path].line_at(edge.line)
            findings.append(Finding(rule_id=self.id, rel_path=edge.rel_path, line=edge.line, source_line=source_line, symbol=edge.target, extra={"source": edge.source, "target": edge.target, "reason": reason}))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Directs the repair toward moving ownership or inverting the dependency seam.
        reason = finding.extra.get("reason", "dependency graph violation")
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} imports {finding.symbol}: {reason}.", why_blocked="Cycles make module ownership and initialization order non-deterministic, while upward imports make foundational code depend on orchestration details. Agents cannot safely change one side without reconstructing a wider graph and may create import-time failures.", how_to_fix="Move shared contracts downward into a dependency-light module, inject the higher-layer behavior through a Protocol, or move the helper to the layer that owns both concepts. Keep package façade re-exports out of the concrete graph and preserve the documented lower-layer direction.", correct_examples=("vidbyte/lib/errors/base.py - dependency-light error definitions consumed by higher layers.", "vidbyte/tools/builtins/code_search/semantic.py - capability dependency is expressed through EmbeddingProvider."), will_not_work=("Adding a local import inside a function to hide the cycle.", "Using a broad utility module that still imports both layers or adding a blanket graph exception."), verify=self.verify_command())

RULE = DirectedDependencyGraphRule()

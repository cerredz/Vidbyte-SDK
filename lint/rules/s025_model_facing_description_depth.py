"""FILE: lint/rules/s025_model_facing_description_depth.py

PURPOSE: Defines S025 as the SDK's model-facing tool/parameter description depth policy.
ROLE IN CODEBASE: Keeps ToolSpec and ToolParameter descriptions readable as real model context.
ARCHITECTURE NOTE: Class hierarchy and constants are extracted statically; importing the SDK is forbidden.
FUNCTION INVENTORY: ClassHierarchyIndex, BaseToolClosure, DescriptionResolver, SentenceCounter, ModelFacingDescriptionDepthAnalyzer/Rule.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Descriptions built by a method call or a non-literal attribute are exempted, not flagged.
RELATED DOCS: docs/design/sdk-tool-description-depth-lint-rule.md, field-guide/vidbyte-sdk/model-facing-tool-contracts.md
TESTS: Exercised by python lint/run.py --rule S025.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import PurePosixPath

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

BASE_TOOL_NAME = "BaseTool"
TOOL_SPEC_CALLEE = "ToolSpec"
TOOL_PARAMETER_CALLEE = "ToolParameter"
MINIMUM_SENTENCES = 4
MAX_IMPORT_HOPS = 3
ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "vs.", "approx.")


@dataclass(frozen=True, slots=True)
class ClassRecord:
    """One tracked class definition with its written base identifiers."""

    name: str
    bases: tuple[str, ...]
    file: SourceFile
    node: ast.ClassDef


class ClassHierarchyIndex:
    """Maps every tracked class name to its base identifiers and defining file."""

    def build(self, files: tuple[SourceFile, ...]) -> dict[str, ClassRecord]:
        # Walks every parsed module and records one ClassRecord per class definition.
        index: dict[str, ClassRecord] = {}
        for source in files:
            if source.tree is None:
                continue
            for node in ast.walk(source.tree):
                if isinstance(node, ast.ClassDef):
                    index[node.name] = ClassRecord(name=node.name, bases=self._base_names(node), file=source, node=node)
        return index

    def _base_names(self, node: ast.ClassDef) -> tuple[str, ...]:
        # Reads each base as its bare name or dotted-attribute identifier.
        names: list[str] = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                names.append(base.id)
            elif isinstance(base, ast.Attribute):
                names.append(base.attr)
        return tuple(names)


class BaseToolClosure:
    """Computes every tracked class transitively subclassing BaseTool."""

    def in_scope_classes(self, index: dict[str, ClassRecord]) -> tuple[ClassRecord, ...]:
        # Runs a fixed-point BFS: a class joins scope once any base is already in scope.
        scoped: set[str] = {BASE_TOOL_NAME}
        changed = True
        while changed:
            changed = False
            for record in index.values():
                if record.name not in scoped and any(base in scoped for base in record.bases):
                    scoped.add(record.name)
                    changed = True
        return tuple(record for name, record in index.items() if name in scoped and name != BASE_TOOL_NAME)


class DescriptionResolver:
    """Statically resolves a description expression to text when possible."""

    def resolve(self, expr: ast.expr, context: SourceFile, owner: ClassRecord | None, files_by_rel: dict[str, SourceFile], hops: int = 0) -> str | None:
        # Dispatches by AST node shape; returns None when the value cannot be proven statically.
        if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
            return expr.value
        if isinstance(expr, ast.JoinedStr):
            return self._resolve_joined_str(expr)
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
            return self._resolve_binop(expr, context, owner, files_by_rel, hops)
        if isinstance(expr, ast.Name):
            return self._resolve_name(expr.id, context, files_by_rel, hops)
        if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name) and expr.value.id == "self" and owner is not None:
            return self._resolve_self_attribute(expr.attr, owner, files_by_rel, hops)
        return None

    def _resolve_joined_str(self, expr: ast.JoinedStr) -> str | None:
        # Concatenates literal segments and splices a neutral placeholder for each interpolation.
        parts: list[str] = []
        for value in expr.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append("0")
            else:
                return None
        return "".join(parts)

    def _resolve_binop(self, expr: ast.BinOp, context: SourceFile, owner: ClassRecord | None, files_by_rel: dict[str, SourceFile], hops: int) -> str | None:
        # Concatenates both operands only when each side resolves independently.
        left = self.resolve(expr.left, context, owner, files_by_rel, hops)
        right = self.resolve(expr.right, context, owner, files_by_rel, hops)
        if left is None or right is None:
            return None
        return left + right

    def _resolve_name(self, name: str, context: SourceFile, files_by_rel: dict[str, SourceFile], hops: int) -> str | None:
        # Finds a module-level assignment in this file, else follows one bounded import hop.
        if context.tree is None:
            return None
        assigned = self._module_level_value(context.tree, name)
        if assigned is not None:
            return self.resolve(assigned, context, None, files_by_rel, hops)
        if hops >= MAX_IMPORT_HOPS:
            return None
        hop = self._import_hop(context, name, files_by_rel)
        if hop is None:
            return None
        target_file, original_name = hop
        return self._resolve_name(original_name, target_file, files_by_rel, hops + 1)

    def _module_level_value(self, tree: ast.Module, name: str) -> ast.expr | None:
        # Returns the assigned expression for one module-level Assign/AnnAssign target.
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name:
                return node.value
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name and node.value is not None:
                return node.value
        return None

    def _import_hop(self, context: SourceFile, name: str, files_by_rel: dict[str, SourceFile]) -> tuple[SourceFile, str] | None:
        # Finds the import statement binding `name` and returns its source file and original name.
        if context.tree is None:
            return None
        for node in context.tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue
            for alias in node.names:
                if (alias.asname or alias.name) != name:
                    continue
                rel = self._module_to_rel_path(node, context.rel)
                target_file = files_by_rel.get(rel) if rel else None
                if target_file is not None:
                    return target_file, alias.name
        return None

    def _module_to_rel_path(self, node: ast.ImportFrom, importer_rel: str) -> str | None:
        # Converts an absolute or relative module reference to a tracked repo-relative path.
        if node.level == 0:
            return node.module.replace(".", "/") + ".py" if node.module else None
        package_dir = PurePosixPath(importer_rel).parent
        for _ in range(node.level - 1):
            package_dir = package_dir.parent
        if node.module:
            return str(package_dir / node.module.replace(".", "/")) + ".py"
        return str(package_dir / "__init__.py")

    def _resolve_self_attribute(self, attr: str, owner: ClassRecord, files_by_rel: dict[str, SourceFile], hops: int) -> str | None:
        # Finds a simple self.<attr> = <expr> assignment inside the owning class's own __init__.
        init = next((item for item in owner.node.body if isinstance(item, ast.FunctionDef) and item.name == "__init__"), None)
        if init is None:
            return None
        for node in ast.walk(init):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self" and target.attr == attr:
                return self.resolve(node.value, owner.file, owner, files_by_rel, hops)
        return None


class SentenceCounter:
    """Counts sentence-like units in resolved model-facing description text."""

    def count(self, text: str) -> int:
        # Counts word-ending terminal punctuation, floored at 1 for any non-empty text.
        stripped = text.strip()
        if not stripped:
            return 0
        total = sum(1 for index, char in enumerate(stripped) if char in ".!?" and self._is_terminal(stripped, index))
        return total if total else 1

    def _is_terminal(self, text: str, index: int) -> bool:
        # A real sentence boundary is followed by whitespace or nothing and is not an abbreviation.
        if index + 1 < len(text) and not text[index + 1].isspace():
            return False
        return not any(text[: index + 1].lower().endswith(abbreviation) for abbreviation in ABBREVIATIONS)


class ModelFacingDescriptionDepthAnalyzer:
    """Finds every BaseTool-derived class's spec() and reports short descriptions."""

    def analyze(self, catalog: SourceCatalog) -> list[tuple[str, int, str, str, int]]:
        # Builds the class graph once, then resolves every reachable description.
        files = catalog.python_files()
        files_by_rel = {source.rel: source for source in files}
        index = ClassHierarchyIndex().build(files)
        in_scope = BaseToolClosure().in_scope_classes(index)
        resolver = DescriptionResolver()
        counter = SentenceCounter()
        hits: list[tuple[str, int, str, str, int]] = []
        for record in in_scope:
            spec_method = self._spec_method(record.node)
            if spec_method is not None:
                hits.extend(self._check_spec_method(record, spec_method, resolver, counter, files_by_rel))
        return hits

    def _spec_method(self, node: ast.ClassDef) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        # Returns this class's own spec() method, ignoring inherited implementations.
        return next((item for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "spec"), None)

    def _check_spec_method(self, record: ClassRecord, method: ast.FunctionDef | ast.AsyncFunctionDef, resolver: DescriptionResolver, counter: SentenceCounter, files_by_rel: dict[str, SourceFile]) -> list[tuple[str, int, str, str, int]]:
        # Resolves the tool's own description plus every parameter description in one spec().
        hits: list[tuple[str, int, str, str, int]] = []
        tool_symbol = record.name
        tool_calls = [node for node in ast.walk(method) if isinstance(node, ast.Call) and self._callee_name(node) == TOOL_SPEC_CALLEE]
        for call in tool_calls:
            resolved_name = self._resolve_argument(call, "name", 0, record, resolver, files_by_rel)
            if resolved_name:
                tool_symbol = resolved_name
            hits.extend(self._describe(call, "description", 1, record, tool_symbol, "tool", resolver, counter, files_by_rel))
        parameter_calls = [node for node in ast.walk(method) if isinstance(node, ast.Call) and self._callee_name(node) == TOOL_PARAMETER_CALLEE]
        for call in parameter_calls:
            param_symbol = self._resolve_argument(call, "name", 0, record, resolver, files_by_rel) or "<parameter>"
            hits.extend(self._describe(call, "description", 2, record, f"{tool_symbol}.{param_symbol}", "parameter", resolver, counter, files_by_rel))
        return hits

    def _describe(self, call: ast.Call, keyword: str, position: int, record: ClassRecord, symbol: str, kind: str, resolver: DescriptionResolver, counter: SentenceCounter, files_by_rel: dict[str, SourceFile]) -> list[tuple[str, int, str, str, int]]:
        # Resolves one description argument and reports it when it reads too short.
        expr = self._argument(call, keyword, position)
        if expr is None:
            return []
        resolved = resolver.resolve(expr, record.file, record, files_by_rel)
        if resolved is None:
            return []
        count = counter.count(resolved)
        if count < MINIMUM_SENTENCES:
            return [(record.file.rel, call.lineno, symbol, kind, count)]
        return []

    def _resolve_argument(self, call: ast.Call, keyword: str, position: int, record: ClassRecord, resolver: DescriptionResolver, files_by_rel: dict[str, SourceFile]) -> str | None:
        # Resolves a call argument expected to be a short identifying string literal.
        expr = self._argument(call, keyword, position)
        return resolver.resolve(expr, record.file, record, files_by_rel) if expr is not None else None

    def _callee_name(self, call: ast.Call) -> str:
        # Reads a call's bare or attribute callee name for pattern matching.
        if isinstance(call.func, ast.Name):
            return call.func.id
        if isinstance(call.func, ast.Attribute):
            return call.func.attr
        return ""

    def _argument(self, call: ast.Call, keyword: str, position: int) -> ast.expr | None:
        # Returns a call's keyword argument, else its positional argument, else None.
        for kw in call.keywords:
            if kw.arg == keyword:
                return kw.value
        return call.args[position] if len(call.args) > position else None


class ModelFacingDescriptionDepthRule(Rule):
    """Requires every BaseTool's ToolSpec/ToolParameter descriptions to read as real context."""

    id = "S025"
    name = "model-facing-description-depth"
    severity = "blocking"
    summary = "ToolSpec and ToolParameter descriptions read as general 4-5 sentence context, not a label."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Delegates detection to the analyzer, then wraps each hit as a stable Finding.
        files = {source.rel: source for source in catalog.python_files()}
        hits = ModelFacingDescriptionDepthAnalyzer().analyze(catalog)
        return [Finding(rule_id=self.id, rel_path=path, line=line, source_line=files[path].line_at(line), symbol=symbol, extra={"kind": kind, "sentence_count": str(count)}) for path, line, symbol, kind, count in hits]

    def explain(self, finding: Finding) -> Diagnostic:
        # Names the exact tool/parameter symbol and count, and demands a general 4-5 sentence rewrite.
        kind = finding.extra.get("kind", "tool")
        count = finding.extra.get("sentence_count", "0")
        field = "ToolSpec.description" if kind == "tool" else "ToolParameter.description"
        return Diagnostic(
            what_happened=f"{finding.rel_path}:{finding.line} {finding.symbol} has a {field} with only {count} resolvable sentence(s).",
            why_blocked="This text is the only operating knowledge a model has of what this field is and why it exists on the tool. A one-line label under-specifies scope and motivation, so the model under-uses or misuses the tool relative to its real capability, exactly the gap field-guide/vidbyte-sdk/model-facing-tool-contracts.md was written to close.",
            how_to_fix="Rewrite this field as a general, 4-5 sentence description of what the field is and why it is in the tool: state what it represents, why it is part of this tool's contract, when a model should rely on it, and any scope or behavior the model needs before calling it. Write it as prose the model reads at call time, not a code comment, and do not add concrete input examples.",
            correct_examples=(
                "vidbyte/tools/builtins/memory/supermemory.py - a tool description already written as 4 general sentences.",
                "vidbyte/tools/builtins/providers/mongodb.py - a tool description composed from a shared, sufficiently long fragment constant.",
                "field-guide/vidbyte-sdk/model-facing-tool-contracts.md - the documented convention this rule enforces.",
            ),
            will_not_work=(
                "Padding the string with filler or repeated clauses just to raise the sentence count.",
                "Moving the depth into a docstring or code comment instead of the ToolSpec/ToolParameter field the model actually receives.",
                "Building the description from a runtime method call so this rule cannot see it; the model still only gets what that call returns, so a short result is still a short result.",
            ),
            verify=self.verify_command(),
        )


RULE = ModelFacingDescriptionDepthRule()

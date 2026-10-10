"""FILE: lint/rules/c006_source_index.py

PURPOSE: Read-only source indexes that C006 consults: literal values, module constants, and which SDK classes are engine-built records.
ROLE IN CODEBASE: Supports lint/rules/c006_finite_numeric_guards.py, which evaluates guards; this module only reads what the source says.
ARCHITECTURE NOTE: Static AST only. Constants resolve through absolute `from vidbyte... import NAME` re-exports; class facts come from every tracked Python file, because a class a test, script, or example names is one callers construct.
FUNCTION INVENTORY: LiteralReader reads literals; ModuleConstants holds one module's literals; ConstantResolver follows imports; EngineRecordIndex knows SDK classes and engine-built records.
COMMON MODIFICATION PATTERNS: Add a literal shape or an engine-record condition here, then rerun C006 and its scratch fixtures.
WHAT NOT TO DO: Do not import SDK modules, execute source, or exempt a class that any tracked file outside vidbyte/ names.
KNOWN EDGE CASES: A class defined in more than one SDK module is never resolved or exempted. String annotations outside vidbyte/ do not count as naming a class.
RELATED DOCS: docs/design/lint-sdk-settings-validation.md
TESTS: python lint/run.py --rule C006; fixture and mutation results are recorded in the S1 pull request body.
"""

from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass

from lint.core.discovery import SourceFile

_CONFIG_SUFFIX = re.compile(r"(Settings|Config|Configuration|Policy|Options)$")
_PACKAGE = "vidbyte/"
_IMPORT_DEPTH = 3


class LiteralReader:
    """Reads the literal values a guard may compare against, without executing anything."""

    @staticmethod
    def number(node: ast.AST) -> float | int | None:
        # Reads numeric literals, negated literals, float("inf"/"nan"), and math.inf/math.nan.
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)) and isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, (int, float)) and not isinstance(node.operand.value, bool):
            return -node.operand.value if isinstance(node.op, ast.USub) else node.operand.value
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "float" and len(node.args) == 1 and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            text = node.args[0].value.strip().lower()
            return float(text) if text in {"inf", "+inf", "-inf", "infinity", "+infinity", "-infinity", "nan"} else None
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "math" and node.attr in {"inf", "nan"}:
            return math.inf if node.attr == "inf" else math.nan
        return None

    @staticmethod
    def strings(node: ast.AST) -> tuple[str, ...]:
        # Returns the strings of a literal tuple/list of string constants, else an empty tuple.
        if isinstance(node, (ast.Tuple, ast.List)) and node.elts and all(isinstance(item, ast.Constant) and isinstance(item.value, str) for item in node.elts):
            return tuple(item.value for item in node.elts if isinstance(item, ast.Constant) and isinstance(item.value, str))
        return ()

    @staticmethod
    def name(node: ast.AST) -> str:
        # Returns the final identifier of a Name or Attribute, else an empty string.
        return node.attr if isinstance(node, ast.Attribute) else (node.id if isinstance(node, ast.Name) else "")


@dataclass(frozen=True, slots=True)
class ModuleConstants:
    """Module-level literals the rule may read: string tuples for field sweeps and numbers for bounds."""

    field_tuples: dict[str, tuple[str, ...]]
    numbers: dict[str, float | int]

    @classmethod
    def read(cls, tree: ast.Module) -> ModuleConstants:
        # One pass over top-level assignments; nothing is imported or executed.
        field_tuples: dict[str, tuple[str, ...]] = {}
        numbers: dict[str, float | int] = {}
        for node in tree.body:
            target = node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else (node.target if isinstance(node, ast.AnnAssign) else None)
            value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
            if isinstance(target, ast.Name) and value is not None:
                number = LiteralReader.number(value)
                if LiteralReader.strings(value):
                    field_tuples[target.id] = LiteralReader.strings(value)
                elif number is not None:
                    numbers[target.id] = number
        return cls(field_tuples=field_tuples, numbers=numbers)

    def merged(self, imported: ModuleConstants) -> ModuleConstants:
        # A module's own literals shadow the names it imports.
        return ModuleConstants(field_tuples={**imported.field_tuples, **self.field_tuples}, numbers={**imported.numbers, **self.numbers})


class ConstantResolver:
    """Resolves the literal constants a module imports from another tracked SDK module, following re-exports."""

    def __init__(self, sources: tuple[SourceFile, ...]) -> None:
        # Index every parsed production module by dotted name, so an import resolves without executing anything.
        self._trees = {self.dotted(source.rel): source.tree for source in sources if source.tree is not None}
        self._cache: dict[tuple[str, int], ModuleConstants] = {}

    @staticmethod
    def dotted(rel: str) -> str:
        # vidbyte/lib/constants/jev.py -> vidbyte.lib.constants.jev; a package __init__ is the package itself.
        parts = rel.removesuffix(".py").split("/")
        return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)

    def constants(self, module: str, depth: int = _IMPORT_DEPTH) -> ModuleConstants:
        # Own literals plus absolute `from vidbyte... import NAME` literals, re-exports followed at most depth hops.
        if (module, depth) in self._cache:
            return self._cache[(module, depth)]
        tree = self._trees.get(module)
        own = ModuleConstants.read(tree) if tree is not None else ModuleConstants(field_tuples={}, numbers={})
        imported = ModuleConstants(field_tuples={}, numbers={})
        for node in tree.body if tree is not None and depth > 0 else ():
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module in self._trees:
                found = self.constants(node.module, depth - 1)
                imported.field_tuples.update({alias.asname or alias.name: found.field_tuples[alias.name] for alias in node.names if alias.name in found.field_tuples})
                imported.numbers.update({alias.asname or alias.name: found.numbers[alias.name] for alias in node.names if alias.name in found.numbers})
        self._cache[(module, depth)] = own.merged(imported)
        return self._cache[(module, depth)]


class EngineRecordIndex:
    """Knows every SDK class by name and which of them are engine-built records that callers never construct."""

    def __init__(self, sources: tuple[SourceFile, ...]) -> None:
        # One pass over every tracked Python file: class definitions, base names, package exports, and who names each class.
        self._classes: dict[str, list[ast.ClassDef]] = {}
        self._bases: set[str] = set()
        self._exported: set[str] = set()
        self._built: set[str] = set()
        self._named_outside: set[str] = set()
        for source in sources:
            if source.tree is not None:
                self._read(source.rel, source.tree)

    def definition(self, name: str) -> ast.ClassDef | None:
        # The class an annotation names, when exactly one SDK module defines it.
        found = self._classes.get(name, [])
        return found[0] if len(found) == 1 else None

    def engine_built(self, name: str) -> bool:
        # Exempt only a record that the SDK builds and that no test, script, or example ever names.
        node = self.definition(name)
        if node is None or _CONFIG_SUFFIX.search(name) or name in self._bases:
            return False
        if name not in self._built or name in self._named_outside:
            return False
        # A plain class exported from a package is a component callers configure through its constructor.
        return self.is_dataclass(node) or name not in self._exported

    def engine_helper(self, tree: ast.Module, name: str) -> bool:
        # A module-level helper is engine-only when every call to it in its module sits inside an engine-built record.
        owners = [owner.name for owner in ast.walk(tree) if isinstance(owner, ast.ClassDef) for node in ast.walk(owner) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name]
        total = sum(1 for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name)
        return bool(owners) and len(owners) == total and all(self.engine_built(owner) for owner in owners)

    @staticmethod
    def is_dataclass(node: ast.ClassDef) -> bool:
        # @dataclass and @dataclass(...) both mark a record whose fields are its constructor.
        return any(LiteralReader.name(item.func if isinstance(item, ast.Call) else item) == "dataclass" for item in node.decorator_list)

    def _read(self, rel: str, tree: ast.Module) -> None:
        # Production code defines, exports, and builds classes; any other tracked file that names a class is a caller.
        inside = rel.startswith(_PACKAGE)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                self._bases.update(LiteralReader.name(base) for base in node.bases)
                if inside:
                    self._classes.setdefault(node.name, []).append(node)
            elif inside and isinstance(node, ast.Call):
                self._built.update({LiteralReader.name(node.func), LiteralReader.name(node.func.value) if isinstance(node.func, ast.Attribute) else ""} - {""})
            elif not inside and isinstance(node, (ast.Name, ast.Attribute, ast.alias)):
                self._named_outside.add(node.name.rpartition(".")[2] if isinstance(node, ast.alias) else LiteralReader.name(node))
        if inside and rel.endswith("/__init__.py"):
            self._exported.update(self._all_names(tree))

    @staticmethod
    def _all_names(tree: ast.Module) -> set[str]:
        # The string entries of a package's __all__, however it is assigned or extended.
        names: set[str] = set()
        for node in tree.body:
            targets = node.targets if isinstance(node, ast.Assign) else ([node.target] if isinstance(node, (ast.AnnAssign, ast.AugAssign)) else [])
            value = getattr(node, "value", None)
            if value is not None and any(LiteralReader.name(target) == "__all__" for target in targets):
                names.update(item.value for item in ast.walk(value) if isinstance(item, ast.Constant) and isinstance(item.value, str))
        return names

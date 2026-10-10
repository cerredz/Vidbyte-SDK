"""FILE: lint/core/python_index.py

PURPOSE: Builds a static index of every tracked vidbyte module (imports, module-level constants, functions, classes with their methods, class-body constants, annotations, and dataclass fields) and resolves a name or annotation to the constant, function, class, or module it refers to, following imports across modules.
ROLE IN CODEBASE: The source model under lint/core/string_flow.py (which evaluates expressions over it) and lint/core/url_flow.py (which walks every function body for request calls). Used by rules C017 and C018 through those modules.
ARCHITECTURE NOTE: Nothing here imports vidbyte; every fact comes from the ASTs SourceCatalog already parsed. Module-level statements inside if/try/with blocks count, because they still run at import time. A function body is summarized once (BodyFacts) without descending into nested functions, classes, or lambdas, whose statements belong to their own scopes.
FUNCTION INVENTORY: ImportRef, ClassFacts, ModuleFacts, FunctionFacts, BodyFacts, ConstSymbol records; ModuleIndex (module, function, body, resolve, resolve_import, bases, is_enum, annotation_classes, symbol_of); direct_calls; private AST helpers for imports, bindings, decorators, and dotted names.
COMMON MODIFICATION PATTERNS: Teach the index a new binding form by extending _BodyReader._record or ModuleFacts._read, then add a C017 scratch fixture that depends on it.
WHAT NOT TO DO: Do not import or execute vidbyte modules, and do not resolve a name by searching every module for it; resolution must follow the importing module's actual imports.
KNOWN EDGE CASES: Star imports are followed in order. A name bound both by assignment and by import resolves to the assignment. Methods of classes nested in functions have no owner. bases() approximates the MRO depth-first, left to right.
RELATED DOCS: docs/design/lint-sdk-cross-repo-contracts.md (C017 URL tracing).
TESTS: python lint/run.py --rule C017 and --rule C018; scratch fixtures and mutants are recorded in the S4 pull request body.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from lint.core.discovery import SourceCatalog, SourceFile

_PROPERTY_DECORATORS = frozenset({"property", "cached_property"})
_ENUM_BASES = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag", "ReprEnum"})
_TYPE_WRAPPERS = frozenset({"Optional", "Union", "Annotated", "ClassVar", "Final", "Type", "type"})
_DICT_MUTATORS = frozenset({"update", "setdefault", "pop", "popitem", "clear", "__setitem__", "__delitem__"})
_SELF_KINDS = frozenset({"method", "classmethod", "property"})


@dataclass(frozen=True, slots=True)
class ImportRef:
    """What a name imported into a module refers to: a module (name None) or one name inside a module."""

    module: str
    name: str | None


class ClassFacts:
    """One module-level class: bases, methods, class-body constants, annotations, and dataclass field order."""

    def __init__(self, module: ModuleFacts, node: ast.ClassDef) -> None:
        # Reads the class body once; nested classes and statements inside methods are not class constants.
        self.module = module
        self.node = node
        self.name = node.name
        self.methods: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        self.constants: dict[str, list[ast.expr | None]] = {}
        self.annotations: dict[str, ast.expr] = {}
        self.fields: list[str] = []
        self.classvars: set[str] = set()
        self.is_dataclass = any(_decorator_name(item) == "dataclass" for item in node.decorator_list)
        for statement in node.body:
            self._read(statement)

    def _read(self, statement: ast.stmt) -> None:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.methods[statement.name] = statement
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            name = statement.target.id
            self.annotations[name] = statement.annotation
            if _annotation_head(statement.annotation) == "ClassVar":
                self.classvars.add(name)
            else:
                self.fields.append(name)
            if statement.value is not None:
                self.constants.setdefault(name, []).append(statement.value)
        elif isinstance(statement, ast.Assign):
            for target in statement.targets:
                for name, value in _bound_names(target, statement.value):
                    self.constants.setdefault(name, []).append(value)

    @property
    def rel(self) -> str:
        return self.module.rel


class ModuleFacts:
    """One parsed vidbyte module: its imports, module-level constants, functions, and classes."""

    def __init__(self, source: SourceFile, dotted: str, is_package: bool) -> None:
        # Reads module-level statements, including those nested in if/try/with blocks but not in functions or classes.
        self.source = source
        self.rel = source.rel
        self.dotted = dotted
        self.package = dotted if is_package else dotted.rpartition(".")[0]
        self.imports: dict[str, ImportRef] = {}
        self.star_imports: list[str] = []
        self.constants: dict[str, list[ast.expr | None]] = {}
        self.functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        self.classes: dict[str, ClassFacts] = {}
        if source.tree is not None:
            for statement in _module_statements(source.tree.body):
                self._read(statement)

    def _read(self, statement: ast.stmt) -> None:
        if isinstance(statement, (ast.Import, ast.ImportFrom)):
            self.imports.update(_import_bindings(statement, self.package))
            if isinstance(statement, ast.ImportFrom) and any(alias.name == "*" for alias in statement.names):
                self.star_imports.append(_absolute_module(statement, self.package))
        elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.functions[statement.name] = statement
        elif isinstance(statement, ast.ClassDef):
            self.classes[statement.name] = ClassFacts(self, statement)
        elif isinstance(statement, ast.Assign):
            for target in statement.targets:
                for name, value in _bound_names(target, statement.value):
                    self.constants.setdefault(name, []).append(value)
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name) and statement.value is not None:
            self.constants.setdefault(statement.target.id, []).append(statement.value)
        elif isinstance(statement, ast.AugAssign) and isinstance(statement.target, ast.Name):
            self.constants.setdefault(statement.target.id, []).append(None)
        elif isinstance(statement, (ast.For, ast.AsyncFor)):
            for name, _ in _bound_names(statement.target, None):
                self.constants.setdefault(name, []).append(None)

    def location(self, node: ast.AST) -> str:
        return f"{self.rel}:{getattr(node, 'lineno', 1)}"


@dataclass(frozen=True, slots=True, eq=False)
class FunctionFacts:
    """One function or method definition with its owning class and calling convention."""

    module: ModuleFacts
    node: ast.FunctionDef | ast.AsyncFunctionDef
    owner: ClassFacts | None
    kind: str

    @property
    def qualname(self) -> str:
        return f"{self.owner.name}.{self.node.name}" if self.owner is not None else self.node.name

    @property
    def location(self) -> str:
        return f"{self.module.rel}:{self.node.lineno}"

    def positional(self) -> list[ast.arg]:
        return [*self.node.args.posonlyargs, *self.node.args.args]

    def param_names(self) -> set[str]:
        args = self.node.args
        names = {arg.arg for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
        names.update(arg.arg for arg in (args.vararg, args.kwarg) if arg is not None)
        return names

    def receiver_name(self) -> str:
        # The first parameter's name when the convention binds it implicitly (self or cls), else "".
        positional = self.positional()
        return positional[0].arg if self.kind in _SELF_KINDS and positional else ""

    def annotation(self, name: str) -> ast.expr | None:
        args = self.node.args
        for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg):
            if arg is not None and arg.arg == name:
                return arg.annotation
        return None

    def default(self, name: str) -> ast.expr | None:
        # The default expression of a parameter, if it has one.
        args = self.node.args
        positional = self.positional()
        for arg, default in zip(positional[len(positional) - len(args.defaults):], args.defaults, strict=True):
            if arg.arg == name:
                return default
        for arg, kw_default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
            if arg.arg == name:
                return kw_default
        return None


@dataclass(slots=True)
class BodyFacts:
    """What one function body binds, returns, mutates, and calls, excluding nested functions and classes."""

    assigned: dict[str, list[ast.expr | None]] = field(default_factory=dict)
    imports: dict[str, ImportRef] = field(default_factory=dict)
    returns: list[ast.Return] = field(default_factory=list)
    yields: bool = False
    item_stores: dict[str, list[ast.expr | None]] = field(default_factory=dict)
    mutated: set[str] = field(default_factory=set)
    globals: set[str] = field(default_factory=set)
    calls: list[ast.Call] = field(default_factory=list)
    attribute_stores: list[tuple[ast.Attribute, ast.expr | None, ast.expr | None]] = field(default_factory=list)


class ModuleIndex:
    """Every tracked vidbyte module by dotted name, with symbol resolution across imports."""

    def __init__(self, catalog: SourceCatalog) -> None:
        # Indexes modules whose source parsed; a syntax error elsewhere is S001's concern, not a trace input.
        self.modules: dict[str, ModuleFacts] = {}
        for source in catalog.python_files():
            if source.tree is None:
                continue
            dotted, is_package = _dotted_name(source.rel)
            self.modules[dotted] = ModuleFacts(source, dotted, is_package)
        self._functions: dict[int, FunctionFacts] = {}
        self._bodies: dict[int, BodyFacts] = {}

    def module(self, dotted: str) -> ModuleFacts | None:
        return self.modules.get(dotted)

    def function(self, module: ModuleFacts, node: ast.FunctionDef | ast.AsyncFunctionDef, owner: ClassFacts | None) -> FunctionFacts:
        # One FunctionFacts per definition node, so identity comparisons are reliable.
        facts = self._functions.get(id(node))
        if facts is None:
            facts = FunctionFacts(module, node, owner, _function_kind(node, owner))
            self._functions[id(node)] = facts
        return facts

    def body(self, function: FunctionFacts) -> BodyFacts:
        facts = self._bodies.get(id(function.node))
        if facts is None:
            facts = _BodyReader(function.module.package).read(function.node)
            self._bodies[id(function.node)] = facts
        return facts

    def resolve(self, module: ModuleFacts, name: str, seen: frozenset[tuple[str, str]] = frozenset()) -> object | None:
        # Returns a ConstSymbol, FunctionFacts, ClassFacts, or ModuleFacts for a module-level name, following imports.
        key = (module.dotted, name)
        if key in seen:
            return None
        seen = seen | {key}
        if name in module.constants:
            return ConstSymbol(module, None, name, tuple(module.constants[name]))
        if name in module.functions:
            return self.function(module, module.functions[name], None)
        if name in module.classes:
            return module.classes[name]
        if name in module.imports:
            return self.resolve_import(module.imports[name], seen)
        for star in module.star_imports:
            target = self.module(star)
            if target is not None:
                found = self.resolve(target, name, seen)
                if found is not None:
                    return found
        return None

    def resolve_import(self, ref: ImportRef, seen: frozenset[tuple[str, str]] = frozenset()) -> object | None:
        # A module import names the module; a from-import names a symbol in it, or a submodule of a package.
        if ref.name is None:
            return self.module(ref.module)
        target = self.module(ref.module)
        if target is not None:
            found = self.resolve(target, ref.name, seen)
            if found is not None:
                return found
        return self.module(f"{ref.module}.{ref.name}")

    def bases(self, cls: ClassFacts) -> list[ClassFacts]:
        # The class and its resolvable vidbyte bases in a depth-first, left-to-right order (an MRO approximation).
        order: list[ClassFacts] = []
        pending = [cls]
        while pending:
            current = pending.pop(0)
            if any(current is seen for seen in order):
                continue
            order.append(current)
            for base in current.node.bases:
                resolved = self.annotation_classes(base, current.module)
                pending.extend(resolved)
        return order

    def is_enum(self, cls: ClassFacts) -> bool:
        # Enum members are not plain strings, so their class-body assignments are not traced as constants.
        for current in self.bases(cls):
            for base in current.node.bases:
                if _annotation_head(base) in _ENUM_BASES:
                    return True
        return False

    def annotation_classes(self, annotation: ast.expr | None, module: ModuleFacts) -> list[ClassFacts]:
        # The vidbyte classes an annotation names, looking through Optional, Union, `X | None`, and string annotations.
        if annotation is None:
            return []
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            try:
                parsed = ast.parse(annotation.value, mode="eval").body
            except SyntaxError:
                return []
            return self.annotation_classes(parsed, module)
        if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
            return [*self.annotation_classes(annotation.left, module), *self.annotation_classes(annotation.right, module)]
        if isinstance(annotation, ast.Subscript):
            if _annotation_head(annotation.value) not in _TYPE_WRAPPERS:
                return []
            inner = annotation.slice
            items = list(inner.elts) if isinstance(inner, ast.Tuple) else [inner]
            if _annotation_head(annotation.value) == "Annotated":
                items = items[:1]
            return [cls for item in items for cls in self.annotation_classes(item, module)]
        symbol = self.symbol_of(annotation, module)
        return [symbol] if isinstance(symbol, ClassFacts) else []

    def symbol_of(self, node: ast.expr, module: ModuleFacts) -> object | None:
        # Resolves a Name or a dotted Attribute chain at module scope.
        if isinstance(node, ast.Name):
            return self.resolve(module, node.id)
        if isinstance(node, ast.Attribute):
            owner = self.symbol_of(node.value, module)
            if isinstance(owner, ModuleFacts):
                return self.resolve(owner, node.attr)
        return None


@dataclass(frozen=True, slots=True, eq=False)
class ConstSymbol:
    """A module-level or class-body name bound by assignment; None in values marks an opaque binding."""

    module: ModuleFacts
    owner: ClassFacts | None
    name: str
    values: tuple[ast.expr | None, ...]


class _BodyReader:
    """Collects a function body's bindings, returns, item stores, mutations, attribute stores, and calls."""

    def __init__(self, package: str) -> None:
        self.package = package
        self.facts = BodyFacts()

    def read(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> BodyFacts:
        for statement in node.body:
            self._visit(statement)
        return self.facts

    def _visit(self, node: ast.AST) -> None:
        # Records this node, then descends into children except nested scopes (their calls belong to them).
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            return
        self._record(node)
        for child in ast.iter_child_nodes(node):
            self._visit(child)

    def _record(self, node: ast.AST) -> None:
        facts = self.facts
        if isinstance(node, ast.Call):
            facts.calls.append(node)
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.attr in _DICT_MUTATORS:
                facts.mutated.add(func.value.id)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                self._store(target, node.value, None)
        elif isinstance(node, ast.AnnAssign):
            self._store(node.target, node.value, node.annotation)
        elif isinstance(node, ast.AugAssign):
            self._store(node.target, None, None)
            if isinstance(node.target, ast.Name):
                facts.mutated.add(node.target.id)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            self._store(node.target, None, None, opaque_only=True)
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            self._store(node.optional_vars, None, None, opaque_only=True)
        elif isinstance(node, ast.NamedExpr):
            self._store(node.target, node.value, None)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            facts.assigned.setdefault(node.name, []).append(None)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            facts.imports.update(_import_bindings(node, self.package))
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            facts.globals.update(node.names)
        elif isinstance(node, ast.Return):
            facts.returns.append(node)
        elif isinstance(node, (ast.Yield, ast.YieldFrom)):
            facts.yields = True
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
                    facts.mutated.add(target.value.id)

    def _store(self, target: ast.expr, value: ast.expr | None, annotation: ast.expr | None, opaque_only: bool = False) -> None:
        facts = self.facts
        if isinstance(target, ast.Name):
            # A bare annotation (`x: T`) binds nothing; an unpacking, loop, or augmented target binds an opaque value.
            if value is None and annotation is not None and not opaque_only:
                return
            facts.assigned.setdefault(target.id, []).append(value)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._store(element.value if isinstance(element, ast.Starred) else element, None, None, opaque_only=True)
        elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
            key = target.slice if not isinstance(target.slice, ast.Slice) else None
            facts.item_stores.setdefault(target.value.id, []).append(key)
        elif isinstance(target, ast.Attribute):
            facts.attribute_stores.append((target, annotation, value))
        elif isinstance(target, ast.Starred):
            self._store(target.value, None, None, opaque_only=True)


def _module_statements(body: Iterable[ast.stmt]) -> Iterator[ast.stmt]:
    # Module-level statements, flattening if/try/with blocks, which still execute at module scope.
    for statement in body:
        yield statement
        if isinstance(statement, (ast.If, ast.With, ast.AsyncWith)):
            yield from _module_statements(statement.body)
            yield from _module_statements(getattr(statement, "orelse", []))
        elif isinstance(statement, ast.Try):
            yield from _module_statements(statement.body)
            for handler in statement.handlers:
                yield from _module_statements(handler.body)
            yield from _module_statements(statement.orelse)
            yield from _module_statements(statement.finalbody)


def direct_calls(body: Iterable[ast.stmt]) -> Iterator[ast.Call]:
    # Calls in these statements, not inside nested functions, classes, or lambdas.
    pending: list[ast.AST] = list(body)
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Call):
            yield node
        pending.extend(ast.iter_child_nodes(node))


def _absolute_module(node: ast.ImportFrom, package: str) -> str:
    # Resolves a relative from-import against the importing module's package.
    if not node.level:
        return node.module or ""
    parts = package.split(".") if package else []
    base = parts[: len(parts) - (node.level - 1)] if node.level > 1 else parts
    return ".".join([*base, node.module] if node.module else base)


def _import_bindings(node: ast.Import | ast.ImportFrom, package: str) -> dict[str, ImportRef]:
    bindings: dict[str, ImportRef] = {}
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.asname:
                bindings[alias.asname] = ImportRef(alias.name, None)
            else:
                bindings[alias.name.split(".")[0]] = ImportRef(alias.name.split(".")[0], None)
        return bindings
    module = _absolute_module(node, package)
    for alias in node.names:
        if alias.name != "*":
            bindings[alias.asname or alias.name] = ImportRef(module, alias.name)
    return bindings


def _bound_names(target: ast.expr, value: ast.expr | None) -> list[tuple[str, ast.expr | None]]:
    # Names an assignment target binds; unpacking binds each name to an opaque value.
    if isinstance(target, ast.Name):
        return [(target.id, value)]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [pair for element in target.elts for pair in _bound_names(element.value if isinstance(element, ast.Starred) else element, None)]
    return []


def _decorator_name(node: ast.expr) -> str:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Attribute):
        return target.attr
    return target.id if isinstance(target, ast.Name) else ""


def _annotation_head(node: ast.expr) -> str:
    if isinstance(node, ast.Subscript):
        return _annotation_head(node.value)
    if isinstance(node, ast.Attribute):
        return node.attr
    return node.id if isinstance(node, ast.Name) else ""


def _function_kind(node: ast.FunctionDef | ast.AsyncFunctionDef, owner: ClassFacts | None) -> str:
    if owner is None:
        return "function"
    names = {_decorator_name(item) for item in node.decorator_list}
    if "staticmethod" in names:
        return "staticmethod"
    if "classmethod" in names:
        return "classmethod"
    if names & _PROPERTY_DECORATORS:
        return "property"
    return "method"


def _dotted_name(rel: str) -> tuple[str, bool]:
    parts = rel.removesuffix(".py").split("/")
    if parts[-1] == "__init__":
        return ".".join(parts[:-1]), True
    return ".".join(parts), False

"""FILE: lint/core/public_api_contract.py

PURPOSE: Defines the SDK public-API contract (contracts/sdk-public-api.json): its fixed schema as validated records, its canonical rendering, a reader for the committed copy, and the static derivation of its data from vidbyte/__init__.py `__all__` and pyproject.toml.
ROLE IN CODEBASE: scripts/generate-sdk-public-api.py writes the contract through PublicApiCodec.render; rule C016 derives the same data and compares it with the committed file. The vidbyte-cli lint lane (C5) vendors the rendered bytes, so the schema here is a cross-repo contract fixed by the lint implementation plan.
ARCHITECTURE NOTE: Nothing here imports vidbyte. `__all__` is resolved from the AST in statement order (literals, `+`, `*name`, list/tuple/sorted, earlier module names, `__all__` imported from another vidbyte module, `+=`, `.extend`, `.append`), and every other shape raises ExportResolutionError naming the line, so the contract can never silently omit a name.
FUNCTION INVENTORY: PublicApiSchemaError; ApiContractSource, PublicApiData, PublicApiContract records; PublicApiCodec render/parse; CommittedPublicApi.load; ExportResolutionError; AllResolver; PyprojectReader; DerivedPublicApi; PublicApiDeriver.derive().
COMMON MODIFICATION PATTERNS: A schema change is a schema_version bump coordinated with the CLI lane; never rename or add fields in place. Support a new `__all__` idiom by adding one case to AllResolver._sequence and a scratch fixture.
WHAT NOT TO DO: Do not import vidbyte, sort keys alphabetically, change separators, or drop the trailing newline; consumers compare the vendored file byte for byte. Do not guess at an unresolvable `__all__`.
KNOWN EDGE CASES: Duplicate `__all__` entries collapse to one export (S015 owns duplicate detection). A `dynamic` version in pyproject.toml fails closed. Names bound in vidbyte/__init__.py but missing from `__all__` are not exports.
RELATED DOCS: docs/design/lint-sdk-cross-repo-contracts.md; cerredz/Vidbyte lint/core/platform_contract/document.py (the platform-contract twin of this module).
TESTS: python lint/run.py --rule C016; python scripts/generate-sdk-public-api.py --check; scratch fixtures and mutants are recorded in the S4 pull request body.
"""

from __future__ import annotations

import ast
import json
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from lint.core.discovery import SourceCatalog, SourceFile

SCHEMA_VERSION = 1
CONTRACT_REL = "contracts/sdk-public-api.json"
REPOSITORY = "cerredz/Vidbyte-SDK"
GENERATOR_REL = "scripts/generate-sdk-public-api.py"
INIT_REL = "vidbyte/__init__.py"
PYPROJECT_REL = "pyproject.toml"
TOP_LEVEL_KEYS = ("schema_version", "source", "distribution", "version", "exports")
SOURCE_KEYS = ("repository", "commit", "generator")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
_EXPORT_MUTATORS = frozenset({"extend", "append"})
_SEQUENCE_CALLS = frozenset({"list", "tuple", "sorted"})


class PublicApiSchemaError(ValueError):
    """A committed contract field is missing, extra, or holds a value the schema does not allow."""

    def __init__(self, field: str, message: str) -> None:
        # Keeps the field path separate so readers can point at the exact key.
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


def _require(condition: bool, field: str, message: str) -> None:
    # Raises the schema error for one failed field check.
    if not condition:
        raise PublicApiSchemaError(field, message)


@dataclass(frozen=True, slots=True)
class ApiContractSource:
    """Provenance: the owning repository, the commit the generator read, and the generator's path."""

    repository: str
    commit: str
    generator: str

    def __post_init__(self) -> None:
        # Pins every provenance field to the one value this repository may record.
        _require(self.repository == REPOSITORY, "source.repository", f"must be {REPOSITORY!r}, got {self.repository!r}")
        _require(isinstance(self.commit, str) and COMMIT_PATTERN.fullmatch(self.commit) is not None, "source.commit", f"must be a 40-character lowercase commit SHA, got {self.commit!r}")
        _require(self.generator == GENERATOR_REL, "source.generator", f"must be {GENERATOR_REL!r}, got {self.generator!r}")

    def as_json(self) -> dict[str, object]:
        # Returns the fields in schema order.
        return {"repository": self.repository, "commit": self.commit, "generator": self.generator}


@dataclass(frozen=True, slots=True)
class PublicApiData:
    """Every derived field of the contract; equality means the same public surface."""

    distribution: str
    version: str
    exports: tuple[str, ...]

    def __post_init__(self) -> None:
        # Rejects blank identity fields and any export list that is not sorted, unique identifiers.
        _require(isinstance(self.distribution, str) and bool(self.distribution.strip()), "distribution", f"must be a non-empty string, got {self.distribution!r}")
        _require(isinstance(self.version, str) and bool(self.version.strip()), "version", f"must be a non-empty string, got {self.version!r}")
        _require(isinstance(self.exports, tuple) and all(isinstance(name, str) and name.isidentifier() for name in self.exports), "exports", "every export must be a Python identifier string")
        _require(list(self.exports) == sorted(set(self.exports)), "exports", "exports must be sorted and unique")


@dataclass(frozen=True, slots=True)
class PublicApiContract:
    """The complete committed document: provenance plus the derived data."""

    source: ApiContractSource
    data: PublicApiData


class PublicApiCodec:
    """Renders the canonical bytes the CLI vendors, and parses a committed copy back into validated records."""

    def render(self, contract: PublicApiContract) -> str:
        # One export per line keeps an added or removed name to a one-line diff in every consuming repository.
        data = contract.data
        lines = ["{", f'  "schema_version": {SCHEMA_VERSION},', f'  "source": {json.dumps(contract.source.as_json())},', f'  "distribution": {json.dumps(data.distribution)},', f'  "version": {json.dumps(data.version)},']
        if not data.exports:
            lines.append('  "exports": []')
        else:
            lines.append('  "exports": [')
            lines.extend(f"    {json.dumps(name)}{',' if index < len(data.exports) - 1 else ''}" for index, name in enumerate(data.exports))
            lines.append("  ]")
        lines.append("}")
        return "\n".join(lines) + "\n"

    def parse(self, text: str) -> PublicApiContract:
        # Decode, then validate every level, so the first schema problem is reported at the field that is wrong.
        raw = json.loads(text)
        _require(isinstance(raw, dict), "$", "the contract must be a JSON object")
        _require(tuple(raw) == TOP_LEVEL_KEYS, "$", f"top-level keys must be exactly {list(TOP_LEVEL_KEYS)} in that order, got {list(raw)}")
        version_field = raw["schema_version"]
        _require(isinstance(version_field, int) and not isinstance(version_field, bool) and version_field == SCHEMA_VERSION, "schema_version", f"must be {SCHEMA_VERSION}, got {version_field!r}")
        source = raw["source"]
        _require(isinstance(source, dict) and tuple(source) == SOURCE_KEYS, "source", f"must be an object with keys exactly {list(SOURCE_KEYS)} in that order")
        exports = raw["exports"]
        _require(isinstance(exports, list), "exports", "must be a JSON array")
        return PublicApiContract(ApiContractSource(**source), PublicApiData(distribution=raw["distribution"], version=raw["version"], exports=tuple(exports)))

    @staticmethod
    def key_line(text: str, key: str) -> int:
        # Returns the 1-based line of a top-level key in the committed text, or 1 when it is absent.
        match = re.search(rf'^\s*"{re.escape(key)}"\s*:', text, flags=re.MULTILINE)
        return text.count("\n", 0, match.start()) + 1 if match else 1

    @staticmethod
    def export_line(text: str, name: str) -> int:
        # Returns the line of one export entry in the committed text, or the exports key line when it is absent.
        match = re.search(rf'^\s*"{re.escape(name)}",?\s*$', text, flags=re.MULTILINE)
        return text.count("\n", 0, match.start()) + 1 if match else PublicApiCodec.key_line(text, "exports")


@dataclass(frozen=True, slots=True)
class CommittedPublicApi:
    """The committed contract file as read from disk: its text, its parsed form, or the problem that stopped parsing."""

    exists: bool
    text: str
    contract: PublicApiContract | None
    problem_field: str
    problem: str
    problem_line: int

    @classmethod
    def load(cls, path: Path) -> CommittedPublicApi:
        # Read the bytes without newline translation, so a CRLF checkout is caught as non-canonical, not hidden.
        if not path.is_file():
            return cls(False, "", None, "$", "the contract file does not exist", 1)
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            return cls(True, "", None, "$", f"the file is not UTF-8: {exc.reason} at byte {exc.start}", 1)
        codec = PublicApiCodec()
        try:
            return cls(True, text, codec.parse(text), "", "", 0)
        except json.JSONDecodeError as exc:
            return cls(True, text, None, "$", f"the file is not valid JSON: {exc.msg}", exc.lineno)
        except (PublicApiSchemaError, TypeError, KeyError) as exc:
            field = exc.field if isinstance(exc, PublicApiSchemaError) else "$"
            message = exc.message if isinstance(exc, PublicApiSchemaError) else f"unexpected shape: {exc}"
            section = field.split(".")[0]
            return cls(True, text, None, field, message, codec.key_line(text, section) if section in TOP_LEVEL_KEYS else 1)


class ExportResolutionError(RuntimeError):
    """`__all__` or the package version cannot be resolved statically, so no honest contract can be derived."""

    def __init__(self, rel: str, line: int, message: str) -> None:
        # Records where the unresolvable declaration is, for the diagnostic and the generator's output.
        self.rel = rel
        self.line = max(1, line)
        self.message = message
        super().__init__(f"{rel}:{self.line}: {message}")


@dataclass(frozen=True, slots=True)
class _ModuleBindings:
    """What one module's top level binds so far: plain string sequences, imported `__all__` lists, and module aliases."""

    sequences: dict[str, list[tuple[str, str]] | str]
    imported_all: dict[str, str]
    module_aliases: dict[str, str]


class AllResolver:
    """Resolves the `__all__` of one vidbyte module from its AST, following other vidbyte modules when it imports theirs."""

    def __init__(self, modules: Mapping[str, SourceFile]) -> None:
        # Indexes the tracked package modules by path; results are cached per module.
        self.modules = modules
        self._cache: dict[str, tuple[list[tuple[str, str]], int]] = {}

    def resolve(self, rel: str, stack: tuple[str, ...] = ()) -> tuple[list[tuple[str, str]], int]:
        # Walk the module's top-level statements in order, applying every binding and mutation of `__all__`.
        if rel in self._cache:
            return self._cache[rel]
        if rel in stack:
            raise ExportResolutionError(rel, 1, f"`__all__` imports form a cycle: {' -> '.join((*stack, rel))}")
        tree = self._tree(rel)
        bindings = _ModuleBindings(sequences={}, imported_all={}, module_aliases={})
        current: list[tuple[str, str]] | None = None
        first_line = 0
        for node in tree.body:
            self._reject_hidden_mutation(rel, node)
            self._record_imports(rel, node, bindings)
            current, line = self._apply(rel, node, current, bindings, (*stack, rel))
            first_line = first_line or line
        if current is None:
            raise ExportResolutionError(rel, 1, "the module declares no module-level `__all__`")
        self._cache[rel] = (current, first_line)
        return current, first_line

    def resolved_modules(self) -> tuple[str, ...]:
        # Lists every module whose `__all__` was read, so the generator can pin all of them to HEAD.
        return tuple(sorted(self._cache))

    def _tree(self, rel: str) -> ast.Module:
        # Returns the parsed module or fails closed on a missing or unparseable file.
        source = self.modules.get(rel)
        if source is None:
            raise ExportResolutionError(rel, 1, "the module is not a tracked vidbyte source file")
        if source.tree is None:
            raise ExportResolutionError(rel, 1, f"the module does not parse ({source.parse_error})")
        return source.tree

    @staticmethod
    def _reject_hidden_mutation(rel: str, node: ast.stmt) -> None:
        # A compound statement or function that touches `__all__` makes the export list conditional, which no static contract can state.
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Expr, ast.Import, ast.ImportFrom)):
            return
        for inner in ast.walk(node):
            stored = isinstance(inner, (ast.Name, ast.Subscript)) and isinstance(inner.ctx, (ast.Store, ast.Del)) and "__all__" in {item.id for item in ast.walk(inner) if isinstance(item, ast.Name)}
            mutated = isinstance(inner, ast.Attribute) and isinstance(inner.value, ast.Name) and inner.value.id == "__all__"
            declared = isinstance(inner, ast.Global) and "__all__" in inner.names
            if stored or mutated or declared:
                raise ExportResolutionError(rel, getattr(inner, "lineno", node.lineno), "`__all__` is changed inside a compound statement or function, so the export list is conditional; declare it at module level")

    def _record_imports(self, rel: str, node: ast.stmt, bindings: _ModuleBindings) -> None:
        # Remembers `from vidbyte.x import __all__ as y` and module aliases so later expressions can follow them.
        if isinstance(node, ast.ImportFrom):
            base = self._absolute_module(rel, node)
            for alias in node.names:
                bound = alias.asname or alias.name
                bindings.sequences.pop(bound, None)
                if alias.name == "__all__" and base:
                    bindings.imported_all[bound] = base
                elif base and self._module_rel(f"{base}.{alias.name}"):
                    bindings.module_aliases[bound] = f"{base}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    bindings.module_aliases[alias.asname] = alias.name

    def _apply(self, rel: str, node: ast.stmt, current: list[tuple[str, str]] | None, bindings: _ModuleBindings, stack: tuple[str, ...]) -> tuple[list[tuple[str, str]] | None, int]:
        # Applies one statement: binds or extends `__all__`, records another name's sequence, or leaves both alone.
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets: list[ast.expr] = list(node.targets) if isinstance(node, ast.Assign) else [node.target]
            if any(self._mentions_all(target) for target in targets):
                if len(targets) != 1 or not isinstance(targets[0], ast.Name) or node.value is None:
                    raise ExportResolutionError(rel, node.lineno, "`__all__` must be bound by one plain `__all__ = [...]` assignment")
                return self._sequence(rel, node.value, current, bindings, stack), node.lineno
            self._bind_other(rel, targets, node.value, current, bindings, stack)
            return current, 0
        if isinstance(node, ast.AugAssign) and self._mentions_all(node.target):
            if not isinstance(node.op, ast.Add) or current is None:
                raise ExportResolutionError(rel, node.lineno, "`__all__` may only be extended with `+=` after it is bound")
            return current + self._sequence(rel, node.value, current, bindings, stack), node.lineno
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == "__all__":
            return self._mutate(rel, node.value, current, bindings, stack), node.lineno
        return current, 0

    @staticmethod
    def _mentions_all(target: ast.expr) -> bool:
        # True when an assignment target is, or contains, the name `__all__`.
        return any(isinstance(inner, ast.Name) and inner.id == "__all__" for inner in ast.walk(target))

    def _bind_other(self, rel: str, targets: list[ast.expr], value: ast.expr | None, current: list[tuple[str, str]] | None, bindings: _ModuleBindings, stack: tuple[str, ...]) -> None:
        # Records a plain name's string sequence for later `__all__` expressions, or why it cannot be one.
        names = [target.id for target in targets if isinstance(target, ast.Name)]
        for name in names:
            bindings.imported_all.pop(name, None)
            bindings.module_aliases.pop(name, None)
            if value is None:
                bindings.sequences[name] = f"`{name}` is annotated without a value"
                continue
            try:
                bindings.sequences[name] = self._sequence(rel, value, current, bindings, stack)
            except ExportResolutionError as exc:
                bindings.sequences[name] = exc.message

    def _mutate(self, rel: str, call: ast.Call, current: list[tuple[str, str]] | None, bindings: _ModuleBindings, stack: tuple[str, ...]) -> list[tuple[str, str]]:
        # Supports `__all__.extend(seq)` and `__all__.append("Name")`; any other method edits the list unpredictably.
        method = call.func.attr if isinstance(call.func, ast.Attribute) else ""
        if method not in _EXPORT_MUTATORS or current is None or len(call.args) != 1 or call.keywords:
            raise ExportResolutionError(rel, call.lineno, f"`__all__.{method}(...)` cannot be resolved statically; only `.extend(seq)` and `.append(\"Name\")` after binding are supported")
        if method == "append":
            return current + self._sequence(rel, ast.List(elts=[call.args[0]], ctx=ast.Load()), current, bindings, stack)
        return current + self._sequence(rel, call.args[0], current, bindings, stack)

    def _sequence(self, rel: str, node: ast.expr, current: list[tuple[str, str]] | None, bindings: _ModuleBindings, stack: tuple[str, ...]) -> list[tuple[str, str]]:
        # Evaluates one expression to (name, "path:line") pairs, or names the exact construct that blocks a static answer.
        if isinstance(node, (ast.List, ast.Tuple)):
            return [pair for element in node.elts for pair in self._element(rel, element, current, bindings, stack)]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self._sequence(rel, node.left, current, bindings, stack) + self._sequence(rel, node.right, current, bindings, stack)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _SEQUENCE_CALLS and len(node.args) == 1 and not node.keywords:
            return self._sequence(rel, node.args[0], current, bindings, stack)
        if isinstance(node, ast.Name):
            return self._named(rel, node, current, bindings, stack)
        if isinstance(node, ast.Attribute) and node.attr == "__all__" and isinstance(node.value, ast.Name) and node.value.id in bindings.module_aliases:
            return self._foreign(rel, node, bindings.module_aliases[node.value.id], stack)
        raise ExportResolutionError(rel, node.lineno, f"`{ast.unparse(node)}` is not a statically resolvable sequence of strings")

    def _element(self, rel: str, element: ast.expr, current: list[tuple[str, str]] | None, bindings: _ModuleBindings, stack: tuple[str, ...]) -> list[tuple[str, str]]:
        # A list element is a string literal or a starred sequence; nothing else names an export.
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            return [(element.value, f"{rel}:{element.lineno}")]
        if isinstance(element, ast.Starred):
            return self._sequence(rel, element.value, current, bindings, stack)
        raise ExportResolutionError(rel, element.lineno, f"`{ast.unparse(element)}` in an export list is not a string literal")

    def _named(self, rel: str, node: ast.Name, current: list[tuple[str, str]] | None, bindings: _ModuleBindings, stack: tuple[str, ...]) -> list[tuple[str, str]]:
        # A name is `__all__` itself, an earlier module-level sequence, or another module's imported `__all__`.
        if node.id == "__all__" and current is not None:
            return list(current)
        bound = bindings.sequences.get(node.id)
        if isinstance(bound, list):
            return list(bound)
        if isinstance(bound, str):
            raise ExportResolutionError(rel, node.lineno, f"`{node.id}` cannot be resolved: {bound}")
        if node.id in bindings.imported_all:
            return self._foreign(rel, node, bindings.imported_all[node.id], stack)
        raise ExportResolutionError(rel, node.lineno, f"`{node.id}` is not bound earlier in the module to a sequence of strings")

    def _foreign(self, rel: str, node: ast.expr, module: str, stack: tuple[str, ...]) -> list[tuple[str, str]]:
        # Resolves another vidbyte module's `__all__` with the same rules.
        target = self._module_rel(module)
        if target is None:
            raise ExportResolutionError(rel, node.lineno, f"`{ast.unparse(node)}` refers to `{module}`, which is not a tracked vidbyte module")
        return list(self.resolve(target, stack)[0])

    def _absolute_module(self, rel: str, node: ast.ImportFrom) -> str:
        # Turns `from .x import y` into a dotted module name relative to the importing package.
        if node.level == 0:
            return node.module or ""
        package = rel.removesuffix(".py").split("/")[:-1]
        package = package[: len(package) - (node.level - 1)] if node.level > 1 else package
        return ".".join([*package, *(node.module.split(".") if node.module else [])])

    def _module_rel(self, dotted: str) -> str | None:
        # Maps a dotted vidbyte module to its tracked file, preferring a package initializer.
        base = dotted.replace(".", "/")
        for candidate in (f"{base}/__init__.py", f"{base}.py"):
            if candidate in self.modules:
                return candidate
        return None


class PyprojectReader:
    """Reads the distribution name and static version from pyproject.toml."""

    @staticmethod
    def read(text: str) -> tuple[str, str, int, int]:
        # Returns (name, version, name line, version line); a dynamic or missing value fails closed.
        try:
            project = tomllib.loads(text).get("project")
        except tomllib.TOMLDecodeError as exc:
            raise ExportResolutionError(PYPROJECT_REL, 1, f"pyproject.toml is not valid TOML: {exc}") from exc
        if not isinstance(project, dict):
            raise ExportResolutionError(PYPROJECT_REL, 1, "pyproject.toml has no [project] table")
        if "version" in project.get("dynamic", []):
            raise ExportResolutionError(PYPROJECT_REL, PyprojectReader.line_of(text, "dynamic"), "[project].version is dynamic, so the contract version cannot be read statically")
        name, version = project.get("name"), project.get("version")
        if not isinstance(name, str) or not name.strip() or not isinstance(version, str) or not version.strip():
            raise ExportResolutionError(PYPROJECT_REL, 1, "[project] must declare a static string `name` and `version`")
        return name, version, PyprojectReader.line_of(text, "name"), PyprojectReader.line_of(text, "version")

    @staticmethod
    def line_of(text: str, key: str) -> int:
        # Finds `key =` inside the [project] table for diagnostics, falling back to line 1.
        table = re.search(r"^\[project\]\s*$", text, flags=re.MULTILINE)
        start = table.end() if table else 0
        match = re.compile(rf"^{re.escape(key)}\s*=", flags=re.MULTILINE).search(text, start)
        return text.count("\n", 0, match.start()) + 1 if match else 1


@dataclass(frozen=True, slots=True)
class DerivedPublicApi:
    """The contract data derived from source now, plus where each fact came from."""

    data: PublicApiData
    export_origins: dict[str, str]
    all_line: int
    version_line: int
    name_line: int
    read_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        # Every export must have a source location, so a stale-exports diagnostic can point at it.
        missing = [name for name in self.data.exports if name not in self.export_origins]
        if missing:
            raise ValueError(f"DerivedPublicApi has exports without an origin: {missing[:5]}")


class PublicApiDeriver:
    """Derives the public-API contract data from the tracked vidbyte/__init__.py and pyproject.toml."""

    def __init__(self, catalog: SourceCatalog) -> None:
        # Binds the tracked source catalogue the rule and the generator both read.
        self.catalog = catalog

    def derive(self) -> DerivedPublicApi:
        # Resolve `__all__` statically, read the static version, and record every file the derivation read.
        modules = {source.rel: source for source in self.catalog.python_files()}
        resolver = AllResolver(modules)
        names, all_line = resolver.resolve(INIT_REL)
        pyproject = self.catalog.root / PYPROJECT_REL
        if not pyproject.is_file():
            raise ExportResolutionError(PYPROJECT_REL, 1, "pyproject.toml is missing")
        distribution, version, name_line, version_line = PyprojectReader.read(pyproject.read_text(encoding="utf-8"))
        origins: dict[str, str] = {}
        for name, origin in names:
            origins.setdefault(name, origin)
        read = tuple(sorted({PYPROJECT_REL, *resolver.resolved_modules()}))
        data = PublicApiData(distribution=distribution, version=version, exports=tuple(sorted(origins)))
        return DerivedPublicApi(data=data, export_origins=origins, all_line=all_line, version_line=version_line, name_line=name_line, read_paths=read)

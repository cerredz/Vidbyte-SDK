"""FILE: tests/features/harness_threads/test_harness_threads_static_policy.py

PURPOSE: The mechanical source rules of the harness modules (AC-14, INV-15, FR-14, INV-20): every module under vidbyte/harnesses/native holds at module level only a docstring, imports, classes, a literal `__all__` list and (in `__init__` modules) public names bound to class attributes; its only str/bytes/int/float constants are docstrings, `__all__` strings, "", 0 and 1; and none of them imports vidbyte.tools.
ROLE IN CODEBASE: Start here when review asks where a flag, a path segment, a JSON member name or a message template lives: it must be an enum member in vidbyte/lib/enums/native_threads.py or a constant in vidbyte/lib/constants/native_threads.py, never a literal in a harness module.
ARCHITECTURE NOTE: Source files are read and parsed with `ast`; nothing is imported, so this file runs before and after the feature lands. The module list must include the files §12.3 names, so an empty or misplaced package cannot pass by having nothing to scan.
FUNCTION INVENTORY: native_modules lists and parses the package's source files; imported_modules resolves an import statement to absolute module names; docstring_nodes finds the docstring constants of a tree; all_strings finds the module-level `__all__` string constants; module_level_problem names a statement rule 1 forbids; the test_* functions are one rule each.
COMMON MODIFICATION PATTERNS: A harness module that needs a value adds it to vidbyte/lib/constants/native_threads.py or an enum, never an exception here.
WHAT NOT TO DO IN THIS FILE: Do not add allow-lists of files or literals; INV-15 has none.
KNOWN EDGE CASES: An f-string's literal parts are ast.Constant nodes, so `f"--model={m}"` breaks rule 2 (as INV-15 says). `-1` parses as a unary minus on the constant 1 and is therefore not caught; INV-15 is stated over ast.Constant nodes.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-functions/spec.md §6.1 INV-15, INV-20, §6.2 AC-14, §12.3 rows 32-44; docs/spec/harness-thread-helpers-skills/spec.md §6.1 INV-15, INV-20, §12.3 rows 11-30
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_static_policy.py
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[3] / "vidbyte" / "harnesses" / "native"
NAMED_MODULES = (
    "__init__.py", "grok/__init__.py", "grok/threads.py", "grok/wire.py", "opencode/__init__.py", "opencode/threads.py", "opencode/wire.py",
    "muse/__init__.py", "muse/threads.py", "muse/wire.py", "muse/launcher.py", "hostkit/errors.py", "hostkit/launcher.py", "hostkit/skills.py",
    # harness-thread-helpers-skills §12.3: the 10 new modules.
    "grok/store.py", "grok/helpers.py", "grok/commands.py", "opencode/helpers.py", "opencode/commands.py",
    "muse/children.py", "muse/helpers.py", "muse/commands.py", "hostkit/listing.py", "hostkit/evidence.py",
)
ALLOWED_VALUES = ("", 0, 1)
FORBIDDEN_IMPORT = "vidbyte.tools"


def native_modules(*, require_named: bool = True) -> dict[str, ast.Module]:
    found = {path.relative_to(PACKAGE).as_posix(): ast.parse(path.read_text(encoding="utf-8"), filename=str(path)) for path in sorted(PACKAGE.rglob("*.py"))}
    missing = [name for name in NAMED_MODULES if name not in found]
    assert not (require_named and missing), f"§12.3 names these modules under vidbyte/harnesses/native, and they are missing: {missing}"
    return found


def imported_modules(name: str, node: ast.AST) -> list[str]:
    # Absolute module names an import statement reaches; relative
    # imports are resolved against the module's package.
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []
    if node.level == 0:
        return [node.module or ""]
    package = ["vidbyte", "harnesses", "native", *name.removesuffix(".py").split("/")]
    package = package[:-1]
    base = package[: len(package) - (node.level - 1)]
    return [".".join([*base, *([node.module] if node.module else [])])]


def docstring_nodes(tree: ast.Module) -> set[int]:
    owners = [tree, *(node for node in ast.walk(tree) if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)))]
    found: set[int] = set()
    for owner in owners:
        first = owner.body[0] if owner.body else None
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            found.add(id(first.value))
    return found


def all_strings(tree: ast.Module) -> set[int]:
    found: set[int] = set()
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and [getattr(target, "id", None) for target in statement.targets] == ["__all__"] and isinstance(statement.value, ast.List):
            found.update(id(element) for element in statement.value.elts if isinstance(element, ast.Constant) and isinstance(element.value, str))
    return found


def module_level_problem(statement: ast.stmt, index: int, is_init: bool) -> str | None:
    if index == 0 and isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
        return None
    if isinstance(statement, (ast.Import, ast.ImportFrom, ast.ClassDef)):
        return None
    if isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
        name, value = statement.targets[0].id, statement.value
        if name == "__all__" and isinstance(value, ast.List) and all(isinstance(element, ast.Constant) and isinstance(element.value, str) for element in value.elts):
            return None
        if is_init and not name.startswith("_") and isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
            return None
    return f"line {statement.lineno}: {type(statement).__name__} `{ast.unparse(statement).splitlines()[0][:80]}`"


def test_module_level_holds_only_docstring_imports_classes_all_and_init_bindings() -> None:
    # INV-15 rule 1 / FR-14: no module-level constants, functions or
    # statements in any harness module.
    problems = []
    for name, tree in native_modules().items():
        is_init = name.endswith("__init__.py")
        problems += [f"{name} {problem}" for index, statement in enumerate(tree.body) if (problem := module_level_problem(statement, index, is_init)) is not None]
    assert not problems, "INV-15 rule 1: module level may hold only a docstring, imports, classes, a literal __all__ list and __init__ bindings:\n" + "\n".join(problems)


def test_only_docstrings_all_entries_and_empty_zero_one_are_literals() -> None:
    # INV-15 rule 2 / AC-14: every other str, bytes, int or float comes
    # from an enum or vidbyte.lib.constants.native_threads.
    problems = []
    for name, tree in native_modules().items():
        allowed = docstring_nodes(tree) | all_strings(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or isinstance(node.value, bool) or not isinstance(node.value, (str, bytes, int, float)):
                continue
            if id(node) in allowed or (type(node.value) in (str, int) and node.value in ALLOWED_VALUES):
                continue
            problems.append(f"{name} line {node.lineno}: {node.value!r}"[:160])
    assert not problems, f"INV-15 rule 2: {len(problems)} literal(s) belong in vidbyte.lib.enums.native_threads or vidbyte.lib.constants.native_threads:\n" + "\n".join(problems[:60])


def test_harness_modules_never_import_the_tools_layer() -> None:
    # INV-20: vidbyte.harnesses.native.* imports nothing from
    # vidbyte.tools (the stdio peer transport is gone, D-1).
    problems = []
    for name, tree in native_modules(require_named=False).items():
        for node in ast.walk(tree):
            problems += [f"{name} line {node.lineno}: {target}" for target in imported_modules(name, node) if target == FORBIDDEN_IMPORT or target.startswith(FORBIDDEN_IMPORT + ".")]
    assert not problems, "INV-20: harness modules import vidbyte.tools:\n" + "\n".join(problems)
